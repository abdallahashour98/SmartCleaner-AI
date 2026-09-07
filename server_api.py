"""
SmartCleaner-AI Backend Bridge API Server
Enables remote mobile access (via Ngrok/LAN), batch manga cleaning & inpainting,
IOPaint model management, and remote PC GUI triggering.

Usage:
    py -3.10 server_api.py
    py -3.10 server_api.py --with-ngrok
    py -3.10 server_api.py --port 8000
"""

import os
import sys
import io
import json
import time
import uuid
import shutil
import zipfile
import subprocess
import argparse
from pathlib import Path
from typing import List, Optional, Dict, Any

import cv2
import numpy as np
from PIL import Image
import requests

from fastapi import FastAPI, Request, File, UploadFile, Form, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import uvicorn
from loguru import logger

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from fast_cleaner import (
    detect_bubbles_for_cleaning,
    clean_page,
    smart_adaptive_inpaint_page,
    inpaint_manga_page,
    inpaint_single_bubble,
    classify_bubble_background,
    read_image_unicode,
    write_image_unicode
)
from pcleaner.iopaint_client import (
    IOPaintClient,
    clean_flat_bubble_locally
)
from pcleaner.ngrok_manager import (
    get_local_ip,
    get_active_ngrok_url,
    start_ngrok_tunnel,
    stop_ngrok,
    stop_server_and_ngrok,
    load_server_config,
    save_server_config
)

# Constants & Paths
BATCHES_DIR = BASE_DIR / "data" / "server_batches"
BATCHES_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = BASE_DIR / "gui_config.json"

ACTIVE_BATCH_PROGRESS: Dict[str, dict] = {}


def set_progress(
    batch_id: str,
    percent: float,
    step: str,
    detail: str = "",
    current_page: int = 0,
    total_pages: int = 0,
    current_image: str = "",
    phase: str = "init"
):
    ACTIVE_BATCH_PROGRESS[batch_id] = {
        "batch_id": batch_id,
        "percent": round(min(1.0, max(0.0, percent)), 2),
        "step": step,
        "detail": detail,
        "current_page": current_page,
        "total_pages": total_pages,
        "current_image": current_image,
        "phase": phase,
        "timestamp": time.time()
    }


IOPAINT_BAT_PATH = r"G:\iopaint\new iopaint\Start_IOPaint.bat"
DEFAULT_IOPAINT_URL = os.environ.get("IOPAINT_URL", "http://127.0.0.1:8080")

# In-memory batch registry
ACTIVE_BATCHES: Dict[str, Dict[str, Any]] = {}

app = FastAPI(
    title="SmartCleaner-AI Bridge API",
    version="1.0.0",
    description="Remote API Server for SmartCleaner-AI Manga Inpainting & Speech Bubble Cleaner"
)

