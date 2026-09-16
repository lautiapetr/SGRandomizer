from __future__ import annotations

import os
from collections.abc import Iterator
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton, QSpinBox, QTabWidget

from sgrand.errors import RandomizerError
from sgrand.gui.tutorial import TUTORIAL_STEPS, TutorialWizard
from sgrand.gui.window import MainWindow
from sgrand.gui_config import preset_config


@pytest.fixture
def window() -> Iterator[MainWindow]:
    application = QApplication.instance() or QApplication([])
    result = MainWindow()
    yield result
    result.close()
    application.processEvents()


@pytest.mark.parametrize("preset", ["Vanilla+", "Balanced", "Chaos", "Custom"])
def test_guided_editors_round_trip_every_preset(window: MainWindow, preset: str) -> None:
    window._set_config(preset_config(preset, spoiler_free=True))
    assert window._config() == preset_config(preset, spoiler_free=True)


def test_form_changes_mark_custom_and_serialize(window: MainWindow) -> None:
    offensive = cast(QSpinBox, window.move_editor.learnsets.control("offensive_percent"))
    offensive.setValue(83)

    assert window.preset_combo.currentText() == "Custom"
    assert window._config().moves["learnsets"]["offensive_percent"] == 83


def test_every_schema_option_has_a_guided_control(window: MainWindow) -> None:
    config = preset_config("Balanced")
    assert set(window.move_editor.learnsets.controls) | {
        "enabled",
        "source_files",
        "progressive_power",
    } == set(config.moves["learnsets"])
    assert set(window.move_editor.compatibility.controls) | {"enabled"} == set(
        config.moves["compatibility"]
    )
    assert set(window.move_editor.properties.controls) | {"enabled", "types"} == set(
        config.moves["properties"]
    )

    ability_profile = config.abilities["profiles"]["Balanced"]
    assert set(window.ability_editor.normal.controls) | {"enabled"} == set(
        ability_profile["abilities"]
    )
    assert set(window.ability_editor.innates.controls) | {"enabled"} == set(
        ability_profile["innates"]
    )

    trainer_profile = config.trainers["profiles"]["Balanced"]
    for category, panel in window.trainer_editor.rules.items():
        assert set(panel.controls) | {"enabled"} == set(trainer_profile[category])


def test_every_guided_option_has_player_friendly_hover_help(window: MainWindow) -> None:
    panels = (
        window.move_editor.learnsets,
        window.move_editor.compatibility,
        window.move_editor.properties,
        window.ability_editor.normal,
        window.ability_editor.innates,
        *window.trainer_editor.rules.values(),
    )
    for panel in panels:
        assert panel.toolTip(), panel.title()
        for spec in panel.specs:
            control = panel.control(spec.key)
            assert spec.help_text, spec.key
            assert control.toolTip() == spec.help_text, spec.key
            assert control.accessibleDescription() == spec.help_text, spec.key

    list_editors = (
        window.move_editor.protected,
        window.move_editor.signature,
        window.move_editor.excluded,
        window.move_editor.source_files,
        window.move_editor.types,
        window.ability_editor.blacklist,
        window.ability_editor.locked,
        window.ability_editor.special,
        window.trainer_editor.blacklist_species,
        window.trainer_editor.blacklist_moves,
        window.trainer_editor.blacklist_items,
        window.trainer_editor.item_allowlist,
        window.trainer_editor.boss_classes,
    )
    for editor in list_editors:
        assert editor.toolTip()
        assert editor.text.toolTip() == editor.toolTip()
        assert editor.text.accessibleDescription() == editor.toolTip()

    assert window.move_editor.power_table.toolTip()
    assert window.source_edit.toolTip()
    assert window.output_edit.toolTip()
    assert window.preset_combo.toolTip()
    assert window.seed_edit.toolTip()


def test_labels_buttons_and_tabs_expose_the_same_contextual_help(window: MainWindow) -> None:
    for label in window.findChildren(QLabel):
        if label.buddy() is not None:
            assert label.toolTip(), label.text()
    for button in window.findChildren(QPushButton):
        assert button.toolTip(), button.text()
        assert button.accessibleDescription(), button.text()
    for tabs in window.findChildren(QTabWidget):
        for index in range(tabs.count()):
            assert tabs.tabToolTip(index), tabs.tabText(index)


def test_ability_profiles_retain_independent_edits(window: MainWindow) -> None:
    delta = cast(QSpinBox, window.ability_editor.normal.control("maximum_rating_delta"))
    delta.setValue(4)
    window.ability_editor.profile_combo.setCurrentText("Chaos")
    chaos_delta = cast(QSpinBox, window.ability_editor.normal.control("maximum_rating_delta"))
    assert chaos_delta.value() == 10
    assert not chaos_delta.isEnabled()

    window.ability_editor.profile_combo.setCurrentText("Balanced")
    assert delta.value() == 4


def test_trainer_dependent_controls_follow_modes(window: MainWindow) -> None:
    panel = window.trainer_editor.rules["leaders"]
    level_mode = cast(QComboBox, panel.control("level_mode"))
    fixed_level = cast(QSpinBox, panel.control("fixed_level"))
    level_percent = cast(QSpinBox, panel.control("level_percent"))
    level_mode.setCurrentIndex(level_mode.findData("fixed"))

    assert fixed_level.isEnabled()
    assert not level_percent.isEnabled()
    assert window._config().trainers["profiles"]["Balanced"]["leaders"]["level_mode"] == "fixed"


def test_invalid_progressive_power_cell_is_reported(window: MainWindow) -> None:
    window.move_editor.power_table.item(0, 0).setText("not-a-number")
    with pytest.raises(RandomizerError, match="fuerza progresiva"):
        window._config()


def test_tutorial_has_complete_guided_flow() -> None:
    application = QApplication.instance() or QApplication([])
    tutorial = TutorialWizard()
    try:
        assert len(tutorial.pageIds()) == len(TUTORIAL_STEPS)
        assert "Tutorial" in tutorial.windowTitle()
    finally:
        tutorial.close()
        application.processEvents()
