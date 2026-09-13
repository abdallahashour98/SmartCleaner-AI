"""
YOLO11 & YOLOv8 Dual-Engine Speech Bubble Detector module for Manga & Comics.
Combines:
1. Primary: YOLO11n Manga109 Instance Segmentation (huyvux3005/manga109-segmentation-bubble)
   for ultra-fast, high-precision bubble contour segmentation and polygon extraction.
2. Auxiliary: Comic Speech Bubble Detector YOLOv8m (ogkalu/comic-speech-bubble-detector-yolov8m)
   trained on 8,000+ comic, manga, and webtoon panels for dark/demonic bubbles and webtoon strips.
3. Tail pointer stripping (extract_bubble_body_box via Euclidean distance transform).
"""

import os
import time
import math
import threading
from pathlib import Path
from typing import List, Tuple, Optional, Union
import numpy as np
import cv2
from loguru import logger

# Hugging Face Model URLs
YOLO11_MANGA_URL = "https://huggingface.co/huyvux3005/manga109-segmentation-bubble/resolve/main/best.pt"
YOLO11_MANGA_FILENAME = "yolo11n-manga109-bubble.pt"

BUBBLE_MODEL_URL = "https://huggingface.co/ogkalu/comic-speech-bubble-detector-yolov8m/resolve/main/comic-speech-bubble-detector.pt"
BUBBLE_MODEL_FILENAME = "comic-speech-bubble-detector.pt"

_yolo_lock = threading.Lock()
_cached_models = None


class DetectedBubble:
    """
    Rich speech bubble detection object supporting both Bounding Box and Segmentation Polygon.
    Backwards compatible with 5-element tuple unpacking: (bx1, by1, bx2, by2, conf).
    """
    __slots__ = ('x1', 'y1', 'x2', 'y2', 'conf', 'polygon', 'is_dark', 'w', 'h')

    def __init__(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        conf: float = 1.0,
        polygon: Optional[list] = None,
        is_dark: bool = False
    ):
        self.x1 = int(x1)
        self.y1 = int(y1)
        self.x2 = int(x2)
        self.y2 = int(y2)
        self.conf = float(conf)
        self.polygon = polygon
        self.is_dark = is_dark
        self.w = max(1, self.x2 - self.x1)
        self.h = max(1, self.y2 - self.y1)

    def __iter__(self):
        # 5-element iteration for backwards compatibility with: (bx1, by1, bx2, by2, conf)
        return iter((self.x1, self.y1, self.x2, self.y2, self.conf))

    def __getitem__(self, idx):
        vals = (self.x1, self.y1, self.x2, self.y2, self.conf, self.polygon, self.is_dark)
        return vals[idx]

    def __len__(self):
        return 5

    def __repr__(self):
        return (
            f"DetectedBubble(box=[{self.x1}, {self.y1}, {self.x2}, {self.y2}], "
            f"conf={self.conf:.2f}, poly={'yes' if self.polygon else 'no'}, dark={self.is_dark})"
        )


def get_models_dir() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    models_dir = base_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


