"""
SmartCleaner-AI - Developer Patch Packager
Automates generating lightweight update patches (<2-5 MB) and the version_manifest.json
for distribution via GitHub Releases or custom web hosting.
"""

import os
import sys
import json
import time
import hashlib
import zipfile
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
UPDATES_OUTPUT_DIR = BASE_DIR / "updates"

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


def create_patch(version: str, notes: str, download_url_base: str = ""):
    UPDATES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    patch_zip_name = f"SmartCleaner_Patch_v{version}.zip"
    patch_zip_path = UPDATES_OUTPUT_DIR / patch_zip_name

    print(f"[*] Packaging SmartCleaner-AI Update Patch v{version}...")

    # Files and folders to package in the modular update
    include_files = [
        "SmartCleaner.bat",
        "SmartCleaner_Debug.bat",
        "Install_Dependencies.bat",
        "Run_SmartCleaner.bat",
        "Run_SmartCleaner.vbs",
        "Run_Server.bat",
        "Silent_Start_Server.vbs",
        "Stop_Server.bat",
        "gui_cleaner.py",
        "fast_cleaner.py",
        "server_api.py",
        "Fix_Update.bat",
        "requirements.txt",
        "pyrightconfig.json"
    ]

    include_dirs = [
        "pcleaner",
        "tools"
    ]

    # Exclusions
    exclude_patterns = [
        "__pycache__",
        ".git",
        ".vscode",
        "*.pyc",
        "*.pyo",
        "ngrok.exe",
        "ngrok_temp.zip",
        "backup",
        "scratch",
        "data"
    ]

    def is_excluded(p: Path) -> bool:
        parts = p.parts
        for part in parts:
            if part in ("__pycache__", ".git", ".vscode", "backup", "scratch", "data"):
                return True
        if p.name.endswith(".pyc") or p.name.endswith(".pyo") or p.name in ("ngrok.exe", "ngrok_temp.zip"):
            return True
        return False

    with zipfile.ZipFile(patch_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        # 1. Update version.json inside the patch
        updated_version_info = {
            "app_name": "SmartCleaner-AI",
            "version": version,
            "build_date": time.strftime("%Y-%m-%d"),
            "channel": "stable",
            "update_manifest_url": f"{download_url_base.rstrip('/')}/version_manifest.json" if download_url_base else "",
            "auto_check_on_startup": True
        }
        z.writestr("version.json", json.dumps(updated_version_info, indent=2, ensure_ascii=False))
        print("  [+] Added: version.json")

        # 2. Add top-level individual files
        for fname in include_files:
            fpath = BASE_DIR / fname
            if fpath.is_file():
                z.write(fpath, arcname=fname)
                print(f"  [+] Added: {fname}")

        # 3. Add directory trees
        for dname in include_dirs:
            dpath = BASE_DIR / dname
            if dpath.is_dir():
                for subfile in dpath.rglob("*"):
                    if subfile.is_file() and not is_excluded(subfile):
                        arcname = str(subfile.relative_to(BASE_DIR)).replace("\\", "/")
                        z.write(subfile, arcname=arcname)
                        print(f"  [+] Added: {arcname}")

    patch_size = patch_zip_path.stat().st_size
    patch_sha = calculate_sha256(patch_zip_path)

    # 4. Generate version_manifest.json
    final_patch_url = f"{download_url_base.rstrip('/')}/{patch_zip_name}" if download_url_base else patch_zip_name
    manifest = {
        "latest_version": version,
        "release_date": time.strftime("%Y-%m-%d"),
        "release_notes": notes or f"SmartCleaner-AI v{version} update and stability improvements.",
        "patch_url": final_patch_url,
        "sha256": patch_sha,
        "size_bytes": patch_size,
        "size_mb": round(patch_size / (1024 * 1024), 2),
        "min_runtime_version": "3.10"
    }

    manifest_path = UPDATES_OUTPUT_DIR / "version_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("✅ Update Patch Created Successfully!")
    print(f"📦 Patch File: {patch_zip_path} ({round(patch_size / 1024, 1)} KB)")
    print(f"📄 Manifest:   {manifest_path}")
    print(f"🔒 SHA256:     {patch_sha}")
    print("=" * 60)
    print("🚀 Deployment Steps:")
    print("  1. Upload 'SmartCleaner_Patch_v{version}.zip' and 'version_manifest.json'")
    print("     to your GitHub Releases or web hosting.")
    print("  2. Existing users will automatically detect and download this patch in seconds!")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create SmartCleaner-AI Update Patch")
    parser.add_argument("--version", default="1.0.1", help="New version number (e.g. 1.0.1)")
    parser.add_argument("--notes", default="تحديث جديد وإصلاحات برمجية عامة.", help="Release notes in Arabic/English")
    parser.add_argument("--url-base", default="", help="Base URL where files will be hosted (e.g. https://github.com/.../releases/download/v1.0.1)")
    args = parser.parse_args()

    create_patch(args.version, args.notes, args.url_base)
