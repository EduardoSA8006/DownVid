import os
import sys
import json
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QFileDialog, QComboBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QProgressBar, QHeaderView, QMessageBox, QTabWidget, QListWidget, QListWidgetItem,
    QAbstractItemView, QCheckBox, QLineEdit, QGroupBox, QFormLayout
)

from download_manager import DownloadManager, DownloadTask
from storage import save_state, load_state


class MainWindow(QMainWindow):
    def __init__(self, manager: DownloadManager, previous_state: Optional[dict] = None):
        super().__init__()
        self.manager = manager
        self.setWindowTitle("DownVid - YouTube Downloader (Tema Escuro)")
        self.setMinimumSize(1200, 760)

        self._task_row: Dict[str, int] = {}  # task_id -> row
        self._completed: List[str] = []

        self._build_ui()
        self._connect_signals()

        # Restaurar histórico e fila anterior
        QTimer.singleShot(50, lambda: self._restore_previous_state(previous_state))

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(10)

        # Linha 1 - Entrada e botões
        controls = QHBoxLayout()

        self.input_url = QPlainTextEdit()
        self.input_url.setPlaceholderText(
            "Cole aqui a URL do vídeo ou playlist do YouTube. "
            "Você também pode colar várias URLs (1 por linha)."
        )
        self.input_url.setFixedHeight(80)

        self.btn_add = QPushButton("Adicionar à fila")

        self.combo_kind = QComboBox()
        self.combo_kind.addItem("Vídeo", userData="video")
        self.combo_kind.addItem("Áudio (MP3)", userData="audio")

        self.lbl_conc = QLabel("Downloads simultâneos:")
        self.spin_conc = QSpinBox()
        self.spin_conc.setRange(1, 16)
        self.spin_conc.setValue(3)

        controls.addWidget(self.input_url, 3)
        controls.addWidget(self.btn_add)
        controls.addWidget(self.combo_kind)
        controls.addWidget(self.lbl_conc)
        controls.addWidget(self.spin_conc)

        main.addLayout(controls)

        # Linha 2 - Opções avançadas
        adv_box = QGroupBox("Opções")
        adv_form = QFormLayout(adv_box)

        # Pasta destino
        dest_layout = QHBoxLayout()
        self.dest_dir_edit = QLineEdit(os.path.join(os.getcwd(), "downloads", "video"))
        self.dest_dir_btn = QPushButton("Escolher pasta")
        self.dest_dir_btn.setFixedWidth(140)
        dest_layout.addWidget(self.dest_dir_edit, 1)
        dest_layout.addWidget(self.dest_dir_btn, 0)
        adv_form.addRow(QLabel("Pasta destino:"), dest_layout)

        # Qualidade de vídeo
        self.combo_quality = QComboBox()
        self.combo_quality.addItem("Melhor (auto)", userData=None)
        self.combo_quality.addItem("2160p (4K)", userData=2160)
        self.combo_quality.addItem("1440p (2K)", userData=1440)
        self.combo_quality.addItem("1080p (Full HD)", userData=1080)
        self.combo_quality.addItem("720p (HD)", userData=720)
        self.combo_quality.addItem("480p", userData=480)
        self.combo_quality.addItem("360p", userData=360)
        adv_form.addRow(QLabel("Qualidade de vídeo:"), self.combo_quality)

        # Container de vídeo
        self.combo_container = QComboBox()
        self.combo_container.addItem("MP4 (compatível)", userData="mp4")
        self.combo_container.addItem("MKV (ideal p/ legendas)", userData="mkv")
        adv_form.addRow(QLabel("Formato do vídeo:"), self.combo_container)

        # Qualidade de áudio (MP3)
        self.combo_audio_quality = QComboBox()
        for b in ["320", "256", "192", "160", "128"]:
            self.combo_audio_quality.addItem(f"{b} kbps", userData=b)
        adv_form.addRow(QLabel("Qualidade do MP3:"), self.combo_audio_quality)

        # Legendas
        self.chk_subs = QCheckBox("Baixar legendas")
        self.edit_subs_langs = QLineEdit()
        self.edit_subs_langs.setPlaceholderText("Ex.: pt,en")
        subs_row = QHBoxLayout()
        subs_row.addWidget(self.chk_subs)
        subs_row.addWidget(QLabel("Idiomas:"))
        subs_row.addWidget(self.edit_subs_langs)
        adv_form.addRow(QLabel("Legendas:"), subs_row)

        self.chk_embed_subs = QCheckBox("Incorporar legendas ao vídeo")
        adv_form.addRow(QLabel("Legenda no arquivo:"), self.chk_embed_subs)

        main.addWidget(adv_box)

        # Linha 3 - Barra de ações
        actions = QHBoxLayout()
        self.btn_pause_all = QPushButton("Pausar todos")
        self.btn_resume_all = QPushButton("Retomar todos")
        self.btn_cancel_sel = QPushButton("Cancelar selecionados")
        self.btn_open_folder = QPushButton("Abrir pasta de destino")
        actions.addWidget(self.btn_pause_all)
        actions.addWidget(self.btn_resume_all)
        actions.addWidget(self.btn_cancel_sel)
        actions.addStretch(1)
        actions.addWidget(self.btn_open_folder)
        main.addLayout(actions)

        # Abas
        tabs = QTabWidget()
        main.addWidget(tabs, 1)

        # Aba Downloads
        tab_dl = QWidget()
        dl_layout = QVBoxLayout(tab_dl)
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
        dl_layout.addWidget(self.table)
        tabs.addTab(tab_dl, "Downloads")

        # Aba Concluídos
        tab_done = QWidget()
        done_layout = QVBoxLayout(tab_done)
        self.list_done = QListWidget()
        done_layout.addWidget(self.list_done)
        tabs.addTab(tab_done, "Concluídos")

        # Status bar
        self.statusBar().showMessage("Pronto")

        # Menu
        menu_bar = self.menuBar()
        m_file = menu_bar.addMenu("Arquivo")
        self.act_export = QAction("Exportar fila...", self)
        self.act_import = QAction("Importar fila...", self)
        m_file.addAction(self.act_export)
        m_file.addAction(self.act_import)

        about_action = QAction("Sobre", self)
        menu_bar.addAction(about_action)
        about_action.triggered.connect(self._show_about)

        # Visibilidade condicional de opções
        self._refresh_options_visibility()

    def _connect_signals(self):
        self.btn_add.clicked.connect(self.on_add_clicked)
        self.btn_pause_all.clicked.connect(self.manager.pause_all)
        self.btn_resume_all.clicked.connect(self.manager.resume_all)
        self.btn_cancel_sel.clicked.connect(self.on_cancel_selected)
        self.btn_open_folder.clicked.connect(self.on_open_folder)
        self.dest_dir_btn.clicked.connect(self.on_pick_dir)
        self.spin_conc.valueChanged.connect(self.on_concurrency_changed)
        self.combo_kind.currentIndexChanged.connect(self._refresh_options_visibility)
        self.act_export.triggered.connect(self.on_export_queue)
        self.act_import.triggered.connect(self.on_import_queue)

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

    def _refresh_options_visibility(self):
        kind = self.combo_kind.currentData()
        is_video = (kind == "video")
        self.combo_quality.setEnabled(is_video)
        self.combo_container.setEnabled(is_video)
        self.chk_subs.setEnabled(is_video)
        self.edit_subs_langs.setEnabled(is_video and self.chk_subs.isChecked())
        self.chk_embed_subs.setEnabled(is_video and self.chk_subs.isChecked())
        self.combo_audio_quality.setEnabled(not is_video)
        # Ajusta pasta default
        if is_video and "video" not in self.dest_dir_edit.text():
            self.dest_dir_edit.setText(os.path.join(os.getcwd(), "downloads", "video"))
        if (not is_video) and "audio" not in self.dest_dir_edit.text():
            self.dest_dir_edit.setText(os.path.join(os.getcwd(), "downloads", "audio"))

    def on_concurrency_changed(self, n: int):
        self.manager.set_concurrency(n)
        self.statusBar().showMessage(f"Paralelismo ajustado para {n}")

    def on_pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Escolher pasta de destino", self.dest_dir_edit.text().strip() or os.getcwd())
        if d:
            self.dest_dir_edit.setText(d)

    def on_open_folder(self):
        path = self.dest_dir_edit.text().strip()
        if not path or not os.path.isdir(path):
            QMessageBox.warning(self, "Pasta inválida", "Selecione uma pasta de destino válida.")
            return
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')

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

    def _collect_urls_from_input(self) -> List[str]:
        raw = self.input_url.toPlainText()
        lines = [s.strip() for s in raw.splitlines() if s.strip()]
        if not lines and raw.strip():
            lines = [raw.strip()]
        return lines

    def on_add_clicked(self):
        lines = self._collect_urls_from_input()
        if not lines:
            QMessageBox.warning(self, "URL vazia", "Cole pelo menos uma URL de vídeo ou playlist do YouTube.")
            return

        kind = self.combo_kind.currentData()
        dest_dir = self.dest_dir_edit.text().strip() or os.getcwd()

        quality_height = self.combo_quality.currentData()
        audio_quality = self.combo_audio_quality.currentData()
        subs_langs = None
        if self.chk_subs.isChecked():
            langs = self.edit_subs_langs.text().strip()
            if langs:
                subs_langs = [p.strip() for p in langs.split(",") if p.strip()]
        embed_subs = bool(self.chk_embed_subs.isChecked())
        container = self.combo_container.currentData()

        added_count = 0
        for line in lines:
            tasks = self.manager.add_url(
                line,
                kind=kind,
                dest_dir=dest_dir,
                quality_height=quality_height,
                audio_quality=audio_quality,
                subs_langs=subs_langs,
                embed_subs=embed_subs,
                container=container,
            )
            added_count += len(tasks)
        self.statusBar().showMessage(f"Adicionados {added_count} itens à fila.")
        self._persist_state()

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
        # Evita I/O excessivo: persistimos no fim/erro

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

        # Atualiza aba "Concluídos"
        text = filepath if filepath else (self.table.item(row, 0).text() if self.table.item(row, 0) else "")
        self.list_done.addItem(QListWidgetItem(text))
        self._completed.append(text)
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

    def on_export_queue(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar fila", os.path.join(os.getcwd(), "fila.json"), "JSON (*.json)")
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
        path, _ = QFileDialog.getOpenFileName(self, "Importar fila", os.getcwd(), "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Erro ao importar", f"Falha ao ler arquivo: {e!r}")
            return

        queue = (data or {}).get("queue", [])
        added = 0
        for item in queue:
            tasks = self.manager.add_url(
                item.get("url", ""),
                kind=item.get("kind", "video"),
                dest_dir=item.get("dest_dir") or os.getcwd(),
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
        state = {"version": 1, "queue": queue}
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
                    tasks = self.manager.add_url(
                        item.get("url", ""),
                        kind=item.get("kind", "video"),
                        dest_dir=item.get("dest_dir") or os.getcwd(),
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