"""Главное окно приложения."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QTabWidget

from ..model import Theme
from .editor_tab import EditorTab
from .lr1_tab import Lr1Tab
from .lr2_tab import Lr2Tab, StudyTab

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_FILE = DATA_DIR / "energy_dispatch.json"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.path: Path | None = None
        self.resize(1400, 860)

        self.editor = EditorTab()
        self.lr1 = Lr1Tab(self.editor.theme)
        self.lr2 = Lr2Tab(self.editor.theme)
        self.study = StudyTab(self.editor.theme, self.lr2.form)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.addTab(self.editor, "Граф диалога")
        tabs.addTab(self.lr1, "ЛР1: время диалога")
        tabs.addTab(self.lr2, "ЛР2: эффективность")
        tabs.addTab(self.study, "ЛР2: исследование")
        self.setCentralWidget(tabs)

        menu = self.menuBar().addMenu("Файл")
        for title, key, slot in (("Открыть…", QKeySequence.Open, self.open),
                                 ("Сохранить", QKeySequence.Save, self.save),
                                 ("Сохранить как…", QKeySequence.SaveAs, self.save_as)):
            act = QAction(title, self)
            act.setShortcut(key)
            act.triggered.connect(slot)
            menu.addAction(act)

        if DEFAULT_FILE.exists():
            self.load(DEFAULT_FILE)
        self._update_title()

    def _update_title(self):
        name = self.path.name if self.path else "без имени"
        self.setWindowTitle(f"Интерфейсы человек–ЭВМ: ЛР1–2 — {name}")

    def load(self, path: Path):
        try:
            self.editor.set_theme(Theme.load(path))
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Открытие файла", f"Не удалось прочитать {path}:\n{e}")
            return
        self.path = Path(path)
        self._update_title()
        self.statusBar().showMessage(f"Загружено: {path}", 5000)

    def open(self):
        name, _ = QFileDialog.getOpenFileName(self, "Открыть вариант", str(DATA_DIR), "JSON (*.json)")
        if name:
            self.load(Path(name))

    def save(self):
        if self.path is None:
            return self.save_as()
        try:
            self.editor.theme().save(self.path)
        except ValueError as e:
            QMessageBox.warning(self, "Сохранение", str(e))
            return
        self.statusBar().showMessage(f"Сохранено: {self.path}", 5000)

    def save_as(self):
        name, _ = QFileDialog.getSaveFileName(self, "Сохранить вариант", str(DATA_DIR), "JSON (*.json)")
        if name:
            self.path = Path(name)
            self._update_title()
            self.save()
