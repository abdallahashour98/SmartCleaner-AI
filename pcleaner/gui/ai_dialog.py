import os
from PySide6 import QtWidgets as Qw, QtCore as Qc
from pcleaner.helpers import tr

class AIDialog(Qw.QDialog):
    def __init__(self, parent=None, saved_key: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("AI Intelligent Matcher"))
        self.setMinimumWidth(450)
        self.setLayout(Qw.QVBoxLayout())

        # Header info
        header = Qw.QLabel(tr("<b>AI Semantic Matching with Gemini 1.5 Flash</b><br/>Maps arbitrary Arabic translations logically to extracted English text."))
        header.setWordWrap(True)
        self.layout().addWidget(header)

        group = Qw.QGroupBox(tr("Configuration"))
        self.layout().addWidget(group)
        form = Qw.QFormLayout(group)

        # Translation File Selection
        self.file_edit = Qw.QLineEdit()
        self.file_edit.setPlaceholderText(tr("Choose translation text file (.txt)"))
        self.browse_btn = Qw.QPushButton(tr("Browse..."))
        self.browse_btn.clicked.connect(self.browse_file)
        
        file_layout = Qw.QHBoxLayout()
        file_layout.addWidget(self.file_edit)
        file_layout.addWidget(self.browse_btn)
        form.addRow(tr("Translation File:"), file_layout)

        # API Key field
        self.key_edit = Qw.QLineEdit()
        self.key_edit.setEchoMode(Qw.QLineEdit.Password)
        self.key_edit.setPlaceholderText(tr("Enter your Gemini API Key here"))
        if saved_key:
            self.key_edit.setText(saved_key)
        form.addRow(tr("Gemini API Key:"), self.key_edit)
        
        # Process Toggle
        self.batch_check = Qw.QCheckBox(tr("Apply across ENTIRE batch of images loaded"))
        self.batch_check.setChecked(True)
        form.addRow(self.batch_check)

        # Bottom Buttons
        self.button_box = Qw.QDialogButtonBox(Qw.QDialogButtonBox.Ok | Qw.QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        self.layout().addWidget(self.button_box)

    def browse_file(self):
        file_path, _ = Qw.QFileDialog.getOpenFileName(
            self,
            tr("Select Translation Text File"),
            "",
            tr("Text Files (*.txt);;All Files (*)")
        )
        if file_path:
            self.file_edit.setText(file_path)

    def validate_and_accept(self):
        if not self.file_edit.text().strip() or not os.path.exists(self.file_edit.text().strip()):
            Qw.QMessageBox.warning(self, tr("Invalid File"), tr("Please choose a valid translation text file first."))
            return
        if not self.key_edit.text().strip():
            Qw.QMessageBox.warning(self, tr("Key Missing"), tr("Google Gemini API key is required to proceed."))
            return
        self.accept()

    def get_inputs(self) -> tuple[str, str, bool]:
        """Returns (file_path, api_key, do_batch)"""
        return self.file_edit.text().strip(), self.key_edit.text().strip(), self.batch_check.isChecked()
