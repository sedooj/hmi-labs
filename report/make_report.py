"""Генерация отчётов по ЛР1 и ЛР2 (.docx и .pdf).

Запуск из корня проекта:   .venv/bin/python report/make_report.py

Оформление — по образцу кафедры: поля 2 см, Times New Roman 14 пт, межстрочный
интервал 1,25, номер страницы внизу по центру (на титульном листе не ставится),
содержание с номерами страниц.

Номера страниц в содержании настоящие: документ собирается, переводится в PDF
через Microsoft Word (пакет docx2pdf), по PDF определяется, на какой странице
начинается каждый раздел, и документ собирается ещё раз с этими номерами.
Без Word (флаг --no-pdf) номера в содержании не проставляются.

Студенты и преподаватель — в STUDENTS / TEACHER ниже.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.section import WD_SECTION  # noqa: E402,F401
from docx.enum.table import WD_TABLE_ALIGNMENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT, WD_TAB_LEADER  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt, RGBColor  # noqa: E402

from hmi_lab import plots  # noqa: E402
from hmi_lab.dialog_sim import (DialogSimulator, SampleStats, auto_k, histogram,  # noqa: E402
                                theory_mean_subtopic, theory_mean_theme)
from hmi_lab.efficiency_sim import EfficiencyModel, Lr2Params  # noqa: E402
from hmi_lab.model import DISTRIBUTIONS, ERROR_MODES, Theme  # noqa: E402

# ---------------------------------------------------------------------------
STUDENTS = ["Герасимов С. П.", "Обеленец П. В.", "Дементьев А. А.", "Ненашкин В. Д."]
GROUP = "АВТ-313"
FACULTY = "АВТФ"
TEACHER = "Терещенко Петр Васильевич"
YEAR = "2026"
SEED = 2026
N = 10_000
P_VALUES = [0.0, 0.3, 0.6, 0.9]
OUT = ROOT / "report"
FIG = OUT / "figures"
BUILD = OUT / "_build"
FONT = "Times New Roman"
FIG.mkdir(parents=True, exist_ok=True)
BUILD.mkdir(parents=True, exist_ok=True)

theme = Theme.load(ROOT / "data" / "variant.json")
S1, S2 = theme.subtopics
plots.print_style()


def ru(text: str) -> str:
    """Десятичная запятая: 0.25 → 0,25."""
    return re.sub(r"(?<=\d)\.(?=\d)", ",", text)


def num(x: float, spec: str = ".2f") -> str:
    return ru(format(x, spec))


# =============================================================================
#                         Построитель документа
# =============================================================================
class Report:
    LINE = 1.25
    INDENT = Cm(1.25)
    WIDTH_CM = 17.0  # 21 − 2 − 2

    def __init__(self, toc_pages: dict | None):
        self.doc = Document()
        self.toc_pages = toc_pages or {}
        self.toc: list[str] = []
        self.sec = 0
        self.sub = 0
        self.tables = 0
        self.figures = 0
        self.formulas = 0
        self._setup()

    # --- стили -------------------------------------------------------------
    @staticmethod
    def _font(style_or_run, size=14, bold=None):
        f = style_or_run.font
        f.name = FONT
        f.size = Pt(size)
        f.color.rgb = RGBColor(0, 0, 0)
        if bold is not None:
            f.bold = bold
        el = style_or_run.element if hasattr(style_or_run, "element") else style_or_run._element
        rpr = el.get_or_add_rPr()
        fonts = rpr.find(qn("w:rFonts"))
        if fonts is None:
            fonts = OxmlElement("w:rFonts")
            rpr.insert(0, fonts)
        for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            fonts.set(qn(attr), FONT)
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            fonts.attrib.pop(qn(attr), None)  # иначе Word берёт шрифт темы (Calibri)

    def _setup(self):
        sec = self.doc.sections[0]
        sec.page_width, sec.page_height = Cm(21), Cm(29.7)
        for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
            setattr(sec, side, Cm(2))
        sec.header_distance = sec.footer_distance = Cm(1.25)

        normal = self.doc.styles["Normal"]
        self._font(normal)
        pf = normal.paragraph_format
        pf.line_spacing = self.LINE
        pf.space_before = pf.space_after = Pt(0)
        pf.first_line_indent = self.INDENT
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        pf.widow_control = True

        for name in ("Heading 1", "Heading 2"):
            h = self.doc.styles[name]
            self._font(h, 14, bold=True)
            h.font.italic = False
            hf = h.paragraph_format
            hf.line_spacing = self.LINE
            hf.first_line_indent = self.INDENT
            hf.left_indent = Cm(0)
            hf.alignment = WD_ALIGN_PARAGRAPH.LEFT
            hf.space_before = Pt(12)
            hf.space_after = Pt(6)
            hf.keep_with_next = True
        for name in ("Table Grid",):
            self._font(self.doc.styles[name])

        # номер страницы внизу по центру, на титульном листе — нет
        sec.different_first_page_header_footer = True
        p = sec.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        run = p.add_run()
        self._font(run)
        for kind, text in (("begin", None), (None, "PAGE"), ("separate", None), (None, "1"),
                           ("end", None)):
            if kind:
                fc = OxmlElement("w:fldChar")
                fc.set(qn("w:fldCharType"), kind)
                run._r.append(fc)
            elif text == "PAGE":
                it = OxmlElement("w:instrText")
                it.set(qn("xml:space"), "preserve")
                it.text = "PAGE"
                run._r.append(it)
            else:
                t = OxmlElement("w:t")
                t.text = text
                run._r.append(t)

    # --- базовые элементы ---------------------------------------------------
    def para(self, text: str = "", *, align=None, indent=True, bold=False, italic=False,
             keep=False, line=None, after=0, before=0, markup=True):
        p = self.doc.add_paragraph()
        if align is not None:
            p.alignment = align
        if not indent:
            p.paragraph_format.first_line_indent = Cm(0)
        if keep:
            p.paragraph_format.keep_with_next = True
        if line is not None:
            p.paragraph_format.line_spacing = line
        p.paragraph_format.space_after = Pt(after)
        p.paragraph_format.space_before = Pt(before)
        if text:
            self._runs(p, ru(text) if markup else text, bold, italic)
        return p

    def _runs(self, p, text, bold=False, italic=False):
        """Мини-разметка: _{…} — нижний индекс, ^{…} — верхний, **…** — жирный."""
        for part in re.split(r"(_\{[^}]*\}|\^\{[^}]*\}|\*\*[^*]+\*\*)", text):
            if not part:
                continue
            if part.startswith("_{"):
                r = p.add_run(part[2:-1])
                r.font.subscript = True
            elif part.startswith("^{"):
                r = p.add_run(part[2:-1])
                r.font.superscript = True
            elif part.startswith("**"):
                r = p.add_run(part[2:-2])
                r.bold = True
            else:
                r = p.add_run(part)
            if bold:
                r.bold = True
            if italic:
                r.italic = True

    def text(self, *paragraphs: str):
        for t in paragraphs:
            self.para(t)

    def items(self, items: list[str], numbered: bool = False, end: str = ";"):
        """Перечисление: «– текст;» или «1) текст;», последний пункт — с точкой."""
        for i, it in enumerate(items, 1):
            mark = f"{i}) " if numbered else "– "
            tail = "." if i == len(items) else end
            body = it.rstrip(".;")
            self.para(mark + body + tail)

    def page_break(self):
        p = self.doc.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(0)
        p.add_run().add_break(WD_BREAK.PAGE)

    # --- заголовки ----------------------------------------------------------
    def section(self, title: str):
        self.sec += 1
        self.sub = 0
        text = f"{self.sec} {title}"
        self.doc.add_paragraph(text, style="Heading 1")
        self.toc.append(text)

    def subsection(self, title: str):
        self.sub += 1
        self.doc.add_paragraph(f"{self.sec}.{self.sub} {title}", style="Heading 2")

    def unnumbered(self, title: str):
        """«Список источников», «Приложение А …» — с новой страницы, по центру."""
        self.page_break()
        p = self.doc.add_paragraph(title, style="Heading 1")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        self.toc.append(title)

    # --- формулы, таблицы, рисунки -----------------------------------------
    def formula(self, expr: str) -> int:
        self.formulas += 1
        p = self.para(indent=False, before=6, after=6)
        ts = p.paragraph_format.tab_stops
        ts.add_tab_stop(Cm(self.WIDTH_CM / 2), WD_TAB_ALIGNMENT.CENTER)
        ts.add_tab_stop(Cm(self.WIDTH_CM), WD_TAB_ALIGNMENT.RIGHT)
        p.add_run("\t")
        self._runs(p, ru(expr))
        p.add_run(f"\t({self.formulas})")
        return self.formulas

    def where(self, lines: list[str]):
        for i, line in enumerate(lines):
            self.para(("где " if i == 0 else "") + line + (";" if i < len(lines) - 1 else "."),
                      indent=False)

    def table(self, caption: str, headers: list[str], rows: list[list[str]],
              widths: list[float], align: list[str] | None = None) -> int:
        self.tables += 1
        self.para(f"Таблица {self.tables} – {caption}", indent=False, keep=True,
                  align=WD_ALIGN_PARAGRAPH.LEFT, before=6)
        t = self.doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        align = align or ["l"] + ["c"] * (len(headers) - 1)

        def fill(cells, values, header=False):
            for c, v in enumerate(values):
                cell = cells[c]
                cell.width = Cm(widths[c])
                p = cell.paragraphs[0]
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.keep_with_next = header
                p.alignment = (WD_ALIGN_PARAGRAPH.CENTER if header or align[c] == "c"
                               else WD_ALIGN_PARAGRAPH.LEFT)
                self._runs(p, ru(str(v)), bold=header)

        fill(t.rows[0].cells, headers, header=True)
        trpr = t.rows[0]._tr.get_or_add_trPr()
        th = OxmlElement("w:tblHeader")
        th.set(qn("w:val"), "true")
        trpr.append(th)
        for row in rows:
            fill(t.add_row().cells, row)
        self.keep_together(t)
        self.para(line=1.0)  # отступ после таблицы
        return self.tables

    @staticmethod
    def keep_together(t):
        """Таблица целиком на одной странице: строки не делятся и держатся вместе."""
        rows = t.rows
        for i, row in enumerate(rows):
            trpr = row._tr.get_or_add_trPr()
            cs = OxmlElement("w:cantSplit")
            cs.set(qn("w:val"), "true")
            trpr.append(cs)
            if i < len(rows) - 1:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        p.paragraph_format.keep_with_next = True

    def figure(self, path: Path, caption: str, width: float = 16.5) -> int:
        self.figures += 1
        p = self.para(indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, keep=True, before=6,
                      line=1.0)
        p.add_run().add_picture(str(path), width=Cm(width))
        self.para(f"Рисунок {self.figures} – {caption}", indent=False,
                  align=WD_ALIGN_PARAGRAPH.CENTER, after=6)
        return self.figures

    # --- титульный лист и содержание ------------------------------------------
    def title_page(self, number: int, title: str):
        c = WD_ALIGN_PARAGRAPH.CENTER

        def line(text="", bold=False):
            return self.para(text, align=c, indent=False, bold=bold, line=1.0, markup=False)

        line("МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ РФ")
        line()
        line("ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ БЮДЖЕТНОЕ")
        line("ОБРАЗОВАТЕЛЬНОЕ УЧРЕЖДЕНИЕ")
        line("ВЫСШЕГО ОБРАЗОВАНИЯ")
        line("«НОВОСИБИРСКИЙ ГОСУДАРСТВЕННЫЙ ТЕХНИЧЕСКИЙ УНИВЕРСИТЕТ»")
        line("_" * 63)
        line("Кафедра автоматизированных систем управления")
        for _ in range(5):
            line()
        line("ОТЧЁТ")
        line(f"по ЛАБОРАТОРНОЙ РАБОТЕ №{number}")
        line(f"«{title}»")
        line("по дисциплине: «Интерфейсы человек–ЭВМ»")
        for _ in range(4):
            line()

        t = self.doc.add_table(rows=1, cols=2)
        t.autofit = False
        tblpr = t._tbl.tblPr
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            e = OxmlElement(f"w:{edge}")
            e.set(qn("w:val"), "nil")
            borders.append(e)
        tblpr.append(borders)
        left = ["Выполнили студенты:", *STUDENTS, f"гр. {GROUP}, {FACULTY}", "",
                f"«___» __________ {YEAR} г.", "_________________", "(подпись)"]
        right = ["Проверил:", *TEACHER.split(" ", 1), "", "«___» __________ 20__ г.", "",
                 "_________________", "(подпись)"]
        cells = t.rows[0].cells
        for ci, (cell, lines, width) in enumerate(((cells[0], left, 9.4), (cells[1], right, 7.6))):
            cell.width = Cm(width)
            for i, text in enumerate(lines):
                p = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.line_spacing = 1.0
                p.paragraph_format.left_indent = Cm(1.25) if ci == 0 else Cm(0)
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                if text:
                    p.add_run(text)
        for _ in range(3):
            line()
        line(f"Новосибирск {YEAR}")
        self.page_break()

    def toc_placeholder(self):
        p = self.para("Содержание", align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, bold=True,
                      after=6)
        self._toc_anchor = p

    def finish_toc(self):
        """Строки содержания вставляются после заголовка «Содержание»."""
        anchor = self._toc_anchor._p
        new = []
        for title in self.toc:
            p = self.doc.add_paragraph()
            pf = p.paragraph_format
            pf.first_line_indent = Cm(0)
            pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
            pf.tab_stops.add_tab_stop(Cm(self.WIDTH_CM), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            page = self.toc_pages.get(title, "")
            p.add_run(f"{title}\t{page}")
            new.append(p._p)
        # перенести созданные абзацы сразу за «Содержание»
        for el in reversed(new):
            anchor.addnext(el)
        # разрыв страницы после содержания
        br = OxmlElement("w:p")
        r = OxmlElement("w:r")
        b = OxmlElement("w:br")
        b.set(qn("w:type"), "page")
        r.append(b)
        br.append(r)
        new[-1].addnext(br)

    def save(self, path: Path):
        self.finish_toc()
        self.doc.save(path)


# =============================================================================
#                                Эксперименты
# =============================================================================
def compute_lr1() -> dict:
    sim = DialogSimulator(theme, SEED)
    samples = {}
    for p in P_VALUES:  # тот же порядок, что в программе, — одинаковые числа
        for tg in ("sub0", "sub1", "theme"):
            samples[(tg, p)] = sim.sample(N, tg, p, "repeat")
    modes = {}
    for mode in ERROR_MODES:
        s = DialogSimulator(theme, SEED)
        for p in (0.1, 0.2, 0.3):
            x = s.sample(N, "theme", p, mode)
            modes[(mode, p)] = (float(x.mean()), s.unfinished)
    return {"samples": samples, "modes": modes}


def compute_lr2() -> dict:
    base = Lr2Params(seed=SEED)
    res = EfficiencyModel(theme, base).run()
    study_base = Lr2Params(seed=SEED, runs=10)
    studies = {
        "p": plots.run_study(theme, study_base, "p", np.linspace(0, 0.6, 7)),
        "time_scale": plots.run_study(theme, study_base, "time_scale", np.linspace(0.5, 2.5, 9)),
        "p2": plots.run_study(theme, study_base, "p2", np.linspace(0, 0.9, 10)),
    }
    return {"base": base, "res": res, "studies": studies}


def screenshots():
    r = subprocess.run([sys.executable, str(OUT / "screenshots.py"), str(SEED), str(FIG)],
                       capture_output=True, text=True)
    if "screenshots ok" not in r.stdout:
        print(r.stdout, r.stderr)
        raise SystemExit("не удалось снять скриншоты программы")


# =============================================================================
#                         Общие фрагменты отчётов
# =============================================================================
def step_rows(sub):
    rows = []
    for i, st in enumerate(sub.steps, 1):
        if st.dist == "const":
            params = f"t = {st.a:g}"
        elif st.dist == "normal":
            params = f"μ = {st.a:g}; σ = {st.b:g}"
        elif st.dist == "uniform":
            params = f"a = {st.a:g}; b = {st.b:g}"
        else:
            params = f"среднее {st.a:g}"
        rows.append([str(i), DISTRIBUTIONS[st.dist][0].replace(" (GOMS)", ""), params,
                     num(st.mean(), ".1f")])
    return rows


def route_rows(sub):
    return [[r.name, f"{r.prob:g}", " – ".join(map(str, r.steps)),
             num(sum(sub.steps[s - 1].mean() for s in r.steps), ".1f")] for r in sub.routes]


def subtopic_tables(rep: Report, k: int, sub):
    rep.table(f"Шаги подтемы {k}",
              ["Шаг", "Закон распределения времени", "Параметры, с", "M[t], с"], step_rows(sub),
              [2.0, 6.0, 6.0, 3.0], ["c", "l", "l", "c"])
    rep.table(f"Маршруты подтемы {k}",
              ["Маршрут", "Вероят-ность", "Последовательность шагов", "M[t] при P = 0, с"],
              route_rows(sub), [3.0, 3.0, 7.8, 3.2], ["c", "c", "l", "c"])


def sources(rep: Report, extra: list[str] = ()):
    rep.unnumbered("Список использованных источников")
    lst = [
        "Методические указания к лабораторным работам 1 и 2 по дисциплине «Интерфейсы "
        "человек–ЭВМ». – Новосибирск : НГТУ.",
        "Раскин Д. Интерфейс: новые направления в проектировании компьютерных систем / "
        "Д. Раскин. – СПб. : Символ-Плюс, 2004. – 272 с.",
        "Card S. K., Moran T. P., Newell A. The Psychology of Human-Computer Interaction. – "
        "Hillsdale : Lawrence Erlbaum Associates, 1983. – 469 p.",
        "Вентцель Е. С. Теория вероятностей / Е. С. Вентцель. – М. : Высшая школа, 2006.",
        *extra,
        "Qt for Python (PySide6) : документация [Электронный ресурс]. – URL: "
        "https://doc.qt.io/qtforpython-6/ (дата обращения: 18.11.2026).",
        "Matplotlib : документация [Электронный ресурс]. – URL: https://matplotlib.org/stable/ "
        "(дата обращения: 18.11.2026).",
    ]
    for i, s in enumerate(lst, 1):
        rep.para(f"{i}. {s}", markup=False)


def appendix_files(rep: Report):
    rep.unnumbered("Приложение А Файлы проекта")
    rep.para("Исходный код программы и данные варианта находятся в репозитории проекта. "
             "Назначение файлов приведено в таблице А.1.")
    rep.tables_saved = rep.tables
    rows = [
        ["main.py", "запуск программы"],
        ["run.sh", "запуск с автоматической установкой зависимостей"],
        ["data/variant.json", "исходные данные варианта: шаги, маршруты, вероятности"],
        ["hmi_lab/model.py", "описание графа диалога, проверка данных, чтение и запись файла"],
        ["hmi_lab/dialog_sim.py", "модель ЛР1: розыгрыш подтем, маршрутов, ошибок; формулы M[T]"],
        ["hmi_lab/efficiency_sim.py", "модель ЛР2: поток заявок, отказы, восстановление, потери"],
        ["hmi_lab/plots.py", "построение графиков"],
        ["hmi_lab/gui/", "окно программы: разделы «Исходные данные», «ЛР1», «ЛР2»"],
        ["report/make_report.py", "проведение экспериментов и формирование отчётов"],
    ]
    p = rep.para("Таблица А.1 – Файлы проекта", indent=False, keep=True,
                 align=WD_ALIGN_PARAGRAPH.LEFT, before=6)
    t = rep.doc.add_table(rows=1, cols=2)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for c, h in enumerate(["Файл", "Назначение"]):
        cell = t.rows[0].cells[c]
        cell.width = Cm([6.0, 11.0][c])
        cp = cell.paragraphs[0]
        cp.paragraph_format.first_line_indent = Cm(0)
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cp.add_run(h).bold = True
    for row in rows:
        cells = t.add_row().cells
        for c, v in enumerate(row):
            cells[c].width = Cm([6.0, 11.0][c])
            cp = cells[c].paragraphs[0]
            cp.paragraph_format.first_line_indent = Cm(0)
            cp.alignment = WD_ALIGN_PARAGRAPH.LEFT
            cp.add_run(v)
    rep.keep_together(t)
    del p


def save_fig(fig, name: str) -> Path:
    path = FIG / f"{name}.png"
    fig.savefig(path, dpi=220)
    plt.close(fig)
    return path


# =============================================================================
#                                    ЛР1
# =============================================================================
def build_lr1(data: dict, pages: dict | None) -> Report:
    rep = Report(pages)
    rep.title_page(1, "Оценка временных характеристик диалога")
    rep.toc_placeholder()
    samples = data["samples"]
    k_auto = auto_k(N)

    rep.section("Цель работы")
    rep.text("Познакомиться с методами оценки временных характеристик пользовательских "
             "интерфейсов и формированием функциональных требований к приложению; разработать "
             "имитационную модель, позволяющую оценить время решения задачи пользователем "
             "диалоговой системы с альтернативной структурой диалога.")

    rep.section("Задание")
    rep.text("В соответствии с методическими указаниями [1] требуется разработать приложение, "
             "позволяющее проводить имитационные эксперименты для заданного графа диалога с "
             "двумя подтемами, и с его помощью:")
    rep.items([
        "оценить среднее время выполнения каждой подтемы при различных значениях вероятности "
        "ошибочного действия P",
        "оценить среднее время выполнения темы диалога, т. е. время решения задачи пользователем",
        "построить гистограммы времени решения задачи для P = 0; 0.3; 0.6; 0.9; начальное число "
        "интервалов гистограммы K для выборки объёмом N определяется по формуле "
        "K = int(1 + 3.22 lg N), при необходимости пользователь задаёт K сам",
    ])

    rep.section("Описание исследуемой диалоговой системы")
    rep.text("Исследуется диалоговая система с альтернативной структурой диалога: диалог ведёт "
             "система, и пользователь решает задачу, проходя один из заранее предписанных "
             "маршрутов. Тема диалога (решение задачи пользователем) состоит из двух подтем.",
             f"Подтема 1 содержит {len(S1.steps)} шагов и {len(S1.routes)} маршрутов, подтема 2 — "
             f"{len(S2.steps)} шагов и {len(S2.routes)} маршрутов. Маршрут — это "
             "последовательность номеров шагов, которые пользователь проходит от начала до конца "
             "подтемы. Каждый шаг диалога характеризуется временем выполнения. При ошибочном "
             "действии пользователя используется процедура обработки ошибок «переход в текущую "
             "вершину графа диалога»: шаг выполняется повторно.")
    rep.text("В соответствии с методическими указаниями [1] о системе принимаются следующие "
             "положения:")
    rep.items([
        "в диалоговой системе две подтемы; в каждой не более 10 маршрутов длиной не более 10 шагов",
        "время выполнения шага — случайная величина с известным законом распределения или "
        "детерминированная величина, оценённая по методике GOMS",
        "вероятность ошибочного действия P одинакова для всех шагов и не зависит от предыстории "
        "диалога",
        "маршруты в подтеме и сами подтемы выбираются с известными вероятностями",
        "пользователю достаточно подсказок на каждом шаге, справочные подтемы не открываются",
    ])

    rep.section("Требования к приложению")
    rep.text("Приложение состоит из трёх разделов: «Исходные данные», «ЛР1 · Время диалога» и "
             "«ЛР2 · Эффективность». К функциям, относящимся к лабораторной работе № 1, "
             "предъявляются следующие требования:")
    rep.items([
        "ввод и редактирование для каждой подтемы шагов диалога (название, закон распределения "
        "времени и его параметры), маршрутов (вероятность и последовательность шагов), "
        "вероятности выбора подтемы и вероятности ошибки",
        "проверка корректности данных: суммы вероятностей равны 1, номера шагов в маршрутах "
        "существуют, ограничения на число шагов и маршрутов соблюдены",
        "сохранение исходных данных в файл и загрузка из файла",
        "моделирование выборки объёмом N одновременно для нескольких значений P",
        "вывод среднего времени выполнения подтемы 1, подтемы 2 и темы в целом, а также "
        "значения, рассчитанного по формуле, для проверки модели",
        "построение гистограмм времени решения задачи с числом интервалов K по формуле или "
        "заданным пользователем; изменение K не требует повторного моделирования",
        "моделирование выполняется в фоновом режиме, интерфейс при этом не блокируется",
    ])

    rep.section("Моделирующий алгоритм")
    rep.text("Одна реализация модели соответствует однократному решению задачи пользователем и "
             "выполняется так:")
    rep.items([
        "разыгрывается подтема: генерируется случайное число u, равномерно распределённое на "
        "[0; 1), и сравнивается с накопленными вероятностями выбора подтем (метод обратной "
        "функции для дискретной случайной величины)",
        "тем же способом разыгрывается маршрут в выбранной подтеме по вероятностям маршрутов",
        "указатель ставится на первый шаг маршрута, время реализации T = 0",
        "генерируется время исполнения текущего шага по его закону распределения и "
        "прибавляется к T",
        "разыгрывается ошибка: если очередное случайное число u < P, действие считается "
        "ошибочным и, согласно процедуре «переход в текущую вершину графа», шаг выполняется "
        "повторно; иначе указатель переходит к следующему шагу маршрута",
        "пункты 4–5 повторяются, пока не выполнен последний шаг маршрута; накопленное T — "
        "время решения задачи в данной реализации",
    ], numbered=True)
    rep.text("Время шага генерируется так: для константы берётся заданное значение; для "
             "нормального закона N(μ, σ) — методом Бокса–Мюллера, отрицательные значения "
             "заменяются нулём; для равномерного закона на [a; b] — по формуле a + (b − a)·u; "
             "для экспоненциального закона со средним m — по формуле −m·ln(1 − u).",
             f"Моделирование повторяется N раз. По выборке вычисляются среднее время t̄, "
             f"среднеквадратическое отклонение s, минимум и максимум. Диапазон [min; max] "
             f"делится на K равных интервалов, где K = int(1 + 3.22 lg N); при N = {N} "
             f"получается K = {k_auto}.",
             "Для проверки модели среднее время рассчитывается также аналитически. При "
             "процедуре «переход в текущую вершину» каждое исполнение шага успешно с "
             "вероятностью 1 − P, поэтому число исполнений шага имеет геометрическое "
             "распределение со средним 1/(1 − P). Отсюда среднее время маршрута m:")
    rep.formula("M[T_{m}] = Σ M[t_{s}] / (1 − P),")
    rep.where(["M[t_{s}] — среднее время шага s, суммирование ведётся по всем шагам маршрута",
               "P — вероятность ошибочного действия"])
    rep.text("Среднее время подтемы и темы:")
    rep.formula("M[T_{подт}] = Σ p_{m} · M[T_{m}],")
    rep.formula("M[T_{темы}] = q_{1} · M[T_{подт 1}] + q_{2} · M[T_{подт 2}],")
    rep.where(["p_{m} — вероятность выбора маршрута m в подтеме",
               "q_{1}, q_{2} — вероятности выбора подтем"])

    # --- исходные данные -----------------------------------------------------
    rep.section("Исходные данные контрольного примера")
    rep.subsection("Обоснование исходных данных")
    rep.text("Вариант исходных данных преподавателем не выдавался, поэтому контрольный пример "
             "составлен самостоятельно по следующим правилам.",
             "1) Времена формализованных шагов, состоящих из простых действий (указать на объект, "
             "нажать кнопку, подтвердить), оценены по методике GOMS [2, 3]: время действия равно "
             "сумме стандартных интервалов элементарных операций. Использованы значения из [2]: "
             "K — нажатие клавиши, 0.2 с; P — указание мышью на объект, 1.1 с; H — перенос руки "
             "между клавиатурой и мышью, 0.4 с; M — мысленная подготовка, 1.35 с. Например, шаг 6 "
             "подтемы 1 = M + P + K + M + K = 1.35 + 1.1 + 0.2 + 1.35 + 0.2 = 4.2 с; шаг 7 "
             "подтемы 1 = M + K ≈ 1.6 с; шаг 2 подтемы 1 = M + P + K ≈ 2.5 с; шаг 1 подтемы 2 = "
             "M + K ≈ 1.5 с. Такие шаги заданы константами.",
             "2) Время шагов, требующих чтения и анализа информации, у разных пользователей "
             "различается, поэтому задано нормальным законом: μ — оценка среднего времени "
             "опытного пользователя, σ — 20–30 % от μ.",
             "3) Для шагов, у которых известны только наименьшее и наибольшее время, использован "
             "равномерный закон.",
             "4) Шаги, на которых пользователь ожидает ответа системы, заданы экспоненциальным "
             "законом: короткие ожидания часты, длинные редки.",
             "5) Вероятности маршрутов заданы так, чтобы основной вклад давали типовые маршруты "
             "М1 и М2; остальные маршруты встречаются реже.",
             "6) Вероятности выбора подтем 0.8 и 0.2: подтема 1 выполняется чаще подтемы 2. Это "
             "согласуется с лабораторной работой № 2, где подтема 1 — обработка часто "
             "поступающих запросов, а подтема 2 — восстановление после редких отказов.",
             "7) Базовая вероятность ошибки P = 0.05 соответствует опытному пользователю; в "
             "экспериментах P задаётся равной 0; 0.3; 0.6; 0.9, как требует задание.")
    rep.text("Данные хранятся в файле data/variant.json и могут быть изменены в разделе "
             "программы «Исходные данные».")
    for k, sub in enumerate(theme.subtopics, 1):
        rep.subsection(f"Подтема {k}")
        rep.text(f"Вероятность выбора подтемы — {sub.choice_prob:g}, базовая вероятность "
                 f"ошибки — {sub.p_error:g}. Шаги приведены в таблице {rep.tables + 1}, "
                 f"маршруты — в таблице {rep.tables + 2}.")
        subtopic_tables(rep, k, sub)

    # --- описание приложения ---------------------------------------------------
    rep.section("Описание приложения")
    rep.text("Приложение написано на языке Python с использованием библиотеки PySide6 [5] "
             "для интерфейса и matplotlib [6] для графиков. Слева в окне расположено меню из "
             "трёх разделов.")
    f1 = rep.figures + 1
    rep.text(f"В разделе «Исходные данные» (рисунок {f1}) для каждой подтемы задаются название, "
             "вероятность выбора, вероятность ошибки, таблица шагов и таблица маршрутов. "
             "Значок в правом верхнем углу показывает результат проверки данных.")
    rep.figure(FIG / "screen_data.png", "Раздел «Исходные данные»")
    rep.text(f"В разделе «ЛР1 · Время диалога» (рисунок {f1 + 1}) задаются объём выборки N, "
             "значения P и число интервалов K. После нажатия кнопки «Моделировать» "
             "выводятся средние времена, гистограммы для каждого значения P и таблица "
             "средних, рассчитанных моделированием и по формуле (3).")
    rep.figure(FIG / "screen_lr1.png", "Раздел «ЛР1 · Время диалога» после моделирования")

    # --- результаты ----------------------------------------------------------
    rep.section("Результаты моделирования")
    rep.text(f"Эксперименты проведены при N = {N} реализаций для каждого значения P; "
             f"генератор случайных чисел инициализирован числом {SEED}, поэтому результаты "
             f"воспроизводимы.")
    rep.subsection("Среднее время выполнения подтем и темы")
    rows, devs = [], []
    for p in P_VALUES:
        th = theory_mean_theme(theme, p)
        st = SampleStats.of(samples[("theme", p)])
        dev = abs(st.mean - th) / th * 100
        devs.append(dev)
        rows.append([f"{p:g}", num(samples[("sub0", p)].mean(), ".1f"),
                     num(samples[("sub1", p)].mean(), ".1f"), num(st.mean, ".1f"),
                     num(th, ".1f"), num(dev, ".2f"), num(st.sd, ".1f")])
    tnum = rep.tables + 1
    rep.text(f"Результаты приведены в таблице {tnum}. Столбец «по формуле» рассчитан по "
             f"формуле (3), отклонение — разница между моделированием и формулой в процентах.")
    rep.table("Среднее время решения задачи, с",
              ["P", "Подтема 1", "Подтема 2", "Тема", "Тема по формуле", "Откло-нение, %",
               "СКО темы"], rows, [1.5, 2.5, 2.5, 2.3, 2.9, 2.6, 2.7], ["c"] * 7)

    fig, ax = plt.subplots(figsize=(6.5, 3.4), layout="constrained")
    ps = np.linspace(0, 0.9, 19)
    for sub, name, style in ((S1, "подтема 1", "--"), (S2, "подтема 2", "-.")):
        ax.plot(ps, [theory_mean_subtopic(sub, p) for p in ps], style, color="black", lw=1,
                label=f"{name}, формула")
    ax.plot(ps, [theory_mean_theme(theme, p) for p in ps], "-", color="black", lw=1.6,
            label="тема, формула")
    for tg, mk in (("sub0", "s"), ("sub1", "^"), ("theme", "o")):
        ax.plot(P_VALUES, [samples[(tg, p)].mean() for p in P_VALUES], mk, color=plots.BLUE,
                ms=5)
    ax.plot([], [], "o", color=plots.BLUE, label="моделирование")
    ax.set_yscale("log")
    ax.set_xlabel("вероятность ошибки P")
    ax.set_ylabel("среднее время, с")
    ax.legend()
    plots._localize(fig)
    fnum = rep.figures + 1
    rep.text(f"Зависимость среднего времени от P показана на рисунке {fnum}. Линии — расчёт "
             "по формулам (1)–(3), точки — результаты моделирования. Вертикальная ось "
             "логарифмическая.")
    rep.figure(save_fig(fig, "lr1_mean_vs_p"), "Зависимость среднего времени от вероятности "
               "ошибки")

    rep.subsection("Гистограммы времени решения задачи")
    fig = plt.figure(figsize=(6.5, 5.8), layout="constrained")
    plots.draw_histograms(fig, {p: samples[("theme", p)] for p in P_VALUES}, None,
                          {p: theory_mean_theme(theme, p) for p in P_VALUES})
    fnum = rep.figures + 1
    rep.text(f"Гистограммы времени решения задачи (тема целиком) для P = 0; 0.3; 0.6; 0.9 "
             f"приведены на рисунке {fnum}. По вертикали — доля реализаций, попавших в "
             f"интервал; выделен интервал, содержащий среднее значение; K = {k_auto}.")
    rep.figure(save_fig(fig, "lr1_hist"), f"Гистограммы времени решения задачи, N = {N}")
    x = samples[("theme", 0.0)]
    counts, edges = histogram(x, k_auto)
    rep.text(f"Частоты по интервалам для P = 0 приведены в таблице {rep.tables + 1}.")
    rep.table("Частоты по интервалам, P = 0",
              ["№", "Интервал, с", "Число попаданий", "Доля"],
              [[str(i + 1), f"{num(lo, '.1f')} – {num(hi, '.1f')}", str(c), num(c / N, ".4f")]
               for i, (lo, hi, c) in enumerate(zip(edges, edges[1:], counts))],
              [1.5, 6.0, 4.5, 3.5], ["c"] * 4)

    rep.subsection("Сравнение процедур обработки ошибок")
    modes = data["modes"]
    rep.text("Дополнительно сравнены три процедуры обработки ошибок, перечисленные в "
             f"методических указаниях [1]. Средние времена решения задачи приведены в таблице "
             f"{rep.tables + 1}.")
    rep.table("Среднее время решения задачи при разных процедурах обработки ошибок, с",
              ["Процедура", "P = 0.1", "P = 0.2", "P = 0.3"],
              [[ERROR_MODES[m]] + [num(modes[(m, p)][0], ".1f") for p in (0.1, 0.2, 0.3)]
               for m in ERROR_MODES], [8.6, 2.8, 2.8, 2.8], ["l", "c", "c", "c"])

    # --- выводы -------------------------------------------------------------
    rep.section("Выводы")
    t0, t9 = samples[("theme", 0.0)].mean(), samples[("theme", 0.9)].mean()
    s0, s9 = samples[("theme", 0.0)].std(ddof=1), samples[("theme", 0.9)].std(ddof=1)
    m1, m2 = samples[("sub0", 0.0)].mean(), samples[("sub1", 0.0)].mean()
    rr = modes[("restart", 0.3)][0] / modes[("repeat", 0.3)][0]
    rb = modes[("back", 0.3)][0] / modes[("repeat", 0.3)][0]
    rep.items([
        "разработаны имитационная модель и приложение для оценки временных характеристик "
        "диалога; средние значения, полученные моделированием, отличаются от рассчитанных по "
        f"формулам не более чем на {num(max(devs), '.1f')} %, что подтверждает правильность модели",
        f"при безошибочной работе (P = 0) среднее время решения задачи составляет "
        f"{num(t0, '.1f')} с; подтема 2 выполняется в {num(m2 / m1, '.1f')} раза дольше подтемы 1, "
        f"но выбирается в 4 раза реже, поэтому основной вклад в среднее время темы даёт подтема 1",
        f"с ростом P среднее время растёт пропорционально 1/(1 − P): при P = 0.9 оно равно "
        f"{num(t9, '.1f')} с, т. е. в {num(t9 / t0, '.1f')} раза больше, чем при P = 0; разброс "
        f"растёт ещё быстрее — СКО увеличивается с {num(s0, '.1f')} до {num(s9, '.1f')} с",
        "при P = 0 гистограмма имеет два максимума: основной образуют маршруты подтемы 1, второй "
        "(в области 120–150 с) — маршруты подтемы 2; с ростом P максимумы сливаются и "
        "появляется длинный правый «хвост», так как число повторов шагов может быть большим",
        f"процедура обработки ошибок сильно влияет на время: при P = 0.3 возврат на шаг назад "
        f"увеличивает среднее время в {num(rb, '.1f')} раза, а возврат в начало маршрута — в "
        f"{num(rr, '.1f')} раза по сравнению с повтором текущего шага; поэтому при проектировании "
        f"диалога после ошибки пользователя следует возвращать в текущий шаг",
    ])

    sources(rep)
    appendix_files(rep)
    return rep


# =============================================================================
#                                    ЛР2
# =============================================================================
def system_diagram() -> Path:
    fig, ax = plt.subplots(figsize=(6.5, 2.9), layout="constrained")
    ax.set_axis_off()
    boxes = {
        "ou": (0.9, 1.3, "Объект\nуправления"),
        "in": (3.0, 2.15, "Подсистема\nсбора данных"),
        "out": (3.0, 0.45, "Подсистема\nвыдачи команд"),
        "arm": (5.1, 1.3, "АРМ: подсистема\nпереработки\nинформации"),
        "op": (7.2, 1.3, "Человек-\nоператор"),
    }
    for x, y, text in boxes.values():
        ax.add_patch(plt.Rectangle((x - 0.85, y - 0.42), 1.7, 0.84, fill=False, lw=1.2))
        ax.text(x, y, text, ha="center", va="center", fontsize=11)

    def arrow(a, b, xy_from, xy_to):
        ax.annotate("", xy=xy_to, xytext=xy_from,
                    arrowprops=dict(arrowstyle="-|>", lw=1.1, color="black"))

    arrow("ou", "in", (1.75, 1.6), (2.15, 2.15))
    arrow("in", "arm", (3.85, 2.15), (4.25, 1.6))
    arrow("arm", "op", (5.95, 1.42), (6.35, 1.42))
    arrow("op", "arm", (6.35, 1.18), (5.95, 1.18))
    arrow("arm", "out", (4.25, 1.0), (3.85, 0.45))
    arrow("out", "ou", (2.15, 0.45), (1.75, 1.0))
    ax.set_xlim(0, 8.1)
    ax.set_ylim(0, 2.65)
    return save_fig(fig, "lr2_system")


def build_lr2(data: dict, pages: dict | None) -> Report:
    rep = Report(pages)
    rep.title_page(2, "Оценка эффективности человеко-машинной системы")
    rep.toc_placeholder()
    base, res, studies = data["base"], data["res"], data["studies"]
    m1 = theory_mean_subtopic(S1, base.p1)
    m2 = theory_mean_subtopic(S2, base.p2)
    rho = base.lam_per_hour / 3600 * m1
    kg = base.mtbf_hours * 3600 / (base.mtbf_hours * 3600 + m2)

    rep.section("Цель работы")
    rep.text("Построение и исследование модели оценки по проектным данным эффективности "
             "функционирования человеко-машинной системы.")

    rep.section("Задание")
    rep.text("В соответствии с методическими указаниями [1] требуется:")
    rep.items([
        "ознакомиться с описанием функционирования системы",
        "разработать показатель оценки качества функционирования системы",
        "разработать моделирующий алгоритм для оценки качества функционирования системы, "
        "используя модули, разработанные в лабораторной работе № 1",
        "исследовать на модели влияние параметров человека-оператора АРМ на эффективность "
        "работы системы",
    ])

    rep.section("Характеристика исследуемой системы")
    fnum = rep.figures + 1
    rep.text(f"Структура системы приведена на рисунке {fnum}; она соответствует рисунку 1 "
             "методических указаний [1].")
    rep.figure(system_diagram(), "Структура исследуемой человеко-машинной системы")
    rep.text("Подсистема сбора данных передаёт на автоматизированное рабочее место (АРМ) "
             "информацию об объекте управления, подсистема выдачи команд передаёт на объект "
             "управляющие воздействия. Человек-оператор (ЧО) принимает оперативные решения и "
             "с помощью диалоговой системы АРМ решает две задачи:")
    rep.items([
        "задача 1 — выработка оперативных регулирующих воздействий, обеспечивающих "
        "функционирование системы в штатном режиме; ей соответствует подтема 1 из "
        "лабораторной работы № 1",
        "задача 2 — восстановление функционирования системы после её отказа; ей соответствует "
        "подтема 2",
    ])
    rep.text(f"Соответствие условий методических указаний и модели приведено в таблице "
             f"{rep.tables + 1}.")
    rep.table("Условия методических указаний и их представление в модели",
              ["Условие методических указаний", "Представление в модели"], [
                  ["Запросы поступают в случайные моменты, известна интенсивность потока",
                   f"пуассоновский поток заявок с интенсивностью λ = {base.lam_per_hour:g} 1/ч"],
                  ["Известен закон распределения времени наработки на отказ",
                   f"экспоненциальный закон со средним T_{{0}} = {base.mtbf_hours:g} ч"],
                  ["После отказа все ожидающие и обрабатываемые запросы аннулируются",
                   "в момент отказа очередь заявок очищается"],
                  ["Потери пропорциональны задержке обработки запроса, удельные потери R1",
                   f"R1 = {base.r1:g} у. е. за 1 с задержки"],
                  ["Потери пропорциональны времени простоя, удельные потери R2",
                   f"R2 = {base.r2:g} у. е. за 1 с простоя"],
                  ["Восстановление — реализация подтемы диалога (задача 2)",
                   "время восстановления — одна реализация подтемы 2 модели ЛР1"],
                  ["Обработка ошибок — переход в текущую вершину графа",
                   "при ошибке шаг выполняется повторно"],
              ], [8.5, 8.5], ["l", "l"])

    rep.section("Показатель эффективности")
    rep.text("Методические указания задают два вида потерь: от задержки выдачи регулирующих "
             "воздействий и от простоя системы. Поэтому в качестве показателя эффективности "
             "выбраны средние удельные потери системы за интервал моделирования:")
    rep.formula("Q = (R1 · Σ τ_{i} + R2 · Σ θ_{j}) / T,")
    rep.where(["τ_{i} — задержка выдачи регулирующего воздействия по i-й заявке, с: время от "
               "поступления заявки до окончания её обработки оператором",
               "θ_{j} — длительность j-го восстановления (простоя), с",
               "T — интервал моделирования, с",
               "Q — потери в единицу времени, у. е./с; чем меньше Q, тем эффективнее система"])
    rep.text("Деление на T позволяет сравнивать результаты, полученные на интервалах разной "
             "длины. Слагаемые Q_{1} = R1 · Σ τ_{i} / T и Q_{2} = R2 · Σ θ_{j} / T показывают "
             "вклад задержек и простоя.",
             "Дополнительно оцениваются коэффициент готовности — доля времени, когда система "
             "работает, — и загрузка оператора заявками:")
    rep.formula("K_{г} = 1 − Σ θ_{j} / T ≈ T_{0} / (T_{0} + M[θ]),")
    rep.formula("ρ = λ · M[t_{обсл}],")
    rep.where(["T_{0} — средняя наработка на отказ",
               "M[θ] — среднее время восстановления",
               "M[t_{обсл}] — среднее время обработки одной заявки"])
    rep.text("Если загрузка ρ приближается к 1, оператор не успевает обрабатывать заявки и "
             "очередь неограниченно растёт.",
             "Модель запускается M раз с разными случайными числами. По результатам вычисляется "
             "среднее значение показателя и 95-процентный доверительный интервал:")
    rep.formula("Q̄ ± 1.96 · s / √M,")
    rep.where(["Q̄ — среднее значение Q по M прогонам", "s — выборочное СКО значений Q"])

    rep.section("Моделирующий алгоритм")
    rep.text("Используется событийное моделирование: модельное время переходит от одного "
             "события (приход заявки, окончание обработки, отказ, окончание восстановления) к "
             "следующему. Один прогон выполняется так:")
    rep.items([
        "t := 0, очередь заявок пуста; момент прихода первой заявки a = −ln(1 − u) / λ",
        "разыгрывается наработка до отказа X = −T_{0} · ln(1 − u); момент отказа "
        "t_{отк} := t + X",
        "пока оператор освобождается раньше момента отказа: все заявки, пришедшие до "
        "освобождения оператора, ставятся в очередь; первая заявка из очереди берётся в "
        "обработку; время обработки — одна реализация подтемы 1 модели ЛР1; если обработка "
        "закончилась до отказа, заявка обслужена и её задержка τ равна моменту окончания "
        "минус момент прихода",
        "при отказе разыгрывается время восстановления θ — одна реализация подтемы 2 модели "
        "ЛР1; все заявки в очереди и на обработке аннулируются, их задержка "
        "τ = t_{отк} + θ − момент прихода; заявки, пришедшие во время восстановления, "
        "ставятся в очередь",
        "t := t_{отк} + θ; если t < T, перейти к пункту 2",
        "вычислить Q по формуле (1)",
    ], numbered=True)
    rep.text("Прогон повторяется M раз, после чего вычисляются среднее и доверительный "
             "интервал по формуле (4). Модель лабораторной работы № 1 используется в каждом "
             "прогоне многократно: для расчёта времени обработки каждой заявки и времени "
             "каждого восстановления.",
             "В модели приняты следующие допущения, не оговорённые в методических указаниях:")
    rep.items([
        "задержка аннулированной заявки считается до окончания восстановления, так как всё это "
        "время регулирующее воздействие по ней не выдано",
        "заявки, поступившие во время восстановления, не теряются: объект продолжает их "
        "передавать, и они обрабатываются после восстановления",
        "оператор один и обрабатывает заявки по очереди в порядке поступления",
        "заявки, не обработанные к концу интервала T, учитываются с задержкой до момента T",
    ])

    rep.section("Исходные данные для имитационных экспериментов")
    rep.subsection("Параметры системы")
    rep.text(f"Параметры базового варианта приведены в таблице {rep.tables + 1}.")
    rep.table("Параметры базового варианта", ["Параметр", "Значение"], [
        ["Интенсивность потока заявок λ", f"{base.lam_per_hour:g} 1/ч (в среднем 1 заявка в 2 мин)"],
        ["Средняя наработка на отказ T_{0}", f"{base.mtbf_hours:g} ч"],
        ["Закон распределения наработки на отказ", "экспоненциальный"],
        ["Удельные потери от задержки R1", f"{base.r1:g} у. е./с"],
        ["Удельные потери от простоя R2", f"{base.r2:g} у. е./с"],
        ["Вероятность ошибки оператора P (подтемы 1 и 2)", f"{base.p1:g}"],
        ["Интервал моделирования T", f"{base.horizon_hours:g} ч (30 суток)"],
        ["Число прогонов M", f"{base.runs}"],
    ], [10.0, 7.0], ["l", "l"])
    rep.subsection("Обоснование исходных данных")
    rep.text("Конкретные значения преподавателем не задавались, поэтому выбраны так, чтобы "
             "модель описывала правдоподобную и в то же время показательную ситуацию:")
    rep.items([
        f"λ = {base.lam_per_hour:g} 1/ч: при среднем времени обработки запроса "
        f"{num(m1, '.1f')} с загрузка оператора ρ = {num(rho, '.3f')} — оператор занят "
        f"меньше половины времени, т. е. работает в нормальном режиме с запасом, который можно "
        f"«съесть» ошибками",
        f"T_{{0}} = {base.mtbf_hours:g} ч: отказ примерно раз в рабочую смену, что даёт около "
        f"{round(base.horizon_hours / base.mtbf_hours)} отказов за 30 суток — достаточно для "
        f"статистики",
        "экспоненциальный закон наработки — стандартная модель внезапных отказов без старения "
        "оборудования [4]",
        f"R2 = {base.r2:g} R1: секунда простоя всей системы принята в 10 раз дороже секунды "
        f"задержки одного запроса; значения условные, поэтому потери выражены в условных "
        f"единицах (у. е.)",
        "P = 0.05 — опытный оператор, как в лабораторной работе № 1",
        "T = 720 ч и M = 20 обеспечивают доверительный интервал показателя Q около 0,5 % "
        "его значения",
    ])
    rep.text(f"Графы диалога подтем — те же, что в лабораторной работе № 1 (таблицы "
             f"{rep.tables + 1} и {rep.tables + 2}). Средние времена: обработка заявки "
             f"(подтема 1) — {num(m1, '.1f')} с, восстановление (подтема 2) — {num(m2, '.1f')} с "
             f"при P = {base.p1:g}.")
    rep.table("Маршруты подтемы 1 (обработка заявки)",
              ["Маршрут", "Вероят-ность", "Последовательность шагов", "M[t] при P = 0, с"],
              route_rows(S1), [6.0, 2.4, 5.8, 2.8], ["l", "c", "l", "c"])
    rep.table("Маршруты подтемы 2 (восстановление)",
              ["Маршрут", "Вероят-ность", "Последовательность шагов", "M[t] при P = 0, с"],
              route_rows(S2), [6.0, 2.4, 5.8, 2.8], ["l", "c", "l", "c"])

    rep.section("Описание приложения")
    f1 = rep.figures + 1
    rep.text(f"Для лабораторной работы № 2 предназначен раздел «ЛР2 · Эффективность» "
             f"(рисунок {f1}). Слева задаются параметры системы; после нажатия кнопки "
             f"«Рассчитать» выводятся показатель Q, его составляющие, коэффициент готовности, "
             f"средняя задержка и графики потерь.")
    rep.figure(FIG / "screen_lr2.png", "Раздел «ЛР2 · Эффективность» после расчёта")
    rep.text(f"В блоке «Исследование» выбирается параметр оператора (вероятность ошибки или "
             f"темп работы); кнопка «Построить зависимость» строит график зависимости Q от "
             f"этого параметра (рисунок {f1 + 1}).")
    rep.figure(FIG / "screen_lr2_study.png", "Исследование зависимости Q от вероятности ошибки")

    rep.section("Результаты моделирования")
    rep.subsection("Базовый вариант")
    names = [("q", "Показатель Q, у. е./с", ".3f"), ("q1", "в т. ч. от задержек Q_{1}, у. е./с", ".3f"),
             ("q2", "в т. ч. от простоя Q_{2}, у. е./с", ".4f"),
             ("availability", "Коэффициент готовности K_{г}", ".4f"),
             ("mean_delay", "Средняя задержка заявки, с", ".1f"),
             ("utilization", "Загрузка оператора заявками", ".3f"),
             ("arrived", "Поступило заявок за 30 суток", ".0f"),
             ("annulled", "Аннулировано заявок", ".0f"), ("failures", "Число отказов", ".0f")]
    rows = []
    for a, title, spec in names:
        m, c = res.mean_ci(a)
        rows.append([title, num(m, spec), "± " + num(c, spec if spec != ".0f" else ".1f")])
    rep.text(f"Результаты для базового варианта приведены в таблице {rep.tables + 1}.")
    rep.table("Результаты для базового варианта", ["Показатель", "Среднее", "95 % ДИ"], rows,
              [10.0, 3.5, 3.5], ["l", "c", "c"])
    q, _ = res.mean_ci("q")
    q1, _ = res.mean_ci("q1")
    kg_sim, _ = res.mean_ci("availability")
    util, _ = res.mean_ci("utilization")
    rep.text(f"Проверка модели по формулам (2) и (3): расчётный коэффициент готовности "
             f"{num(kg, '.4f')}, полученный моделированием — {num(kg_sim, '.4f')}; расчётная "
             f"загрузка {num(rho, '.3f')}, полученная — {num(util, '.3f')}. Совпадение "
             f"подтверждает правильность модели.")
    fig = plt.figure(figsize=(6.5, 3.0), layout="constrained")
    plots.draw_lr2(fig, res)
    fnum = rep.figures + 1
    rep.text(f"На рисунке {fnum} слева показана структура средних потерь, справа — "
             f"накопление потерь за 30 суток в одном прогоне модели.")
    rep.figure(save_fig(fig, "lr2_base"), "Структура и накопление потерь")

    study_titles = {
        "p": ("Влияние вероятности ошибки оператора", "P ошибки (в обеих подтемах)"),
        "time_scale": ("Влияние темпа работы оператора",
                       "темп работы (множитель времени шагов)"),
        "p2": ("Влияние вероятности ошибки при восстановлении", "P ошибки в подтеме 2"),
    }
    explain = {
        "p": "Вероятность ошибки задавалась одинаковой в обеих подтемах и менялась от 0 до 0.6.",
        "time_scale": "Темп работы задаётся множителем к времени всех шагов: 1 — время по "
                      "исходным данным, 2 — оператор работает вдвое медленнее, 0.5 — вдвое "
                      "быстрее.",
        "p2": "Вероятность ошибки менялась только в подтеме 2 (восстановление) от 0 до 0.9, в "
              "подтеме 1 оставалась равной 0.05.",
    }
    for key in ("p", "time_scale", "p2"):
        title, xlabel = study_titles[key]
        rep.subsection(title)
        sdata = studies[key]
        rep.text(explain[key] + f" Для каждого значения выполнено 10 прогонов. Результаты "
                 f"приведены в таблице {rep.tables + 1} и на рисунке {rep.figures + 1}.")
        rep.table(f"{title}",
                  ["Значение", "Q", "Q_{1}", "Q_{2}", "Задерж-ка, с", "Загруз-ка", "K_{г}"],
                  [[ru(f"{v:g}"), num(r.mean_ci('q')[0], ".3f"), num(r.mean_ci('q1')[0], ".3f"),
                    num(r.mean_ci('q2')[0], ".3f"), num(r.mean_ci('mean_delay')[0], ".1f"),
                    num(r.mean_ci('utilization')[0], ".2f"),
                    num(r.mean_ci('availability')[0], ".4f")] for v, r in sdata],
                  [2.8, 2.2, 2.2, 2.2, 2.6, 2.4, 2.6], ["c"] * 7)
        fig = plt.figure(figsize=(6.5, 4.6), layout="constrained")
        plots.draw_study(fig, xlabel, sdata)
        fig.axes[0].set_title("")
        rep.figure(save_fig(fig, f"lr2_study_{key}"), f"{title} на показатели системы")

    rep.section("Выводы")
    sp = dict(studies["p"])
    st = dict(studies["time_scale"])
    s2 = dict(studies["p2"])

    def g(d, v, a="q"):
        return d[min(d, key=lambda x: abs(x - v))].mean_ci(a)[0]

    rep.items([
        "разработан показатель эффективности — средние удельные потери Q, учитывающий потери "
        "от задержек выдачи регулирующих воздействий и от простоя системы, и моделирующий "
        "алгоритм, использующий модель диалога из лабораторной работы № 1 для расчёта времени "
        "обработки заявок и времени восстановления",
        f"в базовом варианте Q = {num(q, '.3f')} у. е./с; {num(q1 / q * 100, '.0f')} % потерь "
        f"приходится на задержки заявок, так как заявки поступают часто (около 30 в час), а "
        f"отказы редки (в среднем раз в 6 ч); коэффициент готовности {num(kg_sim, '.4f')}",
        f"вероятность ошибки оператора влияет на эффективность нелинейно: при росте P от 0 до "
        f"0.3 потери увеличиваются в {num(g(sp, 0.3) / g(sp, 0), '.1f')} раза, при P = 0.6 — в "
        f"{num(g(sp, 0.6) / g(sp, 0), '.0f')} раз; причина — рост загрузки оператора до "
        f"{num(g(sp, 0.6, 'utilization'), '.2f')}: когда загрузка приближается к 1, очередь "
        f"заявок и задержки резко растут",
        f"темп работы влияет так же: замедление оператора вдвое увеличивает Q в "
        f"{num(g(st, 2.0) / g(st, 1.0), '.1f')} раза, ускорение вдвое уменьшает Q в "
        f"{num(g(st, 1.0) / g(st, 0.5), '.1f')} раза",
        f"ошибки при восстановлении влияют слабее, пока P < 0.5 (Q растёт с "
        f"{num(g(s2, 0), '.3f')} до {num(g(s2, 0.5), '.3f')} у. е./с), но при P = 0.9 "
        f"потери от простоя возрастают в {num(g(s2, 0.9, 'q2') / g(s2, 0, 'q2'), '.0f')} раз, а "
        f"коэффициент готовности падает до {num(g(s2, 0.9, 'availability'), '.3f')}",
        "для повышения эффективности системы в первую очередь следует сокращать время и "
        "вероятность ошибок в часто выполняемой задаче 1: уменьшать число шагов в частых "
        "маршрутах, давать подсказки и проверку вводимых данных; загрузку оператора "
        "следует держать заметно ниже 1",
    ])

    sources(rep, ["Клейнрок Л. Теория массового обслуживания / Л. Клейнрок. – М. : "
                  "Машиностроение, 1979. – 432 с."])
    appendix_files(rep)
    return rep


# =============================================================================
#                 Сборка с настоящими номерами страниц
# =============================================================================
def heading_pages(pdf: Path, titles: list[str]) -> dict:
    from pypdf import PdfReader
    pages = [re.sub(r"\s+", " ", p.extract_text() or "") for p in PdfReader(str(pdf)).pages]
    found = {}
    for title in titles:
        key = re.sub(r"\s+", " ", title)
        for i, text in enumerate(pages):
            if i < 2:  # титульный лист и содержание
                continue
            if key in text:
                found[title] = i + 1
                break
    return found


def to_pdf(docx_path: Path, pdf_path: Path):
    from docx2pdf import convert
    convert(str(docx_path), str(pdf_path))


def render(name: str, build, data, use_pdf: bool):
    final = OUT / f"{name}.docx"
    if not use_pdf:
        build(data, None).save(final)
        return final
    draft = BUILD / f"{name}_draft.docx"
    rep = build(data, None)
    titles = list(rep.toc)
    rep.save(draft)
    to_pdf(draft, BUILD / f"{name}_draft.pdf")
    pages = heading_pages(BUILD / f"{name}_draft.pdf", titles)
    missing = [t for t in titles if t not in pages]
    if missing:
        print("не найдены страницы разделов:", missing)
    build(data, pages).save(final)
    to_pdf(final, OUT / f"{name}.pdf")
    check = heading_pages(OUT / f"{name}.pdf", titles)
    if check != pages:
        print("ВНИМАНИЕ: номера страниц сдвинулись", pages, check)
    return final


if __name__ == "__main__":
    use_pdf = "--no-pdf" not in sys.argv
    print("скриншоты программы…")
    screenshots()
    print("эксперименты ЛР1…")
    d1 = compute_lr1()
    print("эксперименты ЛР2…")
    d2 = compute_lr2()
    print(render("Отчёт_ЛР1", build_lr1, d1, use_pdf))
    print(render("Отчёт_ЛР2", build_lr2, d2, use_pdf))
