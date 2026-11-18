"""Раздел 1. Исходные данные: шаги и маршруты двух подтем диалога."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QMessageBox, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ..model import Route, Step, Subtopic, Theme
from .common import Card, button, field, label, page_header, spin, table

LAWS = [("const", "Константа"), ("normal", "Нормальный"),
        ("uniform", "Равномерный"), ("exp", "Экспоненциальный")]


def _num(text: str) -> float:
    return float(text.strip().replace(",", ".") or 0)


class SubtopicCard(Card):
    changed = Signal()

    def __init__(self, number: int, parent=None):
        super().__init__(f"Подтема {number}", "", parent)
        self.number = number
        self._busy = False

        self.name = QLineEdit()
        self.choice = spin(0, 1, 0.5, 0.05, 2)
        self.p_error = spin(0, 0.99, 0.05, 0.05, 2)
        top = QGridLayout()
        top.setHorizontalSpacing(12)
        top.addWidget(field("Название", self.name), 0, 0, 1, 2)
        top.addWidget(field("Вероятность выбора подтемы", self.choice), 1, 0)
        top.addWidget(field("Вероятность ошибки P", self.p_error), 1, 1)
        self.add(top)

        self.add(label("Шаги диалога", "cardTitle"))
        self.steps = table(["Шаг", "Время шага", "П1, с", "П2, с"], editable=True)
        h = self.steps.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.Fixed)
        h.setSectionResizeMode(2, QHeaderView.Fixed)
        h.setSectionResizeMode(3, QHeaderView.Fixed)
        self.steps.setColumnWidth(1, 150)
        self.steps.setColumnWidth(2, 56)
        self.steps.setColumnWidth(3, 56)
        self.add(self.steps, 3)
        self.add(label("Константа: П1 — время · Нормальный: П1 = μ, П2 = σ · "
                       "Равномерный: от П1 до П2 · Экспоненциальный: П1 — среднее", "muted", True))

        routes_head = QHBoxLayout()
        routes_head.addWidget(label("Маршруты", "cardTitle"))
        routes_head.addStretch()
        add = button("+ Добавить", "ghost")
        remove = button("− Удалить последний", "ghost")
        add.clicked.connect(lambda: self._add_route(Route(f"М{self.routes.rowCount() + 1}", 0, [1])))
        remove.clicked.connect(self._remove_route)
        routes_head.addWidget(add)
        routes_head.addWidget(remove)
        self.add(routes_head)
        self.routes = table(["Маршрут", "Вероятность", "Шаги по порядку"], editable=True)
        h = self.routes.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        h.setSectionResizeMode(1, QHeaderView.Fixed)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        self.routes.setColumnWidth(1, 100)
        self.add(self.routes, 2)

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
        where = f"Подтема {self.number}"
        steps = []
        for r in range(self.steps.rowCount()):
            try:
                a = _num(self.steps.item(r, 2).text())
                b = _num(self.steps.item(r, 3).text() if self.steps.item(r, 3) else "")
            except ValueError:
                raise ValueError(f"{where}, шаг {r + 1}: в параметрах должно быть число")
            name = self.steps.item(r, 0).text()
            prefix = f"{r + 1}. "
            steps.append(Step(name[len(prefix):] if name.startswith(prefix) else name,
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
        self.setObjectName("page")
        self.default_file = default_file
        self.cards = [SubtopicCard(1), SubtopicCard(2)]
        self.title = ""

        head = QHBoxLayout()
        head.addWidget(page_header(
            "Исходные данные",
            "Шаги и маршруты двух подтем диалога. Данные уже заполнены — можно сразу "
            "переходить к ЛР1 или ЛР2."), 1)
        self.status = QLabel()
        open_btn = button("Открыть файл", "")
        save_btn = button("Сохранить", "")
        open_btn.clicked.connect(self.open_file)
        save_btn.clicked.connect(self.save_file)
        head.addWidget(self.status, 0, Qt.AlignVCenter)
        head.addSpacing(8)
        head.addWidget(open_btn, 0, Qt.AlignVCenter)
        head.addWidget(save_btn, 0, Qt.AlignVCenter)

        cards = QHBoxLayout()
        cards.setSpacing(18)
        for c in self.cards:
            cards.addWidget(c)
            c.changed.connect(self.validate)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)
        lay.addLayout(head)
        lay.addLayout(cards, 1)

        if default_file.exists():
            self.load(default_file)

    def theme(self) -> Theme:
        """Текущие данные; ValueError, если в них ошибка."""
        theme = Theme(self.title, [c.subtopic() for c in self.cards], "repeat")
        errors = theme.check()
        if errors:
            raise ValueError("\n".join(errors))
        return theme

    def set_theme(self, theme: Theme):
        self.title = theme.title
        for card, sub in zip(self.cards, theme.subtopics):
            card.set_subtopic(sub)
        self.validate()

    def validate(self):
        try:
            self.theme()
            self.status.setText("●  Данные в порядке")
            self.status.setToolTip("")
            self.status.setStyleSheet("color: #047857; background: #D1FAE5; border-radius: 12px;"
                                      " padding: 6px 12px; font-weight: 600;")
        except ValueError as e:
            self.status.setText("●  Есть ошибки — наведите курсор")
            self.status.setToolTip(str(e))
            self.status.setStyleSheet("color: #B91C1C; background: #FEE2E2; border-radius: 12px;"
                                      " padding: 6px 12px; font-weight: 600;")

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
