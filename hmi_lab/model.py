"""Описание графа диалога: шаги, маршруты, подтемы и тема целиком.

Данные хранятся в JSON (см. data/*.json). Номера шагов в маршрутах
считаются с единицы — так, как их видит пользователь.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Законы распределения времени шага и смысл их параметров
DISTRIBUTIONS = {
    "const":   ("Константа (GOMS)", "t, с", ""),
    "normal":  ("Нормальный", "μ, с", "σ, с"),
    "uniform": ("Равномерный", "a, с", "b, с"),
    "exp":     ("Экспоненциальный", "среднее, с", ""),
}

# Способы обработки ошибочного действия на шаге (см. методичку ЛР1)
ERROR_MODES = {
    "repeat":  "Переход в текущую вершину (повтор шага)",
    "back":    "Возврат на предыдущий шаг",
    "restart": "Всплытие — возврат в начало маршрута",
}


@dataclass
class Step:
    name: str
    dist: str = "const"
    a: float = 1.0
    b: float = 0.0

    def mean(self) -> float:
        """Математическое ожидание времени шага (нормальный закон усечён в нуле)."""
        if self.dist == "const":
            return max(self.a, 0.0)
        if self.dist == "uniform":
            return (self.a + self.b) / 2
        if self.dist == "exp":
            return max(self.a, 0.0)
        if self.dist == "normal":
            mu, sigma = self.a, abs(self.b)
            if sigma == 0:
                return max(mu, 0.0)
            z = mu / sigma
            cdf = 0.5 * math.erfc(-z / math.sqrt(2))
            pdf = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
            return mu * cdf + sigma * pdf
        raise ValueError(f"неизвестный закон распределения: {self.dist}")

    def describe(self) -> str:
        if self.dist == "const":
            return f"{self.a:g}"
        if self.dist == "normal":
            return f"N({self.a:g}; {self.b:g})"
        if self.dist == "uniform":
            return f"R[{self.a:g}; {self.b:g}]"
        return f"Exp(ср. {self.a:g})"


@dataclass
class Route:
    name: str
    prob: float
    steps: list[int]

    def path(self) -> str:
        return " → ".join(str(s) for s in self.steps)


@dataclass
class Subtopic:
    name: str
    choice_prob: float
    p_error: float
    steps: list[Step] = field(default_factory=list)
    routes: list[Route] = field(default_factory=list)

    def check(self) -> list[str]:
        """Список ошибок в описании подтемы (пустой — всё в порядке)."""
        errors = []
        if not self.steps:
            errors.append("нет ни одного шага")
        if len(self.steps) > 10:
            errors.append("шагов больше 10")
        if not self.routes:
            errors.append("нет ни одного маршрута")
        if len(self.routes) > 10:
            errors.append("маршрутов больше 10")
        if not 0 <= self.p_error < 1:
            errors.append("вероятность ошибки должна быть в [0; 1)")
        for st in self.steps:
            if st.dist not in DISTRIBUTIONS:
                errors.append(f"шаг «{st.name}»: неизвестный закон {st.dist}")
            elif st.dist == "uniform" and st.b < st.a:
                errors.append(f"шаг «{st.name}»: у равномерного закона b < a")
            elif st.dist in ("const", "exp") and st.a < 0:
                errors.append(f"шаг «{st.name}»: отрицательное время")
        for r in self.routes:
            if not r.steps:
                errors.append(f"{r.name}: пустой маршрут")
            if len(r.steps) > 10:
                errors.append(f"{r.name}: длиннее 10 шагов")
            bad = [s for s in r.steps if not 1 <= s <= len(self.steps)]
            if bad:
                errors.append(f"{r.name}: нет шагов с номерами {bad}")
            if r.prob < 0:
                errors.append(f"{r.name}: отрицательная вероятность")
        total = sum(r.prob for r in self.routes)
        if self.routes and abs(total - 1) > 1e-6:
            errors.append(f"сумма вероятностей маршрутов = {total:.4g}, а не 1")
        return errors


@dataclass
class Theme:
    title: str
    subtopics: list[Subtopic]
    error_mode: str = "repeat"

    def check(self) -> list[str]:
        errors = []
        for i, sub in enumerate(self.subtopics, 1):
            errors += [f"Подтема {i}: {e}" for e in sub.check()]
        total = sum(s.choice_prob for s in self.subtopics)
        if abs(total - 1) > 1e-6:
            errors.append(f"сумма вероятностей выбора подтем = {total:.4g}, а не 1")
        return errors

    # --- файлы -----------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Theme":
        subs = []
        for s in d["subtopics"]:
            subs.append(Subtopic(
                name=s["name"],
                choice_prob=float(s["choice_prob"]),
                p_error=float(s.get("p_error", 0)),
                steps=[Step(**st) for st in s["steps"]],
                routes=[Route(r["name"], float(r["prob"]), [int(x) for x in r["steps"]])
                        for r in s["routes"]],
            ))
        return cls(title=d.get("title", ""), subtopics=subs,
                   error_mode=d.get("error_mode", "repeat"))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                              encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Theme":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
