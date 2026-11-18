"""Вкладка «Граф диалога»: редактирование шагов, маршрутов и подтем."""
from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from ..model import DISTRIBUTIONS, ERROR_MODES, Route, Step, Subtopic, Theme
from .common import ACCENT, ACCENT2, PlotWidget, spin

STEP_COLS = ["Шаг", "Закон распределения", "Параметр 1", "Параметр 2", "M[t], с"]
ROUTE_COLS = ["Маршрут", "Вероятность", "Последовательность шагов", "M[t] при P=0, с"]


def _num(text: str) -> float:
    return float(text.strip().replace(",", ".") or 0)


class SubtopicEditor(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False

        self.name = QLineEdit()
        self.choice = spin(0, 1, 0.5, 0.05)
        self.p_error = spin(0, 0.99, 0.05, 0.05)
        head = QFormLayout()
        head.addRow("Название подтемы:", self.name)
        row = QHBoxLayout()
        row.addWidget(QLabel("Вероятность выбора подтемы:"))
        row.addWidget(self.choice)
        row.addSpacing(20)
        row.addWidget(QLabel("Вероятность ошибки P (одинакова для всех шагов):"))
        row.addWidget(self.p_error)
        row.addStretch()
        head.addRow(row)

        # --- таблица шагов --------------------------------------------------
        self.steps = QTableWidget(0, len(STEP_COLS))
        self.steps.setHorizontalHeaderLabels(STEP_COLS)
        self.steps.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(STEP_COLS)):
            self.steps.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        steps_box = QGroupBox("Шаги диалога (до 10)")
        sl = QVBoxLayout(steps_box)
        sl.addWidget(self.steps)
        sb = QHBoxLayout()
        add_step = QPushButton("+ шаг")
        del_step = QPushButton("− последний шаг")
        add_step.clicked.connect(lambda: self._add_step(Step(f"Шаг {self.steps.rowCount() + 1}")))
        del_step.clicked.connect(lambda: self._remove_last(self.steps))
        sb.addWidget(add_step)
        sb.addWidget(del_step)
        sb.addStretch()
        sl.addLayout(sb)

        # --- таблица маршрутов ----------------------------------------------
        self.routes = QTableWidget(0, len(ROUTE_COLS))
        self.routes.setHorizontalHeaderLabels(ROUTE_COLS)
        self.routes.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.routes.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        routes_box = QGroupBox("Маршруты (до 10); шаги через пробел или дефис, например 1-2-5-10")
        rl = QVBoxLayout(routes_box)
        rl.addWidget(self.routes)
        rb = QHBoxLayout()
        add_route = QPushButton("+ маршрут")
        del_route = QPushButton("− последний маршрут")
        norm = QPushButton("Нормировать вероятности")
        add_route.clicked.connect(
            lambda: self._add_route(Route(f"М{self.routes.rowCount() + 1}", 0.0, [1])))
        del_route.clicked.connect(lambda: self._remove_last(self.routes))
        norm.clicked.connect(self._normalize)
        for b in (add_route, del_route, norm):
            rb.addWidget(b)
        rb.addStretch()
        rl.addLayout(rb)

        self.graph = PlotWidget(toolbar=False)
        self.graph.setMinimumWidth(320)

        tables = QWidget()
        tl = QVBoxLayout(tables)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addLayout(head)
        tl.addWidget(steps_box, 3)
        tl.addWidget(routes_box, 2)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(tables)
        split.addWidget(self.graph)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay = QVBoxLayout(self)
        lay.addWidget(split)

        for w in (self.choice, self.p_error):
            w.valueChanged.connect(self._on_change)
        self.name.textChanged.connect(self._on_change)
        self.steps.itemChanged.connect(self._on_change)
        self.routes.itemChanged.connect(self._on_change)

    # --- заполнение -------------------------------------------------------
    def _add_step(self, st: Step):
        if self.steps.rowCount() >= 10:
            return
        prev, self._loading = self._loading, True
        r = self.steps.rowCount()
        self.steps.insertRow(r)
        self.steps.setVerticalHeaderItem(r, QTableWidgetItem(str(r + 1)))
        self.steps.setItem(r, 0, QTableWidgetItem(st.name))
        combo = QComboBox()
        for key, (title, _, _) in DISTRIBUTIONS.items():
            combo.addItem(title, key)
        combo.setCurrentIndex(list(DISTRIBUTIONS).index(st.dist))
        combo.currentIndexChanged.connect(self._on_change)
        self.steps.setCellWidget(r, 1, combo)
        self.steps.setItem(r, 2, QTableWidgetItem(f"{st.a:g}"))
        self.steps.setItem(r, 3, QTableWidgetItem(f"{st.b:g}"))
        mean = QTableWidgetItem()
        mean.setFlags(Qt.ItemIsEnabled)
        self.steps.setItem(r, 4, mean)
        self._loading = prev
        self._on_change()

    def _add_route(self, rt: Route):
        if self.routes.rowCount() >= 10:
            return
        prev, self._loading = self._loading, True
        r = self.routes.rowCount()
        self.routes.insertRow(r)
        self.routes.setItem(r, 0, QTableWidgetItem(rt.name))
        self.routes.setItem(r, 1, QTableWidgetItem(f"{rt.prob:g}"))
        self.routes.setItem(r, 2, QTableWidgetItem("-".join(map(str, rt.steps))))
        mean = QTableWidgetItem()
        mean.setFlags(Qt.ItemIsEnabled)
        self.routes.setItem(r, 3, mean)
        self._loading = prev
        self._on_change()

    def _remove_last(self, table: QTableWidget):
        if table.rowCount():
            table.removeRow(table.rowCount() - 1)
            self._on_change()

    def _normalize(self):
        sub = self.subtopic(strict=False)
        total = sum(r.prob for r in sub.routes)
        if total <= 0:
            return
        for i, r in enumerate(sub.routes):
            self.routes.item(i, 1).setText(f"{r.prob / total:.4g}")

    def set_subtopic(self, sub: Subtopic):
        self._loading = True
        self.name.setText(sub.name)
        self.choice.setValue(sub.choice_prob)
        self.p_error.setValue(sub.p_error)
        self.steps.setRowCount(0)
        self.routes.setRowCount(0)
        for st in sub.steps:
            self._add_step(st)
        for rt in sub.routes:
            self._add_route(rt)
        self._loading = False
        self._on_change()

    # --- чтение -----------------------------------------------------------
    def subtopic(self, strict: bool = True) -> Subtopic:
        steps, routes = [], []
        for r in range(self.steps.rowCount()):
            try:
                a, b = _num(self.steps.item(r, 2).text()), _num(self.steps.item(r, 3).text())
            except ValueError:
                if strict:
                    raise ValueError(f"«{self.name.text()}», шаг {r + 1}: параметр — не число")
                a, b = 0.0, 0.0
            steps.append(Step(self.steps.item(r, 0).text(),
                              self.steps.cellWidget(r, 1).currentData(), a, b))
        for r in range(self.routes.rowCount()):
            try:
                prob = _num(self.routes.item(r, 1).text())
                seq = [int(x) for x in self.routes.item(r, 2).text().replace("-", " ")
                       .replace(",", " ").replace("→", " ").split()]
            except ValueError:
                if strict:
                    raise ValueError(f"«{self.name.text()}», маршрут {r + 1}: ошибка в записи")
                prob, seq = 0.0, []
            routes.append(Route(self.routes.item(r, 0).text(), prob, seq))
        return Subtopic(self.name.text(), self.choice.value(), self.p_error.value(), steps, routes)

    # --- обновление вычисляемых столбцов и графа --------------------------
    def _on_change(self, *_):
        if self._loading:
            return
        sub = self.subtopic(strict=False)
        self.steps.blockSignals(True)
        self.routes.blockSignals(True)
        for r, st in enumerate(sub.steps):
            hint = DISTRIBUTIONS.get(st.dist, ("", "", ""))
            self.steps.item(r, 2).setToolTip(hint[1])
            self.steps.item(r, 3).setToolTip(hint[2] or "не используется")
            try:
                self.steps.item(r, 4).setText(f"{st.mean():.2f}")
            except ValueError:
                self.steps.item(r, 4).setText("—")
        for r, rt in enumerate(sub.routes):
            ok = rt.steps and all(1 <= s <= len(sub.steps) for s in rt.steps)
            text = f"{sum(sub.steps[s - 1].mean() for s in rt.steps):.2f}" if ok else "ошибка"
            self.routes.item(r, 3).setText(text)
        self.steps.blockSignals(False)
        self.routes.blockSignals(False)
        self._draw_graph(sub)
        self.changed.emit()

    def _draw_graph(self, sub: Subtopic):
        fig = self.graph.figure
        fig.clear()
        ax = fig.add_subplot()
        ax.set_axis_off()
        n = len(sub.steps)
        if n == 0:
            self.graph.draw()
            return
        # вершины упорядочены слева направо по среднему положению шага в
        # маршрутах и разнесены «зигзагом», «Начало» и «Конец» — по краям
        place = defaultdict(list)
        for rt in sub.routes:
            for j, s in enumerate(rt.steps):
                place[s].append((j + 1) / (len(rt.steps) + 1))
        order = sorted(range(1, n + 1),
                       key=lambda s: (sum(place[s]) / len(place[s])) if place[s] else 2 + s)
        pos = {}
        for i, s in enumerate(order):
            x = -1.35 + 2.7 * (i + 0.5) / n
            pos[s] = (x, 0.62 * (1 if i % 2 == 0 else -1) * (0.75 + 0.25 * (i % 4 < 2)))
        pos["Н"] = (-1.75, 0.0)
        pos["К"] = (1.75, 0.0)
        weight = defaultdict(float)
        for rt in sub.routes:
            if not rt.steps or not all(1 <= s <= n for s in rt.steps):
                continue
            path = ["Н", *rt.steps, "К"]
            for u, v in zip(path, path[1:]):
                weight[(u, v)] += rt.prob
        wmax = max(weight.values(), default=1)
        for (u, v), w in weight.items():
            ax.annotate("", xy=pos[v], xytext=pos[u],
                        arrowprops=dict(arrowstyle="-|>", color=ACCENT, alpha=0.35 + 0.6 * w / wmax,
                                        lw=0.6 + 2.6 * w / wmax, shrinkA=11, shrinkB=11,
                                        connectionstyle="arc3,rad=0.12"))
        for key, (x, y) in pos.items():
            special = key in ("Н", "К")
            ax.scatter([x], [y], s=520, color=ACCENT2 if special else "white",
                       edgecolor=ACCENT2 if special else ACCENT, linewidth=1.6, zorder=3)
            ax.text(x, y, str(key), ha="center", va="center", zorder=4, fontsize=9,
                    fontweight="bold", color="white" if special else "black")
        ax.set_xlim(-2.0, 2.0)
        ax.set_ylim(-1.1, 1.1)
        ax.set_aspect("equal")
        ax.set_title(f"Граф подтемы: толщина дуги ~ вероятности перехода\n"
                     f"в каждой вершине — петля ошибки с P = {sub.p_error:g}", fontsize=9)
        self.graph.draw()


