"""
Ngrok & Mobile Bridge Server Manager for SmartCleaner-AI
Handles dynamic user ngrok authtokens, custom or random domains,
LAN/Wi-Fi IP detection, tunnel lifecycle, and QR code generation.
"""

import os
import sys
import json
import time
import socket
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Tuple, Any

import requests
from loguru import logger

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "gui_config.json"


TOOLS_DIR = BASE_DIR / "tools"
TOOLS_NGROK_DIR = TOOLS_DIR / "ngrok"
NGROK_ZIP_URL = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"


def get_ngrok_path() -> Optional[str]:
    """Finds the ngrok executable on local tools dir, system PATH, or known default Windows locations."""
    # 1. Check local project tools directory (priority for standalone/portable distribution)
    local_candidates = [
        TOOLS_NGROK_DIR / "ngrok.exe",
        TOOLS_DIR / "ngrok.exe",
        BASE_DIR / "ngrok.exe"
    ]
    for p in local_candidates:
        if p.is_file():
            return str(p)

    # 2. Check system PATH
    found = shutil.which("ngrok")
    if found:
        return found

    # 3. Check WinGet / AppData paths
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        winget_path = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_path.exists():
            for p in winget_path.glob("Ngrok*/**/ngrok.exe"):
                if p.is_file():
                    return str(p)

    # 4. Check Program Files or standard locations
    for standard_dir in [
        r"C:\Program Files\ngrok\ngrok.exe",
        r"C:\Program Files (x86)\ngrok\ngrok.exe",
        r"C:\ngrok\ngrok.exe",
    ]:
        if os.path.exists(standard_dir):
            return standard_dir

    return None


def download_and_install_ngrok(progress_callback=None) -> Tuple[bool, str]:
    """
    Automatically downloads the official ngrok Windows 64-bit binary,
    extracts it to tools/ngrok/ngrok.exe, and verifies it.
    """
    import zipfile
    TOOLS_NGROK_DIR.mkdir(parents=True, exist_ok=True)
    target_exe = TOOLS_NGROK_DIR / "ngrok.exe"

    if target_exe.is_file() and target_exe.stat().st_size > 1_000_000:
        return True, str(target_exe)

    temp_zip = TOOLS_NGROK_DIR / "ngrok_temp.zip"

    try:
        if progress_callback:
            progress_callback("جاري تنزيل أداة Ngrok الرسمية لنظام ويندوز...", 0.1)

        logger.info(f"Downloading ngrok binary from {NGROK_ZIP_URL}...")
        resp = requests.get(NGROK_ZIP_URL, stream=True, timeout=30)
        resp.raise_for_status()

        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0

        with open(temp_zip, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0 and progress_callback:
                        pct = min(0.85, 0.1 + (downloaded / total_size) * 0.75)
                        progress_callback(f"جاري التنزيل: {downloaded // 1024} KB / {total_size // 1024} KB", pct)

        if progress_callback:
            progress_callback("جاري فك ضغط أداة Ngrok وتثبيتها...", 0.9)

        with zipfile.ZipFile(temp_zip, "r") as z:
            z.extract("ngrok.exe", TOOLS_NGROK_DIR)

        # Cleanup temp zip
        if temp_zip.exists():
            temp_zip.unlink(missing_ok=True)

        if target_exe.is_file():
            if progress_callback:
                progress_callback("تم تثبيت أداة Ngrok بنجاح!", 1.0)
            logger.info(f"✅ Ngrok successfully installed at: {target_exe}")
            return True, str(target_exe)
        else:
            return False, "فشل استخراج ngrok.exe من الحزمة المضغوطة."

    except Exception as e:
        logger.error(f"Failed to download/install ngrok: {e}")
        if temp_zip.exists():
            temp_zip.unlink(missing_ok=True)
        return False, f"فشل تحميل أداة Ngrok: {str(e)}"


def get_local_ip() -> str:
    """Returns local LAN / Wi-Fi IP address (e.g. 192.168.1.x)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Doesn't have to be reachable; just triggers route selection
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def load_server_config() -> Dict[str, Any]:
    """Loads server and ngrok configuration from gui_config.json."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {CONFIG_FILE}: {e}")
        return {}


