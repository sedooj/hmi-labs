"""Раздел 3. ЛР2: эффективность системы «человек-оператор — АРМ — объект управления»."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QMessageBox, QVBoxLayout,
                               QWidget)

from ..dialog_sim import DEFAULT_SEED
from ..efficiency_sim import EfficiencyModel, Lr2Params
from ..plots import draw_lr2, draw_study, run_study
from .common import (Card, Kpi, Plot, Task, button, field, ispin, label, page_header,
                     progress_bar, seed_edit, spin)

STUDIES = [  # ключ параметра, подпись, значения
    ("p", "P ошибки оператора", np.linspace(0, 0.6, 7)),
    ("time_scale", "Темп работы оператора (×время шагов)", np.linspace(0.5, 2.5, 9)),
]


class Lr2Tab(QWidget):
    def __init__(self, get_theme, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.get_theme = get_theme
        d = Lr2Params()
        self.lam = spin(0.1, 1000, d.lam_per_hour, 1, 1, " / ч")
        self.mtbf = spin(0.1, 10_000, d.mtbf_hours, 0.5, 1, " ч")
        self.r1 = spin(0, 1e6, d.r1, 0.5, 2)
        self.r2 = spin(0, 1e6, d.r2, 1, 2)
        self.p1 = spin(0, 0.95, d.p1, 0.05, 2)
        self.p2 = spin(0, 0.95, d.p2, 0.05, 2)
        self.horizon = spin(1, 100_000, d.horizon_hours, 24, 0, " ч")
        self.runs = ispin(1, 500, d.runs)
        self.seed = seed_edit(DEFAULT_SEED)

        # --- параметры -------------------------------------------------------
        params = Card("Параметры системы", "Значения по умолчанию уже подобраны")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        for i, (cap, w) in enumerate((
                ("Интенсивность заявок", self.lam), ("Отказ раз в", self.mtbf),
                ("R1 — за 1 с задержки", self.r1), ("R2 — за 1 с простоя", self.r2),
                ("P ошибки: подтема 1", self.p1), ("P ошибки: подтема 2", self.p2),
                ("Период", self.horizon), ("Повторов", self.runs))):
            grid.addWidget(field(cap, w), i // 2, i % 2)
        grid.addWidget(field("Зерно генератора", self.seed), 4, 0, 1, 2)
        params.add(grid)
        params.add(label("С зерном 2026 получаются те же числа, что в отчёте. "
                         "Пусто — каждый расчёт случайный.", "muted", True))
        self.run_btn = button("Рассчитать")
        self.run_btn.clicked.connect(self.run)
        params.body.addSpacing(4)
        params.add(self.run_btn)

        study = Card("Исследование", "Как потери Q меняются от параметра оператора")
        self.study_param = QComboBox()
        for _, title, _ in STUDIES:
            self.study_param.addItem(title)
        self.study_btn = button("Построить зависимость", "secondary")
        self.study_btn.clicked.connect(self.study)
        study.add(self.study_param)
        study.add(self.study_btn)

        formula = Card("Показатель эффективности")
        formula.add(label("<span style='font-size:15px'><b>Q = (R1·Σ задержек + R2·Σ простоя) / T</b>"
                          "</span><br><span style='color:#6B7280'>средние потери в секунду; "
                          "чем меньше, тем лучше</span>", wrap=True))

        self.progress = progress_bar()
        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(formula)
        left.addWidget(params)
        left.addWidget(study)
        left.addWidget(self.progress)
        left.addStretch()
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(380)

        # --- результаты ------------------------------------------------------
        self.kpi = {
            "q": Kpi("Потери Q", accent=True),
            "q1": Kpi("Задержки"),
            "q2": Kpi("Простой"),
            "availability": Kpi("Готовность"),
            "mean_delay": Kpi("Задержка, с"),
        }
        self.kpi_box = QWidget()
        kpis = QHBoxLayout(self.kpi_box)
        kpis.setContentsMargins(0, 0, 0, 0)
        kpis.setSpacing(14)
        for k in self.kpi.values():
            kpis.addWidget(k)

        self.plot = Plot()
        self.plot_card = Card("Результат", "")
        self.empty = label("Нажмите «Рассчитать» или «Построить зависимость»", "muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.plot_card.add(self.empty, 1)
        self.plot_card.add(self.plot, 1)
        self.plot.setVisible(False)

        right = QVBoxLayout()
        right.setSpacing(16)
        right.addWidget(self.kpi_box)
        right.addWidget(self.plot_card, 1)

        body = QHBoxLayout()
        body.setSpacing(18)
        body.addWidget(left_w)
        body.addLayout(right, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)
        lay.addWidget(page_header(
            "ЛР2 · Эффективность системы",
            "Оператор обрабатывает заявки объекта управления (подтема 1). При отказе очередь "
            "аннулируется, оператор восстанавливает работу системы (подтема 2)."))
        lay.addLayout(body, 1)

    def params(self) -> Lr2Params:
        return Lr2Params(lam_per_hour=self.lam.value(), mtbf_hours=self.mtbf.value(),
                         r1=self.r1.value(), r2=self.r2.value(), p1=self.p1.value(),
                         p2=self.p2.value(), horizon_hours=self.horizon.value(),
                         runs=self.runs.value(), seed=self.seed.value() or None)

    def _start(self, job, on_done, btn):
        try:
            theme = self.get_theme()
        except ValueError as e:
            QMessageBox.warning(self, "Проверьте исходные данные", str(e))
            return
        self._busy_btn, self._busy_text = btn, btn.text()
        btn.setText("Считаю…")
        self.run_btn.setEnabled(False)
        self.study_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.task = Task(lambda report: job(theme, report), self)
        self.task.progress.connect(self.progress.setValue)
        self.task.done.connect(on_done)
        self.task.failed.connect(self._failed)
        self.task.start()

    def _finish(self):
        self._busy_btn.setText(self._busy_text)
        self.run_btn.setEnabled(True)
        self.study_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.empty.setVisible(False)
        self.plot.setVisible(True)

    def _failed(self, text):
        self._finish()
        QMessageBox.critical(self, "Ошибка", text)

    # --- один расчёт -------------------------------------------------------
    def run(self):
        params = self.params()
        self._start(lambda theme, report: EfficiencyModel(theme, params).run(
            progress=lambda i: report(int(100 * i / params.runs))), self._done, self.run_btn)

    def _done(self, res):
        self._finish()
        fmt = {"q": "{:.3f}", "q1": "{:.3f}", "q2": "{:.3f}", "availability": "{:.4f}",
               "mean_delay": "{:.1f}"}
        for key, k in self.kpi.items():
            k.set(fmt[key].format(res.mean_ci(key)[0]))
        self.kpi_box.setVisible(True)
        self.plot_card.title_label.setText("Потери: структура и накопление во времени")
        draw_lr2(self.plot.figure, res)
        self.plot.draw()

    # --- исследование ------------------------------------------------------
    def study(self):
        key, title, values = STUDIES[self.study_param.currentIndex()]
        base = replace(self.params(), runs=min(self.runs.value(), 10))
        self._start(lambda theme, report: run_study(theme, base, key, values, report),
                    lambda data: self._study_done(title, data), self.study_btn)

    def _study_done(self, title, data):
        self._finish()
        self.kpi_box.setVisible(False)
        self.plot_card.title_label.setText(f"Зависимость потерь Q от параметра «{title}»")
        draw_study(self.plot.figure, title, data, simple=True)
        self.plot.draw()
