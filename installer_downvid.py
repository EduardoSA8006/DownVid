import os
import sys
import shutil
import zipfile
import tempfile
import traceback
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

import requests
from requests.adapters import HTTPAdapter
try:
    # urllib3 v1/v2 compat
    from urllib3.util.retry import Retry
except Exception:
    Retry = None  # sem retries avançados

from PySide6.QtCore import QObject, Signal, QThread, Qt
from PySide6.QtGui import QIcon, QFont, QAction
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QCheckBox,
    QMessageBox,
    QFrame,
)

# pywin32 (opcional, para criar atalhos .lnk e resolver diretórios especiais)
try:
    import win32com.client
    from win32com.shell import shell, shellcon  # type: ignore
    PYWIN32_AVAILABLE = True
except Exception:
    PYWIN32_AVAILABLE = False


# ========================
# Configurações do instalador (DownVid)
# ========================
APP_DISPLAY_NAME = "DownVid"
PUBLISHER = "DownVid"
PROJECT_URL = "https://github.com/EduardoSA8006/DownVid"

# Repositório do GitHub para baixar os releases
GITHUB_OWNER = "EduardoSA8006"
GITHUB_REPO = "DownVid"

DOWNLOAD_URL_OVERRIDE: Optional[str] = os.environ.get("DOWNVID_DOWNLOAD_URL") or None
RELEASE_TAG_OVERRIDE: Optional[str] = os.environ.get("DOWNVID_RELEASE_TAG") or None
ASSET_NAME_PREFERENCES = [
    "DownVid-win64.zip",
    "DownVid-Windows.zip",
    "DownVid_win64.zip",
    "DownVid.zip",
]

MAIN_EXE_HINT: Optional[str] = "DownVid.exe"

# Nome dos atalhos
SHORTCUT_NAME = "DownVid"
UNINSTALL_SHORTCUT_NAME = "Desinstalar DownVid"

PROGRESS_WEIGHTS = {
    "download": 60,
    "extract": 30,
    "shortcut": 10,
}


# ========================
# Helpers de SO e Sistema
# ========================
def ensure_admin():
    if os.name != "nt":
        return
    try:
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
        # Reexecuta com privilégios elevados (UAC)
        params = " ".join(f'"{arg}"' for arg in sys.argv[1:])
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        except Exception:
            exe = sys.executable
            script = os.path.abspath(sys.argv[0])
            args = " ".join(f'"{a}"' for a in sys.argv[1:])
            ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, f'"{script}" {args}', None, 1)
        sys.exit(0)
    except Exception:
        pass


def is_windows() -> bool:
    return os.name == "nt"


def get_program_files_dir() -> Path:
    """
    Retorna o diretório "Program Files" apropriado. Tenta detectar 64-bit.
    """
    if not is_windows():
        return Path.home() / "DownVid"
    # Preferir ProgramW6432 em sistemas 64-bit
    pf64 = os.environ.get("ProgramW6432")
    if pf64 and os.path.isdir(pf64):
        return Path(pf64)
    pf = os.environ.get("ProgramFiles")
    if pf and os.path.isdir(pf):
        return Path(pf)
    # Fallback clássico
    return Path("C:/Program Files")


def get_default_install_dir() -> Path:
    return get_program_files_dir() / APP_DISPLAY_NAME


def get_appdata_local_path() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return Path.home() / "AppData" / "Local"
    return Path(local)


def get_desktop_dir(all_users: bool = False) -> Path:
    if PYWIN32_AVAILABLE and is_windows():
        try:
            csidl = shellcon.CSIDL_COMMON_DESKTOPDIRECTORY if all_users else shellcon.CSIDL_DESKTOPDIRECTORY
            desktop = shell.SHGetFolderPath(0, csidl, None, 0)
            return Path(desktop)
        except Exception:
            pass
    # Fallback: Desktop do usuário
    return Path.home() / "Desktop"


def get_start_menu_programs_dir(all_users: bool = True) -> Path:
    """
    Retorna a pasta de "Programas" do Menu Iniciar.
    Por padrão cria para Todos os Usuários (requer admin).
    """
    if PYWIN32_AVAILABLE and is_windows():
        try:
            csidl = shellcon.CSIDL_COMMON_PROGRAMS if all_users else shellcon.CSIDL_PROGRAMS
            path = shell.SHGetFolderPath(0, csidl, None, 0)
            return Path(path)
        except Exception:
            pass
    # Fallback: pasta do usuário
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def human_size(num_bytes: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} EB"


def format_eta(seconds: float) -> str:
    if seconds is None or seconds == float("inf"):
        return "--:--"
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def rmtree_force(path: Path):
    def on_rm_error(func, p, exc_info):
        try:
            os.chmod(p, 0o700)
            func(p)
        except Exception:
            pass
    shutil.rmtree(path, onerror=on_rm_error, ignore_errors=False)


