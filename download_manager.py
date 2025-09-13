import os
import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable, Literal

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool
import yt_dlp
from yt_dlp.utils import DownloadCancelled

Kind = Literal["video", "audio"]


class QtSignals(QObject):
    progress = Signal(str, dict)        # task_id, data: {progress, speed, eta, status}
    status = Signal(str, str)           # task_id, status_text
    meta = Signal(str, dict)            # task_id, meta: {title, ext, filepath}
    finished = Signal(str, str)         # task_id, filepath
    error = Signal(str, str)            # task_id, error_message
    queued = Signal(str)                # task_id
    removed = Signal(str)               # task_id


@dataclass
class DownloadTask:
    url: str
    dest_dir: str
    kind: Kind = "video"  # "video" or "audio"
    # Opções avançadas
    quality_height: Optional[int] = None        # None => melhor disponível
    audio_quality: Optional[str] = "320"        # kbps para MP3
    subs_langs: Optional[List[str]] = None      # ex.: ["pt","en"]
    embed_subs: bool = False
    container: str = "mp4"                      # "mp4" ou "mkv"
    # Estado
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    status_text: str = "Na fila"
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    filepath: Optional[str] = None

    # Controle
    _pause_evt: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _cancel_evt: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self):
        self._pause_evt.set()  # começa em "rodando"

    def pause(self):
        with self._lock:
            self._pause_evt.clear()
            self.status_text = "Pausado"

    def resume(self):
        with self._lock:
            self._pause_evt.set()
            self.status_text = "Retomando..."

    def cancel(self):
        with self._lock:
            self._cancel_evt.set()
            self.status_text = "Cancelando..."

    def is_paused(self) -> bool:
        return not self._pause_evt.is_set()

    def is_cancelled(self) -> bool:
        return self._cancel_evt.is_set()


class YDLLogger:
    def __init__(self, on_log: Optional[Callable[[str], None]] = None):
        self.on_log = on_log or (lambda msg: None)

    def debug(self, msg):
        pass  # muito verboso

    def warning(self, msg):
        self.on_log(f"Aviso: {msg}")

    def error(self, msg):
        self.on_log(f"Erro: {msg}")


class DownloadWorker(QRunnable):
    def __init__(self, task: DownloadTask, signals: QtSignals):
        super().__init__()
        self.task = task
        self.signals = signals

    def run(self):
        try:
            self._execute()
        except DownloadCancelled:
            self.signals.status.emit(self.task.task_id, "Cancelado")
            self.signals.error.emit(self.task.task_id, "Download cancelado pelo usuário.")
        except Exception as e:
            self.signals.status.emit(self.task.task_id, "Erro")
            self.signals.error.emit(self.task.task_id, f"Falha: {e!r}")

    def _progress_hook(self, d: Dict):
        # Pausa cooperativa
        self.task._pause_evt.wait()
        if self.task._cancel_evt.is_set():
            raise DownloadCancelled()

        status = d.get("status", "")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            pct = (downloaded / total * 100.0) if total else 0.0
            speed = d.get("speed", 0) or 0
            eta = d.get("eta", None)

            self.task.progress = pct
            self.task.speed = f"{self._fmt_bytes(speed)}/s" if speed else ""
            self.task.eta = self._fmt_eta(eta) if eta is not None else ""
            self.task.status_text = "Baixando..."

            self.signals.progress.emit(self.task.task_id, {
                "progress": pct,
                "speed": self.task.speed,
                "eta": self.task.eta,
                "status": self.task.status_text,
            })
        elif status == "finished":
            self.task.status_text = "Processando..."
            self.signals.status.emit(self.task.task_id, "Processando...")

    @staticmethod
    def _fmt_bytes(n: float) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while n >= 1024 and i < len(units) - 1:
            n /= 1024.0
            i += 1
        return f"{n:.1f} {units[i]}"

    @staticmethod
    def _fmt_eta(secs: float) -> str:
        secs = int(secs or 0)
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        if h > 0:
            return f"{h}h {m}m {s}s"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"

    def _video_format_for(self, height: Optional[int], container: str) -> str:
        if height is None:
            # melhor disponível
            return "bestvideo*+bestaudio/best"
        if container == "mp4":
            return f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/best[height<={height}][ext=mp4]/best"
        else:  # mkv (qualquer ext)
            return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"

    def _execute(self):
        outtmpl = os.path.join(self.task.dest_dir, "%(title)s [%(id)s].%(ext)s")
        logger = YDLLogger(on_log=lambda msg: self.signals.status.emit(self.task.task_id, msg))

        opts = {
            "outtmpl": outtmpl,
            "progress_hooks": [self._progress_hook],
            "continuedl": True,
            "ignoreerrors": False,
            "noprogress": True,
            "quiet": True,
            "no_warnings": True,
            "logger": logger,
            "retries": 10,
            "fragment_retries": 10,
            "overwrites": False,
            "concurrent_fragment_downloads": 1,
            "prefer_ffmpeg": True,
        }

        # Subtítulos (somente útil para vídeo)
        if self.task.kind == "video" and self.task.subs_langs:
            opts["writesubtitles"] = True
            opts["subtitleslangs"] = self.task.subs_langs
            opts["subtitlesformat"] = "srt/best"
            if self.task.embed_subs:
                # yt-dlp trata embed com postprocessor internamente
                opts["embedsubtitles"] = True

        # Formatos e pós-processadores
        if self.task.kind == "audio":
            aq = self.task.audio_quality or "320"
            opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(aq),
                }],
            })
        else:
            fmt = self._video_format_for(self.task.quality_height, self.task.container)
            opts.update({
                "format": fmt,
                "merge_output_format": self.task.container,
                "postprocessors": [{
                    "key": "FFmpegVideoRemuxer",
                    "preferedformat": self.task.container,
                }],
            })

        # Extrair metadados (titulo)
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl_meta:
            info = ydl_meta.extract_info(self.task.url, download=False)
            title = info.get("title") or self.task.url
            self.task.title = title
            self.signals.meta.emit(self.task.task_id, {"title": title})

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([self.task.url])

        # Resolver caminho final
        final_fp = None
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as y2:
                info2 = y2.extract_info(self.task.url, download=False)
                if self.task.kind == "audio":
                    ext = "mp3"
                else:
                    ext = self.task.container or (info2.get("ext") or "mp4")
                final_fp = os.path.join(self.task.dest_dir, f"{info2.get('title', 'video')} [{info2.get('id', '')}].{ext}")
        except Exception:
            pass

        if final_fp and os.path.exists(final_fp):
            self.task.filepath = final_fp

        self.task.progress = 100.0
        self.task.status_text = "Concluído"
        self.signals.progress.emit(self.task.task_id, {
            "progress": 100.0,
            "speed": "",
            "eta": "",
            "status": "Concluído",
        })
        self.signals.finished.emit(self.task.task_id, self.task.filepath or "")


