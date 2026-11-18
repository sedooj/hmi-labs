"""Главное окно: боковая навигация и три раздела."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QMainWindow, QStackedWidget,
                               QVBoxLayout, QWidget)

from .common import button, label
from .data_tab import DataTab
from .lr1_tab import Lr1Tab
from .lr2_tab import Lr2Tab
from .style import QSS

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "data" / "variant.json"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Интерфейсы человек–ЭВМ")
        self.resize(1440, 900)
        self.setStyleSheet(QSS)

        self.data = DataTab(DEFAULT_FILE)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.data)
        self.pages.addWidget(Lr1Tab(self.data.theme))
        self.pages.addWidget(Lr2Tab(self.data.theme))

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setAttribute(Qt.WA_StyledBackground, True)
        sidebar.setFixedWidth(240)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 24, 16, 16)
        side.setSpacing(6)
        side.addWidget(label("◆ HMI Lab", "brand"))
        side.addWidget(label("Лабораторные работы 1–2", "brandSub", wrap=True))
        self.nav = QButtonGroup(self)
        for i, text in enumerate(("◫   Исходные данные", "◔   ЛР1 · Время диалога",
                                  "◈   ЛР2 · Эффективность")):
            b = button(text, "nav")
            b.setCheckable(True)
            self.nav.addButton(b, i)
            side.addWidget(b)
        self.nav.idClicked.connect(self.pages.setCurrentIndex)
        self.nav.button(0).setChecked(True)
        side.addStretch()
        side.addWidget(label("Интерфейсы человек–ЭВМ", "sidebarFoot", True))

        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(sidebar)
        lay.addWidget(self.pages, 1)
        self.setCentralWidget(root)

    def go(self, index: int):
        self.nav.button(index).setChecked(True)
        self.pages.setCurrentIndex(index)
