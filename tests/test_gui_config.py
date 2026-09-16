from __future__ import annotations

import json
from pathlib import Path

import pytest

from sgrand.ability_config import load_ability_config
from sgrand.engine import Randomizer
from sgrand.errors import RandomizerError
from sgrand.gui_config import (
    PRESET_NAMES,
    gui_config_from_dict,
    load_gui_config,
    materialize_gui_config,
    preset_config,
    save_gui_config,
)
from sgrand.move_config import load_move_config
from sgrand.trainer_config import load_trainer_config


@pytest.mark.parametrize("name", PRESET_NAMES)
def test_presets_are_isolated_and_engine_valid(name: str) -> None:
    config = preset_config(name)
    with materialize_gui_config(config) as paths:
        assert load_move_config(paths.moves).profile
        assert load_ability_config(paths.abilities, paths.ability_profile).profile.name
        assert load_trainer_config(paths.trainers, paths.trainer_profile).profile.name


def test_vanilla_plus_and_chaos_have_distinct_policies() -> None:
    vanilla = preset_config("Vanilla+")
    assert vanilla.moves["learnsets"]["enabled"] is False
    assert vanilla.moves["compatibility"]["enabled"] is False
    assert vanilla.moves["properties"]["enabled"] is False
    assert vanilla.abilities["profiles"]["Vanilla+"]["abilities"]["enabled"] is False
    assert all(
        rules["enabled"] is False for rules in vanilla.trainers["profiles"]["Vanilla+"].values()
    )

    chaos = preset_config("Chaos")
    assert chaos.ability_profile == "Chaos"
    assert chaos.trainer_profile == "Chaos"
    assert chaos.moves["properties"]["power_variation_percent"] == 60


def test_gui_config_import_export_round_trip(tmp_path: Path) -> None:
    expected = preset_config("Balanced", spoiler_free=True)
    target = tmp_path / "config.json"
    save_gui_config(expected, target)
    assert load_gui_config(target) == expected
    assert json.loads(target.read_text(encoding="utf-8"))["schema_version"] == 1


def test_gui_config_is_strict() -> None:
    document = preset_config("Balanced").as_dict()
    document["unexpected"] = True
    with pytest.raises(RandomizerError, match="unknown unexpected"):
        gui_config_from_dict(document)

    document = preset_config("Balanced").as_dict()
    document["schema_version"] = 99
    with pytest.raises(RandomizerError, match="Unsupported GUI configuration schema"):
        gui_config_from_dict(document)


@pytest.mark.parametrize("name", ["Vanilla+", "Balanced", "Chaos"])
def test_gui_presets_drive_the_real_engine(synthetic_source: Path, name: str) -> None:
    config = preset_config(name, spoiler_free=True)
    with materialize_gui_config(config) as paths:
        report = Randomizer().run(
            synthetic_source,
            f"gui-{name}",
            move_config_path=paths.moves,
            ability_config_path=paths.abilities,
            ability_profile=paths.ability_profile,
            trainer_config_path=paths.trainers,
            trainer_profile=paths.trainer_profile,
            include_spoilers=False,
        )
    assert report["spoilers_included"] is False
    assert report["starters"] == []
    assert report["trainer_config"]["profile"] == config.trainer_profile
