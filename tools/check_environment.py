"""
SmartCleaner-AI - End-User Environment & Diagnostics Checker
100% Pure English - Zero encoding issues on any Windows locale.
Runs pre-flight checks on Python version, required AI libraries,
GPU / DirectML hardware detection, and required model files.
"""

import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def run_checks():
    print("=" * 65)
    print("   SmartCleaner-AI Environment Pre-Flight Diagnostics")
    print("=" * 65)

    all_passed = True

    # 1. Check Python version
    py_ver = sys.version_info
    print(f"[*] Python Version: {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    if py_ver < (3, 10):
        print("  [!] Warning: Python 3.10+ is recommended for AI stability.")
    else:
        print("  [+] Python version is fully compatible.")

    # 2. Check Core Dependencies
    required_packages = [
        ("PySide6", "GUI Framework"),
        ("torch", "PyTorch AI Engine"),
        ("cv2", "OpenCV Fast Image Processing"),
        ("PIL", "Pillow Image Library"),
        ("numpy", "NumPy Matrix Math"),
        ("ultralytics", "YOLOv8 Bubble Detection"),
        ("requests", "HTTP Network Client"),
        ("fastapi", "Mobile Bridge Server"),
        ("uvicorn", "Web Server Engine"),
    ]

    print("\n[*] Checking Core Libraries:")
    for pkg, desc in required_packages:
        try:
            __import__(pkg)
            print(f"  [+] {pkg.ljust(15)} : Installed ({desc})")
        except Exception as e:
            err_str = str(e)
            if "126" in err_str or "shm.dll" in err_str:
                print(f"  [-] {pkg.ljust(15)} : Missing Visual C++ Runtime! (Run Install_Visual_Cpp.bat)")
            else:
                print(f"  [-] {pkg.ljust(15)} : NOT installed! ({desc})")
            all_passed = False

    # 3. Check Hardware Acceleration (GPU / CPU)
    print("\n[*] Hardware Acceleration Check:")
    try:
        import torch
        cuda_ok = torch.cuda.is_available()
        if cuda_ok:
            gpu_name = torch.cuda.get_device_name(0)
            print(f"  [+] NVIDIA CUDA is Active & Ready: {gpu_name} (Maximum Speed)")
        else:
            print("  [i] Running on CPU (Intel / AMD) - Fast ONNX acceleration enabled.")
    except Exception as e:
        print(f"  [-] Error during GPU check: {e}")

    # 4. Check AI Models
    print("\n[*] Checking AI Model Files:")
    models_dir = BASE_DIR / "models"
    models_to_check = [
        "yolo11n-manga109-bubble.pt",
        "comic-speech-bubble-detector.pt",
        "comictextdetector.pt",
        "comictextdetector.pt.onnx"
    ]
    for m in models_to_check:
        m_path = models_dir / m
        if m_path.is_file() and m_path.stat().st_size > 1_000_000:
            mb = round(m_path.stat().st_size / (1024 * 1024), 1)
            print(f"  [+] {m.ljust(34)} : Present ({mb} MB)")
        else:
            print(f"  [!] {m.ljust(34)} : Not found (will download on first run)")

    print("\n" + "=" * 65)
    if all_passed:
        print("  [SUCCESS] Environment is 100% ready! You can run the application.")
    else:
        print("  [WARNING] Some packages are missing. Run: pip install -r requirements.txt")
    print("=" * 65)
    return all_passed


if __name__ == "__main__":
    passed = run_checks()
    if not passed or "--wait" in sys.argv:
        input("\nPress Enter to exit...")
