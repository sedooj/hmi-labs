"""Раздел 2. ЛР1: время решения задачи пользователем."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QMessageBox, QVBoxLayout, QWidget

from ..dialog_sim import DEFAULT_SEED, DialogSimulator, theory_mean_theme
from ..plots import draw_histograms
from .common import (Card, Kpi, Plot, Task, button, field, fill, ispin, label, page_header,
                     progress_bar, seed_edit, table)


def parse_p(text: str) -> list[float]:
    try:
        vals = [float(x.replace(",", ".")) for x in text.replace(";", " ").split()]
    except ValueError:
        raise ValueError("Значения P — числа через пробел, например: 0 0.3 0.6 0.9")
    if not vals or any(not 0 <= v < 1 for v in vals):
        raise ValueError("Каждое значение P должно быть от 0 до 1 (не включая 1)")
    return vals


class Lr1Tab(QWidget):
    def __init__(self, get_theme, parent=None):
        super().__init__(parent)
        self.setObjectName("page")
        self.get_theme = get_theme
        self.samples = {}
        self.theory = {}

        # --- параметры -------------------------------------------------------
        self.n = ispin(100, 1_000_000, 10_000, 1000)
        self.p_text = QLineEdit("0 0.3 0.6 0.9")
        self.k = ispin(0, 200, 0, allow_empty=True, placeholder="авто")
        self.k.valueChanged.connect(self.redraw)
        self.seed = seed_edit(DEFAULT_SEED)
        self.run_btn = button("Моделировать")
        self.run_btn.clicked.connect(self.run)
        self.progress = progress_bar()

        params = Card("Параметры", "Задайте значения и запустите моделирование")
        params.add(field("Число реализаций N", self.n))
        params.add(field("Вероятности ошибки P (через пробел)", self.p_text))
        params.add(field("Интервалов гистограммы K", self.k))
        params.add(label("Пусто — K = int(1 + 3.22·lg N). Можно менять после расчёта.",
                         "muted", True))
        params.add(field("Зерно генератора", self.seed))
        params.add(label("С зерном 2026 получаются те же числа, что в отчёте. "
                         "Пусто — каждый запуск случайный.", "muted", True))
        params.body.addSpacing(6)
        params.add(self.run_btn)
        params.add(self.progress)

        # --- результаты ------------------------------------------------------
        self.kpi = {
            "theme": Kpi("Задача, P = 0", accent=True),
            "sub0": Kpi("Подтема 1"),
            "sub1": Kpi("Подтема 2"),
            "dev": Kpi("Отклонение от формулы"),
        }
        kpis = QHBoxLayout()
        kpis.setSpacing(14)
        for k in self.kpi.values():
            kpis.addWidget(k)

        self.plot = Plot()
        self.plot_card = Card("Гистограммы времени решения задачи",
                              "Оранжевый столбец — интервал со средним значением")
        self.empty = label("Нажмите «Моделировать», чтобы увидеть результаты", "muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.plot_card.add(self.empty, 1)
        self.plot_card.add(self.plot, 1)
        self.plot.setVisible(False)

        self.table = table(["P", "Подт. 1", "Подт. 2", "Задача", "Формула"])
        table_card = Card("Среднее время, с", "Моделирование и расчёт по формуле")
        table_card.add(self.table)
        fill(self.table, [])

        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(params)
        left.addWidget(table_card)
        left.addStretch()
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(400)

        right = QVBoxLayout()
        right.setSpacing(16)
        right.addLayout(kpis)
        right.addWidget(self.plot_card, 1)

        body = QHBoxLayout()
        body.setSpacing(18)
        body.addWidget(left_w)
        body.addLayout(right, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)
        lay.addWidget(page_header("ЛР1 · Время диалога",
                                  "Сколько времени пользователь решает задачу и как это зависит "
                                  "от вероятности ошибки P"))
        lay.addLayout(body, 1)

    def run(self):
        try:
            theme = self.get_theme()
            p_values = parse_p(self.p_text.text())
        except ValueError as e:
            QMessageBox.warning(self, "Проверьте данные", str(e))
            return
        n = self.n.value()
        seed = self.seed.value() or None
        total = 3 * n * len(p_values)

        def job(report):
            sim = DialogSimulator(theme, seed)
            out, done = {}, 0
            for p in p_values:
                for target in ("sub0", "sub1", "theme"):
                    out[(target, p)] = sim.sample(
                        n, target, p, "repeat",
                        progress=lambda j, d=done: report(int(100 * (d + j) / total)))
                    done += n
            return theme, p_values, out

        self.run_btn.setEnabled(False)
        self.run_btn.setText("Считаю…")
        self.progress.setVisible(True)
        self.task = Task(job, self)
        self.task.progress.connect(self.progress.setValue)
        self.task.done.connect(self._done)
        self.task.failed.connect(self._failed)
        self.task.start()

    def _finish(self):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Моделировать")
        self.progress.setVisible(False)

    def _failed(self, text):
        self._finish()
        QMessageBox.critical(self, "Ошибка", text)

    def _done(self, result):
        self._finish()
        theme, p_values, out = result
        self.samples = {p: out[("theme", p)] for p in p_values}
        self.theory = {p: theory_mean_theme(theme, p, "repeat") for p in p_values}
        rows = [[f"{p:g}", float(out[("sub0", p)].mean()), float(out[("sub1", p)].mean()),
                 float(out[("theme", p)].mean()), float(self.theory[p])] for p in p_values]
        fill(self.table, rows)

        p0 = p_values[0]
        self.kpi["theme"].title.setText(f"Задача, P = {p0:g}")
        for key in ("theme", "sub0", "sub1"):
            self.kpi[key].set(f"{out[(key, p0)].mean():.1f} с")
        dev = max(abs(out[("theme", p)].mean() - self.theory[p]) / self.theory[p] for p in p_values)
        self.kpi["dev"].set(f"{dev * 100:.1f} %")

        self.empty.setVisible(False)
        self.plot.setVisible(True)
        self.redraw()

    def redraw(self, *_):
        if self.samples:
            draw_histograms(self.plot.figure, self.samples, self.k.value() or None, self.theory)
            self.plot.draw()
