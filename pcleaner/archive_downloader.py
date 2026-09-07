"""
Fast Chapter Archive Downloader & Extractor for FastTypeR
Supports Direct Links (.zip, .rar, .cbz, .7z), Google Drive, Dropbox, Catbox, Mediafire, etc.
Extracts images directly with natural sorting.
"""

import os
import re
import io
import time
import shutil
import zipfile
import urllib.request
from pathlib import Path
from typing import List, Optional

import requests
try:
    from loguru import logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("ArchiveDownloader")


def extract_gdrive_id(url: str) -> Optional[str]:
    """Extracts Google Drive file or folder ID from various URL patterns."""
    if not url:
        return None
    # Clean accidental spaces (which often happen during copy-paste in RTL text fields)
    clean_url = url.strip().replace(" ", "").replace("%20", "")
    patterns = [
        r"/file/d/([a-zA-Z0-9_-]+)",
        r"/folders/([a-zA-Z0-9_-]+)",
        r"id=([a-zA-Z0-9_-]+)",
        r"/open\?id=([a-zA-Z0-9_-]+)",
        r"/d/([a-zA-Z0-9_-]+)",
    ]
    for p in patterns:
        m = re.search(p, clean_url)
        if m:
            return m.group(1)
    return None


def download_file_from_url(url: str, dest_path: Path, progress_cb=None) -> Path:
    """Downloads a file from direct URL, Google Drive, or Dropbox with robust fallbacks."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    clean_url = url.strip()

    # Google Drive handling
    g_id = extract_gdrive_id(clean_url)
    if ("drive.google.com" in clean_url or "docs.google.com" in clean_url) and g_id:
        logger.info(f"Detected Google Drive link. File ID: {g_id}")
        
        # Check if file exists in mounted Google Drive (/content/drive/MyDrive)
        if os.path.exists("/content/drive/MyDrive"):
            for root, _, files in os.walk("/content/drive/MyDrive"):
                for f in files:
                    if g_id in f:
                        found_path = Path(root) / f
                        logger.info(f"Found file directly in mounted Drive: {found_path}")
                        shutil.copy2(found_path, dest_path)
                        return dest_path

        try:
            import gdown
            output = gdown.download(id=g_id, output=str(dest_path), quiet=False, fuzzy=True)
            if output and os.path.exists(output) and os.path.getsize(output) > 1000:
                # Verify it's not an HTML error page
                with open(output, "rb") as check_f:
                    head = check_f.read(300)
                    if b"<html" not in head.lower() and b"<!doctype" not in head.lower():
                        return Path(output)
                    else:
                        logger.warning("gdown downloaded an HTML response page instead of binary archive.")
        except Exception as ge:
            logger.warning(f"gdown download notice ({ge}), trying direct stream...")
        
        clean_url = f"https://drive.google.com/uc?export=download&id={g_id}&confirm=t"

    # Dropbox handling
    if "dropbox.com" in clean_url:
        clean_url = clean_url.replace("dl=0", "dl=1")
        if not clean_url.endswith("dl=1"):
            clean_url += "?dl=1"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }

    logger.info(f"Downloading chapter from URL: {clean_url}")
    session = requests.Session()
    resp = session.get(clean_url, headers=headers, stream=True, timeout=120)
    
    # Handle Google Drive large-file virus scan confirmation page
    if "drive.google.com" in clean_url or "docs.google.com" in clean_url:
        for k, v in resp.cookies.items():
            if k.startswith("download_warning"):
                confirm_url = f"https://drive.google.com/uc?export=download&id={g_id}&confirm={v}"
                logger.info(f"Google Drive large file confirmation token found. Re-requesting: {confirm_url}")
                resp = session.get(confirm_url, headers=headers, stream=True, timeout=120)
                break

    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as he:
        if ("drive.google.com" in clean_url or "drive.usercontent.google.com" in clean_url or (g_id and g_id in clean_url)):
            if resp.status_code == 500:
                raise Exception(
                    "Failed to download Google Drive link (500 Server Error).\n"
                    "📌 Reason: The provided link is a Folder link rather than a direct archive file (.zip / .rar).\n"
                    "💡 Quick Solution: Compress chapter images into a .zip or .rar archive and share its link, or ensure folder permission is 'Anyone with the link'."
                ) from he
            elif resp.status_code in (401, 403):
                raise Exception(
                    "Google Drive link is locked or private (Permission Denied 403).\n"
                    "Please open the link in Google Drive and change sharing permission to 'Anyone with the link'."
                ) from he
            elif resp.status_code == 404:
                raise Exception("Google Drive link not found or was deleted (404 Not Found).") from he
        raise

    total_size = int(resp.headers.get("content-length", 0))
    downloaded = 0

    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total_size > 0:
                    pct = min(99, int((downloaded / total_size) * 100))
                    progress_cb(pct, f"Downloaded {downloaded // 1024} KB / {total_size // 1024} KB")

    # Check if downloaded file is an HTML permission denied error page
    if dest_path.exists():
        with open(dest_path, "rb") as f:
            head = f.read(500).lower()
            if b"<html" in head or b"<!doctype" in head or b"error 404" in head or b"access denied" in head:
                dest_path.unlink(missing_ok=True)
                raise Exception("Google Drive link is locked or private (Permission Denied). Please change sharing permission to 'Anyone with the link'.")

    logger.success(f"Downloaded archive successfully to: {dest_path} ({os.path.getsize(dest_path)//1024} KB)")
    return dest_path


def extract_archive_images(archive_path: Path, dest_dir: Path) -> List[str]:
    """Extracts all image files from a zip/rar/cbz/7z/tar archive into dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    img_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".avif"}
    extracted_images = []

    # 1. Try standard ZipFile (.zip / .cbz)
    try:
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path, 'r') as z:
                for member in z.infolist():
                    if member.is_dir() or member.filename.startswith("__MACOSX"):
                        continue
                    ext = Path(member.filename).suffix.lower()
                    if ext in img_extensions:
                        fname = Path(member.filename).name
                        target = dest_dir / fname
                        with z.open(member) as sf, open(target, "wb") as df:
                            shutil.copyfileobj(sf, df)
                        extracted_images.append(str(target))
            if extracted_images:
                return sort_extracted_images(extracted_images)
    except Exception as ze:
        logger.warning(f"Zip extraction notice: {ze}")

    # 2. Try unar / 7z command line if available (supports RAR, 7Z, TAR, CBZ, CBR)
    import subprocess
    for tool in ["7z", "unar", "unrar"]:
        if shutil.which(tool):
            try:
                temp_extract = dest_dir / "_temp_extract"
                temp_extract.mkdir(parents=True, exist_ok=True)
                if tool == "7z":
                    subprocess.run(["7z", "x", str(archive_path), f"-o{temp_extract}", "-y"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif tool == "unar":
                    subprocess.run(["unar", "-o", str(temp_extract), str(archive_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif tool == "unrar":
                    subprocess.run(["unrar", "x", "-o+", str(archive_path), str(temp_extract)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                for root, _, files in os.walk(temp_extract):
                    for file in files:
                        ext = Path(file).suffix.lower()
                        if ext in img_extensions and not file.startswith("."):
                            src = Path(root) / file
                            target = dest_dir / file
                            shutil.move(str(src), str(target))
                            extracted_images.append(str(target))
                shutil.rmtree(temp_extract, ignore_errors=True)
                if extracted_images:
                    return sort_extracted_images(extracted_images)
            except Exception:
                pass

    # 3. Try shutil.unpack_archive (tar, gztar, zip, etc.)
    try:
        temp_unpack = dest_dir / "_temp_unpack"
        temp_unpack.mkdir(parents=True, exist_ok=True)
        shutil.unpack_archive(str(archive_path), str(temp_unpack))
        for root, _, files in os.walk(temp_unpack):
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in img_extensions and not file.startswith("."):
                    src = Path(root) / file
                    target = dest_dir / file
                    shutil.move(str(src), str(target))
                    extracted_images.append(str(target))
        shutil.rmtree(temp_unpack, ignore_errors=True)
        if extracted_images:
            return sort_extracted_images(extracted_images)
    except Exception:
        pass

    # 4. If the downloaded file is already a direct image
    ext = archive_path.suffix.lower()
    if ext in img_extensions:
        target = dest_dir / archive_path.name
        if str(archive_path) != str(target):
            shutil.copy(str(archive_path), str(target))
        return [str(target)]

    return sort_extracted_images(extracted_images)


def sort_extracted_images(image_paths: List[str]) -> List[str]:
    """Sorts image paths naturally (page 1, 2, ... 10)."""
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', Path(s).name)]
    return sorted(image_paths, key=natural_sort_key)


def download_and_extract_chapter(url: str, extract_to_dir: Path, progress_cb=None) -> List[str]:
    """Downloads a chapter archive or Google Drive folder and extracts all images."""
    clean_url = url.strip()
    extract_to_dir.mkdir(parents=True, exist_ok=True)
    img_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".avif"}

    # 1. Google Drive Folder handling (/drive/folders/...)
    is_gdrive_folder = ("drive.google.com" in clean_url or "docs.google.com" in clean_url) and ("/folders/" in clean_url)
    g_id = extract_gdrive_id(clean_url)

    if is_gdrive_folder and g_id:
        logger.info(f"Detected Google Drive Folder ID: {g_id}. Downloading folder contents...")
        
        # Method A: Try gdown with folder URL
        try:
            import gdown
            folder_url = f"https://drive.google.com/drive/folders/{g_id}"
            gdown.download_folder(url=folder_url, output=str(extract_to_dir), quiet=False, remaining_ok=True)
        except Exception as fe1:
            logger.warning(f"gdown download_folder by url notice: {fe1}")
            try:
                # Method B: Try gdown with folder ID
                import gdown
                gdown.download_folder(id=g_id, output=str(extract_to_dir), quiet=False, remaining_ok=True)
            except Exception as fe2:
                logger.warning(f"gdown download_folder by id notice: {fe2}")

        extracted_images = []
        for root, _, files in os.walk(extract_to_dir):
            for f in files:
                if Path(f).suffix.lower() in img_extensions and not f.startswith("."):
                    extracted_images.append(str(Path(root) / f))

        if extracted_images:
            logger.info(f"Successfully downloaded {len(extracted_images)} images from Google Drive folder.")
            return sort_extracted_images(extracted_images)
        else:
            raise Exception(
                f"Could not download Google Drive folder contents (ID: {g_id}).\n"
                "📌 Common Cause: The folder is private or requires authentication.\n"
                "💡 Recommended Solutions:\n"
                "1. Best & Fastest: Compress chapter images into a (.zip / .rar) archive and share the archive link.\n"
                "2. Or open the folder in Google Drive and set sharing permission to 'Anyone with the link'."
            )

    # 2. Direct File / Archive (.zip, .rar, .cbz) / Single Drive File
    temp_archive = extract_to_dir.parent / f"downloaded_chapter_{int(time.time())}.zip"
    try:
        download_file_from_url(clean_url, temp_archive, progress_cb=progress_cb)
        images = extract_archive_images(temp_archive, extract_to_dir)
        logger.info(f"Extracted {len(images)} manga pages from downloaded archive.")
        return images
    finally:
        if temp_archive.exists():
            try:
                temp_archive.unlink()
            except Exception:
                pass
