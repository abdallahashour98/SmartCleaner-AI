"""
SmartCleaner-AI - End-User Portable Release Packager
Packages a clean, production-ready portable folder and ZIP for end users,
excluding development files, test scripts, and caches.
"""

import os
import sys
import json
import shutil
import zipfile
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "dist"

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



def package_release(include_models: bool = True, create_zip: bool = True):
    version_file = BASE_DIR / "version.json"
    version = "1.0.0"
    if version_file.exists():
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                v_data = json.load(f)
                version = v_data.get("version", "1.0.0")
        except Exception:
            pass

    release_folder_name = "SmartCleaner-AI_Portable"
    release_dir = DIST_DIR / release_folder_name

    print("=" * 65)
    print(f"📦 Packaging SmartCleaner-AI End-User Release v{version}")
    print("=" * 65)

    if release_dir.exists():
        print(f"[*] Cleaning previous build: {release_dir}")
        shutil.rmtree(release_dir, ignore_errors=True)
    release_dir.mkdir(parents=True, exist_ok=True)

    # 1. Essential Top-level files
    top_files = [
        "gui_cleaner.py",
        "fast_cleaner.py",
        "server_api.py",
        "version.json",
        "requirements.txt",
        "SmartCleaner.bat",
        "SmartCleaner_Debug.bat",
        "Install_Dependencies.bat",
        "Run_SmartCleaner.bat",
        "Run_SmartCleaner.vbs",
        "Run_Server.bat",
        "Silent_Start_Server.vbs",
        "Stop_Server.bat",
        "pyrightconfig.json"
    ]

    print("[*] Copying core application files...")
    for tf in top_files:
        src = BASE_DIR / tf
        if src.is_file():
            shutil.copy2(src, release_dir / tf)
            print(f"  [+] {tf}")

    # Write a clean, sanitized default gui_config.json
    clean_config = {
        "last_image_paths": [],
        "last_output_dir": "",
        "last_input_dir": "",
        "last_project_dir": "",
        "last_export_dir": "",
        "last_launcher_dir": "",
        "iopaint_launcher_path": "",
        "mask_padding": 3,
        "snap_to_bubbles": False,
        "iopaint_enabled": False,
        "iopaint_adaptive": True,
        "iopaint_server_url": "http://127.0.0.1:8080",
        "iopaint_model": "anime-lama",
        "iopaint_dilation": 5,
        "use_remote_server": False,
        "remote_server_url": "",
        "shortcuts": {
            "toggle_cleaned": "Space",
            "magic_wand": "W",
            "brush_tool": "B",
            "draw_box": "A",
            "inpaint_page": "C",
            "zoom_in": "+",
            "zoom_out": "-",
            "fit_view": "F",
            "next_page": "Right",
            "prev_page": "Left",
            "export_image": "Ctrl+S",
            "delete_bubble": "Delete"
        },
        "window_width": 1140,
        "window_height": 890,
        "window_is_maximized": False,
        "available_iopaint_models": [
            "anime-lama",
            "lama",
            "cv2",
            "manga"
        ],
        "device_mode": "auto",
        "ngrok_authtoken": "",
        "ngrok_domain": "",
        "server_port": 8000,
        "server_auto_ngrok": True,
        "cached_gpu_info": {
            "has_nvidia": False,
            "gpu_name": ""
        }
    }
    with open(release_dir / "gui_config.json", "w", encoding="utf-8") as f:
        json.dump(clean_config, f, indent=2, ensure_ascii=False)
    print("  [+] gui_config.json (Clean Default Configuration)")

    # 2. Modules and directories
    dirs_to_copy = ["pcleaner", "tools"]
    if include_models:
        dirs_to_copy.append("models")

    def copy_filtered_tree(src_dir: Path, dst_dir: Path):
        dst_dir.mkdir(parents=True, exist_ok=True)
        for item in src_dir.iterdir():
            if item.name in ("__pycache__", ".git", ".vscode", "scratch", "backup"):
                continue
            if item.name.endswith(".pyc") or item.name.endswith(".pyo") or item.name == "ngrok_temp.zip":
                continue
            dst_item = dst_dir / item.name
            if item.is_dir():
                copy_filtered_tree(item, dst_item)
            elif item.is_file():
                shutil.copy2(item, dst_item)

    for d in dirs_to_copy:
        src_d = BASE_DIR / d
        if src_d.is_dir():
            print(f"[*] Copying module directory: {d}...")
            copy_filtered_tree(src_d, release_dir / d)

    # 3. Create Readme_User.txt
    readme_content = f"""====================================================================
           استوديو التبييض الذكي SmartCleaner-AI (الإصدار {version})
====================================================================

مرحباً بك في برنامج SmartCleaner-AI!
أداة الذكاء الاصطناعي المتخصصة في تبييض وإزالة النصوص وإعادة رسم خلفيات المانجا والقصص المصورة.

--------------------------------------------------------------------
🚀 طريقة التشغيل:
--------------------------------------------------------------------
1. انقر نقراً مزدوجاً على ملف:
   SmartCleaner.bat  (أو Run_SmartCleaner.vbs للتشغيل الصامت)

2. في حال حدوث أي خطأ أو أردت التأكد من توافق بيئتك:
   شغّل: SmartCleaner_Debug.bat
   وسيقوم بفحص المكتبات وإظهار أي تنبيهات تشخيصية فوراً.

3. لتثبيت المتطلبات يدوياً في حال كانت بيئتك جديدة:
   pip install -r requirements.txt


--------------------------------------------------------------------
📱 طريقة الربط والتشغيل عن بُعد من الموبايل:
--------------------------------------------------------------------
1. افتح البرنامج واذهب إلى بطاقة "Mobile Bridge Server".
2. ضع كود التوكن الخاص بك من موقع Ngrok (مجاني من dashboard.ngrok.com).
3. اضغط على زر "⚡ تثبيت وتفعيل الخدمة فورياً":
   - سيقوم البرنامج تلقائياً بتثبيت أداة Ngrok وضبط السيريال.
   - سيظهر لك رابط النفق العام وكود الـ QR.
4. افتح تطبيق SmartCleaner على الموبايل وامسح كود الـ QR، وستتمكن من تنظيف الفصول عن بُعد في أي وقت وأي مكان!

--------------------------------------------------------------------
🔄 التحديثات التلقائية (Auto-Update):
--------------------------------------------------------------------
- يحتوي البرنامج على نظام تحديث تلقائي ذكي.
- عند صدور أي إصلاحات أو ميزات جديدة، سيظهر لك إشعار داخل البرنامج.
- يتم تنزيل التحديث الصغير (<2 ميجابايت) واستبدال الملفات تلقائياً في ثوانٍ دون الحاجة لإعادة تحميل البرنامج كاملاً.
- يمكنك أيضاً الضغط على "التحقق من التحديثات" في أي وقت.

نتمنى لك تجربة ممتعة وسريعة! 🎨✨
"""
    with open(release_dir / "README_User.txt", "w", encoding="utf-8") as f:
        f.write(readme_content)

    print("[+] Created user launcher: SmartCleaner.bat")
    print("[+] Created user documentation: README_User.txt")

    # 5. Create final Distribution ZIP if requested
    if create_zip:
        zip_output_path = DIST_DIR / f"SmartCleaner-AI_v{version}_Portable.zip"
        print(f"\n[*] Creating ZIP archive: {zip_output_path}...")
        with zipfile.ZipFile(zip_output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for root, _, files in os.walk(release_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(DIST_DIR)
                    zf.write(file_path, arcname=arcname)

        final_zip_size = zip_output_path.stat().st_size
        print(f"✅ Distribution ZIP created: {round(final_zip_size / (1024 * 1024), 2)} MB")

    print("\n" + "=" * 65)
    print("🎉 End-User Release Built Successfully!")
    print(f"📁 Folder: {release_dir}")
    if create_zip:
        print(f"📦 Archive: {DIST_DIR / f'SmartCleaner-AI_v{version}_Portable.zip'}")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Package SmartCleaner-AI End-User Release")
    parser.add_argument("--no-models", action="store_true", help="Do not include heavy models in the release")
    parser.add_argument("--no-zip", action="store_true", help="Do not create final ZIP archive")
    args = parser.parse_args()

    package_release(include_models=not args.no_models, create_zip=not args.no_zip)
