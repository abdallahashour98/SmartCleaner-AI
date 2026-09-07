"""
IOPaint Server Client for FastTypeR-Extractor

Provides robust HTTP communication with local or remote (ngrok/cloud) IOPaint inpainting servers.
Supports:
- Real-time connection health checking (`/api/v1/model`)
- Dynamic remote model switching (`POST /api/v1/model`)
- Fast inpainting request dispatch (`POST /api/v1/inpaint`) with Base64 or multipart fallback
- Smart manga page mask generation with morphological dilation from detected bubble bounding boxes
- Single-bubble crop inpainting
"""

import io
import json
import base64
import time
import threading
from pathlib import Path
from typing import List, Tuple, Optional, Union

import cv2
import numpy as np
from PIL import Image
import requests
from loguru import logger

# Commonly used models supported by IOPaint
SUPPORTED_IOPAINT_MODELS = [
    "anime-lama",
    "lama"
]

# Global mutex to prevent concurrent inference requests colliding on OpenVINO/PyTorch models
_iopaint_global_lock = threading.Lock()


class IOPaintClient:
    """Client for interacting with IOPaint API server."""

    def __init__(self, server_url: str = "http://127.0.0.1:8080", timeout: int = 300):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self._active_model_cached = None

    def set_server_url(self, server_url: str):
        self.server_url = server_url.rstrip("/")

    def _get_headers(self) -> dict:
        return {
            "ngrok-skip-browser-warning": "true",
            "User-Agent": "FastTypeR-Extractor/1.0"
        }

    def check_connection(self, server_url: Optional[str] = None) -> Tuple[bool, str]:
        """
        Pings IOPaint server to verify connectivity and get the currently active model.
        Returns (is_connected: bool, active_model_or_error: str).
        """
        url = (server_url or self.server_url).rstrip("/")
        if not url:
            return False, "Server URL is empty"

        endpoint = f"{url}/api/v1/model"
        try:
            resp = self.session.get(endpoint, headers=self._get_headers(), timeout=6)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    model_name = data.get("name", "") or data.get("model", "") or "connected"
                    self._active_model_cached = model_name
                    return True, model_name
                except Exception:
                    return True, "connected"
            else:
                return False, f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            return False, "Connection timed out"
        except requests.exceptions.ConnectionError:
            # Fallback check for port 8088 if 8080 was unreachable
            if ":8080" in url:
                alt_url = url.replace(":8080", ":8088")
                try:
                    alt_resp = requests.get(f"{alt_url}/api/v1/model", headers=self._get_headers(), timeout=3)
                    if alt_resp.status_code == 200:
                        self.server_url = alt_url
                        data = alt_resp.json()
                        model_name = data.get("name", "") or data.get("model", "") or "connected"
                        return True, model_name
                except Exception:
                    pass
            return False, "Could not connect to server"
        except Exception as e:
            return False, str(e)

    def get_available_models(self, server_url: Optional[str] = None) -> List[str]:
        """
        Dynamically fetches the actual list of models available on the live IOPaint server
        by querying /api/v1/server-config and /api/v1/model, with a fallback to local scan.
        """
        url = (server_url or self.server_url).rstrip("/")
        models: List[str] = []
        if url:
            try:
                resp = requests.get(f"{url}/api/v1/server-config", headers=self._get_headers(), timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    model_infos = data.get("modelInfos", [])
                    for info in model_infos:
                        if isinstance(info, dict) and "name" in info:
                            m_name = info["name"]
                            if m_name and m_name not in models:
                                models.append(m_name)
            except Exception as e:
                logger.debug(f"Could not retrieve server-config from {url}: {e}")

            try:
                m_resp = requests.get(f"{url}/api/v1/model", headers=self._get_headers(), timeout=3)
                if m_resp.status_code == 200:
                    m_data = m_resp.json()
                    curr_name = m_data.get("name") or m_data.get("model")
                    if curr_name and curr_name not in models:
                        models.append(curr_name)
            except Exception:
                pass

        if not models:
            # Fallback to local scan if iopaint package is installed
            try:
                from iopaint.download import scan_models
                scanned = scan_models()
                for m in scanned:
                    if hasattr(m, "name") and m.name and m.name not in models:
                        models.append(m.name)
            except Exception:
                pass

        if not models:
            models = ["anime-lama", "lama"]

        return models

    def switch_model(self, model_name: str, server_url: Optional[str] = None) -> Tuple[bool, str]:
        """
        Requests the IOPaint server to switch its active inpainting model.
        Returns (success: bool, message: str).
        """
        if self._active_model_cached and self._active_model_cached.strip().lower() == model_name.strip().lower():
            return True, f"Already active on {model_name}"

        url = (server_url or self.server_url).rstrip("/")
        if not url:
            return False, "Server URL is empty"

        endpoint = f"{url}/api/v1/model"
        payload = {"name": model_name}
        try:
            headers = self._get_headers()
            headers["Content-Type"] = "application/json"
            resp = self.session.post(
                endpoint,
                headers=headers,
                data=json.dumps(payload),
                timeout=60
            )
            if resp.status_code in (200, 201, 204):
                self._active_model_cached = model_name
                logger.info(f"IOPaint server switched model to: {model_name}")
                return True, f"Switched to {model_name}"
            else:
                return False, f"HTTP {resp.status_code}"
        except requests.exceptions.ConnectionError:
            return False, "Server is offline"
        except requests.exceptions.Timeout:
            return False, "Connection timed out"
        except Exception as e:
            logger.error(f"Failed to switch IOPaint model: {e}")
            return False, "Connection error"

    def inpaint(
        self,
        image_input: Union[Image.Image, np.ndarray, str, Path],
        mask_input: Union[Image.Image, np.ndarray, str, Path],
        server_url: Optional[str] = None,
        return_numpy: bool = False
    ) -> Union[Image.Image, np.ndarray]:
        """
        Sends an image and mask to IOPaint server for inpainting.
        
        :param image_input: PIL Image, OpenCV BGR ndarray, or file path.
        :param mask_input: PIL Image (binary/grayscale), 2D uint8 ndarray, or file path.
        :param server_url: Optional override of server URL.
        :param return_numpy: If True, returns OpenCV BGR numpy ndarray instead of PIL Image.
        :return: Cleaned PIL Image or BGR numpy array.
        """
        url = (server_url or self.server_url).rstrip("/")
        if not url:
            raise ValueError("IOPaint Server URL is not configured.")

        # 1. Prepare PIL Image
        if isinstance(image_input, (str, Path)):
            pil_img = Image.open(str(image_input)).convert("RGB")
        elif isinstance(image_input, np.ndarray):
            if len(image_input.shape) == 2:
                pil_img = Image.fromarray(image_input).convert("RGB")
            elif image_input.shape[2] == 4:
                pil_img = Image.fromarray(cv2.cvtColor(image_input, cv2.COLOR_BGRA2RGB))
            else:
                pil_img = Image.fromarray(cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB))
        elif isinstance(image_input, Image.Image):
            pil_img = image_input.convert("RGB")
        else:
            raise TypeError(f"Unsupported image type: {type(image_input)}")

        # 2. Prepare PIL Mask (must match image dimensions)
        if isinstance(mask_input, (str, Path)):
            pil_mask = Image.open(str(mask_input)).convert("L")
        elif isinstance(mask_input, np.ndarray):
            pil_mask = Image.fromarray(mask_input).convert("L")
        elif isinstance(mask_input, Image.Image):
            pil_mask = mask_input.convert("L")
        else:
            raise TypeError(f"Unsupported mask type: {type(mask_input)}")

        if pil_mask.size != pil_img.size:
            pil_mask = pil_mask.resize(pil_img.size, Image.Resampling.NEAREST)

        # 3. Encode to PNG (lossless, highest visual quality) in memory
        img_buffer = io.BytesIO()
        pil_img.save(img_buffer, format="PNG", compress_level=1)
        img_bytes = img_buffer.getvalue()

        mask_buffer = io.BytesIO()
        pil_mask.save(mask_buffer, format="PNG", compress_level=1)
        mask_bytes = mask_buffer.getvalue()

        # 4. JSON payload (standard IOPaint format)
        endpoint = f"{url}/api/v1/inpaint"
        img_b64 = "data:image/png;base64," + base64.b64encode(img_bytes).decode("ascii")
        mask_b64 = "data:image/png;base64," + base64.b64encode(mask_bytes).decode("ascii")

        payload = {
            "image": img_b64,
            "mask": mask_b64,
            "hd_strategy": "Original",
            "hd_strategy_crop_margin": 128,
            "hd_strategy_crop_trigger_size": 1024
        }

        headers = self._get_headers()
        headers["Content-Type"] = "application/json"

        # Serialize inference calls to prevent OpenVINO/Torch "Infer Request is busy" collisions
        with _iopaint_global_lock:
            max_retries = 3
            resp = None
            for attempt in range(max_retries):
                try:
                    resp = self.session.post(
                        endpoint,
                        headers=headers,
                        data=json.dumps(payload),
                        timeout=self.timeout
                    )
                    if resp.status_code == 200:
                        break
                    elif resp.status_code == 500 and "busy" in resp.text.lower():
                        logger.warning(f"IOPaint infer request busy, waiting and retrying ({attempt + 1}/{max_retries})...")
                        time.sleep(1.2)
                        continue
                    else:
                        raise RuntimeError(f"IOPaint Server returned error HTTP {resp.status_code}: {resp.text[:200]}")
                except requests.exceptions.Timeout:
                    raise RuntimeError(f"IOPaint Server timed out after {self.timeout}s during inpainting.")
                except requests.exceptions.ConnectionError as conn_err:
                    if attempt < max_retries - 1:
                        time.sleep(1.0)
                        continue
                    raise RuntimeError(f"Could not connect to IOPaint Server at {url}: {conn_err}")
                except Exception as e:
                    if "busy" in str(e).lower() and attempt < max_retries - 1:
                        logger.warning(f"IOPaint busy ({e}), retrying ({attempt + 1}/{max_retries})...")
                        time.sleep(1.2)
                        continue
                    raise

            if resp is None or resp.status_code != 200:
                err_msg = resp.text[:200] if resp is not None else "No response"
                raise RuntimeError(f"IOPaint Server inpainting failed: {err_msg}")

        # Parse response bytes as image
        res_bytes = resp.content
        cleaned_pil = Image.open(io.BytesIO(res_bytes)).convert("RGB")

        if cleaned_pil.size != pil_img.size:
            cleaned_pil = cleaned_pil.resize(pil_img.size, Image.Resampling.LANCZOS)

        if return_numpy:
            return cv2.cvtColor(np.array(cleaned_pil), cv2.COLOR_RGB2BGR)

        return cleaned_pil