def save_server_config(updates: Dict[str, Any]) -> None:
    """Updates server and ngrok configuration in gui_config.json."""
    current = load_server_config()
    current.update(updates)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving {CONFIG_FILE}: {e}")


def configure_ngrok_authtoken(token: str) -> Tuple[bool, str]:
    """Configures user's authtoken via 'ngrok config add-authtoken <token>'."""
    token = (token or "").strip()
    if not token:
        return False, "التوكن فارغ"

    ngrok_bin = get_ngrok_path()
    if not ngrok_bin:
        return False, "لم يتم العثور على برنامج ngrok.exe على جهازك."

    try:
        cmd = [ngrok_bin, "config", "add-authtoken", token]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        if res.returncode == 0:
            # Also save to config file
            save_server_config({"ngrok_authtoken": token})
            return True, "تم حفظ سريال Ngrok بنجاح!"
        else:
            err = res.stderr or res.stdout
            return False, f"فشل ضبط التوكن: {err.strip()}"
    except Exception as e:
        return False, f"خطأ أثناء ضبط التوكن: {str(e)}"


def is_port_in_use(port: int = 8000, timeout: float = 0.03) -> bool:
    """Checks if the given port has an active listening socket."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def get_active_ngrok_url() -> Optional[str]:
    """
    Queries ngrok's local inspection endpoint (http://127.0.0.1:4040/api/tunnels)
    to dynamically retrieve the active public URL.
    """
    if not is_port_in_use(4040, timeout=0.03):
        return None
    try:
        resp = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=1)
        if resp.status_code == 200:
            data = resp.json()
            tunnels = data.get("tunnels", [])
            for t in tunnels:
                proto = t.get("proto")
                public_url = t.get("public_url")
                if proto == "https" and public_url:
                    return public_url
            # Fallback to first tunnel if https not specifically labeled
            if tunnels and tunnels[0].get("public_url"):
                return tunnels[0]["public_url"]
    except Exception:
        pass
    return None


def is_server_online(port: int = 8000) -> bool:
    """Pings the SmartCleaner server health endpoint."""
    if not is_port_in_use(port, timeout=0.03):
        return False
    try:
        r = requests.get(
            f"http://127.0.0.1:{port}/api/health",
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=1
        )
        return r.status_code == 200
    except Exception:
        return False


def start_ngrok_tunnel(port: int = 8000, domain: Optional[str] = None, authtoken: Optional[str] = None) -> Tuple[bool, str]:
    """
    Launches an ngrok tunnel pointing to port 8000.
    Returns (success, public_url_or_error_message).
    """
    # 1. Check if already active
    active = get_active_ngrok_url()
    if active:
        return True, active

    ngrok_bin = get_ngrok_path()
    if not ngrok_bin:
        return False, "لم يتم العثور على ngrok.exe. يرجى تثبيته أولاً."

    # 2. Configure authtoken if provided
    config = load_server_config()
    token_to_use = authtoken or config.get("ngrok_authtoken", "")
    if token_to_use and token_to_use.strip():
        configure_ngrok_authtoken(token_to_use.strip())

    # 3. Build command
    domain_to_use = (domain or config.get("ngrok_domain", "")).strip()
    cmd = [ngrok_bin, "http", str(port)]
    if domain_to_use:
        # If user included full url https://..., strip it for the --url arg
        clean_domain = domain_to_use.replace("https://", "").replace("http://", "").rstrip("/")
        cmd.extend(["--url", clean_domain])

    try:
        # Kill lingering ngrok first
        stop_ngrok()
        time.sleep(0.5)

        # Launch detached background process
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )

        # Poll for public URL up to 8 seconds
        for _ in range(16):
            time.sleep(0.5)
            url = get_active_ngrok_url()
            if url:
                save_server_config({
                    "remote_server_url": url,
                    "ngrok_domain": domain_to_use
                })
                return True, url

        return False, "تم إطلاق نفق Ngrok لكن لم نتمكن من الحصول على الرابط خلال 8 ثوان. تأكد من صحة التوكن والنطاق."
    except Exception as e:
        return False, f"خطأ أثناء تشغيل Ngrok: {str(e)}"


def ensure_server_running(port: int = 8000) -> bool:
    """Checks if server_api.py is running on port; if not, launches it in the background."""
    if is_server_online(port):
        return True

    server_script = BASE_DIR / "server_api.py"
    if not server_script.is_file():
        return False

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    cmd = [sys.executable, str(server_script)]
    try:
        subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )
    except Exception as e:
        logger.error(f"Failed to launch server: {e}")
        return False

    # Wait up to 6 seconds for server to come online
    for _ in range(12):
        time.sleep(0.5)
        if is_server_online(port):
            return True
    return False


def setup_and_activate_ngrok_service(
    authtoken: str,
    domain: Optional[str] = None,
    port: int = 8000,
    progress_callback=None
) -> Tuple[bool, str, str]:
    """
    Complete 1-click installer and service activator:
    1. Downloads & installs ngrok.exe if not present.
    2. Configures the authtoken.
    3. Ensures the server is running on port 8000.
    4. Launches the ngrok tunnel.
    5. Returns (success, public_url, message).
    """
    authtoken = (authtoken or "").strip()
    if not authtoken:
        return False, "", "يرجى إدخال رمز/سيريال Ngrok Auth Token أولاً."

    # 1. Ensure ngrok binary is installed
    ngrok_bin = get_ngrok_path()
    if not ngrok_bin:
        if progress_callback:
            progress_callback("جاري فحص وتثبيت أداة Ngrok...", 0.05)
        ok, res = download_and_install_ngrok(progress_callback)
        if not ok:
            return False, "", f"فشل تثبيت أداة Ngrok: {res}"
        ngrok_bin = res

    # 2. Configure authtoken
    if progress_callback:
        progress_callback("جاري ضبط وتفعيل سيريال Ngrok...", 0.6)
    ok, msg = configure_ngrok_authtoken(authtoken)
    if not ok:
        return False, "", f"فشل ضبط السيريال: {msg}"

    # 3. Ensure server is running
    if progress_callback:
        progress_callback("جاري التحقق من تشغيل خادم الموبايل...", 0.75)
    if not ensure_server_running(port):
        return False, "", "تعذر إطلاق خادم SmartCleaner-AI على المنفذ 8000."

    # 4. Start ngrok tunnel
    if progress_callback:
        progress_callback("جاري فتح نفق Ngrok العالمي...", 0.85)
    ok, url_or_err = start_ngrok_tunnel(port=port, domain=domain, authtoken=authtoken)
    if not ok:
        return False, "", f"فشل تشغيل نفق Ngrok: {url_or_err}"

    if progress_callback:
        progress_callback("تم الاتصال وتفعيل خدمة النفق بنجاح!", 1.0)

    return True, url_or_err, "تم تثبيت خدمة Ngrok وتشغيل خادم الموبايل بنجاح! 🚀"


def stop_ngrok() -> None:
    """Kills any running ngrok.exe processes."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "ngrok.exe"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception:
            pass


def stop_server_and_ngrok(port: int = 8000) -> None:
    """Terminates server running on port and kills ngrok."""
    stop_ngrok()
    if os.name == "nt":
        try:
            # Find PID listening on port and kill it
            cmd = f'for /f "tokens=5" %a in (\'netstat -aon ^| findstr :{port}\') do taskkill /F /PID %a'
            subprocess.run(
                ["cmd.exe", "/c", cmd],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception:
            pass


def generate_qr_code_image(data_text: str, size: int = 240):
    """
    Generates a PIL Image containing a QR code for the specified text/URL.
    """
    import qrcode
    from PIL import Image

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(data_text)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#0284c7", back_color="#0f172a")
    return img.resize((size, size), Image.Resampling.LANCZOS)
