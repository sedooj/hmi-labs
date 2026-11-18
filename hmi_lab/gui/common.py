"""Общие элементы интерфейса."""
from __future__ import annotations

import traceback

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QDoubleSpinBox, QFrame, QHeaderView, QLabel,
                               QProgressBar, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .. import plots  # noqa: F401 — общие настройки графиков


class Plot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.canvas)

    def draw(self):
        self.canvas.draw_idle()


class Task(QThread):
    """Расчёт в фоне, чтобы окно не зависало."""
    progress = Signal(int)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn(self.progress.emit))
        except Exception:  # noqa: BLE001
            self.failed.emit(traceback.format_exc())


def hint(text: str) -> QLabel:
    """Серая подсказка «что здесь делать»."""
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: #555; background: #eef3fa; border-radius: 6px; padding: 8px;")
    return lbl


def section(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 6px;")
    return lbl


def big_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setMinimumHeight(38)
    b.setStyleSheet("QPushButton { background: #2f6db5; color: white; font-weight: bold;"
                    " font-size: 14px; border-radius: 6px; padding: 6px 16px; }"
                    "QPushButton:disabled { background: #9db5d6; }"
                    "QPushButton:hover { background: #255a97; }")
    return b


def progress_bar() -> QProgressBar:
    p = QProgressBar()
    p.setVisible(False)
    p.setTextVisible(False)
    p.setMaximumHeight(6)
    return p


class ValueCard(QFrame):
    """Крупно показанное число с подписью."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("ValueCard { background: white; border: 1px solid #d5dbe3;"
                           " border-radius: 8px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.title = QLabel(title)
        self.title.setStyleSheet("color: #666; border: none;")
        self.title.setWordWrap(True)
        self.value = QLabel("—")
        self.value.setStyleSheet("font-size: 22px; font-weight: bold; color: #1d3f6e; border: none;")
        lay.addWidget(self.title)
        lay.addWidget(self.value)

    def set(self, text: str):
        self.value.setText(text)


def spin(lo, hi, value, step=0.1, decimals=3, suffix="") -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(decimals)
    w.setSingleStep(step)
    w.setValue(value)
    w.setSuffix(suffix)
    return w


def ispin(lo, hi, value, step=1) -> QSpinBox:
    w = QSpinBox()
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setValue(value)
    w.setGroupSeparatorShown(True)
    return w


def result_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionMode(QAbstractItemView.NoSelection)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.setAlternatingRowColors(True)
    return t


def fill(t: QTableWidget, rows: list[list]):
    t.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            text = f"{v:.2f}" if isinstance(v, float) else str(v)
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            t.setItem(i, j, item)
    t.setFixedHeight(t.horizontalHeader().height() + sum(t.rowHeight(i) for i in range(len(rows))) + 4)
