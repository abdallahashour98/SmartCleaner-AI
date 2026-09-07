"""
SmartCleaner-AI - Modular Auto-Updater Engine
Provides update checking, lightweight differential patch downloading,
and seamless restart via tools/apply_patch.py.
"""

import os
import sys
import json
import time
import hashlib
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import requests
from loguru import logger
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor

BASE_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = BASE_DIR / "version.json"
CONFIG_FILE = BASE_DIR / "gui_config.json"


def load_local_version_info() -> Dict[str, Any]:
    """Reads version.json from the application directory."""
    if not VERSION_FILE.exists():
        return {
            "app_name": "SmartCleaner-AI",
            "version": "1.0.0",
            "channel": "stable",
            "update_manifest_url": "",
            "auto_check_on_startup": True
        }
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {VERSION_FILE}: {e}")
        return {"version": "1.0.0"}


def parse_version_tuple(v_str: str) -> tuple:
    """Converts version string like '1.2.3' or 'v1.2.3' to tuple (1, 2, 3)."""
    cleaned = v_str.strip().lstrip("vV")
    parts = []
    for piece in cleaned.split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_version_newer(current_v: str, remote_v: str) -> bool:
    """Returns True if remote_v is strictly newer than current_v."""
    try:
        return parse_version_tuple(remote_v) > parse_version_tuple(current_v)
    except Exception:
        return False


def fetch_remote_manifest(manifest_url: str, timeout: float = 8.0) -> Tuple[bool, Dict[str, Any], str]:
    """
    Fetches remote version_manifest.json.
    Returns (success, manifest_dict, error_or_message).
    """
    if not manifest_url or not manifest_url.startswith("http") or "username" in manifest_url.lower():
        return False, {}, "أنت تستخدم أحدث إصدار محلي مستقر.\n(سيرفر التحديثات لم يتم ربطه بمستودع خارجي بعد)."

    try:
        resp = requests.get(
            manifest_url,
            headers={
                "User-Agent": "SmartCleaner-AI-Updater",
                "Cache-Control": "no-cache"
            },
            timeout=timeout
        )
        if resp.status_code == 200:
            manifest = resp.json()
            return True, manifest, "تم جلب بيانات التحديث بنجاح."
        elif resp.status_code == 404:
            return False, {}, "أنت تستخدم أحدث إصدار متاح حالياً.\n(لا توجد تحديثات جديدة منشورة على السيرفر)."
        else:
            return False, {}, f"سيرفر التحديثات غير متاح حالياً (رمز الاستجابة {resp.status_code})."
    except Exception as e:
        return False, {}, "تعذر الاتصال بسيرفر التحديثات.\nيرجى التحقق من اتصالك بالإنترنت."


class CheckUpdateWorker(QThread):
    """Asynchronous worker to check for updates without freezing the GUI."""
    result_signal = Signal(bool, dict, str)  # (has_update, manifest, msg)

    def __init__(self, manifest_url: str, current_version: str, parent=None):
        super().__init__(parent)
        self.manifest_url = manifest_url
        self.current_version = current_version

    def run(self):
        ok, manifest, msg = fetch_remote_manifest(self.manifest_url)
        if not ok:
            self.result_signal.emit(False, {}, msg)
            return

        latest_v = manifest.get("latest_version", "")
        if is_version_newer(self.current_version, latest_v):
            self.result_signal.emit(True, manifest, f"يوجد إصدار جديد متاح: v{latest_v}")
        else:
            self.result_signal.emit(False, manifest, "أنت تستخدم أحدث إصدار بالفعل.")