# Enable CORS for mobile & web apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_pc_config() -> dict:
    """Reads gui_config.json from workspace."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading gui_config.json: {e}")
    return {}


def is_iopaint_running(iopaint_url: str = DEFAULT_IOPAINT_URL) -> tuple[bool, str]:
    """Checks if Inpainting server is responding."""
    target_url = iopaint_url
    if (":8080" in target_url or os.name != "nt") and ":8088" not in target_url:
        try:
            r88 = requests.get("http://127.0.0.1:8088/api/v1/model", timeout=2)
            if r88.status_code == 200:
                target_url = "http://127.0.0.1:8088"
        except Exception:
            pass

    client = IOPaintClient(target_url)
    is_up, model = client.check_connection()
    if not is_up and ":8088" not in target_url:
        client_8088 = IOPaintClient("http://127.0.0.1:8088")
        is_up88, model88 = client_8088.check_connection()
        if is_up88:
            return True, model88
    return is_up, model


def start_iopaint_service(bat_path: str = IOPAINT_BAT_PATH) -> bool:
    """Launches Inpainting service on Windows (.bat) or Linux."""
    if os.name == "nt":
        # Check custom path from config first
        config = load_pc_config()
        configured_path = config.get("iopaint_launcher_path", "")
        path_to_use = configured_path if (configured_path and os.path.exists(configured_path)) else bat_path

        if not os.path.exists(path_to_use):
            logger.error(f"IOPaint batch file not found at: {path_to_use}")
            return False
        bat_dir = os.path.dirname(path_to_use)
        try:
            subprocess.Popen(f'cmd.exe /c "{path_to_use}"', cwd=bat_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)
            return True
        except Exception as e:
            logger.error(f"Failed to launch IOPaint process: {e}")
            return False
    else:
        # Linux / Google Colab
        lite_server = BASE_DIR / "pcleaner" / "iopaint_server_lite.py"
        if lite_server.exists():
            try:
                subprocess.Popen(["python3", str(lite_server)])
                return True
            except Exception as e:
                logger.error(f"Failed to launch iopaint_server_lite: {e}")
                return False
        return False


def ensure_iopaint_online(iopaint_url: str = DEFAULT_IOPAINT_URL, timeout: int = 40) -> tuple[bool, str]:
    """Checks connection and starts IOPaint if offline, polling until ready."""
    is_up, model = is_iopaint_running(iopaint_url)
    if is_up:
        return True, model

    logger.info("IOPaint is not running. Attempting to start automatically...")
    started = start_iopaint_service()
    if not started:
        return False, "Failed to start IOPaint service."

    start_time = time.time()
    while time.time() - start_time < timeout:
        time.sleep(2)
        is_up, model = is_iopaint_running(iopaint_url)
        if is_up:
            logger.success(f"🎉 IOPaint successfully started and online ({model})!")
            return True, model

    return False, f"IOPaint started but timed out after {timeout} seconds."


def launch_pc_gui(project_path: Optional[str] = None):
    """Opens gui_cleaner.py on the PC screen."""
    python_exe = sys.executable
    script_path = str(BASE_DIR / "gui_cleaner.py")
    cmd = [python_exe, script_path]
    if project_path and os.path.exists(project_path):
        cmd.append(project_path)

    logger.info(f"🖥️ Launching PC GUI: {cmd}")
    try:
        subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        )
        return True
    except Exception as e:
        logger.error(f"Error launching PC GUI: {e}")
        return False


def close_pc_gui() -> bool:
    """Closes running gui_cleaner.py instances."""
    logger.info("🛑 Closing PC GUI...")
    if os.name == "nt":
        try:
            ps_cmd = 'Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like "*gui_cleaner.py*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }'
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)
            return True
        except Exception as e:
            logger.error(f"Error closing PC GUI: {e}")
            return False
    else:
        try:
            subprocess.run(["pkill", "-f", "gui_cleaner.py"])
            return True
        except Exception:
            return False


def stop_iopaint_service() -> bool:
    """Stops IOPaint inpainting server on port 8080 / 8088 to free up VRAM."""
    logger.info("🛑 Stopping IOPaint service...")
    if os.name == "nt":
        try:
            ps_cmd = '$ports = @(8080, 8088); Get-NetTCPConnection -LocalPort $ports -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }'
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True)
            return True
        except Exception as e:
            logger.error(f"Error stopping IOPaint: {e}")
            return False
    else:
        try:
            subprocess.run(["pkill", "-f", "iopaint"])
            return True
        except Exception:
            return False


# =========================================================================
# Server Management & Health Endpoints
# =========================================================================

@app.get("/")
@app.get("/api/health")
async def health_check():
    """Health check and status indicator for mobile app & desktop."""
    config = load_pc_config()
    iopaint_url = config.get("iopaint_server_url", DEFAULT_IOPAINT_URL)
    is_up, model = is_iopaint_running(iopaint_url)

    is_colab = bool(
        os.environ.get("COLAB_GPU") or
        Path("/content").exists() or
        "google.colab" in sys.modules
    )
    server_name = "SmartCleaner Colab GPU" if is_colab else "SmartCleaner-AI PC Server"
    server_type = "colab" if is_colab else "pc"

    active_ngrok = get_active_ngrok_url()

    return {
        "status": "online",
        "server": server_name,
        "server_type": server_type,
        "is_colab": is_colab,
        "version": "1.0.0",
        "timestamp": time.time(),
        "iopaint": {
            "online": is_up,
            "model": model,
            "url": iopaint_url,
            "bat_exists": os.path.exists(config.get("iopaint_launcher_path", IOPAINT_BAT_PATH))
        },
        "ngrok": {
            "online": bool(active_ngrok),
            "url": active_ngrok or ""
        },
        "local_ip": get_local_ip()
    }


@app.get("/api/server/info")
async def server_info():
    """Returns local and public connection information for easy mobile pairing."""
    local_ip = get_local_ip()
    ngrok_url = get_active_ngrok_url()
    return {
        "success": True,
        "local_ip": local_ip,
        "local_url": f"http://{local_ip}:8000",
        "public_url": ngrok_url or "",
        "has_ngrok": bool(ngrok_url)
    }


@app.get("/api/config")
async def get_pc_config():
    """Returns current configuration from gui_config.json."""
    config = load_pc_config()
    return {
        "success": True,
        "config": {
            "fast_mode": config.get("fast_mode", False),
            "snap_to_bubbles": config.get("snap_to_bubbles", True),
            "mask_padding": config.get("mask_padding", 0),
            "iopaint_enabled": config.get("iopaint_enabled", True),
            "iopaint_adaptive": config.get("iopaint_adaptive", True),
            "iopaint_server_url": config.get("iopaint_server_url", DEFAULT_IOPAINT_URL),
            "iopaint_model": config.get("iopaint_model", "anime-lama"),
            "iopaint_dilation": config.get("iopaint_dilation", 0),
            "ngrok_authtoken": config.get("ngrok_authtoken", ""),
            "ngrok_domain": config.get("ngrok_domain", ""),
            "remote_server_url": config.get("remote_server_url", ""),
            "last_output_dir": config.get("last_output_dir", "")
        }
    }


@app.post("/api/config")
async def update_pc_config(settings: Dict[str, Any]):
    """Saves updated settings to gui_config.json on PC."""
    try:
        config = load_pc_config()
        for k, v in settings.items():
            config[k] = v

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        logger.info(f"✅ Updated PC configuration: {settings}")
        return {
            "success": True,
            "message": "تم حفظ وتحديث الإعدادات بنجاح! 💾",
            "config": config
        }
    except Exception as e:
        logger.error(f"Failed to save PC config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to write config: {e}")


@app.post("/api/gui/launch")
@app.post("/api/trigger-gui")
async def api_launch_gui(project_path: Optional[str] = Form(None)):
    """Opens gui_cleaner.py on the PC desktop."""
    success = launch_pc_gui(project_path)
    return {
        "success": success,
        "message": "تم فتح برنامج SmartCleaner-AI على شاشة الكمبيوتر بنجاح! 🚀" if success else "تعذر فتح البرنامج على الكمبيوتر"
    }


@app.post("/api/gui/close")
async def api_close_gui():
    """Closes gui_cleaner.py on the PC."""
    success = close_pc_gui()
    return {
        "success": success,
        "message": "تم إغلاق برنامج SmartCleaner-AI على الكمبيوتر بنجاح! ❌" if success else "فشل إغلاق البرنامج"
    }


@app.post("/api/iopaint/start")
async def api_start_iopaint():
    """Starts IOPaint service."""
    success = start_iopaint_service()
    return {
        "success": success,
        "message": "تم إرسال أمر تشغيل خادم IOPaint على الكمبيوتر! 🎨" if success else "فشل تشغيل IOPaint"
    }


@app.post("/api/iopaint/stop")
async def api_stop_iopaint():
    """Stops IOPaint service to release GPU VRAM."""
    success = stop_iopaint_service()
    return {
        "success": success,
        "message": "تم إيقاف خادم IOPaint وتفريغ ذاكرة كارت الشاشة (VRAM) بنجاح! ⏹️" if success else "فشل إيقاف IOPaint"
    }


@app.post("/api/server/shutdown")
async def api_shutdown_server():
    """Gracefully shuts down the server and ngrok."""
    def _delayed_exit():
        time.sleep(1.0)
        stop_iopaint_service()
        stop_ngrok()
        logger.warning("🛑 Server shutdown executed.")
        os._exit(0)

    import threading
    threading.Thread(target=_delayed_exit, daemon=True).start()
    return {"success": True, "message": "تم إغلاق الخادم ونفق Ngrok بنجاح! 🛑"}


# =========================================================================
# Inpainting Proxy Endpoints (for direct client tool calls)
# =========================================================================

@app.get("/api/v1/model")
async def proxy_get_model():
    """Proxy model status from local inpainting engine."""
    target = "http://127.0.0.1:8088" if (os.name != "nt" or os.path.exists("/content")) else "http://127.0.0.1:8080"
    try:
        r = requests.get(f"{target}/api/v1/model", timeout=3)
        return r.json()
    except Exception:
        return {"name": "anime-lama", "model": "anime-lama", "status": "online"}


@app.post("/api/v1/model")
async def proxy_switch_model(request: Request):
    """Proxy switch model."""
    target = "http://127.0.0.1:8088" if (os.name != "nt" or os.path.exists("/content")) else "http://127.0.0.1:8080"
    try:
        body = await request.body()
        r = requests.post(f"{target}/api/v1/model", data=body, headers={"Content-Type": "application/json"}, timeout=5)
        return r.json()
    except Exception:
        return {"name": "anime-lama", "status": "switched"}


@app.post("/api/v1/inpaint")
async def proxy_inpaint(request: Request):
    """Proxies direct inpainting requests to the GPU inpainting engine."""
    target = "http://127.0.0.1:8088" if (os.name != "nt" or os.path.exists("/content")) else "http://127.0.0.1:8080"
    try:
        body = await request.body()
        resp = requests.post(
            f"{target}/api/v1/inpaint",
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=120
        )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "image/png")
        )
    except Exception as e:
        logger.error(f"Inpaint proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Batch Processing & Worker Core
# =========================================================================

def _run_batch_worker(
    batch_id: str,
    saved_image_paths: list,
    script_path: Optional[str],
    arabic_lines: list,
    api_key: str,
    fast_mode: bool,
    clean_images: bool,
    iopaint_model: str,
    iopaint_adaptive: bool,
    iopaint_dilation: int,
    snap_to_bubbles: bool,
    open_pc_gui: bool,
    chapter_url: Optional[str] = None
):
    """Background worker that runs full AI batch cleaning & detection."""
    try:
        config = load_pc_config()
        batch_dir = BATCHES_DIR / batch_id
        raw_images_dir = batch_dir / "raw_images"
        cleaned_images_dir = batch_dir / "cleaned_images"
        json_export_dir = batch_dir / "typer_json"

        # If chapter_url is given, download images asynchronously in worker
        if chapter_url and chapter_url.strip() and not saved_image_paths:
            clean_u = chapter_url.strip()
            logger.info(f"📥 [Worker] Downloading chapter from URL: {clean_u}")
            set_progress(
                batch_id, 0.02,
                "📥 جاري تنزيل ملف الفصل مباشرة من الرابط السحابي...",
                f"الرابط: {clean_u[:60]}...",
                current_page=0, total_pages=0, phase="download"
            )
            from pcleaner.archive_downloader import download_and_extract_chapter
            saved_image_paths = download_and_extract_chapter(clean_u, raw_images_dir)
            if not saved_image_paths:
                raise Exception("لم يتم العثور على صور صالحة داخل الرابط أو المجلد المحدد.")

            def natural_sort_key(s):
                import re
                return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', Path(s).name)]
            saved_image_paths.sort(key=natural_sort_key)

        total_pages = len(saved_image_paths)
        if total_pages == 0:
            raise Exception("لا توجد صور مانجا صالحة للمعالجة.")

        set_progress(
            batch_id, 0.06,
            "جاري تحضير الملفات وفحص النماذج...",
            f"عدد الصفحات: {total_pages}",
            current_page=0, total_pages=total_pages, phase="upload"
        )

        # On Linux / Google Colab, Inpainting always runs on port 8088
        if os.name != "nt" or os.path.exists("/content"):
            iopaint_url = "http://127.0.0.1:8088"
        else:
            iopaint_url = config.get("iopaint_server_url", DEFAULT_IOPAINT_URL)

        if clean_images:
            set_progress(
                batch_id, 0.10,
                "جاري التأكد من جاهزية محرك الذكاء الاصطناعي IOPaint...",
                f"فحص خادم التبييض ({iopaint_model})...",
                current_page=0, total_pages=total_pages, phase="cleaning"
            )
            logger.info(f"Image cleaning requested. Ensuring IOPaint server ({iopaint_url}) is running...")
            is_ready, iopaint_status_msg = ensure_iopaint_online(iopaint_url, timeout=45)
            if not is_ready:
                logger.warning(f"IOPaint startup issue: {iopaint_status_msg}. Inpainting might be skipped or fail.")

        # Bubble Detection & Cleaning per page using fast_cleaner.py
        logger.info(f"🚀 Processing batch {batch_id} ({total_pages} pages)...")
        page_results = {}
        page_cleaned_images = {}

        for idx, img_p in enumerate(saved_image_paths):
            cur_p_num = idx + 1
            img_name = Path(img_p).name
            base_pct = 0.12 + (idx / max(1, total_pages)) * 0.75

            set_progress(
                batch_id, base_pct + 0.02,
                f"🔍 كشف وتحديد فقاعات الكلام (صفحة {cur_p_num}/{total_pages})",
                f"فحص حدود النصوص في {img_name}...",
                current_page=cur_p_num, total_pages=total_pages, current_image=img_name, phase="detection"
            )

            logger.info(f"Detecting bubbles on page {cur_p_num}/{total_pages}: {img_name}")
            detected_bubbles = detect_bubbles_for_cleaning(
                image_path=img_p,
                mask_padding=config.get("mask_padding", 0),
                snap_to_bubbles=snap_to_bubbles
            )

            # Normalize bounds & geometry fields for mobile & desktop
            normalized_items = []
            for b_idx, it in enumerate(detected_bubbles):
                x = float(it.get("x", 0))
                y = float(it.get("y", 0))
                w = float(it.get("w", it.get("width", 0)))
                h = float(it.get("h", it.get("height", 0)))

                item_copy = dict(it)
                item_copy["bounds"] = [x, y, w, h]
                item_copy["x"] = x
                item_copy["y"] = y
                item_copy["width"] = w
                item_copy["height"] = h
                item_copy["w"] = w
                item_copy["h"] = h
                item_copy["id"] = b_idx + 1
                item_copy["reading_order"] = b_idx + 1
                item_copy["text"] = it.get("text", "")
                item_copy["assigned_translation"] = it.get("assigned_translation", "")
                item_copy["status"] = "detected"
                normalized_items.append(item_copy)

            page_results[img_p] = normalized_items

            # Clean / Inpaint page if cleaning requested
            if clean_images:
                set_progress(
                    batch_id, base_pct + 0.18,
                    f"🧹 تبييض وتنظيف صفحة {cur_p_num}/{total_pages} بالذكاء الاصطناعي",
                    f"معالجة {len(normalized_items)} فقاعة في {img_name}...",
                    current_page=cur_p_num, total_pages=total_pages, current_image=img_name, phase="cleaning"
                )
                try:
                    dest_clean_path = str(cleaned_images_dir / f"clean_{img_name}")

                    def inpaint_prog_cb(msg):
                        set_progress(
                            batch_id, base_pct + 0.22,
                            f"🧹 تبييض صفحة {cur_p_num}/{total_pages}",
                            msg,
                            current_page=cur_p_num, total_pages=total_pages, current_image=img_name, phase="cleaning"
                        )

                    if iopaint_adaptive:
                        cleaned_pil, _ = smart_adaptive_inpaint_page(
                            server_url=iopaint_url,
                            image_input=img_p,
                            bubbles=normalized_items,
                            deep_model=iopaint_model,
                            dilation=iopaint_dilation,
                            padding=config.get("mask_padding", 2),
                            progress_callback=inpaint_prog_cb
                        )
                        cleaned_pil.save(dest_clean_path)
                    else:
                        cleaned_pil = inpaint_manga_page(
                            server_url=iopaint_url,
                            image_input=img_p,
                            bubbles=normalized_items,
                            deep_model=iopaint_model,
                            dilation=iopaint_dilation,
                            padding=config.get("mask_padding", 2),
                            adaptive=False
                        )
                        cleaned_pil.save(dest_clean_path)

                    if os.path.exists(dest_clean_path):
                        page_cleaned_images[img_p] = dest_clean_path
                        for b in normalized_items:
                            b["status"] = "cleaned"
                        logger.info(f"✅ Cleaned image saved: {dest_clean_path}")
                except Exception as e:
                    logger.error(f"Inpainting error for {img_p}: {e}")

        # Optional translation matching if script provided
        if arabic_lines or script_path:
            try:
                from pcleaner.ai_translator import perform_ai_batch_semantic_match
                raw_script_str = ""
                if script_path and os.path.exists(script_path):
                    with open(script_path, "r", encoding="utf-8") as sf:
                        raw_script_str = sf.read().strip()
                if not raw_script_str and arabic_lines:
                    raw_script_str = "\n".join(arabic_lines)

                all_pages_bubbles_dict = {}
                for img_p, items in page_results.items():
                    stem = Path(img_p).stem
                    all_pages_bubbles_dict[stem] = {str(it.get("id", b_idx+1)): it.get("text", "") for b_idx, it in enumerate(items)}

                batch_mapping = perform_ai_batch_semantic_match(
                    all_pages_bubbles=all_pages_bubbles_dict,
                    arabic_raw_text=raw_script_str,
                    api_key=api_key
                )

                for img_p, items in page_results.items():
                    stem = Path(img_p).stem
                    page_matches = batch_mapping.get(stem, {})
                    for b_idx, it in enumerate(items):
                        b_id = str(it.get("id", b_idx+1))
                        matched_text = page_matches.get(b_id, "")
                        if matched_text:
                            it["assigned_translation"] = matched_text
                            it["translation"] = matched_text
            except Exception as tr_e:
                logger.warning(f"Translation matching skipped or failed: {tr_e}")

        # Generate TypeR JSON files for mobile & desktop
        set_progress(
            batch_id, 0.94,
            "💾 حفظ وتوليد ملفات المشروع وحزم التنزيل",
            "تنسيق الإحداثيات وتجهيز ملفات التحميل...",
            current_page=total_pages, total_pages=total_pages, phase="packaging"
        )
        for img_p, items in page_results.items():
            base_name = Path(img_p).stem
            json_path = json_export_dir / f"{base_name}.json"
            typer_data = []
            for it in items:
                bounds = it.get("bounds", [0, 0, 0, 0])
                ar_text = it.get("assigned_translation") or it.get("text", "")
                typer_data.append({
                    "x": int(bounds[0]),
                    "y": int(bounds[1]),
                    "w": int(bounds[2]),
                    "h": int(bounds[3]),
                    "text": ar_text,
                    "reading_order": it.get("reading_order", 1)
                })
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(typer_data, f, ensure_ascii=False, indent=2)

        # Save project state in both .cln (SmartCleaner) and .ftr (FastTypeR mobile compatibility)
        project_data = {
            "batch_id": batch_id,
            "page_results": page_results,
            "cleaned_pages": page_cleaned_images,
            "output_dir": str(cleaned_images_dir),
            "iopaint_url": iopaint_url,
            "iopaint_model": iopaint_model,
            "timestamp": time.time()
        }
        for ext in ("project.cln", "project.ftr"):
            with open(batch_dir / ext, "w", encoding="utf-8") as f:
                json.dump(project_data, f, ensure_ascii=False, indent=2)

        # Create Zip Archives
        json_zip_path = batch_dir / "typer_jsons.zip"
        with zipfile.ZipFile(json_zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for jf in json_export_dir.glob("*.json"):
                z.write(jf, arcname=jf.name)

        if page_cleaned_images:
            clean_zip_path = batch_dir / "cleaned_images.zip"
            with zipfile.ZipFile(clean_zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                for _, cp in page_cleaned_images.items():
                    if os.path.exists(cp):
                        z.write(cp, arcname=Path(cp).name)

        # Launch PC GUI if requested by mobile client
        if open_pc_gui:
            launch_pc_gui(str(batch_dir / "project.cln"))

        ACTIVE_BATCHES[batch_id] = {
            "project_data": project_data,
            "dir": str(batch_dir)
        }

        # Format response
        formatted_pages = []
        for img_p in saved_image_paths:
            items = page_results.get(img_p, [])
            img_name = Path(img_p).name
            clean_p = page_cleaned_images.get(img_p)
            clean_name = Path(clean_p).name if clean_p else None

            im_w, im_h = 1000, 1500
            try:
                with Image.open(img_p) as im_dim:
                    im_w, im_h = im_dim.size
            except Exception:
                pass

            formatted_pages.append({
                "image_path": img_p,
                "image_name": img_name,
                "image_url": f"/api/files/{batch_id}/raw_images/{img_name}",
                "cleaned_url": f"/api/files/{batch_id}/cleaned_images/{clean_name}" if clean_name else None,
                "bubbles_count": len(items),
                "width": im_w,
                "height": im_h,
                "bubbles": items
            })

        final_result = {
            "success": True,
            "batch_id": batch_id,
            "pages_count": len(formatted_pages),
            "pages": formatted_pages,
            "downloads": {
                "cleaned_zip": f"/api/batch/{batch_id}/download-cleaned" if page_cleaned_images else None,
                "json_zip": f"/api/batch/{batch_id}/download-json",
                "project_cln": f"/api/batch/{batch_id}/download-project"
            }
        }

        ACTIVE_BATCH_PROGRESS[batch_id] = {
            "batch_id": batch_id,
            "percent": 1.0,
            "step": "🎉 اكتمل التبييض والمعالجة بنجاح!",
            "detail": "جاهز للمعاينة والتنزيل...",
            "current_page": total_pages,
            "total_pages": total_pages,
            "phase": "done",
            "timestamp": time.time(),
            "result": final_result
        }

        try:
            result_json_path = batch_dir / "result.json"
            with open(result_json_path, "w", encoding="utf-8") as rf:
                json.dump(final_result, rf, ensure_ascii=False, indent=2)
        except Exception:
            pass

        logger.success(f"🎉 Batch {batch_id} fully cleaned and ready!")

    except Exception as exc:
        logger.error(f"❌ Error in batch worker {batch_id}: {exc}")
        ACTIVE_BATCH_PROGRESS[batch_id] = {
            "batch_id": batch_id,
            "percent": 1.0,
            "step": "❌ حدث خطأ أثناء المعالجة",
            "detail": str(exc),
            "phase": "error",
            "error": str(exc),
            "timestamp": time.time()
        }


@app.post("/api/process")
async def process_batch(request: Request):
    """
    Main processing endpoint:
    Starts batch cleaning in background and returns batch_id immediately.
    Client polls /api/progress/{batch_id} until completed.
    """
    try:
        form = await request.form()
    except Exception as fe:
        logger.error(f"Failed to parse multipart form data: {fe}")
        raise HTTPException(status_code=400, detail=f"Failed to parse form data: {fe}")

    raw_images = form.getlist("images")
    if not raw_images:
        img_single = form.get("images")
        if img_single and hasattr(img_single, "filename"):
            raw_images = [img_single]
        else:
            raw_images = form.getlist("files") or form.getlist("file")

    script_file = form.get("script_file")
    script_text = form.get("script_text")
    chapter_url = form.get("chapter_url")
    gemini_api_key = form.get("gemini_api_key")

    def parse_bool(val, default=False):
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() in ("true", "1", "yes")

    fast_mode = parse_bool(form.get("fast_mode"), False)
    clean_images = parse_bool(form.get("clean_images"), True)
    iopaint_model = str(form.get("iopaint_model") or "anime-lama")
    iopaint_adaptive = parse_bool(form.get("iopaint_adaptive"), True)
    try:
        iopaint_dilation = int(form.get("iopaint_dilation") or 0)
    except Exception:
        iopaint_dilation = 0
    snap_to_bubbles = parse_bool(form.get("snap_to_bubbles"), True)
    open_pc_gui = parse_bool(form.get("open_pc_gui"), False)

    has_url = bool(chapter_url and str(chapter_url).strip())
    if not raw_images and not has_url:
        raise HTTPException(status_code=400, detail="No images or chapter URL provided.")

    config = load_pc_config()
    api_key = (gemini_api_key or config.get("api_key") or "").strip()

    batch_id = f"batch_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    batch_dir = BATCHES_DIR / batch_id
    raw_images_dir = batch_dir / "raw_images"
    cleaned_images_dir = batch_dir / "cleaned_images"
    json_export_dir = batch_dir / "typer_json"

    raw_images_dir.mkdir(parents=True, exist_ok=True)
    cleaned_images_dir.mkdir(parents=True, exist_ok=True)
    json_export_dir.mkdir(parents=True, exist_ok=True)

    saved_image_paths = []
    from pcleaner.archive_downloader import extract_archive_images

    # Save uploaded images
    if raw_images:
        for upload in raw_images:
            if hasattr(upload, "filename") and upload.filename and upload.filename != "dummy.txt":
                filename = Path(upload.filename).name
                dest = raw_images_dir / filename
                with open(dest, "wb") as f:
                    content = await upload.read()
                    f.write(content)

                if dest.suffix.lower() in (".zip", ".rar", ".cbz", ".7z", ".cbr", ".tar", ".gz"):
                    extracted = extract_archive_images(dest, raw_images_dir)
                    saved_image_paths.extend(extracted)
                    try:
                        dest.unlink()
                    except Exception:
                        pass
                else:
                    saved_image_paths.append(str(dest))

        def natural_sort_key(s):
            import re
            return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', Path(s).name)]
        saved_image_paths.sort(key=natural_sort_key)

    script_path = None
    arabic_lines = []
    if script_file and hasattr(script_file, "filename") and script_file.filename and script_file.filename != "dummy.txt":
        dest_script = batch_dir / "script.txt"
        script_content = await script_file.read()
        with open(dest_script, "wb") as f:
            f.write(script_content)
        script_path = str(dest_script)
        text_str = script_content.decode("utf-8", errors="replace")
        arabic_lines = [l.strip() for l in text_str.splitlines() if l.strip()]
    elif script_text:
        dest_script = batch_dir / "script.txt"
        with open(dest_script, "w", encoding="utf-8") as f:
            f.write(str(script_text))
        script_path = str(dest_script)
        arabic_lines = [l.strip() for l in str(script_text).splitlines() if l.strip()]

    import threading
    worker_thread = threading.Thread(
        target=_run_batch_worker,
        kwargs={
            "batch_id": batch_id,
            "saved_image_paths": saved_image_paths,
            "script_path": script_path,
            "arabic_lines": arabic_lines,
            "api_key": api_key,
            "fast_mode": fast_mode,
            "clean_images": clean_images,
            "iopaint_model": iopaint_model,
            "iopaint_adaptive": iopaint_adaptive,
            "iopaint_dilation": iopaint_dilation,
            "snap_to_bubbles": snap_to_bubbles,
            "open_pc_gui": open_pc_gui,
            "chapter_url": chapter_url
        },
        daemon=True
    )
    worker_thread.start()

    set_progress(
        batch_id, 0.01,
        "تم استلام الحزمة بنجاح...",
        "جاري إطلاق المعالجة الخلفية...",
        current_page=0, total_pages=len(saved_image_paths), phase="init"
    )

    return {
        "success": True,
        "status": "processing",
        "batch_id": batch_id,
        "total_images": len(saved_image_paths),
        "message": f"تم استلام {len(saved_image_paths)} صفحة. جاري التبييض في الخلفية."
    }


@app.get("/api/progress/{batch_id}")
async def get_batch_progress(batch_id: str):
    """Real-time progress polling endpoint for mobile & desktop."""
    prog = ACTIVE_BATCH_PROGRESS.get(batch_id)
    if prog:
        return prog

    batch_dir = BATCHES_DIR / batch_id
    res_path = batch_dir / "result.json"
    if res_path.exists():
        try:
            with open(res_path, "r", encoding="utf-8") as rf:
                res_data = json.load(rf)
            return {
                "batch_id": batch_id,
                "percent": 1.0,
                "step": "اكتملت المعالجة سابقاً",
                "detail": "النتائج متوفرة",
                "phase": "done",
                "result": res_data
            }
        except Exception:
            pass

    raise HTTPException(status_code=404, detail="Batch progress not found")


@app.get("/api/batch/{batch_id}")
@app.get("/api/batch/{batch_id}/result")
async def get_batch_result(batch_id: str):
    """Returns the full batch result with pages and bubbles."""
    prog = ACTIVE_BATCH_PROGRESS.get(batch_id)
    if prog and prog.get("result"):
        return prog["result"]

    batch_dir = BATCHES_DIR / batch_id
    result_json_path = batch_dir / "result.json"
    if result_json_path.exists():
        with open(result_json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    raise HTTPException(status_code=404, detail="Batch result not ready or not found")


@app.post("/api/batch/{batch_id}/bubble-cleaning-action")
async def bubble_cleaning_action(
    batch_id: str,
    page_key: str = Form(...),
    bubble_index: int = Form(...),
    action: str = Form(...),  # "reclean_ai", "restore_original", "flat_white"
    dilation: int = Form(0)
):
    """
    Applies a granular cleaning action to a single bubble:
    - reclean_ai: Re-inpaints this single bubble using IOPaint AI.
    - restore_original: Copies the original raw crop back onto the cleaned page.
    - flat_white: Instantly paints flat white background for this bubble locally.
    """
    batch_dir = BATCHES_DIR / batch_id
    project_cln = batch_dir / "project.cln"
    project_ftr = batch_dir / "project.ftr"
    proj_path = project_cln if project_cln.exists() else project_ftr

    if not proj_path.exists():
        raise HTTPException(status_code=404, detail="Batch project state not found")

    with open(proj_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    page_results = data.get("page_results", {})
    if page_key not in page_results or not (0 <= bubble_index < len(page_results[page_key])):
        raise HTTPException(status_code=400, detail="Invalid bubble index or page key")

    bubble = page_results[page_key][bubble_index]
    config = load_pc_config()
    iopaint_url = config.get("iopaint_server_url", DEFAULT_IOPAINT_URL)
    iopaint_model = config.get("iopaint_model", "anime-lama")

    img_name = Path(page_key).name
    raw_img_path = batch_dir / "raw_images" / img_name
    cleaned_img_path = batch_dir / "cleaned_images" / f"clean_{img_name}"

    if not raw_img_path.exists():
        raise HTTPException(status_code=404, detail="Raw image file not found")

    if cleaned_img_path.exists():
        current_cleaned_pil = Image.open(str(cleaned_img_path)).convert("RGB")
    else:
        current_cleaned_pil = Image.open(str(raw_img_path)).convert("RGB")

    raw_pil = Image.open(str(raw_img_path)).convert("RGB")

    if action == "restore_original":
        bx = int(bubble.get("x", 0))
        by = int(bubble.get("y", 0))
        bw = int(bubble.get("width", bubble.get("w", 0)))
        bh = int(bubble.get("height", bubble.get("h", 0)))

        crop = raw_pil.crop((bx, by, bx + bw, by + bh))
        current_cleaned_pil.paste(crop, (bx, by))
        current_cleaned_pil.save(str(cleaned_img_path))
        bubble["status"] = "restored"
        msg = "تم استعادة الفقاعة للأصل بنجاح! ↩️"

    elif action == "flat_white":
        current_cleaned_pil = clean_flat_bubble_locally(current_cleaned_pil, bubble, padding=2)
        current_cleaned_pil.save(str(cleaned_img_path))
        bubble["status"] = "cleaned_flat"
        msg = "تم تبييض الفقاعة بالأبيض بنجاح! ⚡"

    elif action == "reclean_ai":
        current_cleaned_pil = inpaint_single_bubble(
            server_url=iopaint_url,
            image_input=current_cleaned_pil,
            bubble=bubble,
            model=iopaint_model,
            dilation=dilation,
            padding=2
        )
        current_cleaned_pil.save(str(cleaned_img_path))
        bubble["status"] = "cleaned_ai"
        msg = "تم إعادة تبييض الفقاعة بالذكاء الاصطناعي بنجاح! 🎨"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown cleaning action: {action}")

    # Save updated project files
    for p_out in (project_cln, project_ftr):
        with open(p_out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "message": msg,
        "action": action,
        "bubble_index": bubble_index,
        "status": bubble["status"],
        "cleaned_url": f"/api/files/{batch_id}/cleaned_images/clean_{img_name}?t={int(time.time()*1000)}"
    }


# =========================================================================
# File Serving & Download Endpoints
# =========================================================================

@app.get("/api/files/{batch_id}/{folder}/{filename}")
async def serve_batch_file(batch_id: str, folder: str, filename: str):
    """Serves raw images, cleaned images, or JSON files to the mobile client."""
    file_path = BATCHES_DIR / batch_id / folder / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    headers = {"ngrok-skip-browser-warning": "true"}
    return FileResponse(path=str(file_path), headers=headers)


@app.get("/api/batch/{batch_id}/download-cleaned")
async def download_cleaned_zip(batch_id: str, format: Optional[str] = "original"):
    """
    Downloads zip containing all cleaned manga images.
    format parameter supports: 'original', 'png', 'jpg', 'webp'
    """
    batch_dir = BATCHES_DIR / batch_id
    cleaned_dir = batch_dir / "cleaned_images"
    if not cleaned_dir.exists():
        raise HTTPException(status_code=404, detail="Cleaned images directory not found")

    clean_files = list(cleaned_dir.glob("clean_*"))
    if not clean_files:
        raise HTTPException(status_code=404, detail="No cleaned images found")

    fmt = (format or "original").lower().strip()

    if fmt in ("png", "jpg", "jpeg", "webp"):
        ext = "jpg" if fmt == "jpeg" else fmt
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            for img_p in clean_files:
                base_stem = img_p.stem
                out_name = f"{base_stem}.{ext}"
                with Image.open(str(img_p)) as im:
                    buf = io.BytesIO()
                    if ext == "png":
                        im.save(buf, format="PNG")
                    elif ext == "webp":
                        im.save(buf, format="WEBP", quality=95)
                    else:
                        im.convert("RGB").save(buf, format="JPEG", quality=95)
                    buf.seek(0)
                    z.writestr(out_name, buf.read())
        zip_buffer.seek(0)
        headers = {
            "ngrok-skip-browser-warning": "true",
            "Content-Disposition": f"attachment; filename={batch_id}_Cleaned_{fmt.upper()}.zip"
        }
        return Response(content=zip_buffer.getvalue(), media_type="application/zip", headers=headers)

    # Default original zip
    zip_path = batch_dir / "cleaned_images.zip"
    if not zip_path.exists():
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for cp in clean_files:
                z.write(cp, arcname=cp.name)

    headers = {"ngrok-skip-browser-warning": "true"}
    return FileResponse(path=str(zip_path), filename=f"{batch_id}_Cleaned_Pages.zip", headers=headers)


@app.get("/api/batch/{batch_id}/download-page/{filename}")
async def download_single_cleaned_page(batch_id: str, filename: str, format: Optional[str] = "original"):
    """Downloads a single cleaned page as a direct standalone uncompressed image."""
    batch_dir = BATCHES_DIR / batch_id
    cleaned_dir = batch_dir / "cleaned_images"

    target_file = cleaned_dir / f"clean_{filename}"
    if not target_file.exists():
        target_file = cleaned_dir / filename

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="Cleaned page not found")

    fmt = (format or "original").lower().strip()
    headers = {"ngrok-skip-browser-warning": "true"}

    if fmt in ("png", "jpg", "jpeg", "webp"):
        ext = "jpg" if fmt == "jpeg" else fmt
        media_type = f"image/{ext}" if ext != "jpg" else "image/jpeg"
        with Image.open(str(target_file)) as im:
            buf = io.BytesIO()
            if ext == "png":
                im.save(buf, format="PNG")
            elif ext == "webp":
                im.save(buf, format="WEBP", quality=95)
            else:
                im.convert("RGB").save(buf, format="JPEG", quality=95)
            buf.seek(0)
            headers["Content-Disposition"] = f'attachment; filename="{Path(filename).stem}.{ext}"'
            return Response(content=buf.getvalue(), media_type=media_type, headers=headers)

    return FileResponse(path=str(target_file), headers=headers)


@app.get("/api/batch/{batch_id}/download-json")
async def download_json_zip(batch_id: str):
    """Downloads zip containing all generated bubble JSON files."""
    zip_path = BATCHES_DIR / batch_id / "typer_jsons.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="JSON zip not found")

    headers = {"ngrok-skip-browser-warning": "true"}
    return FileResponse(path=str(zip_path), filename=f"{batch_id}_Bubbles_JSON.zip", headers=headers)


@app.get("/api/batch/{batch_id}/download-project")
async def download_project_file(batch_id: str):
    """Downloads project file."""
    batch_dir = BATCHES_DIR / batch_id
    cln = batch_dir / "project.cln"
    ftr = batch_dir / "project.ftr"
    target = cln if cln.exists() else ftr
    if not target.exists():
        raise HTTPException(status_code=404, detail="Project file not found")

    headers = {"ngrok-skip-browser-warning": "true"}
    return FileResponse(path=str(target), filename=f"{batch_id}.cln", headers=headers)


# =========================================================================
# Entry Point & CLI
# =========================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SmartCleaner-AI Mobile Bridge Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    parser.add_argument("--with-ngrok", action="store_true", help="Automatically launch Ngrok tunnel on startup")
    args = parser.parse_args()

    port = args.port
    cfg = load_server_config()

    # Automatically start ngrok if requested or configured
    should_start_ngrok = args.with_ngrok or cfg.get("server_auto_ngrok", False)
    ngrok_url = ""
    if should_start_ngrok:
        logger.info("🌐 Launching Ngrok tunnel...")
        ok, res = start_ngrok_tunnel(port=port)
        if ok:
            ngrok_url = res
            logger.success(f"🚀 Ngrok Tunnel is active: {ngrok_url}")
        else:
            logger.warning(f"⚠️ Could not start Ngrok automatically: {res}")
    else:
        active = get_active_ngrok_url()
        if active:
            ngrok_url = active

    local_ip = get_local_ip()

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    logger.info("==================================================================")
    logger.info("  SmartCleaner-AI Mobile Bridge Server is READY!")
    logger.info(f"  Local Wi-Fi (LAN): http://{local_ip}:{port}")
    if ngrok_url:
        logger.info(f"  Ngrok Public URL:  {ngrok_url}")
    else:
        logger.info("  Ngrok: Offline (Run with --with-ngrok or start from Desktop GUI)")
    logger.info("==================================================================")

    uvicorn.run(app, host=args.host, port=port)