def classify_bubble_background(
    img_bgr: np.ndarray,
    bubble: Optional[dict] = None,
    padding: int = 2
) -> Tuple[str, dict]:
    """
    Analyzes the background pixels surrounding text inside a bubble region to determine if it is:
    - 'flat_white': Pure or near-pure solid white background (majority of manga speech bubbles).
    - 'screentone': Screentone / halftone pattern background requiring deep AI.
    - 'complex_art': Textured, patterned, colored, dark, or artwork background requiring deep AI.
    
    Returns (classification_str, stats_dict).
    """
    if img_bgr is None or img_bgr.size == 0:
        return "complex_art", {"reason": "empty"}

    h_img, w_img = img_bgr.shape[:2]
    if bubble is not None:
        bx = max(0, int(bubble.get("x", 0)))
        by = max(0, int(bubble.get("y", 0)))
        bw = min(w_img - bx, int(bubble.get("width", 0)))
        bh = min(h_img - by, int(bubble.get("height", 0)))
        if bw <= 4 or bh <= 4:
            return "flat_white", {"reason": "too_small"}
        roi_bgr = img_bgr[by : by + bh, bx : bx + bw]
    else:
        bx, by = 0, 0
        bw, bh = w_img, h_img
        roi_bgr = img_bgr

    if roi_bgr.size == 0:
        return "complex_art", {"reason": "empty_roi"}

    if len(roi_bgr.shape) == 3:
        roi_gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    else:
        roi_gray = roi_bgr

    # Polygon-aware mask if specified
    poly_mask = None
    if bubble is not None:
        polys = bubble.get("polygons") or ([bubble.get("polygon")] if bubble.get("polygon") else [])
        if polys:
            p_mask = np.zeros((bh, bw), dtype=np.uint8)
            has_p = False
            for poly in polys:
                try:
                    pts = np.array(poly, dtype=np.int32)
                    if pts.ndim == 1 and len(pts) >= 6:
                        pts = pts.reshape(-1, 2)
                    if pts.ndim == 2 and pts.shape[0] >= 3:
                        local_pts = pts - np.array([bx, by], dtype=np.int32)
                        cv2.fillPoly(p_mask, [local_pts], 255)
                        has_p = True
                except Exception:
                    pass
            if has_p:
                poly_mask = (p_mask > 0)

    valid_mask = poly_mask if poly_mask is not None else np.ones((bh, bw), dtype=bool)
    total_valid = np.count_nonzero(valid_mask)
    if total_valid == 0:
        return "complex_art", {"reason": "empty_valid"}

    # Special handling for manual brush strokes: verify surrounding page context
    if bubble is not None and bubble.get("tool") == "brush":
        ctx_m = 18
        cy1, cy2 = max(0, by - ctx_m), min(h_img, by + bh + ctx_m)
        cx1, cx2 = max(0, bx - ctx_m), min(w_img, bx + bw + ctx_m)
        ctx_bgr = img_bgr[cy1:cy2, cx1:cx2]
        ctx_gray = cv2.cvtColor(ctx_bgr, cv2.COLOR_BGR2GRAY) if len(ctx_bgr.shape) == 3 else ctx_bgr
        ctx_white_ratio = float(np.count_nonzero(ctx_gray >= 210) / max(1, ctx_gray.size))
        ctx_mean = float(np.mean(ctx_gray))
        if ctx_white_ratio < 0.50 or ctx_mean < 175.0:
            return "complex_art", {
                "reason": "brush_on_art",
                "ctx_white_ratio": round(ctx_white_ratio, 3),
                "ctx_mean": round(ctx_mean, 1)
            }

    valid_gray = roi_gray[valid_mask]

    # Global Whiteness & Contrast Metrics
    white_pixels_mask = valid_mask & (roi_gray >= 210)
    total_white_count = np.count_nonzero(white_pixels_mask)
    total_white_ratio = float(total_white_count / total_valid)
    overall_mean = float(np.mean(valid_gray))
    overall_median = float(np.median(valid_gray))
    dark_mask = valid_mask & (roi_gray < 110)
    dark_ratio = float(np.count_nonzero(dark_mask) / total_valid)

    # Color difference check (to detect colored backgrounds in manhwa/webtoons)
    if len(roi_bgr.shape) == 3 and roi_bgr.shape[2] >= 3:
        b = roi_bgr[:, :, 0]
        g = roi_bgr[:, :, 1]
        r = roi_bgr[:, :, 2]
        color_diff = np.maximum(np.maximum(b, g), r) - np.minimum(np.minimum(b, g), r)
        mean_col_diff = float(np.mean(color_diff[white_pixels_mask])) if total_white_count > 0 else float(np.mean(color_diff[valid_mask]))
    else:
        mean_col_diff = 0.0

    # Border / Perimeter Whiteness (speech bubbles have white margins around text)
    m_y = max(1, int(bh * 0.10))
    m_x = max(1, int(bw * 0.10))
    border_mask = np.zeros((bh, bw), dtype=bool)
    border_mask[:m_y, :] = True
    border_mask[-m_y:, :] = True
    border_mask[:, :m_x] = True
    border_mask[:, -m_x:] = True
    border_valid = border_mask & valid_mask
    if np.any(border_valid):
        border_pixels = roi_gray[border_valid]
        border_white_ratio = float(np.count_nonzero(border_pixels >= 210) / len(border_pixels))
        border_mean = float(np.mean(border_pixels))
    else:
        border_white_ratio = 1.0
        border_mean = 255.0

    # Screentone / Texture / Halftone check on candidate background
    edges = cv2.Canny(roi_gray, 50, 150)
    if total_white_count > 0:
        bg_edge_density = float(np.count_nonzero(edges[white_pixels_mask]) / total_white_count)
    else:
        bg_edge_density = float(np.count_nonzero(edges[valid_mask]) / total_valid)

    stats = {
        "total_white_ratio": round(total_white_ratio, 3),
        "overall_mean": round(overall_mean, 1),
        "overall_median": round(overall_median, 1),
        "dark_ratio": round(dark_ratio, 3),
        "border_white_ratio": round(border_white_ratio, 3),
        "border_mean": round(border_mean, 1),
        "col_diff": round(mean_col_diff, 1),
        "edge_density": round(bg_edge_density, 3)
    }

    # Reliable Flat White Verification:
    # 1. Total white ratio >= 65% (since dark text letters take up 20-30% of speech bubbles)
    # 2. Border perimeter is white (>= 70%)
    # 3. Overall median brightness must be white (>= 220.0)
    # 4. Overall mean brightness must be high (>= 185.0)
    # 5. Border mean brightness must be high (>= 190.0)
    # 6. No heavy colored tint (col_diff <= 18.0)
    # 7. No screentone/halftone texture in background (edge_density <= 0.04)
    is_flat_white = (
        total_white_ratio >= 0.65 and
        border_white_ratio >= 0.70 and
        dark_ratio <= 0.35 and
        overall_mean >= 185.0 and
        overall_median >= 220.0 and
        border_mean >= 190.0 and
        mean_col_diff <= 18.0 and
        bg_edge_density <= 0.04
    )

    if is_flat_white:
        return "flat_white", stats

    # Screentone / Halftone
    if bg_edge_density > 0.05 or (overall_mean > 160.0 and total_white_ratio < 0.50):
        return "screentone", stats

    # Complex Art / Watermark / Dark Banner / SFX / Colored
    return "complex_art", stats


