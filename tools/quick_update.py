"""
SmartCleaner-AI - Standalone Quick Updater & Repair Tool
Fetches the latest release from SmartCleaner-AI-Updata, extracts it, and updates local files.
"""

import os
import sys
import json
import shutil
import zipfile
import urllib.request
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

MANIFEST_URL = "https://raw.githubusercontent.com/abdallahashour98/SmartCleaner-AI-Updata/main/version_manifest.json"


def run_quick_update(target_dir: Path) -> bool:
    print("=" * 65)
    print("   SmartCleaner-AI - Quick Update & Repair Tool")
    print("=" * 65)
    print(f"[*] Checking for latest version from update server...")

    try:
        req = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "SmartCleaner-Updater"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            manifest = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[-] Failed to fetch update manifest: {e}")
        return False

    latest_ver = manifest.get("latest_version", "1.1.0")
    patch_url = manifest.get("patch_url")
    notes = manifest.get("release_notes", "")

    print(f"[+] Latest version available: v{latest_ver}")
    if notes:
        print(f"[*] Release Notes: {notes}")
    print(f"[*] Downloading patch package...")

    temp_zip = target_dir / f"temp_patch_{os.getpid()}.zip"
    try:
        urllib.request.urlretrieve(patch_url, temp_zip)
        size_kb = round(temp_zip.stat().st_size / 1024, 1)
        print(f"[+] Download complete ({size_kb} KB). Extracting files...")

        with zipfile.ZipFile(temp_zip, "r") as zf:
            zf.extractall(target_dir)

        temp_zip.unlink(missing_ok=True)
        print(f"[+] Successfully installed v{latest_ver}!")
        print("=" * 65)
        return True
    except Exception as e:
        if temp_zip.exists():
            temp_zip.unlink(missing_ok=True)
        print(f"[-] Error installing update: {e}")
        return False


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent
    if len(sys.argv) > 1:
        target = Path(sys.argv[1]).resolve()

    success = run_quick_update(target)
    sys.exit(0 if success else 1)
