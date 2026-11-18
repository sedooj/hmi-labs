"""Вкладка ЛР1: моделирование времени решения задачи и гистограммы."""
from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
                               QSplitter, QVBoxLayout, QWidget)

from ..dialog_sim import (DialogSimulator, SampleStats, auto_k, histogram,
                          theory_mean_subtopic, theory_mean_theme)
from ..model import ERROR_MODES
from .common import ACCENT, ACCENT2, PlotWidget, Task, fill_table, ispin, readonly_table

TARGETS = [("theme", "Тема целиком"), ("sub0", "Подтема 1"), ("sub1", "Подтема 2")]


def parse_p_list(text: str) -> list[float]:
    vals = [float(x.replace(",", ".")) for x in text.replace(";", " ").split()]
    if not vals or any(not 0 <= v < 1 for v in vals):
        raise ValueError("значения P должны быть в [0; 1)")
    return vals


class Lr1Tab(QWidget):
    def __init__(self, get_theme, parent=None):
        super().__init__(parent)
        self.get_theme = get_theme
        self.samples: dict[tuple[str, float], np.ndarray] = {}
        self.unfinished: dict[tuple[str, float], int] = {}
        self.p_values: list[float] = []
        self.task: Task | None = None

        # --- параметры ------------------------------------------------------
        self.n = ispin(10, 1_000_000, 10_000, 1000)
        self.p_text = QLineEdit("0; 0.3; 0.6; 0.9")
        self.p_text.setToolTip("Значения вероятности ошибки через точку с запятой")
        self.mode = QComboBox()
        for key, title in ERROR_MODES.items():
            self.mode.addItem(title, key)
        self.seed = ispin(0, 999_999, 0)
        self.seed.setSpecialValueText("случайный")
        self.run_btn = QPushButton("▶ Моделировать")
        self.run_btn.setDefault(True)
        self.run_btn.clicked.connect(self.run)
        self.progress = QProgressBar()
        self.progress.setVisible(False)

        params = QGroupBox("Эксперимент")
        f = QFormLayout(params)
        f.addRow("Объём выборки N:", self.n)
        f.addRow("Вероятности ошибки P:", self.p_text)
        f.addRow("Обработка ошибок:", self.mode)
        f.addRow("Зерно генератора:", self.seed)
        f.addRow(self.run_btn)
        f.addRow(self.progress)

        # --- отображение гистограмм ---------------------------------------
        self.target = QComboBox()
        for key, title in TARGETS:
            self.target.addItem(title, key)
        self.k_auto = QCheckBox("по формуле K = int(1 + 3.22·lg N)")
        self.k_auto.setChecked(True)
        self.k = ispin(1, 500, 15)
        self.k.setEnabled(False)
        self.k_auto.toggled.connect(lambda on: self.k.setEnabled(not on))
        self.freq_p = QComboBox()
        view = QGroupBox("Гистограмма (перестраивается без повторного моделирования)")
        g = QFormLayout(view)
        g.addRow("Что показывать:", self.target)
        g.addRow("Интервалов K:", self.k_auto)
        g.addRow("", self.k)
        g.addRow("Таблица частот для P:", self.freq_p)
        for sig in (self.target.currentIndexChanged, self.k_auto.toggled, self.k.valueChanged,
                    self.freq_p.currentIndexChanged):
            sig.connect(self.redraw)

        self.summary = readonly_table(["P", "t̄ подтемы 1, с", "t̄ подтемы 2, с", "t̄ темы, с",
                                       "M[t] темы (теор.), с", "СКО темы, с", "мин, с", "макс, с",
                                       "не заверш."])
        self.freq = readonly_table(["№", "Интервал, с", "n", "n/N"])
        self.note = QLabel()
        self.note.setWordWrap(True)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(params)
        ll.addWidget(view)
        ll.addWidget(QLabel("Частоты по интервалам:"))
        ll.addWidget(self.freq, 1)

        self.plot = PlotWidget()
        right = QSplitter(Qt.Vertical)
        right.addWidget(self.plot)
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(QLabel("Средние времена по результатам моделирования:"))
        bl.addWidget(self.summary)
        bl.addWidget(self.note)
        right.addWidget(bottom)
        right.setSizes([560, 230])

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([360, 900])
        QHBoxLayout(self).addWidget(split)

    # --- моделирование ----------------------------------------------------
    def run(self):
        try:
            theme = self.get_theme()
            errors = theme.check()
            if errors:
                raise ValueError("\n".join(errors))
            p_values = parse_p_list(self.p_text.text())
        except ValueError as e:
            QMessageBox.warning(self, "Исходные данные", str(e))
            return
        n = self.n.value()
        mode = self.mode.currentData()
        seed = self.seed.value() or None
        total = len(p_values) * 3 * n

        def job(report):
            sim = DialogSimulator(theme, seed)
            samples, unfinished, done = {}, {}, 0
            for p in p_values:
                for key, _ in TARGETS:
                    before = sim.unfinished
                    samples[(key, p)] = sim.sample(
                        n, key, p, mode, progress=lambda j, d=done: report(int(100 * (d + j) / total)))
                    unfinished[(key, p)] = sim.unfinished - before
                    done += n
            return theme, mode, p_values, samples, unfinished

        self.run_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.task = Task(job, self)
        self.task.progress.connect(self.progress.setValue)
        self.task.done.connect(self._on_done)
        self.task.failed.connect(self._on_fail)
        self.task.start()

    def _on_fail(self, text: str):
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Ошибка моделирования", text)

    def _on_done(self, result):
        self.run_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.theme, self.used_mode, self.p_values, self.samples, self.unfinished = result
        self.freq_p.blockSignals(True)
        self.freq_p.clear()
        for p in self.p_values:
            self.freq_p.addItem(f"{p:g}", p)
        self.freq_p.blockSignals(False)
        self._fill_summary()
        self.redraw()

    def _fill_summary(self):
        rows = []
        for p in self.p_values:
            th = self.samples[("theme", p)]
            st = SampleStats.of(th)
            theory = theory_mean_theme(self.theme, p, self.used_mode)
            unf = sum(self.unfinished[(k, p)] for k, _ in TARGETS)
            rows.append([f"{p:g}",
                         float(self.samples[("sub0", p)].mean()),
                         float(self.samples[("sub1", p)].mean()),
                         st.mean,
                         "—" if theory is None or math.isinf(theory) else float(theory),
                         st.sd, st.min, st.max, unf])
        fill_table(self.summary, rows)
        unf = sum(self.unfinished.values())
        n = len(next(iter(self.samples.values())))
        note = (f"N = {n:,} реализаций на каждое значение P. Теоретическое M[t] получено по "
                "формулам для выбранной процедуры обработки ошибок.".replace(",", " "))
        if unf:
            note += (f"  ⚠ {unf} реализаций оборваны по пределу числа исполнений шагов: "
                     "при такой процедуре и больших P диалог практически не завершается.")
        self.note.setText(note)

    # --- гистограммы ------------------------------------------------------
    def redraw(self, *_):
        if not self.samples:
            return
        target = self.target.currentData()
        title = self.target.currentText()
        fig = self.plot.figure
        fig.clear()
        m = len(self.p_values)
        cols = 2 if m > 1 else 1
        rows = math.ceil(m / cols)
        axes = fig.subplots(rows, cols, squeeze=False).ravel()
        for ax in axes[m:]:
            ax.set_visible(False)
        for ax, p in zip(axes, self.p_values):
            x = self.samples[(target, p)]
            k = auto_k(len(x)) if self.k_auto.isChecked() else self.k.value()
            counts, edges = histogram(x, k)
            mean = x.mean()
            colors = [ACCENT2 if lo <= mean < hi else ACCENT for lo, hi in zip(edges, edges[1:])]
            ax.bar(edges[:-1], counts / len(x), width=np.diff(edges), align="edge",
                   color=colors, edgecolor="white", linewidth=0.5)
            ax.axvline(mean, color=ACCENT2, lw=1.5, ls="--", label=f"t̄ = {mean:.1f} с")
            theory = self._theory(target, p)
            if theory is not None and not math.isinf(theory):
                ax.axvline(theory, color="#444", lw=1, ls=":", label=f"M[t] = {theory:.1f} с")
            ax.set_title(f"{title}, P = {p:g}  (K = {k})")
            ax.set_xlabel("время решения задачи, с")
            ax.set_ylabel("относительная частота")
            ax.legend(loc="upper right", fontsize=8)
        self.plot.draw()
        self._fill_freq(target)

    def _theory(self, target: str, p: float):
        if target == "theme":
            return theory_mean_theme(self.theme, p, self.used_mode)
        return theory_mean_subtopic(self.theme.subtopics[int(target[-1])], p, self.used_mode)

    def _fill_freq(self, target: str):
        p = self.freq_p.currentData()
        if p is None:
            return
        x = self.samples[(target, p)]
        k = auto_k(len(x)) if self.k_auto.isChecked() else self.k.value()
        counts, edges = histogram(x, k)
        rows = [[i + 1, f"{lo:.1f} – {hi:.1f}", int(c), float(c / len(x))]
                for i, (lo, hi, c) in enumerate(zip(edges, edges[1:], counts))]
        fill_table(self.freq, rows)