def download_file_if_needed(url: str, filename: str, desc: str, progress_callback=None) -> Path:
    target_path = get_models_dir() / filename
    if target_path.exists() and target_path.stat().st_size > 1_000_000:
        return target_path

    # Check PhotoApp models directory fallback if available
    photoapp_model = Path(r"G:\project\PhotoApp\tools\models") / filename
    if photoapp_model.exists() and photoapp_model.stat().st_size > 1_000_000:
        try:
            import shutil
            shutil.copyfile(str(photoapp_model), str(target_path))
            logger.info(f"Copied {filename} from PhotoApp cache: {target_path}")
            return target_path
        except Exception:
            pass

    logger.info(f"Downloading {desc} to {target_path}...")
    if progress_callback:
        progress_callback(f"⬇️ Downloading {desc}...")

    import requests
    response = requests.get(url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get("content-length", 0))
    downloaded = 0
    chunk_size = 1024 * 1024

    temp_path = target_path.with_suffix(".tmp")
    with open(temp_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total_size > 0:
                    pct = int(downloaded / total_size * 100)
                    progress_callback(f"CHUNK_PROGRESS:{downloaded // (1024*1024)}/{total_size // (1024*1024)}:Downloading {desc} ({pct}%)...")

    if temp_path.exists():
        temp_path.replace(target_path)

    logger.info(f"Downloaded {filename} successfully ({target_path.stat().st_size} bytes).")
    return target_path


def load_bubble_detector(device: str = "auto", progress_callback=None):
    """
    Loads and caches the Dual-Engine YOLO models:
    1. Primary: YOLO11n Manga109 Segmentation model.
    2. Auxiliary: Comic Speech Bubble Detector YOLOv8m (for dark/webtoon bubbles).
    """
    global _cached_models
    if _cached_models is not None:
        return _cached_models

    with _yolo_lock:
        if _cached_models is not None:
            return _cached_models

        from ultralytics import YOLO
        import torch

        if device == "auto":
            dev = "cuda:0" if torch.cuda.is_available() else "cpu"
        elif device == "cuda":
            dev = "cuda:0" if torch.cuda.is_available() else "cpu"
        else:
            dev = "cpu"

        # 1. Primary Model: YOLO11n Manga109 Segmentation
        manga11_path = download_file_if_needed(
            url=YOLO11_MANGA_URL,
            filename=YOLO11_MANGA_FILENAME,
            desc="YOLO11n Manga109 Seg Model (~12MB)",
            progress_callback=progress_callback
        )
        logger.info(f"Loading Primary YOLO11n Manga109 Bubble Detector on {dev} from {manga11_path}...")
        try:
            manga11_model = YOLO(str(manga11_path))
        except Exception as e:
            logger.warning(f"Failed to load YOLO11 model ({e}), falling back to comic model.")
            manga11_model = None

        # 2. Auxiliary Model: Comic Speech Bubble Detector
        comic_path = download_file_if_needed(
            url=BUBBLE_MODEL_URL,
            filename=BUBBLE_MODEL_FILENAME,
            desc="Comic Bubble Detector Model (~52MB)",
            progress_callback=progress_callback
        )
        logger.info(f"Loading Auxiliary Comic Bubble Detector on {dev} from {comic_path}...")
        try:
            comic_model = YOLO(str(comic_path))
        except Exception as e:
            logger.warning(f"Failed to load comic model: {e}")
            comic_model = None

        _cached_models = (manga11_model, comic_model, dev)
        return _cached_models


def extract_bubble_body_box(
    poly_arr: list,
    orig_box: tuple
) -> tuple:
    """
    Extract the main bubble body bounding box by stripping narrow tail pointers (protrusions).
    Tails are narrow acute extensions pointing to characters, which inflate bounding boxes.
    Uses Euclidean distance transform to separate the core bubble body from thin tails.
    """
    if not poly_arr or len(poly_arr) < 6:
        return orig_box

    try:
        x, y, w, h = orig_box
        if w < 30 or h < 30:
            return orig_box

        pts = np.array(poly_arr, dtype=np.int32)
        pad = 10
        local_mask = np.zeros((int(h + pad * 2), int(w + pad * 2)), dtype=np.uint8)
        local_pts = pts - np.array([x - pad, y - pad], dtype=np.int32)
        cv2.fillPoly(local_mask, [local_pts], 255)

        dist = cv2.distanceTransform(local_mask, cv2.DIST_L2, 5)
        max_r = dist.max()
        if max_r >= 14.0:
            tail_thresh = max(6.0, min(16.0, max_r * 0.22))
            body_core = (dist > tail_thresh).astype(np.uint8) * 255
            k = int(tail_thresh * 2) + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
            body_restored = cv2.bitwise_and(cv2.dilate(body_core, kernel), local_mask)
            bx, by, bw, bh = cv2.boundingRect(body_restored)
            if bw >= w * 0.55 and bh >= h * 0.55:
                return (int(bx + x - pad), int(by + y - pad), int(bw), int(bh))
    except Exception as e:
        logger.warning(f"Tail extraction fallback: {e}")

    return orig_box


def _parse_yolo_results(results, offset_y: int = 0, scale_x: float = 1.0, scale_y: float = 1.0, img_bgr: Optional[np.ndarray] = None) -> List[DetectedBubble]:
    """Parses Ultralytics YOLO results into DetectedBubble objects with polygons & tail stripping."""
    bubbles = []
    if not results or len(results) == 0:
        return bubbles

    res = results[0]
    boxes = res.boxes
    if boxes is None or len(boxes) == 0:
        return bubbles

    has_masks = hasattr(res, 'masks') and res.masks is not None
    masks_xy = res.masks.xy if has_masks else []

    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()

    h_img = img_bgr.shape[0] if img_bgr is not None else 100000
    w_img = img_bgr.shape[1] if img_bgr is not None else 100000

    for i in range(len(xyxy)):
        bx1 = int(xyxy[i][0] * scale_x)
        by1 = int(xyxy[i][1] * scale_y) + offset_y
        bx2 = int(xyxy[i][2] * scale_x)
        by2 = int(xyxy[i][3] * scale_y) + offset_y
        c = float(confs[i])

        polygon = None
        if has_masks and i < len(masks_xy) and len(masks_xy[i]) > 3:
            raw_pts = masks_xy[i]
            scaled_pts = []
            for pt in raw_pts:
                px = round(float(pt[0] * scale_x), 1)
                py = round(float(pt[1] * scale_y) + offset_y, 1)
                scaled_pts.append([px, py])
            polygon = scaled_pts

            # Strip narrow tail pointer so bounding box tightly frames main bubble body
            orig_w = max(1, bx2 - bx1)
            orig_h = max(1, by2 - by1)
            body_x, body_y, body_w, body_h = extract_bubble_body_box(polygon, (bx1, by1, orig_w, orig_h))
            bx1, by1 = body_x, body_y
            bx2, by2 = body_x + body_w, body_y + body_h

        # Determine if bubble background is dark
        is_dark = False
        if img_bgr is not None and by2 > by1 and bx2 > bx1:
            cy1 = max(0, min(h_img, by1))
            cy2 = max(0, min(h_img, by2))
            cx1 = max(0, min(w_img, bx1))
            cx2 = max(0, min(w_img, bx2))
            if (cy2 - cy1) > 10 and (cx2 - cx1) > 10:
                crop = img_bgr[cy1:cy2, cx1:cx2]
                if crop.size > 0:
                    gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
                    is_dark = float(np.mean(gray_crop)) < 65.0

        bubbles.append(DetectedBubble(bx1, by1, bx2, by2, conf=c, polygon=polygon, is_dark=is_dark))

    return bubbles


def detect_speech_bubbles(
    img_or_path,
    model_path: Optional[str] = None,
    conf: float = 0.25,
    device: str = "auto",
    progress_callback=None
) -> List[DetectedBubble]:
    """
    Detects all speech bubbles with instance segmentation polygons using YOLO11 Dual-Engine.
    Returns a list of DetectedBubble objects: [DetectedBubble(x1, y1, x2, y2, conf, polygon, is_dark), ...]
    """
    try:
        primary_model, aux_model, dev = load_bubble_detector(device=device, progress_callback=progress_callback)

        if isinstance(img_or_path, (str, Path)):
            p_str = str(img_or_path)
            try:
                buf = np.fromfile(p_str, dtype=np.uint8)
                img_input = cv2.imdecode(buf, cv2.IMREAD_COLOR) if (buf is not None and len(buf) > 0) else None
            except Exception:
                img_input = None
            if img_input is None:
                img_input = cv2.imread(p_str)
        elif isinstance(img_or_path, np.ndarray):
            img_input = img_or_path
        else:
            raise ValueError("Unsupported image input type for YOLO bubble detector.")

        if img_input is None:
            return []

        h_orig, w_orig = img_input.shape[:2]

        active_model = primary_model if primary_model is not None else aux_model
        if active_model is None:
            logger.warning("No bubble detector model available.")
            return []

        # Tall webtoon strip processing in overlapping chunks
        if h_orig > 2200 or (w_orig > 0 and (h_orig / w_orig) > 2.0):
            chunk_h = 1400
            overlap = 200
            step = chunk_h - overlap
            current_y = 0
            raw_bubbles: List[DetectedBubble] = []

            while current_y < h_orig:
                end_y = min(h_orig, current_y + chunk_h)
                chunk_crop = img_input[current_y:end_y, :]
                if chunk_crop.shape[0] > 50 and chunk_crop.std() > 5.0:
                    results = active_model.predict(
                        source=chunk_crop,
                        conf=conf,
                        device=dev,
                        imgsz=640,
                        verbose=False
                    )
                    chunk_b = _parse_yolo_results(results, offset_y=current_y, img_bgr=img_input)

                    # If primary found 0 detections in chunk and aux_model is available, try aux
                    if len(chunk_b) == 0 and aux_model is not None and aux_model is not active_model:
                        aux_res = aux_model.predict(
                            source=chunk_crop,
                            conf=conf,
                            device=dev,
                            imgsz=640,
                            verbose=False
                        )
                        chunk_b = _parse_yolo_results(aux_res, offset_y=current_y, img_bgr=img_input)

                    raw_bubbles.extend(chunk_b)

                if end_y >= h_orig:
                    break
                current_y += step

            # Deduplicate boxes detected in overlapping chunk zones
            merged_bubbles: List[DetectedBubble] = []
            for b in raw_bubbles:
                matched = False
                for m_idx, m in enumerate(merged_bubbles):
                    inter_x1 = max(b.x1, m.x1)
                    inter_y1 = max(b.y1, m.y1)
                    inter_x2 = min(b.x2, m.x2)
                    inter_y2 = min(b.y2, m.y2)

                    if inter_x2 > inter_x1 and inter_y2 > inter_y1:
                        inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
                        union_area = (b.w * b.h) + (m.w * m.h) - inter_area
                        iou = inter_area / max(1, union_area)
                        containment = inter_area / min(b.w * b.h, m.w * m.h)
                        bcx = (b.x1 + b.x2) / 2.0
                        bcy = (b.y1 + b.y2) / 2.0
                        mcx = (m.x1 + m.x2) / 2.0
                        mcy = (m.y1 + m.y2) / 2.0
                        center_dist = math.hypot(bcx - mcx, bcy - mcy)

                        if iou >= 0.50 or (containment >= 0.70 and center_dist < 40.0):
                            poly = b.polygon if b.polygon else m.polygon
                            dark = b.is_dark or m.is_dark
                            merged_bubbles[m_idx] = DetectedBubble(
                                min(b.x1, m.x1),
                                min(b.y1, m.y1),
                                max(b.x2, m.x2),
                                max(b.y2, m.y2),
                                max(b.conf, m.conf),
                                polygon=poly,
                                is_dark=dark
                            )
                            matched = True
                            break

                if not matched:
                    merged_bubbles.append(b)

            return merged_bubbles

        # Standard manga / comic page: single-pass inference
        scale_x = 1.0
        scale_y = 1.0
        predict_input = img_input

        if dev == "cpu":
            max_dim = max(h_orig, w_orig)
            if max_dim > 1024:
                scale = 1024 / max_dim
                new_w = int(w_orig * scale)
                new_h = int(h_orig * scale)
                predict_input = cv2.resize(img_input, (new_w, new_h), interpolation=cv2.INTER_AREA)
                scale_x = w_orig / new_w
                scale_y = h_orig / new_h

        target_imgsz = 1280 if dev == "cuda" else 640
        results = active_model.predict(
            source=predict_input,
            conf=conf,
            device=dev,
            imgsz=target_imgsz,
            verbose=False
        )
        detected_bubbles = _parse_yolo_results(results, scale_x=scale_x, scale_y=scale_y, img_bgr=img_input)

        # Ensemble Fallback: if primary found 0 detections or if aux_model is available, supplement with aux
        if (len(detected_bubbles) == 0 or any(b.is_dark for b in detected_bubbles)) and aux_model is not None and aux_model is not active_model:
            aux_results = aux_model.predict(
                source=predict_input,
                conf=conf,
                device=dev,
                imgsz=target_imgsz,
                verbose=False
            )
            aux_bubbles = _parse_yolo_results(aux_results, scale_x=scale_x, scale_y=scale_y, img_bgr=img_input)
            for ab in aux_bubbles:
                # Add if not overlapping an existing detection
                if not any(
                    (max(ab.x1, db.x1) < min(ab.x2, db.x2) and max(ab.y1, db.y1) < min(ab.y2, db.y2))
                    for db in detected_bubbles
                ):
                    detected_bubbles.append(ab)

        return detected_bubbles

    except Exception as e:
        logger.warning(f"Speech Bubble Detection error: {e}")
        return []


def match_and_expand_bubbles(
    blk_list: list,
    yolo_bubbles: List[Union[DetectedBubble, Tuple]],
    img_shape: tuple,
    mask_padding: int = 0
) -> list:
    """
    Pairs ComicTextDetector TextBlocks with enclosing YOLO speech bubbles.
    Crucially:
    - Retains blk.raw_text_xyxy strictly as the inner text boundary.
    - Attaches blk.bubble_bbox = [bx1, by1, bx2, by2] as the bubble container.
    - Attaches blk.bubble_polygon = polygon as the true bubble contour for border shielding.
    - Sets blk.xyxy as the crop/container boundary without destroying text coordinates!
    """
    if not yolo_bubbles:
        for blk in blk_list:
            raw_x1, raw_y1, raw_x2, raw_y2 = blk.xyxy
            blk.raw_text_xyxy = [int(raw_x1), int(raw_y1), int(raw_x2), int(raw_y2)]
            blk.bubble_bbox = None
            blk.bubble_polygon = None
            blk.is_dark = False
            blk.has_matched_bubble = False
        return blk_list

    im_h, im_w = img_shape[:2]

    # Convert yolo_bubbles to DetectedBubble if tuples were passed
    standard_yolo: List[DetectedBubble] = []
    for yb in yolo_bubbles:
        if isinstance(yb, DetectedBubble):
            standard_yolo.append(yb)
        else:
            poly = yb[5] if len(yb) > 5 else None
            dark = yb[6] if len(yb) > 6 else False
            standard_yolo.append(DetectedBubble(yb[0], yb[1], yb[2], yb[3], conf=yb[4] if len(yb) > 4 else 1.0, polygon=poly, is_dark=dark))

    # First pass: find candidate matches between text blocks and YOLO bubbles
    matches_per_yolo = {}  # yolo_idx -> list of (score, blk_idx)
    blk_best_yolo = {}     # blk_idx -> (yolo_idx, DetectedBubble)

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

        for y_idx, yb in enumerate(standard_yolo):
            center_inside = (yb.x1 <= tcx <= yb.x2) and (yb.y1 <= tcy <= yb.y2)
            ix1 = max(raw_x1, yb.x1)
            iy1 = max(raw_y1, yb.y1)
            ix2 = min(raw_x2, yb.x2)
            iy2 = min(raw_y2, yb.y2)
            iw = max(0, ix2 - ix1)
            ih = max(0, iy2 - iy1)
            intersection = iw * ih
            iota = intersection / (tw * th)

            if center_inside or iota > 0.35:
                score = (iota * 2.0) + (1.0 if center_inside else 0.0)
                if score > best_overlap_score:
                    best_overlap_score = score
                    best_yolo_idx = y_idx
                    best_bubble = yb

        if best_bubble is not None and best_yolo_idx is not None:
            blk_best_yolo[blk_idx] = (best_yolo_idx, best_bubble)
            if best_yolo_idx not in matches_per_yolo:
                matches_per_yolo[best_yolo_idx] = []
            matches_per_yolo[best_yolo_idx].append((best_overlap_score, blk_idx))

    # Second pass: assign container bounds and retain clean text bounds
    for blk_idx, blk in enumerate(blk_list):
        raw_x1, raw_y1, raw_x2, raw_y2 = blk.raw_text_xyxy
        tw = max(1, raw_x2 - raw_x1)
        th = max(1, raw_y2 - raw_y1)

        if blk_idx in blk_best_yolo:
            y_idx, yb = blk_best_yolo[blk_idx]
            num_blocks_in_bubble = len(matches_per_yolo.get(y_idx, []))

            blk.has_matched_bubble = True
            blk.bubble_bbox = [yb.x1, yb.y1, yb.x2, yb.y2]
            blk.bubble_polygon = yb.polygon
            blk.is_dark = yb.is_dark

            if num_blocks_in_bubble == 1:
                # Single text block inside bubble: container box encompasses full bubble
                snap_x1 = max(0, min(yb.x1, raw_x1))
                snap_y1 = max(0, min(yb.y1, raw_y1))
                snap_x2 = min(im_w, max(yb.x2, raw_x2))
                snap_y2 = min(im_h, max(yb.y2, raw_y2))
                blk.xyxy = [snap_x1, snap_y1, snap_x2, snap_y2]
            else:
                # Multi-dialogue connected bubble: preserve individual block crop bounds
                pad = mask_padding if mask_padding > 0 else (int(min(tw, th) * 0.10) + 8)
                blk.xyxy = [
                    max(0, raw_x1 - pad),
                    max(0, raw_y1 - pad),
                    min(im_w, raw_x2 + pad),
                    min(im_h, raw_y2 + pad)
                ]
        else:
            # Floating SFX / artwork text (no bubble container)
            pad = mask_padding if mask_padding > 0 else (int(min(tw, th) * 0.10) + 6)
            blk.has_matched_bubble = False
            blk.bubble_bbox = None
            blk.bubble_polygon = None
            blk.is_dark = False
            blk.xyxy = [
                max(0, raw_x1 - pad),
                max(0, raw_y1 - pad),
                min(im_w, raw_x2 + pad),
                min(im_h, raw_y2 + pad)
            ]

    return blk_list
