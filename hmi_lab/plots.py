"""Графики ЛР1 и ЛР2 (используются и в окне программы, и в отчёте)."""
from __future__ import annotations

import math
from dataclasses import replace

import matplotlib
import numpy as np

from .dialog_sim import auto_k, histogram
from .efficiency_sim import EfficiencyModel, Lr2Params, Lr2Result

MUTED = "#6B7280"
matplotlib.rcParams.update({
    "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    "font.size": 9.5,
    "text.color": "#111827",
    "axes.labelcolor": MUTED,
    "axes.edgecolor": "#D1D5DB",
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.titlepad": 10,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.color": "#E5E7EB",
    "grid.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "ytick.left": False,
    "legend.frameon": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})

DECIMAL = "."  # для отчёта заменяется на запятую (print_style)


def print_style():
    """Оформление графиков для отчёта: Times New Roman, чёрный текст, десятичная запятая."""
    global DECIMAL
    DECIMAL = ","
    matplotlib.rcParams.update({
        "font.family": ["Times New Roman", "DejaVu Serif"],
        "font.size": 12,
        "text.color": "black",
        "axes.labelcolor": "black",
        "axes.titleweight": "normal",
        "axes.titlesize": 12,
        "axes.edgecolor": "black",
        "axes.spines.left": True,
        "xtick.color": "black",
        "ytick.color": "black",
        "ytick.left": True,
        "legend.fontsize": 11,
    })


def n(x: float, spec: str = "g") -> str:
    """Число с нужным десятичным разделителем."""
    return format(x, spec).replace(".", DECIMAL)


def _localize(fig):
    if DECIMAL == ".":
        return
    from matplotlib.ticker import FuncFormatter, ScalarFormatter
    f = FuncFormatter(lambda v, _: n(round(v, 10)))
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            # только обычные числовые оси (не логарифмические и не категории)
            if isinstance(axis.get_major_formatter(), ScalarFormatter):
                axis.set_major_formatter(f)


BLUE = "#4F46E5"     # основной (индиго)
ORANGE = "#F59E0B"   # акцент (янтарный)
GREEN = "#10B981"
RED = "#EF4444"
PURPLE = "#8B5CF6"


# --- ЛР1 ---------------------------------------------------------------------
def draw_histograms(fig, samples: dict[float, np.ndarray], k: int | None = None,
                    theory: dict[float, float] | None = None):
    """Гистограммы времени решения задачи, по одной на каждое значение P."""
    fig.clear()
    ps = list(samples)
    cols = 2 if len(ps) > 1 else 1
    rows = math.ceil(len(ps) / cols)
    axes = fig.subplots(rows, cols, squeeze=False).ravel()
    for ax in axes[len(ps):]:
        ax.set_visible(False)
    for ax, p in zip(axes, ps):
        x = samples[p]
        kk = k or auto_k(len(x))
        counts, edges = histogram(x, kk)
        mean = x.mean()
        colors = [ORANGE if lo <= mean < hi else BLUE for lo, hi in zip(edges, edges[1:])]
        ax.bar(edges[:-1], counts / len(x), width=np.diff(edges), align="edge",
               color=colors, edgecolor="white", linewidth=1.2)
        ax.axvline(mean, color=ORANGE, lw=1.5, ls="--", label=f"среднее {n(mean, '.1f')} с")
        if theory and p in theory:
            ax.axvline(theory[p], color="#111827", lw=1, ls=":", label=f"по формуле {n(theory[p], '.1f')} с")
        ax.set_title(f"P = {n(p)}", loc="left")
        ax.text(1, 1.02, f"K = {kk}", transform=ax.transAxes, ha="right", va="bottom",
                color=MUTED)
        ax.set_xlabel("время, с")
        ax.legend(loc="upper right", fontsize="small")
    _localize(fig)


