import sys
import os
import shutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from widgets import MainWindow
from download_manager import DownloadManager
from theme import apply_dark_theme
from storage import load_state


def ensure_dirs():
    base = os.path.join(os.getcwd(), "downloads")
    os.makedirs(base, exist_ok=True)
    os.makedirs(os.path.join(base, "audio"), exist_ok=True)
    os.makedirs(os.path.join(base, "video"), exist_ok=True)


def main():
    ensure_dirs()
    app = QApplication(sys.argv)
    app.setApplicationName("DownVid - YouTube Downloader (Dark)")
    app.setOrganizationName("DownVid")
    app.setStyle("Fusion")
    apply_dark_theme(app)

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        def warn_ffmpeg():
            QMessageBox.warning(
                None,
                "FFmpeg não encontrado",
                "FFmpeg não foi encontrado no PATH. Conversão para MP3 e mesclagem/embutir legendas podem falhar.\n\n"
                "Instale o FFmpeg e garanta que o executável 'ffmpeg' esteja no PATH."
            )
        QTimer.singleShot(700, warn_ffmpeg)

    manager = DownloadManager()
    previous_state = load_state()
    window = MainWindow(manager, previous_state)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()