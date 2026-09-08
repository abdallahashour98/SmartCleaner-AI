"""
SmartCleaner-AI - Master Build & Release Packager
Packages clean, production-ready distributions for end users:
1. Portable Folder (dist/SmartCleaner-AI_Portable)
2. Full Portable ZIP with AI Models (dist/SmartCleaner-AI_v{version}_Portable.zip)
3. Complete Code Update ZIP without models (dist/SmartCleaner_Complete_Code_Update.zip)
4. Minimal Fix Patch ZIP (dist/SmartCleaner_Fix_Only.zip)
5. In-App Auto-Update Patch & Manifest (updates/SmartCleaner_Patch_v{version}.zip & updates/version_manifest.json)
"""

import os
import sys
import json
import time
import shutil
import hashlib
import zipfile
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "dist"
UPDATES_DIR = BASE_DIR / "updates"

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def calculate_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_version() -> str:
    version_file = BASE_DIR / "version.json"
    if version_file.exists():
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                v_data = json.load(f)
                return v_data.get("version", "1.0.0")
        except Exception:
            pass
    return "1.0.0"


def copy_filtered_tree(src_dir: Path, dst_dir: Path):
    dst_dir.mkdir(parents=True, exist_ok=True)
    exclude_dirs = {"__pycache__", ".git", ".vscode", "scratch", "backup"}
    exclude_files = {".pyc", ".pyo"}
    for item in src_dir.iterdir():
        if item.name in exclude_dirs:
            continue
        if any(item.name.endswith(ext) for ext in exclude_files) or item.name == "ngrok_temp.zip":
            continue
        dst_item = dst_dir / item.name
        if item.is_dir():
            copy_filtered_tree(item, dst_item)
        elif item.is_file():
            shutil.copy2(item, dst_item)


