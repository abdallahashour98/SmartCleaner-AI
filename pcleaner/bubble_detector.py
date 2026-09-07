"""
YOLOv8 Speech Bubble Detector module for Manga & Comics.
Uses pre-trained YOLOv8m model trained on 8,000+ comic, manga, and webtoon panels
to accurately detect full speech bubble contours as objects.
"""

import os
import time
import math
import threading
from pathlib import Path
from typing import List, Tuple, Optional
import numpy as np
import cv2
from loguru import logger

# Hugging Face Model URL for comic-speech-bubble-detector-yolov8m
BUBBLE_MODEL_URL = "https://huggingface.co/ogkalu/comic-speech-bubble-detector-yolov8m/resolve/main/comic-speech-bubble-detector.pt"
BUBBLE_MODEL_FILENAME = "comic-speech-bubble-detector.pt"

_yolo_lock = threading.Lock()
_cached_yolo_model = None


def get_default_model_path() -> Path:
    """Returns the default path for the YOLOv8 bubble detector weights."""
    base_dir = Path(__file__).resolve().parent.parent
    models_dir = base_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir / BUBBLE_MODEL_FILENAME


def download_bubble_model_if_needed(model_path: Optional[Path] = None, progress_callback=None) -> Path:
    """Downloads the YOLOv8 speech bubble detector model from Hugging Face if not present."""
    if model_path is None:
        model_path = get_default_model_path()
    else:
        model_path = Path(model_path)

    if model_path.exists() and model_path.stat().st_size > 1_000_000:
        return model_path

    logger.info(f"Downloading YOLOv8 Speech Bubble Detector model to {model_path}...")
    if progress_callback:
        progress_callback("⬇️ Downloading YOLOv8 Speech Bubble AI Model (~50MB)...")

    import requests
    response = requests.get(BUBBLE_MODEL_URL, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    downloaded = 0
    chunk_size = 1024 * 1024 # 1MB chunks

    temp_path = model_path.with_suffix(".tmp")
    with open(temp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total_size > 0:
                    pct = int(downloaded / total_size * 100)
                    progress_callback(f"CHUNK_PROGRESS:{downloaded // (1024*1024)}/{total_size // (1024*1024)}:Downloading YOLOv8 Bubble Model ({pct}%)...")

    if temp_path.exists():
        temp_path.replace(model_path)
    
    logger.info(f"YOLOv8 Speech Bubble Detector downloaded successfully ({model_path.stat().st_size} bytes).")
    return model_path


def load_bubble_detector(model_path: Optional[str] = None, device: str = "auto"):
    """Loads and caches the Ultralytics YOLO model for speech bubble detection."""
    global _cached_yolo_model
    if _cached_yolo_model is not None:
        return _cached_yolo_model

    with _yolo_lock:
        if _cached_yolo_model is not None:
            return _cached_yolo_model

        from ultralytics import YOLO
        import torch

        p = download_bubble_model_if_needed(Path(model_path) if model_path else None)

        if device == "auto":
            dev = "cuda:0" if torch.cuda.is_available() else "cpu"
        elif device == "cuda":
            dev = "cuda:0" if torch.cuda.is_available() else "cpu"
        else:
            dev = "cpu"

        logger.info(f"Loading YOLOv8 Speech Bubble Detector on {dev} from {p}...")
        model = YOLO(str(p))
        _cached_yolo_model = (model, dev)
        return _cached_yolo_model


def detect_speech_bubbles(
    img_or_path,
    model_path: Optional[str] = None,
    conf: float = 0.25,
    device: str = "auto",
    progress_callback=None
) -> List[Tuple[int, int, int, int, float]]:
    """
    Detects all speech bubble bounding boxes in the image using YOLOv8.
    Returns a list of tuples: [(x1, y1, x2, y2, confidence), ...]
    """
    try:
        model, dev = load_bubble_detector(model_path=model_path, device=device)

        if isinstance(img_or_path, (str, Path)):
            p_str = str(img_or_path)
            try:
                buf = np.fromfile(p_str, dtype=np.uint8)
                img_input = cv2.imdecode(buf, cv2.IMREAD_COLOR) if (buf is not None and len(buf) > 0) else None
            except Exception:
                img_input = None
            if img_input is None:
                img_input = p_str
        elif isinstance(img_or_path, np.ndarray):
            img_input = img_or_path
        else:
            raise ValueError("Unsupported image input type for YOLO bubble detector.")

        detected_boxes = []

        if isinstance(img_input, np.ndarray):
            h_orig, w_orig = img_input.shape[:2]
        else:
            h_orig, w_orig = 0, 0

        # If tall webtoon strip, process in overlapping chunks to prevent aspect ratio destruction
        if h_orig > 2200 or (w_orig > 0 and (h_orig / w_orig) > 2.0):
            chunk_h = 1400
            overlap = 200
            step = chunk_h - overlap
            current_y = 0

            raw_boxes = []
            while current_y < h_orig:
                end_y = min(h_orig, current_y + chunk_h)
                chunk_crop = img_input[current_y:end_y, :]
                if chunk_crop.shape[0] > 50 and chunk_crop.std() > 5.0:
                    results = model.predict(
                        source=chunk_crop,
                        conf=conf,
                        device=dev,
                        imgsz=640,
                        verbose=False
                    )
                    if results and len(results) > 0 and results[0].boxes is not None:
                        xyxy = results[0].boxes.xyxy.cpu().numpy()
                        confs = results[0].boxes.conf.cpu().numpy()
                        for i in range(len(xyxy)):
                            bx1, by1, bx2, by2 = xyxy[i]
                            raw_boxes.append((
                                int(bx1),
                                int(by1 + current_y),
                                int(bx2),
                                int(by2 + current_y),
                                float(confs[i])
                            ))
                if end_y >= h_orig:
                    break
                current_y += step

            # Deduplicate boxes detected in overlapping chunk zones
            merged_boxes = []
            for b in raw_boxes:
                bx1, by1, bx2, by2, bconf = b
                b_area = max(1, (bx2 - bx1) * (by2 - by1))
                bcx = (bx1 + bx2) / 2.0
                bcy = (by1 + by2) / 2.0
                matched = False

                for m_idx, (mx1, my1, mx2, my2, mconf) in enumerate(merged_boxes):
                    m_area = max(1, (mx2 - mx1) * (my2 - my1))
                    mcx = (mx1 + mx2) / 2.0
                    mcy = (my1 + my2) / 2.0

                    inter_x1 = max(bx1, mx1)
                    inter_y1 = max(by1, my1)
                    inter_x2 = min(bx2, mx2)
                    inter_y2 = min(by2, my2)

                    if inter_x2 > inter_x1 and inter_y2 > inter_y1:
                        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
                        union_area = b_area + m_area - inter_area
                        iou = inter_area / max(1, union_area)
                        containment = inter_area / min(b_area, m_area)
                        center_dist = math.hypot(bcx - mcx, bcy - mcy)

                        if iou >= 0.50 or (containment >= 0.70 and center_dist < 40.0):
                            merged_boxes[m_idx] = (
                                min(bx1, mx1),
                                min(by1, my1),
                                max(bx2, mx2),
                                max(by2, my2),
                                max(bconf, mconf)
                            )
                            matched = True
                            break

                if not matched:
                    merged_boxes.append(b)

            return merged_boxes

        # Standard aspect ratio manga / comic page: single-pass inference
        scale_x = 1.0
        scale_y = 1.0
        predict_input = img_input

        if dev == "cpu" and isinstance(img_input, np.ndarray):
            max_dim = max(h_orig, w_orig)
            if max_dim > 1024:
                scale = 1024 / max_dim
                new_w = int(w_orig * scale)
                new_h = int(h_orig * scale)
                predict_input = cv2.resize(img_input, (new_w, new_h), interpolation=cv2.INTER_AREA)
                scale_x = w_orig / new_w
                scale_y = h_orig / new_h

        target_imgsz = 1280 if dev == "cuda" else 640
        results = model.predict(
            source=predict_input,
            conf=conf,
            device=dev,
            imgsz=target_imgsz,
            verbose=False
        )

        detected_boxes = []
        if results and len(results) > 0:
            boxes = results[0].boxes
            if boxes is not None and len(boxes) > 0:
                xyxy = boxes.xyxy.cpu().numpy()
                confs = boxes.conf.cpu().numpy()
                for i in range(len(xyxy)):
                    bx1, by1, bx2, by2 = xyxy[i]
                    # Map coordinates back if scaled
                    bx1 = int(bx1 * scale_x)
                    by1 = int(by1 * scale_y)
                    bx2 = int(bx2 * scale_x)
                    by2 = int(by2 * scale_y)
                    c = float(confs[i])
                    detected_boxes.append((bx1, by1, bx2, by2, c))

        return detected_boxes
    except Exception as e:
        logger.warning(f"YOLOv8 Speech Bubble Detection error: {e}")
        return []


def match_and_expand_bubbles(
    blk_list: list,
    yolo_bubbles: List[Tuple[int, int, int, int, float]],
    img_shape: tuple,
    mask_padding: int = 0
) -> list:
    """
    Matches each ComicTextDetector TextBlock with enclosing YOLO speech bubbles.
    If a text block is located inside a YOLO bubble, snaps the TextBlock bounding box
    to the clean outer speech bubble boundaries.
    """
    if not yolo_bubbles:
        return blk_list

    im_h, im_w = img_shape[:2]

    # First pass: find candidate matches between text blocks and YOLO bubbles
    matches_per_yolo = {}  # yolo_idx -> list of (score, blk_idx)
    blk_best_yolo = {}     # blk_idx -> (yolo_idx, bubble_coords)

    for blk_idx, blk in enumerate(blk_list):
        raw_x1, raw_y1, raw_x2, raw_y2 = blk.xyxy
        blk.raw_text_xyxy = [int(raw_x1), int(raw_y1), int(raw_x2), int(raw_y2)]

        tw = max(1, raw_x2 - raw_x1)
        th = max(1, raw_y2 - raw_y1)
        tcx = (raw_x1 + raw_x2) / 2
        tcy = (raw_y1 + raw_y2) / 2

        best_yolo_idx = None
        best_overlap_score = 0.0
        best_bubble = None

        for y_idx, (bx1, by1, bx2, by2, bconf) in enumerate(yolo_bubbles):
            bw = max(1, bx2 - bx1)
            bh = max(1, by2 - by1)

            center_inside = (bx1 <= tcx <= bx2) and (by1 <= tcy <= by2)
            ix1 = max(raw_x1, bx1)
            iy1 = max(raw_y1, by1)
            ix2 = min(raw_x2, bx2)
            iy2 = min(raw_y2, by2)
            iw = max(0, ix2 - ix1)
            ih = max(0, iy2 - iy1)
            intersection = iw * ih
            iota = intersection / (tw * th)

            if center_inside or iota > 0.4:
                score = (iota * 2.0) + (1.0 if center_inside else 0.0)
                if score > best_overlap_score:
                    best_overlap_score = score
                    best_yolo_idx = y_idx
                    best_bubble = (bx1, by1, bx2, by2)

        if best_bubble is not None and best_yolo_idx is not None:
            blk_best_yolo[blk_idx] = (best_yolo_idx, best_bubble)
            if best_yolo_idx not in matches_per_yolo:
                matches_per_yolo[best_yolo_idx] = []
            matches_per_yolo[best_yolo_idx].append((best_overlap_score, blk_idx))

    # Second pass: apply snapping. If a YOLO bubble contains >1 text blocks,
    # do NOT collapse both to the giant union box; keep them as separate individual bubbles!
    for blk_idx, blk in enumerate(blk_list):
        raw_x1, raw_y1, raw_x2, raw_y2 = blk.raw_text_xyxy
        tw = max(1, raw_x2 - raw_x1)
        th = max(1, raw_y2 - raw_y1)

        if blk_idx in blk_best_yolo:
            y_idx, (bx1, by1, bx2, by2) = blk_best_yolo[blk_idx]
            num_blocks_in_bubble = len(matches_per_yolo.get(y_idx, []))

            if num_blocks_in_bubble == 1:
                # Single text block inside bubble -> clean full snap
                pad = mask_padding
                snap_x1 = max(0, bx1 - pad)
                snap_y1 = max(0, by1 - pad)
                snap_x2 = min(im_w, bx2 + pad)
                snap_y2 = min(im_h, by2 + pad)

                blk.xyxy = [
                    min(snap_x1, raw_x1),
                    min(snap_y1, raw_y1),
                    max(snap_x2, raw_x2),
                    max(snap_y2, raw_y2)
                ]
            else:
                # Multi-bubble / connected compound bubble: preserve individual bubble bounds!
                pad = mask_padding if mask_padding > 0 else (int(min(tw, th) * 0.08) + 6)
                blk.xyxy = [
                    max(0, raw_x1 - pad),
                    max(0, raw_y1 - pad),
                    min(im_w, raw_x2 + pad),
                    min(im_h, raw_y2 + pad)
                ]
        else:
            # Floating SFX / artwork text
            pad = mask_padding if mask_padding > 0 else (int(min(tw, th) * 0.08) + 5)
            blk.xyxy = [
                max(0, raw_x1 - pad),
                max(0, raw_y1 - pad),
                min(im_w, raw_x2 + pad),
                min(im_h, raw_y2 + pad)
            ]

    return blk_list