class DownloadManager(QObject):
    """
    Gerencia fila de downloads com paralelismo ajustável via QThreadPool.
    """
    def __init__(self):
        super().__init__()
        self.signals = QtSignals()
        self.tasks: Dict[str, DownloadTask] = {}
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(3)  # default
        self.default_video_dir = os.path.join(os.getcwd(), "downloads", "video")
        self.default_audio_dir = os.path.join(os.getcwd(), "downloads", "audio")

    def set_concurrency(self, n: int):
        self.pool.setMaxThreadCount(max(1, int(n)))

    def add_url(
        self,
        url: str,
        kind: Kind,
        dest_dir: Optional[str] = None,
        quality_height: Optional[int] = None,
        audio_quality: Optional[str] = "320",
        subs_langs: Optional[List[str]] = None,
        embed_subs: bool = False,
        container: str = "mp4",
    ) -> List[DownloadTask]:
        """
        Adiciona um único vídeo ou expande se for playlist, retornando tarefas criadas (iniciadas automaticamente).
        """
        url = url.strip()
        if not url:
            return []
        try:
            entries = self._expand_playlist(url)
        except Exception:
            entries = [url]

        tasks = []
        for u in entries:
            task = DownloadTask(
                url=u,
                dest_dir=dest_dir or (self.default_audio_dir if kind == "audio" else self.default_video_dir),
                kind=kind,
                quality_height=quality_height,
                audio_quality=audio_quality,
                subs_langs=subs_langs,
                embed_subs=embed_subs,
                container=container,
            )
            self.tasks[task.task_id] = task
            self.signals.queued.emit(task.task_id)
            self._start_task(task)
            tasks.append(task)
        return tasks

    def _start_task(self, task: DownloadTask):
        worker = DownloadWorker(task, self.signals)
        self.pool.start(worker)

    def pause_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task:
            return
        task.pause()
        self.signals.status.emit(task_id, "Pausado")

    def resume_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task:
            return
        task.resume()
        self.signals.status.emit(task_id, "Retomando...")

    def cancel_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task:
            return
        task.cancel()
        self.signals.status.emit(task_id, "Cancelando...")

    def remove_task(self, task_id: str):
        if task_id in self.tasks:
            del self.tasks[task_id]
            self.signals.removed.emit(task_id)

    def pause_all(self):
        for t in self.tasks.values():
            t.pause()
        for tid in list(self.tasks.keys()):
            self.signals.status.emit(tid, "Pausado")

    def resume_all(self):
        for t in self.tasks.values():
            t.resume()
        for tid in list(self.tasks.keys()):
            self.signals.status.emit(tid, "Retomando...")

    def cancel_selected(self, task_ids: List[str]):
        for tid in task_ids:
            self.cancel_task(tid)

    def _expand_playlist(self, url: str) -> List[str]:
        """
        Se url for playlist, retorna lista de URLs de vídeos; caso contrário, retorna [url].
        """
        with yt_dlp.YoutubeDL({"quiet": True, "extract_flat": "in_playlist"}) as ydl:
            info = ydl.extract_info(url, download=False)
            if info is None:
                return [url]
            if "entries" in info:
                out = []
                for e in info["entries"]:
                    if not e:
                        continue
                    eu = e.get("url")
                    if eu and eu.startswith("http"):
                        out.append(eu)
                    else:
                        vid = e.get("id")
                        if vid:
                            out.append(f"https://www.youtube.com/watch?v={vid}")
                return out or [url]
            else:
                return [url]