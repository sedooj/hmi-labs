"""Вкладки ЛР2: расчёт показателя эффективности и исследование влияния параметров."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QMessageBox, QProgressBar, QPushButton, QSplitter, QVBoxLayout,
                               QWidget)

from ..efficiency_sim import EfficiencyModel, Lr2Params, Lr2Result
from .common import (ACCENT, ACCENT2, ACCENT3, PlotWidget, Task, fill_table, ispin,
                     readonly_table, spin)

INDICATORS = [
    ("q", "Q — средние удельные потери, у.е./с"),
    ("q1", "  в т.ч. от задержек регулирования R1·Στ/T"),
    ("q2", "  в т.ч. от простоя R2·Σθ/T"),
    ("availability", "Коэффициент готовности"),
    ("mean_delay", "Средняя задержка выдачи воздействия, с"),
    ("utilization", "Загрузка диспетчера заявками"),
    ("arrived", "Поступило заявок"),
    ("served", "Обслужено заявок"),
    ("annulled", "Аннулировано заявок"),
    ("failures", "Отказов"),
    ("downtime", "Суммарный простой, с"),
]


class ParamsForm(QGroupBox):
    """Исходные данные ЛР2. Используется и для расчёта, и как база для исследования."""

    def __init__(self, parent=None):
        super().__init__("Параметры системы и диспетчера", parent)
        d = Lr2Params()
        self.lam = spin(0.1, 1000, d.lam_per_hour, 1, 2, " 1/ч")
        self.mtbf = spin(0.01, 10_000, d.mtbf_hours, 0.5, 2, " ч")
        self.law = QComboBox()
        self.law.addItem("экспоненциальный", "exp")
        self.law.addItem("Вейбулла", "weibull")
        self.shape = spin(0.2, 10, d.weibull_shape, 0.1, 2)
        self.shape.setEnabled(False)
        self.law.currentIndexChanged.connect(
            lambda: self.shape.setEnabled(self.law.currentData() == "weibull"))
        self.r1 = spin(0, 1e6, d.r1, 0.5, 3, " у.е./с")
        self.r2 = spin(0, 1e6, d.r2, 1, 3, " у.е./с")
        self.p1 = spin(0, 0.95, d.p1, 0.05)
        self.p2 = spin(0, 0.95, d.p2, 0.05)
        self.scale = spin(0.1, 5, d.time_scale, 0.1, 2)
        self.scale.setToolTip("Множитель времени всех шагов: 1 — норматив, 2 — диспетчер вдвое медленнее")
        self.horizon = spin(1, 100_000, d.horizon_hours, 24, 1, " ч")
        self.runs = ispin(1, 1000, d.runs)
        self.seed = ispin(0, 999_999, 0)
        self.seed.setSpecialValueText("случайный")
        f = QFormLayout(self)
        f.addRow(QLabel("<b>Объект управления</b>"))
        f.addRow("Интенсивность заявок λ:", self.lam)
        f.addRow("Средняя наработка на отказ:", self.mtbf)
        f.addRow("Закон наработки на отказ:", self.law)
        f.addRow("Параметр формы (Вейбулл):", self.shape)
        f.addRow(QLabel("<b>Потери</b>"))
        f.addRow("R1 — за задержку заявки:", self.r1)
        f.addRow("R2 — за простой системы:", self.r2)
        f.addRow(QLabel("<b>Диспетчер (человек-оператор)</b>"))
        f.addRow("P ошибки, подтема 1:", self.p1)
        f.addRow("P ошибки, подтема 2:", self.p2)
        f.addRow("Темп работы (×время шагов):", self.scale)
        f.addRow(QLabel("<b>Моделирование</b>"))
        f.addRow("Интервал моделирования T:", self.horizon)
        f.addRow("Число прогонов:", self.runs)
        f.addRow("Зерно генератора:", self.seed)

    def params(self) -> Lr2Params:
        return Lr2Params(
            lam_per_hour=self.lam.value(), mtbf_hours=self.mtbf.value(),
            failure_law=self.law.currentData(), weibull_shape=self.shape.value(),
            r1=self.r1.value(), r2=self.r2.value(), horizon_hours=self.horizon.value(),
            runs=self.runs.value(), p1=self.p1.value(), p2=self.p2.value(),
            time_scale=self.scale.value(), seed=self.seed.value() or None)


def checked_theme(widget, get_theme):
    try:
        theme = get_theme()
        errors = theme.check()
        if errors:
            raise ValueError("\n".join(errors))
        return theme
    except ValueError as e:
        QMessageBox.warning(widget, "Исходные данные", str(e))
        return None


class Lr2Tab(QWidget):
    def __init__(self, get_theme, parent=None):
        super().__init__(parent)
        self.get_theme = get_theme
        self.form = ParamsForm()
        self.run_btn = QPushButton("▶ Рассчитать показатель")
        self.run_btn.clicked.connect(self.run)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.formula = QLabel(
            "<b>Показатель эффективности</b><br>"
            "Q = (R1·Σ τ<sub>i</sub> + R2·Σ θ<sub>j</sub>) / T<br>"
            "τ<sub>i</sub> — задержка выдачи регулирующего воздействия по i-й заявке,<br>"
            "θ<sub>j</sub> — длительность j-го простоя (восстановления), T — интервал моделирования.<br>"
            "Чем меньше Q, тем эффективнее система.")
        self.formula.setWordWrap(True)
        self.result = readonly_table(["Показатель", "Среднее", "± 95% ДИ"])

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(self.form)
        ll.addWidget(self.run_btn)
        ll.addWidget(self.progress)
        ll.addStretch()

        self.plot = PlotWidget()
        mid = QSplitter(Qt.Vertical)
        mid.addWidget(self.plot)
        bottom = QWidget()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.result, 3)
        bl.addWidget(self.formula, 2)
        mid.addWidget(bottom)
        mid.setStretchFactor(0, 3)
        mid.setStretchFactor(1, 2)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(mid)
        split.setStretchFactor(1, 1)
        split.setSizes([340, 900])
        QHBoxLayout(self).addWidget(split)

    def run(self):
        theme = checked_theme(self, self.get_theme)
        if theme is None:
            return
        params = self.form.params()

        def job(report):
            return EfficiencyModel(theme, params).run(
                progress=lambda i: report(int(100 * i / params.runs)))

        self.run_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.task = Task(job, self)
        self.task.progress.connect(self.progress.setValue)
        self.task.done.connect(self._on_done)
        self.task.failed.connect(self._on_fail)
        self.task.start()

    def _on_fail(self, text):
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Ошибка моделирования", text)

    def _on_done(self, res: Lr2Result):
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        rows = []
        for attr, title in INDICATORS:
            m, ci = res.mean_ci(attr)
            rows.append([title, float(m), float(ci)])
        fill_table(self.result, rows)
        draw_lr2(self.plot.figure, res)
        self.plot.draw()


def draw_lr2(fig, res: Lr2Result, window_hours: float = 8.0):
    """Структура потерь и динамика очереди в первом прогоне (используется и в отчёте)."""
    fig.clear()
    ax1, ax2 = fig.subplots(1, 2, width_ratios=[1, 2.4])
    q1, c1 = res.mean_ci("q1")
    q2, c2 = res.mean_ci("q2")
    ax1.bar(["задержки\n(R1)", "простой\n(R2)"], [q1, q2], yerr=[c1, c2], capsize=5,
            color=[ACCENT, ACCENT2])
    ax1.set_title(f"Потери: Q = {q1 + q2:.4f} у.е./с")
    ax1.set_ylabel("у.е./с")

    run = res.runs[0]
    H = min(window_hours * 3600, run.horizon)
    t, q, down, t_fail = [0.0], [0], [], None
    for time, qlen, state in run.trace:
        if time > H:
            break
        t.append(time)
        q.append(qlen)
        if state == 0:
            t_fail = time
        elif t_fail is not None:
            down.append((t_fail, time))
            t_fail = None
    t.append(H)
    q.append(q[-1])
    th = np.array(t) / 3600
    ax2.fill_between(th, q, step="post", color=ACCENT, alpha=0.35, lw=0)
    ax2.step(th, q, where="post", color=ACCENT, lw=0.8)
    top = max(q) + 1
    for a, b in down:
        ax2.axvspan(a / 3600, b / 3600, color="#d64545", alpha=0.35, lw=0)
        ax2.plot([a / 3600], [top], "v", color="#d64545", ms=7)
    ax2.set_ylim(0, top + 0.6)
    ax2.set_xlim(0, H / 3600)
    ax2.set_title(f"Очередь заявок: первые {H / 3600:g} ч (▼ — отказ)")
    ax2.set_xlabel("время, ч")
    ax2.set_ylabel("заявок в очереди")


STUDY_PARAMS = [
    ("p", "P ошибки диспетчера (в обеих подтемах)", 0.0, 0.9, 10),
    ("p1", "P ошибки в подтеме 1 (регулирование)", 0.0, 0.9, 10),
    ("p2", "P ошибки в подтеме 2 (восстановление)", 0.0, 0.9, 10),
    ("time_scale", "Темп работы диспетчера (×время шагов)", 0.5, 2.5, 9),
    ("lam_per_hour", "Интенсивность заявок λ, 1/ч", 5, 60, 12),
    ("mtbf_hours", "Средняя наработка на отказ, ч", 1, 24, 12),
]


def apply_param(base: Lr2Params, key: str, value: float) -> Lr2Params:
    if key == "p":
        return replace(base, p1=value, p2=value)
    return replace(base, **{key: value})


def run_study(theme, base: Lr2Params, key: str, values, report=None):
    """Для каждого значения параметра — серия прогонов модели ЛР2."""
    out = []
    for i, v in enumerate(values):
        res = EfficiencyModel(theme, apply_param(base, key, float(v))).run()
        out.append((float(v), res))
        if report:
            report(int(100 * (i + 1) / len(values)))
    return out


def draw_study(fig, title: str, data):
    fig.clear()
    ax1, ax2 = fig.subplots(2, 1, sharex=True)
    x = np.array([v for v, _ in data])
    for attr, label, color in (("q", "Q (всего)", "black"), ("q1", "от задержек", ACCENT),
                               ("q2", "от простоя", ACCENT2)):
        m = np.array([r.mean_ci(attr)[0] for _, r in data])
        c = np.array([r.mean_ci(attr)[1] for _, r in data])
        ax1.plot(x, m, "o-", color=color, ms=3, label=label, lw=1.6 if attr == "q" else 1)
        ax1.fill_between(x, m - c, m + c, color=color, alpha=0.12, lw=0)
    ax1.set_ylabel("потери, у.е./с")
    qs = [r.mean_ci("q")[0] for _, r in data]
    if min(qs) > 0 and max(qs) / min(qs) > 50:
        ax1.set_yscale("log")
        ax2.set_yscale("log")
    ax1.set_title(f"Влияние параметра: {title}")
    ax1.legend(fontsize=8)
    d = np.array([r.mean_ci("mean_delay")[0] for _, r in data])
    a = np.array([r.mean_ci("availability")[0] for _, r in data])
    ax2.plot(x, d, "s-", color=ACCENT3, ms=3)
    ax2.set_ylabel("средняя задержка, с", color=ACCENT3)
    ax3 = ax2.twinx()
    ax3.plot(x, a, "^--", color="#7b4fb0", ms=3)
    ax3.set_ylabel("коэфф. готовности", color="#7b4fb0")
    ax3.grid(False)
    ax2.set_xlabel(title)


class StudyTab(QWidget):
    def __init__(self, get_theme, form: ParamsForm, parent=None):
        super().__init__(parent)
        self.get_theme = get_theme
        self.form = form
        self.param = QComboBox()
        for key, title, lo, hi, n in STUDY_PARAMS:
            self.param.addItem(title, (key, lo, hi, n))
        self.lo = spin(0, 1000, 0, 0.1, 3)
        self.hi = spin(0, 1000, 0.9, 0.1, 3)
        self.points = ispin(2, 50, 10)
        self.param.currentIndexChanged.connect(self._defaults)
        self.run_btn = QPushButton("▶ Исследовать")
        self.run_btn.clicked.connect(self.run)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        box = QGroupBox("Исследование влияния параметров на эффективность")
        f = QFormLayout(box)
        f.addRow("Варьируемый параметр:", self.param)
        f.addRow("От:", self.lo)
        f.addRow("До:", self.hi)
        f.addRow("Число точек:", self.points)
        f.addRow(QLabel("Остальные параметры берутся с вкладки «ЛР2: эффективность»."))
        f.addRow(self.run_btn)
        f.addRow(self.progress)
        self.table = readonly_table(["Значение", "Q", "± ДИ", "Q₁ задержки", "Q₂ простой",
                                     "Задержка, с", "Kг"])
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(box)
        ll.addWidget(self.table, 1)
        self.plot = PlotWidget()
        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(self.plot)
        split.setStretchFactor(1, 1)
        split.setSizes([420, 820])
        QHBoxLayout(self).addWidget(split)
        self._defaults()

    def _defaults(self):
        _, lo, hi, n = self.param.currentData()
        self.lo.setValue(lo)
        self.hi.setValue(hi)
        self.points.setValue(n)

    def run(self):
        theme = checked_theme(self, self.get_theme)
        if theme is None:
            return
        key = self.param.currentData()[0]
        if key.startswith("p") and self.hi.value() >= 1:
            QMessageBox.warning(self, "Параметры", "Вероятность ошибки должна быть меньше 1")
            return
        values = np.linspace(self.lo.value(), self.hi.value(), self.points.value())
        base = self.form.params()
        title = self.param.currentText()

        self.run_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.task = Task(lambda report: run_study(theme, base, key, values, report), self)
        self.task.progress.connect(self.progress.setValue)
        self.task.done.connect(lambda data: self._on_done(title, data))
        self.task.failed.connect(self._on_fail)
        self.task.start()

    def _on_fail(self, text):
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Ошибка моделирования", text)

    def _on_done(self, title, data):
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        rows = []
        for v, r in data:
            q, c = r.mean_ci("q")
            rows.append([f"{v:g}", q, c, r.mean_ci("q1")[0], r.mean_ci("q2")[0],
                         r.mean_ci("mean_delay")[0], r.mean_ci("availability")[0]])
        fill_table(self.table, rows)
        draw_study(self.plot.figure, title, data)
        self.plot.draw()