def scan_existing_installations() -> List[Path]:
    """
    Procura instalações antigas em locais comuns: Program Files e AppData\Local.
    """
    found: List[Path] = []
    candidates = [
        get_program_files_dir() / APP_DISPLAY_NAME,
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / APP_DISPLAY_NAME,
        get_appdata_local_path() / APP_DISPLAY_NAME,
        get_appdata_local_path() / "DownVid",
    ]
    for p in candidates:
        if p.exists():
            found.append(p)

    uniq = []
    seen = set()
    for p in found:
        sp = str(p.resolve()).lower()
        if sp not in seen:
            seen.add(sp)
            uniq.append(p)
    return uniq


def find_executable(root: Path, hint: Optional[str] = None) -> Optional[Path]:
    if hint:
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() == ".exe" and p.name.lower() == hint.lower():
                return p
    for p in root.glob("*.exe"):
        return p
    for p in root.rglob("*.exe"):
        return p
    return None


def create_shortcut(target: Path, shortcut_path: Path, icon: Optional[Path] = None, working_dir: Optional[Path] = None, description: str = "", arguments: str = ""):
    if not PYWIN32_AVAILABLE or not is_windows():
        raise RuntimeError("Criar atalho requer pywin32 no Windows.")
    if shortcut_path.suffix.lower() != ".lnk":
        shortcut_path = shortcut_path.with_suffix(".lnk")
    shell_obj = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell_obj.CreateShortcut(str(shortcut_path))
    shortcut.TargetPath = str(target)
    shortcut.WorkingDirectory = str(working_dir or target.parent)
    if arguments:
        shortcut.Arguments = arguments
    if icon and icon.exists():
        shortcut.IconLocation = str(icon)
    else:
        shortcut.IconLocation = str(target)
    if description:
        shortcut.Description = description
    shortcut.save()


def remove_shortcut(shortcut_path: Path):
    try:
        if shortcut_path.suffix.lower() != ".lnk":
            shortcut_path = shortcut_path.with_suffix(".lnk")
        if shortcut_path.exists():
            shortcut_path.unlink(missing_ok=True)
    except Exception:
        pass


def apply_dark_theme(app: QApplication):
    app.setStyle("Fusion")
    from PySide6.QtGui import QPalette, QColor

    dark_palette = QPalette()
    base = QColor("#0d1117")
    panel = QColor("#161b22")
    card = QColor("#1b1f24")
    text = QColor("#e6edf3")
    subtext = QColor("#9da7b1")
    accent = QColor("#1f6feb")
    danger = QColor("#d14343")

    dark_palette.setColor(QPalette.Window, panel)
    dark_palette.setColor(QPalette.WindowText, text)
    dark_palette.setColor(QPalette.Base, base)
    dark_palette.setColor(QPalette.AlternateBase, card)
    dark_palette.setColor(QPalette.ToolTipBase, card)
    dark_palette.setColor(QPalette.ToolTipText, text)
    dark_palette.setColor(QPalette.Text, text)
    dark_palette.setColor(QPalette.Button, card)
    dark_palette.setColor(QPalette.ButtonText, text)
    dark_palette.setColor(QPalette.BrightText, danger)
    dark_palette.setColor(QPalette.Highlight, accent)
    dark_palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))

    app.setPalette(dark_palette)

    app.setStyleSheet("""
        QWidget { font-size: 10.5pt; color: #e6edf3; }
        QMainWindow { background-color: #161b22; }
        QLabel.title { font-weight: 700; font-size: 18pt; }
        QLabel.subtitle { font-size: 10.5pt; color: #9da7b1; }
        QFrame#Header { background-color: #1b1f24; border-bottom: 1px solid #30363d; }
        QFrame#Card { background-color: #0d1117; border: 1px solid #30363d; border-radius: 10px; }
        QPushButton { background-color: #1f6feb20; border: 1px solid #30363d; padding: 9px 14px; border-radius: 8px; }
        QPushButton:hover { background-color: #1f6feb33; }
        QPushButton:pressed { background-color: #1f6feb22; }
        QPushButton#accent { background-color: #1f6feb; border: 1px solid #1a60d1; color: #ffffff; }
        QPushButton#accent:hover { background-color: #2b79ff; }
        QPushButton#accent:pressed { background-color: #1a60d1; }
        QPushButton#danger { background-color: #d1434330; border: 1px solid #d14343; color: #ffdddd; }
        QProgressBar { background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; text-align: center; height: 20px; }
        QProgressBar::chunk { background-color: #2ea043; border-radius: 8px; }
        QTextEdit { background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; }
        QCheckBox::indicator { width: 18px; height: 18px; }
        QCheckBox::indicator:checked { image: none; border: 2px solid #2ea043; background-color: #0d1117; }
        QCheckBox::indicator:unchecked { image: none; border: 2px solid #5A5A60; background-color: #0d1117; }
        QFrame#line { color: #30363d; background-color: #30363d; max-height: 1px; min-height: 1px; }
        a { color: #58a6ff; }
        a:hover { color: #79c0ff; }
    """)


