"""Графики ЛР1 и ЛР2 (используются и в окне программы, и в отчёте)."""
from __future__ import annotations

import math
from dataclasses import replace

import matplotlib
import numpy as np

from .dialog_sim import auto_k, histogram
from .efficiency_sim import EfficiencyModel, Lr2Params, Lr2Result

matplotlib.rcParams.update({
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

BLUE = "#2f6db5"
ORANGE = "#d9822b"
GREEN = "#3a9b5c"


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
               color=colors, edgecolor="white", linewidth=0.5)
        ax.axvline(mean, color=ORANGE, lw=1.5, ls="--", label=f"среднее {mean:.1f} с")
        if theory and p in theory:
            ax.axvline(theory[p], color="#444", lw=1, ls=":", label=f"по формуле {theory[p]:.1f} с")
        ax.set_title(f"P = {p:g}   (K = {kk})")
        ax.set_xlabel("время решения задачи, с")
        ax.set_ylabel("доля реализаций")
        ax.legend(loc="upper right", fontsize=8)


# --- ЛР2 ---------------------------------------------------------------------
def draw_lr2(fig, res: Lr2Result, window_hours: float = 8.0):
    """Структура потерь и очередь заявок в первом прогоне."""
    fig.clear()
    ax1, ax2 = fig.subplots(1, 2, width_ratios=[1, 2.4])
    q1, c1 = res.mean_ci("q1")
    q2, c2 = res.mean_ci("q2")
    ax1.bar(["задержки\n(R1)", "простой\n(R2)"], [q1, q2], yerr=[c1, c2], capsize=5,
            color=[BLUE, ORANGE])
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
    ax2.fill_between(th, q, step="post", color=BLUE, alpha=0.35, lw=0)
    ax2.step(th, q, where="post", color=BLUE, lw=0.8)
    top = max(q) + 1
    for a, b in down:
        ax2.axvspan(a / 3600, b / 3600, color="#d64545", alpha=0.35, lw=0)
        ax2.plot([a / 3600], [top], "v", color="#d64545", ms=7)
    ax2.set_ylim(0, top + 0.6)
    ax2.set_xlim(0, H / 3600)
    ax2.set_title(f"Очередь заявок: первые {H / 3600:g} ч (▼ — отказ)")
    ax2.set_xlabel("время, ч")
    ax2.set_ylabel("заявок в очереди")


STUDY_PARAMS = {
    "p": "P ошибки диспетчера",
    "p1": "P ошибки в подтеме 1",
    "p2": "P ошибки в подтеме 2",
    "time_scale": "Темп работы диспетчера (×время шагов)",
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
    ax1.set_title(f"Влияние параметра: {title}")
    ax1.legend(fontsize=9)
    if simple:
        ax1.set_xlabel(title)
        return
    d = np.array([r.mean_ci("mean_delay")[0] for _, r in data])
    a = np.array([r.mean_ci("availability")[0] for _, r in data])
    ax2.plot(x, d, "s-", color=GREEN, ms=3)
    ax2.set_ylabel("средняя задержка, с", color=GREEN)
    if d.min() > 0 and d.max() / d.min() > 50:
        ax2.set_yscale("log")
    ax3 = ax2.twinx()
    ax3.plot(x, a, "^--", color="#7b4fb0", ms=3)
    ax3.set_ylabel("коэфф. готовности", color="#7b4fb0")
    ax3.grid(False)
    ax2.set_xlabel(title)
