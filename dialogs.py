import os
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QComboBox, QLineEdit,
    QPushButton, QFileDialog, QGroupBox, QFormLayout, QCheckBox, QDialogButtonBox, QWidget
)

from paths import get_default_download_dirs


class AddDownloadDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None, defaults: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Novo Download")
        self.setMinimumWidth(600)
        # Defaults (Documents/DownVid) com fallback
        self.defaults = defaults or get_default_download_dirs()
        self._build_ui()
        self._connect_signals()
        self._refresh_visibility()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(10)

        # URLs
        main.addWidget(QLabel("URLs (uma por linha):"))
        self.txt_urls = QPlainTextEdit()
        self.txt_urls.setPlaceholderText("https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/playlist?list=...")
        self.txt_urls.setFixedHeight(100)
        main.addWidget(self.txt_urls)

        # Opções
        box = QGroupBox("Opções")
        form = QFormLayout(box)

        self.combo_kind = QComboBox()
        self.combo_kind.addItem("Vídeo", userData="video")
        self.combo_kind.addItem("Áudio (MP3)", userData="audio")
        form.addRow(QLabel("Tipo:"), self.combo_kind)

        # Destino
        dest_row = QHBoxLayout()
        self.edit_dest = QLineEdit(self.defaults.get("video_dir", get_default_download_dirs()["video_dir"]))
        self.btn_pick_dest = QPushButton("Escolher pasta")
        self.btn_pick_dest.setFixedWidth(140)
        dest_row.addWidget(self.edit_dest, 1)
        dest_row.addWidget(self.btn_pick_dest, 0)
        form.addRow(QLabel("Pasta destino:"), dest_row)

        # Qualidade de vídeo
        self.combo_quality = QComboBox()
        self.combo_quality.addItem("Melhor (auto)", userData=None)
        self.combo_quality.addItem("2160p (4K)", userData=2160)
        self.combo_quality.addItem("1440p (2K)", userData=1440)
        self.combo_quality.addItem("1080p (Full HD)", userData=1080)
        self.combo_quality.addItem("720p (HD)", userData=720)
        self.combo_quality.addItem("480p", userData=480)
        self.combo_quality.addItem("360p", userData=360)
        form.addRow(QLabel("Qualidade de vídeo:"), self.combo_quality)

        # Container de vídeo
        self.combo_container = QComboBox()
        self.combo_container.addItem("MP4 (compatível)", userData="mp4")
        self.combo_container.addItem("MKV (ideal p/ legendas)", userData="mkv")
        form.addRow(QLabel("Formato do vídeo:"), self.combo_container)

        # Qualidade de áudio (MP3)
        self.combo_audio_quality = QComboBox()
        for b in ["320", "256", "192", "160", "128"]:
            self.combo_audio_quality.addItem(f"{b} kbps", userData=b)
        form.addRow(QLabel("Qualidade do MP3:"), self.combo_audio_quality)

        # Legendas
        subs_row = QHBoxLayout()
        self.chk_subs = QCheckBox("Baixar legendas")
        self.edit_subs_langs = QLineEdit()
        self.edit_subs_langs.setPlaceholderText("Ex.: pt,en")
        subs_row.addWidget(self.chk_subs)
        subs_row.addWidget(QLabel("Idiomas:"))
        subs_row.addWidget(self.edit_subs_langs)
        form.addRow(QLabel("Legendas:"), subs_row)

        self.chk_embed_subs = QCheckBox("Incorporar legendas ao vídeo")
        form.addRow(QLabel("Legenda no arquivo:"), self.chk_embed_subs)

        main.addWidget(box)

        # Botões
        self.btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        main.addWidget(self.btns)

    def _connect_signals(self):
        self.btns.accepted.connect(self.accept)
        self.btns.rejected.connect(self.reject)
        self.combo_kind.currentIndexChanged.connect(self._refresh_visibility)
        self.chk_subs.toggled.connect(self._refresh_visibility)
        self.btn_pick_dest.clicked.connect(self._pick_dest)

    def _refresh_visibility(self):
        kind = self.combo_kind.currentData()
        is_video = (kind == "video")
        # Ajuste de pasta padrão ao trocar tipo
        if is_video:
            d = self.defaults.get("video_dir", get_default_download_dirs()["video_dir"])
            if "audio" in (self.edit_dest.text().lower()):
                self.edit_dest.setText(d)
        else:
            d = self.defaults.get("audio_dir", get_default_download_dirs()["audio_dir"])
            if "video" in (self.edit_dest.text().lower()):
                self.edit_dest.setText(d)

        self.combo_quality.setEnabled(is_video)
        self.combo_container.setEnabled(is_video)
        self.chk_subs.setEnabled(is_video)
        self.edit_subs_langs.setEnabled(is_video and self.chk_subs.isChecked())
        self.chk_embed_subs.setEnabled(is_video and self.chk_subs.isChecked())
        self.combo_audio_quality.setEnabled(not is_video)

    def _pick_dest(self):
        start = self.edit_dest.text().strip() or os.getcwd()
        d = QFileDialog.getExistingDirectory(self, "Escolher pasta de destino", start)
        if d:
            self.edit_dest.setText(d)

    def get_urls(self) -> List[str]:
        raw = self.txt_urls.toPlainText()
        lines = [s.strip() for s in raw.splitlines() if s.strip()]
        if not lines and raw.strip():
            lines = [raw.strip()]
        return lines

    def get_options(self) -> Dict:
        kind = self.combo_kind.currentData()
        is_video = (kind == "video")
        defaults = self.defaults or get_default_download_dirs()
        dest = self.edit_dest.text().strip() or (defaults.get("video_dir") if is_video else defaults.get("audio_dir"))
        opts = {
            "kind": kind,
            "dest_dir": dest,
            "quality_height": self.combo_quality.currentData() if is_video else None,
            "audio_quality": self.combo_audio_quality.currentData() if not is_video else None,
            "subs_langs": None,
            "embed_subs": False,
            "container": self.combo_container.currentData() if is_video else "mp4",
        }
        if is_video and self.chk_subs.isChecked():
            langs = self.edit_subs_langs.text().strip()
            if langs:
                opts["subs_langs"] = [p.strip() for p in langs.split(",") if p.strip()]
            opts["embed_subs"] = bool(self.chk_embed_subs.isChecked())
        return opts

    def accept(self):
        if not self.get_urls():
            return
        # Cria diretório destino se não existir
        dest = self.edit_dest.text().strip()
        if dest and not os.path.isdir(dest):
            try:
                os.makedirs(dest, exist_ok=True)
            except Exception:
                pass
        super().accept()