# ========================
# GitHub Release Download
# ========================
def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept": "application/vnd.github+json",
        "User-Agent": "DownVid-Installer/1.0 (+https://github.com/EduardoSA8006/DownVid)",
    })
    # Auth opcional para evitar rate-limit
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        s.headers["Authorization"] = f"Bearer {token}"

    # Retries
    try:
        if Retry:
            retries = Retry(
                total=5,
                connect=5,
                read=5,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET", "HEAD"],
            )
            adapter = HTTPAdapter(max_retries=retries)
            s.mount("https://", adapter)
            s.mount("http://", adapter)
    except Exception:
        pass
    return s


def _pick_asset_url_from_release(release_json: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Escolhe um asset .zip adequado do JSON de um release.
    Retorna (download_url, asset_name).
    """
    assets = release_json.get("assets") or []
    # Primeiro, preferências explícitas
    for pref in ASSET_NAME_PREFERENCES:
        for a in assets:
            name = a.get("name") or ""
            if name.lower() == pref.lower():
                return a.get("browser_download_url"), name
    # Senão, qualquer asset que contenha 'win' e '.zip'
    for a in assets:
        name = (a.get("name") or "").lower()
        if "win" in name and name.endswith(".zip"):
            return a.get("browser_download_url"), a.get("name")
    # Senão, qualquer .zip
    for a in assets:
        name = (a.get("name") or "").lower()
        if name.endswith(".zip"):
            return a.get("browser_download_url"), a.get("name")
    return None, None


def resolve_download_url(log_fn=print) -> Tuple[str, str]:
    """
    Resolve a URL de download do pacote:
    - Se DOWNLOAD_URL_OVERRIDE setado, usa ele.
    - Se RELEASE_TAG_OVERRIDE setado, busca esse release.
    - Caso contrário, usa /releases/latest.
    Retorna (url, label).
    """
    if DOWNLOAD_URL_OVERRIDE:
        return DOWNLOAD_URL_OVERRIDE, "URL direta (override)"

    s = _new_session()
    base = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"

    try:
        if RELEASE_TAG_OVERRIDE:
            resp = s.get(f"{base}/tags/{RELEASE_TAG_OVERRIDE}", timeout=30)
        else:
            resp = s.get(f"{base}/latest", timeout=30)
        resp.raise_for_status()
        rel = resp.json()
        url, asset_name = _pick_asset_url_from_release(rel)
        if not url:
            raise RuntimeError("Nenhum asset .zip compatível encontrado no release selecionado.")
        label = f"GitHub Releases ({rel.get('tag_name') or 'latest'}) • {asset_name}"
        return url, label
    except Exception as e:
        raise RuntimeError(f"Falha ao resolver download no GitHub Releases: {e}")


# ========================
# Instalação (worker)
# ========================
@dataclass
class InstallConfig:
    install_dir: Path
    create_shortcut_desktop: bool
    create_shortcut_startmenu: bool = True
    main_exe_hint: Optional[str] = None
    paths_to_remove: List[Path] = field(default_factory=list)
    download_url: Optional[str] = None
    download_label: Optional[str] = None


class InstallerWorker(QObject):
    # Sinais para UI
    progress = Signal(int)               # 0..100 (geral ponderado)
    status = Signal(str)                 # Texto de status (etapa atual)
    progress_text = Signal(str)          # Texto customizado na barra (% + velocidade + ETA)
    log = Signal(str)                    # Logs detalhados
    finished = Signal(bool, str, str)    # success, message, exe_path (ou "")

    def __init__(self, config: InstallConfig):
        super().__init__()
        self.config = config
        self._stop = False

    def stop(self):
        self._stop = True

    def _emit_progress(self, stage: str, stage_progress: float):
        # Converte progresso da etapa em progresso geral
        total = 0
        if stage == "download":
            total = (stage_progress / 100.0) * PROGRESS_WEIGHTS["download"]
        elif stage == "extract":
            total = PROGRESS_WEIGHTS["download"] + (stage_progress / 100.0) * PROGRESS_WEIGHTS["extract"]
        elif stage == "shortcut":
            total = PROGRESS_WEIGHTS["download"] + PROGRESS_WEIGHTS["extract"] + (stage_progress / 100.0) * PROGRESS_WEIGHTS["shortcut"]
        overall = min(100, int(round(total)))
        self.progress.emit(overall)

    def run(self):
        temp_dir = None
        try:
            if not is_windows():
                raise RuntimeError("Este instalador foi projetado para Windows.")

            self.status.emit("Preparando...")
            self.progress_text.emit("%p%")
            self._emit_progress("download", 0)
            self.log.emit(f"Instalação em: {self.config.install_dir}")

            # Resolve URL do pacote
            try:
                if not self.config.download_url:
                    url, label = resolve_download_url(self.log.emit)
                    self.config.download_url = url
                    self.config.download_label = label
                self.log.emit(f"Origem: {self.config.download_label or self.config.download_url}")
            except Exception as e:
                raise RuntimeError(str(e))

            # Remover instalações antigas (se houver)
            if self.config.paths_to_remove:
                self.status.emit("Removendo instalações anteriores...")
                for p in self.config.paths_to_remove:
                    try:
                        if p.exists():
                            self.log.emit(f"Removendo: {p}")
                            rmtree_force(p)
                    except Exception as e:
                        self.log.emit(f"Falha ao remover {p}: {e}")

            # Limpar diretório de instalação (se existir)
            if self.config.install_dir.exists():
                try:
                    self.log.emit(f"Limpando diretório de instalação existente: {self.config.install_dir}")
                    rmtree_force(self.config.install_dir)
                except Exception as e:
                    self.log.emit(f"Falha ao limpar diretório de instalação: {e}")
                    raise
            self.config.install_dir.mkdir(parents=True, exist_ok=True)

            # Checagem de espaço (opcional, melhor esforço)
            try:
                free_bytes = shutil.disk_usage(str(self.config.install_dir)).free
                self.log.emit(f"Espaço livre no destino: {human_size(free_bytes)}")
            except Exception:
                pass

            # Download
            temp_dir = Path(tempfile.mkdtemp(prefix="downvid_installer_"))
            zip_path = temp_dir / "package.zip"
            self.status.emit("Baixando pacote do GitHub...")
            self._download_with_progress(self.config.download_url, zip_path)

            if self._stop:
                raise RuntimeError("Instalação cancelada pelo usuário.")

            # Extração
            self.status.emit("Extraindo arquivos...")
            self.progress_text.emit("Extraindo... %p%")
            self._extract_with_progress(zip_path, self.config.install_dir)

            # Encontrar executável
            exe_path = find_executable(self.config.install_dir, self.config.main_exe_hint)
            if not exe_path:
                raise FileNotFoundError("Não foi possível localizar o executável (.exe) após a extração.")

            self.log.emit(f"Executável detectado: {exe_path}")

            # Ícone (se existir .ico no pacote)
            icon_candidate = None
            for p in self.config.install_dir.rglob("*.ico"):
                icon_candidate = p
                break

            # Copiar o próprio instalador como "Uninstall DownVid.exe" (se estiver congelado)
            try:
                if getattr(sys, "frozen", False):
                    uninst_exe = self.config.install_dir / "Uninstall DownVid.exe"
                    shutil.copyfile(sys.executable, uninst_exe)
                    self.log.emit(f"Uninstaller copiado: {uninst_exe}")
                else:
                    # Fallback: gerar um .bat de desinstalação
                    uninst_bat = self.config.install_dir / "uninstall_downvid.bat"
                    with open(uninst_bat, "w", encoding="utf-8") as f:
                        f.write(f"""@echo off
echo Desinstalando DownVid...
setlocal
REM Fecha app se estiver aberto (melhor esforço)
taskkill /IM "{MAIN_EXE_HINT or 'DownVid.exe'}" /F >nul 2>&1
REM Apaga atalhos
del "%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs\\DownVid\\*.lnk" /F /Q >nul 2>&1
rmdir "%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs\\DownVid" /S /Q >nul 2>&1
del "%USERPROFILE%\\Desktop\\{SHORTCUT_NAME}.lnk" /F /Q >nul 2>&1
REM Remove arquivos
rmdir "{self.config.install_dir}" /S /Q
echo Concluido.
pause
""")
                    self.log.emit(f"Uninstaller (BAT) criado: {uninst_bat}")
            except Exception as e:
                self.log.emit(f"Aviso: falha ao preparar uninstaller: {e}")

            # Atalho Menu Iniciar
            if self.config.create_shortcut_startmenu:
                try:
                    self.status.emit("Criando atalhos no Menu Iniciar...")
                    self._emit_progress("shortcut", 20)
                    start_menu = get_start_menu_programs_dir(all_users=True)
                    start_menu.mkdir(parents=True, exist_ok=True)
                    start_folder = start_menu / APP_DISPLAY_NAME
                    start_folder.mkdir(parents=True, exist_ok=True)

                    # Atalho principal
                    shortcut_path = start_folder / SHORTCUT_NAME
                    create_shortcut(
                        target=exe_path,
                        shortcut_path=shortcut_path,
                        icon=icon_candidate,
                        working_dir=exe_path.parent,
                        description=f"{APP_DISPLAY_NAME} - {PUBLISHER}",
                    )
                    self.log.emit(f"Atalho (Menu Iniciar): {shortcut_path.with_suffix('.lnk')}")

                    # Atalho de desinstalação
                    try:
                        if getattr(sys, "frozen", False):
                            uninst_target = (self.config.install_dir / "Uninstall DownVid.exe")
                            uninst_args = "--uninstall"
                        else:
                            # se não estiver congelado, aponte para .bat
                            uninst_target = (self.config.install_dir / "uninstall_downvid.bat")
                            uninst_args = ""
                        uninstall_shortcut = start_folder / UNINSTALL_SHORTCUT_NAME
                        create_shortcut(
                            target=uninst_target,
                            shortcut_path=uninstall_shortcut,
                            icon=icon_candidate,
                            working_dir=uninst_target.parent if uninst_target else exe_path.parent,
                            description=f"{APP_DISPLAY_NAME} - Desinstalar",
                            arguments=uninst_args,
                        )
                        self.log.emit(f"Atalho (Uninstall): {uninstall_shortcut.with_suffix('.lnk')}")
                    except Exception as e:
                        self.log.emit(f"Aviso: falha ao criar atalho de desinstalação: {e}")
                except Exception as e:
                    self.log.emit(f"Aviso: falha ao criar atalho no Menu Iniciar: {e}")

            # Atalho na Área de Trabalho
            if self.config.create_shortcut_desktop:
                try:
                    self.status.emit("Criando atalho na Área de Trabalho...")
                    self._emit_progress("shortcut", 60)
                    desktop = get_desktop_dir(all_users=False)
                    desktop.mkdir(parents=True, exist_ok=True)
                    shortcut_path = desktop / SHORTCUT_NAME
                    create_shortcut(
                        target=exe_path,
                        shortcut_path=shortcut_path,
                        icon=icon_candidate,
                        working_dir=exe_path.parent,
                        description=f"{APP_DISPLAY_NAME} - {PUBLISHER}",
                    )
                    self.log.emit(f"Atalho (Desktop): {shortcut_path.with_suffix('.lnk')}")
                except Exception as e:
                    self.log.emit(f"Aviso: falha ao criar atalho na Área de Trabalho: {e}")

            self._emit_progress("shortcut", 100)
            self.status.emit("Concluído!")
            self.progress_text.emit("Concluído! 100%")
            self.progress.emit(100)
            self.finished.emit(True, "Instalação concluída com sucesso.", str(exe_path))

        except Exception as e:
            tb = traceback.format_exc()
            self.log.emit(tb)
            self.finished.emit(False, f"Falha na instalação: {e}", "")
        finally:
            if temp_dir and Path(temp_dir).exists():
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except Exception:
                    pass

    def _download_with_progress(self, url: str, dest: Path):
        # Para assets do GitHub Releases (browser_download_url), o cabeçalho já é octet-stream.
        # Ainda assim, tratamos com stream para mostrar progresso.
        s = requests.Session()
        s.headers.update({
            "Accept": "application/octet-stream",
            "User-Agent": "DownVid-Installer/1.0 (+https://github.com/EduardoSA8006/DownVid)",
        })
        try:
            if Retry:
                retries = Retry(
                    total=5,
                    connect=5,
                    read=5,
                    backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["GET", "HEAD"],
                )
                adapter = HTTPAdapter(max_retries=retries)
                s.mount("https://", adapter)
                s.mount("http://", adapter)
        except Exception:
            pass

        with s.get(url, stream=True, timeout=(15, 60)) as r:
            r.raise_for_status()
            total = r.headers.get("Content-Length")
            total_size = int(total) if total and total.isdigit() else None

            downloaded = 0
            chunk_size = 128 * 1024  # 128KB
            start_time = time.monotonic()
            last_time = start_time
            window_bytes = 0

            # Texto inicial
            if total_size:
                self.status.emit(f"Baixando... 0.0% (0 de {human_size(total_size)})")
                self.progress_text.emit(f"Baixando... %p%  |  0.0 B/s  |  0 / {human_size(total_size)}  |  ETA --:--")
            else:
                self.status.emit("Baixando...")
                self.progress_text.emit("Baixando... %p%")

            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if self._stop:
                        raise RuntimeError("Instalação cancelada pelo usuário durante download.")
                    if not chunk:
                        continue

                    f.write(chunk)
                    downloaded += len(chunk)
                    window_bytes += len(chunk)

                    now = time.monotonic()
                    dt = now - last_time

                    # Atualização periódica de velocidade/ETA (a cada ~0.25s)
                    if dt >= 0.25:
                        speed_bps = window_bytes / dt if dt > 0 else 0.0
                        speed_text = f"{human_size(speed_bps)}/s"
                        if total_size and speed_bps > 0:
                            remaining = max(0, total_size - downloaded)
                            eta_s = remaining / speed_bps
                            eta_text = format_eta(eta_s)
                        else:
                            eta_text = "--:--"

                        if total_size:
                            pct = (downloaded / total_size) * 100.0
                            self._emit_progress("download", pct)
                            self.status.emit(f"Baixando... {pct:.1f}% ({human_size(downloaded)} de {human_size(total_size)})")
                            self.progress_text.emit(
                                f"Baixando... {pct:.1f}%  |  {speed_text}  |  {human_size(downloaded)} / {human_size(total_size)}  |  ETA {eta_text}"
                            )
                        else:
                            # Sem tamanho total conhecido
                            self.status.emit(f"Baixando... {human_size(downloaded)}")
                            self.progress_text.emit(f"Baixando... %p%  |  {speed_text}  |  {human_size(downloaded)}")

                        window_bytes = 0
                        last_time = now

            # Força 100% ao final se total era conhecido
            if total_size:
                self._emit_progress("download", 100)
                avg_speed = downloaded / max(1e-9, (time.monotonic() - start_time))
                self.progress_text.emit(
                    f"Baixando... 100%  |  {human_size(avg_speed)}/s  |  "
                    f"{human_size(downloaded)} / {human_size(total_size)}  |  ETA 00:00"
                )

    def _extract_with_progress(self, zip_path: Path, dest_dir: Path):
        # Extração segura para evitar path traversal
        def is_within_directory(base: Path, target: Path) -> bool:
            try:
                base_resolved = base.resolve()
                target_resolved = target.resolve()
                return str(target_resolved).startswith(str(base_resolved))
            except Exception:
                return False

        with zipfile.ZipFile(zip_path, 'r') as zf:
            infos = [info for info in zf.infolist()]
            total_uncompressed = sum(info.file_size for info in infos if not info.is_dir())
            extracted = 0

            for info in infos:
                if self._stop:
                    raise RuntimeError("Instalação cancelada pelo usuário durante extração.")

                target_path = dest_dir / info.filename
                if not is_within_directory(dest_dir, target_path):
                    raise RuntimeError(f"Arquivo suspeito no ZIP (path traversal): {info.filename}")

                if info.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info, 'r') as source, open(target_path, 'wb') as out:
                        shutil.copyfileobj(source, out)

                    extracted += info.file_size
                    if total_uncompressed > 0:
                        pct = (extracted / total_uncompressed) * 100.0
                        self._emit_progress("extract", pct)
                        self.status.emit(f"Extraindo... {pct:.1f}%")
                        self.progress_text.emit(f"Extraindo... {pct:.1f}%")

            self._emit_progress("extract", 100)
            self.progress_text.emit("Extraindo... 100%")


# ========================
# Desinstalação (worker)
# ========================
class UninstallWorker(QObject):
    progress = Signal(int)
    status = Signal(str)
    log = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, install_dir: Path):
        super().__init__()
        self.install_dir = install_dir
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            if not is_windows():
                raise RuntimeError("Este desinstalador foi projetado para Windows.")
            self.status.emit("Preparando...")
            self.progress.emit(5)

            # Fechar app se estiver aberto (best effort)
            try:
                os.system(f'taskkill /IM "{MAIN_EXE_HINT or "DownVid.exe"}" /F >nul 2>&1')
            except Exception:
                pass

            # Remover atalhos
            self.status.emit("Removendo atalhos...")
            try:
                start_menu = get_start_menu_programs_dir(all_users=True) / APP_DISPLAY_NAME
                remove_shortcut(start_menu / SHORTCUT_NAME)
                remove_shortcut(start_menu / UNINSTALL_SHORTCUT_NAME)
                # Remove pasta se vazia
                try:
                    if start_menu.exists():
                        for child in start_menu.iterdir():
                            break
                        else:
                            start_menu.rmdir()
                except Exception:
                    pass
            except Exception as e:
                self.log.emit(f"Aviso: falha ao remover atalhos do Menu Iniciar: {e}")

            try:
                desktop = get_desktop_dir(all_users=False)
                remove_shortcut(desktop / SHORTCUT_NAME)
            except Exception as e:
                self.log.emit(f"Aviso: falha ao remover atalho da Área de Trabalho: {e}")
            self.progress.emit(25)

            # Remover arquivos
            self.status.emit("Removendo arquivos de instalação...")
            if self.install_dir.exists():
                try:
                    rmtree_force(self.install_dir)
                except Exception as e:
                    raise RuntimeError(f"Falha ao remover diretório de instalação: {e}")

            self.progress.emit(90)
            self.status.emit("Limpando restos...")
            time.sleep(0.2)
            self.progress.emit(100)
            self.finished.emit(True, "Desinstalação concluída.")
        except Exception as e:
            tb = traceback.format_exc()
            self.log.emit(tb)
            self.finished.emit(False, f"Falha na desinstalação: {e}")


# ========================
# Interface (MainWindow)
# ========================
class InstallerWindow(QMainWindow):
    def __init__(self, mode_uninstall: bool = False):
        super().__init__()
        self.mode_uninstall = mode_uninstall
        self.setWindowTitle(f"{'Desinstalador' if mode_uninstall else 'Instalador'} - {APP_DISPLAY_NAME}")
        self.setMinimumSize(820, 600)
        try:
            self.setWindowIcon(QIcon.fromTheme("application"))
        except Exception:
            pass

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Header estilizado
        header = QFrame()
        header.setObjectName("Header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 16, 16, 16)
        title = QLabel(f"{APP_DISPLAY_NAME}")
        title.setObjectName("title")
        title.setProperty("class", "title")
        subtitle = QLabel(
            "Desinstalador com UAC e tema escuro" if mode_uninstall
            else "Instalador com UAC, tema escuro, limpeza de versões antigas e atalhos"
        )
        subtitle.setObjectName("subtitle")
        subtitle.setProperty("class", "subtitle")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        # Card com informações
        info = QFrame()
        info.setObjectName("Card")
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(12, 12, 12, 12)
        info_layout.setSpacing(6)

        if not mode_uninstall:
            link_row = QHBoxLayout()
            lbl_url = QLabel("Projeto:")
            val_url = QLabel(f"<a href='{PROJECT_URL}'>{PROJECT_URL}</a>")
            val_url.setOpenExternalLinks(True)
            link_row.addWidget(lbl_url)
            link_row.addWidget(val_url, 1)
            info_layout.addLayout(link_row)

        path_row = QHBoxLayout()
        lbl_path = QLabel("Pasta de instalação:")
        self.install_path_label = QLabel(str(get_default_install_dir()))
        path_row.addWidget(lbl_path)
        path_row.addWidget(self.install_path_label, 1)
        info_layout.addLayout(path_row)

        if not mode_uninstall:
            # Opções
            options_row = QHBoxLayout()
            self.chk_shortcut_desktop = QCheckBox("Criar atalho na Área de Trabalho")
            self.chk_shortcut_desktop.setChecked(True)
            self.chk_shortcut_startmenu = QCheckBox("Criar atalho no Menu Iniciar")
            self.chk_shortcut_startmenu.setChecked(True)
            options_row.addWidget(self.chk_shortcut_desktop)
            options_row.addWidget(self.chk_shortcut_startmenu)
            options_row.addStretch(1)
            info_layout.addLayout(options_row)

        root.addWidget(info)

        # Linha separadora
        sep = QFrame()
        sep.setObjectName("line")
        sep.setFrameShape(QFrame.HLine)
        root.addWidget(sep)

        # Progresso e ações
        status_row = QHBoxLayout()
        self.status_label = QLabel("Pronto para desinstalar." if mode_uninstall else "Pronto para instalar.")
        status_row.addWidget(self.status_label, 1)

        self.btn_primary = QPushButton("Desinstalar" if mode_uninstall else "Instalar")
        self.btn_primary.setObjectName("danger" if mode_uninstall else "accent")
        self.btn_primary.clicked.connect(self.on_primary)
        status_row.addWidget(self.btn_primary)

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.clicked.connect(self.on_cancel)
        status_row.addWidget(self.btn_cancel)

        root.addLayout(status_row)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        root.addWidget(self.progress)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Logs aparecerão aqui...")
        root.addWidget(self.log, 1)

        # Rodapé
        footer_row = QHBoxLayout()
        self.btn_open_folder = QPushButton("Abrir pasta de instalação")
        self.btn_open_folder.setEnabled(True if mode_uninstall else False)
        self.btn_open_folder.clicked.connect(self.open_install_folder)
        footer_row.addWidget(self.btn_open_folder)

        self.btn_exit = QPushButton("Fechar")
        self.btn_exit.clicked.connect(self.close)
        footer_row.addStretch(1)
        footer_row.addWidget(self.btn_exit)
        root.addLayout(footer_row)

        self.setCentralWidget(central)

        about_action = QAction("Sobre", self)
        about_action.triggered.connect(self.show_about)
        self.menuBar().addAction(about_action)

        self.worker_thread: Optional[QThread] = None
        self.worker_obj: Optional[QObject] = None

        if not PYWIN32_AVAILABLE:
            self.append_log("Aviso: pywin32 não está instalado. A criação de atalhos (.lnk) pode falhar.")
        if not is_windows():
            self.append_log("Aviso: este instalador foi projetado para Windows.")

    def append_log(self, text: str):
        self.log.append(text)

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_progress_text(self, text: str):
        try:
            self.progress.setFormat(text.replace("%", "%%") if "%p%" not in text else text)
        except Exception:
            self.progress.setFormat("%p%")

    def on_primary(self):
        if self.worker_thread is not None:
            return

        install_dir = get_default_install_dir()
        self.install_path_label.setText(str(install_dir))

        if self.mode_uninstall:
            reply = QMessageBox.question(self, "Confirmar", f"Deseja desinstalar o {APP_DISPLAY_NAME} de:\n{install_dir}?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply != QMessageBox.Yes:
                return

            self.progress.setValue(0)
            self.set_progress_text("%p%")
            self.append_log("Iniciando desinstalação...")
            self.toggle_controls(running=True)

            self.worker_thread = QThread()
            self.worker_obj = UninstallWorker(install_dir)
            self.worker_obj.moveToThread(self.worker_thread)

            self.worker_thread.started.connect(self.worker_obj.run)
            self.worker_obj.progress.connect(self.progress.setValue)
            self.worker_obj.status.connect(self.set_status)
            self.worker_obj.log.connect(self.append_log)
            self.worker_obj.finished.connect(self.on_uninstall_finished)
            self.worker_thread.start()
            return

        # Modo instalação
        found_paths = scan_existing_installations()
        if install_dir.exists() and install_dir not in found_paths:
            found_paths.append(install_dir)

        if found_paths:
            msg = "Foram encontradas instalações antigas nas seguintes pastas:\n\n"
            msg += "\n".join(f"- {p}" for p in found_paths)
            msg += "\n\nDeseja remover essas pastas antes de instalar a nova versão?"
            reply = QMessageBox.question(self, "Instalação existente encontrada", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply != QMessageBox.Yes:
                self.append_log("Instalação cancelada pelo usuário (não confirmou remoção da versão antiga).")
                return

        self.progress.setValue(0)
        self.set_progress_text("%p%")
        self.append_log("Resolvendo pacote no GitHub Releases...")
        self.toggle_controls(running=True)

        config = InstallConfig(
            install_dir=install_dir,
            create_shortcut_desktop=self.chk_shortcut_desktop.isChecked(),
            create_shortcut_startmenu=self.chk_shortcut_startmenu.isChecked(),
            main_exe_hint=MAIN_EXE_HINT,
            paths_to_remove=found_paths,
        )

        self.worker_thread = QThread()
        self.worker_obj = InstallerWorker(config)
        self.worker_obj.moveToThread(self.worker_thread)

        self.worker_thread.started.connect(self.worker_obj.run)
        self.worker_obj.progress.connect(self.progress.setValue)
        self.worker_obj.progress_text.connect(self.set_progress_text)
        self.worker_obj.status.connect(self.set_status)
        self.worker_obj.log.connect(self.append_log)
        self.worker_obj.finished.connect(self.on_install_finished)
        self.worker_thread.start()

    def on_cancel(self):
        if self.worker_obj and hasattr(self.worker_obj, "stop"):
            self.worker_obj.stop()
            self.append_log("Solicitando cancelamento...")
            self.set_status("Cancelando...")

    def on_install_finished(self, success: bool, message: str, exe_path: str):
        self.append_log(message)
        self.set_status(message)
        self.toggle_controls(running=False)
        self.btn_open_folder.setEnabled(True)

        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
        self.worker_thread = None
        self.worker_obj = None

        if success and exe_path:
            ret = QMessageBox.question(self, "Concluído", "Instalação concluída. Deseja executar o aplicativo agora?")
            if ret == QMessageBox.Yes:
                try:
                    os.startfile(exe_path)  # somente Windows
                except Exception as e:
                    QMessageBox.warning(self, "Erro", f"Não foi possível iniciar o aplicativo: {e}")
        elif not success:
            QMessageBox.critical(self, "Falha", message)

    def on_uninstall_finished(self, success: bool, message: str):
        self.append_log(message)
        self.set_status(message)
        self.toggle_controls(running=False)

        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
        self.worker_thread = None
        self.worker_obj = None

        if success:
            QMessageBox.information(self, "Concluído", "Desinstalação concluída.")
        else:
            QMessageBox.critical(self, "Falha", message)

    def toggle_controls(self, running: bool):
        self.btn_primary.setEnabled(not running)
        self.btn_primary.setVisible(not running)
        self.btn_cancel.setEnabled(running)

    def open_install_folder(self):
        try:
            path = get_default_install_dir()
            if path.exists():
                os.startfile(str(path))
            else:
                QMessageBox.information(self, "Info", "A pasta de instalação não existe.")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível abrir a pasta: {e}")

    def show_about(self):
        QMessageBox.information(
            self,
            "Sobre",
            f"{APP_DISPLAY_NAME}\n"
            f"{'Desinstalador' if self.mode_uninstall else 'Instalador'} com tema dark e elevação UAC.\n"
            f"Publicador: {PUBLISHER}\n"
            f"Projeto: {PROJECT_URL}",
        )


# ========================
# main
# ========================
def main():
    if not is_windows():
        print("Aviso: este instalador foi projetado para Windows.")
    # Garante elevação admin no início (necessário para Program Files)
    ensure_admin()

    # Modo desinstalação quando chamado com --uninstall
    mode_uninstall = any(arg.lower() == "--uninstall" for arg in sys.argv[1:])

    app = QApplication(sys.argv)
    apply_dark_theme(app)

    font = QFont()
    font.setPointSize(10)
    app.setFont(font)

    w = InstallerWindow(mode_uninstall=mode_uninstall)
    w.resize(900, 640)
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()