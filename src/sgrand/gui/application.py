"""GUI entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .theme import APP_STYLESHEET, dark_palette, icon
from .window import MainWindow


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    smoke_test = "--smoke-test" in arguments
    if smoke_test:
        arguments.remove("--smoke-test")
    application = QApplication(arguments)
    application.setApplicationName("SGRand")
    application.setOrganizationName("SGRand")
    application.setStyle("Fusion")
    application.setPalette(dark_palette())
    application.setStyleSheet(APP_STYLESHEET)
    application.setWindowIcon(icon("app"))
    window = MainWindow()
    if smoke_test:
        window.close()
        return 0
    window.show()
    return application.exec()
