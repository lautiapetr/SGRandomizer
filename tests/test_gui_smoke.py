from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from sgrand.gui.theme import dark_palette
from sgrand.gui.window import MainWindow


def test_main_window_starts_with_balanced_sections() -> None:
    application = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert "SGRand" in window.windowTitle()
        assert window.preset_combo.currentText() == "Balanced"
        assert window.move_editor.document()["schema_version"] == 1
        assert window.ability_editor.profile_name == "Balanced"
        assert window.trainer_editor.profile_name == "Balanced"
        assert window.tabs.count() == 6
        assert not window.windowIcon().isNull()
        for index in range(window.tabs.count()):
            assert not window.tabs.tabIcon(index).isNull(), window.tabs.tabText(index)
        for button in (
            window.diagnose_button,
            window.preview_button,
            window.apply_button,
            window.build_button,
        ):
            assert not button.icon().isNull(), button.text()
        assert window.apply_button.property("kind") == "primary"
        assert window.build_button.property("kind") == "gold"
    finally:
        window.close()
        application.processEvents()


def test_application_palette_is_dark_and_readable() -> None:
    palette = dark_palette()
    assert palette.window().color().lightness() < 40
    assert palette.windowText().color().lightness() > 180
    assert palette.base().color().lightness() < 50
