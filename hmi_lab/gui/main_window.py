"""Главное окно: три вкладки."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QTabWidget

from .data_tab import DataTab
from .lr1_tab import Lr1Tab
from .lr2_tab import Lr2Tab

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "data" / "energy_dispatch.json"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Интерфейсы человек–ЭВМ — ЛР1 и ЛР2")
        self.resize(1400, 860)
        self.data = DataTab(DEFAULT_FILE)
        tabs = QTabWidget()
        tabs.setStyleSheet("QTabBar::tab { padding: 8px 22px; font-size: 14px; }")
        tabs.addTab(self.data, "1. Исходные данные")
        tabs.addTab(Lr1Tab(self.data.theme), "2. ЛР1 — время диалога")
        tabs.addTab(Lr2Tab(self.data.theme), "3. ЛР2 — эффективность")
        self.setCentralWidget(tabs)
