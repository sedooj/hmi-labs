"""Генерация отчётов по ЛР1 и ЛР2 (.docx) с результатами моделирования.

Запуск из корня проекта:  .venv/bin/python report/make_report.py
Все эксперименты проводятся с фиксированным зерном генератора, поэтому
отчёт воспроизводим.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from hmi_lab.dialog_sim import (DialogSimulator, SampleStats, auto_k, histogram,
                                theory_mean_subtopic, theory_mean_theme)
from hmi_lab.efficiency_sim import EfficiencyModel, Lr2Params
from hmi_lab.gui import common  # noqa: F401 — общие настройки matplotlib
from hmi_lab.gui.common import ACCENT, ACCENT2
from hmi_lab.gui.lr2_tab import draw_lr2, draw_study, run_study
from hmi_lab.model import DISTRIBUTIONS, ERROR_MODES, Theme

SEED = 2026
N = 10_000
P_VALUES = [0.0, 0.3, 0.6, 0.9]
OUT = ROOT / "report"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)

theme = Theme.load(ROOT / "data" / "energy_dispatch.json")
S1, S2 = theme.subtopics


# --- оформление docx --------------------------------------------------------
def new_doc() -> Document:
    doc = Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    sec.left_margin, sec.right_margin = Cm(3), Cm(1.5)
    sec.top_margin = sec.bottom_margin = Cm(2)
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(13)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    st.paragraph_format.space_after = Pt(4)
    st.paragraph_format.line_spacing = 1.15
    for name, size in (("Heading 1", 15), ("Heading 2", 13)):
        h = doc.styles[name]
        h.font.name = "Times New Roman"
        h.font.size = Pt(size)
        h.font.bold = True
        h.font.color.rgb = None
        h.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
        h.paragraph_format.space_before = Pt(12)
        h.paragraph_format.space_after = Pt(6)
    return doc


def ru(text: str) -> str:
    """Десятичная запятая вместо точки: 0.25 → 0,25."""
    return re.sub(r"(?<=\d)\.(?=\d)", ",", text)


def para(doc, text="", bold=False, align=None, size=None, italic=False):
    text = ru(text)
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold, run.italic = bold, italic
    if size:
        run.font.size = Pt(size)
    if align:
        p.alignment = align
    else:
        p.paragraph_format.first_line_indent = Cm(1.0)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return p


def bullets(doc, items, numbered=False):
    for it in items:
        p = doc.add_paragraph(ru(it), style="List Number" if numbered else "List Bullet")
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def code(doc, text):
    for line in text.strip("\n").split("\n"):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        r = p.add_run(line or " ")
        r.font.name = "Courier New"
        r.font.size = Pt(10)


def table(doc, headers, rows, caption=None, widths=None, font=10):
    if caption:
        para(doc, caption, align=WD_ALIGN_PARAGRAPH.LEFT, italic=True, size=11)
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for c, h in enumerate(headers):
        cell = t.rows[0].cells[c]
        cell.text = ""
        r = cell.paragraphs[0].add_run(h)
        r.bold = True
        r.font.size = Pt(font)
    for row in rows:
        cells = t.add_row().cells
        for c, v in enumerate(row):
            cells[c].text = ""
            r = cells[c].paragraphs[0].add_run(ru(v if isinstance(v, str) else f"{v:.2f}"))
            r.font.size = Pt(font)
    if widths:
        for row in t.rows:
            for c, w in enumerate(widths):
                row.cells[c].width = Cm(w)
    doc.add_paragraph()
    return t


fig_no = {"n": 0}


def figure(doc, fig, name, caption, width=16):
    path = FIG / f"{name}.png"
    fig.savefig(path, dpi=200)
    plt.close(fig)
    doc.add_picture(str(path), width=Cm(width))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    fig_no["n"] += 1
    para(doc, f"Рисунок {fig_no['n']} — {caption}", align=WD_ALIGN_PARAGRAPH.CENTER, size=11)


def title_page(doc, number, title):
    for text, kw in (
        ("Министерство науки и высшего образования Российской Федерации", {}),
        ("Новосибирский государственный технический университет", {"bold": True}),
        ("Кафедра ________________________________", {}),
    ):
        para(doc, text, align=WD_ALIGN_PARAGRAPH.CENTER, **kw)
    for _ in range(7):
        doc.add_paragraph()
    para(doc, f"ЛАБОРАТОРНАЯ РАБОТА № {number}", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, size=15)
    para(doc, "по дисциплине «Интерфейсы человек–ЭВМ»", align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, f"«{title}»", bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    for _ in range(7):
        doc.add_paragraph()
    for text in ("Выполнил: студент гр. ________", "______________________________",
                 "Проверил: ______________________________"):
        para(doc, text, align=WD_ALIGN_PARAGRAPH.RIGHT)
    for _ in range(5):
        doc.add_paragraph()
    para(doc, "Новосибирск, 2026", align=WD_ALIGN_PARAGRAPH.CENTER)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def step_rows(sub):
    rows = []
    for i, st in enumerate(sub.steps, 1):
        p1 = DISTRIBUTIONS[st.dist][1]
        p2 = DISTRIBUTIONS[st.dist][2]
        params = f"{p1} = {st.a:g}" + (f"; {p2} = {st.b:g}" if p2 else "")
        rows.append([str(i), st.name, DISTRIBUTIONS[st.dist][0].lower(), params, f"{st.mean():.2f}"])
    return rows


def route_rows(sub):
    return [[r.name, f"{r.prob:g}", r.path(),
             f"{sum(sub.steps[s - 1].mean() for s in r.steps):.2f}"] for r in sub.routes]


def initial_data(doc, prefix=""):
    for k, sub in enumerate(theme.subtopics, 1):
        doc.add_heading(f"{prefix}Подтема {k}. {sub.name}", 2)
        para(doc, f"Вероятность выбора подтемы — {sub.choice_prob:g}. "
                  f"Вероятность ошибочного действия на шаге в базовом варианте — {sub.p_error:g}.")
        table(doc, ["№", "Шаг диалога", "Закон", "Параметры", "M[t], с"], step_rows(sub),
              caption=f"Таблица шагов подтемы {k}", widths=[1, 6.5, 3, 4, 1.8])
        table(doc, ["Маршрут", "Вероятность", "Последовательность шагов", "M[t] при P=0, с"],
              route_rows(sub), caption=f"Маршруты подтемы {k}", widths=[5.5, 2.2, 6, 2.6])


# =============================================================================
#                                    ЛР1
# =============================================================================
def lr1():
    fig_no["n"] = 0
    doc = new_doc()
    title_page(doc, 1, "Оценка временных характеристик диалога")

    doc.add_heading("1. Цель работы", 1)
    para(doc, "Познакомиться с методами оценки временных характеристик пользовательских "
              "интерфейсов и формированием функциональных требований к приложению; "
              "разработать имитационную модель, позволяющую оценивать время решения задачи "
              "пользователем диалоговой системы с альтернативной структурой диалога.")

    doc.add_heading("2. Описание исследуемой диалоговой системы", 1)
    para(doc, f"Объект исследования — {theme.title.lower()} (АРМ диспетчера РЭС). Тема диалога — "
              "оперативное управление распределительной сетью. Тема разбита на две подтемы:")
    bullets(doc, [f"подтема 1 — «{S1.name}»: диспетчер обрабатывает заявку на изменение "
                  "схемы питания (вывод линии в ремонт, перевод нагрузки и т. п.);",
                  f"подтема 2 — «{S2.name}»: диспетчер локализует повреждение и "
                  "восстанавливает электроснабжение потребителей после срабатывания защиты."])
    para(doc, "В каждой подтеме задано до 10 шагов диалога и до 10 маршрутов длиной не более "
              "10 шагов. Время шага — случайная величина с известным законом распределения "
              "(нормальным, равномерным, экспоненциальным) либо детерминированная величина, "
              "оценённая по методике GOMS (например, ввод команды телеуправления: "
              "M + P + B + K·n ≈ 4,2 с). Маршруты выбираются с разными вероятностями, подтемы — "
              "с заданными вероятностями выбора. Вероятность ошибочного действия P одинакова "
              "для всех шагов и не зависит от предыстории диалога.")

    doc.add_heading("3. Требования к приложению", 1)
    bullets(doc, [
        "ввод и редактирование графа диалога: шагов (название, закон распределения времени и "
        "его параметры), маршрутов (вероятность, последовательность шагов), вероятностей выбора "
        "подтем и вероятности ошибки; контроль корректности данных; сохранение и загрузка "
        "варианта в файл JSON;",
        "наглядное отображение графа подтемы (толщина дуги пропорциональна вероятности перехода);",
        "выбор процедуры обработки ошибок: переход в текущую вершину, возврат на предыдущий "
        "шаг, «всплытие» в начало маршрута;",
        "моделирование выборки объёмом N для подтемы 1, подтемы 2 и темы в целом при "
        "нескольких значениях P одновременно (по умолчанию 0; 0,3; 0,6; 0,9);",
        "вывод среднего времени, СКО, минимума, максимума и теоретического матожидания;",
        "построение гистограмм с начальным числом интервалов K = int(1 + 3,22·lg N) и "
        "возможностью задать K вручную без повторного моделирования; таблица частот.",
    ])

    doc.add_heading("4. Моделирующий алгоритм", 1)
    para(doc, "Одна реализация (решение задачи пользователем) моделируется так:")
    bullets(doc, [
        "Разыграть подтему k: случайное число u ~ R[0;1) сравнивается с накопленными "
        "вероятностями выбора подтем (метод обратной функции для дискретного закона).",
        "Тем же способом разыграть маршрут m в подтеме k по вероятностям маршрутов.",
        "Установить указатель i на первый шаг маршрута, время T = 0.",
        "Сгенерировать время исполнения шага s = m[i] по его закону: константа; "
        "N(μ, σ) с отсечением отрицательных значений; R[a, b]; Exp(1/среднее). "
        "Прибавить его к T.",
        "Разыграть ошибку: если u < P, действие ошибочно. Тогда при «переходе в текущую "
        "вершину» шаг повторяется (i не меняется), при «возврате» i := max(i−1, 0), при "
        "«всплытии» i := 0. Иначе i := i + 1.",
        "Повторять п. 4–5, пока не пройден последний шаг маршрута. T — время реализации.",
    ], numbered=True)
    para(doc, "Выборка из N реализаций обрабатывается: t̄ = ΣT/N, s = √(Σ(T − t̄)²/(N−1)), "
              "минимум и максимум; диапазон [min; max] делится на K равных интервалов, "
              "K = int(1 + 3,22·lg N).")
    para(doc, "Для проверки модели используются аналитические оценки. При переходе в текущую "
              "вершину число исполнений шага имеет геометрическое распределение со средним "
              "1/(1 − P), поэтому")
    code(doc, """
