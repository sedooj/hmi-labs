"""Окно 3. ЛР2: эффективность системы «диспетчер — АРМ — электросеть»."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
                               QMessageBox, QVBoxLayout, QWidget)

from ..efficiency_sim import EfficiencyModel, Lr2Params
from ..plots import draw_lr2, draw_study, run_study
from .common import (Plot, Task, ValueCard, big_button, hint, ispin, progress_bar, section, spin)

STUDIES = [  # ключ параметра, подпись, значения
    ("p", "P ошибки диспетчера", np.linspace(0, 0.6, 7)),
    ("time_scale", "Темп работы диспетчера (×время шагов)", np.linspace(0.5, 2.5, 9)),
]


class Lr2Tab(QWidget):
    def __init__(self, get_theme, parent=None):
        super().__init__(parent)
        self.get_theme = get_theme
        d = Lr2Params()
        self.lam = spin(0.1, 1000, d.lam_per_hour, 1, 1, " в час")
        self.mtbf = spin(0.1, 10_000, d.mtbf_hours, 0.5, 1, " ч")
        self.r1 = spin(0, 1e6, d.r1, 0.5, 2)
        self.r2 = spin(0, 1e6, d.r2, 1, 2)
        self.p1 = spin(0, 0.95, d.p1, 0.05, 2)
        self.p2 = spin(0, 0.95, d.p2, 0.05, 2)
        self.horizon = spin(1, 100_000, d.horizon_hours, 24, 0, " ч")
        self.runs = ispin(1, 500, d.runs)

        form = QFormLayout()
        form.addRow("Заявок от сети:", self.lam)
        form.addRow("Отказ в среднем раз в:", self.mtbf)
        form.addRow("R1 — потери за 1 с задержки:", self.r1)
        form.addRow("R2 — потери за 1 с простоя:", self.r2)
        form.addRow("P ошибки при регулировании:", self.p1)
        form.addRow("P ошибки при восстановлении:", self.p2)
        form.addRow("Моделировать период:", self.horizon)
        form.addRow("Повторов расчёта:", self.runs)

        self.run_btn = big_button("Рассчитать")
        self.run_btn.clicked.connect(self.run)
        self.study_param = QComboBox()
        for _, title, _ in STUDIES:
            self.study_param.addItem(title)
        self.study_btn = big_button("Построить зависимость")
        self.study_btn.clicked.connect(self.study)
        self.progress = progress_bar()

        left = QVBoxLayout()
        left.addWidget(hint("<b>ЛР2. Насколько эффективно работает система.</b><br><br>"
                            "Диспетчер обрабатывает заявки от сети (подтема 1). Иногда система "
                            "отказывает: очередь заявок пропадает, диспетчер восстанавливает работу "
                            "(подтема 2).<br><br>"
                            "Показатель — средние потери в секунду:<br>"
                            "<b>Q = (R1·Σ задержек + R2·Σ простоя) / T</b><br>"
                            "Чем меньше Q, тем лучше."))
        left.addLayout(form)
        left.addWidget(self.run_btn)
        left.addSpacing(10)
        left.addWidget(section("Как Q зависит от параметра"))
        left.addWidget(self.study_param)
        left.addWidget(self.study_btn)
        left.addWidget(self.progress)
        left.addStretch()
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(360)

        self.cards = {
            "q": ValueCard("Q — потери, у.е./с"),
            "q1": ValueCard("из них от задержек"),
            "q2": ValueCard("из них от простоя"),
            "availability": ValueCard("Коэффициент готовности"),
            "mean_delay": ValueCard("Средняя задержка заявки, с"),
            "annulled": ValueCard("Пропало заявок из-за отказов"),
        }
        self.cards_box = QWidget()
        grid = QGridLayout(self.cards_box)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, card in enumerate(self.cards.values()):
            grid.addWidget(card, 0, i)
        self.plot_title = section("Результат")
        self.plot = Plot()
        self.placeholder = QLabel("Нажмите «Рассчитать» или «Построить зависимость»")
        self.placeholder.setStyleSheet("color: #888; font-size: 16px;")
        right = QVBoxLayout()
        right.addWidget(self.cards_box)
        right.addWidget(self.plot_title)
        right.addWidget(self.placeholder)
        right.addWidget(self.plot, 1)

        lay = QHBoxLayout(self)
        lay.addWidget(left_w)
        lay.addLayout(right, 1)

    def params(self) -> Lr2Params:
        return Lr2Params(lam_per_hour=self.lam.value(), mtbf_hours=self.mtbf.value(),
                         r1=self.r1.value(), r2=self.r2.value(), p1=self.p1.value(),
                         p2=self.p2.value(), horizon_hours=self.horizon.value(),
                         runs=self.runs.value())

    def _start(self, job, on_done):
        try:
            theme = self.get_theme()
        except ValueError as e:
            QMessageBox.warning(self, "Проверьте исходные данные", str(e))
            return
        self.run_btn.setEnabled(False)
        self.study_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.task = Task(lambda report: job(theme, report), self)
        self.task.progress.connect(self.progress.setValue)
        self.task.done.connect(on_done)
        self.task.failed.connect(self._failed)
        self.task.start()

    def _finish(self):
        self.run_btn.setEnabled(True)
        self.study_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.placeholder.setVisible(False)

    def _failed(self, text):
        self._finish()
        QMessageBox.critical(self, "Ошибка", text)

    # --- один расчёт -------------------------------------------------------
    def run(self):
        params = self.params()
        self._start(lambda theme, report: EfficiencyModel(theme, params).run(
            progress=lambda i: report(int(100 * i / params.runs))), self._done)

    def _done(self, res):
        self._finish()
        fmt = {"q": "{:.3f}", "q1": "{:.3f}", "q2": "{:.3f}", "availability": "{:.4f}",
               "mean_delay": "{:.1f}", "annulled": "{:.0f}"}
        for key, card in self.cards.items():
            card.set(fmt[key].format(res.mean_ci(key)[0]))
        self.cards_box.setVisible(True)
        self.plot_title.setText("Структура потерь и очередь заявок")
        draw_lr2(self.plot.figure, res)
        self.plot.draw()

    # --- исследование ------------------------------------------------------
    def study(self):
        key, title, values = STUDIES[self.study_param.currentIndex()]
        base = replace(self.params(), runs=min(self.runs.value(), 10))
        self._start(lambda theme, report: run_study(theme, base, key, values, report),
                    lambda data: self._study_done(title, data))

    def _study_done(self, title, data):
        self._finish()
        self.cards_box.setVisible(False)
        self.plot_title.setText(f"Как потери Q зависят от параметра «{title}» "
                                "(полоса — 95% доверительный интервал)")
        draw_study(self.plot.figure, title, data, simple=True)
        self.plot.draw()
