"""
SmartCleaner-AI - Standalone Patch Applier & Auto-Restart Helper
This script runs independently when the main application closes to:
1. Wait for the main app process to release file locks.
2. Create a timestamped backup of modified files.
3. Extract and replace updated code files from the patch ZIP.
4. Update version.json.
5. Relaunch SmartCleaner-AI automatically.
"""

import os
import sys
import time
import shutil
import zipfile
import argparse
import subprocess
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass



def wait_for_pid(pid: int, timeout: float = 15.0) -> bool:
    """Waits until the given process terminates."""
    if pid <= 0:
        return True
    start = time.time()
    while time.time() - start < timeout:
        try:
            # os.kill(pid, 0) checks if process exists on POSIX and Windows (with pywin32 or ctypes)
            if os.name == "nt":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                process = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if not process:
                    return True
                kernel32.CloseHandle(process)
            else:
                os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.3)
    return False


def apply_patch(patch_zip: str, target_dir: str, caller_pid: int, restart_cmd: str):
    target_path = Path(target_dir).resolve()
    zip_path = Path(patch_zip).resolve()

    print(f"[*] SmartCleaner-AI Patch Installer")
    print(f"[*] Target Directory: {target_path}")
    print(f"[*] Patch ZIP: {zip_path}")

    # 1. Wait for caller process to exit
    if caller_pid > 0:
        print(f"[*] Waiting for application (PID {caller_pid}) to close...")
        wait_for_pid(caller_pid, timeout=12.0)
        time.sleep(0.5)

    if not zip_path.is_file():
        print(f"[-] Error: Patch file not found: {zip_path}")
        sys.exit(1)

    # 2. Inspect ZIP contents & create backup
    backup_dir = target_path / "backup" / f"backup_{int(time.time())}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    print(f"[*] Creating rollback backup in: {backup_dir}")

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            namelist = z.namelist()
            print(f"[*] Files to update ({len(namelist)}): {namelist}")

            # Backup existing files that will be overwritten
            for item_name in namelist:
                if item_name.endswith("/") or item_name.endswith("\\"):
                    continue
                dest_file = target_path / item_name
                if dest_file.is_file():
                    backup_dest = backup_dir / item_name
                    backup_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest_file, backup_dest)

            # Extract new files
            print("[*] Extracting update files...")
            for item in z.infolist():
                # Avoid path traversal attacks
                target_file_path = (target_path / item.filename).resolve()
                if not str(target_file_path).startswith(str(target_path)):
                    print(f"[-] Skipping unsafe path: {item.filename}")
                    continue

                if item.is_dir():
                    target_file_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_file_path.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(item) as src, open(target_file_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)

        print("[+] Update files applied successfully!")

        # Remove temp zip
        try:
            zip_path.unlink(missing_ok=True)
        except Exception:
            pass

    except Exception as e:
        print(f"[-] Failed to apply patch: {e}")
        print("[*] Rolling back from backup...")
        for bkp_file in backup_dir.rglob("*"):
            if bkp_file.is_file():
                rel = bkp_file.relative_to(backup_dir)
                restore_dst = target_path / rel
                restore_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bkp_file, restore_dst)
        print("[!] Rollback complete.")
        sys.exit(1)

    # 3. Relaunch application
    if restart_cmd:
        print(f"[*] Relaunching SmartCleaner-AI: {restart_cmd}")
        time.sleep(0.5)
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_CONSOLE

        try:
            subprocess.Popen(restart_cmd, shell=True, cwd=str(target_path), creationflags=creationflags)
        except Exception as e:
            print(f"[-] Failed to relaunch: {e}")

    print("[+] All done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SmartCleaner-AI Patch Applier")
    parser.add_argument("--patch-zip", required=True, help="Path to downloaded patch zip file")
    parser.add_argument("--target-dir", required=True, help="Path to project root directory")
    parser.add_argument("--caller-pid", type=int, default=0, help="PID of the app to wait for")
    parser.add_argument("--restart-cmd", default="", help="Command to restart the application")
    args = parser.parse_args()

    apply_patch(args.patch_zip, args.target_dir, args.caller_pid, args.restart_cmd)