def build_release(
    include_models: bool = True,
    build_full: bool = True,
    build_code_update: bool = True,
    build_fix_only: bool = True,
    build_inapp_patch: bool = True
):
    version = get_version()
    release_dir = DIST_DIR / "SmartCleaner-AI_Portable"
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    UPDATES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"  SmartCleaner-AI - Full Build Pipeline v{version}")
    print("=" * 70)

    # 1. Clean previous build folder
    if release_dir.exists():
        print(f"[*] Cleaning previous staging folder: {release_dir.name}...")
        shutil.rmtree(release_dir, ignore_errors=True)
    release_dir.mkdir(parents=True, exist_ok=True)

    # 2. Copy Top-level Files
    top_files = [
        "SmartCleaner.bat",
        "SmartCleaner_Debug.bat",
        "Install_Dependencies.bat",
        "Install_Visual_Cpp.bat",
        "Run_SmartCleaner.bat",
        "Run_SmartCleaner.vbs",
        "Run_Server.bat",
        "Silent_Start_Server.vbs",
        "Stop_Server.bat",
        "gui_cleaner.py",
        "fast_cleaner.py",
        "server_api.py",
        "version.json",
        "requirements.txt",
        "pyrightconfig.json"
    ]

    print("[*] Copying core application files...")
    for tf in top_files:
        src = BASE_DIR / tf
        if src.is_file():
            shutil.copy2(src, release_dir / tf)
            print(f"  [+] {tf}")

    # 3. Create sanitized default configuration
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
    print("  [+] gui_config.json (Default Clean Configuration)")

    # 4. Copy Directories (pcleaner, tools, models)
    dirs_to_copy = ["pcleaner", "tools"]
    if include_models:
        dirs_to_copy.append("models")

    for d in dirs_to_copy:
        src_d = BASE_DIR / d
        if src_d.is_dir():
            print(f"[*] Copying module directory: {d}...")
            copy_filtered_tree(src_d, release_dir / d)

    # 5. Create user documentation
    readme_content = f"""====================================================================
           استوديو التبييض الذكي SmartCleaner-AI (الإصدار {version})
====================================================================

مرحباً بك في برنامج SmartCleaner-AI!
أداة الذكاء الاصطناعي المتخصصة في تبييض وإزالة النصوص وإعادة رسم خلفيات المانجا والقصص المصورة.

--------------------------------------------------------------------
🚀 طريقة التشغيل لأول مرة:
--------------------------------------------------------------------
1. تأكد من استخراج المجلد المضغوط كاملاً (Extract All / استخراج الكل).
2. انقر نقراً مزدوجاً على:
   SmartCleaner.bat
   (سيقوم البرنامج تلقائياً بالتحقق من بيئة بايثون وتثبيت المكتبات فوراً).

3. في حال واجهت أي استفسار أو مشكلة:
   شغّل: SmartCleaner_Debug.bat
   أو: Install_Dependencies.bat

--------------------------------------------------------------------
📱 الربط عن بُعد مع تطبيق الموبايل (Mobile Bridge):
--------------------------------------------------------------------
1. افتح البرنامج ثم انتقل إلى تبويب "Mobile Bridge Server".
2. أدخل توكن حسابك المجاني من ngrok.com.
3. اضغط "تثبيت وتفعيل الخدمة"، وسيظهر لك رمز QR للاتصال المباشر من هاتفك.

--------------------------------------------------------------------
🔄 التحديثات التلقائية (Auto-Update):
--------------------------------------------------------------------
- يتضمن البرنامج نظام تحديث تلقائي ذكي يتحقق من وجود أي إصلاحات
  جديدة ويقوم بتنزيلها وتثبيتها بضغطة زر دون إعادة تحميل البرنامج كاملاً.

نتمنى لك تجربة ممتعة وسريعة! 🎨✨
"""
    with open(release_dir / "README_User.txt", "w", encoding="utf-8") as f:
        f.write(readme_content)
    print("  [+] README_User.txt")

    results = []

    # 6. Build Full Portable ZIP (with Models)
    if build_full:
        full_zip_path = DIST_DIR / f"SmartCleaner-AI_v{version}_Portable.zip"
        print(f"\n[*] Compressing Full Release: {full_zip_path.name}...")
        with zipfile.ZipFile(full_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for root, _, files in os.walk(release_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(DIST_DIR)
                    zf.write(file_path, arcname=arcname)
        size_mb = round(full_zip_path.stat().st_size / (1024 * 1024), 2)
        results.append(("Full Portable Bundle (With AI Models)", full_zip_path, f"{size_mb} MB"))
        print(f"  [✓] Created {full_zip_path.name} ({size_mb} MB)")

    # 7. Build Complete Code Update ZIP (Everything except models)
    if build_code_update:
        code_update_path = DIST_DIR / "SmartCleaner_Complete_Code_Update.zip"
        print(f"\n[*] Compressing Complete Code Update: {code_update_path.name}...")
        with zipfile.ZipFile(code_update_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for root, _, files in os.walk(release_dir):
                for file in files:
                    file_path = Path(root) / file
                    rel_to_rel = file_path.relative_to(release_dir)
                    # Skip models directory in code update
                    if rel_to_rel.parts and rel_to_rel.parts[0] == "models":
                        continue
                    zf.write(file_path, arcname=str(rel_to_rel).replace("\\", "/"))
        size_kb = round(code_update_path.stat().st_size / 1024, 1)
        results.append(("Complete Code Update (Extract to replace existing app)", code_update_path, f"{size_kb} KB"))
        print(f"  [✓] Created {code_update_path.name} ({size_kb} KB)")

    # 8. Build Fix-Only ZIP (Only essential launchers and fixed core files)
    if build_fix_only:
        fix_zip_path = DIST_DIR / "SmartCleaner_Fix_Only.zip"
        print(f"\n[*] Compressing Hotfix Package: {fix_zip_path.name}...")
        fix_files = [
            "SmartCleaner.bat",
            "SmartCleaner_Debug.bat",
            "Install_Dependencies.bat",
            "Install_Visual_Cpp.bat",
            "Run_SmartCleaner.bat",
            "Run_SmartCleaner.vbs",
            "gui_cleaner.py",
            "version.json",
            "requirements.txt",
            "tools/launcher.py",
            "tools/check_environment.py",
            "pcleaner/updater.py"
        ]
        with zipfile.ZipFile(fix_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for ff in fix_files:
                src_f = BASE_DIR / ff
                if src_f.is_file():
                    zf.write(src_f, arcname=ff)
        size_kb = round(fix_zip_path.stat().st_size / 1024, 1)
        results.append(("Hotfix Only (Launchers, Launcher.py, GUI, Updater)", fix_zip_path, f"{size_kb} KB"))
        print(f"  [✓] Created {fix_zip_path.name} ({size_kb} KB)")

    # 9. Build In-App Auto-Update Patch & Manifest
    if build_inapp_patch:
        patch_name = f"SmartCleaner_Patch_v{version}.zip"
        patch_path = UPDATES_DIR / patch_name
        print(f"\n[*] Compressing In-App Auto-Update Patch: {patch_name}...")
        # Use code update contents for the patch
        with zipfile.ZipFile(patch_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for root, _, files in os.walk(release_dir):
                for file in files:
                    file_path = Path(root) / file
                    rel_to_rel = file_path.relative_to(release_dir)
                    if rel_to_rel.parts and rel_to_rel.parts[0] == "models":
                        continue
                    zf.write(file_path, arcname=str(rel_to_rel).replace("\\", "/"))

        patch_sha = calculate_sha256(patch_path)
        patch_size = patch_path.stat().st_size
        manifest = {
            "latest_version": version,
            "release_date": time.strftime("%Y-%m-%d"),
            "release_notes": f"تحديث شامل SmartCleaner-AI v{version} مع مشغل التشغيل الذكي التلقائي وحل مشاكل الترميز.",
            "patch_url": f"https://raw.githubusercontent.com/abdallahashour98/SmartCleaner-AI/main/updates/{patch_name}",
            "sha256": patch_sha,
            "size_bytes": patch_size,
            "size_mb": round(patch_size / (1024 * 1024), 2),
            "min_runtime_version": "3.10"
        }
        manifest_path = UPDATES_DIR / "version_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        results.append(("In-App Auto-Update Patch (GitHub hosted)", patch_path, f"{round(patch_size / 1024, 1)} KB"))
        results.append(("Update Manifest JSON", manifest_path, f"{manifest_path.stat().st_size} bytes"))
        print(f"  [✓] Created {patch_name} & version_manifest.json")

    # 10. Summary Table
    print("\n" + "=" * 70)
    print("🎉 BUILD PROCESS COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print(f"{'Package Name':<45} | {'Size':<10}")
    print("-" * 70)
    for desc, path, sz in results:
        print(f"{path.name:<45} | {sz:<10}")
    print("=" * 70)
    print(f"\nStaging Directory: {release_dir}")
    print(f"Output Directory:  {DIST_DIR}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SmartCleaner-AI Master Build System")
    parser.add_argument("--no-models", action="store_true", help="Exclude AI models from the full build")
    parser.add_argument("--full-only", action="store_true", help="Build only the full portable package")
    parser.add_argument("--code-only", action="store_true", help="Build only the code update package")
    parser.add_argument("--fix-only", action="store_true", help="Build only the fix patch package")
    args = parser.parse_args()

    b_full = True
    b_code = True
    b_fix = True

    if args.full_only:
        b_code = False
        b_fix = False
    elif args.code_only:
        b_full = False
        b_fix = False
    elif args.fix_only:
        b_full = False
        b_code = False

    build_release(
        include_models=not args.no_models,
        build_full=b_full,
        build_code_update=b_code,
        build_fix_only=b_fix,
        build_inapp_patch=True
    )
