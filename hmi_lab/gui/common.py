"""Общие элементы интерфейса: карточки, поля, кнопки, фоновые задачи."""
from __future__ import annotations

import traceback

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QLineEdit,
                               QGraphicsDropShadowEffect, QHBoxLayout, QHeaderView, QLabel,
                               QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .. import plots  # noqa: F401 — общие настройки графиков


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def shadow(w: QWidget, blur: int = 24, alpha: int = 18):
    eff = QGraphicsDropShadowEffect(w)
    eff.setBlurRadius(blur)
    eff.setOffset(0, 4)
    eff.setColor(QColor(15, 23, 42, alpha))
    w.setGraphicsEffect(eff)


class Card(QFrame):
    """Белая карточка со скруглёнными углами, заголовком и подзаголовком."""

    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        shadow(self)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(20, 18, 20, 18)
        self.body.setSpacing(10)
        if title or subtitle:
            self.header = QHBoxLayout()
            titles = QVBoxLayout()
            titles.setSpacing(2)
            self.title_label = label(title, "cardTitle")
            titles.addWidget(self.title_label)
            self.subtitle_label = label(subtitle, "muted", wrap=True)
            if subtitle:
                titles.addWidget(self.subtitle_label)
            self.header.addLayout(titles, 1)
            self.body.addLayout(self.header)

    def add(self, w, stretch: int = 0):
        if isinstance(w, QWidget):
            self.body.addWidget(w, stretch)
        else:
            self.body.addLayout(w, stretch)
        return w


class Kpi(QFrame):
    """Показатель крупным числом."""

    def __init__(self, title: str, accent: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("kpiAccent" if accent else "kpi")
        shadow(self, 20, 30 if accent else 14)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        self.title = label(title, "kpiTitle", wrap=True)
        self.value = label("—", "kpiValue")
        if accent:
            self.title.setStyleSheet("color: rgba(255,255,255,0.8);")
        lay.addWidget(self.title)
        lay.addWidget(self.value)

    def set(self, text: str):
        self.value.setText(text)


def page_header(title: str, subtitle: str) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(4, 0, 0, 6)
    lay.setSpacing(4)
    lay.addWidget(label(title, "pageTitle"))
    lay.addWidget(label(subtitle, "pageSub", wrap=True))
    return w


def field(caption: str, widget: QWidget) -> QWidget:
    """Подпись над полем ввода."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(5)
    lay.addWidget(label(caption, "fieldLabel"))
    widget.setMinimumHeight(38)
    lay.addWidget(widget)
    return w


def button(text: str, kind: str = "primary") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(kind)
    b.setCursor(Qt.PointingHandCursor)
    return b


def progress_bar() -> QProgressBar:
    p = QProgressBar()
    p.setTextVisible(False)
    p.setVisible(False)
    return p


class NumberEdit(QLineEdit):
    """Поле для числа: обычная строка ввода с проверкой диапазона.

    Пустое поле при allow_empty означает 0 (например, «авто» для K).
    """
    valueChanged = Signal(float)

    def __init__(self, lo, hi, value, decimals=3, integer=False, allow_empty=False,
                 placeholder="", suffix=""):
        super().__init__()
        self.lo, self.hi, self.decimals, self.integer = lo, hi, decimals, integer
        self.allow_empty = allow_empty
        self.suffix = suffix
        self._value = value
        self.setPlaceholderText(placeholder)
        self.setValue(value)
        self.editingFinished.connect(self._commit)
        self.textEdited.connect(self._live)

    def _parse(self, text: str):
        text = text.replace(self.suffix, "").replace(" ", "").replace(",", ".").strip()
        if not text:
            return 0 if self.allow_empty else None
        try:
            v = float(text)
        except ValueError:
            return None
        if not self.lo <= v <= self.hi:
            return None
        return int(v) if self.integer else v

    def _live(self, text):
        v = self._parse(text)
        bad = v is None
        self.setProperty("invalid", bad)
        self.setStyleSheet("border: 1.5px solid #EF4444; border-radius: 8px;" if bad else "")
        if not bad and v != self._value:
            self._value = v
            self.valueChanged.emit(v)

    def _commit(self):
        v = self._parse(self.text())
        self.setValue(self._value if v is None else v)

    def value(self):
        return self._value

    def setValue(self, v):
        v = int(v) if self.integer else float(v)
        changed = v != self._value
        self._value = v
        if self.allow_empty and v == 0:
            self.setText("")
        elif self.integer:
            self.setText(f"{v:,}".replace(",", " ") + self.suffix)
        else:
            text = f"{v:.{self.decimals}f}"
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            self.setText(text + self.suffix)
        self.setStyleSheet("")
        if changed:
            self.valueChanged.emit(v)


def spin(lo, hi, value, step=0.1, decimals=3, suffix="") -> NumberEdit:
    return NumberEdit(lo, hi, value, decimals, suffix=suffix)


def ispin(lo, hi, value, step=1, allow_empty=False, placeholder="") -> NumberEdit:
    return NumberEdit(lo, hi, value, integer=True, allow_empty=allow_empty,
                      placeholder=placeholder)


class Plot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setStyleSheet("background: transparent;")
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


def table(headers: list[str], editable: bool = False) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(38)
    t.setShowGrid(False)
    t.setFocusPolicy(Qt.StrongFocus if editable else Qt.NoFocus)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    t.horizontalHeader().setHighlightSections(False)
    if not editable:
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    return t


def fill(t: QTableWidget, rows: list[list], fit: bool = True):
    t.setRowCount(len(rows))
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            text = f"{v:,.2f}".replace(",", " ") if isinstance(v, float) else str(v)
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if j == 0:
                f = item.font()
                f.setBold(True)
                item.setFont(f)
            t.setItem(i, j, item)
    if fit:
        t.setFixedHeight(t.horizontalHeader().sizeHint().height()
                         + sum(t.rowHeight(i) for i in range(len(rows))) + 4)
