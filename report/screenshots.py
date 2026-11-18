"""Скриншоты окон программы для отчётов.

Запускается из make_report.py отдельным процессом. В поля «Зерно генератора»
вписывается то же зерно, что и в отчёте, поэтому числа на скриншотах совпадают
с таблицами отчёта.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "report" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

app = QApplication([])
app.setStyle("Fusion")

from hmi_lab.gui.main_window import MainWindow  # noqa: E402

w = MainWindow()
w.resize(1440, 900)
w.show()


def settle(n=40):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


def wait(task):
    loop = QEventLoop()
    task.finished.connect(loop.quit)
    if task.isRunning():
        loop.exec()
    settle()


def shot(index, name):
    w.go(index)
    settle()
    w.grab().save(str(OUT / f"{name}.png"))


shot(0, "screen_data")
lr1 = w.pages.widget(1)
lr1.seed.setValue(SEED)  # то же зерно, что в отчёте (оно же стоит по умолчанию)
lr1.run()
wait(lr1.task)
shot(1, "screen_lr1")
lr2 = w.pages.widget(2)
lr2.seed.setValue(SEED)
lr2.run()
wait(lr2.task)
shot(2, "screen_lr2")
lr2.study()
wait(lr2.task)
shot(2, "screen_lr2_study")
print("screenshots ok")
