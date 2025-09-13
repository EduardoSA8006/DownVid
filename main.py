import sys
import os
import shutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from widgets import MainWindow
from download_manager import DownloadManager
from theme import apply_dark_theme
from storage import load_state
from ffmpeg_downloader import ensure_ffmpeg_and_update_path, is_windows
from paths import get_default_download_dirs, ensure_dirs_for_defaults


def main():
    # Carrega estado antes para honrar diretórios previamente escolhidos
    previous_state = load_state()
    defaults = {}
    if previous_state and isinstance(previous_state.get("defaults"), dict):
        defaults = previous_state["defaults"]
    else:
        defaults = get_default_download_dirs()

    # Garante pastas padrão em Documents
    ensure_dirs_for_defaults(defaults)

    app = QApplication(sys.argv)
    app.setApplicationName("DownVid - YouTube Downloader (Dark)")
    app.setOrganizationName("DownVid")
    app.setStyle("Fusion")
    apply_dark_theme(app)

    if is_windows():
        ok_ffmpeg, _ = ensure_ffmpeg_and_update_path(parent=None)
        if not ok_ffmpeg:
            QMessageBox.warning(
                None,
                "FFmpeg não instalado",
                "Não foi possível instalar automaticamente o FFmpeg. "
                "Conversão para MP3 e mesclagem/embutir legendas podem falhar.\n\n"
                "Instale manualmente e garanta que 'ffmpeg.exe' esteja acessível no PATH.",
            )
    else:
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
    window = MainWindow(manager, previous_state)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()