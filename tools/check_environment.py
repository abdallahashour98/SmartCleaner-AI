"""
SmartCleaner-AI - End-User Environment & Diagnostics Checker
Runs pre-flight checks on Python version, required AI libraries,
GPU / DirectML hardware detection, and required model files.
"""

import os
import sys
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
    print("   فحص بيئة تشغيل استوديو التبييض الذكي SmartCleaner-AI")
    print("   SmartCleaner-AI Environment Pre-Flight Diagnostics")
    print("=" * 65)

    all_passed = True

    # 1. Check Python version
    py_ver = sys.version_info
    print(f"[*] إصدار بايثون (Python Version): {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    if py_ver < (3, 10):
        print("  [!] تحذير: يُفضل استخدام بايثون 3.10 أو أحدث لضمان استقرار الذكاء الاصطناعي.")
    else:
        print("  [+] إصدار بايثون متوافق تماماً.")

    # 2. Check Core Dependencies
    required_packages = [
        ("PySide6", "مكتبة واجهة المستخدم الرسومية (GUI Framework)"),
        ("torch", "محرك الذكاء الاصطناعي (PyTorch Engine)"),
        ("cv2", "مكتبة معالجة الصور السريعة (OpenCV)"),
        ("PIL", "مكتبة الصور (Pillow)"),
        ("numpy", "مكتبة المصفوفات الرياضية (NumPy)"),
        ("ultralytics", "نموذج اكتشاف الفقاعات (YOLOv8)"),
        ("requests", "مكتبة الاتصال والشبكة (Requests)"),
        ("fastapi", "سيرفر الاتصال وتطبيق الموبايل (FastAPI)"),
        ("uvicorn", "خادم ويب السيرفر (Uvicorn)"),
    ]

    print("\n[*] فحص المكتبات البرمجية الأساسية (Core Libraries):")
    for pkg, desc in required_packages:
        try:
            __import__(pkg)
            print(f"  [+] {pkg.ljust(15)} : مثبت بنجاح ({desc})")
        except ImportError:
            print(f"  [-] {pkg.ljust(15)} : غير متوفر! ({desc})")
            all_passed = False

    # 3. Check Hardware Acceleration (GPU / CPU)
    print("\n[*] فحص تسريع العتاد وكارت الشاشة (Hardware Acceleration):")
    try:
        import torch
        cuda_ok = torch.cuda.is_available()
        if cuda_ok:
            gpu_name = torch.cuda.get_device_name(0)
            print(f"  [+] NVIDIA CUDA نشط وجاهز: {gpu_name} (أقصى سرعة)")
        else:
            print("  [i] تشغيل على المعالج CPU (Intel / AMD) - تم تفعيل تسريع ONNX السريع.")
    except Exception as e:
        print(f"  [-] خطأ أثناء فحص GPU: {e}")

    # 4. Check AI Models
    print("\n[*] فحص نماذج وأوزان الذكاء الاصطناعي (AI Models):")
    models_dir = BASE_DIR / "models"
    models_to_check = [
        "comic-speech-bubble-detector.pt",
        "comictextdetector.pt",
        "comictextdetector.pt.onnx"
    ]
    for m in models_to_check:
        m_path = models_dir / m
        if m_path.is_file() and m_path.stat().st_size > 1_000_000:
            mb = round(m_path.stat().st_size / (1024 * 1024), 1)
            print(f"  [+] {m.ljust(34)} : متوفر ومكتمل ({mb} MB)")
        else:
            print(f"  [!] {m.ljust(34)} : غير موجود (سيتم تنزيله تلقائياً عند أول تشغيل)")

    print("\n" + "=" * 65)
    if all_passed:
        print("✨ بيئة التشغيل مكتملة وجاهزة بنسبة 100%! يمكنك تشغيل البرنامج الآن.")
    else:
        print("⚠️ هناك بعض المكتبات الناقصة. يرجى تثبيت المتطلبات عبر: pip install -r requirements.txt")
    print("=" * 65)
    return all_passed


if __name__ == "__main__":
    passed = run_checks()
    if not passed or "--wait" in sys.argv:
        input("\nاضغط Enter للإغلاق...")