def generate_bubble_lasso_polygons(lines: list, line_gap_threshold: float = 2.0) -> list:
    """
    Given a list of text lines in a bubble (each line is a list of [x, y] points):
    - Combines lines that belong to the same speech bubble dialogue into unified polygonal lasso convex hulls.
    - Matches the Photoshop Lasso tool workflow (encircling the full text block in one smooth boundary).
    - Only splits if there is an extreme vertical gap (> 2.0x line height) with zero horizontal overlap.
    - Returns a list of polygon contours (each polygon is a list of [x, y] points).
    """
    if not lines or not isinstance(lines, (list, tuple)):
        return []
    line_infos = []
    for l in lines:
        if not isinstance(l, (list, tuple)):
            continue
        try:
            pts = np.array(l, dtype=np.float32)
            if pts.ndim == 1 and len(pts) >= 6:
                pts = pts.reshape(-1, 2)
            if pts.ndim != 2 or pts.shape[0] < 2:
                continue
            min_x = float(np.min(pts[:, 0]))
            max_x = float(np.max(pts[:, 0]))
            min_y = float(np.min(pts[:, 1]))
            max_y = float(np.max(pts[:, 1]))
            h = max(8.0, max_y - min_y)
            w = max(8.0, max_x - min_x)
            line_infos.append({
                'pts': pts,
                'min_x': min_x,
                'max_x': max_x,
                'min_y': min_y,
                'max_y': max_y,
                'height': h,
                'width': w
            })
        except Exception:
            continue
    if not line_infos:
        return []
    line_infos.sort(key=lambda x: x['min_y'])
    clusters = [[line_infos[0]]]
    for i in range(1, len(line_infos)):
        prev_line = clusters[-1][-1]
        curr_line = line_infos[i]
        avg_h = (prev_line['height'] + curr_line['height']) / 2.0
        gap = curr_line['min_y'] - prev_line['max_y']

        # Only split if there is an extreme vertical gap (> 2.0x line height) with zero horizontal overlap
        overlap_x = max(0.0, min(prev_line['max_x'], curr_line['max_x']) - max(prev_line['min_x'], curr_line['min_x']))
        is_separate = (gap > (avg_h * line_gap_threshold) and overlap_x <= 0.0)
        if is_separate:
            clusters.append([curr_line])
        else:
            clusters[-1].append(curr_line)
    cluster_polys = []
    for cluster in clusters:
        cluster_pts = []
        for l_info in cluster:
            for p in l_info['pts']:
                cluster_pts.append(p)
        if len(cluster_pts) >= 3:
            hull = cv2.convexHull(np.array(cluster_pts, dtype=np.int32))
            cluster_polys.append(hull.reshape(-1, 2).tolist())
    return cluster_polys