class PreferencesDialog(QDialog):
    def __init__(self, parent: Optional[Widget] = None, defaults: Optional[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Preferências")
        self.defaults = defaults or get_default_download_dirs()
        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(10)

        box = QGroupBox("Diretórios padrão (Documentos/DownVid)")
        form = QFormLayout(box)

        # Vídeo
        row_v = QHBoxLayout()
        self.edit_video_dir = QLineEdit(self.defaults.get("video_dir", get_default_download_dirs()["video_dir"]))
        self.btn_video_dir = QPushButton("Escolher")
        self.btn_video_dir.setFixedWidth(100)
        row_v.addWidget(self.edit_video_dir, 1)
        row_v.addWidget(self.btn_video_dir, 0)
        form.addRow(QLabel("Pasta de vídeo:"), row_v)

        # Áudio
        row_a = QHBoxLayout()
        self.edit_audio_dir = QLineEdit(self.defaults.get("audio_dir", get_default_download_dirs()["audio_dir"]))
        self.btn_audio_dir = QPushButton("Escolher")
        self.btn_audio_dir.setFixedWidth(100)
        row_a.addWidget(self.edit_audio_dir, 1)
        row_a.addWidget(self.btn_audio_dir, 0)
        form.addRow(QLabel("Pasta de áudio:"), row_a)

        main.addWidget(box)

        self.btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        main.addWidget(self.btns)

    def _connect_signals(self):
        self.btns.accepted.connect(self.accept)
        self.btns.rejected.connect(self.reject)
        self.btn_video_dir.clicked.connect(lambda: self._pick_dir(self.edit_video_dir))
        self.btn_audio_dir.clicked.connect(lambda: self._pick_dir(self.edit_audio_dir))

    def _pick_dir(self, edit: QLineEdit):
        start = edit.text().strip() or os.getcwd()
        d = QFileDialog.getExistingDirectory(self, "Escolher pasta", start)
        if d:
            edit.setText(d)

    def get_defaults(self) -> Dict:
        return {
            "video_dir": self.edit_video_dir.text().strip() or get_default_download_dirs()["video_dir"],
            "audio_dir": self.edit_audio_dir.text().strip() or get_default_download_dirs()["audio_dir"],
        }

    def accept(self):
        # Cria diretórios se não existirem
        for p in [self.edit_video_dir.text().strip(), self.edit_audio_dir.text().strip()]:
            if p and not os.path.isdir(p):
                try:
                    os.makedirs(p, exist_ok=True)
                except Exception:
                    pass
        super().accept()