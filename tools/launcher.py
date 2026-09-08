"""
SmartCleaner-AI - Universal Bootstrapper & Environment Verifier
Guarantees reliable execution on all Windows systems:
1. Verifies Python version.
2. Checks all required packages (PySide6, cv2, torch, ultralytics, etc.).
3. Automatically installs missing dependencies from requirements.txt if needed.
4. Catches all launch exceptions and displays graphical + console diagnostic messages.
"""

import sys
import os
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
os.chdir(str(BASE_DIR))

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def show_native_alert(title: str, message: str, is_error: bool = False):
    """Displays a native Windows graphical alert dialog using standard ctypes."""
    try:
        import ctypes
        icon_flag = 0x10 if is_error else 0x40  # MB_ICONERROR or MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(0, message, title, icon_flag)
    except Exception:
        pass


REQUIRED_MODULES = [
    ("PySide6", "PySide6"),
    ("cv2", "opencv-python"),
    ("torch", "torch"),
    ("torchvision", "torchvision"),
    ("ultralytics", "ultralytics"),
    ("PIL", "pillow"),
    ("numpy", "numpy"),
    ("requests", "requests"),
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("loguru", "loguru"),
    ("qrcode", "qrcode")
]


def check_and_install_dependencies():
    missing = []
    for mod_name, pkg_name in REQUIRED_MODULES:
        try:
            __import__(mod_name)
        except ImportError:
            missing.append(pkg_name)

    if not missing:
        return True

    print("=" * 65)
    print("  ⚡ SmartCleaner-AI: First-time Dependency Setup")
    print("  جاري تهيئة وتثبيت مكتبات الذكاء الاصطناعي لأول مرة...")
    print("=" * 65)
    print(f"[*] Missing modules detected: {', '.join(missing)}")
    print("[*] Installing requirements from requirements.txt via pip...")
    print("    (This runs only once and takes 1-2 minutes. Please wait...)\n")

    req_file = BASE_DIR / "requirements.txt"
    if not req_file.exists():
        print(f"[!] Error: requirements.txt not found at {req_file}")
        return False

    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "pip"]
    try:
        subprocess.run(cmd, check=False)
    except Exception:
        pass

    install_cmd = [sys.executable, "-m", "pip", "install", "-r", str(req_file)]
    res = subprocess.run(install_cmd)

    if res.returncode == 0:
        print("\n" + "=" * 65)
        print("  ✅ All dependencies installed successfully! Launching app...")
        print("=" * 65 + "\n")
        return True
    else:
        error_msg = (
            "فشل تثبيت بعض المكتبات المطلوبة تلقائياً.\n"
            "يرجى التأكد من اتصالك بالإنترنت ثم إعادة تشغيل البرنامج.\n\n"
            f"Command exit code: {res.returncode}"
        )
        print("\n[!] " + error_msg)
        show_native_alert("SmartCleaner-AI Setup Error", error_msg, is_error=True)
        return False


def main():
    print("========================================================")
    print("  🚀 Starting SmartCleaner-AI Studio...")
    print(f"  Python executable: {sys.executable}")
    print(f"  Python version: {sys.version.split()[0]}")
    print("========================================================\n")

    # 1. Check Python version
    if sys.version_info < (3, 9):
        err = f"Python version is too old: {sys.version}. Please install Python 3.10+."
        print(f"[!] {err}")
        show_native_alert("Python Version Error", err, is_error=True)
        return 1

    # 2. Check and install dependencies if missing
    if not check_and_install_dependencies():
        input("\nPress Enter to exit...")
        return 1

    # 3. Launch main GUI
    try:
        import gui_cleaner
        gui_cleaner.main()
        return 0
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print("\n" + "=" * 65)
        print("  [CRITICAL ERROR] Failed to run SmartCleaner-AI:")
        print("=" * 65)
        print(tb)
        print("=" * 65)

        err_msg = f"حدث خطأ أثناء تشغيل البرنامج:\n\n{str(e)}\n\nيرجى مراجعة تفاصيل الخطأ في نافذة التيرمنال."
        show_native_alert("SmartCleaner-AI Launch Error", err_msg, is_error=True)
        input("\nPress Enter to exit...")
        return 1


if __name__ == "__main__":
    sys.exit(main())
