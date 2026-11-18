"""Запуск приложения: python main.py"""
import sys

from PySide6.QtWidgets import QApplication

from hmi_lab.gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("HMI Lab")
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