class DownloadPatchWorker(QThread):
    """Asynchronous worker to download the lightweight patch zip."""
    progress_signal = Signal(float, str)  # (percent, detail_msg)
    finished_signal = Signal(bool, str, str)  # (success, saved_zip_path, error_msg)

    def __init__(self, patch_url: str, expected_sha: str = "", parent=None):
        super().__init__(parent)
        self.patch_url = patch_url
        self.expected_sha = (expected_sha or "").lower().strip()
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        temp_dir = Path(tempfile.gettempdir()) / "SmartCleaner_Updates"
        temp_dir.mkdir(parents=True, exist_ok=True)
        dest_zip = temp_dir / f"patch_{int(time.time())}.zip"

        try:
            self.progress_signal.emit(0.05, "جاري الاتصال لتحميل التحديث...")
            resp = requests.get(self.patch_url, stream=True, timeout=30)
            resp.raise_for_status()

            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            hasher = hashlib.sha256()

            with open(dest_zip, "wb") as f:
                for chunk in resp.iter_content(chunk_size=32768):
                    if self._is_cancelled:
                        dest_zip.unlink(missing_ok=True)
                        self.finished_signal.emit(False, "", "تم إلغاء التنزيل بواسطة المستخدم.")
                        return

                    if chunk:
                        f.write(chunk)
                        hasher.update(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = min(0.95, downloaded / total_size)
                            mb_down = round(downloaded / (1024 * 1024), 2)
                            mb_total = round(total_size / (1024 * 1024), 2)
                            self.progress_signal.emit(pct, f"جاري التحميل: {mb_down} MB / {mb_total} MB")

            # Verify SHA256 if provided
            if self.expected_sha:
                calc_sha = hasher.hexdigest().lower()
                if calc_sha != self.expected_sha:
                    dest_zip.unlink(missing_ok=True)
                    self.finished_signal.emit(False, "", "تطابق ملف التحديث غير سليم (SHA256 Mismatch)!")
                    return

            self.progress_signal.emit(1.0, "اكتمل تنزيل حزمة التحديث بنجاح!")
            self.finished_signal.emit(True, str(dest_zip), "")

        except Exception as e:
            if dest_zip.exists():
                dest_zip.unlink(missing_ok=True)
            self.finished_signal.emit(False, "", f"خطأ أثناء التحميل: {str(e)}")


class UpdateDialog(QDialog):
    """Modern Dark-Themed Update Notification & Installation Dialog."""

    def __init__(self, manifest: dict, current_version: str, parent=None):
        super().__init__(parent)
        self.manifest = manifest
        self.current_version = current_version
        self.download_worker: Optional[DownloadPatchWorker] = None

        new_v = manifest.get("latest_version", "New")
        self.setWindowTitle(f"🚀 تحديث جديد متوفر - SmartCleaner-AI v{new_v}")
        self.setMinimumWidth(520)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b1120;
                color: #f1f5f9;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        # Header card
        hdr_frame = QFrame()
        hdr_frame.setStyleSheet("background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 10px;")
        hdr_layout = QVBoxLayout(hdr_frame)
        hdr_layout.setSpacing(6)

        title_lbl = QLabel(f"🎉 يتوفر إصدار جديد من SmartCleaner-AI: v{new_v}")
        title_lbl.setFont(QFont("Segoe UI", 12, QFont.Bold))
        title_lbl.setStyleSheet("color: #38bdf8;")
        hdr_layout.addWidget(title_lbl)

        ver_info = QLabel(f"الإصدار الحالي: v{current_version}  ⬅️  الإصدار الجديد: v{new_v}")
        ver_info.setFont(QFont("Segoe UI", 9))
        ver_info.setStyleSheet("color: #94a3b8;")
        hdr_layout.addWidget(ver_info)

        size_mb = manifest.get("size_mb", 0)
        if size_mb:
            size_lbl = QLabel(f"📦 حجم التحديث الخفيف: {size_mb} MB (تحديث ملفات برمجية فقط بدون إعادة تحميل المكتبات)")
            size_lbl.setStyleSheet("color: #4ade80; font-size: 10px; font-weight: bold;")
            hdr_layout.addWidget(size_lbl)

        layout.addWidget(hdr_frame)

        # Release notes
        notes_title = QLabel("📝 سجل التغييرات والميزات الجديدة (What's New):")
        notes_title.setStyleSheet("color: #cbd5e1; font-weight: 600; font-size: 11px;")
        layout.addWidget(notes_title)

        self.notes_box = QTextEdit()
        self.notes_box.setReadOnly(True)
        self.notes_box.setPlainText(manifest.get("release_notes", "تحسينات عامة وإصلاحات برمجية."))
        self.notes_box.setMaximumHeight(130)
        self.notes_box.setStyleSheet("""
            QTextEdit {
                background: #06090e;
                color: #e2e8f0;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 8px;
                font-size: 11px;
            }
        """)
        layout.addWidget(self.notes_box)

        # Progress bar
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #38bdf8; font-size: 10px; font-weight: bold;")
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border-radius: 8px;
                text-align: center;
                color: white;
                font-size: 9px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
                border-radius: 8px;
            }
        """)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.update_btn = QPushButton("⚡ تحديث وتثبيت الآن")
        self.update_btn.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.update_btn.setMinimumHeight(38)
        self.update_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0ea5e9);
                color: white;
                border: 1px solid #38bdf8;
                border-radius: 6px;
                padding: 4px 16px;
            }
            QPushButton:hover { background: #0369a1; }
        """)
        self.update_btn.clicked.connect(self.start_download)

        self.later_btn = QPushButton("لاحقاً")
        self.later_btn.setMinimumHeight(38)
        self.later_btn.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px 14px;
            }
            QPushButton:hover { background: #334155; color: white; }
        """)
        self.later_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.later_btn)
        btn_layout.addWidget(self.update_btn)
        layout.addLayout(btn_layout)

    def start_download(self):
        patch_url = self.manifest.get("patch_url", "")
        if not patch_url:
            QMessageBox.critical(self, "خطأ", "رابط ملف التحديث غير موجود في المانفيست.")
            return

        self.update_btn.setEnabled(False)
        self.later_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_label.setText("جاري تنزيل التحديث الخفيف...")

        sha = self.manifest.get("sha256", "")
        self.download_worker = DownloadPatchWorker(patch_url, expected_sha=sha, parent=self)
        self.download_worker.progress_signal.connect(self._on_download_progress)
        self.download_worker.finished_signal.connect(self._on_download_finished)
        self.download_worker.start()

    def _on_download_progress(self, percent: float, msg: str):
        self.progress_bar.setValue(int(percent * 100))
        self.progress_label.setText(msg)

    def _on_download_finished(self, success: bool, zip_path: str, err_msg: str):
        if not success:
            QMessageBox.critical(self, "فشل التحديث", f"تعذر إكمال التحديث:\n{err_msg}")
            self.update_btn.setEnabled(True)
            self.later_btn.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.progress_label.setVisible(False)
            return

        # Trigger standalone patch applier and close GUI
        self.progress_label.setText("جاري تطبيق التحديث وإعادة تشغيل التطبيق...")
        time.sleep(0.5)

        apply_script = BASE_DIR / "tools" / "apply_patch.py"
        target_dir = str(BASE_DIR)
        caller_pid = os.getpid()

        # Build restart command
        restart_cmd = f'"{sys.executable}" "{BASE_DIR / "gui_cleaner.py"}"'

        cmd = [
            sys.executable,
            str(apply_script),
            "--patch-zip", zip_path,
            "--target-dir", target_dir,
            "--caller-pid", str(caller_pid),
            "--restart-cmd", restart_cmd
        ]

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS

        try:
            subprocess.Popen(cmd, cwd=str(BASE_DIR), creationflags=creationflags)
            logger.info("Launched apply_patch.py. Exiting main application now.")
            # Close the entire application cleanly
            self.accept()
            os._exit(0)
        except Exception as e:
            QMessageBox.critical(self, "خطأ في التثبيت", f"فشل إطلاق مثبت التحديث:\n{e}")
            self.update_btn.setEnabled(True)
            self.later_btn.setEnabled(True)


def check_for_updates_gui(parent_widget=None, silent: bool = False):
    """
    Checks for updates and displays UpdateDialog if a newer version is available.
    If silent=False, displays a notification when already up to date or on connection failure.
    """
    version_info = load_local_version_info()
    current_version = version_info.get("version", "1.0.0")
    manifest_url = version_info.get("update_manifest_url", "")

    if not manifest_url or "username" in manifest_url.lower():
        if not silent and parent_widget:
            QMessageBox.information(
                parent_widget,
                "التحقق من التحديثات",
                f"أنت تستخدم أحدث إصدار متاح: v{current_version}\n\nالنظام محدث بالكامل ولا توجد تحديثات جديدة حالياً."
            )
        return

    # Create worker
    worker = CheckUpdateWorker(manifest_url, current_version, parent=parent_widget)

    def _on_check_done(has_update: bool, manifest: dict, msg: str):
        if has_update:
            dlg = UpdateDialog(manifest, current_version, parent=parent_widget)
            dlg.exec()
        else:
            if not silent and parent_widget:
                QMessageBox.information(
                    parent_widget,
                    "التحقق من التحديثات",
                    f"الإصدار الحالي: v{current_version}\n\n{msg}"
                )

    worker.result_signal.connect(_on_check_done)
    # Prevent garbage collection of worker
    if parent_widget and hasattr(parent_widget, "_update_worker"):
        parent_widget._update_worker = worker
    worker.start()