class EditorTab(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = QLineEdit()
        self.mode = QComboBox()
        for key, title in ERROR_MODES.items():
            self.mode.addItem(title, key)
        top = QFormLayout()
        top.addRow("Тема диалога:", self.title)
        top.addRow("Обработка ошибок:", self.mode)
        self.editors = [SubtopicEditor(), SubtopicEditor()]
        self.tabs = QTabWidget()
        for i, ed in enumerate(self.editors, 1):
            self.tabs.addTab(ed, f"Подтема {i}")
            ed.changed.connect(self.changed)
            ed.name.textChanged.connect(self._retitle)
        self.status = QLabel()
        self.status.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.tabs)
        lay.addWidget(self.status)
        self.changed.connect(self._validate)

    def _retitle(self):
        for i, ed in enumerate(self.editors):
            self.tabs.setTabText(i, f"Подтема {i + 1}: {ed.name.text()[:30]}")

    def set_theme(self, theme: Theme):
        self.title.setText(theme.title)
        self.mode.setCurrentIndex(max(0, self.mode.findData(theme.error_mode)))
        for ed, sub in zip(self.editors, theme.subtopics):
            ed.set_subtopic(sub)
        self._validate()

    def theme(self) -> Theme:
        return Theme(self.title.text(), [ed.subtopic() for ed in self.editors],
                     self.mode.currentData())

    def _validate(self):
        try:
            errors = self.theme().check()
        except ValueError as e:
            errors = [str(e)]
        if errors:
            self.status.setText("⚠ " + "; ".join(errors))
            self.status.setStyleSheet("color: #b3261e;")
        else:
            self.status.setText("✓ Исходные данные корректны")
            self.status.setStyleSheet("color: #2e7d32;")
