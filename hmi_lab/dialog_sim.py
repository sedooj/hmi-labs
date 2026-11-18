"""ЛР1. Имитационная модель времени решения задачи в диалоговой системе.

Одна реализация темы:
  1) по вероятностям выбора подтем разыгрывается подтема;
  2) по вероятностям маршрутов разыгрывается маршрут в подтеме;
  3) шаги маршрута проходятся по порядку; время каждого исполнения шага —
     случайная величина по заданному закону; с вероятностью P действие
     ошибочно, и диалог продолжается согласно выбранной процедуре обработки
     ошибок (повтор шага / возврат на шаг назад / всплытие в начало).
Время реализации — сумма времён всех исполненных шагов.
"""
from __future__ import annotations

import bisect
import itertools
import math
import random
from dataclasses import dataclass

import numpy as np

from .model import Step, Subtopic, Theme

# Защита от «бесконечных» реализаций при возврате/всплытии и больших P
MAX_EXECUTIONS = 2_000


def auto_k(n: int) -> int:
    """Начальное число интервалов гистограммы: K = int(1 + 3.22·lg N)."""
    return max(1, int(1 + 3.22 * math.log10(n))) if n > 1 else 1


class DialogSimulator:
    def __init__(self, theme: Theme, seed: int | None = None, time_scale: float = 1.0):
        self.theme = theme
        self.rng = random.Random(seed)
        self.time_scale = time_scale  # «темп» оператора: множитель времён шагов
        # Накопленные вероятности для розыгрыша подтем и маршрутов
        self._sub_cum = list(itertools.accumulate(s.choice_prob for s in theme.subtopics))
        self._route_cum = [list(itertools.accumulate(r.prob for r in s.routes))
                           for s in theme.subtopics]
        self.unfinished = 0  # реализации, оборванные по MAX_EXECUTIONS

    # --- элементарные розыгрыши ------------------------------------------
    def step_time(self, step: Step) -> float:
        r = self.rng
        if step.dist == "const":
            t = step.a
        elif step.dist == "normal":
            t = r.gauss(step.a, step.b) if step.b > 0 else step.a
        elif step.dist == "uniform":
            t = r.uniform(step.a, step.b)
        elif step.dist == "exp":
            t = r.expovariate(1 / step.a) if step.a > 0 else 0.0
        else:
            raise ValueError(step.dist)
        return max(t, 0.0) * self.time_scale

    @staticmethod
    def _pick(cum: list[float], u: float) -> int:
        return min(bisect.bisect_right(cum, u * cum[-1]), len(cum) - 1)

    def pick_subtopic(self) -> int:
        return self._pick(self._sub_cum, self.rng.random())

    def pick_route(self, sub_index: int) -> int:
        return self._pick(self._route_cum[sub_index], self.rng.random())

    # --- реализации -------------------------------------------------------
    def run_route(self, sub: Subtopic, route_steps: list[int], p: float,
                  mode: str) -> tuple[float, int]:
        """Проход маршрута. Возвращает (время, число ошибок)."""
        rnd = self.rng.random
        steps = sub.steps
        total, errors, executions = 0.0, 0, 0
        i = 0
        while i < len(route_steps):
            total += self.step_time(steps[route_steps[i] - 1])
            executions += 1
            if executions >= MAX_EXECUTIONS:
                self.unfinished += 1
                break
            if p > 0 and rnd() < p:
                errors += 1
                if mode == "repeat":
                    continue            # остаёмся в текущей вершине
                if mode == "back":
                    i = max(i - 1, 0)   # шаг назад по маршруту
                    continue
                i = 0                   # всплытие — в начало маршрута
                continue
            i += 1
        return total, errors

    def realize_subtopic(self, sub_index: int, p: float | None = None,
                         mode: str | None = None) -> float:
        sub = self.theme.subtopics[sub_index]
        route = sub.routes[self.pick_route(sub_index)]
        p = sub.p_error if p is None else p
        mode = mode or self.theme.error_mode
        return self.run_route(sub, route.steps, p, mode)[0]

    def realize_theme(self, p: float | None = None, mode: str | None = None) -> tuple[int, float]:
        k = self.pick_subtopic()
        return k, self.realize_subtopic(k, p, mode)

    def sample(self, n: int, target: str, p: float | None, mode: str | None = None,
               progress=None) -> np.ndarray:
        """Выборка из n реализаций. target: 'sub0', 'sub1' или 'theme'."""
        out = np.empty(n)
        for j in range(n):
            if target == "theme":
                out[j] = self.realize_theme(p, mode)[1]
            else:
                out[j] = self.realize_subtopic(int(target[-1]), p, mode)
            if progress and j % 2000 == 0:
                progress(j)
        return out


# --- аналитика -----------------------------------------------------------
def theory_mean_subtopic(sub: Subtopic, p: float, mode: str = "repeat",
                         time_scale: float = 1.0) -> float | None:
    """Точное матожидание времени подтемы.

    Для повтора шага каждое исполнение — геометрическое число попыток со
    средним 1/(1−P). Для «всплытия» матожидание маршрута длины n с суммой
    средних шагов по префиксам считается рекуррентно. Для возврата на шаг
    назад формула громоздкая — возвращается None.
    """
    if p >= 1:
        return math.inf
    total = 0.0
    for r in sub.routes:
        means = [sub.steps[s - 1].mean() for s in r.steps]
        if mode == "repeat":
            route_t = sum(means) / (1 - p)
        elif mode == "restart":
            # E_k — ожидаемое время до прохождения первых k шагов.
            # Попытка шага k: (время E_{k-1} уже затрачено) + m_k; при ошибке
            # (вероятность p) всё начинается заново: E_k = (E_{k-1} + m_k)/(1−p)
            e = 0.0
            for m in means:
                e = (e + m) / (1 - p)
            route_t = e
        else:
            return None
        total += r.prob * route_t
    return total * time_scale


def theory_mean_theme(theme: Theme, p: float, mode: str | None = None,
                      time_scale: float = 1.0) -> float | None:
    mode = mode or theme.error_mode
    parts = [theory_mean_subtopic(s, p, mode, time_scale) for s in theme.subtopics]
    if any(x is None for x in parts):
        return None
    return sum(s.choice_prob * x for s, x in zip(theme.subtopics, parts))


@dataclass
class SampleStats:
    n: int
    mean: float
    sd: float
    min: float
    max: float
    total: float

    @classmethod
    def of(cls, x: np.ndarray) -> "SampleStats":
        return cls(len(x), float(x.mean()), float(x.std(ddof=1)) if len(x) > 1 else 0.0,
                   float(x.min()), float(x.max()), float(x.sum()))


def histogram(x: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Частоты и границы K равных интервалов от min до max выборки."""
    lo, hi = float(x.min()), float(x.max())
    if hi <= lo:
        lo, hi = lo - 0.5, hi + 0.5
    counts, edges = np.histogram(x, bins=k, range=(lo, hi))
    return counts, edges