M[T_подтемы] = Σ_m p_m · Σ_(s∈m) M[t_s] / (1 − P)
M[T_темы]    = Σ_k q_k · M[T_подтемы k]""")
    para(doc, "При «всплытии» ожидаемое время прохождения первых j шагов маршрута "
              "E_j = (E_(j−1) + M[t_j]) / (1 − P), E_0 = 0, т. е. растёт как (1 − P)^(−n) с "
              "длиной маршрута n.")
    para(doc, "Фрагмент программной реализации (Python, модуль hmi_lab/dialog_sim.py):")
    code(doc, """
def run_route(self, sub, route_steps, p, mode):
    total, errors, i = 0.0, 0, 0
    while i < len(route_steps):
        total += self.step_time(sub.steps[route_steps[i] - 1])
        if p > 0 and self.rng.random() < p:      # ошибочное действие
            errors += 1
            if mode == "back":    i = max(i - 1, 0)
            elif mode == "restart": i = 0
            continue                               # repeat: остаёмся в вершине
        i += 1
    return total, errors""")

    doc.add_heading("5. Исходные данные контрольного примера", 1)
    para(doc, f"Процедура обработки ошибок — «{ERROR_MODES[theme.error_mode].lower()}». "
              f"Объём выборки N = {N:,}, K = int(1 + 3,22·lg N) = {auto_k(N)}. "
              f"Зерно генератора — {SEED}.".replace(",", " "))
    initial_data(doc, "5.")

    doc.add_heading("6. Результаты моделирования", 1)
    sim = DialogSimulator(theme, SEED)
    samples = {}
    for p in P_VALUES:
        for tg in ("sub0", "sub1", "theme"):
            samples[(tg, p)] = sim.sample(N, tg, p, "repeat")
    rows = []
    for p in P_VALUES:
        for tg, name, th in (("sub0", "Подтема 1", theory_mean_subtopic(S1, p)),
                             ("sub1", "Подтема 2", theory_mean_subtopic(S2, p)),
                             ("theme", "Тема", theory_mean_theme(theme, p))):
            st = SampleStats.of(samples[(tg, p)])
            rows.append([f"{p:g}", name, st.mean, th, abs(st.mean - th) / th * 100,
                         st.sd, st.min, st.max])
    rows = [[r[0], r[1], f"{r[2]:.1f}", f"{r[3]:.1f}", f"{r[4]:.2f}", f"{r[5]:.1f}",
             f"{r[6]:.1f}", f"{r[7]:.1f}"] for r in rows]
    doc.add_heading("6.1. Среднее время выполнения подтем и темы", 2)
    table(doc, ["P", "Объект", "t̄, с", "M[t] теор., с", "Откл., %", "СКО, с", "min, с", "max, с"],
          rows, caption="Результаты моделирования (переход в текущую вершину)",
          widths=[1.2, 2.6, 2, 2.4, 1.8, 2, 2, 2.2])

    fig, ax = plt.subplots(figsize=(7.5, 3.6), layout="constrained")
    ps = np.linspace(0, 0.9, 19)
    for sub, name, c in ((S1, "подтема 1", ACCENT), (S2, "подтема 2", ACCENT2)):
        ax.plot(ps, [theory_mean_subtopic(sub, p) for p in ps], color=c, label=f"{name} (теория)")
    ax.plot(ps, [theory_mean_theme(theme, p) for p in ps], color="black", label="тема (теория)")
    for tg, c in (("sub0", ACCENT), ("sub1", ACCENT2), ("theme", "black")):
        ax.plot(P_VALUES, [samples[(tg, p)].mean() for p in P_VALUES], "o", color=c, ms=5)
    ax.set_yscale("log")
    ax.set_xlabel("вероятность ошибки P")
    ax.set_ylabel("среднее время, с")
    ax.legend(fontsize=8, title="точки — моделирование", title_fontsize=8)
    figure(doc, fig, "lr1_mean_vs_p", "Зависимость среднего времени от вероятности ошибки")

    doc.add_heading("6.2. Гистограммы времени решения задачи", 2)
    fig, axes = plt.subplots(2, 2, figsize=(8, 6.2), layout="constrained")
    k = auto_k(N)
    for ax, p in zip(axes.ravel(), P_VALUES):
        x = samples[("theme", p)]
        counts, edges = histogram(x, k)
        m = x.mean()
        colors = [ACCENT2 if lo <= m < hi else ACCENT for lo, hi in zip(edges, edges[1:])]
        ax.bar(edges[:-1], counts / N, width=np.diff(edges), align="edge", color=colors,
               edgecolor="white", lw=0.5)
        ax.axvline(m, color=ACCENT2, ls="--", lw=1.4, label=f"t̄ = {m:.1f} с")
        ax.set_title(f"P = {p:g}")
        ax.set_xlabel("время, с")
        ax.set_ylabel("отн. частота")
        ax.legend(fontsize=8)
    figure(doc, fig, "lr1_hist", f"Гистограммы времени решения задачи (тема, N = {N}, K = {k})")

    x = samples[("theme", 0.0)]
    counts, edges = histogram(x, k)
    table(doc, ["№", "Интервал, с", "n", "n/N"],
          [[str(i + 1), f"{lo:.1f} – {hi:.1f}", str(c), f"{c / N:.4f}"]
           for i, (lo, hi, c) in enumerate(zip(edges, edges[1:], counts))],
          caption="Таблица частот для темы при P = 0", widths=[1.2, 5, 2, 2.5])

    doc.add_heading("6.3. Сравнение процедур обработки ошибок", 2)
    rows = []
    cmp = {}
    for mode in ERROR_MODES:
        s = DialogSimulator(theme, SEED)
        for p in (0.1, 0.3, 0.5):
            x = s.sample(N, "theme", p, mode)
            cmp[(mode, p)] = x.mean()
        rows.append([ERROR_MODES[mode]] + [f"{cmp[(mode, p)]:.1f}" for p in (0.1, 0.3, 0.5)])
    table(doc, ["Процедура", "P = 0,1", "P = 0,3", "P = 0,5"], rows,
          caption="Среднее время решения задачи (тема), с", widths=[8, 2.5, 2.5, 2.5])

    doc.add_heading("7. Выводы", 1)
    t0, t9 = samples[("theme", 0.0)].mean(), samples[("theme", 0.9)].mean()
    s0, s9 = samples[("theme", 0.0)].std(), samples[("theme", 0.9)].std()
    ratio_sub = samples[("sub1", 0.0)].mean() / samples[("sub0", 0.0)].mean()
    max_dev = max(float(r[4]) for r in [[0, 0, 0, 0, abs(samples[(tg, p)].mean() - th) / th * 100]
                  for p in P_VALUES for tg, th in (("sub0", theory_mean_subtopic(S1, p)),
                                                   ("sub1", theory_mean_subtopic(S2, p)),
                                                   ("theme", theory_mean_theme(theme, p)))])
    bullets(doc, [
        f"Разработана имитационная модель и приложение с графическим интерфейсом для оценки "
        f"временных характеристик диалога. Средние, полученные моделированием, отличаются от "
        f"аналитических не более чем на {max_dev:.1f} % при N = {N}, что подтверждает "
        f"корректность модели.",
        f"При безошибочной работе (P = 0) среднее время решения задачи составляет {t0:.1f} с; "
        f"подтема восстановления в {ratio_sub:.1f} раза длительнее подтемы переключения, но "
        f"выбирается реже (вероятность {S2.choice_prob:g}), поэтому основной вклад в среднее "
        f"время темы даёт подтема 1.",
        f"С ростом P среднее время растёт как 1/(1 − P): при P = 0,9 оно равно {t9:.1f} с, т. е. "
        f"в {t9 / t0:.1f} раза больше, чем при P = 0. Одновременно растёт разброс: СКО "
        f"увеличивается с {s0:.1f} до {s9:.1f} с.",
        "При P = 0 гистограмма двухмодальна: основной максимум (40–60 с) образуют маршруты "
        "подтемы 1, второй максимум в области 120–150 с — маршруты подтемы 2. С ростом P "
        "распределение «размывается», второй максимум исчезает, появляется длинный правый "
        "хвост, характерный для суммы геометрически распределённого числа слагаемых.",
        f"Процедура обработки ошибок сильно влияет на время: при P = 0,3 «возврат на шаг назад» "
        f"увеличивает среднее время в {cmp[('back', 0.3)] / cmp[('repeat', 0.3)]:.1f} раза, а "
        f"«всплытие» — в {cmp[('restart', 0.3)] / cmp[('repeat', 0.3)]:.1f} раза по сравнению "
        f"с переходом в текущую вершину. Для длинных маршрутов и ошибкоопасных шагов "
        f"предпочтительна обработка ошибок с возвратом в текущую вершину.",
    ])
    path = OUT / "Отчёт_ЛР1.docx"
    doc.save(path)
    return path


# =============================================================================
#                                    ЛР2
# =============================================================================
def lr2():
    fig_no["n"] = 0
    doc = new_doc()
    title_page(doc, 2, "Оценка эффективности человеко-машинной системы")
    base = Lr2Params(seed=SEED)

    doc.add_heading("1. Цель работы", 1)
    para(doc, "Построение и исследование модели оценки по проектным данным эффективности "
              "функционирования человеко-машинной системы.")

    doc.add_heading("2. Характеристика исследуемой системы", 1)
    para(doc, "Исследуется система оперативно-диспетчерского управления районными электрическими "
              "сетями: объект управления (распределительная сеть) → подсистема сбора данных "
              "(телеметрия, телесигнализация) → АРМ диспетчера (подсистема переработки "
              "информации) → человек-оператор (диспетчер) → подсистема выдачи команд "
              "(телеуправление коммутационными аппаратами) → объект управления.")
    para(doc, "Диспетчер решает две задачи, каждой из которых в диалоговой системе АРМ "
              "соответствует своя подтема (граф диалога из ЛР1):")
    bullets(doc, [
        f"задача 1 — выработка регулирующих воздействий по заявкам объекта (подтема «{S1.name}»);",
        f"задача 2 — восстановление функционирования системы после отказа (подтема «{S2.name}»).",
    ])
    para(doc, "Известно из проекта: заявки поступают в случайные моменты времени "
              "(пуассоновский поток интенсивности λ); наработка на отказ — случайная величина "
              "с заданным законом распределения; при отказе все заявки, ожидающие обработки или "
              "обрабатываемые, аннулируются; задержка выдачи регулирующего воздействия приводит к "
              "потерям с удельной величиной R1 на единицу времени задержки; простой системы — к "
              "потерям с удельной величиной R2; ошибки обрабатываются переходом в текущую вершину "
              "графа диалога.")

    doc.add_heading("3. Показатель оценки качества функционирования", 1)
    para(doc, "В качестве показателя эффективности принимаются средние удельные потери системы "
              "за интервал наблюдения T:")
    code(doc, """
       R1 · Σ_i τ_i  +  R2 · Σ_j θ_j
  Q = ───────────────────────────────  [у.е./с],
                    T""")
    para(doc, "где τ_i — задержка выдачи регулирующего воздействия по i-й заявке (от момента "
              "поступления до окончания обработки; для аннулированной заявки — до окончания "
              "восстановления системы, так как всё это время воздействие не выдано); θ_j — "
              "длительность j-го восстановления (простоя). Чем меньше Q, тем эффективнее система. "
              "Дополнительно оцениваются коэффициент готовности Kг = 1 − Σθ/T, средняя задержка, "
              "загрузка диспетчера и число аннулированных заявок. Показатель оценивается по M "
              "независимым прогонам модели; для него строится 95-процентный доверительный "
              "интервал Q̄ ± 1,96·s/√M.")

    doc.add_heading("4. Моделирующий алгоритм", 1)
    bullets(doc, [
        "t := 0, очередь пуста; разыгрывается момент прихода первой заявки "
        "a₁ = −ln(1 − u)/λ.",
        "Разыгрывается наработка до отказа X (экспоненциальный закон X = −ln(1 − u)·T₀ или "
        "закон Вейбулла с тем же средним T₀); момент отказа t_отк := t + X.",
        "Период работы. Пока диспетчер свободен раньше t_отк: все заявки с моментом прихода, "
        "не превышающим момент освобождения диспетчера, ставятся в очередь; первая заявка из "
        "очереди берётся в обработку; время обработки — одна реализация подтемы 1 (модель "
        "ЛР1). Если обработка закончилась до отказа — заявка обслужена, её задержка "
        "τ = окончание − приход. Иначе обработка прерывается отказом.",
        "Отказ. Время восстановления θ — одна реализация подтемы 2 (модель ЛР1). Все заявки в "
        "очереди и на обработке аннулируются, их задержка τ = (t_отк + θ) − приход. Заявки, "
        "поступившие во время восстановления, ждут в очереди.",
        "t := t_отк + θ; если t < T — перейти к п. 2.",
        "Вычислить L1 = R1·Στ, L2 = R2·Σθ, Q = (L1 + L2)/T.",
        "Повторить п. 1–6 M раз, вычислить среднее и доверительный интервал.",
    ], numbered=True)

    doc.add_heading("5. Исходные данные для имитационных экспериментов", 1)
    table(doc, ["Параметр", "Значение"], [
        ["Интенсивность потока заявок λ", f"{base.lam_per_hour:g} 1/ч"],
        ["Средняя наработка на отказ T₀", f"{base.mtbf_hours:g} ч"],
        ["Закон наработки на отказ", "экспоненциальный"],
        ["Удельные потери от задержки R1", f"{base.r1:g} у.е./с"],
        ["Удельные потери от простоя R2", f"{base.r2:g} у.е./с"],
        ["Вероятность ошибки диспетчера P (подтемы 1 и 2)", f"{base.p1:g}"],
        ["Темп работы диспетчера (множитель времени шагов)", f"{base.time_scale:g}"],
        ["Интервал моделирования T", f"{base.horizon_hours:g} ч (30 суток)"],
        ["Число прогонов M", f"{base.runs}"],
    ], caption="Параметры системы", widths=[10, 5])
    para(doc, "Графы диалога подтем — из ЛР1:")
    initial_data(doc, "5.")

    doc.add_heading("6. Результаты моделирования", 1)
    res = EfficiencyModel(theme, base).run()
    names = [("q", "Q, у.е./с"), ("q1", "в т. ч. от задержек, у.е./с"),
             ("q2", "в т. ч. от простоя, у.е./с"), ("availability", "Коэффициент готовности"),
             ("mean_delay", "Средняя задержка, с"), ("utilization", "Загрузка диспетчера"),
             ("arrived", "Поступило заявок"), ("annulled", "Аннулировано заявок"),
             ("failures", "Число отказов")]
    rows = []
    for a, n in names:
        m, c = res.mean_ci(a)
        rows.append([n, f"{m:.4g}", f"± {c:.2g}"])
    doc.add_heading("6.1. Базовый вариант", 2)
    table(doc, ["Показатель", "Среднее", "95% ДИ"], rows,
          caption="Результаты для базового варианта", widths=[8, 3.5, 3.5])
    fig = plt.figure(figsize=(9, 3.6), layout="constrained")
    draw_lr2(fig, res)
    figure(doc, fig, "lr2_base", "Структура потерь и динамика очереди заявок")

    studies = [
        ("p", "P ошибки диспетчера (в обеих подтемах)", np.linspace(0, 0.6, 7)),
        ("time_scale", "Темп работы диспетчера (×время шагов)", np.linspace(0.5, 2.5, 9)),
        ("p2", "P ошибки в подтеме 2 (восстановление)", np.linspace(0, 0.9, 10)),
    ]
    sres = {}
    for idx, (key, title, values) in enumerate(studies, 2):
        doc.add_heading(f"6.{idx}. Влияние параметра: {title.lower()}", 2)
        data = run_study(theme, Lr2Params(seed=SEED, runs=10), key, values)
        sres[key] = data
        table(doc, ["Значение", "Q", "Q₁ (задержки)", "Q₂ (простой)", "Задержка, с", "Загрузка", "Kг"],
              [[f"{v:g}", f"{r.mean_ci('q')[0]:.3f}", f"{r.mean_ci('q1')[0]:.3f}",
                f"{r.mean_ci('q2')[0]:.3f}", f"{r.mean_ci('mean_delay')[0]:.1f}",
                f"{r.mean_ci('utilization')[0]:.3f}", f"{r.mean_ci('availability')[0]:.4f}"]
               for v, r in data], caption="Результаты исследования (M = 10 прогонов на точку)",
              widths=[2, 2, 2.4, 2.4, 2.4, 2, 2])
        fig = plt.figure(figsize=(8, 5.5), layout="constrained")
        draw_study(fig, title, data)
        figure(doc, fig, f"lr2_study_{key}", f"Влияние параметра «{title}» на эффективность")

    doc.add_heading("7. Выводы", 1)
    q, _ = res.mean_ci("q")
    q1, _ = res.mean_ci("q1")
    sp = {v: r for v, r in sres["p"]}
    st = {v: r for v, r in sres["time_scale"]}
    s2 = {v: r for v, r in sres["p2"]}
    g = lambda d, v, a="q": d[min(d, key=lambda x: abs(x - v))].mean_ci(a)[0]  # noqa: E731
    bullets(doc, [
        "Разработан показатель эффективности — средние удельные потери Q, учитывающий потери от "
        "задержек выдачи регулирующих воздействий и от простоя системы, и моделирующий "
        "алгоритм, использующий модель диалога из ЛР1 для расчёта времени обработки заявок "
        "и времени восстановления.",
        f"В базовом варианте Q = {q:.3f} у.е./с, из них {q1 / q * 100:.0f} % — потери от задержек "
        f"регулирования; коэффициент готовности {res.mean_ci('availability')[0]:.4f}, загрузка "
        f"диспетчера {res.mean_ci('utilization')[0]:.2f}. Система чувствительнее всего к "
        f"качеству решения задачи 1, т. к. она решается многократно.",
        f"Вероятность ошибки диспетчера влияет на эффективность нелинейно: при росте P от 0 до "
        f"0,3 потери увеличиваются в {g(sp, 0.3) / g(sp, 0):.1f} раза, а при P = 0,6 — в "
        f"{g(sp, 0.6) / g(sp, 0):.0f} раз: загрузка диспетчера приближается к 1 "
        f"({g(sp, 0.6, 'utilization'):.2f}), очередь заявок неограниченно растёт.",
        f"Аналогично влияет темп работы: замедление диспетчера вдвое увеличивает Q в "
        f"{g(st, 2.0) / g(st, 1.0):.1f} раза, ускорение вдвое уменьшает Q в "
        f"{g(st, 1.0) / g(st, 0.5):.1f} раза. Поэтому для АРМ важны сокращение числа шагов "
        f"в частых маршрутах подтемы 1 и подсказки, снижающие вероятность ошибки.",
        f"Ошибки при восстановлении (подтема 2) влияют слабее, пока P < 0,5: Q растёт с "
        f"{g(s2, 0):.3f} до {g(s2, 0.5):.3f} у.е./с, но при P = 0,9 потери от простоя "
        f"возрастают почти в {g(s2, 0.9, 'q2') / g(s2, 0, 'q2'):.0f} раз, а Kг падает до "
        f"{g(s2, 0.9, 'availability'):.3f}.",
        "Модель позволяет по проектным данным (граф диалога, характеристики потоков заявок и "
        "отказов, удельные потери) сравнивать варианты интерфейса АРМ и требования к "
        "подготовке операторов до создания системы.",
    ])
    path = OUT / "Отчёт_ЛР2.docx"
    doc.save(path)
    return path


if __name__ == "__main__":
    print(lr1())
    print(lr2())
