"""
SmartCleaner-AI Studio - Dedicated Multi-Page Manga & Webtoon Inpainting & Cleaning Studio

Features:
1. Deep Learning Speech Bubble Detection (YOLOv8 + ComicTextDetector).
2. Smart Adaptive Inpainting (Instant White-Fill in <0.005s + Deep AI inpainting with IOPaint).
3. Interactive Canvas: Magic Wand (W), Freehand Brush Mask (B), Box Tool (A), and Revert (R).
4. Live 1-Key Toggle (Space / Tab) between Cleaned and Original pages.
5. Batch Inpainting & Export for entire chapters/volumes.
6. Support for local IOPaint and remote Google Colab GPU servers.

Usage:
    py -3.10 gui_cleaner.py
"""

import sys
import os
import json
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QTextEdit,
    QProgressBar, QMessageBox, QFrame, QCheckBox, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QGraphicsRectItem, QGraphicsPolygonItem, QGraphicsPathItem, QGraphicsItemGroup, QGraphicsSimpleTextItem,
    QListWidget, QListWidgetItem, QStackedWidget,
    QRadioButton, QButtonGroup, QInputDialog, QSpinBox, QSlider, QSizePolicy,
    QMenu, QAbstractItemView, QPlainTextEdit, QProgressDialog, QComboBox,
    QScrollArea, QGroupBox
)
from PySide6.QtCore import Qt, QThread, Signal, QRectF, QSize, QBuffer, QEvent, QPoint, QPointF, QTimer, QEventLoop, QUrl
from PySide6.QtGui import (
    QShortcut,
    QFont, QColor, QPixmap, QPen, QBrush, QIcon, QPainter, QImage,
    QPainterPath, QPainterPathStroker, QTextCursor, QKeySequence, QKeyEvent, QPolygonF,
    QDesktopServices
)

import webbrowser
import tempfile
import shutil
import re
import io
import uuid
import zipfile
import tarfile
import cv2
import numpy as np

# Add current dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Unicode-safe image loader without importing heavy libraries
def read_image_unicode(path: str) -> np.ndarray:
    """Read image safely from Unicode/Arabic file path using cv2.imdecode."""
    with open(path, "rb") as f:
        bytes_data = f.read()
    return cv2.imdecode(np.frombuffer(bytes_data, np.uint8), cv2.IMREAD_COLOR)

from pcleaner.iopaint_client import (
    IOPaintClient, SUPPORTED_IOPAINT_MODELS, generate_page_mask,
    inpaint_manga_page, inpaint_single_bubble, smart_adaptive_inpaint_page,
    classify_bubble_background, generate_bubble_lasso_polygons,
    clean_flat_bubble_locally
)
from pcleaner.ngrok_manager import (
    get_local_ip,
    get_active_ngrok_url,
    start_ngrok_tunnel,
    stop_ngrok,
    stop_server_and_ngrok,
    configure_ngrok_authtoken,
    is_server_online,
    generate_qr_code_image,
    download_and_install_ngrok,
    setup_and_activate_ngrok_service
)
from pcleaner.updater import check_for_updates_gui, load_local_version_info


