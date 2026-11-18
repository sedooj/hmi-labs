"""Окно 2. ЛР1: время решения задачи пользователем."""
from __future__ import annotations

from PySide6.QtWidgets import (QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QVBoxLayout, QWidget)

from ..dialog_sim import DialogSimulator, theory_mean_theme
from ..plots import draw_histograms
from .common import Plot, Task, big_button, fill, hint, ispin, progress_bar, result_table, section


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
        self.get_theme = get_theme
        self.samples = {}
        self.theory = {}

        self.n = ispin(100, 1_000_000, 10_000, 1000)
        self.p_text = QLineEdit("0 0.3 0.6 0.9")
        self.k = ispin(0, 200, 0)
        self.k.setSpecialValueText("авто")
        self.k.setToolTip("Число интервалов гистограммы. «авто» — K = int(1 + 3.22·lg N)")
        self.k.valueChanged.connect(self.redraw)
        self.run_btn = big_button("Моделировать")
        self.run_btn.clicked.connect(self.run)
        self.progress = progress_bar()

        form = QFormLayout()
        form.addRow("Число реализаций N:", self.n)
        form.addRow("Вероятности ошибки P:", self.p_text)
        form.addRow("Интервалов K:", self.k)

        left = QVBoxLayout()
        left.addWidget(hint("<b>ЛР1. Сколько времени пользователь решает задачу.</b><br><br>"
                            "1. Задайте число реализаций N и значения вероятности ошибки P.<br>"
                            "2. Нажмите «Моделировать».<br><br>"
                            "Справа появятся гистограммы времени решения задачи для каждого P, "
                            "внизу — средние времена. Число интервалов K можно поменять после "
                            "расчёта — гистограммы перестроятся сразу."))
        left.addLayout(form)
        left.addWidget(self.run_btn)
        left.addWidget(self.progress)
        left.addStretch()
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(330)

        self.plot = Plot()
        self.table = result_table(["P", "Подтема 1, с", "Подтема 2, с",
                                   "Задача целиком, с", "По формуле, с"])
        self.table.setVisible(False)
        self.placeholder = QLabel("Нажмите «Моделировать», чтобы увидеть результаты")
        self.placeholder.setStyleSheet("color: #888; font-size: 16px;")
        right = QVBoxLayout()
        right.addWidget(section("Гистограммы времени решения задачи"))
        right.addWidget(self.placeholder)
        right.addWidget(self.plot, 1)
        right.addWidget(section("Среднее время"))
        right.addWidget(self.table)

        lay = QHBoxLayout(self)
        lay.addWidget(left_w)
        lay.addLayout(right, 1)

    def run(self):
        try:
            theme = self.get_theme()
            p_values = parse_p(self.p_text.text())
        except ValueError as e:
            QMessageBox.warning(self, "Проверьте данные", str(e))
            return
        n = self.n.value()
        total = 3 * n * len(p_values)

        def job(report):
            sim = DialogSimulator(theme)
            out, done = {}, 0
            for p in p_values:
                for target in ("sub0", "sub1", "theme"):
                    out[(target, p)] = sim.sample(
                        n, target, p, "repeat",
                        progress=lambda j, d=done: report(int(100 * (d + j) / total)))
                    done += n
            return theme, p_values, out

        self.run_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.task = Task(job, self)
        self.task.progress.connect(self.progress.setValue)
        self.task.done.connect(self._done)
        self.task.failed.connect(self._failed)
        self.task.start()

    def _failed(self, text):
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Ошибка", text)

    def _done(self, result):
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        theme, p_values, out = result
        self.samples = {p: out[("theme", p)] for p in p_values}
        self.theory = {p: theory_mean_theme(theme, p, "repeat") for p in p_values}
        rows = [[f"{p:g}", float(out[("sub0", p)].mean()), float(out[("sub1", p)].mean()),
                 float(out[("theme", p)].mean()), float(self.theory[p])] for p in p_values]
        fill(self.table, rows)
        self.table.setVisible(True)
        self.placeholder.setVisible(False)
        self.redraw()

    def redraw(self, *_):
        if self.samples:
            draw_histograms(self.plot.figure, self.samples, self.k.value() or None, self.theory)
            self.plot.draw()
