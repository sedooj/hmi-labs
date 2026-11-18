"""ЛР2. Оценка эффективности человеко-машинной системы «диспетчер — АРМ — сеть».

Модель (время в секундах):
  * заявки на оперативное регулирование приходят пуассоновским потоком с
    интенсивностью λ; диспетчер один и обслуживает их по очереди (FIFO);
    время обслуживания заявки — реализация подтемы 1 модели ЛР1;
  * наработка на отказ — случайная величина (экспоненциальный закон или
    закон Вейбулла); при отказе все заявки в очереди и на обслуживании
    аннулируются;
  * восстановление — реализация подтемы 2 модели ЛР1; на время
    восстановления система простаивает, новые заявки копятся в очереди и
    обслуживаются после восстановления;
  * обработка ошибок — переход в текущую вершину графа (повтор шага).

Потери:
  L1 = R1 · Σ задержек выдачи регулирующих воздействий;
     задержка обслуженной заявки = момент окончания обслуживания − момент
     прихода; для аннулированной — момент окончания восстановления − момент
     прихода (воздействие так и не выдано всё это время);
  L2 = R2 · Σ времени простоя.
Показатель эффективности — средние удельные потери Q = (L1 + L2) / T,
где T — моделируемый интервал. Чем меньше Q, тем эффективнее система.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .dialog_sim import DialogSimulator
from .model import Theme


@dataclass
class Lr2Params:
    lam_per_hour: float = 30.0     # интенсивность потока заявок, 1/ч
    mtbf_hours: float = 6.0        # средняя наработка на отказ, ч
    failure_law: str = "exp"       # 'exp' или 'weibull'
    weibull_shape: float = 1.5     # параметр формы закона Вейбулла
    r1: float = 1.0                # удельные потери от задержки, у.е./с
    r2: float = 10.0               # удельные потери от простоя, у.е./с
    horizon_hours: float = 720.0   # моделируемый интервал T, ч
    runs: int = 20                 # число прогонов модели
    p1: float = 0.05               # P ошибки диспетчера в подтеме 1
    p2: float = 0.05               # P ошибки диспетчера в подтеме 2
    time_scale: float = 1.0        # темп работы диспетчера (×время шагов)
    seed: int | None = None


@dataclass
class RunResult:
    horizon: float = 0.0
    arrived: int = 0
    served: int = 0
    annulled: int = 0
    failures: int = 0
    sum_delay: float = 0.0
    sum_service: float = 0.0
    downtime: float = 0.0
    loss1: float = 0.0
    loss2: float = 0.0
    trace: list = field(default_factory=list)  # (t, длина очереди, состояние) первого прогона
    loss_trace: list = field(default_factory=list)  # (t, накопл. потери R1, накопл. потери R2)

    @property
    def q(self) -> float:
        return (self.loss1 + self.loss2) / self.horizon

    @property
    def q1(self) -> float:
        return self.loss1 / self.horizon

    @property
    def q2(self) -> float:
        return self.loss2 / self.horizon

    @property
    def availability(self) -> float:
        return 1 - self.downtime / self.horizon

    @property
    def mean_delay(self) -> float:
        n = self.served + self.annulled
        return self.sum_delay / n if n else 0.0

    @property
    def utilization(self) -> float:
        return self.sum_service / self.horizon


@dataclass
class Lr2Result:
    params: Lr2Params
    runs: list[RunResult]

    def _arr(self, attr: str) -> np.ndarray:
        return np.array([getattr(r, attr) for r in self.runs], dtype=float)

    def mean_ci(self, attr: str) -> tuple[float, float]:
        """Среднее по прогонам и полуширина 95%-го доверительного интервала."""
        x = self._arr(attr)
        if len(x) < 2:
            return float(x.mean()), 0.0
        return float(x.mean()), 1.96 * float(x.std(ddof=1)) / math.sqrt(len(x))


class EfficiencyModel:
    def __init__(self, theme: Theme, params: Lr2Params):
        self.theme = theme
        self.p = params
        self.sim = DialogSimulator(theme, params.seed, params.time_scale)
        self.rng = self.sim.rng

    def _uptime(self) -> float:
        mean = self.p.mtbf_hours * 3600
        if self.p.failure_law == "weibull":
            k = self.p.weibull_shape
            scale = mean / math.gamma(1 + 1 / k)  # масштаб, дающий нужное среднее
            return self.rng.weibullvariate(scale, k)
        return self.rng.expovariate(1 / mean)

    def run_once(self, keep_trace: bool = False) -> RunResult:
        p = self.p
        H = p.horizon_hours * 3600
        lam = p.lam_per_hour / 3600
        res = RunResult(horizon=H)
        rnd = self.rng
        sim = self.sim
        trace = res.trace if keep_trace else None

        t = 0.0                                  # начало очередного периода работы
        queue: deque[float] = deque()            # моменты прихода ожидающих заявок
        next_arrival = rnd.expovariate(lam) if lam > 0 else math.inf

        while t < H:
            t_fail = t + self._uptime()
            end = min(t_fail, H)
            free_at = t                          # когда диспетчер освободится
            # --- работа: обслуживание заявок до отказа ---------------------
            while True:
                # все заявки, пришедшие до освобождения диспетчера, встают в очередь
                while next_arrival <= min(free_at, end):
                    queue.append(next_arrival)
                    res.arrived += 1
                    if trace is not None:
                        trace.append((next_arrival, len(queue), 1))
                    next_arrival += rnd.expovariate(lam)
                if not queue:
                    if next_arrival >= end:
                        break
                    free_at = next_arrival       # ждём следующую заявку
                    continue
                if free_at >= end:
                    break
                arr = queue.popleft()
                start = free_at
                if trace is not None:
                    trace.append((start, len(queue), 1))
                service = sim.realize_subtopic(0, p.p1, "repeat")
                finish = start + service
                if finish <= end:
                    res.served += 1
                    res.sum_delay += finish - arr
                    if trace is not None:
                        res.loss_trace.append((finish, p.r1 * res.sum_delay, p.r2 * res.downtime))
                    res.sum_service += service
                    free_at = finish
                else:
                    # отказ во время обслуживания — заявка аннулируется
                    res.sum_service += end - start
                    queue.appendleft(arr)
                    free_at = end
                    break
            # заявки, пришедшие, пока шло последнее (прерванное) обслуживание
            while next_arrival < end:
                queue.append(next_arrival)
                res.arrived += 1
                next_arrival += rnd.expovariate(lam)
            if t_fail >= H:
                # горизонт закончился раньше отказа: незавершённые заявки
                # учитываются с задержкой до конца интервала
                for arr in queue:
                    res.sum_delay += H - arr
                break
            # --- отказ и восстановление ------------------------------------
            res.failures += 1
            recovery = sim.realize_subtopic(1, p.p2, "repeat")
            t_up = t_fail + recovery
            res.downtime += min(t_up, H) - t_fail
            if trace is not None:
                trace.append((t_fail, 0, 0))
            for arr in queue:
                res.annulled += 1
                res.sum_delay += min(t_up, H) - arr
            queue.clear()
            # заявки, пришедшие во время восстановления, ждут в очереди
            while next_arrival < min(t_up, H):
                queue.append(next_arrival)
                res.arrived += 1
                next_arrival += rnd.expovariate(lam)
            if trace is not None:
                trace.append((min(t_up, H), len(queue), 1))
                res.loss_trace.append((min(t_up, H), p.r1 * res.sum_delay, p.r2 * res.downtime))
            t = t_up

        res.loss1 = p.r1 * res.sum_delay
        res.loss2 = p.r2 * res.downtime
        return res

    def run(self, progress=None) -> Lr2Result:
        runs = []
        for i in range(self.p.runs):
            runs.append(self.run_once(keep_trace=(i == 0)))
            if progress:
                progress(i + 1)
        return Lr2Result(self.p, runs)