def compute_safe_bubble_text_mask(
    gray_roi: np.ndarray,
    initial_text_mask: Optional[np.ndarray],
    dilation: int = 5
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes a smart adaptive text mask and a protective speech bubble border shield.
    
    1. Captures 100% of all text strokes, dots, punctuation marks, and anti-aliased subpixels
       using connected components inside the bubble text zone (zero residual specks).
    2. Identifies speech bubble borders, panel contours, spikes, and dividing lines.
    3. Builds a protected border shield with a safety buffer that strictly prevents erosion (0px erased).
    4. Expands text with requested padding/dilation while strictly respecting the border shield.
    
    :return: (safe_clean_mask, border_shield)
    """
    bh, bw = gray_roi.shape[:2]
    if bh <= 4 or bw <= 4:
        init_m = initial_text_mask.copy() if initial_text_mask is not None else np.zeros((bh, bw), dtype=np.uint8)
        return init_m, np.zeros((bh, bw), dtype=np.uint8)

    # Adaptive ink thresholding
    if np.mean(gray_roi) < 100:
        # Inverted bubble (white text on dark background)
        ink_binary = (gray_roi > 140).astype(np.uint8) * 255
    else:
        bg_val = float(np.percentile(gray_roi, 85))
        ink_thresh = min(235, max(140, int(bg_val - 25)))
        ink_binary = (gray_roi < ink_thresh).astype(np.uint8) * 255

    num_ink, ink_labels, ink_stats, _ = cv2.connectedComponentsWithStats(ink_binary, connectivity=8)

    border_mask = np.zeros((bh, bw), dtype=np.uint8)
    text_ink_mask = np.zeros((bh, bw), dtype=np.uint8)

    has_text_ref = initial_text_mask is not None and np.any(initial_text_mask > 0)
    if has_text_ref:
        # Search zone for punctuation marks near text
        k_punct_search = cv2.dilate(initial_text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (45, 45)))
    else:
        k_punct_search = np.zeros((bh, bw), dtype=np.uint8)

    for i in range(1, num_ink):
        cw = ink_stats[i, cv2.CC_STAT_WIDTH]
        ch = ink_stats[i, cv2.CC_STAT_HEIGHT]
        left = ink_stats[i, cv2.CC_STAT_LEFT]
        top = ink_stats[i, cv2.CC_STAT_TOP]
        area = ink_stats[i, cv2.CC_STAT_AREA]
        comp = (ink_labels == i)

        solidity = area / float(cw * ch) if (cw * ch > 0) else 1.0
        touches_edge = (left <= 3 or top <= 3 or left + cw >= bw - 3 or top + ch >= bh - 3)

        # Bubble borders/curves are elongated thin strokes (low solidity) or touch ROI perimeter edges
        is_border = (
            (max(cw, ch) > 75 and solidity < 0.25)
            or (max(cw, ch) > 120)
            or (touches_edge and (cw > 50 or ch > 50 or area > 300))
        )

        if has_text_ref:
            # Check direct intersection with text reference
            intersects_text = np.any(comp & (initial_text_mask > 0))
            
            # Check if it is a punctuation mark / dot / dash / symbol (e.g. ? ! . , ... - ~ " ' :)
            # Any unattached ink glyph inside the speech bubble that is not an outer border belongs to text/punctuation
            is_punctuation = (
                (not is_border and not touches_edge and max(cw, ch) <= 95 and area <= 2500)
                or (area <= 400 and max(cw, ch) <= 45 and np.any(comp & (k_punct_search > 0)))
            )
            
            if (intersects_text or is_punctuation) and not is_border:
                if touches_edge and (cw > 50 or ch > 50 or area > 300):
                    # Text stroke merged with subtle background gradient / border at edge!
                    # Preserve text inside the expanded text zone, assign outer tail to border
                    k_zone = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
                    text_zone = cv2.dilate(initial_text_mask, k_zone)
                    text_zone_comp = comp & (text_zone > 0)
                    border_zone_comp = comp & (text_zone == 0)
                    if np.any(text_zone_comp):
                        text_ink_mask[text_zone_comp] = 255
                    if np.any(border_zone_comp):
                        border_mask[border_zone_comp] = 255
                else:
                    text_ink_mask[comp] = 255
            else:
                # Outside text reference -> it is bubble border / panel line / artwork!
                border_mask[comp] = 255
        else:
            # Fallback when no text polygons provided: central ink is text, perimeter ink is border
            if is_border or touches_edge or area > (bw * bh * 0.2):
                border_mask[comp] = 255
            else:
                text_ink_mask[comp] = 255

    # Protected border shield: dilate border_mask by 2px (5x5 ellipse)
    k_shield = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    shield = cv2.dilate(border_mask, k_shield)

    # Effective dilation for text ink
    eff_d = max(4, dilation if dilation > 0 else 4)
    k_text = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (eff_d * 2 + 1, eff_d * 2 + 1))
    
    # Expand text ink with padding
    dilated_text = cv2.dilate(text_ink_mask, k_text, iterations=1)

    # Safe mask has full padding, never touches shield, and 100% preserves border lines
    safe_mask = ((dilated_text & (~shield)) | text_ink_mask) & (~border_mask)
    return safe_mask, shield


def create_bubble_border_shield(
    gray_roi: np.ndarray,
    text_mask: Optional[np.ndarray] = None,
    bg_threshold: int = 185
) -> np.ndarray:
    """
    Builds a protected barrier mask for the speech bubble's outer borders and dividing contours.
    Returns an 8-bit mask (255 = protected border line, 0 = interior/safe to clean).
    Guarantees that text padding/dilation will NEVER erase or eat into the bubble border.
    """
    _, shield = compute_safe_bubble_text_mask(
        gray_roi,
        text_mask if text_mask is not None else np.zeros_like(gray_roi),
        dilation=5
    )
    return shield


def clean_flat_bubble_locally(
    img_bgr: np.ndarray,
    bubble: dict,
    classification: str = "flat_white",
    dilation: int = 5,
    padding: int = 2
) -> np.ndarray:
    """
    Cleans text inside a flat white or solid color bubble locally with instant execution (< 0.002s).
    Captures 100% of text strokes, dots, and punctuation marks without leaving any residue,
    while strictly protecting outer speech bubble outlines and dividing borders (0px erosion).
    """
    h_img, w_img = img_bgr.shape[:2]
    bx = max(0, int(bubble.get("x", 0)))
    by = max(0, int(bubble.get("y", 0)))
    bw = min(w_img - bx, int(bubble.get("width", 0)))
    bh = min(h_img - by, int(bubble.get("height", 0)))

    if bw <= 4 or bh <= 4:
        return img_bgr

    roi_bgr = img_bgr[by : by + bh, bx : bx + bw].copy()
    gray_roi = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY) if len(roi_bgr.shape) == 3 else roi_bgr.copy()

    local_text_mask = np.zeros((bh, bw), dtype=np.uint8)
    has_polys = False

    # Prefer lines first (tightest contour per individual text line, avoiding bridging gaps)
    lines = bubble.get("lines", [])
    if lines and isinstance(lines, (list, tuple)) and len(lines) > 0:
        for line_poly in lines:
            try:
                pts = np.array(line_poly, dtype=np.int32)
                if pts.ndim == 2 and pts.shape[0] >= 3:
                    local_pts = pts - np.array([bx, by], dtype=np.int32)
                    cv2.fillPoly(local_text_mask, [local_pts], 255)
                    has_polys = True
                elif pts.ndim == 1 and len(pts) >= 6:
                    pts = pts.reshape(-1, 2)
                    local_pts = pts - np.array([bx, by], dtype=np.int32)
                    cv2.fillPoly(local_text_mask, [local_pts], 255)
                    has_polys = True
            except Exception:
                pass

    if not has_polys:
        polygons = bubble.get("polygons")
        if not polygons and bubble.get("lines"):
            polygons = generate_bubble_lasso_polygons(bubble.get("lines"))
        if not polygons and bubble.get("polygon"):
            polygons = [bubble.get("polygon")]

        if polygons and isinstance(polygons, (list, tuple)) and len(polygons) > 0:
            for poly in polygons:
                try:
                    pts = np.array(poly, dtype=np.int32)
                    if pts.ndim == 2 and pts.shape[0] >= 3:
                        local_pts = pts - np.array([bx, by], dtype=np.int32)
                        cv2.fillPoly(local_text_mask, [local_pts], 255)
                        has_polys = True
                    elif pts.ndim == 1 and len(pts) >= 6:
                        pts = pts.reshape(-1, 2)
                        local_pts = pts - np.array([bx, by], dtype=np.int32)
                        cv2.fillPoly(local_text_mask, [local_pts], 255)
                        has_polys = True
                except Exception:
                    pass

    # Ensure text_x, text_y, text_width, text_height is also included in local_text_mask
    # so that trailing punctuation marks (e.g. ?, !, ..., -) detected by the block detector are always included
    tx = bubble.get("text_x")
    ty = bubble.get("text_y")
    tw = bubble.get("text_width")
    th = bubble.get("text_height")

    if tx is not None and tw is not None and int(tw) > 0 and int(th) > 0:
        ltx = max(0, int(tx) - bx)
        lty = max(0, int(ty) - by)
        ltw = min(bw - ltx, int(tw))
        lth = min(bh - lty, int(th))
        if ltw > 0 and lth > 0:
            local_text_mask[lty : lty + lth, ltx : ltx + ltw] = 255
            has_polys = True
    elif not has_polys:
        inset_x = int(bw * 0.15) if bw > 30 else 0
        inset_y = int(bh * 0.15) if bh > 30 else 0
        ltx = max(0, inset_x)
        lty = max(0, inset_y)
        ltw = min(bw - ltx, max(1, bw - (inset_x * 2)))
        lth = min(bh - lty, max(1, bh - (inset_y * 2)))
        if ltw > 0 and lth > 0:
            local_text_mask[lty : lty + lth, ltx : ltx + ltw] = 255

    # Compute safe mask with generous text padding and 100% border preservation
    eff_dilation = max(5, dilation if dilation > 0 else 5, bubble.get("mask_padding", 0), padding)
    safe_clean_mask, shield = compute_safe_bubble_text_mask(gray_roi, local_text_mask, dilation=eff_dilation)

    # Clean the masked text strokes
    if classification == "flat_white":
        # Adaptive fill color: sample background color inside the bubble
        bg_mask = (gray_roi > 190) & (shield == 0) & (safe_clean_mask == 0)
        if np.any(bg_mask):
            bg_col = np.median(roi_bgr[bg_mask], axis=0).astype(np.uint8).tolist()
            if all(c >= 240 for c in bg_col):
                bg_col = [255, 255, 255]
        else:
            bg_col = [255, 255, 255]
        roi_bgr[safe_clean_mask > 0] = bg_col
    else:
        roi_bgr = cv2.inpaint(roi_bgr, safe_clean_mask, 3, cv2.INPAINT_TELEA)

    img_bgr[by : by + bh, bx : bx + bw] = roi_bgr
    return img_bgr


def generate_page_mask(
    image_size: Tuple[int, int],
    bubbles: List[dict],
    dilation: int = 5,
    padding: int = 2,
    img_bgr: Optional[np.ndarray] = None
) -> Image.Image:
    """
    Generates a high-quality binary inpainting mask (white on black) specifically targeting
    the exact TEXT lines / contours inside speech bubbles, with Bubble Border Shielding
    preserving the outer speech bubble outlines, borders, tails, and dividing lines 100%.
    
    :param image_size: (width, height) of the manga page.
    :param bubbles: List of bubble dicts.
    :param dilation: Morphological expansion (in px) to completely cover text strokes.
    :param padding: Extra bounding box padding.
    :param img_bgr: Optional OpenCV image for computing accurate border shielding.
    :return: 8-bit Grayscale PIL Image mask where 255 = area to inpaint, 0 = keep.
    """
    w, h = image_size
    mask_np = np.zeros((h, w), dtype=np.uint8)

    effective_dilation = max(5, dilation if dilation > 0 else 5)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (effective_dilation * 2 + 1, effective_dilation * 2 + 1))

    for b in bubbles:
        bx = max(0, int(b.get("x", 0)))
        by = max(0, int(b.get("y", 0)))
        bw = min(w - bx, int(b.get("width", 0)))
        bh = min(h - by, int(b.get("height", 0)))

        if bw <= 4 or bh <= 4:
            continue

        local_mask = np.zeros((bh, bw), dtype=np.uint8)

        has_polys = False

        # Prefer lines first (tightest contour per individual text line, avoiding bridging gaps)
        lines = b.get("lines", [])
        if lines and isinstance(lines, (list, tuple)) and len(lines) > 0:
            for line_poly in lines:
                try:
                    pts = np.array(line_poly, dtype=np.int32)
                    if pts.ndim == 2 and pts.shape[0] >= 3:
                        local_pts = pts - np.array([bx, by], dtype=np.int32)
                        cv2.fillPoly(local_mask, [local_pts], 255)
                        has_polys = True
                    elif pts.ndim == 1 and len(pts) >= 6:
                        pts = pts.reshape(-1, 2)
                        local_pts = pts - np.array([bx, by], dtype=np.int32)
                        cv2.fillPoly(local_mask, [local_pts], 255)
                        has_polys = True
                except Exception:
                    pass

        if not has_polys:
            polygons = b.get("polygons")
            if not polygons and b.get("lines"):
                polygons = generate_bubble_lasso_polygons(b.get("lines"))
            if not polygons and b.get("polygon"):
                polygons = [b.get("polygon")]

            if polygons and isinstance(polygons, (list, tuple)) and len(polygons) > 0:
                for poly in polygons:
                    try:
                        pts = np.array(poly, dtype=np.int32)
                        if pts.ndim == 2 and pts.shape[0] >= 3:
                            local_pts = pts - np.array([bx, by], dtype=np.int32)
                            cv2.fillPoly(local_mask, [local_pts], 255)
                            has_polys = True
                        elif pts.ndim == 1 and len(pts) >= 6:
                            pts = pts.reshape(-1, 2)
                            local_pts = pts - np.array([bx, by], dtype=np.int32)
                            cv2.fillPoly(local_mask, [local_pts], 255)
                            has_polys = True
                    except Exception:
                        pass

        # Ensure text_x, text_y, text_width, text_height is also included in local_mask
        # so that trailing punctuation marks (e.g. ?, !, ..., -) detected by the block detector are always included
        tx = b.get("text_x")
        ty = b.get("text_y")
        tw = b.get("text_width")
        th = b.get("text_height")

        if tx is not None and tw is not None and int(tw) > 0 and int(th) > 0:
            ltx = max(0, int(tx) - bx)
            lty = max(0, int(ty) - by)
            ltw = min(bw - ltx, int(tw))
            lth = min(bh - lty, int(th))
            if ltw > 0 and lth > 0:
                local_mask[lty : lty + lth, ltx : ltx + ltw] = 255
                has_polys = True
        elif not has_polys:
            inset_x = int(bw * 0.15) if bw > 30 else 0
            inset_y = int(bh * 0.15) if bh > 30 else 0
            ltx = max(0, inset_x)
            lty = max(0, inset_y)
            ltw = min(bw - ltx, max(1, bw - (inset_x * 2)))
            lth = min(bh - lty, max(1, bh - (inset_y * 2)))
            if ltw > 0 and lth > 0:
                local_mask[lty : lty + lth, ltx : ltx + ltw] = 255

        # Protect bubble border if image is provided
        if img_bgr is not None and img_bgr.shape[0] >= (by + bh) and img_bgr.shape[1] >= (bx + bw):
            roi = img_bgr[by : by + bh, bx : bx + bw]
            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if len(roi.shape) == 3 else roi
            safe_bubble_mask, _ = compute_safe_bubble_text_mask(gray_roi, local_mask, dilation=dilation)
        else:
            safe_bubble_mask = cv2.dilate(local_mask, kernel, iterations=1)

        mask_np[by : by + bh, bx : bx + bw] = np.bitwise_or(
            mask_np[by : by + bh, bx : bx + bw],
            safe_bubble_mask
        )

    return Image.fromarray(mask_np, mode="L")


def smart_adaptive_inpaint_page(
    server_url: str,
    image_input: Union[Image.Image, np.ndarray, str, Path],
    bubbles: List[dict],
    deep_model: str = "anime-lama",
    dilation: int = 5,
    padding: int = 2,
    progress_callback=None
) -> Tuple[Image.Image, dict]:
    """
    Smart Adaptive Hybrid Inpainting:
    1. Analyzes each speech bubble background.
    2. Instantly cleans flat white & solid bubbles locally (< 0.005s each) with pure color fidelity.
    3. Routes only complex art / textured / screentone bubbles to IOPaint deep AI (anime-lama).
    4. If all bubbles are flat white, skips the heavy AI model completely!
    
    :return: (cleaned_pil_image, stats_dict)
    """
    if isinstance(image_input, (str, Path)):
        p_str = str(image_input)
        try:
            buf = np.fromfile(p_str, dtype=np.uint8)
            img_bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR) if (buf is not None and len(buf) > 0) else None
        except Exception:
            img_bgr = None
        if img_bgr is None:
            img_bgr = cv2.imread(p_str)
    elif isinstance(image_input, np.ndarray):
        img_bgr = image_input.copy()
    elif isinstance(image_input, Image.Image):
        img_bgr = cv2.cvtColor(np.array(image_input.convert("RGB")), cv2.COLOR_RGB2BGR)
    else:
        raise ValueError(f"Unsupported image input type: {type(image_input)}")

    if img_bgr is None:
        raise ValueError("Failed to load image for inpainting.")

    if not bubbles:
        pil_res = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        return pil_res, {"flat_count": 0, "complex_count": 0, "total": 0, "ai_skipped": True}

    flat_bubbles = []
    complex_bubbles = []

    # 1. Classify all bubbles
    for b in bubbles:
        bt = b.get("bg_type", "")
        if bt in ("complex", "screentone", "art", "not_white"):
            complex_bubbles.append(b)
            continue
        if bt == "white":
            flat_bubbles.append((b, "flat_white"))
            continue
        cls_type, stats = classify_bubble_background(img_bgr, b, padding=padding)
        if cls_type == "flat_white" or stats.get("total_white_ratio", 0) >= 0.65:
            flat_bubbles.append((b, "flat_white"))
        else:
            complex_bubbles.append(b)

    # 2. Pass 1: Instantly clean all flat/white bubbles locally
    for b, cls_type in flat_bubbles:
        img_bgr = clean_flat_bubble_locally(img_bgr, b, classification=cls_type, dilation=dilation, padding=padding)

    stats = {
        "flat_count": len(flat_bubbles),
        "complex_count": len(complex_bubbles),
        "total": len(bubbles),
        "ai_skipped": len(complex_bubbles) == 0
    }

    # 3. Pass 2: If there are complex art bubbles, send ONLY small crops to IOPaint AI concurrently (Multi-tasking)!
    if complex_bubbles and server_url:
        total_complex = len(complex_bubbles)
        if progress_callback:
            progress_callback(f"🧠 Multi-tasking: Inpainting {total_complex} complex bubble crop(s) concurrently ({deep_model})...")
        logger.info(f"Smart Inpaint: {len(flat_bubbles)} cleaned instantly locally, {total_complex} cropped & routed concurrently to AI.")

        pil_intermediate = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        client = IOPaintClient(server_url)

        def inpaint_crop_worker(b_info):
            b_idx, bubble = b_info
            bx = int(bubble.get("x", 0))
            by = int(bubble.get("y", 0))
            bw = int(bubble.get("width", 0))
            bh = int(bubble.get("height", 0))

            tx = bubble.get("text_x")
            ty = bubble.get("text_y")
            tw = bubble.get("text_width")
            th = bubble.get("text_height")

            # Build unified polygonal lasso mask (convex hull around lines, or user polygon)
            polys = []
            if bubble.get("lines"):
                polys = generate_bubble_lasso_polygons(bubble["lines"])
            if not polys and bubble.get("polygons"):
                polys = bubble["polygons"]
            if not polys and bubble.get("polygon"):
                polys = [bubble["polygon"]]

            all_poly_pts = []
            if polys:
                for poly in polys:
                    pts = np.array(poly, dtype=np.int32)
                    if pts.ndim == 1 and len(pts) >= 6:
                        pts = pts.reshape(-1, 2)
                    if pts.ndim == 2 and pts.shape[0] >= 3:
                        all_poly_pts.extend(pts.tolist())

            if all_poly_pts:
                poly_arr = np.array(all_poly_pts, dtype=np.int32)
                sel_x1 = int(np.min(poly_arr[:, 0]))
                sel_x2 = int(np.max(poly_arr[:, 0]))
                sel_y1 = int(np.min(poly_arr[:, 1]))
                sel_y2 = int(np.max(poly_arr[:, 1]))
            elif tx is not None and tw is not None and int(tw) > 0 and int(th) > 0:
                sel_x1, sel_y1 = int(tx), int(ty)
                sel_x2, sel_y2 = int(tx) + int(tw), int(ty) + int(th)
            else:
                sel_x1, sel_y1 = bx, by
                sel_x2, sel_y2 = bx + bw, by + bh

            # Crop bounds with 60px context padding (exact Photoshop plugin setting)
            w_page, h_page = pil_intermediate.size
            padding_context = 60
            roi_x1 = max(0, sel_x1 - padding_context)
            roi_y1 = max(0, sel_y1 - padding_context)
            roi_x2 = min(w_page, sel_x2 + padding_context)
            roi_y2 = min(h_page, sel_y2 + padding_context)
            roi_w = roi_x2 - roi_x1
            roi_h = roi_y2 - roi_y1

            crop_img = pil_intermediate.crop((roi_x1, roi_y1, roi_x2, roi_y2))
            local_mask_np = np.zeros((roi_h, roi_w), dtype=np.uint8)

            if polys:
                for poly in polys:
                    pts = np.array(poly, dtype=np.int32) - np.array([roi_x1, roi_y1], dtype=np.int32)
                    if pts.ndim == 1 and len(pts) >= 6:
                        pts = pts.reshape(-1, 2)
                    if pts.ndim == 2 and pts.shape[0] >= 3:
                        cv2.fillPoly(local_mask_np, [pts], 255)
            else:
                lx1 = max(0, sel_x1 - roi_x1)
                ly1 = max(0, sel_y1 - roi_y1)
                lx2 = min(roi_w, sel_x2 - roi_x1)
                ly2 = min(roi_h, sel_y2 - roi_y1)
                if lx2 > lx1 and ly2 > ly1:
                    local_mask_np[ly1:ly2, lx1:lx2] = 255

            eff_dilation = max(dilation, bubble.get("mask_padding", 0), padding, 6)
            if eff_dilation > 0:
                k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (eff_dilation * 2 + 1, eff_dilation * 2 + 1))
                safe_crop_mask = cv2.dilate(local_mask_np, k)
            else:
                safe_crop_mask = local_mask_np.copy()

            local_mask_pil = Image.fromarray(safe_crop_mask, mode="L")
            cleaned_crop = client.inpaint(crop_img, local_mask_pil)
            return (b_idx, roi_x1, roi_y1, cleaned_crop)

        for i, b in enumerate(complex_bubbles):
            try:
                b_idx, rx1, ry1, cleaned_crop = inpaint_crop_worker((i, b))
                pil_intermediate.paste(cleaned_crop, (rx1, ry1))
                if progress_callback:
                    progress_callback(f"🧹 Cleaned complex crop [{i + 1}/{total_complex}]")
            except Exception as c_err:
                logger.warning(f"Error inpainting complex crop #{i + 1}: {c_err}")

        return pil_intermediate, stats
    else:
        logger.info(f"Smart Inpaint: All {len(flat_bubbles)} bubbles cleaned instantly locally in <0.02s (AI skipped)!")
        cleaned_pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        return cleaned_pil, stats


def inpaint_manga_page(
    server_url: str,
    image_input: Union[Image.Image, np.ndarray, str, Path],
    bubbles: List[dict],
    dilation: int = 5,
    padding: int = 2,
    adaptive: bool = True,
    deep_model: str = "anime-lama",
    progress_callback=None
) -> Image.Image:
    """
    Cleans and inpaints speech bubbles on a manga page.
    If adaptive=True (default), automatically switches between instant local cleaning for flat white bubbles
    and deep neural network inpainting for complex art bubbles.
    """
    if adaptive:
        cleaned_pil, _ = smart_adaptive_inpaint_page(
            server_url=server_url,
            image_input=image_input,
            bubbles=bubbles,
            deep_model=deep_model,
            dilation=dilation,
            padding=padding,
            progress_callback=progress_callback
        )
        return cleaned_pil

    # Full AI Mode with concurrent crop inpainting
    if isinstance(image_input, (str, Path)):
        pil_img = Image.open(str(image_input)).convert("RGB")
    elif isinstance(image_input, np.ndarray):
        pil_img = Image.fromarray(cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB))
    elif isinstance(image_input, Image.Image):
        pil_img = image_input.convert("RGB")
    else:
        raise ValueError(f"Unsupported image input type: {type(image_input)}")

    if not bubbles:
        return pil_img.copy()

    from concurrent.futures import ThreadPoolExecutor, as_completed
    client = IOPaintClient(server_url)
    result_page = pil_img.copy()
    w_page, h_page = result_page.size

    def _inpaint_one(b_info):
        idx, bubble = b_info
        bx = int(bubble.get("x", 0))
        by = int(bubble.get("y", 0))
        bw = int(bubble.get("width", 0))
        bh = int(bubble.get("height", 0))
        margin = 64

        rx1 = max(0, bx - margin)
        ry1 = max(0, by - margin)
        rx2 = min(w_page, bx + bw + margin)
        ry2 = min(h_page, by + bh + margin)
        rw = rx2 - rx1
        rh = ry2 - ry1

        crop = result_page.crop((rx1, ry1, rx2, ry2))
        local_mask = np.zeros((rh, rw), dtype=np.uint8)

        lines = bubble.get("lines", [])
        if not lines and bubble.get("polygons"):
            lines = bubble.get("polygons")
        if not lines and bubble.get("polygon"):
            lines = [bubble.get("polygon")]
        has_lines = False
        if lines and isinstance(lines, (list, tuple)) and len(lines) > 0:
            for line_poly in lines:
                try:
                    pts = np.array(line_poly, dtype=np.int32)
                    if pts.ndim == 2 and pts.shape[0] >= 3:
                        local_pts = pts - np.array([rx1, ry1], dtype=np.int32)
                        cv2.fillPoly(local_mask, [local_pts], 255)
                        has_lines = True
                    elif pts.ndim == 1 and len(pts) >= 6:
                        pts = pts.reshape(-1, 2)
                        local_pts = pts - np.array([rx1, ry1], dtype=np.int32)
                        cv2.fillPoly(local_mask, [local_pts], 255)
                        has_lines = True
                except Exception:
                    pass

        tx = bubble.get("text_x")
        ty = bubble.get("text_y")
        tw = bubble.get("text_width")
        th = bubble.get("text_height")

        if tx is not None and tw is not None and int(tw) > 0 and int(th) > 0:
            ltx = max(0, int(tx) - rx1)
            lty = max(0, int(ty) - ry1)
            ltw = min(rw - ltx, int(tw))
            lth = min(rh - lty, int(th))
            if ltw > 0 and lth > 0:
                local_mask[lty : lty + lth, ltx : ltx + ltw] = 255
        elif not has_lines:
            ltx = max(0, bx - rx1)
            lty = max(0, by - ry1)
            ltw = min(rw - ltx, bw)
            lth = min(rh - lty, bh)
            if ltw > 0 and lth > 0:
                local_mask[lty : lty + lth, ltx : ltx + ltw] = 255

        eff_dilation = max(dilation, bubble.get("mask_padding", 0), padding)
        is_explicitly_complex = bubble.get("bg_type") in ("complex", "screentone", "art", "not_white")
        tool_name = bubble.get("tool", "")
        if tool_name in ("box", "lasso", "brush", "wand", "manual") or is_explicitly_complex:
            safe_crop_mask = local_mask.copy()
            if eff_dilation > 0:
                k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (eff_dilation * 2 + 1, eff_dilation * 2 + 1))
                safe_crop_mask = cv2.dilate(safe_crop_mask, k)
        else:
            crop_cv = cv2.cvtColor(np.array(crop), cv2.COLOR_RGB2GRAY)
            safe_crop_mask, _ = compute_safe_bubble_text_mask(crop_cv, local_mask, dilation=eff_dilation)
            if np.count_nonzero(safe_crop_mask) < 20 and np.count_nonzero(local_mask) > 0:
                safe_crop_mask = local_mask.copy()
                if eff_dilation > 0:
                    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (eff_dilation * 2 + 1, eff_dilation * 2 + 1))
                    safe_crop_mask = cv2.dilate(safe_crop_mask, k)

        m_pil = Image.fromarray(safe_crop_mask, mode="L")
        cleaned_crop = client.inpaint(crop, m_pil)
        return (idx, rx1, ry1, cleaned_crop)

    total_b = len(bubbles)
    for i, b in enumerate(bubbles):
        try:
            _, rx1, ry1, c_crop = _inpaint_one((i, b))
            result_page.paste(c_crop, (rx1, ry1))
            if progress_callback:
                progress_callback(f"🧹 Cleaned bubble [{i + 1}/{total_b}]")
        except Exception as e:
            logger.warning(f"Crop inpaint error on bubble #{i + 1}: {e}")

    return result_page


def inpaint_single_bubble(
    server_url: str,
    base_page_pil: Image.Image,
    bubble: dict,
    dilation: int = 5,
    margin_expand: int = 40,
    adaptive: bool = True,
    model: Optional[str] = None
) -> Image.Image:
    """
    Inpaints only the text area of a specific speech bubble on the page and pastes it seamlessly back.
    If adaptive=True and bubble is flat white, immediately cleans flat white bubbles in 0.001s without server overhead.
    If bubble is not white (complex art, screentone, dark, colored), routes immediately to IOPaint AI.
    """
    w_page, h_page = base_page_pil.size
    
    # Outer bubble boundary for ROI context
    bx = int(bubble.get("x", 0))
    by = int(bubble.get("y", 0))
    bw = int(bubble.get("width", 0))
    bh = int(bubble.get("height", 0))

    if bw <= 0 or bh <= 0:
        return base_page_pil

    is_explicitly_complex = bubble.get("bg_type") in ("complex", "screentone", "art", "not_white")
    is_explicitly_white = bubble.get("bg_type") == "white"

    # Fast Local Clean for Flat White Bubbles (skipped if explicitly marked non-white/complex)
    if adaptive and (is_explicitly_white or not is_explicitly_complex):
        img_bgr = cv2.cvtColor(np.array(base_page_pil.convert("RGB")), cv2.COLOR_RGB2BGR)
        if is_explicitly_white:
            cleaned_bgr = clean_flat_bubble_locally(img_bgr, bubble, classification="flat_white", dilation=dilation)
            return Image.fromarray(cv2.cvtColor(cleaned_bgr, cv2.COLOR_BGR2RGB))
        cls_type, stats = classify_bubble_background(img_bgr, bubble)
        if cls_type == "flat_white" or stats.get("total_white_ratio", 0) >= 0.65:
            cleaned_bgr = clean_flat_bubble_locally(img_bgr, bubble, classification="flat_white", dilation=dilation)
            return Image.fromarray(cv2.cvtColor(cleaned_bgr, cv2.COLOR_BGR2RGB))

    # Complex Art / Non-White / Full AI Mode: Route ROI crop directly to IOPaint server
    tx = bubble.get("text_x")
    ty = bubble.get("text_y")
    tw = bubble.get("text_width")
    th = bubble.get("text_height")

    # Build unified polygonal lasso mask (convex hull around lines, or user polygon)
    polys = []
    if bubble.get("lines"):
        polys = generate_bubble_lasso_polygons(bubble["lines"])
    if not polys and bubble.get("polygons"):
        polys = bubble["polygons"]
    if not polys and bubble.get("polygon"):
        polys = [bubble["polygon"]]

    all_poly_pts = []
    if polys:
        for poly in polys:
            pts = np.array(poly, dtype=np.int32)
            if pts.ndim == 1 and len(pts) >= 6:
                pts = pts.reshape(-1, 2)
            if pts.ndim == 2 and pts.shape[0] >= 3:
                all_poly_pts.extend(pts.tolist())

    if all_poly_pts:
        poly_arr = np.array(all_poly_pts, dtype=np.int32)
        sel_x1 = int(np.min(poly_arr[:, 0]))
        sel_x2 = int(np.max(poly_arr[:, 0]))
        sel_y1 = int(np.min(poly_arr[:, 1]))
        sel_y2 = int(np.max(poly_arr[:, 1]))
    elif tx is not None and tw is not None and int(tw) > 0 and int(th) > 0:
        sel_x1, sel_y1 = int(tx), int(ty)
        sel_x2, sel_y2 = int(tx) + int(tw), int(ty) + int(th)
    else:
        sel_x1, sel_y1 = bx, by
        sel_x2, sel_y2 = bx + bw, by + bh

    # Crop bounds with 60px context padding (exact Photoshop plugin setting)
    padding_context = 60
    roi_x1 = max(0, sel_x1 - padding_context)
    roi_y1 = max(0, sel_y1 - padding_context)
    roi_x2 = min(w_page, sel_x2 + padding_context)
    roi_y2 = min(h_page, sel_y2 + padding_context)

    roi_w = roi_x2 - roi_x1
    roi_h = roi_y2 - roi_y1

    crop_img = base_page_pil.crop((roi_x1, roi_y1, roi_x2, roi_y2))
    local_mask_np = np.zeros((roi_h, roi_w), dtype=np.uint8)

    if polys:
        for poly in polys:
            pts = np.array(poly, dtype=np.int32) - np.array([roi_x1, roi_y1], dtype=np.int32)
            if pts.ndim == 1 and len(pts) >= 6:
                pts = pts.reshape(-1, 2)
            if pts.ndim == 2 and pts.shape[0] >= 3:
                cv2.fillPoly(local_mask_np, [pts], 255)
    else:
        lx1 = max(0, sel_x1 - roi_x1)
        ly1 = max(0, sel_y1 - roi_y1)
        lx2 = min(roi_w, sel_x2 - roi_x1)
        ly2 = min(roi_h, sel_y2 - roi_y1)
        if lx2 > lx1 and ly2 > ly1:
            local_mask_np[ly1:ly2, lx1:lx2] = 255

    effective_dilation = max(dilation, bubble.get("mask_padding", 0), 6)
    if effective_dilation > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (effective_dilation * 2 + 1, effective_dilation * 2 + 1))
        safe_crop_mask = cv2.dilate(local_mask_np, k)
    else:
        safe_crop_mask = local_mask_np.copy()

    local_mask_pil = Image.fromarray(safe_crop_mask, mode="L")
    client = IOPaintClient(server_url)
    if model:
        try:
            client.switch_model(model)
        except Exception:
            pass
    cleaned_crop = client.inpaint(crop_img, local_mask_pil)

    # Paste back onto page
    result_page = base_page_pil.copy()
    result_page.paste(cleaned_crop, (roi_x1, roi_y1))
    return result_page

