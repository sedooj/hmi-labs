"""Оформление приложения: палитра и таблица стилей Qt."""
from pathlib import Path

CHEVRON = (Path(__file__).parent / "chevron.svg").as_posix()

BG = "#F3F5F9"
SURFACE = "#FFFFFF"
BORDER = "#E4E8EF"
TEXT = "#111827"
MUTED = "#6B7280"
PRIMARY = "#4F46E5"
PRIMARY_HOVER = "#4338CA"
PRIMARY_SOFT = "#EEF0FF"
SIDEBAR = "#0F172A"

QSS = f"""
* {{
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, QWidget#page, QStackedWidget {{
    background: {BG};
}}

/* ---------- боковая панель ---------- */
QWidget#sidebar {{
    background: {SIDEBAR};
}}
QLabel#brand {{
    color: white;
    font-size: 17px;
    font-weight: 700;
    padding: 4px 6px;
}}
QLabel#brandSub {{
    color: #94A3B8;
    font-size: 12px;
    padding: 0 6px 18px 6px;
}}
QPushButton#nav {{
    background: transparent;
    color: #CBD5E1;
    text-align: left;
    padding: 11px 14px;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
}}
QPushButton#nav:hover {{
    background: #1E293B;
    color: white;
}}
QPushButton#nav:checked {{
    background: {PRIMARY};
    color: white;
    font-weight: 600;
}}
QLabel#sidebarFoot {{
    color: #64748B;
    font-size: 11px;
    padding: 6px;
}}

/* ---------- заголовки страниц ---------- */
QLabel#pageTitle {{
    font-size: 24px;
    font-weight: 700;
}}
QLabel#pageSub {{
    color: {MUTED};
    font-size: 13px;
}}
QLabel#cardTitle {{
    font-size: 15px;
    font-weight: 600;
}}
QLabel#muted {{
    color: {MUTED};
    font-size: 12px;
}}
QLabel#fieldLabel {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 500;
}}

/* ---------- карточки ---------- */
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#kpi {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#kpiAccent {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366F1, stop:1 #4F46E5);
    border: none;
    border-radius: 14px;
}}
QFrame#kpiAccent QLabel {{
    color: white;
}}
QLabel#kpiTitle {{
    color: {MUTED};
    font-size: 12px;
}}
QLabel#kpiValue {{
    font-size: 24px;
    font-weight: 700;
}}

/* ---------- поля ввода ---------- */
QLineEdit, QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 0px 10px;
    min-height: 34px;
    selection-background-color: {PRIMARY};
    selection-color: white;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1.5px solid {PRIMARY};
}}
QComboBox::drop-down {{
    border: none;
    width: 30px;
}}
QComboBox::down-arrow {{
    image: url({CHEVRON});
    width: 12px;
    height: 8px;
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
    outline: none;
}}

/* ---------- кнопки ---------- */
QPushButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: #F8FAFC;
    border-color: #CBD5E1;
}}
QPushButton#primary {{
    background: {PRIMARY};
    color: white;
    border: none;
    border-radius: 10px;
    padding: 11px 18px;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: {PRIMARY_HOVER};
}}
QPushButton#primary:disabled {{
    background: #A5B4FC;
}}
QPushButton#secondary {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY};
    border: none;
    border-radius: 10px;
    padding: 11px 18px;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton#secondary:hover {{
    background: #E0E3FF;
}}
QPushButton#secondary:disabled {{
    color: #A5B4FC;
}}
QPushButton#ghost {{
    background: transparent;
    border: 1px dashed #CBD5E1;
    color: {MUTED};
    padding: 6px 12px;
}}
QPushButton#ghost:hover {{
    border-color: {PRIMARY};
    color: {PRIMARY};
}}

/* ---------- таблицы ---------- */
QTableWidget {{
    background: {SURFACE};
    border: none;
    gridline-color: transparent;
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
    outline: none;
}}
QTableWidget::item {{
    border-bottom: 1px solid #F1F3F7;
    padding: 4px 6px;
}}
QTableWidget::item:focus {{
    border: 1px solid {PRIMARY};
}}
QHeaderView::section {{
    background: {SURFACE};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 8px 6px;
    font-size: 11px;
    font-weight: 600;
}}
QTableCornerButton::section {{
    background: {SURFACE};
    border: none;
}}
QTableWidget QComboBox {{
    border: none;
    background: transparent;
    padding: 2px 6px;
}}

/* ---------- прокрутка, прогресс ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #D1D5DB;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0; width: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #D1D5DB;
    border-radius: 4px;
    min-width: 30px;
}}
QProgressBar {{
    background: {PRIMARY_SOFT};
    border: none;
    border-radius: 3px;
    max-height: 6px;
}}
QProgressBar::chunk {{
    background: {PRIMARY};
    border-radius: 3px;
}}
QToolTip {{
    background: {SIDEBAR};
    color: white;
    border: none;
    padding: 6px 8px;
    border-radius: 6px;
}}
QMessageBox QLabel {{
    color: {TEXT};
}}
"""
