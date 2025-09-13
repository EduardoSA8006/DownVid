import os
import sys
import json
from typing import Dict, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QProgressBar, QHeaderView, QMessageBox, QListWidget, QListWidgetItem,
    QAbstractItemView, QToolBar, QDockWidget, QFileDialog, QWidgetAction
)

from download_manager import DownloadManager
from storage import save_state
from dialogs import AddDownloadDialog, PreferencesDialog
from paths import get_default_download_dirs, ensure_dirs_for_defaults, get_preferred_base_dir


class MainWindow(QMainWindow):
    def __init__(self, manager: DownloadManager, previous_state: Optional[dict] = None):
        super().__init__()
        self.manager = manager
        self.setWindowTitle("DownVid - YouTube Downloader (Tema Escuro)")
        self.setMinimumSize(1200, 760)

        self._task_row: Dict[str, int] = {}  # task_id -> row

        # Defaults usados pelos diálogos (baseados em Documents/DownVid)
        if previous_state and isinstance(previous_state.get("defaults"), dict):
            self.defaults = previous_state["defaults"]
        else:
            self.defaults = get_default_download_dirs()
        ensure_dirs_for_defaults(self.defaults)

        self._build_ui()
        self._connect_signals()

        # Restaurar histórico e fila anterior
        QTimer.singleShot(50, lambda: self._restore_previous_state(previous_state))

    def _build_ui(self):
        # Central: Tabela
        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(8)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "Título/URL", "Tipo", "Qualidade", "Progresso", "Velocidade", "ETA", "Status", "Arquivo", "Ações"
        ])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in [1, 2, 3, 4, 5, 6, 8]:
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        main.addWidget(self.table, 1)

        # Dock: Concluídos (flutuante)
        self.dock_done = QDockWidget("Concluídos", self)
        self.dock_done.setObjectName("dock_concluidos")
        self.dock_done.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        dock_inner = QWidget()
        dock_layout = QVBoxLayout(dock_inner)
        dock_layout.setContentsMargins(6, 6, 6, 6)
        self.list_done = QListWidget()
        dock_layout.addWidget(self.list_done)
        self.dock_done.setWidget(dock_inner)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_done)

        # Toolbar
        tb = QToolBar("Ações", self)
        tb.setMovable(True)
        self.addToolBar(tb)

        self.act_new = QAction("Novo Download", self)
        self.act_pause_all = QAction("Pausar todos", self)
        self.act_resume_all = QAction("Retomar todos", self)
        self.act_cancel_sel = QAction("Cancelar selecionados", self)
        self.act_open_folder = QAction("Abrir pasta de downloads", self)

        tb.addAction(self.act_new)
        tb.addSeparator()
        tb.addAction(self.act_pause_all)
        tb.addAction(self.act_resume_all)
        tb.addAction(self.act_cancel_sel)
        tb.addSeparator()

        # Concorrência como widgets embutidos
        lbl_conc = QLabel("Concorrência:")
        self.spin_conc = QSpinBox()
        self.spin_conc.setRange(1, 16)
        self.spin_conc.setValue(3)
        w_conc = QWidget()
        h_conc = QHBoxLayout(w_conc)
        h_conc.setContentsMargins(0, 0, 0, 0)
        h_conc.setSpacing(6)
        h_conc.addWidget(lbl_conc)
        h_conc.addWidget(self.spin_conc)
        act_conc = QWidgetAction(self)
        act_conc.setDefaultWidget(w_conc)
        tb.addAction(act_conc)

        tb.addSeparator()
        tb.addAction(self.act_open_folder)

        # Menu
        menu_bar = self.menuBar()

        m_file = menu_bar.addMenu("Arquivo")
        self.act_export = QAction("Exportar fila...", self)
        self.act_import = QAction("Importar fila...", self)
        self.act_prefs = QAction("Preferências...", self)
        m_file.addAction(self.act_export)
        m_file.addAction(self.act_import)
        m_file.addSeparator()
        m_file.addAction(self.act_prefs)

        m_view = menu_bar.addMenu("Exibir")
        self.act_toggle_done = self.dock_done.toggleViewAction()
        m_view.addAction(self.act_toggle_done)

        m_help = menu_bar.addMenu("Ajuda")
        about_action = QAction("Sobre", self)
        m_help.addAction(about_action)
        about_action.triggered.connect(self._show_about)

        # Status bar
        self.statusBar().showMessage("Pronto")

    def _connect_signals(self):
        # Toolbar actions
        self.act_new.triggered.connect(self.on_new_download)
        self.act_pause_all.triggered.connect(self.manager.pause_all)
        self.act_resume_all.triggered.connect(self.manager.resume_all)
        self.act_cancel_sel.triggered.connect(self.on_cancel_selected)
        self.act_open_folder.triggered.connect(self.on_open_folder)

        # Concurrency
        self.spin_conc.valueChanged.connect(self.on_concurrency_changed)

        # Menu actions
        self.act_export.triggered.connect(self.on_export_queue)
        self.act_import.triggered.connect(self.on_import_queue)
        self.act_prefs.triggered.connect(self.on_open_preferences)

        # Manager signals
        s = self.manager.signals
        s.queued.connect(self.on_task_queued)
        s.meta.connect(self.on_task_meta)
        s.progress.connect(self.on_task_progress)
        s.status.connect(self.on_task_status)
        s.finished.connect(self.on_task_finished)
        s.error.connect(self.on_task_error)
        s.removed.connect(self.on_task_removed)

    def _show_about(self):
        QMessageBox.information(
            self, "Sobre",
            "DownVid (PySide6) - Downloader do YouTube com tema escuro.\n\n"
            "Apenas para fins educacionais. Respeite direitos autorais e os Termos de Serviço do YouTube."
        )

    # Ações

    def on_concurrency_changed(self, n: int):
        self.manager.set_concurrency(n)
        self.statusBar().showMessage(f"Paralelismo ajustado para {n}")

    def on_open_folder(self):
        # Abre a pasta base preferida (ex.: Documents/DownVid)
        base = get_preferred_base_dir(self.defaults)
        try:
            os.makedirs(base, exist_ok=True)
        except Exception:
            pass

        if os.name == "nt":
            os.startfile(base)
        elif sys.platform == "darwin":
            os.system(f'open "{base}"')
        else:
            os.system(f'xdg-open "{base}"')

    def on_cancel_selected(self):
        rows = set([i.row() for i in self.table.selectedIndexes()])
        ids = []
        for r in rows:
            tid_item = self.table.item(r, 0)
            if tid_item:
                tid = tid_item.data(Qt.ItemDataRole.UserRole)
                if tid:
                    ids.append(tid)
        if not ids:
            return
        self.manager.cancel_selected(ids)
        self._persist_state()

    def on_new_download(self):
        dlg = AddDownloadDialog(self, defaults=self.defaults)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        urls = dlg.get_urls()
        if not urls:
            QMessageBox.warning(self, "URL vazia", "Cole pelo menos uma URL de vídeo ou playlist do YouTube.")
            return

        opts = dlg.get_options()
        added_count = 0
        for u in urls:
            tasks = self.manager.add_url(
                u,
                kind=opts["kind"],
                dest_dir=opts["dest_dir"],
                quality_height=opts["quality_height"],
                audio_quality=opts["audio_quality"],
                subs_langs=opts["subs_langs"],
                embed_subs=opts["embed_subs"],
                container=opts["container"],
            )
            added_count += len(tasks)
        self.statusBar().showMessage(f"Adicionados {added_count} itens à fila.")
        self._persist_state()

        # Atualiza defaults se usuário mudou de pasta no diálogo
        if opts["kind"] == "video":
            self.defaults["video_dir"] = opts["dest_dir"]
        else:
            self.defaults["audio_dir"] = opts["dest_dir"]
        ensure_dirs_for_defaults(self.defaults)
        self._persist_state()

    def on_open_preferences(self):
        dlg = PreferencesDialog(self, defaults=self.defaults.copy())
        if dlg.exec() == dlg.DialogCode.Accepted:
            new_defaults = dlg.get_defaults()
            self.defaults.update(new_defaults)
            ensure_dirs_for_defaults(self.defaults)
            self._persist_state()
            self.statusBar().showMessage("Preferências atualizadas.")

    # Sinais do Manager

    def on_task_queued(self, task_id: str):
        task = self.manager.tasks.get(task_id)
        if not task:
            return
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Coluna 0 - Título/URL (atualiza com meta)
        item0 = QTableWidgetItem(task.url)
        item0.setData(Qt.ItemDataRole.UserRole, task_id)
        self.table.setItem(row, 0, item0)

        # Coluna 1 - Tipo
        item1 = QTableWidgetItem("Áudio (MP3)" if task.kind == "audio" else f"Vídeo ({task.container.upper()})")
        self.table.setItem(row, 1, item1)

        # Coluna 2 - Qualidade
        if task.kind == "audio":
            qtxt = f"{task.audio_quality or '320'} kbps"
        else:
            qtxt = f"{task.quality_height}p" if task.quality_height else "Auto"
            if task.subs_langs:
                qtxt += " + Legendas"
                if task.embed_subs:
                    qtxt += " (inc.)"
        self.table.setItem(row, 2, QTableWidgetItem(qtxt))

        # Coluna 3 - Progresso
        pb = QProgressBar()
        pb.setRange(0, 100)
        pb.setValue(0)
        self.table.setCellWidget(row, 3, pb)

        # Coluna 4 - Velocidade
        self.table.setItem(row, 4, QTableWidgetItem(""))

        # Coluna 5 - ETA
        self.table.setItem(row, 5, QTableWidgetItem(""))

        # Coluna 6 - Status
        self.table.setItem(row, 6, QTableWidgetItem(task.status_text))

        # Coluna 7 - Arquivo
        self.table.setItem(row, 7, QTableWidgetItem(""))

        # Coluna 8 - Ações
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        btn_pause = QPushButton("Pausar")
        btn_resume = QPushButton("Retomar")
        btn_cancel = QPushButton("Cancelar")
        btn_pause.clicked.connect(lambda _, tid=task_id: (self.manager.pause_task(tid), self._persist_state()))
        btn_resume.clicked.connect(lambda _, tid=task_id: (self.manager.resume_task(tid), self._persist_state()))
        btn_cancel.clicked.connect(lambda _, tid=task_id: (self.manager.cancel_task(tid), self._persist_state()))
        h.addWidget(btn_pause)
        h.addWidget(btn_resume)
        h.addWidget(btn_cancel)
        self.table.setCellWidget(row, 8, w)

        self._task_row[task_id] = row
        self._persist_state()

    def on_task_meta(self, task_id: str, meta: Dict):
        row = self._task_row.get(task_id)
        if row is None:
            return
        title = meta.get("title") or ""
        it = self.table.item(row, 0)
        if it:
            it.setText(title)
        self._persist_state()

    def on_task_progress(self, task_id: str, data: Dict):
        row = self._task_row.get(task_id)
        if row is None:
            return
        pb = self.table.cellWidget(row, 3)
        if isinstance(pb, QProgressBar):
            pb.setValue(int(data.get("progress", 0)))
        vitem = self.table.item(row, 4)
        if vitem:
            vitem.setText(data.get("speed", ""))
        eitem = self.table.item(row, 5)
        if eitem:
            eitem.setText(data.get("eta", ""))
        sitem = self.table.item(row, 6)
        if sitem:
            sitem.setText(data.get("status", ""))

    def on_task_status(self, task_id: str, status: str):
        row = self._task_row.get(task_id)
        if row is None:
            return
        sitem = self.table.item(row, 6)
        if sitem:
            sitem.setText(status)

    def on_task_finished(self, task_id: str, filepath: str):
        row = self._task_row.get(task_id)
        if row is None:
            return
        sitem = self.table.item(row, 6)
        if sitem:
            sitem.setText("Concluído")
        pb = self.table.cellWidget(row, 3)
        if isinstance(pb, QProgressBar):
            pb.setValue(100)
        aitem = self.table.item(row, 7)
        if aitem and filepath:
            aitem.setText(filepath)

        # Atualiza dock "Concluídos"
        text = filepath if filepath else (self.table.item(row, 0).text() if self.table.item(row, 0) else "")
        self.list_done.addItem(QListWidgetItem(text))
        self._persist_state()

    def on_task_error(self, task_id: str, message: str):
        row = self._task_row.get(task_id)
        if row is None:
            return
        sitem = self.table.item(row, 6)
        if sitem:
            sitem.setText(f"Erro: {message}")
        self._persist_state()

    def on_task_removed(self, task_id: str):
        row = self._task_row.pop(task_id, None)
        if row is not None:
            self.table.removeRow(row)
        self._persist_state()

    # Exportar/Importar e Estado

    def on_export_queue(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar fila", os.path.join(get_preferred_base_dir(self.defaults), "fila.json"), "JSON (*.json)")
        if not path:
            return
        data = self._compose_state(include_completed=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.statusBar().showMessage(f"Fila exportada para {path}")
        except Exception as e:
            QMessageBox.critical(self, "Erro ao exportar", f"Falha ao salvar arquivo: {e!r}")

    def on_import_queue(self):
        start_dir = get_preferred_base_dir(self.defaults)
        path, _ = QFileDialog.getOpenFileName(self, "Importar fila", start_dir, "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Erro ao importar", f"Falha ao ler arquivo: {e!r}")
            return

        queue = (data or {}).get("queue", [])
        # Restaura defaults se presentes
        defaults = (data or {}).get("defaults")
        if isinstance(defaults, dict):
            self.defaults.update(defaults)
            ensure_dirs_for_defaults(self.defaults)

        added = 0
        for item in queue:
            kind = item.get("kind", "video")
            dest = item.get("dest_dir") or (self.defaults["video_dir"] if kind == "video" else self.defaults["audio_dir"])
            tasks = self.manager.add_url(
                item.get("url", ""),
                kind=kind,
                dest_dir=dest,
                quality_height=item.get("quality_height"),
                audio_quality=item.get("audio_quality") or "320",
                subs_langs=item.get("subs_langs"),
                embed_subs=bool(item.get("embed_subs")),
                container=item.get("container") or "mp4",
            )
            added += len(tasks)
        self.statusBar().showMessage(f"Importado(s) {added} item(ns) da fila.")
        self._persist_state()

    def _compose_state(self, include_completed: bool = True) -> dict:
        # Snapshot da fila atual
        queue = []
        for t in self.manager.tasks.values():
            if t.status_text != "Concluído":
                queue.append({
                    "url": t.url,
                    "kind": t.kind,
                    "dest_dir": t.dest_dir,
                    "quality_height": t.quality_height,
                    "audio_quality": t.audio_quality,
                    "subs_langs": t.subs_langs,
                    "embed_subs": t.embed_subs,
                    "container": t.container,
                    "title": t.title,
                })
        state = {
            "version": 2,
            "queue": queue,
            "defaults": self.defaults,
        }
        if include_completed:
            completed = []
            for i in range(self.list_done.count()):
                completed.append(self.list_done.item(i).text())
            state["completed"] = completed
        return state

    def _persist_state(self):
        try:
            save_state(self._compose_state(include_completed=True))
        except Exception:
            pass

    def _restore_previous_state(self, previous_state: Optional[dict]):
        # Defaults
        if previous_state and isinstance(previous_state.get("defaults"), dict):
            self.defaults.update(previous_state["defaults"])
            ensure_dirs_for_defaults(self.defaults)

        # Restaurar concluídos
        if previous_state and previous_state.get("completed"):
            for text in previous_state["completed"]:
                self.list_done.addItem(QListWidgetItem(text))

        # Perguntar se quer recarregar fila anterior
        queue = (previous_state or {}).get("queue", [])
        if queue:
            ret = QMessageBox.question(
                self,
                "Recarregar fila anterior?",
                f"Foi encontrada uma fila salva com {len(queue)} item(ns).\n"
                f"Deseja recarregar e iniciar os downloads agora?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if ret == QMessageBox.StandardButton.Yes:
                added = 0
                for item in queue:
                    kind = item.get("kind", "video")
                    dest = item.get("dest_dir") or (self.defaults["video_dir"] if kind == "video" else self.defaults["audio_dir"])
                    tasks = self.manager.add_url(
                        item.get("url", ""),
                        kind=kind,
                        dest_dir=dest,
                        quality_height=item.get("quality_height"),
                        audio_quality=item.get("audio_quality") or "320",
                        subs_langs=item.get("subs_langs"),
                        embed_subs=bool(item.get("embed_subs")),
                        container=item.get("container") or "mp4",
                    )
                    added += len(tasks)
                self.statusBar().showMessage(f"Recarregados {added} item(ns) da fila salva.")
        # Concurrency default
        self.on_concurrency_changed(self.spin_conc.value())