"""
SmartCleaner-AI - Universal Bootstrapper & Environment Verifier
100% Pure English - Zero encoding issues on any Windows locale.
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
base_dir_str = str(BASE_DIR)
if base_dir_str not in sys.path:
    sys.path.insert(0, base_dir_str)
os.chdir(base_dir_str)

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def show_native_alert(title: str, message: str, is_error: bool = False):
    """Displays a native Windows alert dialog using standard ctypes."""
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
    ("pyclipper", "pyclipper"),
    ("shapely", "shapely"),
    ("onnxruntime", "onnxruntime-directml" if sys.platform == "win32" else "onnxruntime"),
    ("PIL", "pillow"),
    ("numpy", "numpy"),
    ("requests", "requests"),
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("loguru", "loguru"),
    ("qrcode", "qrcode")
]


def install_vcredist():
    """Automatically downloads and installs Microsoft Visual C++ 2015-2022 Redistributable."""
    print("\n" + "=" * 65)
    print("  [!] Microsoft Visual C++ Redistributable Required")
    print("  PyTorch AI engine requires Visual C++ 2015-2022 (vcruntime140_1.dll).")
    print("=" * 65)

    # 1. Try winget first
    try:
        res = subprocess.run(
            ["winget", "install", "Microsoft.VCRedist.2015+.x64", "--accept-package-agreements", "--accept-source-agreements"],
            capture_output=True, text=True
        )
        if res.returncode == 0:
            print("[+] Installed Microsoft Visual C++ Redistributable via winget!")
            return True
    except Exception:
        pass

    # 2. Direct download from Microsoft
    installer_path = BASE_DIR / "vc_redist.x64.exe"
    print("[*] Downloading official vc_redist.x64.exe from Microsoft...")
    try:
        import urllib.request
        urllib.request.urlretrieve("https://aka.ms/vs/17/release/vc_redist.x64.exe", str(installer_path))
        if installer_path.exists():
            print("[*] Installing Microsoft Visual C++ Redistributable (takes ~5 seconds)...")
            subprocess.run([str(installer_path), "/passive", "/norestart"], check=True)
            installer_path.unlink(missing_ok=True)
            print("[+] Microsoft Visual C++ Redistributable installed successfully!")
            return True
    except Exception as dl_err:
        print(f"[!] Could not auto-install: {dl_err}")
        show_native_alert(
            "Visual C++ Required",
            "PyTorch requires Microsoft Visual C++ 2015-2022 Redistributable.\n\n"
            "Please install it from:\nhttps://aka.ms/vs/17/release/vc_redist.x64.exe",
            is_error=True
        )
        try:
            import webbrowser
            webbrowser.open("https://aka.ms/vs/17/release/vc_redist.x64.exe")
        except Exception:
            pass
    return False


def check_and_install_dependencies():
    missing = []
    for mod_name, pkg_name in REQUIRED_MODULES:
        try:
            __import__(mod_name)
        except Exception as e:
            err_str = str(e)
            if mod_name == "torch" and ("126" in err_str or "shm.dll" in err_str or "vcruntime" in err_str):
                print(f"\n[*] PyTorch C++ runtime missing (WinError 126).")
                if install_vcredist():
                    try:
                        __import__("torch")
                        print("[+] PyTorch loaded successfully after VC++ installation!")
                        continue
                    except Exception as e_retry:
                        print(f"[!] PyTorch import error after VC++ installation: {e_retry}")
            missing.append(pkg_name)

    if not missing:
        return True

    print("=" * 65)
    print("  SmartCleaner-AI: First-time Dependency Setup")
    print("  Preparing and installing required AI libraries...")
    print("=" * 65)
    print(f"[*] Missing modules: {', '.join(missing)}")
    print("[*] Installing packages from requirements.txt via pip...")
    print("    (This runs once and takes 1-2 minutes. Please wait...)\n")

    req_file = BASE_DIR / "requirements.txt"
    if not req_file.exists():
        print(f"[!] Error: requirements.txt not found at {req_file}")
        return False

    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=False)
    except Exception:
        pass

    install_cmd = [sys.executable, "-m", "pip", "install", "-r", str(req_file)]
    res = subprocess.run(install_cmd)

    if res.returncode == 0:
        print("\n" + "=" * 65)
        print("  [SUCCESS] All dependencies installed! Launching app...")
        print("=" * 65 + "\n")
        return True
    else:
        error_msg = (
            "Failed to install required Python packages automatically.\n\n"
            "• If the error mentions 'Access is denied' (WinError 5), another running\n"
            "  Python or SmartCleaner instance has locked the DLL files.\n"
            "  Please close any other Python console windows or restart your PC, then retry.\n"
            "• Otherwise, please check your internet connection.\n\n"
            f"Command exit code: {res.returncode}"
        )
        print("\n[!] " + error_msg)
        show_native_alert("SmartCleaner-AI Setup Error", error_msg, is_error=True)
        return False


def main():
    print("========================================================")
    print("  Starting SmartCleaner-AI Studio...")
    print(f"  Python executable: {sys.executable}")
    print(f"  Python version: {sys.version.split()[0]}")
    print("========================================================\n")

    # 1. Check Python version
    if sys.version_info < (3, 9):
        err = f"Python version is too old: {sys.version}. Please install Python 3.10 or newer."
        print(f"[!] {err}")
        show_native_alert("Python Version Error", err, is_error=True)
        return 1

    # 2. Check and install dependencies if missing
    if not check_and_install_dependencies():
        input("\nPress Enter to exit...")
        return 1

    # 3. Launch main GUI
    if base_dir_str not in sys.path:
        sys.path.insert(0, base_dir_str)

    gui_file = BASE_DIR / "gui_cleaner.py"
    if not gui_file.exists():
        err_msg = f"gui_cleaner.py was not found at:\n{gui_file}\n\nPlease ensure you have fully extracted the application ZIP."
        print(f"[!] {err_msg}")
        show_native_alert("Missing File Error", err_msg, is_error=True)
        input("\nPress Enter to exit...")
        return 1

    try:
        try:
            import gui_cleaner
            gui_cleaner.main()
            return 0
        except ModuleNotFoundError as mne:
            if "gui_cleaner" in str(mne):
                import importlib.util
                spec = importlib.util.spec_from_file_location("gui_cleaner", str(gui_file))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules["gui_cleaner"] = mod
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "main"):
                        mod.main()
                        return 0
            raise mne
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print("\n" + "=" * 65)
        print("  [CRITICAL ERROR] Failed to run SmartCleaner-AI:")
        print("=" * 65)
        print(tb)
        print("=" * 65)

        err_msg = (
            f"An error occurred while launching SmartCleaner-AI:\n\n"
            f"{str(e)}\n\n"
            "Please check the terminal console window for full traceback details."
        )
        show_native_alert("SmartCleaner-AI Launch Error", err_msg, is_error=True)
        input("\nPress Enter to exit...")
        return 1


if __name__ == "__main__":
    sys.exit(main())
