"""Общие элементы интерфейса: холст matplotlib, фоновая задача, таблицы."""
from __future__ import annotations

import traceback

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (QDoubleSpinBox, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget, QHeaderView, QAbstractItemView)

matplotlib.rcParams.update({
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

ACCENT = "#2f6db5"
ACCENT2 = "#d9822b"
ACCENT3 = "#3a9b5c"


class PlotWidget(QWidget):
    """Холст matplotlib с панелью инструментов (масштаб, сохранение в PNG)."""

    def __init__(self, parent=None, toolbar: bool = True):
        super().__init__(parent)
        self.figure = Figure(layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if toolbar:
            lay.addWidget(NavigationToolbar2QT(self.canvas, self))
        lay.addWidget(self.canvas)

    def draw(self):
        self.canvas.draw_idle()


class Task(QThread):
    """Выполняет функцию в фоне, чтобы окно не замирало на время моделирования."""
    progress = Signal(int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn(self.progress.emit))
        except Exception:  # noqa: BLE001 — показываем пользователю любую ошибку
            self.failed.emit(traceback.format_exc())


def spin(lo: float, hi: float, value: float, step: float = 0.1, decimals: int = 3,
         suffix: str = "") -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(decimals)
    w.setSingleStep(step)
    w.setValue(value)
    if suffix:
        w.setSuffix(suffix)
    return w


def ispin(lo: int, hi: int, value: int, step: int = 1) -> QSpinBox:
    w = QSpinBox()
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setValue(value)
    w.setGroupSeparatorShown(True)
    return w


def readonly_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    t.setAlternatingRowColors(True)
    return t


def fill_table(t: QTableWidget, rows: list[list]) -> None:
    t.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            if isinstance(v, float):
                text = f"{v:,.3f}".replace(",", " ")
            else:
                text = str(v)
            item = QTableWidgetItem(text)
            if isinstance(v, (int, float)):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(i, j, item)
