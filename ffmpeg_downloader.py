import os
import sys
import time
import zipfile
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Optional, Tuple

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QDialogButtonBox, QMessageBox

# URLs estáveis de builds para Windows (zip)
# Preferência: build "release-essentials" da gyan.dev (contém bin/ffmpeg.exe)
PRIMARY_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FALLBACK_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-git-essentials.zip"

# Tamanho aproximado para exibir ao usuário (não estrito)
APPROX_SIZE_MB = 100


def is_windows() -> bool:
    return sys.platform.startswith("win")


def get_app_base_dir() -> str:
    # Diretório raiz do programa (instalação). No PyInstaller, é o diretório do executável.
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # Em desenvolvimento, cair para o diretório do projeto (onde está este arquivo)
    return os.path.dirname(os.path.abspath(__file__))


def get_candidate_local_ffmpeg_dir() -> str:
    # Preferimos raiz do programa: <app>/ffmpeg/bin
    base = get_app_base_dir()
    return os.path.join(base, "ffmpeg", "bin")


def get_user_fallback_ffmpeg_dir() -> str:
    # Fallback em pasta do usuário caso Program Files (ou dir protegido) não permita escrita
    local_appdata = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(local_appdata, "DownVid", "ffmpeg", "bin")


def find_local_ffmpeg() -> Optional[str]:
    # Procura ffmpeg.exe nas pastas candidatas locais
    for bin_dir in [get_candidate_local_ffmpeg_dir(), get_user_fallback_ffmpeg_dir()]:
        exe_path = os.path.join(bin_dir, "ffmpeg.exe")
        if os.path.isfile(exe_path):
            return exe_path
    return None


def add_to_path(bin_dir: str):
    # Injeta no PATH do processo atual (não persiste no sistema)
    if bin_dir and os.path.isdir(bin_dir):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


@dataclass
class DownloadResult:
    success: bool
    bin_dir: Optional[str] = None
    error: Optional[str] = None


class FfmpegDownloadWorker(QThread):
    progress = Signal(int)               # 0-100
    status = Signal(str)                 # texto de status
    finished_with_result = Signal(object)  # DownloadResult
    chunk = 1024 * 256                   # 256 KiB

    def __init__(self, target_root: str, url: str):
        super().__init__()
        self._cancel = False
        self.target_root = target_root    # raiz onde extrair (ex.: <app>/ffmpeg)
        self.url = url

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            os.makedirs(self.target_root, exist_ok=True)
            tmp_dir = tempfile.mkdtemp(prefix="ffmpeg_dl_")
            zip_path = os.path.join(tmp_dir, "ffmpeg.zip")

            # Download
            self.status.emit("Baixando FFmpeg...")
            start_t = time.time()
            bytes_done = 0
            total = None

            with urllib.request.urlopen(self.url) as resp, open(zip_path, "wb") as out:
                meta_len = resp.getheader("Content-Length")
                try:
                    total = int(meta_len) if meta_len else None
                except Exception:
                    total = None

                last_update = 0.0
                while True:
                    if self._cancel:
                        raise RuntimeError("cancelled")
                    chunk = resp.read(self.chunk)
                    if not chunk:
                        break
                    out.write(chunk)
                    bytes_done += len(chunk)
                    # Atualiza progresso com parcimônia
                    now = time.time()
                    if total:
                        pct = int(bytes_done * 100 / total)
                    else:
                        # Sem tamanho total; estima por tempo
                        pct = min(99, int((now - start_t) % 100))
                    if now - last_update > 0.05:
                        self.progress.emit(pct)
                        self.status.emit(self._fmt_speed(bytes_done, now - start_t))
                        last_update = now

            self.progress.emit(100)
            self.status.emit("Extraindo arquivos...")
            # Extração
            extract_root = os.path.join(self.target_root)  # ex.: <app>/ffmpeg
            os.makedirs(extract_root, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_root)

            # Localiza bin/ffmpeg.exe dentro do que foi extraído
            bin_dir = None
            for root, dirs, files in os.walk(extract_root):
                if "ffmpeg.exe" in files:
                    bin_dir = root
                    break

            if not bin_dir:
                raise RuntimeError("ffmpeg.exe não encontrado após extração.")

            # Resultado
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass

            self.finished_with_result.emit(DownloadResult(success=True, bin_dir=bin_dir))
        except Exception as e:
            self.finished_with_result.emit(DownloadResult(success=False, error=str(e)))

    @staticmethod
    def _fmt_speed(bytes_done: int, seconds: float) -> str:
        if seconds <= 0:
            return ""
        bps = bytes_done / seconds
        if bps >= 1024 * 1024:
            return f"Baixando... {bps/1024/1024:.1f} MB/s"
        elif bps >= 1024:
            return f"Baixando... {bps/1024:.1f} KB/s"
        return f"Baixando... {bps:.0f} B/s"