ARCHIVE_EXTENSIONS = {".zip", ".cbz", ".rar", ".cbr", ".7z", ".cb7", ".tar", ".gz", ".tgz", ".bz2", ".xz"}
VALID_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def natural_sort_key(s):
    """Sort strings with numbers naturally (1, 2, 10 instead of 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]


def extract_archive_if_needed(file_or_dir_path: str, progress_callback=None) -> list:
    """
    Extracts archive (.zip, .cbz, .rar, etc.) to temporary directory or scans folders.
    Returns naturally sorted list of image file paths.
    """
    p = Path(file_or_dir_path)
    if not p.exists():
        return []

    if p.is_dir():
        imgs = [str(f) for f in p.rglob("*") if f.suffix.lower() in VALID_IMAGE_EXTENSIONS]
        imgs.sort(key=natural_sort_key)
        return imgs

    ext = p.suffix.lower()
    if ext in VALID_IMAGE_EXTENSIONS:
        return [str(p)]

    if ext in ARCHIVE_EXTENSIONS:
        if progress_callback:
            progress_callback(f"📦 Extracting compressed archive: {p.name}...")
        
        temp_base = Path(tempfile.gettempdir()) / "SmartCleaner-AI_Archives"
        temp_dir = temp_base / p.stem
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        if ext in (".zip", ".cbz"):
            with zipfile.ZipFile(p, "r") as z:
                z.extractall(temp_dir)
        elif ext in (".tar", ".tar.gz", ".tgz", ".cbt"):
            with tarfile.open(p, "r:*") as t:
                t.extractall(temp_dir)
        else:
            import subprocess
            try:
                subprocess.run(["tar", "-xf", str(p), "-C", str(temp_dir)], check=True, capture_output=True)
            except Exception as e:
                print(f"Archive extraction failed: {e}")

        found_imgs = [str(f) for f in temp_dir.rglob("*") if f.suffix.lower() in VALID_IMAGE_EXTENSIONS]
        found_imgs.sort(key=natural_sort_key)
        return found_imgs

    return []


DARK_NAVY_STYLESHEET = """
QMainWindow, QDialog {
    background-color: #080c14;
    color: #e2e8f0;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
}
QFrame.card-frame {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 12px;
}
QLabel {
    color: #94a3b8;
    font-size: 12px;
}
QLabel.section-header {
    color: #38bdf8;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.3px;
}
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #090d16;
    border: 1px solid #1e293b;
    color: #f8fafc;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
    selection-background-color: #0284c7;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #38bdf8;
    background-color: #0d1527;
}
QListWidget {
    background-color: #090d16;
    border: 1px solid #1e293b;
    color: #f1f5f9;
    border-radius: 8px;
    padding: 4px;
    font-size: 12px;
    outline: none;
}
QListWidget:focus {
    border: 1px solid #0284c7;
}
QListWidget::item {
    padding: 8px 10px;
    border-radius: 6px;
    margin-bottom: 3px;
    border: 1px solid transparent;
}
QListWidget::item:hover {
    background-color: #1e293b;
    color: #38bdf8;
    border: 1px solid #334155;
}
QListWidget::item:selected {
    background-color: #0284c7;
    color: #ffffff;
    font-weight: bold;
    border: 1px solid #38bdf8;
}
QSpinBox {
    background-color: #090d16;
    border: 1px solid #1e293b;
    color: #f1f5f9;
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 12px;
}
QSpinBox:focus {
    border: 1px solid #38bdf8;
}
QComboBox {
    background-color: #090d16;
    border: 1px solid #1e293b;
    color: #f1f5f9;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
}
QComboBox:focus {
    border: 1px solid #38bdf8;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    color: #f1f5f9;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
    border-radius: 6px;
    padding: 4px;
}
QPushButton {
    background-color: #1e293b;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #334155;
    color: #38bdf8;
    border-color: #0284c7;
}
QPushButton:pressed {
    background-color: #0f172a;
}
QPushButton:disabled {
    background-color: #0b0f19;
    color: #475569;
    border-color: #1e293b;
}
QProgressBar {
    border: 1px solid #1e293b;
    border-radius: 6px;
    background-color: #090d16;
    height: 18px;
    text-align: center;
    color: #f8fafc;
    font-weight: bold;
    font-size: 11px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
    border-radius: 5px;
}
QTableWidget {
    background-color: #090d16;
    gridline-color: #1e293b;
    color: #e2e8f0;
    border: 1px solid #1e293b;
    border-radius: 8px;
    font-size: 12px;
    outline: none;
}
QTableWidget::item {
    padding: 6px;
    border-bottom: 1px solid #141d2e;
}
QTableWidget::item:hover {
    background-color: #131d31;
}
QTableWidget::item:selected {
    background-color: #0c2d48;
    color: #38bdf8;
}
QHeaderView::section {
    background-color: #0f172a;
    color: #38bdf8;
    padding: 8px;
    font-weight: bold;
    border: 1px solid #1e293b;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
QRadioButton {
    color: #cbd5e1;
    font-size: 12px;
    spacing: 8px;
}
QRadioButton:hover {
    color: #f8fafc;
}
QRadioButton::indicator {
    width: 18px;
    height: 18px;
    border-radius: 10px;
    border: 2px solid #475569;
    background-color: #090d16;
}
QRadioButton::indicator:hover {
    border-color: #38bdf8;
    background-color: #0f172a;
}
QRadioButton::indicator:checked {
    border: 2px solid #38bdf8;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #38bdf8, stop:0.55 #0284c7, stop:0.65 #090d16, stop:1 #090d16);
}
QRadioButton:checked {
    color: #38bdf8;
    font-weight: 600;
}
QCheckBox {
    color: #cbd5e1;
    font-size: 12px;
    spacing: 8px;
}
QCheckBox:hover {
    color: #f8fafc;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #334155;
    background-color: #090d16;
}
QCheckBox::indicator:hover {
    border-color: #38bdf8;
    background-color: #0f172a;
}
QCheckBox::indicator:checked {
    background-color: #0284c7;
    border-color: #38bdf8;
}
QCheckBox:checked {
    color: #f1f5f9;
}
QSplitter::handle:horizontal {
    background-color: #1e293b;
    width: 6px;
    margin: 4px 0px;
    border-radius: 3px;
}
QSplitter::handle:horizontal:hover {
    background-color: #38bdf8;
}
QScrollBar:vertical {
    border: none;
    background: #080c14;
    width: 8px;
    border-radius: 4px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #334155;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #475569;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    border: none;
    background: #080c14;
    height: 8px;
    border-radius: 4px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #334155;
    min-width: 24px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #475569;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QMenu {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 6px;
    color: #e2e8f0;
}
QMenu::item {
    padding: 8px 24px 8px 14px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
}
QMenu::item:hover, QMenu::item:selected {
    background-color: #0284c7;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background-color: #1e293b;
    margin: 4px 6px;
}
"""

SHORTCUT_ACTION_DEFINITIONS = [
    ("toggle_cleaned", "✨ Toggle Original / Cleaned View", "Space"),
    ("toggle_masks", "👁️ Show / Hide Bubble Masks", "M"),
    ("magic_wand", "🪄 Magic Wand Tool", "W"),
    ("brush_tool", "🖌️ Freehand Brush Tool", "B"),
    ("lasso_tool", "🪢 Freehand Lasso Tool", "L"),
    ("pan_tool", "✋ Hand / Pan Tool", "H"),
    ("draw_box", "🔲 Add / Draw Box Tool", "A"),
    ("delete_bubble", "🗑️ Delete Selected Bubble", "Delete"),
    ("inpaint_bubble", "🧹 Inpaint Selected Bubble", "Ctrl+I"),
    ("inpaint_page", "🧹 Inpaint Full Page", "C"),
    ("next_bubble", "⬇️ Next Bubble (Select Down)", "Down"),
    ("prev_bubble", "⬆️ Previous Bubble (Select Up)", "Up"),
    ("next_page", "📄 Next Page", "Right"),
    ("prev_page", "📄 Previous Page", "Left"),
    ("zoom_in", "➕ Zoom In", "+"),
    ("zoom_out", "➖ Zoom Out", "-"),
    ("fit_view", "🔍 Fit Screen", "F"),
    ("zoom_100", "⬛ 100% Size", "1"),
    ("export_image", "🖼️ Export Active Image", "Ctrl+E"),
    ("export_all", "📦 Export Chapter Images", "Ctrl+Shift+E"),
    ("save_project", "💾 Save Project (.cln)", "Ctrl+S"),
]

DEFAULT_SHORTCUTS = {k: def_k for k, _, def_k in SHORTCUT_ACTION_DEFINITIONS}


class IOPaintPingWorker(QThread):
    status_signal = Signal(bool, str, list)

    def __init__(self, server_url: str, parent=None):
        super().__init__(parent)
        self.server_url = server_url

    def run(self):
        try:
            client = IOPaintClient(self.server_url)
            is_online, model_name = client.check_connection()
            available_models = []
            if is_online:
                available_models = client.get_available_models(self.server_url)
            self.status_signal.emit(is_online, model_name, available_models)
        except Exception as e:
            self.status_signal.emit(False, str(e), [])


class IOPaintStartupWaiterWorker(QThread):
    progress_signal = Signal(int, str)
    finished_signal = Signal(bool, str)

    def __init__(self, server_url: str, max_wait_sec: int = 60, parent=None):
        super().__init__(parent)
        self.server_url = server_url
        self.max_wait_sec = max_wait_sec
        self._is_canceled = False

    def cancel(self):
        self._is_canceled = True

    def run(self):
        start_t = time.time()
        client = IOPaintClient(self.server_url)
        while not self._is_canceled:
            elapsed = int(time.time() - start_t)
            pct = min(95, int((elapsed / self.max_wait_sec) * 100))
            self.progress_signal.emit(pct, f"⏳ Starting IOPaint Server & loading model into memory ({elapsed}s)...")
            
            try:
                ok, model = client.check_connection()
                if ok:
                    self.progress_signal.emit(100, "🎉 IOPaint Server is online and ready!")
                    self.finished_signal.emit(True, model or "Ready")
                    return
            except Exception:
                pass

            if elapsed >= self.max_wait_sec:
                self.finished_signal.emit(False, "Server took longer than expected.")
                return

            time.sleep(1.0)

        self.finished_signal.emit(False, "Canceled by user.")


class IOPaintSwitchModelWorker(QThread):
    finished_signal = Signal(bool, str, str)

    def __init__(self, server_url: str, new_model: str, parent=None):
        super().__init__(parent)
        self.server_url = server_url
        self.new_model = new_model

    def run(self):
        try:
            client = IOPaintClient(self.server_url)
            ok, msg = client.switch_model(self.new_model)
            self.finished_signal.emit(ok, self.new_model, msg)
        except Exception as e:
            self.finished_signal.emit(False, self.new_model, str(e))


_ACTIVE_BACKGROUND_WORKERS = set()

def track_running_worker(worker: QThread):
    """
    Keeps a persistent reference to a running QThread so that neither Python GC
    nor Qt parent destruction can destroy the QThread while it is still executing.
    Automatically cleans up when finished.
    """
    if worker:
        _ACTIVE_BACKGROUND_WORKERS.add(worker)
        def _on_finished():
            _ACTIVE_BACKGROUND_WORKERS.discard(worker)
        try:
            worker.finished.connect(_on_finished)
        except Exception:
            pass
    return worker


class PageInpaintWorker(QThread):
    finished_signal = Signal(bool, str, str)  # success, cleaned_image_path, error_msg

    def __init__(self, image_path: str, bubbles: list, server_url: str = "http://127.0.0.1:8080", model: str = "anime-lama", dilation: int = 5, padding: int = 0, adaptive_mode: bool = True, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.bubbles = bubbles
        self.server_url = server_url or "http://127.0.0.1:8080"
        self.model = model
        self.dilation = dilation
        self.padding = padding
        self.adaptive_mode = adaptive_mode
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            from PIL import Image
            for b in self.bubbles:
                if self.padding > 0:
                    b["mask_padding"] = max(b.get("mask_padding", 0), self.padding)

            eff_dil = max(self.dilation, self.padding)
            if self.adaptive_mode:
                cleaned_img, _ = smart_adaptive_inpaint_page(
                    server_url=self.server_url,
                    image_input=self.image_path,
                    bubbles=self.bubbles,
                    deep_model=self.model,
                    dilation=eff_dil,
                    padding=self.padding
                )
            else:
                cleaned_img = inpaint_manga_page(
                    server_url=self.server_url,
                    image_input=self.image_path,
                    bubbles=self.bubbles,
                    dilation=eff_dil,
                    padding=self.padding,
                    adaptive=False,
                    deep_model=self.model
                )

            stem = Path(self.image_path).stem
            ext = Path(self.image_path).suffix or ".png"
            cleaned_path = str(Path(self.image_path).parent / f"{stem}_clean{ext}")
            cleaned_img.save(cleaned_path, quality=95)

            for b in self.bubbles:
                b['status'] = 'cleaned'

            if not self._is_cancelled:
                self.finished_signal.emit(True, cleaned_path, "")
        except Exception as e:
            if not self._is_cancelled:
                self.finished_signal.emit(False, "", str(e))


class SingleBubbleInpaintWorker(QThread):
    finished_signal = Signal(bool, int, str, str)  # success, bubble_idx, cleaned_image_path, error_msg

    def __init__(self, current_img_path: str, bubble_dict: dict, bubble_idx: int, server_url: str = "http://127.0.0.1:8080", model: str = "anime-lama", dilation: int = 5, parent=None):
        super().__init__(parent)
        self.current_img_path = current_img_path
        self.bubble_dict = bubble_dict
        self.bubble_idx = bubble_idx
        self.server_url = server_url or "http://127.0.0.1:8080"
        self.model = model
        self.dilation = dilation
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            from PIL import Image
            pil_page = Image.open(self.current_img_path).convert("RGB")
            cleaned_pil = inpaint_single_bubble(
                server_url=self.server_url,
                base_page_pil=pil_page,
                bubble=self.bubble_dict,
                dilation=self.dilation,
                adaptive=True,
                model=self.model
            )
            stem = Path(self.current_img_path).stem.replace("_clean", "")
            ext = Path(self.current_img_path).suffix or ".png"
            out_path = str(Path(self.current_img_path).parent / f"{stem}_clean{ext}")
            cleaned_pil.save(out_path, quality=95)
            if not self._is_cancelled:
                self.finished_signal.emit(True, self.bubble_idx, out_path, "")
        except Exception as e:
            if not self._is_cancelled:
                self.finished_signal.emit(False, self.bubble_idx, "", str(e))


class BatchPageInpaintWorker(QThread):
    progress_signal = Signal(int, int, str)
    finished_signal = Signal(dict)

    def __init__(self, pages_dict: dict, server_url: str = "http://127.0.0.1:8080", model: str = "anime-lama", dilation: int = 5, padding: int = 0, adaptive_mode: bool = True, parent=None):
        super().__init__(parent)
        self.pages_dict = pages_dict
        self.server_url = server_url
        self.model = model
        self.dilation = dilation
        self.padding = padding
        self.adaptive_mode = adaptive_mode
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        client = IOPaintClient(self.server_url)
        results = {}
        total = len(self.pages_dict)

        for idx, (img_path, bubbles) in enumerate(self.pages_dict.items()):
            if self._is_cancelled:
                break
            p_name = Path(img_path).name
            self.progress_signal.emit(idx, total, f"Cleaning page {idx+1}/{total}: {p_name} ({len(bubbles)} bubbles)...")

            try:
                from PIL import Image
                eff_dil = max(self.dilation, self.padding)
                for b in bubbles:
                    if self.padding > 0:
                        b["mask_padding"] = max(b.get("mask_padding", 0), self.padding)

                if self.adaptive_mode:
                    cleaned_img, _ = smart_adaptive_inpaint_page(
                        server_url=self.server_url,
                        image_input=img_path,
                        bubbles=bubbles,
                        deep_model=self.model,
                        dilation=eff_dil,
                        padding=self.padding
                    )
                else:
                    cleaned_img = inpaint_manga_page(
                        server_url=self.server_url,
                        image_input=img_path,
                        bubbles=bubbles,
                        dilation=eff_dil,
                        padding=self.padding,
                        adaptive=False,
                        deep_model=self.model
                    )

                stem = Path(img_path).stem
                ext = Path(img_path).suffix or ".png"
                out_path = str(Path(img_path).parent / f"{stem}_clean{ext}")
                cleaned_img.save(out_path, quality=95)
                results[img_path] = out_path

                for b in bubbles:
                    b['status'] = 'cleaned'
            except Exception as e:
                print(f"Error cleaning {p_name}: {e}")

        self.finished_signal.emit(results)


class KeyRecorderButton(QPushButton):
    key_recorded = Signal(str)

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.recording = False
        self.setCheckable(True)
        self.clicked.connect(self._on_click)

    def _on_click(self):
        self.recording = True
        self.setText("Press any key...")
        self.setStyleSheet("background: #0284c7; color: white; font-weight: bold; border: 1px solid #38bdf8;")

    def keyPressEvent(self, event: QKeyEvent):
        if not self.recording:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return

        seq = QKeySequence(event.modifiers() | key)
        key_str = seq.toString(QKeySequence.NativeText)

        if key_str == " ":
            key_str = "Space"

        self.recording = False
        self.setChecked(False)
        self.setText(key_str)
        self.setStyleSheet("")
        self.key_recorded.emit(key_str)


class ShortcutsSettingsDialog(QDialog):
    """
    Modern Dialog allowing full customization of all Keyboard Shortcuts in SmartCleaner-AI.
    """
    def __init__(self, current_shortcuts: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ SmartCleaner-AI - Keyboard Shortcuts Settings")
        self.resize(580, 600)
        self.setStyleSheet(DARK_NAVY_STYLESHEET)
        self.shortcuts = dict(DEFAULT_SHORTCUTS)
        if current_shortcuts:
            self.shortcuts.update(current_shortcuts)
        
        self.recorders = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("⌨️ Customize Studio Keyboard Shortcuts")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet("color: #38bdf8;")
        layout.addWidget(title)

        desc = QLabel("Click any shortcut button and press the desired key or combination (e.g. Space, W, B, L, A, Delete, Ctrl+S).")
        desc.setFont(QFont("Segoe UI", 10))
        desc.setStyleSheet("color: #94a3b8;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Action", "Current Shortcut", "Clear"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setRowCount(len(SHORTCUT_ACTION_DEFINITIONS))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)

        for row, (act_key, act_label, def_key) in enumerate(SHORTCUT_ACTION_DEFINITIONS):
            item_label = QTableWidgetItem(act_label)
            item_label.setFont(QFont("Segoe UI", 10))
            self.table.setItem(row, 0, item_label)

            cur_k = self.shortcuts.get(act_key, def_key)
            rec_btn = KeyRecorderButton(cur_k)
            rec_btn.key_recorded.connect(lambda k, k_act=act_key: self.on_key_updated(k_act, k))
            self.recorders[act_key] = rec_btn
            self.table.setCellWidget(row, 1, rec_btn)

            clear_btn = QPushButton("✖")
            clear_btn.setFixedWidth(32)
            clear_btn.setFixedHeight(28)
            clear_btn.setStyleSheet("background: #1e293b; color: #f87171; font-weight: bold; border-radius: 4px; border: 1px solid #dc2626;")
            clear_btn.clicked.connect(lambda _, k_act=act_key: self.clear_shortcut(k_act))
            self.table.setCellWidget(row, 2, clear_btn)

            self.table.setRowHeight(row, 40)

        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("🔄 Reset Defaults")
        reset_btn.setStyleSheet("background: #1e293b; color: #fbbf24; border: 1px solid #d97706; padding: 6px 14px; border-radius: 6px;")
        reset_btn.clicked.connect(self.reset_defaults)
        btn_row.addWidget(reset_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background: #1e293b; color: #cbd5e1; border: 1px solid #475569; padding: 6px 14px; border-radius: 6px;")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("💾 Save Shortcuts")
        save_btn.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 6px 18px; border-radius: 6px;")
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def on_key_updated(self, act_key: str, new_key: str):
        self.shortcuts[act_key] = new_key

    def clear_shortcut(self, act_key: str):
        self.shortcuts[act_key] = ""
        if act_key in self.recorders:
            self.recorders[act_key].setText("None")

    def reset_defaults(self):
        self.shortcuts = dict(DEFAULT_SHORTCUTS)
        for act_key, _, def_k in SHORTCUT_ACTION_DEFINITIONS:
            if act_key in self.recorders:
                self.recorders[act_key].setText(def_k)

    def get_shortcuts(self) -> dict:
        return self.shortcuts


DEVELOPER_DISCORD_ID = "700498157821231144"
DEVELOPER_DISCORD_URL = f"https://discord.com/users/{DEVELOPER_DISCORD_ID}"


class DiscordContactDialog(QDialog):
    """Dialog displaying developer's Discord info, opening Discord profile, and copying ID."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("التواصل مع المبرمج - Discord")
        self.setFixedWidth(460)
        self.setStyleSheet(DARK_NAVY_STYLESHEET)

        # Automatically copy ID to clipboard and attempt to open Discord
        try:
            QApplication.clipboard().setText(DEVELOPER_DISCORD_ID)
        except Exception:
            pass

        try:
            QDesktopServices.openUrl(QUrl(DEVELOPER_DISCORD_URL))
            webbrowser.open(DEVELOPER_DISCORD_URL)
        except Exception:
            pass

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(22, 22, 22, 22)

        hdr = QLabel("💬 التواصل مع المبرمج عبر ديسكورد")
        hdr.setFont(QFont("Segoe UI", 14, QFont.Bold))
        hdr.setStyleSheet("color: #5865F2;")  # Discord Blurple
        layout.addWidget(hdr)

        info_lbl = QLabel(
            "تم فتح صفحة حساب المبرمج على Discord في المتصفح تلقائياً.\n"
            "يمكنك أيضاً إضافة المبرمج كصديق أو إرسال رسالة مباشرة باستخدام المعرف التالي:"
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: #cbd5e1; font-size: 12px; line-height: 1.4;")
        layout.addWidget(info_lbl)

        id_card = QFrame()
        id_card.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #5865F2;
                border-radius: 10px;
                padding: 12px;
            }
        """)
        id_layout = QVBoxLayout(id_card)
        id_layout.setSpacing(8)

        id_title = QLabel("🎮 Discord User ID:")
        id_title.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold;")
        id_layout.addWidget(id_title)

        self.id_box = QLineEdit(DEVELOPER_DISCORD_ID)
        self.id_box.setReadOnly(True)
        self.id_box.setAlignment(Qt.AlignCenter)
        self.id_box.setFont(QFont("Consolas", 14, QFont.Bold))
        self.id_box.setStyleSheet("""
            QLineEdit {
                background-color: #090d16;
                color: #5865F2;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px;
                letter-spacing: 1px;
            }
        """)
        id_layout.addWidget(self.id_box)

        self.status_lbl = QLabel("✅ تم نسخ الآيدي إلى الحافظة تلقائياً!")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setStyleSheet("color: #22c55e; font-size: 11px; font-weight: 600;")
        id_layout.addWidget(self.status_lbl)

        layout.addWidget(id_card)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        copy_btn = QPushButton("📋 نسخ الآيدي")
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #334155; color: #38bdf8; border-color: #0284c7; }
        """)
        copy_btn.clicked.connect(self._copy_id)
        btn_row.addWidget(copy_btn)

        open_web_btn = QPushButton("🌐 فتح الرابط")
        open_web_btn.setStyleSheet("""
            QPushButton {
                background-color: #5865F2;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4752c4; }
        """)
        open_web_btn.clicked.connect(self._open_url)
        btn_row.addWidget(open_web_btn)

        close_btn = QPushButton("إغلاق")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #090d16;
                color: #94a3b8;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 8px 14px;
            }
            QPushButton:hover { background-color: #1e293b; color: #f8fafc; }
        """)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _copy_id(self):
        try:
            QApplication.clipboard().setText(DEVELOPER_DISCORD_ID)
            self.status_lbl.setText("✅ تم نسخ الآيدي مجدداً!")
            self.status_lbl.setStyleSheet("color: #22c55e; font-size: 11px; font-weight: 600;")
        except Exception:
            pass

    def _open_url(self):
        try:
            QDesktopServices.openUrl(QUrl(DEVELOPER_DISCORD_URL))
            webbrowser.open(DEVELOPER_DISCORD_URL)
        except Exception:
            pass


class AboutAppDialog(QDialog):
    """Dialog showing application and version information."""
    def __init__(self, version: str = "1.0.0", parent=None):
        super().__init__(parent)
        self.setWindowTitle("معلومات البرنامج والإصدار")
        self.setFixedWidth(460)
        self.setStyleSheet(DARK_NAVY_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(22, 22, 22, 22)

        hdr_row = QHBoxLayout()
        hdr_lbl = QLabel("⚡ SmartCleaner-AI")
        hdr_lbl.setFont(QFont("Segoe UI", 15, QFont.Bold))
        hdr_lbl.setStyleSheet("color: #38bdf8;")

        ver_badge = QLabel(f"v{version}")
        ver_badge.setStyleSheet("background: #0284c7; color: white; border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: bold;")

        hdr_row.addWidget(hdr_lbl)
        hdr_row.addWidget(ver_badge)
        hdr_row.addStretch()
        layout.addLayout(hdr_row)

        desc_lbl = QLabel(
            "الاستوديو المتكامل لتنظيف وتبييض صفحات المانجا والكوميكس والويب تون "
            "باستخدام الذكاء الاصطناعي ونماذج كشف الفقاعات المتقدمة (YOLOv8 + ComicTextDetector) "
            "والترميم الذكي (IOPaint + Fast White-Fill)."
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.5;")
        layout.addWidget(desc_lbl)

        info_card = QFrame()
        info_card.setStyleSheet("""
            QFrame {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        ic_layout = QVBoxLayout(info_card)
        ic_layout.setSpacing(6)

        ic_v = QLabel(f"• الإصدار الحالي: v{version} (مستقر)")
        ic_v.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        ic_layout.addWidget(ic_v)

        ic_dev = QLabel(f"• ديسكورد المبرمج: {DEVELOPER_DISCORD_ID}")
        ic_dev.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        ic_layout.addWidget(ic_dev)

        ic_update = QLabel("• التحديثات: مدعومة بنظام باتشات خفيف وتلقائي")
        ic_update.setStyleSheet("color: #e2e8f0; font-size: 11px;")
        ic_layout.addWidget(ic_update)

        layout.addWidget(info_card)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        contact_btn = QPushButton("💬 تواصل مع المبرمج")
        contact_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #5865F2;
                border: 1px solid #5865F2;
                border-radius: 6px;
                padding: 7px 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #5865F2; color: white; }
        """)
        contact_btn.clicked.connect(self._open_contact)
        btn_row.addWidget(contact_btn)

        check_btn = QPushButton("🔄 فحص التحديثات")
        check_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f172a;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 6px;
                padding: 7px 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #0284c7; color: white; }
        """)
        check_btn.clicked.connect(self._check_updates)
        btn_row.addWidget(check_btn)

        close_btn = QPushButton("إغلاق")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #090d16;
                color: #94a3b8;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 7px 14px;
            }
            QPushButton:hover { background-color: #1e293b; color: #f8fafc; }
        """)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    def _open_contact(self):
        self.accept()
        dlg = DiscordContactDialog(parent=self.parent())
        dlg.exec()

    def _check_updates(self):
        self.accept()
        check_for_updates_gui(parent_widget=self.parent(), silent=False)


class PageViewerWidget(QGraphicsView):
    """
    Full manga page image viewer supporting:
    - High-quality Antialiased & Smooth Pixmap Transform
    - Bounding Box Highlights with Glowing Neon active outline
    - Interactive Zoom In (+), Zoom Out (-), Fit Screen (F), 100% Zoom (1), and Mouse Wheel Zooming / Scrolling
    - Silky Smooth Click-to-drag Panning (Hand Drag)
    - Real-time Hover tracking & click bubble to emit selection signal
    - Draw mode: click & drag to draw a new bubble rectangle (A)
    - Magic Wand mode (W): click inside any speech bubble to auto-detect bounds
    - Freehand Brush Tool (B): Paint red mask freely on SFX/text
    - Freehand Lasso Tool (L): Draw freehand polygon around text
    """
    bubble_clicked_signal = Signal(int)
    new_bubble_drawn_signal = Signal(int, int, int, int)
    magic_wand_clicked_signal = Signal(int, int)
    brush_mask_applied_signal = Signal(int, int, int, int, list)
    lasso_drawn_signal = Signal(int, int, int, int, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setStyleSheet("""
            QGraphicsView {
                border: 1px solid #1e293b;
                border-radius: 10px;
                background-color: #06090f;
            }
        """)

        self.pixmap_item = None
        self.rect_items = []
        self.bubbles = []
        self.selected_idx = -1
        self.hover_idx = -1
        self._target_badge_group = None
        self._target_badge_items = []

        self._draw_mode = False
        self._wand_mode = False
        self._brush_mode = False
        self._lasso_mode = False
        self._brush_size = 24

        self._draw_start = None
        self._press_pos = None
        self._is_dragging = False
        self._is_panning = False
        self._pan_start = None
        self._draw_preview_rect = None
        self._brush_path_item = None
        self._current_brush_path = None
        self._current_lasso_path = None
        self._lasso_path_item = None
        self._lasso_points = []
        self._overlays_visible = True

    def load_page(self, image_path: str, bubbles: list, maintain_view: bool = False):
        if maintain_view:
            transform = self.transform()
            h_scroll = self.horizontalScrollBar().value()
            v_scroll = self.verticalScrollBar().value()

        self.scene.clear()
        self.rect_items = []
        self.bubbles = list(bubbles) if bubbles else []
        self.selected_idx = -1
        self.hover_idx = -1
        self._draw_preview_rect = None
        self._brush_path_item = None
        self._target_badge_group = None
        self._target_badge_items = []
        self._draw_start = None
        self._press_pos = None
        self._is_dragging = False
        self._is_panning = False
        self._pan_start = None
        if self.is_tool_active():
            self.setDragMode(QGraphicsView.NoDrag)
            self.viewport().setCursor(Qt.CrossCursor)
            self.setCursor(Qt.CrossCursor)
        else:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.viewport().setCursor(Qt.OpenHandCursor)
            self.setCursor(Qt.OpenHandCursor)

        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return

        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.scene.setSceneRect(QRectF(pixmap.rect()))

        for idx, b in enumerate(bubbles):
            x, y, w, h = b["x"], b["y"], b["width"], b["height"]
            is_cleaned = b.get("status") == "cleaned"
            
            pen_color = QColor(74, 222, 128) if is_cleaned else QColor(2, 132, 199)
            brush_color = QColor(74, 222, 128, 30) if is_cleaned else QColor(2, 132, 199, 35)

            polygons = None
            if b.get("lines"):
                polygons = generate_bubble_lasso_polygons(b.get("lines"))
            if not polygons and b.get("polygons"):
                polygons = b.get("polygons")
            if not polygons and b.get("polygon"):
                polygons = [b.get("polygon")]

            if polygons and len(polygons) > 0:
                path = QPainterPath()
                has_valid = False
                for p in polygons:
                    if isinstance(p, (list, tuple)) and len(p) >= 3:
                        qpoly = QPolygonF([QPointF(float(pt[0]), float(pt[1])) for pt in p])
                        path.addPolygon(qpoly)
                        has_valid = True
                if has_valid:
                    item = self.scene.addPath(path, QPen(pen_color, 2), QBrush(brush_color))
                else:
                    tx = b.get("text_x", x)
                    ty = b.get("text_y", y)
                    tw = b.get("text_width", w)
                    th = b.get("text_height", h)
                    item = self.scene.addRect(QRectF(tx, ty, tw, th), QPen(pen_color, 2), QBrush(brush_color))
            else:
                tx = b.get("text_x", x)
                ty = b.get("text_y", y)
                tw = b.get("text_width", w)
                th = b.get("text_height", h)
                item = self.scene.addRect(QRectF(tx, ty, tw, th), QPen(pen_color, 2), QBrush(brush_color))

            item.setZValue(10)
            item.setData(0, idx)
            item.setVisible(getattr(self, "_overlays_visible", True))
            self.rect_items.append(item)

        if maintain_view:
            self.setTransform(transform)
            self.horizontalScrollBar().setValue(h_scroll)
            self.verticalScrollBar().setValue(v_scroll)
        else:
            self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def update_background_pixmap(self, image_path_or_pixmap):
        if isinstance(image_path_or_pixmap, QPixmap):
            pixmap = image_path_or_pixmap
        else:
            pixmap = QPixmap(str(image_path_or_pixmap))
        if pixmap.isNull():
            return
        if self.pixmap_item:
            self.pixmap_item.setPixmap(pixmap)
        else:
            self.pixmap_item = self.scene.addPixmap(pixmap)
            self.pixmap_item.setZValue(0)

    def set_overlays_visible(self, visible: bool):
        self._overlays_visible = visible
        for item in self.rect_items:
            try:
                item.setVisible(visible)
            except Exception:
                pass
        if hasattr(self, "_target_badge_items"):
            for it in self._target_badge_items:
                try:
                    if it and it.scene():
                        it.setVisible(visible)
                except Exception:
                    pass
        if self._target_badge_group and self._target_badge_group.scene():
            try:
                self._target_badge_group.setVisible(visible)
            except Exception:
                pass

    def is_overlays_visible(self) -> bool:
        return getattr(self, "_overlays_visible", True)

    def is_tool_active(self) -> bool:
        return bool(self._draw_mode or self._wand_mode or self._brush_mode or self._lasso_mode)

    def enable_draw_mode(self):
        self._draw_mode = True
        self._wand_mode = False
        self._brush_mode = False
        self._lasso_mode = False
        self._is_panning = False
        self._pan_start = None
        self.setDragMode(QGraphicsView.NoDrag)
        self.viewport().setCursor(Qt.CrossCursor)
        self.setCursor(Qt.CrossCursor)

    def enable_wand_mode(self):
        self._wand_mode = True
        self._draw_mode = False
        self._brush_mode = False
        self._lasso_mode = False
        self._is_panning = False
        self._pan_start = None
        self.setDragMode(QGraphicsView.NoDrag)
        self.viewport().setCursor(Qt.CrossCursor)
        self.setCursor(Qt.CrossCursor)

    def enable_brush_mode(self):
        self._brush_mode = True
        self._draw_mode = False
        self._wand_mode = False
        self._lasso_mode = False
        self._is_panning = False
        self._pan_start = None
        self.setDragMode(QGraphicsView.NoDrag)
        self.viewport().setCursor(Qt.CrossCursor)
        self.setCursor(Qt.CrossCursor)

    def enable_lasso_mode(self):
        self._lasso_mode = True
        self._brush_mode = False
        self._draw_mode = False
        self._wand_mode = False
        self._is_panning = False
        self._pan_start = None
        self.setDragMode(QGraphicsView.NoDrag)
        self.viewport().setCursor(Qt.CrossCursor)
        self.setCursor(Qt.CrossCursor)

    def set_brush_size(self, size: int):
        self._brush_size = max(4, min(120, size))

    def disable_all_tools(self):
        self._draw_mode = False
        self._wand_mode = False
        self._brush_mode = False
        self._lasso_mode = False
        self._draw_start = None
        self._press_pos = None
        self._is_dragging = False
        self._is_panning = False
        self._pan_start = None
        self._lasso_points = []
        self._current_brush_path = None
        self._current_lasso_path = None
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.viewport().setCursor(Qt.OpenHandCursor)
        self.setCursor(Qt.OpenHandCursor)
        if self._draw_preview_rect and self._draw_preview_rect.scene():
            self.scene.removeItem(self._draw_preview_rect)
        self._draw_preview_rect = None
        if self._brush_path_item and self._brush_path_item.scene():
            self.scene.removeItem(self._brush_path_item)
        self._brush_path_item = None
        if self._lasso_path_item and self._lasso_path_item.scene():
            self.scene.removeItem(self._lasso_path_item)
        self._lasso_path_item = None

    def zoom_in(self):
        self.scale(1.25, 1.25)

    def zoom_out(self):
        self.scale(0.8, 0.8)

    def reset_fit(self):
        if self.scene and not self.scene.sceneRect().isEmpty():
            self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def reset_100(self):
        self.resetTransform()

    def _clear_target_badge(self):
        if hasattr(self, "_target_badge_items") and self._target_badge_items:
            for item in self._target_badge_items:
                try:
                    if item and item.scene():
                        self.scene.removeItem(item)
                except Exception:
                    pass
            self._target_badge_items.clear()
        if self._target_badge_group and self._target_badge_group.scene():
            try:
                self.scene.removeItem(self._target_badge_group)
            except Exception:
                pass
            self._target_badge_group = None

    def clear_highlights(self):
        self.selected_idx = -1
        self._clear_target_badge()
        for idx, item in enumerate(self.rect_items):
            try:
                is_cleaned = False
                if hasattr(self, "bubbles") and idx < len(self.bubbles):
                    is_cleaned = self.bubbles[idx].get("status") == "cleaned"
                pen_col = QColor(74, 222, 128) if is_cleaned else QColor(2, 132, 199)
                brush_col = QColor(74, 222, 128, 30) if is_cleaned else QColor(2, 132, 199, 35)
                item.setPen(QPen(pen_col, 2))
                item.setBrush(QBrush(brush_col))
                item.setZValue(10)
                item.setVisible(getattr(self, "_overlays_visible", True))
            except Exception:
                pass

    def wheelEvent(self, event):
        zoom_in_factor = 1.2
        zoom_out_factor = 1 / zoom_in_factor
        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)

    def highlight_bubble(self, index: int, center_on_item: bool = True):
        self.selected_idx = index
        
        # Remove previous target badge safely
        self._clear_target_badge()

        target_rect = None
        for idx, item in enumerate(self.rect_items):
            try:
                if idx == index:
                    item.setPen(QPen(QColor(0, 240, 255), 4, Qt.SolidLine))
                    item.setBrush(QBrush(QColor(0, 240, 255, 75)))
                    item.setZValue(30)
                    item.setVisible(getattr(self, "_overlays_visible", True))
                    target_rect = item.boundingRect()
                else:
                    is_cleaned = False
                    if hasattr(self, "bubbles") and idx < len(self.bubbles):
                        is_cleaned = self.bubbles[idx].get("status") == "cleaned"
                    pen_col = QColor(74, 222, 128) if is_cleaned else QColor(2, 132, 199)
                    brush_col = QColor(74, 222, 128, 30) if is_cleaned else QColor(2, 132, 199, 35)
                    item.setPen(QPen(pen_col, 2))
                    item.setBrush(QBrush(brush_col))
                    item.setZValue(10)
                    item.setVisible(getattr(self, "_overlays_visible", True))
            except Exception:
                pass

        if target_rect:
            if getattr(self, "_overlays_visible", True):
                badge_txt = QGraphicsSimpleTextItem(f"🎯 #{index + 1}")
                badge_txt.setFont(QFont("Segoe UI", 10, QFont.Bold))
                badge_txt.setBrush(QBrush(QColor(255, 255, 255)))
                
                tb = badge_txt.boundingRect()
                badge_bg = QGraphicsRectItem(QRectF(-6, -4, tb.width() + 12, tb.height() + 8))
                badge_bg.setBrush(QBrush(QColor(15, 23, 42, 235)))
                badge_bg.setPen(QPen(QColor(0, 240, 255), 2))
                
                bx = target_rect.x()
                by = max(4, target_rect.y() - tb.height() - 14)
                badge_bg.setPos(bx, by)
                badge_txt.setPos(bx, by)
                badge_bg.setZValue(100)
                badge_txt.setZValue(101)
                
                self.scene.addItem(badge_bg)
                self.scene.addItem(badge_txt)
                self._target_badge_items = [badge_bg, badge_txt]

            margin_rect = target_rect.adjusted(-60, -60, 60, 60)
            self.ensureVisible(margin_rect)
            if center_on_item:
                self.centerOn(target_rect.center())

    def mousePressEvent(self, event):
        # Middle-click or Right-click: ALWAYS smooth drag-pan regardless of active tool!
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self._is_panning = True
            self._pan_start = event.position().toPoint()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        # If a tool is active, Left-click is strictly reserved for drawing with the active tool!
        if self.is_tool_active() and event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            self._draw_start = scene_pos
            self._press_pos = event.position().toPoint()
            self._is_dragging = False

            if self._brush_mode:
                self._current_brush_path = QPainterPath()
                self._current_brush_path.moveTo(scene_pos)
                pen = QPen(QColor(239, 68, 68, 180), getattr(self, "_brush_size", 24), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                self._brush_path_item = self.scene.addPath(self._current_brush_path, pen)
                self._brush_path_item.setZValue(60)
            elif self._lasso_mode:
                self._lasso_points = [scene_pos]
                self._current_lasso_path = QPainterPath()
                self._current_lasso_path.moveTo(scene_pos)
                pen = QPen(QColor(245, 158, 11), 2, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin)
                brush = QBrush(QColor(245, 158, 11, 40))
                self._lasso_path_item = self.scene.addPath(self._current_lasso_path, pen, brush)
                self._lasso_path_item.setZValue(60)
            event.accept()
            return

        # If NO tool is active (Pan / Select mode):
        if not self.is_tool_active():
            if event.button() == Qt.LeftButton:
                # Check if user clicked a speech bubble overlay
                item = self.itemAt(event.position().toPoint())
                if isinstance(item, (QGraphicsRectItem, QGraphicsPolygonItem, QGraphicsPathItem)):
                    if getattr(self, "_overlays_visible", True):
                        idx = item.data(0)
                        if idx is not None:
                            self.highlight_bubble(idx)
                            self.bubble_clicked_signal.emit(idx)
                            event.accept()
                            return
                # Left-click on canvas starts smooth panning
                self._is_panning = True
                self._pan_start = event.position().toPoint()
                self.viewport().setCursor(Qt.ClosedHandCursor)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 1. Active smooth drag panning (via Middle, Right, or Left in Pan mode)
        if self._is_panning and self._pan_start is not None:
            curr_pt = event.position().toPoint()
            delta = curr_pt - self._pan_start
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._pan_start = curr_pt
            event.accept()
            return

        # 2. Brush drawing
        if self._brush_mode and self._current_brush_path and self._brush_path_item:
            scene_pos = self.mapToScene(event.position().toPoint())
            self._current_brush_path.lineTo(scene_pos)
            self._brush_path_item.setPath(self._current_brush_path)
            event.accept()
            return

        # 3. Lasso drawing
        if self._lasso_mode and self._current_lasso_path and self._lasso_path_item:
            scene_pos = self.mapToScene(event.position().toPoint())
            self._lasso_points.append(scene_pos)
            self._current_lasso_path.lineTo(scene_pos)
            self._lasso_path_item.setPath(self._current_lasso_path)
            event.accept()
            return

        # 4. Box or Wand drag preview
        if (self._draw_mode or self._wand_mode) and self._draw_start and self._press_pos:
            curr_pos = event.position().toPoint()
            if (curr_pos - self._press_pos).manhattanLength() > 4:
                self._is_dragging = True
                if not self._draw_preview_rect:
                    pen = QPen(QColor(56, 189, 248), 3, Qt.DashLine)
                    brush = QBrush(QColor(56, 189, 248, 45))
                    self._draw_preview_rect = self.scene.addRect(
                        QRectF(self._draw_start, self._draw_start), pen, brush
                    )
                    self._draw_preview_rect.setZValue(50)
                current = self.mapToScene(curr_pos)
                rect = QRectF(self._draw_start, current).normalized()
                self._draw_preview_rect.setRect(rect)
            event.accept()
            return

        # 5. When a tool is active, the cursor MUST stay CrossCursor! Never change to hand!
        if self.is_tool_active():
            self.viewport().setCursor(Qt.CrossCursor)
            event.accept()
            return

        # 6. If NO tool is active (Pan mode): Hover detection over speech bubbles
        if not getattr(self, "_overlays_visible", True):
            self.viewport().setCursor(Qt.OpenHandCursor)
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        found_h_idx = -1
        if hasattr(self, "bubbles") and self.bubbles:
            for idx in reversed(range(len(self.bubbles))):
                b = self.bubbles[idx]
                rect = QRectF(b["x"], b["y"], b["width"], b["height"])
                if rect.contains(scene_pos):
                    found_h_idx = idx
                    break

        if found_h_idx != self.hover_idx:
            self.hover_idx = found_h_idx
            for idx, item in enumerate(self.rect_items):
                if idx == self.selected_idx:
                    continue
                if idx == self.hover_idx:
                    item.setPen(QPen(QColor(56, 189, 248), 3, Qt.DashLine))
                    item.setBrush(QBrush(QColor(56, 189, 248, 50)))
                    item.setZValue(20)
                else:
                    is_cleaned = False
                    if hasattr(self, "bubbles") and idx < len(self.bubbles):
                        is_cleaned = self.bubbles[idx].get("status") == "cleaned"
                    pen_col = QColor(74, 222, 128) if is_cleaned else QColor(2, 132, 199)
                    brush_col = QColor(74, 222, 128, 30) if is_cleaned else QColor(2, 132, 199, 35)
                    item.setPen(QPen(pen_col, 2))
                    item.setBrush(QBrush(brush_col))
                    item.setZValue(10)

        if self.hover_idx >= 0:
            self.viewport().setCursor(Qt.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.OpenHandCursor)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # If panning was active:
        if self._is_panning:
            self._is_panning = False
            self._pan_start = None
            if self.is_tool_active():
                self.viewport().setCursor(Qt.CrossCursor)
            elif self.hover_idx >= 0:
                self.viewport().setCursor(Qt.PointingHandCursor)
            else:
                self.viewport().setCursor(Qt.OpenHandCursor)
            event.accept()
            return

        # Brush release
        if self._brush_mode and self._current_brush_path and self._brush_path_item:
            stroker = QPainterPathStroker()
            stroker.setWidth(getattr(self, "_brush_size", 24))
            stroker.setCapStyle(Qt.RoundCap)
            stroker.setJoinStyle(Qt.RoundJoin)
            stroked_path = stroker.createStroke(self._current_brush_path)
            bbox = stroked_path.boundingRect()
            polys = stroked_path.toSubpathPolygons()
            polygon_pts = []
            for p in polys:
                polygon_pts.append([[int(pt.x()), int(pt.y())] for pt in p])

            self.scene.removeItem(self._brush_path_item)
            self._brush_path_item = None
            self._current_brush_path = None

            bx = max(0, int(bbox.x()))
            by = max(0, int(bbox.y()))
            bw = max(10, int(bbox.width()))
            bh = max(10, int(bbox.height()))
            self.viewport().setCursor(Qt.CrossCursor)
            self.brush_mask_applied_signal.emit(bx, by, bw, bh, polygon_pts)
            event.accept()
            return

        # Lasso release
        if self._lasso_mode and self._current_lasso_path and self._lasso_path_item:
            if len(self._lasso_points) >= 3:
                self._current_lasso_path.closeSubpath()
                self._lasso_path_item.setPath(self._current_lasso_path)
                bbox = self._lasso_path_item.boundingRect()
                pts_list = [[int(pt.x()), int(pt.y())] for pt in self._lasso_points]
                self.scene.removeItem(self._lasso_path_item)
                self._lasso_path_item = None
                self._current_lasso_path = None
                self._lasso_points = []
                bx = max(0, int(bbox.x()))
                by = max(0, int(bbox.y()))
                bw = max(10, int(bbox.width()))
                bh = max(10, int(bbox.height()))
                self.viewport().setCursor(Qt.CrossCursor)
                self.lasso_drawn_signal.emit(bx, by, bw, bh, pts_list)
            else:
                self.scene.removeItem(self._lasso_path_item)
                self._lasso_path_item = None
                self._current_lasso_path = None
                self._lasso_points = []
                self.viewport().setCursor(Qt.CrossCursor)
            event.accept()
            return

        # Box or Wand release
        if (self._draw_mode or self._wand_mode) and event.button() == Qt.LeftButton and self._draw_start:
            if self._is_dragging and self._draw_preview_rect:
                rect = self._draw_preview_rect.rect()
                self.scene.removeItem(self._draw_preview_rect)
                self._draw_preview_rect = None
                
                x = int(rect.x())
                y = int(rect.y())
                w = int(rect.width())
                h = int(rect.height())
                
                self._draw_start = None
                self._press_pos = None
                self._is_dragging = False
                self.viewport().setCursor(Qt.CrossCursor)

                if w >= 10 and h >= 10:
                    self.new_bubble_drawn_signal.emit(x, y, w, h)
                event.accept()
                return
            elif not self._is_dragging and self._wand_mode:
                click_scene_pos = self._draw_start
                self._draw_start = None
                self._press_pos = None
                self._is_dragging = False
                self.viewport().setCursor(Qt.CrossCursor)
                self.magic_wand_clicked_signal.emit(int(click_scene_pos.x()), int(click_scene_pos.y()))
                event.accept()
                return

            self._draw_start = None
            self._press_pos = None
            self._is_dragging = False
            self.viewport().setCursor(Qt.CrossCursor)
            event.accept()
            return
            
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        event.ignore()


class SinglePageReviewWidget(QWidget):
    """
    Split-Screen Studio for inpainting and inspecting a single manga page.
    - Left: Full interactive canvas, Zoom/Fit tools, Magic Wand, Brush Mask, Box Tool, Toggle Cleaned/Original.
    - Right: Speech Bubble & Inpaint Inspector table with real-time inpaint actions.
    """
    padding_changed = Signal(int)

    def __init__(self, image_path: str, items: list, parent=None, cleaned_image_path: str = None, iopaint_url: str = None, iopaint_model: str = None, iopaint_dilation: int = 5, mask_padding: int = 0):
        super().__init__(parent)
        self.image_path = image_path
        self.items = items
        self.orig_pixmap = QPixmap(image_path)
        self.cleaned_image_path = cleaned_image_path if (cleaned_image_path and os.path.exists(cleaned_image_path)) else None
        self.cleaned_pixmap = QPixmap(self.cleaned_image_path) if (self.cleaned_image_path and os.path.exists(self.cleaned_image_path)) else None
        self.iopaint_url = iopaint_url or "http://127.0.0.1:8080"
        self.iopaint_model = iopaint_model or "anime-lama"
        self.iopaint_dilation = iopaint_dilation
        self.mask_padding = mask_padding if mask_padding > 0 else iopaint_dilation
        self.is_showing_cleaned = False
        self.is_inpainting = False
        self.inpaint_worker = None
        self._active_workers = []

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)

        # Left: Viewer Panel
        viewer_container = QWidget()
        viewer_container.setMinimumWidth(380)
        v_layout = QVBoxLayout(viewer_container)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(6)

        # Top Control Toolbar
        tools_frame = QFrame()
        tools_frame.setStyleSheet("background-color: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 2px;")
        tools_bar = QHBoxLayout(tools_frame)
        tools_bar.setContentsMargins(6, 4, 6, 4)
        tools_bar.setSpacing(6)

        # View Controls
        zoom_in_btn = QPushButton("➕ In")
        zoom_out_btn = QPushButton("➖ Out")
        reset_btn = QPushButton("🔍 Fit")
        reset_100_btn = QPushButton("⬛ 100%")

        for b in (zoom_in_btn, zoom_out_btn, reset_btn, reset_100_btn):
            b.setFocusPolicy(Qt.NoFocus)
            b.setStyleSheet("""
                QPushButton { background: #1e293b; color: #cbd5e1; padding: 4px 8px; border-radius: 6px; border: 1px solid #334155; font-size: 11px; font-weight: 600; }
                QPushButton:hover { background: #334155; color: #38bdf8; }
            """)

        tools_bar.addWidget(zoom_in_btn)
        tools_bar.addWidget(zoom_out_btn)
        tools_bar.addWidget(reset_btn)
        tools_bar.addWidget(reset_100_btn)

        tools_bar.addSpacing(6)

        # ✨ Toggle Cleaned View Button
        self.toggle_cleaned_btn = QPushButton("✨ Show Cleaned (Space)")
        self.toggle_cleaned_btn.setCheckable(True)
        self.toggle_cleaned_btn.setFocusPolicy(Qt.NoFocus)
        self.toggle_cleaned_btn.setStyleSheet("""
            QPushButton {
                background: #064e3b;
                color: #4ade80;
                border: 1px solid #10b981;
                border-radius: 6px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { background: #047857; color: #ffffff; }
            QPushButton:checked {
                background: #047857;
                color: #ffffff;
                border: 1px solid #34d399;
            }
            QPushButton:disabled {
                background: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
            }
        """)
        self.toggle_cleaned_btn.clicked.connect(self.toggle_cleaned_view)
        tools_bar.addWidget(self.toggle_cleaned_btn)

        # 👁️ Toggle Bubble Masks Button
        self.toggle_masks_btn = QPushButton("👁️ Masks (M)")
        self.toggle_masks_btn.setCheckable(True)
        self.toggle_masks_btn.setChecked(True)
        self.toggle_masks_btn.setFocusPolicy(Qt.NoFocus)
        self.toggle_masks_btn.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 6px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { background: #0c4a6e; color: #ffffff; }
            QPushButton:checked {
                background: #0369a1;
                color: #ffffff;
                border: 1px solid #38bdf8;
            }
        """)
        self.toggle_masks_btn.clicked.connect(self.toggle_masks_view)
        tools_bar.addWidget(self.toggle_masks_btn)

        v_layout.addWidget(tools_frame)

        # Inpainting Action Toolbar (Magic Wand, Brush, Add Box, Inpaint Page, Revert)
        action_frame = QFrame()
        action_frame.setStyleSheet("background-color: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 2px;")
        action_bar = QHBoxLayout(action_frame)
        action_bar.setContentsMargins(6, 4, 6, 4)
        action_bar.setSpacing(6)

        self.btn_inpaint_page = QPushButton("🧹 Inpaint Page")
        self.btn_inpaint_page.setFocusPolicy(Qt.NoFocus)
        self.btn_inpaint_page.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0ea5e9); color: white; border: 1px solid #38bdf8; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background: #0369a1; }
        """)
        self.btn_inpaint_page.clicked.connect(self.inpaint_active_page)
        action_bar.addWidget(self.btn_inpaint_page)

        self.magic_wand_btn = QPushButton("🪄 Magic Wand (W)")
        self.magic_wand_btn.setCheckable(True)
        self.magic_wand_btn.setFocusPolicy(Qt.NoFocus)
        self.magic_wand_btn.setStyleSheet("""
            QPushButton { background: #1e293b; color: #c084fc; border: 1px solid #7c3aed; border-radius: 6px; padding: 4px 8px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background: #4c1d95; color: white; }
            QPushButton:checked { background: #6d28d9; color: white; border: 1px solid #a78bfa; }
        """)
        self.magic_wand_btn.clicked.connect(self.toggle_magic_wand)
        action_bar.addWidget(self.magic_wand_btn)

        self.brush_tool_btn = QPushButton("🖌️ Brush (B)")
        self.brush_tool_btn.setCheckable(True)
        self.brush_tool_btn.setFocusPolicy(Qt.NoFocus)
        self.brush_tool_btn.setStyleSheet("""
            QPushButton { background: #1e293b; color: #f87171; border: 1px solid #dc2626; border-radius: 6px; padding: 4px 8px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background: #7f1d1d; color: white; }
            QPushButton:checked { background: #b91c1c; color: white; border: 1px solid #fca5a5; }
        """)
        self.brush_tool_btn.clicked.connect(self.toggle_brush_tool)
        action_bar.addWidget(self.brush_tool_btn)

        self.lasso_tool_btn = QPushButton("🪢 Lasso (L)")
        self.lasso_tool_btn.setCheckable(True)
        self.lasso_tool_btn.setFocusPolicy(Qt.NoFocus)
        self.lasso_tool_btn.setStyleSheet("""
            QPushButton { background: #1e293b; color: #fbbf24; border: 1px solid #d97706; border-radius: 6px; padding: 4px 8px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background: #78350f; color: white; }
            QPushButton:checked { background: #b45309; color: white; border: 1px solid #fde68a; }
        """)
        self.lasso_tool_btn.clicked.connect(self.toggle_lasso_tool)
        action_bar.addWidget(self.lasso_tool_btn)

        self.add_bubble_btn = QPushButton("🔲 Box (A)")
        self.add_bubble_btn.setCheckable(True)
        self.add_bubble_btn.setFocusPolicy(Qt.NoFocus)
        self.add_bubble_btn.setStyleSheet("""
            QPushButton { background: #1e293b; color: #38bdf8; border: 1px solid #0284c7; border-radius: 6px; padding: 4px 8px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background: #0c4a6e; color: white; }
            QPushButton:checked { background: #0284c7; color: white; }
        """)
        self.add_bubble_btn.clicked.connect(self.toggle_add_bubble)
        action_bar.addWidget(self.add_bubble_btn)

        self.pan_tool_btn = QPushButton("✋ Pan (H)")
        self.pan_tool_btn.setCheckable(True)
        self.pan_tool_btn.setChecked(True)
        self.pan_tool_btn.setFocusPolicy(Qt.NoFocus)
        self.pan_tool_btn.setStyleSheet("""
            QPushButton { background: #1e293b; color: #38bdf8; border: 1px solid #0284c7; border-radius: 6px; padding: 4px 8px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background: #0c4a6e; color: white; }
            QPushButton:checked { background: #0284c7; color: white; }
        """)
        self.pan_tool_btn.clicked.connect(self.toggle_pan_tool)
        action_bar.addWidget(self.pan_tool_btn)

        self.delete_bubble_btn = QPushButton("🗑️ Delete (Del)")
        self.delete_bubble_btn.setFocusPolicy(Qt.NoFocus)
        self.delete_bubble_btn.setStyleSheet("""
            QPushButton { background: #1e293b; color: #f87171; border: 1px solid #dc2626; border-radius: 6px; padding: 4px 8px; font-weight: bold; font-size: 11px; }
            QPushButton:hover { background: #7f1d1d; color: white; }
        """)
        self.delete_bubble_btn.setToolTip("Delete / remove selected speech bubble (Del)")
        self.delete_bubble_btn.clicked.connect(self.delete_selected_bubble)
        action_bar.addWidget(self.delete_bubble_btn)

        lbl_pad = QLabel("🔲 Padding:")
        lbl_pad.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold; margin-left: 6px;")
        self.padding_spin = QSpinBox()
        self.padding_spin.setRange(0, 100)
        self.padding_spin.setValue(self.mask_padding)
        self.padding_spin.setToolTip("Mask dilation & padding in pixels applied to manual boxes, lassos, brushes, and IOPaint")
        self.padding_spin.setStyleSheet("background: #1e293b; color: #38bdf8; border: 1px solid #0284c7; border-radius: 4px; padding: 2px 4px; font-weight: bold; font-size: 11px;")
        self.padding_spin.valueChanged.connect(self.on_padding_changed)
        action_bar.addWidget(lbl_pad)
        action_bar.addWidget(self.padding_spin)

        v_layout.addWidget(action_frame)

        # Status Hint
        self.draw_status_label = QLabel("🎯 Click inside bubble with Magic Wand or drag rectangle...")
        self.draw_status_label.setStyleSheet("color: #38bdf8; font-weight: bold; padding: 4px 10px; background: #0c192c; border: 1px solid #0284c7; border-radius: 6px;")
        self.draw_status_label.hide()
        v_layout.addWidget(self.draw_status_label)

        # Graphics Viewer
        self.page_viewer = PageViewerWidget()
        self.page_viewer.load_page(self.image_path, self.items)
        self.page_viewer.bubble_clicked_signal.connect(self.on_bubble_clicked_from_viewer)
        self.page_viewer.new_bubble_drawn_signal.connect(self.on_new_bubble_drawn)
        self.page_viewer.magic_wand_clicked_signal.connect(self.on_magic_wand_clicked)
        self.page_viewer.brush_mask_applied_signal.connect(self.on_brush_mask_applied)
        self.page_viewer.lasso_drawn_signal.connect(self.on_lasso_drawn)

        zoom_in_btn.clicked.connect(self.page_viewer.zoom_in)
        zoom_out_btn.clicked.connect(self.page_viewer.zoom_out)
        reset_btn.clicked.connect(self.page_viewer.reset_fit)
        reset_100_btn.clicked.connect(self.page_viewer.reset_100)

        v_layout.addWidget(self.page_viewer, 1)

        # Right: Speech Bubble & Inpaint Inspector Table
        table_container = QWidget()
        table_container.setMinimumWidth(360)
        t_layout = QVBoxLayout(table_container)
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_layout.setSpacing(6)

        header_row = QHBoxLayout()
        self.lbl_table_header = QLabel(f"🫧 Detected Bubbles ({len(self.items)}):")
        self.lbl_table_header.setProperty("class", "section-header")
        header_row.addWidget(self.lbl_table_header)
        header_row.addStretch()

        self.bubble_search_input = QLineEdit()
        self.bubble_search_input.setPlaceholderText("🔍 Filter bubbles...")
        self.bubble_search_input.setMaximumWidth(180)
        self.bubble_search_input.setFixedHeight(28)
        self.bubble_search_input.textChanged.connect(self.filter_table_rows)
        header_row.addWidget(self.bubble_search_input)
        t_layout.addLayout(header_row)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["#", "Crop Preview", "Background & Size", "Inpaint Status / Actions"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        
        self.table.setColumnWidth(0, 48)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 150)
        
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setIconSize(QSize(120, 65))
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.table.cellClicked.connect(self.on_cell_clicked)

        self._populate_table()
        t_layout.addWidget(self.table, 1)

        splitter.addWidget(viewer_container)
        splitter.addWidget(table_container)
        splitter.setSizes([600, 450])
        layout.addWidget(splitter)

        if len(self.items) > 0:
            self.table.selectRow(0)

        if self.cleaned_image_path and os.path.exists(self.cleaned_image_path):
            self.toggle_cleaned_view(True)

    def update_table_row_status(self, row: int):
        if not (0 <= row < self.table.rowCount()):
            return
        if not (0 <= row < len(self.items)):
            return
        is_cleaned = self.items[row].get("status") == "cleaned"
        action_widget = self.table.cellWidget(row, 3)
        if action_widget:
            status_lbl = action_widget.findChild(QLabel)
            if status_lbl:
                status_lbl.setText("✨ Cleaned" if is_cleaned else "⏳ Pending")
                status_lbl.setStyleSheet(f"color: {'#4ade80' if is_cleaned else '#fbbf24'}; font-weight: bold; font-size: 11px;")

    def _populate_table(self):
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(self.items))
            for r, item in enumerate(self.items):
                self.table.setRowHeight(r, 72)

                # 0. ID
                id_item = QTableWidgetItem(f"#{r+1}")
                id_item.setTextAlignment(Qt.AlignCenter)
                id_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table.setItem(r, 0, id_item)

                # 1. Thumbnail Crop
                x, y, w, h = item["x"], item["y"], item["width"], item["height"]
                crop_pixmap = self.orig_pixmap.copy(x, y, w, h) if not self.orig_pixmap.isNull() else QPixmap()
                scaled_thumb = crop_pixmap.scaled(120, 65, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                thumb_item = QTableWidgetItem()
                thumb_item.setIcon(QIcon(scaled_thumb))
                thumb_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table.setItem(r, 1, thumb_item)

                # 2. Dimensions & Background Type
                bg_type = item.get("bg_type", "white")
                bg_icon = "⚪ Flat White" if bg_type == "white" else ("🔘 Screentone" if bg_type == "screentone" else "🎨 Complex Art")
                info_text = f"{w} × {h} px\n{bg_icon}"
                info_item = QTableWidgetItem(info_text)
                info_item.setFont(QFont("Segoe UI", 9))
                info_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table.setItem(r, 2, info_item)

                # 3. Status & Action Button Container
                action_widget = QWidget()
                a_layout = QHBoxLayout(action_widget)
                a_layout.setContentsMargins(4, 4, 4, 4)
                a_layout.setSpacing(6)

                is_cleaned = item.get("status") == "cleaned"
                status_lbl = QLabel("✨ Cleaned" if is_cleaned else "⏳ Pending")
                status_lbl.setStyleSheet(f"color: {'#4ade80' if is_cleaned else '#fbbf24'}; font-weight: bold; font-size: 11px;")
                a_layout.addWidget(status_lbl)
                a_layout.addStretch()

                inpaint_btn = QPushButton("🧹 Clean")
                inpaint_btn.setFixedHeight(26)
                inpaint_btn.setStyleSheet("background: #0284c7; color: white; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 8px;")
                inpaint_btn.clicked.connect(lambda _, row=r: self.inpaint_single_bubble_by_row(row))
                a_layout.addWidget(inpaint_btn)

                delete_btn = QPushButton("🗑️ Delete")
                delete_btn.setFixedHeight(26)
                delete_btn.setStyleSheet("background: #1e293b; color: #f87171; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 6px; border: 1px solid #dc2626;")
                delete_btn.setToolTip("Delete this bubble")
                delete_btn.clicked.connect(lambda _, row=r: self.delete_bubble_by_row(row))
                a_layout.addWidget(delete_btn)

                self.table.setCellWidget(r, 3, action_widget)
        finally:
            self.table.blockSignals(False)

    def filter_table_rows(self, query: str):
        query = query.strip().lower()
        for r in range(self.table.rowCount()):
            if not query:
                self.table.setRowHidden(r, False)
                continue
            id_text = f"#{r+1}"
            info_item = self.table.item(r, 2)
            info_text = info_item.text().lower() if info_item else ""
            matches = (query in id_text) or (query in info_text)
            self.table.setRowHidden(r, not matches)

    def toggle_masks_view(self, checked: bool = None):
        if checked is None:
            new_state = not self.page_viewer.is_overlays_visible()
        else:
            new_state = bool(checked)
        self.page_viewer.set_overlays_visible(new_state)
        self.toggle_masks_btn.blockSignals(True)
        self.toggle_masks_btn.setChecked(new_state)
        self.toggle_masks_btn.setText("👁️ Masks (M)" if new_state else "🙈 Masks (M)")
        self.toggle_masks_btn.blockSignals(False)

    def toggle_cleaned_view(self, checked: bool = None):
        if getattr(self, "is_inpainting", False):
            return

        if self.cleaned_pixmap and not self.cleaned_pixmap.isNull():
            if checked is None:
                self.is_showing_cleaned = not self.is_showing_cleaned
            else:
                self.is_showing_cleaned = bool(checked)

            self.toggle_cleaned_btn.blockSignals(True)
            self.toggle_cleaned_btn.setChecked(self.is_showing_cleaned)
            self.toggle_cleaned_btn.blockSignals(False)

            if self.is_showing_cleaned:
                self.toggle_cleaned_btn.setText("📄 Show Original (Space)")
                self.page_viewer.update_background_pixmap(self.cleaned_pixmap)
                # In Cleaned Mode: HIDE all bubble masks so user views only clean artwork!
                self.toggle_masks_view(False)
            else:
                self.toggle_cleaned_btn.setText("✨ Show Cleaned (Space)")
                self.page_viewer.update_background_pixmap(self.orig_pixmap)
                # In Original Mode: SHOW bubble masks so user can inspect and select bubbles!
                self.toggle_masks_view(True)
        else:
            # First time inpainting requested
            self.toggle_cleaned_btn.blockSignals(True)
            self.toggle_cleaned_btn.setText("⏳ Cleaning Page...")
            self.toggle_cleaned_btn.setEnabled(False)
            self.toggle_cleaned_btn.blockSignals(False)
            self.inpaint_active_page()

    def export_current_image(self):
        src_path = self.cleaned_image_path if (self.is_showing_cleaned and self.cleaned_image_path and os.path.exists(self.cleaned_image_path)) else self.image_path
        if not os.path.exists(src_path):
            QMessageBox.warning(self, "Image Not Found", "The image file could not be found.")
            return

        stem = Path(self.image_path).stem
        default_filename = f"{stem}_clean.png"

        parent_dlg = self.window()
        last_dir = ""
        if parent_dlg and hasattr(parent_dlg, "get_last_dir"):
            last_dir = parent_dlg.get_last_dir("last_export_dir", "")
        if not last_dir or not os.path.exists(last_dir):
            last_dir = os.path.dirname(self.image_path)

        default_save_path = os.path.join(last_dir, default_filename)

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Export Page Image", default_save_path,
            "PNG Image (*.png);;Adobe Photoshop PSD (*.psd);;JPEG Image (*.jpg *.jpeg);;WebP Image (*.webp);;All Files (*.*)"
        )
        if save_path:
            if parent_dlg and hasattr(parent_dlg, "set_last_dir"):
                parent_dlg.set_last_dir("last_export_dir", os.path.dirname(save_path))
            ext = Path(save_path).suffix.lower()
            if ext == ".psd":
                from PIL import Image
                from psd_tools import PSDImage
                pil_img = Image.open(src_path)
                psd = PSDImage.frompil(pil_img)
                psd.save(save_path)
            else:
                shutil.copy2(src_path, save_path)
            QMessageBox.information(self, "Export Successful", f"Saved image to:\n{save_path}")

    def on_padding_changed(self, val: int):
        self.mask_padding = int(val)
        for b in self.items:
            b["mask_padding"] = self.mask_padding
        self.padding_changed.emit(self.mask_padding)
        p = self.parent()
        while p:
            if hasattr(p, "mask_padding"):
                p.mask_padding = self.mask_padding
            p = p.parent()

    def toggle_pan_tool(self, checked: bool = True):
        self.pan_tool_btn.setChecked(True)
        self.magic_wand_btn.setChecked(False)
        self.brush_tool_btn.setChecked(False)
        self.lasso_tool_btn.setChecked(False)
        self.add_bubble_btn.setChecked(False)
        self.draw_status_label.setText("✋ Pan Active: Drag canvas to navigate • Click bubble to inspect")
        self.draw_status_label.show()
        self.page_viewer.disable_all_tools()

    def toggle_magic_wand(self, checked: bool):
        if checked:
            self.magic_wand_btn.setChecked(True)
            self.pan_tool_btn.setChecked(False)
            self.add_bubble_btn.setChecked(False)
            self.brush_tool_btn.setChecked(False)
            self.lasso_tool_btn.setChecked(False)
            self.draw_status_label.setText("🪄 Magic Wand Active: Click inside speech bubble • Right-drag to Pan")
            self.draw_status_label.show()
            self.page_viewer.enable_wand_mode()
        else:
            self.toggle_pan_tool(True)

    def toggle_brush_tool(self, checked: bool):
        if checked:
            self.brush_tool_btn.setChecked(True)
            self.pan_tool_btn.setChecked(False)
            self.magic_wand_btn.setChecked(False)
            self.add_bubble_btn.setChecked(False)
            self.lasso_tool_btn.setChecked(False)
            self.draw_status_label.setText("🖌️ Brush Tool Active: Paint over text/SFX • Right-drag to Pan")
            self.draw_status_label.show()
            self.page_viewer.enable_brush_mode()
        else:
            self.toggle_pan_tool(True)

    def toggle_lasso_tool(self, checked: bool):
        if checked:
            self.lasso_tool_btn.setChecked(True)
            self.pan_tool_btn.setChecked(False)
            self.magic_wand_btn.setChecked(False)
            self.brush_tool_btn.setChecked(False)
            self.add_bubble_btn.setChecked(False)
            self.draw_status_label.setText("🪢 Lasso Tool Active: Draw lasso around text/SFX • Right-drag to Pan")
            self.draw_status_label.show()
            self.page_viewer.enable_lasso_mode()
        else:
            self.toggle_pan_tool(True)

    def toggle_add_bubble(self, checked: bool):
        if checked:
            self.add_bubble_btn.setChecked(True)
            self.pan_tool_btn.setChecked(False)
            self.magic_wand_btn.setChecked(False)
            self.brush_tool_btn.setChecked(False)
            self.lasso_tool_btn.setChecked(False)
            self.draw_status_label.setText("🔲 Box Tool Active: Left-drag to draw box • Right-drag to Pan")
            self.draw_status_label.show()
            self.page_viewer.enable_draw_mode()
        else:
            self.toggle_pan_tool(True)

    def create_and_clean_manual_item(self, x: int, y: int, w: int, h: int, tool_type: str, polygon_pts: list = None):
        """
        Analyzes the background of a manually drawn region (Brush, Lasso, Box, Wand):
        - If bubble is verified as pure/flat white (>90% white ratio): cleans locally with instant white fill.
        - If bubble is NOT white (screentone, dark, colored, texture, complex art):
          immediately routes directly to IOPaint AI with the exact selection mask!
        """
        # Always evaluate against original image so previous edits don't corrupt classification
        eval_img = self.image_path if (self.image_path and os.path.exists(self.image_path)) else (self.cleaned_image_path or self.image_path)

        # Determine background classification from original image
        bg_type = "complex"
        try:
            img_bgr = read_image_unicode(eval_img)
            if img_bgr is not None:
                dummy_bubble = {
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "tool": tool_type,
                }
                if polygon_pts:
                    dummy_bubble["polygons"] = polygon_pts if (isinstance(polygon_pts[0][0], list)) else [polygon_pts]
                    dummy_bubble["polygon"] = dummy_bubble["polygons"][0]
                cls_type, stats = classify_bubble_background(img_bgr, dummy_bubble)
                if cls_type == "flat_white" and stats.get("total_white_ratio", 0) >= 0.90 and stats.get("border_white_ratio", 0) >= 0.90:
                    bg_type = "white"
                else:
                    bg_type = "complex"
        except Exception as e:
            print(f"Error classifying manual bubble background: {e}")

        new_id = len(self.items) + 1
        new_item = {
            "id": new_id,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "bg_type": bg_type,
            "tool": tool_type,
            "is_manual": True,
            "mask_padding": self.mask_padding,
            "status": "pending"
        }
        if polygon_pts:
            new_item["polygon"] = polygon_pts[0] if (isinstance(polygon_pts[0][0], list)) else polygon_pts
            new_item["polygons"] = polygon_pts if (isinstance(polygon_pts[0][0], list)) else [polygon_pts]
            new_item["lines"] = new_item["polygons"]

        self.items.append(new_item)
        current_display_img = self.cleaned_image_path if (self.is_showing_cleaned and self.cleaned_image_path and os.path.exists(self.cleaned_image_path)) else self.image_path
        self.page_viewer.load_page(current_display_img, self.items, maintain_view=True)
        if self.is_showing_cleaned:
            self.toggle_masks_view(False)
        self._populate_table()
        self.table.selectRow(len(self.items) - 1)
        self.lbl_table_header.setText(f"🫧 Detected Bubbles ({len(self.items)}):")

        # Provide immediate user feedback in status bar
        if bg_type == "white":
            self.draw_status_label.setText(f"⚪ Pure white bubble (>90%): Cleaning instantly with flat white fill...")
        else:
            self.draw_status_label.setText(f"🎨 Non-white bubble/art: Inpainting immediately with IOPaint ({self.iopaint_model})...")
        self.draw_status_label.show()

        # Inpaint immediately
        self.inpaint_single_bubble_by_row(len(self.items) - 1)

    def on_lasso_drawn(self, x: int, y: int, w: int, h: int, polygon_pts: list):
        self.create_and_clean_manual_item(x, y, w, h, tool_type="lasso", polygon_pts=polygon_pts)

    def on_magic_wand_clicked(self, x: int, y: int):
        from fast_cleaner import detect_bubble_at_point
        detected_rect = detect_bubble_at_point(self.image_path, x, y, padding=self.iopaint_dilation)
        if detected_rect:
            bx, by, bw, bh = detected_rect
            self.create_and_clean_manual_item(bx, by, bw, bh, tool_type="wand", polygon_pts=None)
        else:
            QMessageBox.information(self, "No Bubble Detected", "Could not detect a clear speech bubble boundary at this point.")

    def on_brush_mask_applied(self, x: int, y: int, w: int, h: int, polygon_pts: list):
        self.create_and_clean_manual_item(x, y, w, h, tool_type="brush", polygon_pts=polygon_pts)

    def on_new_bubble_drawn(self, x: int, y: int, w: int, h: int):
        self.create_and_clean_manual_item(x, y, w, h, tool_type="box", polygon_pts=None)

    def on_bubble_clicked_from_viewer(self, idx: int):
        if 0 <= idx < self.table.rowCount():
            self.table.blockSignals(True)
            self.table.selectRow(idx)
            item = self.table.item(idx, 0)
            if item:
                self.table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
            self.table.blockSignals(False)

    def on_cell_clicked(self, row: int, col: int):
        if self.table.currentRow() != row:
            self.table.selectRow(row)
        else:
            self.page_viewer.highlight_bubble(row, center_on_item=True)

    def on_table_selection_changed(self):
        selected = self.table.selectedItems()
        if selected:
            row = selected[0].row()
            self.page_viewer.highlight_bubble(row, center_on_item=True)



    def inpaint_active_page(self):
        if not self.items:
            QMessageBox.information(self, "No Bubbles", "No speech bubbles found to clean.")
            self.toggle_cleaned_btn.blockSignals(True)
            self.toggle_cleaned_btn.setChecked(False)
            self.toggle_cleaned_btn.setText("✨ Show Cleaned (Space)")
            self.toggle_cleaned_btn.setEnabled(True)
            self.toggle_cleaned_btn.blockSignals(False)
            return

        self.is_inpainting = True
        self.btn_inpaint_page.setEnabled(False)
        self.btn_inpaint_page.setText("🧹 Cleaning Page...")
        self.toggle_cleaned_btn.blockSignals(True)
        self.toggle_cleaned_btn.setEnabled(False)
        self.toggle_cleaned_btn.setText("⏳ Cleaning Page...")
        self.toggle_cleaned_btn.blockSignals(False)
        
        eff_dil = max(self.iopaint_dilation, self.mask_padding)
        for b in self.items:
            b["mask_padding"] = self.mask_padding

        self.inpaint_worker = PageInpaintWorker(
            image_path=self.image_path,
            bubbles=self.items,
            server_url=self.iopaint_url,
            model=self.iopaint_model,
            dilation=eff_dil,
            padding=self.mask_padding,
            adaptive_mode=True,
            parent=None
        )
        track_running_worker(self.inpaint_worker)
        self.inpaint_worker.finished_signal.connect(self.on_page_inpaint_finished)
        self.inpaint_worker.start()

    def stop_all_workers(self):
        if self.inpaint_worker:
            try:
                self.inpaint_worker.cancel()
                self.inpaint_worker.finished_signal.disconnect()
            except Exception:
                pass
            self.inpaint_worker = None

        for w in list(self._active_workers):
            try:
                if hasattr(w, "cancel"):
                    w.cancel()
                w.finished_signal.disconnect()
            except Exception:
                pass
        self._active_workers.clear()

    def closeEvent(self, event):
        self.stop_all_workers()
        super().closeEvent(event)

    def on_page_inpaint_finished(self, success: bool, cleaned_path: str, err: str):
        self.is_inpainting = False
        self.btn_inpaint_page.setEnabled(True)
        self.btn_inpaint_page.setText("🧹 Inpaint Page")
        self.toggle_cleaned_btn.setEnabled(True)

        if not self.isVisible() and not self.parent():
            return

        if success:
            self.cleaned_image_path = cleaned_path
            self.cleaned_pixmap = QPixmap(cleaned_path)
            self.is_showing_cleaned = True
            self.toggle_cleaned_btn.blockSignals(True)
            self.toggle_cleaned_btn.setChecked(True)
            self.toggle_cleaned_btn.setText("📄 Show Original (Space)")
            self.toggle_cleaned_btn.blockSignals(False)
            self.page_viewer.update_background_pixmap(self.cleaned_pixmap)
            self.toggle_masks_view(False)
            self._populate_table()
        else:
            self.is_showing_cleaned = False
            self.toggle_cleaned_btn.blockSignals(True)
            self.toggle_cleaned_btn.setChecked(False)
            self.toggle_cleaned_btn.setText("✨ Show Cleaned (Space)")
            self.toggle_cleaned_btn.blockSignals(False)
            self.page_viewer.update_background_pixmap(self.orig_pixmap)
            self.toggle_masks_view(True)
            QMessageBox.critical(self, "Inpainting Error", f"Failed to inpaint page:\n{err}")

    def inpaint_single_bubble_by_row(self, row: int):
        if not (0 <= row < len(self.items)):
            return
        bubble = self.items[row]
        current_img = self.cleaned_image_path if (self.cleaned_image_path and os.path.exists(self.cleaned_image_path)) else self.image_path

        bubble["mask_padding"] = self.mask_padding
        worker = SingleBubbleInpaintWorker(
            current_img_path=current_img,
            bubble_dict=bubble,
            bubble_idx=row,
            server_url=self.iopaint_url,
            model=self.iopaint_model,
            dilation=max(self.iopaint_dilation, self.mask_padding),
            parent=None
        )
        track_running_worker(worker)
        if not hasattr(self, "_active_workers"):
            self._active_workers = []
        self._active_workers.append(worker)

        def _on_single_done(ok, b_idx, out_p, err):
            try:
                if ok:
                    self.cleaned_image_path = out_p
                    self.cleaned_pixmap = QPixmap(out_p)
                    self.items[b_idx]["status"] = "cleaned"
                    self.update_table_row_status(b_idx)
                    self.is_showing_cleaned = True
                    self.toggle_cleaned_btn.blockSignals(True)
                    self.toggle_cleaned_btn.setChecked(True)
                    self.toggle_cleaned_btn.setText("📄 Show Original (Space)")
                    self.toggle_cleaned_btn.blockSignals(False)
                    self.page_viewer.update_background_pixmap(self.cleaned_pixmap)
                    self.toggle_masks_view(False)
                else:
                    QMessageBox.critical(self, "Inpaint Failed", f"Bubble inpaint error:\n{err}")
            finally:
                if worker in self._active_workers:
                    self._active_workers.remove(worker)

        worker.finished_signal.connect(_on_single_done)
        worker.start()

    def delete_bubble_by_row(self, row: int):
        if not (0 <= row < len(self.items)):
            return
        bubble = self.items.pop(row)

        # If cleaned image exists, restore original crop region for that bubble area
        if self.cleaned_image_path and os.path.exists(self.cleaned_image_path):
            try:
                from PIL import Image
                orig_pil = Image.open(self.image_path)
                clean_pil = Image.open(self.cleaned_image_path)

                x, y, w, h = bubble["x"], bubble["y"], bubble["width"], bubble["height"]
                crop_orig = orig_pil.crop((x, y, x + w, y + h))
                clean_pil.paste(crop_orig, (x, y))
                clean_pil.save(self.cleaned_image_path, quality=95)
                self.cleaned_pixmap = QPixmap(self.cleaned_image_path)
            except Exception:
                pass

        # Re-index remaining IDs
        for idx, b in enumerate(self.items):
            b["id"] = idx + 1

        self.lbl_table_header.setText(f"🫧 Detected Bubbles ({len(self.items)}):")
        self._populate_table()

        current_display_img = self.cleaned_image_path if (self.is_showing_cleaned and self.cleaned_image_path and os.path.exists(self.cleaned_image_path)) else self.image_path
        self.page_viewer.load_page(current_display_img, self.items, maintain_view=True)
        if self.is_showing_cleaned:
            self.toggle_masks_view(False)

        if len(self.items) > 0:
            new_select_row = min(row, len(self.items) - 1)
            self.table.selectRow(new_select_row)
        else:
            self.page_viewer.clear_highlights()

    def inpaint_selected_bubble(self):
        selected = self.table.selectedItems()
        if selected:
            row = selected[0].row()
            self.inpaint_single_bubble_by_row(row)

    def delete_selected_bubble(self):
        selected = self.table.selectedItems()
        if selected:
            row = selected[0].row()
            self.delete_bubble_by_row(row)


class ExportOptionsDialog(QDialog):
    """
    Advanced Manga Chapter Export Dialog with options for:
    - Complete Chapter (Cleaned + Uncleaned Raw for missing pages to preserve sequence)
    - Cleaned Pages Only
    - Raw Original Pages Only
    - Export to Folder or ZIP archive
    - Original names vs _clean suffix
    - Image format conversion: Original / PNG / PSD (Photoshop) / JPEG / WebP
    """
    def __init__(self, image_paths: list, cleaned_pages: dict, default_out_dir: str = "", parent=None):
        super().__init__(parent)
        self.image_paths = image_paths
        self.cleaned_pages = cleaned_pages
        self.default_out_dir = default_out_dir
        self.setWindowTitle("📦 SmartCleaner-AI — Export Chapter Images")
        self.setMinimumWidth(540)
        self.setStyleSheet(DARK_NAVY_STYLESHEET)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 16, 18, 16)

        # Header Title
        hdr = QLabel("📦 Export Manga Chapter Options")
        hdr.setFont(QFont("Segoe UI", 13, QFont.Bold))
        hdr.setStyleSheet("color: #38bdf8;")
        layout.addWidget(hdr)

        # 1. Export Scope Group
        scope_group = QGroupBox("🎯 1. What would you like to export?")
        scope_group.setStyleSheet("QGroupBox { color: #38bdf8; font-weight: bold; border: 1px solid #1e293b; border-radius: 8px; margin-top: 10px; padding: 12px; }")
        scope_layout = QVBoxLayout(scope_group)
        scope_layout.setSpacing(8)

        cleaned_count = sum(1 for p in self.image_paths if self.cleaned_pages.get(p) and os.path.exists(self.cleaned_pages[p]))
        total_count = len(self.image_paths)

        self.radio_full_chapter = QRadioButton(f"📦 Full Complete Chapter ({total_count} pages) — Cleaned + Raw to preserve complete sequence")
        self.radio_full_chapter.setChecked(True)
        self.radio_full_chapter.setCursor(Qt.PointingHandCursor)
        self.radio_full_chapter.setToolTip("Exports all pages in order: uses Cleaned image if page was cleaned, and Raw original if page had no bubbles.")

        self.radio_cleaned_only = QRadioButton(f"✨ Cleaned Pages Only ({cleaned_count} pages)")
        self.radio_cleaned_only.setCursor(Qt.PointingHandCursor)

        self.radio_raw_only = QRadioButton(f"📄 Raw Original Pages Only ({total_count} pages)")
        self.radio_raw_only.setCursor(Qt.PointingHandCursor)

        self.scope_btn_group = QButtonGroup(self)
        self.scope_btn_group.addButton(self.radio_full_chapter, 0)
        self.scope_btn_group.addButton(self.radio_cleaned_only, 1)
        self.scope_btn_group.addButton(self.radio_raw_only, 2)

        scope_layout.addWidget(self.radio_full_chapter)
        scope_layout.addWidget(self.radio_cleaned_only)
        scope_layout.addWidget(self.radio_raw_only)
        layout.addWidget(scope_group)

        # 2. Destination & Package Format
        dest_group = QGroupBox("📁 2. Output Destination & Type")
        dest_group.setStyleSheet("QGroupBox { color: #38bdf8; font-weight: bold; border: 1px solid #1e293b; border-radius: 8px; margin-top: 10px; padding: 12px; }")
        dest_layout = QVBoxLayout(dest_group)
        dest_layout.setSpacing(8)

        row_type = QHBoxLayout()
        self.radio_type_folder = QRadioButton("📁 Folder")
        self.radio_type_folder.setChecked(True)
        self.radio_type_folder.setCursor(Qt.PointingHandCursor)
        self.radio_type_zip = QRadioButton("🗜️ ZIP Archive (.zip)")
        self.radio_type_zip.setCursor(Qt.PointingHandCursor)

        self.type_btn_group = QButtonGroup(self)
        self.type_btn_group.addButton(self.radio_type_folder, 0)
        self.type_btn_group.addButton(self.radio_type_zip, 1)

        row_type.addWidget(self.radio_type_folder)
        row_type.addWidget(self.radio_type_zip)
        dest_layout.addLayout(row_type)

        row_path = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Select output folder or archive destination...")
        if self.default_out_dir:
            self.path_input.setText(self.default_out_dir)
        
        browse_btn = QPushButton("📁 Browse...")
        browse_btn.setFixedWidth(90)
        browse_btn.setStyleSheet("background: #1e293b; color: #38bdf8; border: 1px solid #0284c7; border-radius: 6px; padding: 4px 8px; font-weight: bold;")
        browse_btn.clicked.connect(self.browse_destination)

        row_path.addWidget(self.path_input, stretch=1)
        row_path.addWidget(browse_btn)
        dest_layout.addLayout(row_path)
        layout.addWidget(dest_group)

        # 3. File Naming & Image Format
        options_group = QGroupBox("🏷️ 3. Naming & Format")
        options_group.setStyleSheet("QGroupBox { color: #38bdf8; font-weight: bold; border: 1px solid #1e293b; border-radius: 8px; margin-top: 10px; padding: 12px; }")
        opt_layout = QHBoxLayout(options_group)
        opt_layout.setSpacing(12)

        # Naming style
        v_naming = QVBoxLayout()
        v_naming.setSpacing(4)
        lbl_name = QLabel("🏷️ File Names:")
        lbl_name.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold;")
        self.combo_naming = QComboBox()
        self.combo_naming.addItems([
            "Original Names (001.png, 002.png) [Recommended]",
            "Add Suffix (001_clean.png)"
        ])
        v_naming.addWidget(lbl_name)
        v_naming.addWidget(self.combo_naming)
        opt_layout.addLayout(v_naming, stretch=1)

        # Image format
        v_fmt = QVBoxLayout()
        v_fmt.setSpacing(4)
        lbl_fmt = QLabel("🖼️ Image Format:")
        lbl_fmt.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold;")
        self.combo_fmt = QComboBox()
        self.combo_fmt.addItems([
            "Original Format (Keep source format)",
            "PNG (Lossless)",
            "PSD (Adobe Photoshop .psd) 🎨",
            "JPEG (High Quality 95%)",
            "WebP (Optimized)"
        ])
        v_fmt.addWidget(lbl_fmt)
        v_fmt.addWidget(self.combo_fmt)
        opt_layout.addLayout(v_fmt, stretch=1)
        layout.addWidget(options_group)

        # Bottom Action Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 6px; padding: 6px 16px; font-size: 11px;")
        cancel_btn.clicked.connect(self.reject)

        self.start_export_btn = QPushButton("🚀 Start Export")
        self.start_export_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #15803d, stop:1 #22c55e);
                color: white;
                border: 1px solid #4ade80;
                border-radius: 6px;
                padding: 6px 20px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover { background: #166534; }
        """)
        self.start_export_btn.clicked.connect(self.perform_export)

        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.start_export_btn)
        layout.addLayout(btn_box)

    def browse_destination(self):
        parent_dlg = self.parent()
        last_export = ""
        if parent_dlg and hasattr(parent_dlg, "get_last_dir"):
            last_export = parent_dlg.get_last_dir("last_export_dir", self.path_input.text() or "")
        else:
            last_export = self.path_input.text() or os.getcwd()

        if self.radio_type_folder.isChecked():
            folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder", last_export)
            if folder:
                self.path_input.setText(folder)
                if parent_dlg and hasattr(parent_dlg, "set_last_dir"):
                    parent_dlg.set_last_dir("last_export_dir", folder)
        elif self.radio_type_zip.isChecked():
            folder_name = ""
            if self.image_paths:
                folder_name = Path(self.image_paths[0]).parent.name
            zip_filename = f"{folder_name}.zip" if (folder_name and folder_name != ".") else "Chapter_Cleaned.zip"
            default_zip = os.path.join(last_export, zip_filename) if os.path.isdir(last_export) else zip_filename
            f_path, _ = QFileDialog.getSaveFileName(self, "Save Chapter ZIP Archive", default_zip, "ZIP Archive (*.zip)")
            if f_path:
                self.path_input.setText(f_path)
                if parent_dlg and hasattr(parent_dlg, "set_last_dir"):
                    parent_dlg.set_last_dir("last_export_dir", os.path.dirname(f_path))

    def perform_export(self):
        dest = self.path_input.text().strip()
        if not dest:
            QMessageBox.warning(self, "Destination Required", "Please select a destination folder or archive path.")
            return

        is_folder = self.radio_type_folder.isChecked()
        export_full = self.radio_full_chapter.isChecked()
        export_cleaned_only = self.radio_cleaned_only.isChecked()

        use_original_names = (self.combo_naming.currentIndex() == 0)
        fmt_choice = self.combo_fmt.currentIndex()  # 0: Orig, 1: PNG, 2: PSD, 3: JPG, 4: WebP

        import zipfile
        from PIL import Image

        try:
            if is_folder:
                os.makedirs(dest, exist_ok=True)
                zip_obj = None
            else:
                dest_dir = os.path.dirname(dest)
                if dest_dir:
                    os.makedirs(dest_dir, exist_ok=True)
                zip_obj = zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED)

            exported_count = 0
            for idx, img_p in enumerate(self.image_paths):
                clean_p = self.cleaned_pages.get(img_p)
                has_clean = (clean_p and os.path.exists(clean_p))

                if export_cleaned_only and not has_clean:
                    continue

                src_path = clean_p if has_clean else img_p
                stem = Path(img_p).stem
                orig_ext = Path(src_path).suffix or ".png"

                # Suffix decision
                if use_original_names:
                    base_name = stem
                else:
                    base_name = f"{stem}_clean" if has_clean else stem

                # Format decision: 0: Orig, 1: PNG, 2: PSD, 3: JPG, 4: WebP
                if fmt_choice == 1:
                    out_ext = ".png"
                elif fmt_choice == 2:
                    out_ext = ".psd"
                elif fmt_choice == 3:
                    out_ext = ".jpg"
                elif fmt_choice == 4:
                    out_ext = ".webp"
                else:
                    out_ext = orig_ext

                target_filename = f"{base_name}{out_ext}"

                # Image writing / conversion
                if fmt_choice == 2:  # PSD (Adobe Photoshop)
                    from psd_tools import PSDImage
                    pil_img = Image.open(src_path)
                    psd = PSDImage.frompil(pil_img)
                    if is_folder:
                        out_file_path = os.path.join(dest, target_filename)
                        psd.save(out_file_path)
                    else:
                        import io
                        buf = io.BytesIO()
                        psd.save(buf)
                        zip_obj.writestr(target_filename, buf.getvalue())

                elif fmt_choice in (1, 3, 4) or (out_ext.lower() != orig_ext.lower()):
                    pil_img = Image.open(src_path)
                    if out_ext.lower() in (".jpg", ".jpeg"):
                        pil_img = pil_img.convert("RGB")

                    if is_folder:
                        out_file_path = os.path.join(dest, target_filename)
                        pil_img.save(out_file_path, quality=95)
                    else:
                        import io
                        buf = io.BytesIO()
                        pil_fmt = "PNG" if out_ext == ".png" else ("JPEG" if out_ext in (".jpg", ".jpeg") else "WEBP")
                        pil_img.save(buf, format=pil_fmt, quality=95)
                        zip_obj.writestr(target_filename, buf.getvalue())
                else:
                    if is_folder:
                        out_file_path = os.path.join(dest, target_filename)
                        shutil.copy2(src_path, out_file_path)
                    else:
                        zip_obj.write(src_path, arcname=target_filename)

                exported_count += 1

            if zip_obj:
                zip_obj.close()

            dest_label = dest if is_folder else Path(dest).name
            QMessageBox.information(
                self,
                "Export Complete",
                f"✅ Successfully exported {exported_count} page(s) to:\n{dest_label}"
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed during export:\n{e}")


class MultiPageReviewDialog(QDialog):
    """
    Studio Dialog managing all manga pages in the active batch:
    - Sidebar page list with Cleaned/Raw badges.
    - Stacked SinglePageReviewWidget for the active page.
    - Batch inpainting for checked pages.
    - Export all cleaned images to folder/archive.
    - Save/Load cleaner project state (.cln / .ftr).
    """
    def __init__(self, page_results: dict, output_dir: str, parent=None, cleaned_pages: dict = None, iopaint_url: str = None, iopaint_model: str = None, iopaint_dilation: int = 5, mask_padding: int = 0):
        super().__init__(parent)
        self.setWindowTitle("⚡ SmartCleaner-AI Studio - Multi-Page Manga Inpainting Hub")
        self.setWindowFlags(Qt.Window | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        self.resize(1380, 860)
        self.setLayoutDirection(Qt.LeftToRight)
        self.setStyleSheet(DARK_NAVY_STYLESHEET)

        self.config_file = Path(__file__).parent / "gui_config.json"
        self.config = self.load_config()
        self.shortcuts = dict(DEFAULT_SHORTCUTS)
        if "shortcuts" in self.config and isinstance(self.config["shortcuts"], dict):
            self.shortcuts.update(self.config["shortcuts"])

        self.page_results = page_results
        self.output_dir = output_dir or ""
        self.cleaned_pages = dict(cleaned_pages) if cleaned_pages else {}
        self.iopaint_url = iopaint_url or "http://127.0.0.1:8080"
        self.iopaint_model = iopaint_model or "anime-lama"
        self.iopaint_dilation = iopaint_dilation
        self.mask_padding = mask_padding if mask_padding > 0 else iopaint_dilation
        self.image_paths = list(page_results.keys())
        self.page_widgets = {}
        self.active_shortcuts = []
        self._active_workers = []

        self.init_ui()
        self.setup_global_shortcuts()
        self.installEventFilter(self)

    def _cleanup(self):
        try:
            self.removeEventFilter(self)
        except Exception:
            pass
        for w in list(self.page_widgets.values()):
            try:
                w.stop_all_workers()
            except Exception:
                pass
        for w in list(self._active_workers):
            try:
                if hasattr(w, "cancel"):
                    w.cancel()
                w.finished_signal.disconnect()
            except Exception:
                pass
        self._active_workers.clear()

    def closeEvent(self, event):
        self._cleanup()
        super().closeEvent(event)

    def done(self, r):
        self._cleanup()
        super().done(r)

    def reject(self):
        self._cleanup()
        super().reject()

    def accept(self):
        self._cleanup()
        super().accept()

    def __del__(self):
        self._cleanup()

    def load_config(self) -> dict:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_last_dir(self, key: str, fallback: str = "") -> str:
        val = self.config.get(key, fallback)
        if val and os.path.exists(val):
            return val if os.path.isdir(val) else os.path.dirname(val)
        return fallback or os.getcwd()

    def set_last_dir(self, key: str, path: str):
        if path:
            dir_path = path if os.path.isdir(path) else os.path.dirname(path)
            if os.path.exists(dir_path):
                self.config[key] = dir_path
                self.save_config()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # Header Info Bar
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #0f172a; border: 1px solid #1e293b; border-radius: 10px; padding: 4px 10px;")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(10)

        header_title = QLabel("⚡ SmartCleaner-AI")
        header_title.setFont(QFont("Segoe UI", 12, QFont.Bold))
        header_title.setStyleSheet("color: #38bdf8; background: transparent; border: none;")
        header_layout.addWidget(header_title)

        self.active_page_badge = QLabel(f"📄 Page 01 / {len(self.image_paths):02d}")
        self.active_page_badge.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.active_page_badge.setStyleSheet("color: #94a3b8; background: #1e293b; border: 1px solid #334155; padding: 3px 10px; border-radius: 6px;")
        header_layout.addWidget(self.active_page_badge)

        header_layout.addStretch()

        # Shortcuts Settings Button
        self.shortcuts_btn = QPushButton("⚙️ Shortcuts")
        self.shortcuts_btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.shortcuts_btn.setStyleSheet("background: #1e293b; color: #38bdf8; padding: 4px 12px; border-radius: 6px; border: 1px solid #0284c7;")
        self.shortcuts_btn.clicked.connect(self.open_shortcuts_dialog)
        header_layout.addWidget(self.shortcuts_btn)

        main_layout.addWidget(header_frame)

        # Splitter (Sidebar + Stacked Page Viewers)
        splitter = QSplitter(Qt.Horizontal)

        # Sidebar
        sidebar_container = QWidget()
        sidebar_container.setMaximumWidth(260)
        s_layout = QVBoxLayout(sidebar_container)
        s_layout.setContentsMargins(0, 0, 0, 0)
        s_layout.setSpacing(6)

        header_s_row = QHBoxLayout()
        self.lbl_p = QLabel(f"📚 Pages ({len(self.image_paths)}):")
        self.lbl_p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.lbl_p.setStyleSheet("color: #38bdf8;")
        header_s_row.addWidget(self.lbl_p)
        header_s_row.addStretch()

        btn_sel_all = QPushButton("☑️ All")
        btn_sel_all.clicked.connect(lambda: self.set_all_pages_checked(True))
        btn_sel_none = QPushButton("⬜ None")
        btn_sel_none.clicked.connect(lambda: self.set_all_pages_checked(False))
        btn_invert = QPushButton("🔄 Inv")
        btn_invert.clicked.connect(self.invert_pages_selection)

        for b in (btn_sel_all, btn_sel_none, btn_invert):
            b.setFont(QFont("Segoe UI", 8, QFont.Bold))
            b.setStyleSheet("background: #1e293b; color: #cbd5e1; border: 1px solid #334155; border-radius: 4px; padding: 2px 6px;")
            header_s_row.addWidget(b)

        s_layout.addLayout(header_s_row)

        self.page_search_input = QLineEdit()
        self.page_search_input.setPlaceholderText("🔍 Filter pages...")
        self.page_search_input.setFixedHeight(28)
        self.page_search_input.textChanged.connect(self.filter_pages)
        s_layout.addWidget(self.page_search_input)

        self.page_list = QListWidget()
        self.page_list.setFont(QFont("Segoe UI", 10))
        self.populate_page_list()
        self.page_list.currentRowChanged.connect(self.on_page_selected)
        s_layout.addWidget(self.page_list, 1)

        # Stacked Pages (Lazy loaded on-demand for instantaneous dialog opening <0.05s)
        self.stacked_widget = QStackedWidget()
        self.page_widgets = {}
        if self.image_paths:
            self._get_or_create_page_widget(0)

        splitter.addWidget(sidebar_container)
        splitter.addWidget(self.stacked_widget)
        splitter.setSizes([240, 1140])
        main_layout.addWidget(splitter, 1)

        # Bottom Action Bar
        bottom_frame = QFrame()
        bottom_frame.setStyleSheet("background-color: #0f172a; border: 1px solid #1e293b; border-radius: 10px; padding: 4px;")
        btn_row = QHBoxLayout(bottom_frame)
        btn_row.setContentsMargins(8, 6, 8, 6)
        btn_row.setSpacing(8)

        self.save_proj_btn = QPushButton("💾 Save Project (.cln)")
        self.save_proj_btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.save_proj_btn.setMinimumHeight(38)
        self.save_proj_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #15803d, stop:1 #22c55e); color: white; padding: 6px 14px; border-radius: 6px; border: 1px solid #4ade80; }
            QPushButton:hover { background: #166534; }
        """)
        self.save_proj_btn.clicked.connect(self.save_project_state)
        btn_row.addWidget(self.save_proj_btn)

        self.batch_clean_btn = QPushButton("🧹 Inpaint Checked Pages")
        self.batch_clean_btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.batch_clean_btn.setMinimumHeight(38)
        self.batch_clean_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0ea5e9); color: white; padding: 6px 14px; border-radius: 6px; border: 1px solid #38bdf8; }
            QPushButton:hover { background: #0369a1; }
        """)
        self.batch_clean_btn.clicked.connect(self.batch_inpaint_checked_pages)
        btn_row.addWidget(self.batch_clean_btn)

        btn_row.addStretch()

        self.export_current_img_btn = QPushButton("🖼️ Export Active Image")
        self.export_current_img_btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.export_current_img_btn.setMinimumHeight(38)
        self.export_current_img_btn.setStyleSheet("""
            QPushButton { background: #042f2e; color: #2dd4bf; padding: 6px 12px; border-radius: 6px; border: 1px solid #0d9488; }
            QPushButton:hover { background: #115e59; color: #99f6e4; }
        """)
        self.export_current_img_btn.clicked.connect(self.export_current_page_image)
        btn_row.addWidget(self.export_current_img_btn)

        self.export_all_clean_btn = QPushButton("📦 Export Chapter Images...")
        self.export_all_clean_btn.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.export_all_clean_btn.setMinimumHeight(38)
        self.export_all_clean_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7e22ce, stop:1 #a855f7); color: white; padding: 6px 16px; border-radius: 6px; border: 1px solid #c084fc; }
            QPushButton:hover { background: #6b21a8; }
        """)
        self.export_all_clean_btn.clicked.connect(self.export_all_cleaned_pages)
        btn_row.addWidget(self.export_all_clean_btn)

        main_layout.addWidget(bottom_frame)

    def populate_page_list(self):
        self.page_list.clear()
        for idx, img_p in enumerate(self.image_paths):
            p_name = Path(img_p).stem
            num_b = len(self.page_results.get(img_p, []))
            clean_icon = "✨" if (self.cleaned_pages.get(img_p) and os.path.exists(self.cleaned_pages[img_p])) else "📄"
            item = QListWidgetItem(f"{clean_icon} Page {idx+1:02d} ({p_name}) [{num_b}]")
            item.setData(Qt.UserRole, img_p)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.page_list.addItem(item)

    def filter_pages(self, query: str):
        query = query.strip().lower()
        for i in range(self.page_list.count()):
            item = self.page_list.item(i)
            item.setHidden(bool(query and query not in item.text().lower()))

    def set_all_pages_checked(self, checked: bool):
        st = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.page_list.count()):
            self.page_list.item(i).setCheckState(st)

    def invert_pages_selection(self):
        for i in range(self.page_list.count()):
            item = self.page_list.item(i)
            item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def on_child_padding_changed(self, val: int):
        self.mask_padding = int(val)
        for w in self.page_widgets.values():
            if w.mask_padding != val:
                w.mask_padding = int(val)
                w.padding_spin.blockSignals(True)
                w.padding_spin.setValue(int(val))
                w.padding_spin.blockSignals(False)

    def _get_or_create_page_widget(self, index: int):
        if not (0 <= index < len(self.image_paths)):
            return None
        img_p = self.image_paths[index]
        if img_p not in self.page_widgets:
            items = self.page_results.get(img_p, [])
            clean_p = self.cleaned_pages.get(img_p, None)
            p_widget = SinglePageReviewWidget(
                img_p, items,
                parent=self,
                cleaned_image_path=clean_p,
                iopaint_url=self.iopaint_url,
                iopaint_model=self.iopaint_model,
                iopaint_dilation=self.iopaint_dilation,
                mask_padding=self.mask_padding
            )
            p_widget.padding_changed.connect(self.on_child_padding_changed)
            self.page_widgets[img_p] = p_widget
            self.stacked_widget.addWidget(p_widget)
        return self.page_widgets[img_p]

    def on_page_selected(self, row: int):
        if 0 <= row < len(self.image_paths):
            w = self._get_or_create_page_widget(row)
            if w:
                self.stacked_widget.setCurrentWidget(w)
            self.active_page_badge.setText(f"📄 Page {row+1:02d} / {len(self.image_paths):02d}")

    def export_current_page_image(self):
        cur_widget = self.stacked_widget.currentWidget()
        if isinstance(cur_widget, SinglePageReviewWidget):
            cur_widget.export_current_image()

    def export_all_cleaned_pages(self):
        # Sync latest cleaned paths from single page widgets
        for img_p, w in self.page_widgets.items():
            if w.cleaned_image_path and os.path.exists(w.cleaned_image_path):
                self.cleaned_pages[img_p] = w.cleaned_image_path

        dlg = ExportOptionsDialog(
            image_paths=self.image_paths,
            cleaned_pages=self.cleaned_pages,
            default_out_dir=self.output_dir,
            parent=self
        )
        dlg.exec()

    def batch_inpaint_checked_pages(self):
        to_clean = {}
        for idx in range(self.page_list.count()):
            item = self.page_list.item(idx)
            if item.checkState() == Qt.Checked:
                img_p = item.data(Qt.UserRole)
                to_clean[img_p] = self.page_results.get(img_p, [])

        if not to_clean:
            QMessageBox.warning(self, "No Pages Checked", "Please check at least one page to clean.")
            return

        prog = QProgressDialog("🧹 Batch inpainting pages...", "Cancel", 0, len(to_clean), self)
        prog.setWindowTitle("Batch Inpainting")
        prog.setWindowModality(Qt.WindowModal)
        prog.setStyleSheet(DARK_NAVY_STYLESHEET)
        prog.show()

        worker = BatchPageInpaintWorker(
            pages_dict=to_clean,
            server_url=self.iopaint_url,
            model=self.iopaint_model,
            dilation=max(self.iopaint_dilation, self.mask_padding),
            padding=self.mask_padding,
            adaptive_mode=True,
            parent=None
        )
        track_running_worker(worker)
        if not hasattr(self, "_active_workers"):
            self._active_workers = []
        self._active_workers.append(worker)
        prog.canceled.connect(worker.cancel)

        def _on_prog(cur, tot, msg):
            prog.setValue(cur)
            prog.setLabelText(msg)

        def _on_done(res):
            try:
                prog.close()
                self.cleaned_pages.update(res)
                self.populate_page_list()
                for img_p, clean_p in res.items():
                    if img_p in self.page_widgets:
                        self.page_widgets[img_p].cleaned_image_path = clean_p
                        self.page_widgets[img_p].toggle_cleaned_view(True)
                QMessageBox.information(self, "Inpainting Complete", f"✨ Cleaned {len(res)} pages successfully!")
            finally:
                if worker in self._active_workers:
                    self._active_workers.remove(worker)

        worker.progress_signal.connect(_on_prog)
        worker.finished_signal.connect(_on_done)
        worker.start()

    def save_project_state(self):
        start_dir = self.get_last_dir("last_project_dir", "")
        folder_name = ""
        if self.image_paths:
            folder_name = Path(self.image_paths[0]).parent.name
        proj_filename = f"{folder_name}.cln" if (folder_name and folder_name != ".") else "project.cln"
        default_file = os.path.join(start_dir, proj_filename) if start_dir else proj_filename
        file_path, _ = QFileDialog.getSaveFileName(self, "Save SmartCleaner-AI Project", default_file, "SmartCleaner-AI Project (*.cln *.ftr)")
        if not file_path:
            return
        self.set_last_dir("last_project_dir", os.path.dirname(file_path))

        project_data = {
            "page_results": self.page_results,
            "output_dir": self.output_dir,
            "cleaned_pages": self.cleaned_pages,
            "iopaint_url": self.iopaint_url,
            "iopaint_model": self.iopaint_model,
            "iopaint_dilation": self.iopaint_dilation,
            "mask_padding": self.mask_padding
        }
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(project_data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Saved", f"Project saved successfully to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save project:\n{e}")

    def open_shortcuts_dialog(self):
        dlg = ShortcutsSettingsDialog(self.shortcuts, self)
        if dlg.exec() == QDialog.Accepted:
            self.shortcuts = dlg.get_shortcuts()
            self.config["shortcuts"] = self.shortcuts
            self.save_config()
            self.setup_global_shortcuts()

    def get_active_review_widget(self):
        cur = self.stacked_widget.currentWidget()
        if isinstance(cur, SinglePageReviewWidget):
            return cur
        return None

    def setup_global_shortcuts(self):
        # Clear existing shortcuts
        for sc in self.active_shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self.active_shortcuts.clear()

        def _add_sc(key_str, callback):
            if not key_str:
                return
            try:
                sc = QShortcut(QKeySequence(key_str), self)
                sc.setContext(Qt.WindowShortcut)
                sc.activated.connect(callback)
                self.active_shortcuts.append(sc)
            except Exception:
                pass

        for act, def_k in DEFAULT_SHORTCUTS.items():
            k_val = self.shortcuts.get(act, def_k)
            if k_val:
                _add_sc(k_val, lambda a=act: self.execute_shortcut_action(a))

        # Fallback aliases
        _add_sc("Backspace", lambda: self.execute_shortcut_action("delete_bubble"))
        _add_sc("Del", lambda: self.execute_shortcut_action("delete_bubble"))
        _add_sc("=", lambda: self.execute_shortcut_action("zoom_in"))

    def execute_shortcut_action(self, action_name: str):
        focused = QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return

        cur = self.get_active_review_widget()
        if not cur:
            return

        if action_name == "toggle_cleaned":
            cur.toggle_cleaned_view()
        elif action_name == "toggle_masks":
            cur.toggle_masks_view()
        elif action_name == "magic_wand":
            cur.toggle_magic_wand(not cur.magic_wand_btn.isChecked())
        elif action_name == "brush_tool":
            cur.toggle_brush_tool(not cur.brush_tool_btn.isChecked())
        elif action_name == "lasso_tool":
            cur.toggle_lasso_tool(not cur.lasso_tool_btn.isChecked())
        elif action_name == "pan_tool":
            cur.toggle_pan_tool(True)
        elif action_name == "draw_box":
            cur.toggle_add_bubble(not cur.add_bubble_btn.isChecked())
        elif action_name == "delete_bubble":
            cur.delete_selected_bubble()
        elif action_name == "inpaint_bubble":
            cur.inpaint_selected_bubble()
        elif action_name == "inpaint_page":
            cur.inpaint_active_page()
        elif action_name == "next_bubble":
            if cur.table.rowCount() > 0:
                row = cur.table.currentRow()
                nxt = min(cur.table.rowCount() - 1, row + 1 if row >= 0 else 0)
                cur.table.selectRow(nxt)
        elif action_name == "prev_bubble":
            if cur.table.rowCount() > 0:
                row = cur.table.currentRow()
                prv = max(0, row - 1 if row >= 0 else 0)
                cur.table.selectRow(prv)
        elif action_name == "next_page":
            idx = self.stacked_widget.currentIndex()
            if idx < len(self.image_paths) - 1:
                self.page_list.setCurrentRow(idx + 1)
        elif action_name == "prev_page":
            idx = self.stacked_widget.currentIndex()
            if idx > 0:
                self.page_list.setCurrentRow(idx - 1)
        elif action_name == "zoom_in":
            cur.page_viewer.zoom_in()
        elif action_name == "zoom_out":
            cur.page_viewer.zoom_out()
        elif action_name == "fit_view":
            cur.page_viewer.reset_fit()
        elif action_name == "zoom_100":
            cur.page_viewer.reset_100()
        elif action_name == "export_image":
            cur.export_current_image()
        elif action_name == "export_all":
            self.export_all_cleaned_pages()
        elif action_name == "save_project":
            self.save_project_state()

    def eventFilter(self, obj, event):
        try:
            if not self.isVisible():
                return False

            if event.type() == QEvent.KeyPress:
                # Only intercept if event belongs to this dialog or its children
                if isinstance(obj, QWidget) and (obj is self or self.isAncestorOf(obj)):
                    focused = QApplication.focusWidget()
                    if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
                        return False

                    key = event.key()
                    modifiers = event.modifiers()
                    parts = []
                    if modifiers & Qt.ControlModifier:
                        parts.append("Ctrl")
                    if modifiers & Qt.ShiftModifier:
                        parts.append("Shift")
                    if modifiers & Qt.AltModifier:
                        parts.append("Alt")

                    special_keys = {
                        Qt.Key_Delete: "Delete",
                        Qt.Key_Backspace: "Delete",
                        Qt.Key_Return: "Enter",
                        Qt.Key_Enter: "Enter",
                        Qt.Key_Space: "Space",
                        Qt.Key_Tab: "Tab",
                        Qt.Key_Left: "Left",
                        Qt.Key_Right: "Right",
                        Qt.Key_Up: "Up",
                        Qt.Key_Down: "Down",
                        Qt.Key_PageUp: "PageUp",
                        Qt.Key_PageDown: "PageDown",
                        Qt.Key_Plus: "+",
                        Qt.Key_Minus: "-",
                        Qt.Key_Equal: "+",
                    }

                    key_name = special_keys.get(key, "")
                    if not key_name:
                        if Qt.Key_A <= key <= Qt.Key_Z:
                            key_name = chr(key)
                        elif Qt.Key_0 <= key <= Qt.Key_9:
                            key_name = chr(key)
                        elif Qt.Key_F1 <= key <= Qt.Key_F12:
                            key_name = f"F{key - Qt.Key_F1 + 1}"
                        else:
                            seq = QKeySequence(key).toString()
                            key_name = seq if seq else ""

                    if not key_name and event.text():
                        txt = event.text().strip().upper()
                        if len(txt) == 1 and "A" <= txt <= "Z":
                            key_name = txt

                    if key_name and key_name not in parts:
                        parts.append(key_name)

                    key_str = "+".join(parts).upper()

                    # Check matches against self.shortcuts
                    matched_action = None
                    for act, sc in self.shortcuts.items():
                        if sc and sc.strip().upper() == key_str:
                            matched_action = act
                            break

                    # Fallback aliases
                    if not matched_action:
                        if key_str in ("SPACE", " "):
                            matched_action = "toggle_cleaned"
                        elif key_str in ("M",):
                            matched_action = "toggle_masks"
                        elif key_str in ("W",):
                            matched_action = "magic_wand"
                        elif key_str in ("B",):
                            matched_action = "brush_tool"
                        elif key_str in ("L",):
                            matched_action = "lasso_tool"
                        elif key_str in ("A",):
                            matched_action = "draw_box"
                        elif key_str in ("C",):
                            matched_action = "inpaint_page"
                        elif key_str in ("DELETE", "BACKSPACE", "DEL"):
                            matched_action = "delete_bubble"
                        elif key_str in ("F",):
                            matched_action = "fit_view"
                        elif key_str in ("1",):
                            matched_action = "zoom_100"
                        elif key_str in ("+", "="):
                            matched_action = "zoom_in"
                        elif key_str in ("-", "_"):
                            matched_action = "zoom_out"
                        elif key_str in ("RIGHT", "D"):
                            matched_action = "next_page"
                        elif key_str in ("LEFT", "Q"):
                            matched_action = "prev_page"
                        elif key_str in ("DOWN", "S"):
                            matched_action = "next_bubble"
                        elif key_str in ("UP", "Z"):
                            matched_action = "prev_bubble"

                    if matched_action:
                        self.execute_shortcut_action(matched_action)
                        return True
        except Exception:
            return False

        return False

    def keyPressEvent(self, event: QKeyEvent):
        focused = QApplication.focusWidget()
        if isinstance(focused, (QLineEdit, QTextEdit, QPlainTextEdit)):
            super().keyPressEvent(event)
            return

        key = event.key()
        modifiers = event.modifiers()
        parts = []
        if modifiers & Qt.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.AltModifier:
            parts.append("Alt")

        special_keys = {
            Qt.Key_Delete: "Delete",
            Qt.Key_Backspace: "Backspace",
            Qt.Key_Return: "Enter",
            Qt.Key_Enter: "Enter",
            Qt.Key_Space: "Space",
            Qt.Key_Tab: "Tab",
            Qt.Key_Left: "Left",
            Qt.Key_Right: "Right",
            Qt.Key_Up: "Up",
            Qt.Key_Down: "Down",
            Qt.Key_Plus: "+",
            Qt.Key_Minus: "-",
            Qt.Key_Equal: "=",
        }

        key_name = special_keys.get(key, "")
        if not key_name:
            if Qt.Key_A <= key <= Qt.Key_Z:
                key_name = chr(key)
            elif Qt.Key_0 <= key <= Qt.Key_9:
                key_name = chr(key)
            elif Qt.Key_F1 <= key <= Qt.Key_F12:
                key_name = f"F{key - Qt.Key_F1 + 1}"
            else:
                seq = QKeySequence(key).toString()
                key_name = seq if seq else ""

        if not key_name and event.text():
            txt = event.text().strip().upper()
            if len(txt) == 1 and "A" <= txt <= "Z":
                key_name = txt

        if key_name and key_name not in parts:
            parts.append(key_name)

        key_str = "+".join(parts).upper()

        matched_action = None
        for act, sc in self.shortcuts.items():
            if sc and sc.strip().upper() == key_str:
                matched_action = act
                break

        if not matched_action:
            if key_str in ("SPACE", " "):
                matched_action = "toggle_cleaned"
            elif key_str in ("M",):
                matched_action = "toggle_masks"
            elif key_str in ("W",):
                matched_action = "magic_wand"
            elif key_str in ("B",):
                matched_action = "brush_tool"
            elif key_str in ("L",):
                matched_action = "lasso_tool"
            elif key_str in ("H",):
                matched_action = "pan_tool"
            elif key_str in ("A",):
                matched_action = "draw_box"
            elif key_str in ("C",):
                matched_action = "inpaint_page"
            elif key_str in ("DELETE", "BACKSPACE", "DEL"):
                matched_action = "delete_bubble"
            elif key_str in ("F",):
                matched_action = "fit_view"
            elif key_str in ("1",):
                matched_action = "zoom_100"
            elif key_str in ("+", "="):
                matched_action = "zoom_in"
            elif key_str in ("-", "_"):
                matched_action = "zoom_out"
            elif key_str in ("RIGHT", "D"):
                matched_action = "next_page"
            elif key_str in ("LEFT", "Q"):
                matched_action = "prev_page"
            elif key_str in ("DOWN", "S"):
                matched_action = "next_bubble"
            elif key_str in ("UP", "Z"):
                matched_action = "prev_bubble"

        if matched_action:
            self.execute_shortcut_action(matched_action)
            event.accept()
            return

        super().keyPressEvent(event)


class PreloadWorker(QThread):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            if not self._is_cancelled:
                from fast_cleaner import get_text_detector
                get_text_detector()
        except Exception:
            pass


class ServerMonitorWorker(QThread):
    status_signal = Signal(bool, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            if self._is_cancelled:
                return
            server_up = is_server_online(8000)
            if self._is_cancelled:
                return
            active_url = get_active_ngrok_url() if server_up else ""
            lan_ip = get_local_ip()
            if not self._is_cancelled:
                self.status_signal.emit(server_up, active_url or "", lan_ip)
        except Exception:
            pass


class NgrokServiceInstallerWorker(QThread):
    """Worker to download ngrok, configure authtoken, and launch the service in background."""
    progress_signal = Signal(str, float)
    finished_signal = Signal(bool, str, str)  # (success, public_url, message)

    def __init__(self, authtoken: str, domain: str = "", port: int = 8000, parent=None):
        super().__init__(parent)
        self.authtoken = authtoken
        self.domain = domain
        self.port = port

    def run(self):
        try:
            def _prog(msg, pct):
                self.progress_signal.emit(msg, pct)
            ok, url, msg = setup_and_activate_ngrok_service(
                authtoken=self.authtoken,
                domain=self.domain,
                port=self.port,
                progress_callback=_prog
            )
            self.finished_signal.emit(ok, url, msg)
        except Exception as e:
            self.finished_signal.emit(False, "", f"خطأ غير متوقع أثناء تثبيت الخدمة: {str(e)}")


class BatchCleanerWorker(QThread):
    progress_signal = Signal(str)
    overall_progress_signal = Signal(int, int, str)
    current_progress_signal = Signal(int, int, str)
    finished_signal = Signal(bool, object)

    def __init__(self, image_paths: list, mask_padding: int = 0, snap_to_bubbles: bool = False, iopaint_enabled: bool = True, iopaint_url: str = "http://127.0.0.1:8080", iopaint_model: str = "anime-lama", iopaint_dilation: int = 5, iopaint_adaptive: bool = True, device: str = "auto", parent=None):
        super().__init__(parent)
        self.image_paths = image_paths
        self.mask_padding = mask_padding
        self.snap_to_bubbles = snap_to_bubbles
        self.iopaint_enabled = iopaint_enabled
        self.iopaint_url = iopaint_url
        self.iopaint_model = iopaint_model
        self.iopaint_dilation = iopaint_dilation
        self.iopaint_adaptive = iopaint_adaptive
        self.device = device
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            from fast_cleaner import detect_bubbles_for_cleaning
            total_pages = len(self.image_paths)
            page_results = {}
            cleaned_images = {}
            client = IOPaintClient(self.iopaint_url) if self.iopaint_enabled else None

            for idx, img_p in enumerate(self.image_paths):
                if self._is_cancelled:
                    self.finished_signal.emit(False, "Cancelled by user")
                    return

                p_name = Path(img_p).name
                self.overall_progress_signal.emit(idx, total_pages, f"Processing page {idx+1}/{total_pages}: {p_name}")
                self.current_progress_signal.emit(10, 100, f"Scanning {p_name}...")
                self.progress_signal.emit(f"🔍 [Page {idx+1}/{total_pages}] Detecting speech bubbles on {p_name}...")

                def on_detector_progress(msg):
                    if not self._is_cancelled:
                        if msg.startswith("CHUNK_PROGRESS:"):
                            try:
                                _, prog_str, txt = msg.split(":", 2)
                                curr, tot = map(int, prog_str.split("/"))
                                step_pct = int(10 + (curr / max(1, tot)) * 40)
                                self.current_progress_signal.emit(step_pct, 100, f"Analyzing {p_name} (Part {curr}/{tot})...")
                            except:
                                pass
                        else:
                            self.progress_signal.emit(f"[{idx+1}/{total_pages}] {msg}")

                bubbles = detect_bubbles_for_cleaning(
                    image_path=img_p,
                    mask_padding=self.mask_padding,
                    snap_to_bubbles=self.snap_to_bubbles,
                    device=self.device,
                    progress_callback=on_detector_progress,
                    cancel_callback=lambda: self._is_cancelled
                )
                page_results[img_p] = bubbles

                self.current_progress_signal.emit(50, 100, f"Found {len(bubbles)} bubble(s)")
                self.progress_signal.emit(f"✅ [Page {idx+1}/{total_pages}] Detected {len(bubbles)} bubbles on {p_name}.")

                if bubbles:
                    if self.iopaint_enabled and client:
                        self.progress_signal.emit(f"🧹 [Page {idx+1}/{total_pages}] Inpainting {len(bubbles)} bubbles ({self.iopaint_model})...")
                        self.current_progress_signal.emit(60, 100, f"Inpainting {len(bubbles)} bubbles...")

                        def on_inpaint_progress(msg_txt):
                            self.progress_signal.emit(f"🧹 {msg_txt}")

                        try:
                            if self.iopaint_adaptive:
                                cleaned_pil, stats = smart_adaptive_inpaint_page(
                                    server_url=self.iopaint_url,
                                    image_input=img_p,
                                    bubbles=bubbles,
                                    deep_model=self.iopaint_model,
                                    dilation=max(self.iopaint_dilation, self.mask_padding),
                                    padding=self.mask_padding,
                                    progress_callback=on_inpaint_progress
                                )
                                flat_n = stats.get("flat_count", 0)
                                comp_n = stats.get("complex_count", 0)
                                self.progress_signal.emit(f"✨ [Adaptive] {flat_n} white bubbles fast-filled, {comp_n} routed to AI.")
                            else:
                                cleaned_pil = inpaint_manga_page(
                                    server_url=self.iopaint_url,
                                    image_input=img_p,
                                    bubbles=bubbles,
                                    dilation=max(self.iopaint_dilation, self.mask_padding),
                                    padding=self.mask_padding,
                                    adaptive=False,
                                    deep_model=self.iopaint_model
                                )

                            stem = Path(img_p).stem
                            ext = Path(img_suffix if (img_suffix := Path(img_p).suffix) else ".png")
                            out_p = str(Path(img_p).parent / f"{stem}_clean{ext}")
                            cleaned_pil.save(out_p, quality=95)
                            cleaned_images[img_p] = out_p

                            for b in bubbles:
                                b["status"] = "cleaned"
                            self.progress_signal.emit(f"💾 Saved cleaned image to: {Path(out_p).name}")
                        except Exception as e:
                            self.progress_signal.emit(f"⚠️ IOPaint error on {p_name}: {e}")
                    else:
                        # Instant local fast cleaning (<0.02s per page)
                        self.progress_signal.emit(f"⚡ [Page {idx+1}/{total_pages}] Fast-cleaning {len(bubbles)} bubbles...")
                        try:
                            cv_img = cv2.imdecode(np.fromfile(img_p, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if cv_img is not None:
                                for b in bubbles:
                                    cv_img = clean_flat_bubble_locally(cv_img, b, classification="flat_white", dilation=self.iopaint_dilation)
                                    b["status"] = "cleaned"
                                stem = Path(img_p).stem
                                ext = Path(img_p).suffix or ".png"
                                out_p = str(Path(img_p).parent / f"{stem}_clean{ext}")
                                is_success, buf = cv2.imencode(ext, cv_img)
                                if is_success:
                                    buf.tofile(out_p)
                                    cleaned_images[img_p] = out_p
                                    self.progress_signal.emit(f"💾 Saved cleaned image to: {Path(out_p).name}")
                        except Exception as fe:
                            self.progress_signal.emit(f"⚠️ Fast cleaning notice: {fe}")

                self.current_progress_signal.emit(100, 100, f"Completed {p_name}")

            self.overall_progress_signal.emit(total_pages, total_pages, "All pages completed!")
            self.finished_signal.emit(True, (page_results, cleaned_images))
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class IOPaintProcessWorker(QThread):
    log_signal = Signal(str)
    started_signal = Signal(int)
    finished_signal = Signal(int)

    def __init__(self, cmd: list, cwd: str, silent: bool = True, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.cwd = cwd
        self.silent = silent
        self.proc = None
        self._is_stopped = False

    def run(self):
        import subprocess, sys
        creationflags = 0x08000000 if (self.silent and sys.platform == "win32") else 0
        startupinfo = None
        if self.silent and sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        try:
            self.proc = subprocess.Popen(
                self.cmd,
                cwd=self.cwd,
                creationflags=creationflags,
                startupinfo=startupinfo,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1
            )
            self.started_signal.emit(self.proc.pid)

            for line in iter(self.proc.stdout.readline, ""):
                if self._is_stopped:
                    break
                line_str = line.strip()
                if line_str:
                    self.log_signal.emit(f"⚙️ [IOPaint] {line_str}")

            self.proc.stdout.close()
            ret_code = self.proc.wait()
            self.finished_signal.emit(ret_code)

        except Exception as e:
            self.log_signal.emit(f"❌ [IOPaint Error] {e}")
            self.finished_signal.emit(-1)

    def terminate_process(self):
        self._is_stopped = True
        if self.proc:
            try:
                pid = self.proc.pid
                if sys.platform == "win32":
                    import subprocess
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        creationflags=0x08000000,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                else:
                    self.proc.terminate()
            except Exception:
                pass


class NvidiaCudaInstallWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(int, str)
    finished_signal = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        import subprocess, sys
        self.progress_signal.emit(10, "Checking NVIDIA GPU & PyTorch...")
        self.log_signal.emit("🔍 [NVIDIA CUDA Setup] Checking environment and hardware...")

        try:
            # 1. Run pip install torch torchvision with CUDA 12.1 / 11.8
            self.progress_signal.emit(30, "Downloading & Installing PyTorch with NVIDIA CUDA (cu121)...")
            self.log_signal.emit("⚡ [NVIDIA CUDA Setup] Installing PyTorch with CUDA support (--index-url https://download.pytorch.org/whl/cu121)...")
            
            cmd = [
                sys.executable, "-m", "pip", "install",
                "torch", "torchvision", "torchaudio",
                "--index-url", "https://download.pytorch.org/whl/cu121"
            ]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=0x08000000 if sys.platform == "win32" else 0
            )

            for line in iter(proc.stdout.readline, ""):
                line_str = line.strip()
                if line_str:
                    self.log_signal.emit(f"📦 [pip CUDA] {line_str}")

            proc.stdout.close()
            ret = proc.wait()

            if ret == 0:
                self.progress_signal.emit(90, "Verifying CUDA availability...")
                # Verify in a sub-check
                chk_cmd = [sys.executable, "-c", "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None')"]
                out = subprocess.check_output(chk_cmd, text=True).strip().splitlines()
                cuda_ok = out[0].strip() == "True"
                dev_name = out[1].strip() if len(out) > 1 else ""

                if cuda_ok:
                    self.progress_signal.emit(100, f"NVIDIA CUDA Ready ({dev_name})")
                    self.log_signal.emit(f"🎉 [NVIDIA CUDA Setup] Successfully installed & activated NVIDIA CUDA! Device: {dev_name}")
                    self.finished_signal.emit(True, f"CUDA Ready: {dev_name}")
                else:
                    self.progress_signal.emit(100, "PyTorch CUDA installed (No physical NVIDIA GPU detected)")
                    self.log_signal.emit("ℹ️ [NVIDIA CUDA Setup] PyTorch CUDA binaries installed successfully. If an NVIDIA GPU is attached, it will now be used automatically.")
                    self.finished_signal.emit(True, "PyTorch CUDA installed successfully!")
            else:
                self.log_signal.emit(f"❌ [NVIDIA CUDA Setup] pip exited with code {ret}")
                self.finished_signal.emit(False, f"Installation exited with code {ret}")

        except Exception as e:
            self.log_signal.emit(f"❌ [NVIDIA CUDA Setup Error] {e}")
            self.finished_signal.emit(False, str(e))


class CleanerGUI(QMainWindow):
    """
    Main Application Window for SmartCleaner-AI Studio.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("⚡ SmartCleaner-AI - Multi-Page Manga & Webtoon Inpainting")
        self.config_file = Path(__file__).parent / "gui_config.json"
        self.config = self.load_config()

        # Generous default window dimensions and smart screen centering
        self.setMinimumSize(960, 720)
        saved_w = self.config.get("window_width")
        saved_h = self.config.get("window_height")
        if saved_w and saved_h and saved_w >= 960 and saved_h >= 720:
            self.resize(saved_w, saved_h)
        else:
            try:
                screen_geo = QApplication.primaryScreen().availableGeometry()
                w = min(1140, int(screen_geo.width() * 0.88))
                h = min(890, int(screen_geo.height() * 0.90))
                self.resize(w, h)
                self.move(screen_geo.center().x() - w // 2, max(20, screen_geo.center().y() - h // 2))
            except Exception:
                self.resize(1140, 890)

        self.setLayoutDirection(Qt.LeftToRight)
        self.setStyleSheet(DARK_NAVY_STYLESHEET)
        self.selected_image_paths = []
        self.mask_padding = self.config.get("mask_padding", 0)
        self.worker = None
        self.iopaint_ping_worker = None
        self.iopaint_switch_worker = None
        self._server_worker = None

        self.eta_timer = QTimer(self)
        self.eta_timer.timeout.connect(self.update_eta_ticker)
        self.batch_start_time = None
        self.step_start_time = None
        self.total_batch_pages = 0
        self.completed_batch_pages = 0

        version_data = load_local_version_info()
        self.current_app_version = version_data.get("version", "1.0.0")

        self.init_ui()

        self.preload_thread = PreloadWorker(parent=None)
        track_running_worker(self.preload_thread)
        self.preload_thread.start()

        QTimer.singleShot(600, self.ping_iopaint_server)

        # Silent background update check on launch
        if version_data.get("auto_check_on_startup", True):
            QTimer.singleShot(3500, lambda: check_for_updates_gui(self, silent=True))


    def load_config(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get_last_dir(self, key: str, fallback: str = "") -> str:
        val = self.config.get(key, fallback)
        if val and os.path.exists(val):
            return val if os.path.isdir(val) else os.path.dirname(val)
        return fallback or os.getcwd()

    def set_last_dir(self, key: str, path: str):
        if path:
            dir_path = path if os.path.isdir(path) else os.path.dirname(path)
            if os.path.exists(dir_path):
                self.config[key] = dir_path
                self.save_config()

    def detect_nvidia_gpu_hardware(self) -> tuple:
        # 1. Try PyTorch CUDA if torch already imported
        if "torch" in sys.modules:
            try:
                import torch
                if torch.cuda.is_available():
                    return True, torch.cuda.get_device_name(0)
            except Exception:
                pass

        # 2. Check Windows Video Controllers via Registry & DLLs in <0.001s (zero process spawn)
        if sys.platform == "win32":
            try:
                has_nv_dll = os.path.exists(r"C:\Windows\System32\nvcuda.dll") or os.path.exists(r"C:\Windows\System32\nvapi64.dll")
                if not has_nv_dll:
                    return False, ""
                import winreg
                key_path = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
                    for i in range(winreg.QueryInfoKey(k)[0]):
                        sub = winreg.EnumKey(k, i)
                        if sub.isdigit():
                            with winreg.OpenKey(k, sub) as sk:
                                try:
                                    name, _ = winreg.QueryValueEx(sk, "DriverDesc")
                                    if any(w in name.lower() for w in ['nvidia', 'geforce', 'quadro', 'rtx', 'gtx', 'tesla']):
                                        return True, name
                                except Exception:
                                    pass
            except Exception:
                pass

        return False, ""

    def check_cuda_status(self):
        try:
            torch_mod = sys.modules.get("torch")
            cuda_avail = torch_mod.cuda.is_available() if (torch_mod and hasattr(torch_mod, "cuda")) else False

            # Use cached hardware detection if available, else do fast instant check
            cached = self.config.get("cached_gpu_info")
            if cached and isinstance(cached, dict):
                has_nvidia = cached.get("has_nvidia", False)
                gpu_name = cached.get("gpu_name", "")
            else:
                has_nvidia, gpu_name = self.detect_nvidia_gpu_hardware()
                self.config["cached_gpu_info"] = {"has_nvidia": has_nvidia, "gpu_name": gpu_name}
                self.save_config()

            if cuda_avail:
                dev_name = torch_mod.cuda.get_device_name(0) if torch_mod.cuda.device_count() > 0 else (gpu_name or "NVIDIA GPU")
                self.cuda_status_dot.setText("🟢")
                self.cuda_status_label.setText(f"NVIDIA CUDA Ready ({dev_name})")
                self.cuda_status_label.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
                self.cuda_install_btn.setText("✅ CUDA Active")
                self.cuda_install_btn.setStyleSheet("background: #064e3b; color: #6ee7b7; border: 1px solid #059669; border-radius: 6px; padding: 2px 10px; font-size: 11px;")
            elif has_nvidia:
                self.cuda_status_dot.setText("🟡")
                self.cuda_status_label.setText(f"NVIDIA GPU Detected ({gpu_name})")
                self.cuda_status_label.setStyleSheet("color: #facc15; font-size: 11px; font-weight: bold;")
                self.cuda_install_btn.setText("⚡ Install NVIDIA CUDA")
                self.cuda_install_btn.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #15803d, stop:1 #22c55e); color: white; border: 1px solid #4ade80; border-radius: 6px; padding: 2px 10px; font-size: 11px; font-weight: bold;")
            else:
                self.cuda_status_dot.setText("💻")
                self.cuda_status_label.setText("CPU Mode (Intel/AMD Optimized)")
                self.cuda_status_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
                self.cuda_install_btn.setText("💻 CPU Active (No NVIDIA GPU)")
                self.cuda_install_btn.setStyleSheet("background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 6px; padding: 2px 10px; font-size: 11px;")
        except Exception:
            self.cuda_status_dot.setText("⚪")
            self.cuda_status_label.setText("Status Unknown")

    def on_device_mode_changed(self, idx):
        modes = ["auto", "cuda", "cpu"]
        mode = modes[idx] if 0 <= idx < len(modes) else "auto"
        self.config["device_mode"] = mode
        self.save_config()
        self.log(f"🎮 Switched compute device mode to: {mode.upper()}")


    def start_nvidia_cuda_install(self):
        has_nvidia, gpu_name = self.detect_nvidia_gpu_hardware()
        if not has_nvidia:
            QMessageBox.information(
                self,
                "CPU Mode Active",
                "ℹ️ No dedicated NVIDIA GPU detected on this system (running on Intel / AMD CPU).\n\nThe application is currently running in high-performance CPU mode (ONNX & OpenCV acceleration) with zero extra packages required."
            )
            return

        reply = QMessageBox.question(
            self,
            "Install NVIDIA CUDA Support",
            f"NVIDIA GPU Detected: {gpu_name}\n\nThe application will download and install PyTorch with NVIDIA CUDA 12.1 in the background.\n\nWould you like to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        self.cuda_install_btn.setEnabled(False)
        self.cuda_status_dot.setText("⏳")
        self.cuda_status_label.setText("Installing CUDA...")
        self.cuda_status_label.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        self.log("🚀 Starting silent NVIDIA CUDA installation in background...")

        self.cuda_worker = NvidiaCudaInstallWorker(parent=None)
        self.cuda_worker.log_signal.connect(self.log)
        
        def _on_prog(pct, msg):
            self.cuda_status_label.setText(f"CUDA: {msg} ({pct}%)")

        def _on_done(ok, msg):
            self.cuda_install_btn.setEnabled(True)
            self.check_cuda_status()
            if ok:
                QMessageBox.information(self, "NVIDIA CUDA Ready", f"✨ NVIDIA CUDA support installed and ready!\n\n{msg}")
            else:
                QMessageBox.warning(self, "CUDA Installation Note", f"Installation completed with note:\n{msg}")

        self.cuda_worker.progress_signal.connect(_on_prog)
        self.cuda_worker.finished_signal.connect(_on_done)
        track_running_worker(self.cuda_worker)
        self.cuda_worker.start()

    def init_ui(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background-color: #080c14; border: none; }")

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background-color: #080c14;")
        main_layout = QVBoxLayout(scroll_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 12, 20, 12)

        # Title Header
        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        header_top_row = QHBoxLayout()
        header_top_row.setSpacing(10)

        # Left symmetry spacer so the title remains centered
        left_dummy_spacer = QWidget()
        left_dummy_spacer.setFixedSize(36, 36)

        title_label = QLabel("⚡ SmartCleaner-AI")
        title_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title_label.setStyleSheet("color: #38bdf8; letter-spacing: 0.5px;")

        # Three-Dots Options Menu Button
        self.menu_dots_btn = QPushButton("⋮")
        self.menu_dots_btn.setFixedSize(36, 36)
        self.menu_dots_btn.setToolTip("خيارات إضافية (معلومات الإصدار، التحديثات، التواصل مع المبرمج)")
        self.menu_dots_btn.setCursor(Qt.PointingHandCursor)
        self.menu_dots_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f172a;
                color: #94a3b8;
                border: 1px solid #1e293b;
                border-radius: 8px;
                font-size: 20px;
                font-weight: bold;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background-color: #1e293b;
                color: #38bdf8;
                border-color: #0284c7;
            }
            QPushButton:pressed {
                background-color: #0284c7;
                color: #ffffff;
            }
        """)
        self.menu_dots_btn.clicked.connect(self.show_three_dots_menu)

        header_top_row.addWidget(left_dummy_spacer)
        header_top_row.addStretch()
        header_top_row.addWidget(title_label)
        header_top_row.addStretch()
        header_top_row.addWidget(self.menu_dots_btn)

        subtitle_label = QLabel("Dedicated Multi-Page Manga Inpainting & Intelligent Bubble Whitener")
        subtitle_label.setFont(QFont("Segoe UI", 9))
        subtitle_label.setStyleSheet("color: #94a3b8;")
        subtitle_label.setAlignment(Qt.AlignCenter)

        title_box.addLayout(header_top_row)
        title_box.addWidget(subtitle_label)
        main_layout.addLayout(title_box)

        # Main Card
        card = QFrame()
        card.setProperty("class", "card-frame")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)
        card_layout.setContentsMargins(18, 14, 18, 14)

        BTN_COL_WIDTH = 278

        # 1. Image Selection
        v_img = QVBoxLayout()
        v_img.setSpacing(3)
        lbl_img = QLabel("🖼️ Select Manga Images, Archives (.zip/.rar/.cbz/.7z), or Folder:")
        lbl_img.setStyleSheet("color: #e2e8f0; font-weight: 600; font-size: 11px;")

        row_img = QHBoxLayout()
        row_img.setSpacing(8)
        self.img_input = QLineEdit()
        self.img_input.setMinimumHeight(32)
        self.img_input.setPlaceholderText("Select image(s), archive (.zip/.rar/.cbz/.7z), or folder...")

        last_paths = self.config.get("last_image_paths", [])
        if last_paths:
            self.selected_image_paths = [p for p in last_paths if os.path.exists(p)]
            if self.selected_image_paths:
                self.img_input.setText(f"{len(self.selected_image_paths)} images selected")

        browse_files_btn = QPushButton("🖼️ Files...")
        browse_files_btn.setMinimumHeight(32)
        browse_files_btn.setFixedWidth(88)
        browse_files_btn.clicked.connect(self.browse_images)

        browse_folder_btn = QPushButton("📁 Folder...")
        browse_folder_btn.setMinimumHeight(32)
        browse_folder_btn.setFixedWidth(88)
        browse_folder_btn.clicked.connect(self.browse_folder)

        browse_url_btn = QPushButton("🔗 URL...")
        browse_url_btn.setMinimumHeight(32)
        browse_url_btn.setFixedWidth(88)
        browse_url_btn.clicked.connect(self.enter_chapter_url)

        row_img.addWidget(self.img_input, stretch=1)
        row_img.addWidget(browse_files_btn)
        row_img.addWidget(browse_folder_btn)
        row_img.addWidget(browse_url_btn)
        v_img.addWidget(lbl_img)
        v_img.addLayout(row_img)
        card_layout.addLayout(v_img)

        # 2. Output Folder Path
        v_out = QVBoxLayout()
        v_out.setSpacing(3)
        lbl_out = QLabel("📂 Cleaned Images Output Directory:")
        lbl_out.setStyleSheet("color: #e2e8f0; font-weight: 600; font-size: 11px;")

        row_out = QHBoxLayout()
        row_out.setSpacing(8)
        self.out_input = QLineEdit()
        self.out_input.setMinimumHeight(32)
        self.out_input.setText(self.config.get("last_output_dir", ""))
        self.out_input.setPlaceholderText("Select folder to save cleaned/whitened images...")

        out_btn = QPushButton("📂 Browse Output...")
        out_btn.setMinimumHeight(32)
        out_btn.setFixedWidth(BTN_COL_WIDTH)
        out_btn.clicked.connect(self.browse_output_dir)

        row_out.addWidget(self.out_input, stretch=1)
        row_out.addWidget(out_btn)
        v_out.addWidget(lbl_out)
        v_out.addLayout(row_out)
        card_layout.addLayout(v_out)

        # Hardware Acceleration Card (NVIDIA GPU / CUDA / CPU)
        hw_frame = QFrame()
        hw_frame.setStyleSheet("background-color: #080f1e; border: 1px solid #1e293b; border-radius: 8px;")
        v_hw = QVBoxLayout(hw_frame)
        v_hw.setSpacing(8)
        v_hw.setContentsMargins(14, 8, 14, 8)

        row_hw_top = QHBoxLayout()
        row_hw_top.setSpacing(12)
        lbl_hw_title = QLabel("🎮 Hardware Acceleration:")
        lbl_hw_title.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 11px;")

        self.hw_device_combo = QComboBox()
        self.hw_device_combo.setMinimumHeight(30)
        self.hw_device_combo.addItems([
            "🤖 Auto-Detect (NVIDIA GPU if available, else CPU)",
            "🟢 Force NVIDIA GPU (CUDA)",
            "💻 Force CPU (Multi-core ONNX)"
        ])
        saved_dev_mode = self.config.get("device_mode", "auto")
        if saved_dev_mode == "cuda":
            self.hw_device_combo.setCurrentIndex(1)
        elif saved_dev_mode == "cpu":
            self.hw_device_combo.setCurrentIndex(2)
        else:
            self.hw_device_combo.setCurrentIndex(0)
        self.hw_device_combo.currentIndexChanged.connect(self.on_device_mode_changed)

        self.cuda_status_dot = QLabel("⚪")
        self.cuda_status_label = QLabel("Checking...")
        self.cuda_status_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")

        self.cuda_install_btn = QPushButton("⚡ Install NVIDIA CUDA")
        self.cuda_install_btn.setMinimumHeight(30)
        self.cuda_install_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #15803d, stop:1 #22c55e);
                color: white;
                border: 1px solid #4ade80;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background: #166534; }
        """)
        self.cuda_install_btn.setToolTip("Automatically downloads and installs PyTorch with NVIDIA CUDA 12.1 silently in the background with live progress.")
        self.cuda_install_btn.clicked.connect(self.start_nvidia_cuda_install)

        row_hw_top.addWidget(lbl_hw_title)
        row_hw_top.addWidget(self.hw_device_combo, stretch=2)
        row_hw_top.addWidget(self.cuda_status_dot)
        row_hw_top.addWidget(self.cuda_status_label, stretch=1)
        row_hw_top.addWidget(self.cuda_install_btn)
        v_hw.addLayout(row_hw_top)
        card_layout.addWidget(hw_frame)

        # 4. Mobile Bridge Server & Ngrok Tunnel Card
        mobile_server_frame = QFrame()
        mobile_server_frame.setStyleSheet("background-color: #080f1e; border: 1px solid #1e293b; border-radius: 8px;")
        v_mserver = QVBoxLayout(mobile_server_frame)
        v_mserver.setSpacing(10)
        v_mserver.setContentsMargins(14, 10, 14, 10)

        # Top row: Title + Status + Action Buttons
        row_ms_top = QHBoxLayout()
        row_ms_top.setSpacing(10)

        lbl_ms_title = QLabel("📱 Mobile Bridge & Ngrok Server")
        lbl_ms_title.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 12px;")

        self.server_status_dot = QLabel("⚪")
        self.server_status_label = QLabel("Server: Stopped")
        self.server_status_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")

        self.ngrok_status_dot = QLabel("⚪")
        self.ngrok_status_label = QLabel("Ngrok: Offline")
        self.ngrok_status_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")

        self.start_server_btn = QPushButton("🚀 Start Server & Ngrok")
        self.start_server_btn.setMinimumHeight(28)
        self.start_server_btn.setStyleSheet("background: #0284c7; color: white; border-radius: 6px; padding: 4px 12px; font-size: 11px; font-weight: bold;")
        self.start_server_btn.clicked.connect(self.toggle_mobile_server)

        self.qr_code_btn = QPushButton("📱 QR Code Pairing")
        self.qr_code_btn.setMinimumHeight(28)
        self.qr_code_btn.setStyleSheet("background: #1e293b; color: #c084fc; border: 1px solid #9333ea; border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: bold;")
        self.qr_code_btn.clicked.connect(self.show_mobile_pairing_qr)

        row_ms_top.addWidget(lbl_ms_title)
        row_ms_top.addStretch()
        row_ms_top.addWidget(self.server_status_dot)
        row_ms_top.addWidget(self.server_status_label)
        row_ms_top.addWidget(self.ngrok_status_dot)
        row_ms_top.addWidget(self.ngrok_status_label)
        row_ms_top.addWidget(self.start_server_btn)
        row_ms_top.addWidget(self.qr_code_btn)
        v_mserver.addLayout(row_ms_top)

        # Row 2: Ngrok Authtoken / Serial & Domain inputs
        row_ms_inputs = QHBoxLayout()
        row_ms_inputs.setSpacing(10)

        lbl_token = QLabel("🔑 Ngrok Auth Token:")
        lbl_token.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.ngrok_token_input = QLineEdit()
        self.ngrok_token_input.setMinimumHeight(28)
        self.ngrok_token_input.setEchoMode(QLineEdit.Password)
        self.ngrok_token_input.setText(self.config.get("ngrok_authtoken", ""))
        self.ngrok_token_input.setPlaceholderText("Enter your Ngrok authtoken here...")

        self.toggle_token_vis_btn = QPushButton("👁️")
        self.toggle_token_vis_btn.setFixedSize(28, 28)
        self.toggle_token_vis_btn.setStyleSheet("background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 4px;")
        self.toggle_token_vis_btn.clicked.connect(self.toggle_token_visibility)

        save_token_btn = QPushButton("💾 Save Token")
        save_token_btn.setMinimumHeight(28)
        save_token_btn.setStyleSheet("background: #1e293b; color: #4ade80; border: 1px solid #16a34a; border-radius: 6px; padding: 3px 10px; font-size: 11px; font-weight: 600;")
        save_token_btn.clicked.connect(self.save_ngrok_authtoken_gui)

        self.install_ngrok_service_btn = QPushButton("⚡ تثبيت وتفعيل الخدمة فورياً")
        self.install_ngrok_service_btn.setMinimumHeight(28)
        self.install_ngrok_service_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10b981);
                color: white;
                border: 1px solid #34d399;
                border-radius: 6px;
                padding: 3px 12px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background: #047857; }
        """)
        self.install_ngrok_service_btn.setToolTip("تثبيت أداة Ngrok تلقائياً وضبط السيريال وتشغيل السيرفر وعرض كود الـ QR لربط الموبايل فوراً!")
        self.install_ngrok_service_btn.clicked.connect(self.install_and_activate_mobile_service)

        lbl_domain = QLabel("🌐 Custom Domain (Optional):")
        lbl_domain.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.ngrok_domain_input = QLineEdit()
        self.ngrok_domain_input.setMinimumHeight(28)
        self.ngrok_domain_input.setText(self.config.get("ngrok_domain", ""))
        self.ngrok_domain_input.setPlaceholderText("Static domain (or leave blank for automatic free domain)")

        row_ms_inputs.addWidget(lbl_token)
        row_ms_inputs.addWidget(self.ngrok_token_input, stretch=2)
        row_ms_inputs.addWidget(self.toggle_token_vis_btn)
        row_ms_inputs.addWidget(save_token_btn)
        row_ms_inputs.addWidget(self.install_ngrok_service_btn)
        row_ms_inputs.addWidget(lbl_domain)
        row_ms_inputs.addWidget(self.ngrok_domain_input, stretch=2)
        v_mserver.addLayout(row_ms_inputs)

        # Row 3: Active connection URLs (Ngrok Public + Wi-Fi LAN)
        row_ms_urls = QHBoxLayout()
        row_ms_urls.setSpacing(10)

        lbl_public_url = QLabel("🌐 Ngrok Public URL:")
        lbl_public_url.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.public_url_display = QLineEdit()
        self.public_url_display.setMinimumHeight(28)
        self.public_url_display.setReadOnly(True)
        self.public_url_display.setText("")
        self.public_url_display.setPlaceholderText("Public URL will appear here once the tunnel starts...")

        copy_public_btn = QPushButton("📋 Copy")
        copy_public_btn.setMinimumHeight(28)
        copy_public_btn.setFixedWidth(65)
        copy_public_btn.setStyleSheet("background: #1e293b; color: #38bdf8; border: 1px solid #0284c7; border-radius: 6px; font-size: 11px;")
        copy_public_btn.clicked.connect(lambda: self.copy_to_clipboard(self.public_url_display.text()))

        lbl_lan_url = QLabel("🏠 Wi-Fi LAN:")
        lbl_lan_url.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.lan_url_display = QLineEdit()
        self.lan_url_display.setMinimumHeight(28)
        self.lan_url_display.setReadOnly(True)
        self.lan_url_display.setText("http://127.0.0.1:8000")

        copy_lan_btn = QPushButton("📋 Copy")
        copy_lan_btn.setMinimumHeight(28)
        copy_lan_btn.setFixedWidth(65)
        copy_lan_btn.setStyleSheet("background: #1e293b; color: #38bdf8; border: 1px solid #0284c7; border-radius: 6px; font-size: 11px;")
        copy_lan_btn.clicked.connect(lambda: self.copy_to_clipboard(self.lan_url_display.text()))

        row_ms_urls.addWidget(lbl_public_url)
        row_ms_urls.addWidget(self.public_url_display, stretch=2)
        row_ms_urls.addWidget(copy_public_btn)
        row_ms_urls.addWidget(lbl_lan_url)
        row_ms_urls.addWidget(self.lan_url_display, stretch=1)
        row_ms_urls.addWidget(copy_lan_btn)
        v_mserver.addLayout(row_ms_urls)

        # Row 4: Google Colab Remote GPU (Optional alternative)
        row_colab = QHBoxLayout()
        row_colab.setSpacing(10)
        self.use_remote_server_cb = QCheckBox("☁️ Use Google Colab GPU Server (Remote Cloud Processing)")
        self.use_remote_server_cb.setChecked(self.config.get("use_remote_server", False))
        self.use_remote_server_cb.setStyleSheet("color: #94a3b8; font-size: 11px;")

        self.server_url_input = QLineEdit()
        self.server_url_input.setMinimumHeight(26)
        self.server_url_input.setText(self.config.get("remote_server_url", ""))
        self.server_url_input.setPlaceholderText("https://xxxx.ngrok-free.app (Colab Ngrok URL)")

        self.server_check_btn = QPushButton("🔄 Test Colab")
        self.server_check_btn.setMinimumHeight(26)
        self.server_check_btn.setFixedWidth(105)
        self.server_check_btn.setStyleSheet("background: #1e293b; color: #94a3b8; border: 1px solid #334155; border-radius: 6px; font-size: 11px;")
        self.server_check_btn.clicked.connect(self.ping_remote_server)

        row_colab.addWidget(self.use_remote_server_cb)
        row_colab.addWidget(self.server_url_input, stretch=1)
        row_colab.addWidget(self.server_check_btn)
        v_mserver.addLayout(row_colab)

        card_layout.addWidget(mobile_server_frame)

        # 5. IOPaint Inpainting Settings Card
        iopaint_frame = QFrame()
        iopaint_frame.setStyleSheet("background-color: #080f1e; border: 1px solid #1e293b; border-radius: 8px;")
        v_iopaint = QVBoxLayout(iopaint_frame)
        v_iopaint.setSpacing(8)
        v_iopaint.setContentsMargins(14, 8, 14, 8)

        row_iopaint_top = QHBoxLayout()
        row_iopaint_top.setSpacing(12)
        self.iopaint_enabled_cb = QCheckBox("🧹 Enable Inpainting / Cleaning")
        self.iopaint_enabled_cb.setChecked(self.config.get("iopaint_enabled", True))
        self.iopaint_enabled_cb.setStyleSheet("color: #4ade80; font-weight: bold; font-size: 11px;")

        self.iopaint_adaptive_cb = QCheckBox("⚡ Smart Adaptive (Fast Fill for White)")
        self.iopaint_adaptive_cb.setChecked(self.config.get("iopaint_adaptive", True))
        self.iopaint_adaptive_cb.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 11px;")

        self.iopaint_status_dot = QLabel("⚪")
        self.iopaint_status_label = QLabel("IOPaint: Offline")
        self.iopaint_status_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.iopaint_status_label.setMaximumWidth(280)

        self.iopaint_check_btn = QPushButton("🔄 Test Connection")
        self.iopaint_check_btn.setMinimumHeight(28)
        self.iopaint_check_btn.setFixedWidth(135)
        self.iopaint_check_btn.setStyleSheet("background: #1e293b; color: #38bdf8; border: 1px solid #0284c7; border-radius: 6px; padding: 3px 8px; font-size: 11px; font-weight: 600;")
        self.iopaint_check_btn.clicked.connect(self.ping_iopaint_server)

        row_iopaint_top.addWidget(self.iopaint_enabled_cb)
        row_iopaint_top.addWidget(self.iopaint_adaptive_cb)
        row_iopaint_top.addStretch()
        row_iopaint_top.addWidget(self.iopaint_status_dot)
        row_iopaint_top.addWidget(self.iopaint_status_label)
        row_iopaint_top.addWidget(self.iopaint_check_btn)
        v_iopaint.addLayout(row_iopaint_top)

        # Launcher Selection Row
        row_launcher = QHBoxLayout()
        row_launcher.setSpacing(10)
        lbl_launcher = QLabel("📁 Launcher File (.bat/.exe/.vbs):")
        lbl_launcher.setStyleSheet("color: #94a3b8; font-weight: 600; font-size: 11px;")
        
        self.iopaint_launcher_input = QLineEdit()
        self.iopaint_launcher_input.setMinimumHeight(30)
        self.iopaint_launcher_input.setText(self.config.get("iopaint_launcher_path", ""))
        self.iopaint_launcher_input.setPlaceholderText("Select IOPaint launch file/script (e.g. Start_IOPaint.bat)...")

        browse_launcher_btn = QPushButton("📁 Browse...")
        browse_launcher_btn.setMinimumHeight(30)
        browse_launcher_btn.setFixedWidth(90)
        browse_launcher_btn.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 6px;
                padding: 3px 8px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover { background: #0284c7; color: white; }
        """)
        browse_launcher_btn.clicked.connect(self.browse_iopaint_launcher)

        self.iopaint_start_btn = QPushButton("⚡ Start Server")
        self.iopaint_start_btn.setMinimumHeight(30)
        self.iopaint_start_btn.setFixedWidth(130)
        self.iopaint_start_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #15803d, stop:1 #22c55e);
                color: white;
                border: 1px solid #4ade80;
                border-radius: 6px;
                padding: 3px 10px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { background: #166534; }
        """)
        self.iopaint_start_btn.setToolTip("Starts IOPaint in the background.")
        self.iopaint_start_btn.clicked.connect(self.start_silent_iopaint_server)

        self.iopaint_stop_btn = QPushButton("🛑 Stop")
        self.iopaint_stop_btn.setMinimumHeight(30)
        self.iopaint_stop_btn.setFixedWidth(75)
        self.iopaint_stop_btn.setStyleSheet("background: #1e293b; color: #f87171; border: 1px solid #dc2626; border-radius: 6px; padding: 3px 8px; font-size: 11px; font-weight: bold;")
        self.iopaint_stop_btn.clicked.connect(self.stop_iopaint_server)

        row_launcher.addWidget(lbl_launcher)
        row_launcher.addWidget(self.iopaint_launcher_input, stretch=1)
        row_launcher.addWidget(browse_launcher_btn)
        row_launcher.addWidget(self.iopaint_start_btn)
        row_launcher.addWidget(self.iopaint_stop_btn)
        v_iopaint.addLayout(row_launcher)



        row_iopaint_controls = QHBoxLayout()
        row_iopaint_controls.setSpacing(10)
        lbl_url = QLabel("🌐 URL:")
        lbl_url.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.iopaint_url_input = QLineEdit()
        self.iopaint_url_input.setMinimumHeight(30)
        self.iopaint_url_input.setText(self.config.get("iopaint_server_url", "http://127.0.0.1:8080"))

        lbl_model = QLabel("🧠 Model:")
        lbl_model.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.iopaint_model_combo = QComboBox()
        self.iopaint_model_combo.setMinimumHeight(30)
        self.iopaint_model_combo.blockSignals(True)
        saved_models = self.config.get("available_iopaint_models", ["anime-lama", "lama"])
        self.iopaint_model_combo.addItems(saved_models)
        saved_model = self.config.get("iopaint_model", "anime-lama")
        m_idx = self.iopaint_model_combo.findText(saved_model)
        if m_idx >= 0:
            self.iopaint_model_combo.setCurrentIndex(m_idx)
        self.iopaint_model_combo.blockSignals(False)
        self.iopaint_model_combo.currentTextChanged.connect(self.on_iopaint_model_changed)

        lbl_dilation = QLabel("⭕ Dilation (px):")
        lbl_dilation.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.iopaint_dilation_spin = QSpinBox()
        self.iopaint_dilation_spin.setMinimumHeight(30)
        self.iopaint_dilation_spin.setRange(0, 50)
        self.iopaint_dilation_spin.setValue(self.config.get("iopaint_dilation", 5))

        lbl_padding = QLabel("🔲 Padding (px):")
        lbl_padding.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.mask_padding_spin = QSpinBox()
        self.mask_padding_spin.setMinimumHeight(30)
        self.mask_padding_spin.setRange(0, 100)
        saved_pad = self.config.get("mask_padding")
        if saved_pad is None or saved_pad == 0:
            saved_pad = self.config.get("iopaint_dilation", 5)
        self.mask_padding_spin.setValue(saved_pad)
        self.mask_padding_spin.setToolTip("Mask expansion and padding around text/bubble regions in pixels")

        row_iopaint_controls.addWidget(lbl_url)
        row_iopaint_controls.addWidget(self.iopaint_url_input, stretch=2)
        row_iopaint_controls.addWidget(lbl_model)
        row_iopaint_controls.addWidget(self.iopaint_model_combo, stretch=1)
        row_iopaint_controls.addWidget(lbl_dilation)
        row_iopaint_controls.addWidget(self.iopaint_dilation_spin)
        row_iopaint_controls.addWidget(lbl_padding)
        row_iopaint_controls.addWidget(self.mask_padding_spin)
        v_iopaint.addLayout(row_iopaint_controls)
        card_layout.addWidget(iopaint_frame)

        main_layout.addWidget(card)

        # Dual Progress Dashboard
        self.progress_container = QFrame()
        self.progress_container.setStyleSheet("background-color: #080f1e; border: 1px solid #1e293b; border-radius: 8px;")
        prog_layout = QVBoxLayout(self.progress_container)
        prog_layout.setSpacing(6)
        prog_layout.setContentsMargins(14, 8, 14, 8)

        overall_hdr_row = QHBoxLayout()
        self.overall_label = QLabel("📊 Overall Batch Progress: Ready")
        self.overall_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.overall_label.setStyleSheet("color: #38bdf8;")

        self.overall_eta_label = QLabel("⏱️ Elapsed: 00:00  |  ⏳ ETA: --:--")
        self.overall_eta_label.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self.overall_eta_label.setStyleSheet("color: #fbbf24; background: #1e293b; border: 1px solid #334155; border-radius: 5px; padding: 2px 10px;")

        overall_hdr_row.addWidget(self.overall_label)
        overall_hdr_row.addStretch()
        overall_hdr_row.addWidget(self.overall_eta_label)
        prog_layout.addLayout(overall_hdr_row)

        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        prog_layout.addWidget(self.overall_progress)

        current_hdr_row = QHBoxLayout()
        self.current_label = QLabel("🔍 Current Page: Idle")
        self.current_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        self.current_label.setStyleSheet("color: #c084fc;")

        self.current_eta_label = QLabel("⏱️ Step Time: 00:00")
        self.current_eta_label.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self.current_eta_label.setStyleSheet("color: #94a3b8; background: #1e293b; border: 1px solid #334155; border-radius: 5px; padding: 2px 10px;")

        current_hdr_row.addWidget(self.current_label)
        current_hdr_row.addStretch()
        current_hdr_row.addWidget(self.current_eta_label)
        prog_layout.addLayout(current_hdr_row)

        self.current_progress = QProgressBar()
        self.current_progress.setRange(0, 100)
        self.current_progress.setValue(0)
        prog_layout.addWidget(self.current_progress)

        main_layout.addWidget(self.progress_container)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setStyleSheet("background-color: #06090e; border: 1px solid #1e293b; border-radius: 6px; color: #a5f3fc; padding: 6px;")
        self.log_text.setMaximumHeight(65)
        self.log_text.setPlaceholderText("Cleaner activity logs will appear here...")
        main_layout.addWidget(self.log_text)

        # Action Buttons Row
        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.run_btn = QPushButton("🚀 Run Batch Cleaning")
        self.run_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.run_btn.setMinimumHeight(40)
        self.run_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #0ea5e9); color: white; border-radius: 6px; border: 1px solid #38bdf8; }
            QPushButton:hover { background: #0369a1; }
        """)
        self.run_btn.clicked.connect(self.start_processing)

        self.load_proj_btn = QPushButton("📂 Load Saved Project")
        self.load_proj_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.load_proj_btn.setMinimumHeight(40)
        self.load_proj_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #15803d, stop:1 #22c55e); color: white; border-radius: 6px; border: 1px solid #4ade80; }
            QPushButton:hover { background: #166534; }
        """)
        self.load_proj_btn.clicked.connect(self.load_project_state)

        self.cancel_btn = QPushButton("🛑 Stop / Cancel")
        self.cancel_btn.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b91c1c, stop:1 #ef4444); color: white; border-radius: 6px; border: 1px solid #f87171; }
            QPushButton:hover { background: #991b1b; }
        """)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_processing)

        action_row.addWidget(self.run_btn, stretch=1)
        action_row.addWidget(self.load_proj_btn, stretch=1)
        action_row.addWidget(self.cancel_btn, stretch=1)
        main_layout.addLayout(action_row)

        scroll_area.setWidget(scroll_widget)
        self.setCentralWidget(scroll_area)
        self.check_cuda_status()

        # Start periodic mobile server & ngrok monitor timer
        self.server_monitor_timer = QTimer(self)
        self.server_monitor_timer.timeout.connect(self.refresh_server_and_ngrok_status)
        self.server_monitor_timer.start(4000)
        QTimer.singleShot(600, self.refresh_server_and_ngrok_status)

    def ping_remote_server(self):
        url = self.server_url_input.text().strip().rstrip("/")
        if not url:
            QMessageBox.warning(self, "Missing URL", "Please enter a Colab server URL.")
            return

        self.server_status_dot.setText("⏳")
        self.server_status_label.setText("Testing...")

        class PingColabWorker(QThread):
            res_signal = Signal(bool, str)
            def __init__(self, u, parent=None):
                super().__init__(parent)
                self.u = u
            def run(self):
                import requests
                try:
                    r = requests.get(f"{self.u}/api/health", headers={"ngrok-skip-browser-warning": "true"}, timeout=8)
                    if r.status_code == 200:
                        self.res_signal.emit(True, "Online (Colab GPU Ready)")
                    else:
                        self.res_signal.emit(False, f"HTTP {r.status_code}")
                except Exception:
                    self.res_signal.emit(False, "Offline")

        self.colab_ping_worker = PingColabWorker(url, parent=None)
        def _on_colab(ok, msg):
            self.server_status_dot.setText("🟢" if ok else "🔴")
            self.server_status_label.setText(f"Colab: {msg}")
            self.server_status_label.setStyleSheet(f"color: {'#4ade80' if ok else '#f87171'}; font-size: 11px; font-weight: bold;")
        self.colab_ping_worker.res_signal.connect(_on_colab)
        track_running_worker(self.colab_ping_worker)
        self.colab_ping_worker.start()

    def toggle_token_visibility(self):
        """Toggles between hidden password and visible text for Ngrok token."""
        if self.ngrok_token_input.echoMode() == QLineEdit.Password:
            self.ngrok_token_input.setEchoMode(QLineEdit.Normal)
            self.toggle_token_vis_btn.setText("🔒")
        else:
            self.ngrok_token_input.setEchoMode(QLineEdit.Password)
            self.toggle_token_vis_btn.setText("👁️")

    def save_ngrok_authtoken_gui(self):
        """Saves Ngrok authtoken and domain to config and ngrok configuration."""
        token = self.ngrok_token_input.text().strip()
        domain = self.ngrok_domain_input.text().strip()
        self.config["ngrok_authtoken"] = token
        self.config["ngrok_domain"] = domain
        self.save_config()

        if token:
            ok, msg = configure_ngrok_authtoken(token)
            if ok:
                QMessageBox.information(self, "Ngrok Token", "✅ Ngrok authtoken saved and configured successfully!")
            else:
                QMessageBox.warning(self, "Ngrok Token", f"⚠️ {msg}")
        else:
            QMessageBox.information(self, "Settings Saved", "Settings saved successfully.")

    def install_and_activate_mobile_service(self):
        """1-Click Ngrok installation, token configuration, and server launch."""
        token = self.ngrok_token_input.text().strip()
        if not token:
            QMessageBox.warning(
                self,
                "مطلوب كود Ngrok",
                "يرجى إدخال رمز/سيريال Ngrok Auth Token أولاً.\nيمكنك الحصول عليه مجاناً من:\nhttps://dashboard.ngrok.com"
            )
            self.ngrok_token_input.setFocus()
            return

        domain = self.ngrok_domain_input.text().strip()
        self.config["ngrok_authtoken"] = token
        self.config["ngrok_domain"] = domain
        self.save_config()

        self.install_ngrok_service_btn.setEnabled(False)
        self.install_ngrok_service_btn.setText("⏳ جاري التثبيت والتفعيل...")
        self.server_status_dot.setText("⏳")
        self.server_status_label.setText("جاري إعداد السيرفر...")

        self.ngrok_installer_worker = NgrokServiceInstallerWorker(token, domain, 8000, parent=None)

        def _on_prog(msg, pct):
            self.log(f"🌐 [Ngrok Service] {msg}")
            self.server_status_label.setText(msg)

        def _on_done(ok, public_url, msg):
            self.install_ngrok_service_btn.setEnabled(True)
            self.install_ngrok_service_btn.setText("⚡ تثبيت وتفعيل الخدمة فورياً")
            self.refresh_server_and_ngrok_status()

            if ok:
                self.public_url_display.setText(public_url)
                self.log(f"✅ {msg} | Public URL: {public_url}")
                QMessageBox.information(self, "نجاح التفعيل", f"{msg}\n\nالرابط العام:\n{public_url}\n\nسيتم فتح كود QR الآن للمسح السريع من الموبايل!")
                self.show_mobile_pairing_qr()
            else:
                QMessageBox.critical(self, "خطأ في التثبيت والتفعيل", msg)

        self.ngrok_installer_worker.progress_signal.connect(_on_prog)
        self.ngrok_installer_worker.finished_signal.connect(_on_done)
        track_running_worker(self.ngrok_installer_worker)
        self.ngrok_installer_worker.start()

    def copy_to_clipboard(self, text: str):
        """Copies given text to system clipboard."""
        if text and text.strip():
            QApplication.clipboard().setText(text.strip())
            QMessageBox.information(self, "Copied", f"Public URL copied to clipboard successfully: 📋\n{text.strip()}")

    def refresh_server_and_ngrok_status(self):
        """Asynchronously checks if server and ngrok are running in a background thread."""
        if hasattr(self, "_server_worker") and self._server_worker is not None:
            if self._server_worker.isRunning():
                return
            try:
                self._server_worker.status_signal.disconnect()
            except Exception:
                pass
        self._server_worker = ServerMonitorWorker(parent=None)
        self._server_worker.status_signal.connect(self._on_server_status_ready)
        track_running_worker(self._server_worker)
        self._server_worker.start()

    def _on_server_status_ready(self, server_up: bool, active_url: str, lan_ip: str):
        if server_up:
            self.server_status_dot.setText("🟢")
            self.server_status_label.setText("Server: Online (8000)")
            self.server_status_label.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
            self.start_server_btn.setText("🛑 Stop Server")
            self.start_server_btn.setStyleSheet("background: #b91c1c; color: white; border-radius: 6px; padding: 4px 12px; font-size: 11px; font-weight: bold;")
        else:
            self.server_status_dot.setText("🔴")
            self.server_status_label.setText("Server: Stopped")
            self.server_status_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
            self.start_server_btn.setText("🚀 Start Server & Ngrok")
            self.start_server_btn.setStyleSheet("background: #0284c7; color: white; border-radius: 6px; padding: 4px 12px; font-size: 11px; font-weight: bold;")

        if active_url:
            self.ngrok_status_dot.setText("🟢")
            self.ngrok_status_label.setText("Ngrok: Online")
            self.ngrok_status_label.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
            self.public_url_display.setText(active_url)
        else:
            self.ngrok_status_dot.setText("⚪")
            self.ngrok_status_label.setText("Ngrok: Offline")
            self.ngrok_status_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")

        self.lan_url_display.setText(f"http://{lan_ip}:8000")

    def toggle_mobile_server(self):
        """Starts or stops the Mobile Bridge Server & Ngrok."""
        server_up = is_server_online(8000)
        if server_up:
            # Stop server
            stop_server_and_ngrok(8000)
            time.sleep(1.0)
            self.refresh_server_and_ngrok_status()
            self.log("🛑 SmartCleaner Mobile Bridge Server & Ngrok have been stopped.")
        else:
            # Save token & domain before launch
            token = self.ngrok_token_input.text().strip()
            domain = self.ngrok_domain_input.text().strip()
            if token:
                self.config["ngrok_authtoken"] = token
                configure_ngrok_authtoken(token)
            if domain:
                self.config["ngrok_domain"] = domain
            self.save_config()

            # Launch server_api.py with --with-ngrok
            server_script = str(Path(__file__).resolve().parent / "server_api.py")
            cmd = [sys.executable, server_script, "--with-ngrok"]

            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_CONSOLE

            try:
                subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parent), creationflags=creationflags)
                self.log("🚀 Launching SmartCleaner Mobile Bridge Server & Ngrok Tunnel...")
                # Poll status for a few seconds
                QTimer.singleShot(2500, self.refresh_server_and_ngrok_status)
                QTimer.singleShot(5000, self.refresh_server_and_ngrok_status)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to start server: {e}")

    def show_mobile_pairing_qr(self):
        """Displays QR code dialog for fast mobile pairing."""
        active_url = self.public_url_display.text().strip()
        lan_url = self.lan_url_display.text().strip()
        target_url = active_url or lan_url

        dlg = QDialog(self)
        dlg.setWindowTitle("📱 Mobile Pairing QR Code - SmartCleaner-AI")
        dlg.setMinimumWidth(380)
        dlg.setStyleSheet("background-color: #0f172a; color: #f8fafc;")

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("📲 Connect Mobile App to SmartCleaner-AI")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title)

        subtitle = QLabel("Open mobile app or phone camera and scan the QR code below to connect instantly:")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 11px; color: #94a3b8;")
        layout.addWidget(subtitle)

        # Generate QR code
        try:
            qr_pil = generate_qr_code_image(target_url, size=240)
            buf = io.BytesIO()
            qr_pil.save(buf, format="PNG")
            qimg = QImage.fromData(buf.getvalue())
            pixmap = QPixmap.fromImage(qimg)

            qr_label = QLabel()
            qr_label.setAlignment(Qt.AlignCenter)
            qr_label.setPixmap(pixmap)
            layout.addWidget(qr_label)
        except Exception as e:
            err_label = QLabel(f"QR Generation Error: {e}")
            err_label.setStyleSheet("color: #f87171;")
            layout.addWidget(err_label)

        # Display URL text
        url_box = QLineEdit(target_url)
        url_box.setReadOnly(True)
        url_box.setAlignment(Qt.AlignCenter)
        url_box.setStyleSheet("background: #1e293b; color: #4ade80; border: 1px solid #334155; border-radius: 6px; padding: 6px; font-size: 11px; font-weight: bold;")
        layout.addWidget(url_box)

        # Buttons
        btn_row = QHBoxLayout()
        copy_btn = QPushButton("📋 Copy URL")
        copy_btn.setStyleSheet("background: #0284c7; color: white; border-radius: 6px; padding: 6px 12px; font-weight: bold;")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(target_url))

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("background: #334155; color: white; border-radius: 6px; padding: 6px 12px;")
        close_btn.clicked.connect(dlg.accept)

        btn_row.addWidget(copy_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dlg.exec()

    def browse_iopaint_launcher(self):
        start_dir = self.get_last_dir("last_launcher_dir", "")
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select IOPaint Launcher File / Script (.bat, .exe, .vbs, .py)",
            start_dir,
            "Executable / Script Files (*.bat *.cmd *.exe *.vbs *.py);;Batch Files (*.bat *.cmd);;Executable Files (*.exe);;All Files (*.*)"
        )
        if file_path:
            self.iopaint_launcher_input.setText(file_path)
            self.config["iopaint_launcher_path"] = file_path
            self.set_last_dir("last_launcher_dir", os.path.dirname(file_path))
            self.log(f"📁 Selected IOPaint launcher file: {file_path}")

    def start_silent_iopaint_server(self):
        url = self.iopaint_url_input.text().strip() or "http://127.0.0.1:8080"
        try:
            client = IOPaintClient(url)
            ok, m = client.check_connection()
            if ok:
                self.iopaint_status_dot.setText("🟢")
                self.iopaint_status_label.setText(f"IOPaint: Online ({m or 'Ready'})")
                self.iopaint_status_label.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
                self.iopaint_start_btn.setEnabled(True)
                self.iopaint_stop_btn.setEnabled(True)
                self.log(f"🎉✨ IOPaint server is already running and ready ({m or 'Ready'}) on {url}!")
                return
        except Exception:
            pass

        launcher_path = self.iopaint_launcher_input.text().strip()

        # Smart path correction (e.g. Start IOPaint.bat -> Start_IOPaint.bat)
        if launcher_path and not os.path.exists(launcher_path):
            alt_path = launcher_path.replace("Start IOPaint.bat", "Start_IOPaint.bat").replace("Start IOPaint", "Start_IOPaint")
            if os.path.exists(alt_path):
                launcher_path = alt_path
                self.iopaint_launcher_input.setText(alt_path)
                self.config["iopaint_launcher_path"] = alt_path
                self.save_config()

        if launcher_path and os.path.exists(launcher_path):
            self.log(f"🚀 Starting IOPaint via {Path(launcher_path).name} (Live output streaming below)...")
            ext = Path(launcher_path).suffix.lower()
            if ext in (".bat", ".cmd"):
                cmd = ["cmd.exe", "/c", launcher_path]
            elif ext == ".vbs":
                cmd = ["wscript.exe", launcher_path]
            elif ext == ".py":
                cmd = ["py", "-3.10", launcher_path]
            else:
                cmd = [launcher_path]
            cwd = str(Path(launcher_path).parent)
        else:
            self.log("🚀 Starting default IOPaint server on port 8080 in background...")
            model = self.iopaint_model_combo.currentText().strip() or "anime-lama"
            cmd = ["py", "-3.10", "-m", "iopaint", "start", "--model", model, "--port", "8080", "--host", "127.0.0.1"]
            cwd = str(Path(__file__).parent)

        self.iopaint_status_dot.setText("⏳")
        self.iopaint_status_label.setText("IOPaint: Launching (Loading/Downloading Model)...")
        self.iopaint_status_label.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        self.iopaint_start_btn.setEnabled(False)
        self.iopaint_stop_btn.setEnabled(True)

        self.iopaint_proc_worker = IOPaintProcessWorker(cmd, cwd, silent=True, parent=None)
        self.iopaint_proc_worker.log_signal.connect(self.log)

        def _on_proc_finished(ret):
            if hasattr(self, 'iopaint_poll_timer') and self.iopaint_poll_timer.isActive():
                self.iopaint_poll_timer.stop()
            self.iopaint_start_btn.setEnabled(True)
            self.iopaint_stop_btn.setEnabled(False)
            if ret != 0:
                self.log(f"ℹ️ IOPaint process exited with code {ret}.")

        self.iopaint_proc_worker.finished_signal.connect(_on_proc_finished)
        track_running_worker(self.iopaint_proc_worker)
        self.iopaint_proc_worker.start()

        # Start continuous auto-polling with elapsed counter
        self.iopaint_poll_start_time = time.time()
        self.iopaint_poll_timer = QTimer(self)
        self.iopaint_poll_timer.timeout.connect(self._check_silent_iopaint_started)
        self.iopaint_poll_timer.start(1000)

    def _check_silent_iopaint_started(self):
        url = self.iopaint_url_input.text().strip() or "http://127.0.0.1:8080"
        elapsed = int(time.time() - getattr(self, "iopaint_poll_start_time", time.time()))

        class FastPingWorker(QThread):
            res_signal = Signal(bool, str, list)
            def __init__(self, u, parent=None):
                super().__init__(parent)
                self.u = u
            def run(self):
                try:
                    c = IOPaintClient(self.u)
                    ok, m = c.check_connection()
                    models = []
                    if ok:
                        models = c.get_available_models(self.u)
                    self.res_signal.emit(ok, m, models)
                except Exception as err:
                    self.res_signal.emit(False, str(err), [])

        if hasattr(self, '_fast_pinger') and self._fast_pinger is not None:
            if self._fast_pinger.isRunning():
                return
            try:
                self._fast_pinger.res_signal.disconnect()
            except Exception:
                pass

        self._fast_pinger = FastPingWorker(url, parent=None)
        def _on_fast_ping(ok, m, models):
            if ok:
                if hasattr(self, 'iopaint_poll_timer') and self.iopaint_poll_timer.isActive():
                    self.iopaint_poll_timer.stop()
                self.iopaint_status_dot.setText("🟢")
                self.iopaint_status_label.setText(f"IOPaint: Online & Ready ({m or 'Ready'})")
                self.iopaint_status_label.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
                self.iopaint_start_btn.setEnabled(True)
                if models:
                    self.update_iopaint_models_from_server(models, active_model=m)
                self.log(f"🎉✨ IOPaint server is fully online and ready ({m or 'anime-lama'})!")
            else:
                self.iopaint_status_dot.setText("⏳")
                self.iopaint_status_label.setText(f"IOPaint: Starting up ({elapsed}s)...")
                self.iopaint_status_label.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: 600;")

        self._fast_pinger.res_signal.connect(_on_fast_ping)
        track_running_worker(self._fast_pinger)
        self._fast_pinger.start()

    def _kill_port_8080_processes(self):
        if sys.platform == "win32":
            try:
                import subprocess, os
                out = subprocess.check_output(
                    "netstat -ano | findstr :8080",
                    shell=True,
                    text=True,
                    creationflags=0x08000000,
                    stderr=subprocess.DEVNULL
                )
                pids = set()
                for line in out.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 5 and "LISTENING" in parts[3]:
                        pid = parts[4]
                        if pid.isdigit() and int(pid) > 0 and int(pid) != os.getpid():
                            pids.add(pid)
                for pid in pids:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        creationflags=0x08000000,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
            except Exception:
                pass

    def stop_iopaint_server(self):
        try:
            if hasattr(self, 'iopaint_poll_timer') and self.iopaint_poll_timer.isActive():
                self.iopaint_poll_timer.stop()

            if hasattr(self, 'iopaint_proc_worker') and self.iopaint_proc_worker:
                self.iopaint_proc_worker.terminate_process()
                self.iopaint_proc_worker = None

            self._kill_port_8080_processes()

            self.iopaint_status_dot.setText("🔴")
            self.iopaint_status_label.setText("IOPaint: Stopped")
            self.iopaint_status_label.setStyleSheet("color: #f87171; font-size: 11px; font-weight: 600;")
            self.iopaint_start_btn.setEnabled(True)
            self.iopaint_stop_btn.setEnabled(False)
            self.log("🛑 Stopped IOPaint server and cleaned background processes.")
        except Exception as e:
            self.log(f"Stop server note: {e}")

    def closeEvent(self, event):
        try:
            self.config["window_width"] = self.width()
            self.config["window_height"] = self.height()
            self.config["window_is_maximized"] = self.isMaximized()
            self.save_config()

            if hasattr(self, 'server_monitor_timer') and self.server_monitor_timer.isActive():
                self.server_monitor_timer.stop()
            if hasattr(self, 'eta_timer') and self.eta_timer.isActive():
                self.eta_timer.stop()
            if hasattr(self, 'iopaint_poll_timer') and self.iopaint_poll_timer.isActive():
                self.iopaint_poll_timer.stop()

            if hasattr(self, 'iopaint_proc_worker') and self.iopaint_proc_worker:
                self.stop_iopaint_server()
            if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
                self.worker.cancel()
            if hasattr(self, '_server_worker') and self._server_worker and self._server_worker.isRunning():
                self._server_worker.cancel()
            if hasattr(self, 'preload_thread') and self.preload_thread and self.preload_thread.isRunning():
                self.preload_thread.cancel()
        except Exception:
            pass
        event.accept()

    def ping_iopaint_server(self):
        url = self.iopaint_url_input.text().strip() or "http://127.0.0.1:8080"
        self.iopaint_status_dot.setText("⏳")
        self.iopaint_status_label.setText("Testing connection...")
        
        if hasattr(self, "iopaint_ping_worker") and self.iopaint_ping_worker is not None:
            if self.iopaint_ping_worker.isRunning():
                return
            try:
                self.iopaint_ping_worker.status_signal.disconnect()
            except Exception:
                pass

        self.iopaint_ping_worker = IOPaintPingWorker(url, parent=None)
        self.iopaint_ping_worker.status_signal.connect(self.on_iopaint_ping_finished)
        track_running_worker(self.iopaint_ping_worker)
        self.iopaint_ping_worker.start()

    def on_iopaint_ping_finished(self, is_online: bool, active_model: str, available_models: list = None):
        if is_online:
            self.iopaint_status_dot.setText("🟢")
            self.iopaint_status_label.setText(f"IOPaint: Online ({active_model or 'Ready'})")
            self.iopaint_status_label.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
            if available_models:
                self.update_iopaint_models_from_server(available_models, active_model=active_model)
            elif active_model and active_model != "connected":
                idx = self.iopaint_model_combo.findText(active_model)
                if idx >= 0:
                    self.iopaint_model_combo.blockSignals(True)
                    self.iopaint_model_combo.setCurrentIndex(idx)
                    self.iopaint_model_combo.blockSignals(False)
        else:
            self.iopaint_status_dot.setText("🔴")
            self.iopaint_status_label.setText("IOPaint: Offline (Click Test Connection)")
            self.iopaint_status_label.setStyleSheet("color: #f87171; font-size: 11px; font-weight: 600;")

    def update_iopaint_models_from_server(self, models: list, active_model: str = ""):
        """
        Dynamically updates the models combo box from actual discovered models,
        persists them to gui_config.json, and selects the active model.
        """
        if not models:
            return

        current_selection = self.iopaint_model_combo.currentText().strip()
        existing_items = [self.iopaint_model_combo.itemText(i) for i in range(self.iopaint_model_combo.count())]

        if set(existing_items) != set(models):
            self.iopaint_model_combo.blockSignals(True)
            self.iopaint_model_combo.clear()
            self.iopaint_model_combo.addItems(models)
            
            target = active_model if (active_model and active_model in models) else current_selection
            idx = self.iopaint_model_combo.findText(target)
            if idx >= 0:
                self.iopaint_model_combo.setCurrentIndex(idx)
            else:
                self.iopaint_model_combo.setCurrentIndex(0)
            self.iopaint_model_combo.blockSignals(False)

            self.config["available_iopaint_models"] = models
            self.config["iopaint_model"] = self.iopaint_model_combo.currentText().strip()
            self.save_config()
            self.log(f"📋 IOPaint models updated from server ({len(models)}): {', '.join(models)}")
        elif active_model and active_model in models:
            idx = self.iopaint_model_combo.findText(active_model)
            if idx >= 0 and self.iopaint_model_combo.currentIndex() != idx:
                self.iopaint_model_combo.blockSignals(True)
                self.iopaint_model_combo.setCurrentIndex(idx)
                self.iopaint_model_combo.blockSignals(False)
                self.config["iopaint_model"] = active_model
                self.save_config()

    def on_iopaint_model_changed(self, new_model: str):
        if not new_model:
            return
        self.config["iopaint_model"] = new_model
        self.save_config()
        url = self.iopaint_url_input.text().strip() or "http://127.0.0.1:8080"
        self.iopaint_status_label.setText(f"Switching to {new_model}...")
        if hasattr(self, "iopaint_switch_worker") and self.iopaint_switch_worker is not None:
            if self.iopaint_switch_worker.isRunning():
                return
            try:
                self.iopaint_switch_worker.finished_signal.disconnect()
            except Exception:
                pass
        self.iopaint_switch_worker = IOPaintSwitchModelWorker(url, new_model, parent=None)
        self.iopaint_switch_worker.finished_signal.connect(self.on_iopaint_model_switched)
        track_running_worker(self.iopaint_switch_worker)
        self.iopaint_switch_worker.start()

    def on_iopaint_model_switched(self, success: bool, model_name: str, msg: str):
        if success:
            self.iopaint_status_dot.setText("🟢")
            self.iopaint_status_label.setText(f"IOPaint: Online ({model_name})")
            self.iopaint_status_label.setStyleSheet("color: #4ade80; font-size: 11px; font-weight: bold;")
            self.log(f"🧠 IOPaint model switched successfully to: {model_name}")
        else:
            self.iopaint_status_dot.setText("⚪")
            self.iopaint_status_label.setText(f"IOPaint: Offline ({model_name} saved)")
            self.iopaint_status_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")

    def browse_images(self):
        start_dir = self.get_last_dir("last_input_dir", os.path.dirname(self.selected_image_paths[0]) if self.selected_image_paths else "")
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Manga Images or Archive", start_dir,
            "Manga Images & Archives (*.png *.jpg *.jpeg *.webp *.bmp *.zip *.cbz *.rar *.cbr *.7z *.tar);;All Files (*.*)"
        )
        if files:
            self.set_last_dir("last_input_dir", os.path.dirname(files[0]))
            all_resolved = []
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in ARCHIVE_EXTENSIONS:
                    all_resolved.extend(extract_archive_if_needed(f, progress_callback=self.log))
                elif ext in VALID_IMAGE_EXTENSIONS:
                    all_resolved.append(f)

            all_resolved.sort(key=natural_sort_key)
            if all_resolved:
                self.selected_image_paths = all_resolved
                self.img_input.setText(f"{len(all_resolved)} images selected")
                self.log(f"✅ Loaded {len(all_resolved)} manga image page(s).")
            else:
                QMessageBox.warning(self, "No Images Found", "No valid image files were found.")

    def browse_folder(self):
        start_dir = self.get_last_dir("last_input_dir", "")
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing Manga Images", start_dir)
        if folder:
            self.set_last_dir("last_input_dir", folder)
            all_resolved = extract_archive_if_needed(folder, progress_callback=self.log)
            if all_resolved:
                self.selected_image_paths = all_resolved
                self.img_input.setText(f"📁 Folder ({len(all_resolved)} images): {Path(folder).name}")
                self.log(f"✅ Loaded {len(all_resolved)} manga image page(s) from folder.")
            else:
                QMessageBox.warning(self, "No Images Found", f"No valid image files found in folder:\n{folder}")

    def enter_chapter_url(self):
        url, ok = QInputDialog.getText(self, "🔗 Chapter URL", "Paste direct archive URL (.zip/.rar/.cbz or Google Drive):")
        if ok and url.strip():
            self.img_input.setText(url.strip())
            self.log(f"🔗 Chapter URL set: {url.strip()}")

    def browse_output_dir(self):
        start_dir = self.get_last_dir("last_output_dir", self.out_input.text().strip() or "")
        folder = QFileDialog.getExistingDirectory(self, "Select Output Directory for Cleaned Images", start_dir)
        if folder:
            self.out_input.setText(folder)
            self.set_last_dir("last_output_dir", folder)

    def log(self, msg: str):
        self.log_text.append(msg)

    def update_eta_ticker(self):
        if self.batch_start_time is None:
            return
        now = time.time()
        elapsed_sec = int(now - self.batch_start_time)
        elapsed_min = elapsed_sec // 60
        elapsed_s = elapsed_sec % 60
        self.overall_eta_label.setText(f"⏱️ Elapsed: {elapsed_min:02d}:{elapsed_s:02d}")

        if self.step_start_time:
            step_sec = int(now - self.step_start_time)
            self.current_eta_label.setText(f"⏱️ Step Time: {step_sec//60:02d}:{step_sec%60:02d}")

    def update_overall_progress(self, current: int, total: int, msg: str):
        self.completed_batch_pages = current
        self.total_batch_pages = total
        self.step_start_time = time.time()
        pct = int((current / max(1, total)) * 100)
        self.overall_label.setText(f"📊 Overall Progress: {msg}")
        self.overall_progress.setValue(pct)
        self.update_eta_ticker()

    def update_current_progress(self, current: int, total: int, msg: str):
        pct = int((current / max(1, total)) * 100)
        self.current_label.setText(f"🔍 Current Step: {msg}")
        self.current_progress.setValue(pct)

    def start_processing(self):
        txt = self.img_input.text().strip()
        if not self.selected_image_paths and os.path.exists(txt):
            self.selected_image_paths = extract_archive_if_needed(txt, progress_callback=self.log)

        if not self.selected_image_paths:
            QMessageBox.warning(self, "Input Error", "Please select manga image files or a folder.")
            return

        out_dir = self.out_input.text().strip()
        iopaint_enabled = self.iopaint_enabled_cb.isChecked()
        iopaint_adaptive = self.iopaint_adaptive_cb.isChecked()
        iopaint_url = self.iopaint_url_input.text().strip() or "http://127.0.0.1:8080"
        iopaint_model = self.iopaint_model_combo.currentText().strip() or "anime-lama"
        iopaint_dilation = self.iopaint_dilation_spin.value()
        snap_to_bubbles = False
        mask_padding = self.mask_padding_spin.value()
        self.mask_padding = mask_padding

        # If inpainting is enabled, verify if IOPaint is online
        if iopaint_enabled:
            client = IOPaintClient(iopaint_url)
            is_online, _ = client.check_connection()
            if not is_online:
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("IOPaint Server Offline")
                msg_box.setIcon(QMessageBox.Question)
                msg_box.setText(
                    "⚠️ IOPaint Server (Deep AI Inpainting) is currently offline.\n\n"
                    "If your pages contain complex art backgrounds or screentones, IOPaint is recommended to inpaint them with deep AI.\n\n"
                    "• Would you like to start the IOPaint server automatically now?"
                )
                btn_start = msg_box.addButton("⚡ Start IOPaint & Use", QMessageBox.YesRole)
                btn_continue = msg_box.addButton("⏩ Continue with Fast Cleaning (No IOPaint)", QMessageBox.NoRole)
                btn_cancel = msg_box.addButton("❌ Cancel", QMessageBox.RejectRole)
                msg_box.exec()

                clicked = msg_box.clickedButton()
                if clicked == btn_cancel:
                    return
                elif clicked == btn_start:
                    self.start_silent_iopaint_server()
                    # Show responsive non-blocking waiting dialog
                    progress_dlg = QProgressDialog("⏳ Starting IOPaint Server & loading model into memory...", "Cancel", 0, 100, self)
                    progress_dlg.setWindowTitle("Starting IOPaint Server")
                    progress_dlg.setWindowModality(Qt.WindowModal)
                    progress_dlg.setAutoClose(False)
                    progress_dlg.setAutoReset(False)
                    progress_dlg.setMinimumDuration(0)
                    progress_dlg.show()
                    
                    waiter = IOPaintStartupWaiterWorker(iopaint_url, max_wait_sec=60, parent=None)
                    loop = QEventLoop()

                    def _on_waiter_prog(val, msg):
                        progress_dlg.setValue(val)
                        progress_dlg.setLabelText(msg)

                    def _on_waiter_done(ok, model_or_err):
                        loop.quit()

                    progress_dlg.canceled.connect(waiter.cancel)
                    waiter.progress_signal.connect(_on_waiter_prog)
                    waiter.finished_signal.connect(_on_waiter_done)
                    track_running_worker(waiter)
                    waiter.start()
                    loop.exec()
                    progress_dlg.close()

                    client = IOPaintClient(iopaint_url)
                    started_ok, m = client.check_connection()
                    if not started_ok:
                        reply = QMessageBox.question(
                            self,
                            "IOPaint Server Starting",
                            "⚠️ IOPaint server startup took longer than expected.\n\nWould you like to proceed with Fast Cleaning (Instant white/solid inpainting) now?",
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.Yes
                        )
                        if reply != QMessageBox.Yes:
                            return
                        iopaint_enabled = False
                elif clicked == btn_continue:
                    iopaint_enabled = False

        # Save config
        self.config["last_image_paths"] = self.selected_image_paths
        self.config["last_output_dir"] = out_dir
        self.config["mask_padding"] = mask_padding
        self.config["snap_to_bubbles"] = snap_to_bubbles
        self.config["iopaint_enabled"] = iopaint_enabled
        self.config["iopaint_adaptive"] = iopaint_adaptive
        self.config["iopaint_server_url"] = iopaint_url
        self.config["iopaint_model"] = iopaint_model
        self.config["iopaint_dilation"] = iopaint_dilation
        self.config["iopaint_launcher_path"] = self.iopaint_launcher_input.text().strip()
        self.config["ngrok_authtoken"] = self.ngrok_token_input.text().strip()
        self.config["ngrok_domain"] = self.ngrok_domain_input.text().strip()
        self.save_config()

        self.run_btn.setEnabled(False)
        self.load_proj_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_text.clear()

        self.batch_start_time = time.time()
        self.step_start_time = time.time()
        self.total_batch_pages = len(self.selected_image_paths)
        self.eta_timer.start(500)

        self.log(f"🧹 Starting Batch Cleaning on {len(self.selected_image_paths)} pages (Model: {iopaint_model}, Dilation: {iopaint_dilation}px)...")

        device_mode = self.config.get("device_mode", "auto")
        self.worker = BatchCleanerWorker(
            image_paths=self.selected_image_paths,
            mask_padding=mask_padding,
            snap_to_bubbles=snap_to_bubbles,
            iopaint_enabled=iopaint_enabled,
            iopaint_url=iopaint_url,
            iopaint_model=iopaint_model,
            iopaint_dilation=iopaint_dilation,
            iopaint_adaptive=iopaint_adaptive,
            device=device_mode,
            parent=None
        )
        self.worker.progress_signal.connect(self.log)
        self.worker.overall_progress_signal.connect(self.update_overall_progress)
        self.worker.current_progress_signal.connect(self.update_current_progress)
        self.worker.finished_signal.connect(self.on_processing_finished)
        track_running_worker(self.worker)
        self.worker.start()

    def cancel_processing(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.log("🛑 Cancelling batch cleaning process...")
            self.cancel_btn.setEnabled(False)

    def on_processing_finished(self, success: bool, result):
        self.eta_timer.stop()
        self.cancel_btn.setEnabled(False)
        self.run_btn.setEnabled(True)
        self.load_proj_btn.setEnabled(True)

        if not success:
            QMessageBox.critical(self, "Processing Error", str(result))
            return

        page_results, cleaned_images = result
        out_dir = self.out_input.text().strip()
        iopaint_url = self.iopaint_url_input.text().strip() or "http://127.0.0.1:8080"
        iopaint_model = self.iopaint_model_combo.currentText().strip() or "anime-lama"
        iopaint_dilation = self.iopaint_dilation_spin.value()
        mask_padding = self.mask_padding_spin.value()
        self.mask_padding = mask_padding

        try:
            dialog = MultiPageReviewDialog(
                page_results=page_results,
                output_dir=out_dir,
                parent=None,
                cleaned_pages=cleaned_images,
                iopaint_url=iopaint_url,
                iopaint_model=iopaint_model,
                iopaint_dilation=iopaint_dilation,
                mask_padding=mask_padding
            )
            self.hide()
            try:
                dialog.exec()
            finally:
                try:
                    dialog._cleanup()
                except Exception:
                    pass
                self.show()
                self.raise_()
                self.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "Review Window Error", f"Failed to open studio:\n{e}")

    def load_project_state(self, file_path: str = None):
        if not file_path:
            file_path, _ = QFileDialog.getOpenFileName(self, "Load Cleaner Project", "", "SmartCleaner-AI Project (*.cln *.ftr)")
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                project_data = json.load(f)

            page_results = project_data.get("page_results", {})
            out_dir = project_data.get("output_dir", "")
            cleaned_pages = project_data.get("cleaned_pages", {})
            iopaint_url = project_data.get("iopaint_url", "http://127.0.0.1:8080")
            iopaint_model = project_data.get("iopaint_model", "anime-lama")
            iopaint_dilation = project_data.get("iopaint_dilation", 5)
            mask_padding = project_data.get("mask_padding", self.mask_padding_spin.value())

            if not page_results:
                QMessageBox.warning(self, "Invalid File", "Project file contains no pages.")
                return

            dialog = MultiPageReviewDialog(
                page_results=page_results,
                output_dir=out_dir,
                parent=None,
                cleaned_pages=cleaned_pages,
                iopaint_url=iopaint_url,
                iopaint_model=iopaint_model,
                iopaint_dilation=iopaint_dilation,
                mask_padding=mask_padding
            )
            self.hide()
            try:
                dialog.exec()
            finally:
                try:
                    dialog._cleanup()
                except Exception:
                    pass
                self.show()
                self.raise_()
                self.activateWindow()
        except Exception as e:
            QMessageBox.critical(self, "Error Loading Project", f"Could not load project:\n{e}")

    def show_three_dots_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 6px;
                color: #e2e8f0;
            }
            QMenu::item {
                padding: 9px 22px 9px 14px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 500;
            }
            QMenu::item:hover, QMenu::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #1e293b;
                margin: 4px 6px;
            }
        """)

        about_act = menu.addAction("ℹ️ معلومات عن الإصدار والتطبيق")
        about_act.triggered.connect(self.show_about_dialog)

        update_act = menu.addAction("🔄 التحقق من وجود تحديثات")
        update_act.triggered.connect(lambda: check_for_updates_gui(self, silent=False))

        menu.addSeparator()

        discord_act = menu.addAction("💬 التواصل مع المبرمج (Discord)")
        discord_act.triggered.connect(self.open_developer_discord)

        # Position popup menu directly under the three-dots button aligned with its right edge
        hint = menu.sizeHint()
        btn_pos = self.menu_dots_btn.mapToGlobal(QPoint(0, 0))
        x = btn_pos.x() + self.menu_dots_btn.width() - hint.width()
        y = btn_pos.y() + self.menu_dots_btn.height() + 4
        menu.exec(QPoint(x, y))

    def show_about_dialog(self):
        dlg = AboutAppDialog(version=self.current_app_version, parent=self)
        dlg.exec()

    def open_developer_discord(self):
        dlg = DiscordContactDialog(parent=self)
        dlg.exec()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    gui = CleanerGUI()
    if gui.config.get("window_is_maximized", False):
        gui.showMaximized()
    else:
        gui.show()
    app.processEvents()

    if len(sys.argv) > 1:
        arg_path = sys.argv[1].replace('"', '').replace("'", "")
        if os.path.exists(arg_path) and (arg_path.lower().endswith(".cln") or arg_path.lower().endswith(".ftr")):
            QTimer.singleShot(150, lambda: gui.load_project_state(arg_path))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
