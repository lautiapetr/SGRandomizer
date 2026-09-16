from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from sgrand.gui.window import MainWindow


def test_main_window_starts_with_balanced_sections() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert "SGRand" in window.windowTitle()
        assert window.preset_combo.currentText() == "Balanced"
        assert '"schema_version": 1' in window.move_editor.toPlainText()
        assert window.tabs.count() == 6
    finally:
        window.close()
        application.processEvents()