class FfmpegDownloadDialog(QDialog):
    def __init__(self, parent=None, target_root: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("Instalando FFmpeg")
        self.setModal(True)
        self.setMinimumWidth(420)

        self._worker: Optional[FfmpegDownloadWorker] = None
        self._result: Optional[DownloadResult] = None

        # Tenta primeiro na raiz do programa; se falhar por permissão, cairá para LOCALAPPDATA
        self.install_root = target_root or os.path.join(get_app_base_dir(), "ffmpeg")

        layout = QVBoxLayout(self)
        self.lbl = QLabel(f"FFmpeg não encontrado.\nBaixar e instalar agora (~{APPROX_SIZE_MB} MB)?")
        self.lbl.setWordWrap(True)
        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        self.prog.setValue(0)
        self.status = QLabel("")
        self.status.setWordWrap(True)

        self.btns = QDialogButtonBox()
        self.btn_ok = self.btns.addButton("Baixar", QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_cancel = self.btns.addButton(QDialogButtonBox.StandardButton.Cancel)

        layout.addWidget(self.lbl)
        layout.addWidget(self.prog)
        layout.addWidget(self.status)
        layout.addWidget(self.btns)

        self.btn_ok.clicked.connect(self._start_download)
        self.btn_cancel.clicked.connect(self._cancel_or_close)

    def _start_download(self):
        # Escolhe URL principal, com fallback automático no término
        self._start_with_url(PRIMARY_URL)

    def _start_with_url(self, url: str, tried_fallback=False):
        try:
            os.makedirs(self.install_root, exist_ok=True)
        except PermissionError:
            # Sem permissão na raiz do programa; usar LOCALAPPDATA
            self.install_root = os.path.dirname(get_user_fallback_ffmpeg_dir())

        self.btn_ok.setEnabled(False)
        self.btn_cancel.setText("Cancelar")
        self.prog.setValue(0)
        self.status.setText("Iniciando download...")

        self._worker = FfmpegDownloadWorker(self.install_root, url)
        self._worker.progress.connect(self.prog.setValue)
        self._worker.status.connect(self.status.setText)
        self._worker.finished_with_result.connect(lambda res: self._on_finished(res, tried_fallback))
        self._worker.start()

    def _on_finished(self, res: DownloadResult, tried_fallback: bool):
        self._result = res
        if not res.success and not tried_fallback:
            # Tenta fallback automaticamente uma vez
            self.status.setText("Falhou. Tentando mirror alternativo...")
            self._start_with_url(FALLBACK_URL, tried_fallback=True)
            return

        if res.success:
            self.prog.setValue(100)
            self.status.setText("FFmpeg instalado com sucesso.")
            self.btn_cancel.setText("Fechar")
            add_to_path(res.bin_dir or "")
            QMessageBox.information(self, "FFmpeg", "Instalação concluída.")
            self.accept()
        else:
            self.btn_ok.setEnabled(True)
            self.btn_cancel.setText("Fechar")
            self.status.setText(f"Falha: {res.error or 'Erro desconhecido'}")

    def _cancel_or_close(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.status.setText("Cancelando...")
            self.btn_cancel.setEnabled(False)
        else:
            self.reject()


def ensure_ffmpeg_and_update_path(parent=None) -> Tuple[bool, Optional[str]]:

    import shutil

    # Se já existe no PATH, ok
    path = shutil.which("ffmpeg")
    if path:
        return True, path

    # Se existe localmente, injeta em PATH e ok
    local = find_local_ffmpeg()
    if local:
        add_to_path(os.path.dirname(local))
        return True, local

    if not is_windows():
        # Em outros SOs, apenas alerta (mantém comportamento antigo)
        return False, None

    # Pergunta e baixa
    dlg = FfmpegDownloadDialog(parent=parent)
    ok = dlg.exec() == QDialog.DialogCode.Accepted

    # Revalida após possível instalação
    if ok:
        path2 = shutil.which("ffmpeg")
        if path2:
            return True, path2

        # Se por algum motivo não entrou no PATH, tenta localizar localmente e injetar
        local2 = find_local_ffmpeg()
        if local2:
            add_to_path(os.path.dirname(local2))
            return True, local2

    return False, None