"""Окно 1. Исходные данные: шаги и маршруты двух подтем диалога."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..model import Route, Step, Subtopic, Theme
from .common import hint, spin

LAWS = [("const", "Константа"), ("normal", "Нормальный"),
        ("uniform", "Равномерный"), ("exp", "Экспоненциальный")]


def _num(text: str) -> float:
    return float(text.strip().replace(",", ".") or 0)


class SubtopicPanel(QGroupBox):
    changed = Signal()

    def __init__(self, number: int, parent=None):
        super().__init__(f"Подтема {number}", parent)
        self.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }"
                           "QGroupBox * { font-weight: normal; font-size: 13px; }")
        self._busy = False

        self.name = QLineEdit()
        self.choice = spin(0, 1, 0.5, 0.05, 2)
        self.p_error = spin(0, 0.99, 0.05, 0.05, 2)
        probs = QHBoxLayout()
        probs.addWidget(QLabel("Вероятность выбора:"))
        probs.addWidget(self.choice)
        probs.addSpacing(16)
        probs.addWidget(QLabel("Вероятность ошибки P:"))
        probs.addWidget(self.p_error)
        probs.addStretch()

        self.steps = QTableWidget(0, 4)
        self.steps.setHorizontalHeaderLabels(["Шаг", "Время шага", "Параметр 1, с", "Параметр 2, с"])
        h = self.steps.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3):
            h.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        legend = QLabel("Константа: П1 = время.  Нормальный: П1 = μ, П2 = σ.  "
                        "Равномерный: от П1 до П2.  Экспоненциальный: П1 = среднее.")
        legend.setStyleSheet("color: #666; font-size: 11px;")
        legend.setWordWrap(True)

        self.routes = QTableWidget(0, 3)
        self.routes.setHorizontalHeaderLabels(["Маршрут", "Вероятность", "Номера шагов по порядку"])
        h = self.routes.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        add = QPushButton("+ маршрут")
        remove = QPushButton("− маршрут")
        add.clicked.connect(lambda: self._add_route(Route(f"М{self.routes.rowCount() + 1}", 0, [1])))
        remove.clicked.connect(self._remove_route)
        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch()

        lay = QVBoxLayout(self)
        lay.addWidget(self.name)
        lay.addLayout(probs)
        lay.addWidget(QLabel("Шаги диалога:"))
        lay.addWidget(self.steps, 3)
        lay.addWidget(legend)
        lay.addWidget(QLabel("Маршруты (например: 1 2 3 7 10):"))
        lay.addWidget(self.routes, 2)
        lay.addLayout(buttons)

        self.name.textChanged.connect(self.changed)
        self.choice.valueChanged.connect(self.changed)
        self.p_error.valueChanged.connect(self.changed)
        self.steps.itemChanged.connect(self._emit)
        self.routes.itemChanged.connect(self._emit)

    def _emit(self, *_):
        if not self._busy:
            self.changed.emit()

    def _add_step(self, st: Step):
        r = self.steps.rowCount()
        self.steps.insertRow(r)
        self.steps.setItem(r, 0, QTableWidgetItem(st.name))
        law = QComboBox()
        for key, title in LAWS:
            law.addItem(title, key)
        law.setCurrentIndex([k for k, _ in LAWS].index(st.dist))
        law.currentIndexChanged.connect(self._emit)
        self.steps.setCellWidget(r, 1, law)
        self.steps.setItem(r, 2, QTableWidgetItem(f"{st.a:g}"))
        self.steps.setItem(r, 3, QTableWidgetItem(f"{st.b:g}" if st.dist in ("normal", "uniform") else ""))

    def _add_route(self, rt: Route):
        if self.routes.rowCount() >= 10:
            return
        self._busy = True
        r = self.routes.rowCount()
        self.routes.insertRow(r)
        self.routes.setItem(r, 0, QTableWidgetItem(rt.name))
        self.routes.setItem(r, 1, QTableWidgetItem(f"{rt.prob:g}"))
        self.routes.setItem(r, 2, QTableWidgetItem(" ".join(map(str, rt.steps))))
        self._busy = False
        self._emit()

    def _remove_route(self):
        if self.routes.rowCount():
            self.routes.removeRow(self.routes.rowCount() - 1)
            self._emit()

    def set_subtopic(self, sub: Subtopic):
        self._busy = True
        self.name.setText(sub.name)
        self.choice.setValue(sub.choice_prob)
        self.p_error.setValue(sub.p_error)
        self.steps.setRowCount(0)
        self.routes.setRowCount(0)
        for st in sub.steps:
            self._add_step(st)
        self._busy = False
        for rt in sub.routes:
            self._add_route(rt)

    def subtopic(self) -> Subtopic:
        where = self.title()
        steps = []
        for r in range(self.steps.rowCount()):
            try:
                a = _num(self.steps.item(r, 2).text())
                b = _num(self.steps.item(r, 3).text() if self.steps.item(r, 3) else "")
            except ValueError:
                raise ValueError(f"{where}, шаг {r + 1}: в параметрах должно быть число")
            steps.append(Step(self.steps.item(r, 0).text(),
                              self.steps.cellWidget(r, 1).currentData(), a, b))
        routes = []
        for r in range(self.routes.rowCount()):
            try:
                prob = _num(self.routes.item(r, 1).text())
                seq = [int(x) for x in self.routes.item(r, 2).text()
                       .replace("-", " ").replace(",", " ").split()]
            except ValueError:
                raise ValueError(f"{where}, маршрут {r + 1}: ошибка в записи")
            routes.append(Route(self.routes.item(r, 0).text(), prob, seq))
        return Subtopic(self.name.text(), self.choice.value(), self.p_error.value(), steps, routes)


class DataTab(QWidget):
    def __init__(self, default_file, parent=None):
        super().__init__(parent)
        self.default_file = default_file
        self.panels = [SubtopicPanel(1), SubtopicPanel(2)]
        self.title = ""

        open_btn = QPushButton("Открыть файл…")
        save_btn = QPushButton("Сохранить в файл…")
        open_btn.clicked.connect(self.open_file)
        save_btn.clicked.connect(self.save_file)
        self.status = QLabel()
        self.status.setWordWrap(True)

        top = QHBoxLayout()
        top.addWidget(hint("Здесь заданы шаги и маршруты двух подтем диалога. Данные уже "
                           "заполнены — можно ничего не менять и сразу перейти на вкладку "
                           "«ЛР1» или «ЛР2». Вероятности маршрутов в подтеме и вероятности "
                           "выбора двух подтем должны давать в сумме 1."), 1)
        top.addWidget(open_btn)
        top.addWidget(save_btn)

        panels = QHBoxLayout()
        for p in self.panels:
            panels.addWidget(p)
            p.changed.connect(self.validate)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(panels, 1)
        lay.addWidget(self.status)

        if default_file.exists():
            self.load(default_file)

    # --- данные ----------------------------------------------------------
    def theme(self) -> Theme:
        """Текущие данные; ValueError, если в них ошибка."""
        theme = Theme(self.title, [p.subtopic() for p in self.panels], "repeat")
        errors = theme.check()
        if errors:
            raise ValueError("\n".join(errors))
        return theme

    def set_theme(self, theme: Theme):
        self.title = theme.title
        for panel, sub in zip(self.panels, theme.subtopics):
            panel.set_subtopic(sub)
        self.validate()

    def validate(self):
        try:
            self.theme()
            self.status.setText("✓ Данные в порядке")
            self.status.setStyleSheet("color: #2e7d32; font-weight: bold;")
        except ValueError as e:
            self.status.setText("⚠ " + str(e).replace("\n", ";  "))
            self.status.setStyleSheet("color: #b3261e; font-weight: bold;")

    # --- файлы -----------------------------------------------------------
    def load(self, path):
        try:
            self.set_theme(Theme.load(path))
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Открытие файла", f"Не удалось прочитать файл:\n{e}")

    def open_file(self):
        name, _ = QFileDialog.getOpenFileName(self, "Открыть", str(self.default_file.parent),
                                              "Данные (*.json)")
        if name:
            self.load(name)

    def save_file(self):
        try:
            theme = self.theme()
        except ValueError as e:
            QMessageBox.warning(self, "Сохранение", f"Сначала исправьте ошибки:\n{e}")
            return
        name, _ = QFileDialog.getSaveFileName(self, "Сохранить", str(self.default_file),
                                              "Данные (*.json)")
        if name:
            theme.save(name)
