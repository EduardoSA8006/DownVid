import os
import sys
from typing import Dict, Optional


def _linux_xdg_documents_dir() -> Optional[str]:

    try:
        home = os.path.expanduser("~")
        cfg = os.path.join(home, ".config", "user-dirs.dirs")
        if not os.path.isfile(cfg):
            return None
        with open(cfg, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("XDG_DOCUMENTS_DIR"):
                    # Formato: XDG_DOCUMENTS_DIR="$HOME/Documents"
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        val = parts[1].strip().strip('"')
                        val = val.replace("$HOME", home)
                        val = os.path.expandvars(val)
                        return os.path.normpath(val)
    except Exception:
        pass
    return None


def get_user_documents_dir() -> str:
    home = os.path.expanduser("~")

    if sys.platform.startswith("win"):
        # Caminho padrão costuma ser %USERPROFILE%\Documents (nome apresentado pode ser localizado)
        doc = os.path.join(os.environ.get("USERPROFILE", home), "Documents")
        return doc if os.path.isdir(doc) or not os.path.isdir(home) else doc

    if sys.platform == "darwin":
        # macOS
        doc = os.path.join(home, "Documents")
        return doc

    # Linux e outros POSIX
    xdg_doc = _linux_xdg_documents_dir()
    if xdg_doc:
        return xdg_doc
    # Fallbacks
    doc = os.path.join(home, "Documents")
    if os.path.isdir(doc) or not os.path.isdir(home):
        return doc
    return home  # último recurso


def get_default_download_dirs(app_folder_name: str = "DownVid") -> Dict[str, str]:

    base = os.path.join(get_user_documents_dir(), app_folder_name)
    return {
        "video_dir": os.path.join(base, "video"),
        "audio_dir": os.path.join(base, "audio"),
    }


def ensure_dirs_for_defaults(defaults: Dict[str, str]):
    """
    Cria as pastas default de áudio e vídeo, se não existirem.
    """
    try:
        for key in ("video_dir", "audio_dir"):
            d = defaults.get(key)
            if d:
                os.makedirs(d, exist_ok=True)
    except Exception:
        pass


def get_preferred_base_dir(defaults: Dict[str, str]) -> str:
    video_dir = defaults.get("video_dir", "")
    audio_dir = defaults.get("audio_dir", "")
    paths = [p for p in (video_dir, audio_dir) if p]
    if len(paths) >= 2:
        try:
            common = os.path.commonpath(paths)
            return common
        except Exception:
            pass
    # Fallback para a pasta pai de video_dir
    if video_dir:
        parent = os.path.dirname(video_dir)
        return parent or video_dir
    # Último recurso: Documents/DownVid
    base = os.path.join(get_user_documents_dir(), "DownVid")
    return base