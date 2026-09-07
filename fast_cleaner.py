"""
SmartCleaner-AI Engine - Standalone Manga/Webtoon Inpainting & Speech Bubble Cleaner

Features:
1. Deep learning text & speech bubble detection (comictextdetector + YOLOv8).
2. Magic wand interactive contour & floodfill bubble detection.
3. Smart adaptive inpainting (instant flat-white cleaning in <0.005s + deep AI inpainting via IOPaint).
4. Multi-threaded batch page cleaning.
"""

import argparse
import gc
import json
import math
import os
import sys
import time
import threading
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Union, Optional, List, Tuple

import copy
import cv2
import numpy as np
import torch
from PIL import Image
from loguru import logger
from pcleaner.iopaint_client import generate_bubble_lasso_polygons

# Add project directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Optimize PyTorch CPU threads
if hasattr(torch, "set_num_threads"):
    try:
        max_threads = min(8, os.cpu_count() or 4)
        torch.set_num_threads(max_threads)
        torch.set_num_interop_threads(max(2, max_threads // 2))
    except Exception:
        pass

try:
    torch.set_float32_matmul_precision('medium')
except Exception:
    pass

from pcleaner.comic_text_detector.inference import TextDetector
from pcleaner.iopaint_client import (
    IOPaintClient,
    SUPPORTED_IOPAINT_MODELS,
    generate_page_mask,
    inpaint_manga_page,
    smart_adaptive_inpaint_page,
    inpaint_single_bubble,
    classify_bubble_background
)

MODEL_URL_PT = "https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/comictextdetector.pt"
MODEL_URL_ONNX = "https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/comictextdetector.pt.onnx"

_detector_model_instance = None


def ensure_model_exists(target_path: str = None, device: str = "auto", progress_callback=None) -> str:
    if target_path and os.path.exists(target_path):
        return target_path

    base_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(base_dir, "models")
    os.makedirs(models_dir, exist_ok=True)

    pt_path = os.path.join(models_dir, "comictextdetector.pt")
    onnx_path = os.path.join(models_dir, "comictextdetector.pt.onnx")

    # If running on CPU, ONNX with OpenCV DNN is 10x faster
    if device == "cpu" and os.path.exists(onnx_path) and os.path.getsize(onnx_path) > 1_000_000:
        return onnx_path

    if os.path.exists(pt_path):
        return pt_path
    if os.path.exists(onnx_path):
        return onnx_path

    url = MODEL_URL_PT
    save_path = pt_path

    logger.info(f"Model not found. Downloading detector model from {url}...")
    if progress_callback:
        progress_callback("DOWNLOADING_MODEL:0:Downloading AI detector model (~80MB)...")

    def _reporthook(count, block_size, total_size):
        if total_size > 0 and progress_callback:
            percent = int(count * block_size * 100 / total_size)
            progress_callback(f"DOWNLOADING_MODEL:{percent}:Downloading detector model: {percent}%")

    try:
        urllib.request.urlretrieve(url, save_path, reporthook=_reporthook)
        logger.info(f"Downloaded model successfully to {save_path}")
        return save_path
    except Exception as e:
        logger.error(f"Failed to download model: {e}")
        raise RuntimeError(f"Could not download model automatically: {e}")


_detector_lock = threading.Lock()
_detector_model_instance = None


def get_text_detector(model_path: str = None, device: str = "auto", progress_callback=None):
    global _detector_model_instance
    if _detector_model_instance is not None:
        return _detector_model_instance

    with _detector_lock:
        if _detector_model_instance is not None:
            return _detector_model_instance

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        
        path = ensure_model_exists(model_path, device=device, progress_callback=progress_callback)
        logger.info(f"Loading TextDetector model from {path} onto {device}...")
        inst = TextDetector(
            model_path=path,
            input_size=1024,
            device=device,
            act='leaky'
        )
        try:
            # Pre-warm detector with a dummy 1024x1024 tensor so first user page is instantaneous
            dummy_img = np.zeros((1024, 1024, 3), dtype=np.uint8)
            _ = inst(dummy_img, refine_mode=None, keep_undetected_mask=False)
        except Exception:
            pass
        _detector_model_instance = inst
    return _detector_model_instance


def read_image_unicode(path: Union[str, Path, np.ndarray], flags: int = cv2.IMREAD_COLOR) -> Optional[np.ndarray]:
    """
    Safely reads an image from a path that may contain non-ASCII / Unicode characters
    (e.g. Korean, Arabic, Japanese, Chinese, special characters) on Windows and POSIX.
    Supports receiving an already loaded numpy array.
    """
    if path is None:
        return None
    if isinstance(path, np.ndarray):
        return path
    if isinstance(path, (str, Path)) and not str(path).strip():
        return None
    p_str = str(path)
    if not os.path.exists(p_str):
        return None
    try:
        data = np.fromfile(p_str, dtype=np.uint8)
        if data is not None and len(data) > 0:
            img = cv2.imdecode(data, flags)
            if img is not None:
                return img
    except Exception:
        pass
    try:
        return cv2.imread(p_str, flags)
    except Exception:
        return None


def write_image_unicode(path: Union[str, Path], img: np.ndarray, quality: int = 95) -> bool:
    """
    Safely writes an image to a path that may contain non-ASCII / Unicode characters.
    """
    try:
        p_str = str(path)
        ext = os.path.splitext(p_str)[1].lower() or ".png"
        params = []
        if ext in (".jpg", ".jpeg"):
            params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        elif ext == ".webp":
            params = [int(cv2.IMWRITE_WEBP_QUALITY), quality]
        elif ext == ".png":
            params = [int(cv2.IMWRITE_PNG_COMPRESSION), 4]

        success, buf = cv2.imencode(ext, img, params)
        if success:
            buf.tofile(p_str)
            return True
        return False
    except Exception:
        return False


def preload_image(img_path: str):
    try:
        return read_image_unicode(img_path)
    except Exception:
        return None


def detect_bubble_at_point(
    image_path: str,
    click_x: int,
    click_y: int,
    preloaded_img=None,
    padding: int = 5,
    min_w: int = 20,
    min_h: int = 20,
    max_search_radius: int = 400
):
    try:
        if isinstance(image_path, np.ndarray):
            img = image_path
        elif preloaded_img is not None:
            img = preloaded_img
        else:
            img = read_image_unicode(image_path)
        if img is None:
            return None

        h, w = img.shape[:2]
        if click_x < 0 or click_x >= w or click_y < 0 or click_y >= h:
            return None

        x1_roi = max(0, click_x - max_search_radius)
        y1_roi = max(0, click_y - max_search_radius)
        x2_roi = min(w, click_x + max_search_radius)
        y2_roi = min(h, click_y + max_search_radius)

        roi = img[y1_roi:y2_roi, x1_roi:x2_roi]
        seed_x = click_x - x1_roi
        seed_y = click_y - y1_roi

        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        blurred = cv2.GaussianBlur(gray_roi, (5, 5), 0)
        edges = cv2.Canny(blurred, 30, 120)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        closed_edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        contours, hierarchy = cv2.findContours(closed_edges, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        if contours:
            for cnt in contours:
                if cv2.pointPolygonTest(cnt, (float(seed_x), float(seed_y)), False) >= 0:
                    bx, by, bw, bh = cv2.boundingRect(cnt)
                    if bw >= min_w and bh >= min_h and bw < roi.shape[1] * 0.96 and bh < roi.shape[0] * 0.96:
                        area = cv2.contourArea(cnt)
                        if area > (min_w * min_h):
                            candidates.append((area, bx, by, bw, bh))

        if candidates:
            candidates.sort(key=lambda c: c[0])
            _, bx, by, bw, bh = candidates[0]
            global_x = max(0, x1_roi + bx - padding)
            global_y = max(0, y1_roi + by - padding)
            global_w = min(w - global_x, bw + 2 * padding)
            global_h = min(h - global_y, bh + 2 * padding)
            return (int(global_x), int(global_y), int(global_w), int(global_h))

        seed_val = int(gray_roi[seed_y, seed_x])
        thresh_val = max(175, seed_val - 45)
        _, binary = cv2.threshold(gray_roi, thresh_val, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        mask = np.zeros((closed.shape[0] + 2, closed.shape[1] + 2), dtype=np.uint8)
        cv2.floodFill(closed, mask, (seed_x, seed_y), 128)
        flooded = (closed == 128).astype(np.uint8) * 255

        contours, _ = cv2.findContours(flooded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            valid_cnts = [c for c in contours if cv2.pointPolygonTest(c, (float(seed_x), float(seed_y)), False) >= 0]
            if valid_cnts:
                best_cnt = max(valid_cnts, key=cv2.contourArea)
                bx, by, bw, bh = cv2.boundingRect(best_cnt)
                if bw >= min_w and bh >= min_h and bw < gray_roi.shape[1] * 0.94 and bh < gray_roi.shape[0] * 0.94:
                    global_x = max(0, x1_roi + bx - padding)
                    global_y = max(0, y1_roi + by - padding)
                    global_w = min(w - global_x, bw + 2 * padding)
                    global_h = min(h - global_y, bh + 2 * padding)
                    return (int(global_x), int(global_y), int(global_w), int(global_h))

        return None
    except Exception as e:
        logger.warning(f"Magic wand detection error: {e}")
        return None


def deduplicate_and_merge_bubbles(bubbles: list, iou_thresh: float = 0.85, containment_thresh: float = 0.90) -> list:
    """
    Deduplicates only near-identical speech bubble detections (e.g. across chunk boundaries).
    Preserves connected / adjacent distinct speech bubbles as separate independent entities.
    """
    if not bubbles:
        return []

    # Sort bubbles by area descending
    sorted_b = sorted(bubbles, key=lambda b: (b.get('width', 0) * b.get('height', 0)), reverse=True)
    merged_list = []

    for b in sorted_b:
        x1 = b['x']
        y1 = b['y']
        x2 = b['x'] + b['width']
        y2 = b['y'] + b['height']
        area = max(1, b['width'] * b['height'])
        bcx = (x1 + x2) / 2.0
        bcy = (y1 + y2) / 2.0

        matched = False
        for m in merged_list:
            mx1 = m['x']
            my1 = m['y']
            mx2 = m['x'] + m['width']
            my2 = m['y'] + m['height']
            m_area = max(1, m['width'] * m['height'])
            mcx = (mx1 + mx2) / 2.0
            mcy = (my1 + my2) / 2.0

            # Intersection
            inter_x1 = max(x1, mx1)
            inter_y1 = max(y1, my1)
            inter_x2 = min(x2, mx2)
            inter_y2 = min(y2, my2)

            if inter_x2 > inter_x1 and inter_y2 > inter_y1:
                inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
                union_area = area + m_area - inter_area
                iou = inter_area / max(1, union_area)
                containment = inter_area / min(area, m_area)
                center_dist = math.hypot(bcx - mcx, bcy - mcy)

                # Only merge if it's a true near-duplicate detection of the same bubble
                # (e.g. chunk overlap where boxes virtually match or one slice contained the other).
                # Never merge two distinct bubbles that have different text line centers!
                max_allowed_dist = max(35.0, min(m['height'], b['height']) * 0.60)
                if (iou >= iou_thresh or (containment >= containment_thresh and center_dist < max_allowed_dist)):
                    new_x1 = min(x1, mx1)
                    new_y1 = min(y1, my1)
                    new_x2 = max(x2, mx2)
                    new_y2 = max(y2, my2)
                    m['x'] = new_x1
                    m['y'] = new_y1
                    m['width'] = new_x2 - new_x1
                    m['height'] = new_y2 - new_y1

                    if 'text_x' in b and 'text_x' in m:
                        tx1 = min(b['text_x'], m['text_x'])
                        ty1 = min(b['text_y'], m['text_y'])
                        tx2 = max(b['text_x'] + b.get('text_width', b['width']), m['text_x'] + m.get('text_width', m['width']))
                        ty2 = max(b['text_y'] + b.get('text_height', b['height']), m['text_y'] + m.get('text_height', m['height']))
                        m['text_x'] = tx1
                        m['text_y'] = ty1
                        m['text_width'] = tx2 - tx1
                        m['text_height'] = ty2 - ty1

                    if 'lines' in b and b['lines']:
                        if 'lines' not in m or not m['lines']:
                            m['lines'] = []
                        # Avoid duplicating identical lines across chunk overlaps
                        for bl in b['lines']:
                            b_pts = np.array(bl)
                            is_dup = False
                            for ml in m['lines']:
                                m_pts = np.array(ml)
                                if b_pts.shape == m_pts.shape and np.mean(np.abs(b_pts - m_pts)) < 12.0:
                                    is_dup = True
                                    break
                            if not is_dup:
                                m['lines'].append(bl)

                    if m.get('lines'):
                        m_polys = generate_bubble_lasso_polygons(m['lines'])
                        m['polygons'] = m_polys
                        m['polygon'] = m_polys[0] if len(m_polys) == 1 else (m_polys[0] if m_polys else None)

                    matched = True
                    break

        if not matched:
            merged_list.append(b.copy())

    # Sort top-to-bottom and re-index IDs
    merged_list.sort(key=lambda b: (b['y'], b['x']))
    for idx, b in enumerate(merged_list):
        b['id'] = idx + 1

    return merged_list


def split_multibubble_block(lines: list, max_normal_line_gap_ratio: float = 0.85) -> list:
    """
    Splits a detected TextBlock's lines into separate bubble line-groups if they belong to different connected bubbles.
    Handles both vertical gap separation, center alignment shift, and horizontal separation.
    Preserves unified multi-line paragraphs as a single group.
    Returns a list of line-groups: [[line1, line2], [line3, line4, line5]]
    """
    if not lines or not isinstance(lines, (list, tuple)):
        return []
    if len(lines) == 1:
        return [lines]

    line_infos = []
    for l in lines:
        if not isinstance(l, (list, tuple)):
            continue
        try:
            pts = np.array(l, dtype=np.float32)
            if pts.ndim == 1 and len(pts) >= 6:
                pts = pts.reshape(-1, 2)
            if pts.ndim != 2 or pts.shape[0] < 3:
                continue
            min_x = float(np.min(pts[:, 0]))
            max_x = float(np.max(pts[:, 0]))
            min_y = float(np.min(pts[:, 1]))
            max_y = float(np.max(pts[:, 1]))
            h = max(8.0, max_y - min_y)
            w = max(8.0, max_x - min_x)
            line_infos.append({
                'line_pts': l,
                'min_x': min_x, 'max_x': max_x,
                'min_y': min_y, 'max_y': max_y,
                'height': h, 'width': w
            })
        except Exception:
            continue

    if len(line_infos) <= 1:
        return [lines]

    def _are_in_same_bubble(l1, l2):
        overlap_x = max(0.0, min(l1['max_x'], l2['max_x']) - max(l1['min_x'], l2['min_x']))
        min_w = max(1.0, min(l1['width'], l2['width']))
        overlap_x_ratio = overlap_x / min_w

        overlap_y = max(0.0, min(l1['max_y'], l2['max_y']) - max(l1['min_y'], l2['min_y']))
        min_h = max(1.0, min(l1['height'], l2['height']))
        overlap_y_ratio = overlap_y / min_h

        vert_gap = max(0.0, max(l1['min_y'], l2['min_y']) - min(l1['max_y'], l2['max_y']))
        horiz_gap = max(0.0, max(l1['min_x'], l2['min_x']) - min(l1['max_x'], l2['max_x']))
        avg_h = (l1['height'] + l2['height']) / 2.0

        c1_x = (l1['min_x'] + l1['max_x']) / 2.0
        c2_x = (l2['min_x'] + l2['max_x']) / 2.0
        center_dist_x = abs(c1_x - c2_x)
        max_w = max(l1['width'], l2['width'])
        is_center_shifted = (center_dist_x > min_w * 0.60 and center_dist_x > max_w * 0.35)

        # Standard horizontal text lines: reasonable horizontal overlap and normal vertical gap
        if (overlap_x_ratio >= 0.25 or overlap_x > 15.0) and vert_gap <= (avg_h * max_normal_line_gap_ratio) and not (is_center_shifted and vert_gap > avg_h * 0.60):
            return True
        # Vertical Japanese text lines: high vertical overlap and small horizontal gap
        if overlap_y_ratio >= 0.35 and horiz_gap <= min(avg_h * 1.1, 50.0):
            return True
        # Very close proximity (lines close to each other inside a bubble)
        center_dist = math.hypot(c1_x - c2_x, (l1['min_y'] + l1['max_y'])/2 - (l2['min_y'] + l2['max_y'])/2)
        if center_dist < avg_h * 1.3 and vert_gap <= avg_h * 0.50:
            return True

        return False

    # Build adjacency and find connected components
    n = len(line_infos)
    adj = {i: [] for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            if _are_in_same_bubble(line_infos[i], line_infos[j]):
                adj[i].append(j)
                adj[j].append(i)

    visited = [False] * n
    split_groups = []

    # Sort lines top-to-bottom to preserve reading order
    order_indices = sorted(range(n), key=lambda idx: (line_infos[idx]['min_y'], line_infos[idx]['min_x']))

    for start_node in order_indices:
        if visited[start_node]:
            continue
        component = []
        queue = [start_node]
        visited[start_node] = True
        while queue:
            node = queue.pop(0)
            component.append(node)
            for neighbor in adj[node]:
                if not visited[neighbor]:
                    visited[neighbor] = True
                    queue.append(neighbor)

        # Sort lines inside this group top-to-bottom
        component.sort(key=lambda idx: (line_infos[idx]['min_y'], line_infos[idx]['min_x']))
        split_groups.append([line_infos[idx]['line_pts'] for idx in component])

    return split_groups


def detect_bubbles_for_cleaning(
    image_path: str,
    model_path: str = None,
    device: str = "auto",
    progress_callback=None,
    preloaded_img=None,
    mask_padding: int = 0,
    snap_to_bubbles: bool = True,
    cancel_callback=None
) -> list:
    """
    Detects all speech bubbles and text blocks on a manga page.
    Splits multi-bubble connected blocks into individual bubble entries.
    """
    if cancel_callback and cancel_callback():
        return []

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    if device == "cuda" and torch.cuda.is_available():
        torch.backends.cudnn.benchmark = True

    model = get_text_detector(model_path=model_path, device=device, progress_callback=progress_callback)

    if isinstance(image_path, np.ndarray):
        img = image_path
    elif preloaded_img is not None:
        img = preloaded_img
    else:
        img = read_image_unicode(image_path)

    if img is None:
        raise ValueError(f"Could not read image at path: {image_path}")

    if cancel_callback and cancel_callback():
        return []

    with torch.inference_mode():
        h, w = img.shape[:2]
        # Keep chunk height balanced with width for optimal panel context and character resolution.
        # Slicing at up to 2048px with 300px overlap prevents bubble fragmentation across chunk seams,
        # provides ample context for Korean/Japanese punctuation, and maximizes detection speed.
        max_chunk_height = max(1600, min(2048, int(w * 2.2)))
        chunk_overlap = 300
        step = max_chunk_height - chunk_overlap

        if h <= max_chunk_height:
            _, _, blk_list = model(img, refine_mode=None, keep_undetected_mask=False)
        else:
            blk_list = []
            current_y = 0
            current_chunk = 1
            estimated_chunks = math.ceil((h - chunk_overlap) / step)

            while current_y < h:
                if cancel_callback and cancel_callback():
                    return []

                end_y = min(h, current_y + max_chunk_height)
                chunk_img = np.ascontiguousarray(img[current_y:end_y, :])

                # Skip completely uniform or empty white/black gutters
                if chunk_img.shape[0] > 50 and chunk_img.std() > 5.0:
                    if progress_callback:
                        progress_callback(f"CHUNK_PROGRESS:{current_chunk}/{estimated_chunks}:Processing chunk {current_chunk}/{estimated_chunks}")

                    try:
                        _, _, chunk_blks = model(chunk_img, refine_mode=None, keep_undetected_mask=False)
                        if chunk_blks:
                            for blk in chunk_blks:
                                blk.xyxy[1] += current_y
                                blk.xyxy[3] += current_y
                                if hasattr(blk, 'lines') and blk.lines is not None:
                                    for line in blk.lines:
                                        for point in line:
                                            point[1] += current_y
                                blk_list.append(blk)
                    except Exception as chunk_err:
                        logger.warning(f"Warning analyzing chunk {current_chunk}/{estimated_chunks}: {chunk_err}")

                if end_y >= h:
                    break
                current_y += step
                current_chunk += 1

    # Immediately decompose any multi-bubble blocks into separate TextBlock objects
    expanded_blk_list = []
    for blk in blk_list:
        b_lines = []
        if hasattr(blk, 'lines') and blk.lines is not None and len(blk.lines) > 0:
            for l in blk.lines:
                try:
                    if hasattr(l, 'tolist'):
                        line_pts = l.tolist()
                    elif isinstance(l, (list, tuple)):
                        line_pts = [[int(p[0]), int(p[1])] for p in l]
                    else:
                        line_pts = []
                    if line_pts:
                        b_lines.append(line_pts)
                except Exception:
                    pass

        line_groups = split_multibubble_block(b_lines) if b_lines else [[]]
        if len(line_groups) <= 1:
            expanded_blk_list.append(blk)
        else:
            for grp in line_groups:
                pts_arr = np.array([pt for l in grp for pt in l], dtype=np.int32)
                min_x = int(np.min(pts_arr[:, 0]))
                min_y = int(np.min(pts_arr[:, 1]))
                max_x = int(np.max(pts_arr[:, 0]))
                max_y = int(np.max(pts_arr[:, 1]))
                new_blk = copy.deepcopy(blk)
                new_blk.xyxy = [min_x, min_y, max_x, max_y]
                new_blk.lines = grp
                new_blk.raw_text_xyxy = [min_x, min_y, max_x, max_y]
                expanded_blk_list.append(new_blk)

    blk_list = expanded_blk_list

    if snap_to_bubbles:
        try:
            from pcleaner.bubble_detector import detect_speech_bubbles, match_and_expand_bubbles
            yolo_bubbles = detect_speech_bubbles(img, device=device)
            if yolo_bubbles:
                blk_list = match_and_expand_bubbles(blk_list, yolo_bubbles, img.shape, mask_padding=mask_padding)
        except Exception as e:
            logger.warning(f"YOLOv8 bubble detection error: {e}")

    bubbles_raw = []
    bubble_counter = 1

    for idx, blk in enumerate(blk_list):
        b_lines = []
        if hasattr(blk, 'lines') and blk.lines is not None and len(blk.lines) > 0:
            for l in blk.lines:
                try:
                    if hasattr(l, 'tolist'):
                        line_pts = l.tolist()
                    elif isinstance(l, (list, tuple)):
                        line_pts = [[int(p[0]), int(p[1])] for p in l]
                    else:
                        line_pts = []
                    if line_pts:
                        b_lines.append(line_pts)
                except Exception:
                    pass

        raw_x1, raw_y1, raw_x2, raw_y2 = int(blk.xyxy[0]), int(blk.xyxy[1]), int(blk.xyxy[2]), int(blk.xyxy[3])
        if b_lines:
            all_pts = [pt for l in b_lines for pt in l]
            pts_arr = np.array(all_pts, dtype=np.int32)
            lx1 = int(np.min(pts_arr[:, 0]))
            ly1 = int(np.min(pts_arr[:, 1]))
            lx2 = int(np.max(pts_arr[:, 0]))
            ly2 = int(np.max(pts_arr[:, 1]))
            # Merge line bounding box with block detector bounding box (which includes trailing punctuation marks,
            # dots, exclamation marks, question marks, and dashes not converted to standalone line polygons)
            tx1 = min(raw_x1, max(0, lx1 - 3))
            ty1 = min(raw_y1, max(0, ly1 - 3))
            tx2 = max(raw_x2, min(img.shape[1], lx2 + 3))
            ty2 = max(raw_y2, min(img.shape[0], ly2 + 3))

            # If block bounds extend beyond line contours (e.g. trailing punctuation like "?!", "...", "-"),
            # ensure all_pts includes the extended corners so convex hull polygon covers the punctuation
            if raw_x2 > lx2 + 4 or raw_x1 < lx1 - 4 or raw_y2 > ly2 + 4 or raw_y1 < ly1 - 4:
                all_pts.extend([[tx1, ty1], [tx2, ty1], [tx2, ty2], [tx1, ty2]])
                pts_arr = np.array(all_pts, dtype=np.int32)

            if len(all_pts) >= 3:
                try:
                    hull = cv2.convexHull(pts_arr)
                    polygon = hull.reshape(-1, 2).tolist()
                except Exception:
                    polygon = None
            else:
                polygon = None
        else:
            tx1, ty1, tx2, ty2 = raw_x1, raw_y1, raw_x2, raw_y2
            polygon = None

        pad_amount = mask_padding if mask_padding > 0 else (int(min(tx2 - tx1, ty2 - ty1) * 0.08) + 5)
        x1 = max(0, tx1 - pad_amount)
        y1 = max(0, ty1 - pad_amount)
        x2 = min(img.shape[1], tx2 + pad_amount)
        y2 = min(img.shape[0], ty2 + pad_amount)
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)

        bg_type = "white"
        try:
            crop = img[y1:y2, x1:x2]
            if crop.size > 0:
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
                border_mean = (float(np.mean(gray[:2, :])) + float(np.mean(gray[-2:, :])) + float(np.mean(gray[:, :2])) + float(np.mean(gray[:, -2:]))) / 4.0
                if border_mean >= 195 and float(np.mean(gray)) >= 170:
                    bg_type = "white"
                else:
                    bg_type = "complex"
        except Exception:
            pass

        bubbles_raw.append({
            "id": bubble_counter,
            "x": x1,
            "y": y1,
            "width": w,
            "height": h,
            "text_x": tx1,
            "text_y": ty1,
            "text_width": max(1, tx2 - tx1),
            "text_height": max(1, ty2 - ty1),
            "lines": b_lines,
            "polygons": [polygon] if polygon else None,
            "polygon": polygon,
            "bg_type": bg_type,
            "status": "pending",
            "confidence": getattr(blk, 'confidence', 0.95)
        })
        bubble_counter += 1

    # Deduplicate and merge heavily overlapping bubbles (only merge true duplicate detections)
    final_bubbles = deduplicate_and_merge_bubbles(bubbles_raw, iou_thresh=0.60, containment_thresh=0.75)
    return final_bubbles


def clean_page(
    image_path: str,
    output_path: str = None,
    iopaint_url: str = "http://127.0.0.1:8080",
    iopaint_model: str = "anime-lama",
    iopaint_dilation: int = 5,
    adaptive_mode: bool = True,
    snap_to_bubbles: bool = True,
    mask_padding: int = 0,
    progress_callback=None,
    cancel_callback=None
) -> tuple:
    if progress_callback:
        progress_callback(f"🔍 Detecting bubbles on {Path(image_path).name}...")

    bubbles = detect_bubbles_for_cleaning(
        image_path=image_path,
        mask_padding=mask_padding,
        snap_to_bubbles=snap_to_bubbles,
        progress_callback=progress_callback,
        cancel_callback=cancel_callback
    )

    if not bubbles:
        if progress_callback:
            progress_callback("ℹ️ No text or speech bubbles detected.")
        return image_path, []

    if cancel_callback and cancel_callback():
        return image_path, bubbles

    adaptive_label = "Adaptive Fast Fill" if adaptive_mode else iopaint_model
    if progress_callback:
        progress_callback(f"🧹 Inpainting {len(bubbles)} detected bubbles ({adaptive_label})...")

    client = IOPaintClient(server_url=iopaint_url)

    from PIL import Image
    eff_dilation = max(iopaint_dilation, mask_padding)
    for b in bubbles:
        if mask_padding > 0:
            b["mask_padding"] = max(b.get("mask_padding", 0), mask_padding)

    if adaptive_mode:
        cleaned_img, _ = smart_adaptive_inpaint_page(
            server_url=iopaint_url,
            image_input=image_path,
            bubbles=bubbles,
            deep_model=iopaint_model,
            dilation=eff_dilation,
            padding=mask_padding
        )
    else:
        cleaned_img = inpaint_manga_page(
            server_url=iopaint_url,
            image_input=image_path,
            bubbles=bubbles,
            dilation=eff_dilation,
            padding=mask_padding,
            adaptive=False,
            deep_model=iopaint_model
        )

    if output_path is None:
        stem = Path(image_path).stem
        ext = Path(image_path).suffix or ".png"
        output_path = str(Path(image_path).parent / f"{stem}_clean{ext}")

    cleaned_img.save(output_path, quality=95)
    
    for b in bubbles:
        b['status'] = 'cleaned'

    if progress_callback:
        progress_callback(f"✨ Page cleaned and saved to {output_path}")

    return output_path, bubbles


def main():
    parser = argparse.ArgumentParser(description="SmartCleaner-AI - Manga/Webtoon Inpainting & Cleaning Engine")
    parser.add_argument("--image", "-i", type=str, required=True, help="Input manga image path")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output cleaned image path")
    parser.add_argument("--iopaint-url", type=str, default="http://127.0.0.1:8080", help="IOPaint server URL")
    parser.add_argument("--model", type=str, default="anime-lama", help="IOPaint model (anime-lama, lama, manga, etc.)")
    parser.add_argument("--dilation", type=int, default=5, help="Mask dilation in pixels")
    parser.add_argument("--adaptive", action="store_true", default=True, help="Enable smart adaptive fast fill for white bubbles")
    parser.add_argument("--snap", action="store_true", default=True, help="Snap to speech bubble contours via YOLOv8")
    parser.add_argument("--padding", type=int, default=0, help="Additional mask padding in pixels")

    args = parser.parse_args()

    clean_page(
        image_path=args.image,
        output_path=args.output,
        iopaint_url=args.iopaint_url,
        iopaint_model=args.model,
        iopaint_dilation=args.dilation,
        adaptive_mode=args.adaptive,
        snap_to_bubbles=args.snap,
        mask_padding=args.padding,
        progress_callback=print
    )


if __name__ == "__main__":
    main()