# --- ЛР2 ---------------------------------------------------------------------
def draw_lr2(fig, res: Lr2Result):
    """Структура потерь и их накопление во времени."""
    fig.clear()
    ax1, ax2 = fig.subplots(1, 2, width_ratios=[1, 2.4])
    q1, c1 = res.mean_ci("q1")
    q2, c2 = res.mean_ci("q2")
    ax1.bar(["задержки\n(R1)", "простой\n(R2)"], [q1, q2], yerr=[c1, c2], capsize=4,
            color=[BLUE, ORANGE], width=0.55, ecolor="#9CA3AF")
    ax1.set_title("Средние потери")
    ax1.set_ylabel("у.е./с")

    run = res.runs[0]
    lt = np.array(run.loss_trace) if run.loss_trace else np.zeros((1, 3))
    t = np.concatenate([[0], lt[:, 0] / 3600])
    l1 = np.concatenate([[0], lt[:, 1]]) / 1000
    l2 = np.concatenate([[0], lt[:, 2]]) / 1000
    ax2.stackplot(t, l1, l2, colors=[BLUE, ORANGE], alpha=0.85,
                  labels=["от задержек (R1)", "от простоя (R2)"])
    ax2.set_xlim(0, t[-1])
    ax2.set_ylim(0)
    ax2.set_title("Накопленные потери (один прогон)")
    ax2.set_xlabel("время, ч")
    ax2.set_ylabel("потери, тыс. у.е.")
    ax2.legend(loc="upper left")
    _localize(fig)


STUDY_PARAMS = {
    "p": "P ошибки оператора",
    "p1": "P ошибки в подтеме 1",
    "p2": "P ошибки в подтеме 2",
    "time_scale": "Темп работы оператора (×время шагов)",
}


def apply_param(base: Lr2Params, key: str, value: float) -> Lr2Params:
    if key == "p":
        return replace(base, p1=value, p2=value)
    return replace(base, **{key: value})


def run_study(theme, base: Lr2Params, key: str, values, report=None):
    """Для каждого значения параметра — серия прогонов модели ЛР2."""
    out = []
    for i, v in enumerate(values):
        out.append((float(v), EfficiencyModel(theme, apply_param(base, key, float(v))).run()))
        if report:
            report(int(100 * (i + 1) / len(values)))
    return out


def draw_study(fig, title: str, data, simple: bool = False):
    """Q(параметр); в полном варианте ещё задержка и коэффициент готовности."""
    fig.clear()
    if simple:
        ax1 = fig.subplots()
    else:
        ax1, ax2 = fig.subplots(2, 1, sharex=True)
    x = np.array([v for v, _ in data])
    for attr, label, color in (("q", "Q (всего)", "black"), ("q1", "от задержек", BLUE),
                               ("q2", "от простоя", ORANGE)):
        m = np.array([r.mean_ci(attr)[0] for _, r in data])
        c = np.array([r.mean_ci(attr)[1] for _, r in data])
        ax1.plot(x, m, "o-", color=color, ms=3, label=label, lw=1.6 if attr == "q" else 1)
        ax1.fill_between(x, m - c, m + c, color=color, alpha=0.12, lw=0)
    ax1.set_ylabel("потери, у.е./с")
    qs = [r.mean_ci("q")[0] for _, r in data]
    if min(qs) > 0 and max(qs) / min(qs) > 50:
        ax1.set_yscale("log")
    if not simple:
        ax1.set_title(f"Влияние параметра: {title}")
    ax1.legend()
    if simple:
        ax1.set_xlabel(title)
        _localize(fig)
        return
    d = np.array([r.mean_ci("mean_delay")[0] for _, r in data])
    a = np.array([r.mean_ci("availability")[0] for _, r in data])
    ax2.plot(x, d, "s-", color=GREEN, ms=3)
    ax2.set_ylabel("средняя задержка, с", color=GREEN)
    if d.min() > 0 and d.max() / d.min() > 50:
        ax2.set_yscale("log")
    ax3 = ax2.twinx()
    ax3.plot(x, a, "^--", color=PURPLE, ms=3)
    ax3.set_ylabel("коэфф. готовности", color=PURPLE)
    ax3.grid(False)
    ax2.set_xlabel(title)
    _localize(fig)
