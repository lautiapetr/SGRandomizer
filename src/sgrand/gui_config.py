"""Versioned GUI workspace configuration and built-in presets."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

from .ability_config import load_ability_config
from .errors import RandomizerError
from .move_config import load_move_config
from .trainer_config import load_trainer_config

GUI_CONFIG_SCHEMA_VERSION = 1
PRESET_NAMES = ("Vanilla+", "Balanced", "Chaos", "Custom")
GUI_CONFIG_KEYS = {
    "schema_version",
    "preset",
    "spoiler_free",
    "ability_profile",
    "trainer_profile",
    "moves",
    "abilities",
    "trainers",
}


@dataclass(frozen=True)
class GuiConfig:
    schema_version: int
    preset: str
    spoiler_free: bool
    ability_profile: str
    trainer_profile: str
    moves: dict[str, Any]
    abilities: dict[str, Any]
    trainers: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "preset": self.preset,
            "spoiler_free": self.spoiler_free,
            "ability_profile": self.ability_profile,
            "trainer_profile": self.trainer_profile,
            "moves": copy.deepcopy(self.moves),
            "abilities": copy.deepcopy(self.abilities),
            "trainers": copy.deepcopy(self.trainers),
        }


@dataclass(frozen=True)
class MaterializedGuiConfig:
    moves: Path
    abilities: Path
    trainers: Path
    ability_profile: str
    trainer_profile: str


def _embedded_document(name: str) -> dict[str, Any]:
    raw = files("sgrand").joinpath("configs", name).read_text(encoding="utf-8")
    document = json.loads(raw)
    if not isinstance(document, dict):  # pragma: no cover - shipped resources are tested
        raise RandomizerError(f"Embedded configuration {name} is not an object")
    return cast(dict[str, Any], document)


def _vanilla_plus(
    moves: dict[str, Any], abilities: dict[str, Any], trainers: dict[str, Any]
) -> tuple[str, str]:
    moves["profile"] = "Vanilla+"
    moves["learnsets"]["enabled"] = False
    moves["compatibility"]["enabled"] = False
    moves["properties"]["enabled"] = False

    balanced_abilities = copy.deepcopy(abilities["profiles"]["Balanced"])
    balanced_abilities["abilities"]["enabled"] = False
    balanced_abilities["innates"]["enabled"] = False
    abilities["profiles"]["Vanilla+"] = balanced_abilities
    abilities["default_profile"] = "Vanilla+"

    vanilla_trainers = copy.deepcopy(trainers["profiles"]["Balanced"])
    for rules in vanilla_trainers.values():
        rules["enabled"] = False
    trainers["profiles"]["Vanilla+"] = vanilla_trainers
    trainers["default_profile"] = "Vanilla+"
    return "Vanilla+", "Vanilla+"


def _chaos(moves: dict[str, Any], abilities: dict[str, Any], trainers: dict[str, Any]) -> None:
    moves["profile"] = "Chaos"
    moves["learnsets"].update(
        {
            "offensive_percent": 80,
            "stab_percent": 35,
            "category_match_percent": 45,
            "minimum_accuracy": 50,
        }
    )
    moves["compatibility"].update({"tm_percent": 75, "tutor_percent": 70})
    moves["properties"].update(
        {
            "power_variation_percent": 60,
            "minimum_accuracy": 50,
            "minimum_pp": 1,
            "maximum_pp": 48,
        }
    )
    abilities["default_profile"] = "Chaos"
    trainers["default_profile"] = "Chaos"


def preset_config(name: str, *, spoiler_free: bool = False) -> GuiConfig:
    """Return an isolated, fully versioned configuration for a GUI preset."""
    if name not in PRESET_NAMES:
        raise RandomizerError(f"Unknown GUI preset {name!r}")
    moves = _embedded_document("moves-v1.json")
    abilities = _embedded_document("abilities-v1.json")
    trainers = _embedded_document("trainers-v1.json")
    ability_profile = "Balanced"
    trainer_profile = "Balanced"
    if name == "Vanilla+":
        ability_profile, trainer_profile = _vanilla_plus(moves, abilities, trainers)
    elif name == "Chaos":
        _chaos(moves, abilities, trainers)
        ability_profile = trainer_profile = "Chaos"
    # Custom starts from the safe Balanced baseline and becomes distinct on export.
    result = GuiConfig(
        schema_version=GUI_CONFIG_SCHEMA_VERSION,
        preset=name,
        spoiler_free=spoiler_free,
        ability_profile=ability_profile,
        trainer_profile=trainer_profile,
        moves=moves,
        abilities=abilities,
        trainers=trainers,
    )
    validate_gui_config(result)
    return result


def _string(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str) or not value.strip():
        raise RandomizerError(f"GUI configuration {key} must be a non-empty string")
    return value


def gui_config_from_dict(document: object) -> GuiConfig:
    if not isinstance(document, dict):
        raise RandomizerError("GUI configuration root must be an object")
    raw = cast(dict[str, object], document)
    actual = set(raw)
    if actual != GUI_CONFIG_KEYS:
        missing = sorted(GUI_CONFIG_KEYS - actual)
        unknown = sorted(actual - GUI_CONFIG_KEYS)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise RandomizerError("Invalid GUI configuration keys: " + "; ".join(details))
    version = raw["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise RandomizerError("GUI configuration schema_version must be an integer")
    if version != GUI_CONFIG_SCHEMA_VERSION:
        raise RandomizerError(
            f"Unsupported GUI configuration schema {version}; expected {GUI_CONFIG_SCHEMA_VERSION}"
        )
    preset = _string(raw, "preset")
    if preset not in PRESET_NAMES:
        raise RandomizerError(f"Unknown GUI preset {preset!r}")
    spoiler_free = raw["spoiler_free"]
    if not isinstance(spoiler_free, bool):
        raise RandomizerError("GUI configuration spoiler_free must be boolean")
    sections: dict[str, dict[str, Any]] = {}
    for key in ("moves", "abilities", "trainers"):
        value = raw[key]
        if not isinstance(value, dict):
            raise RandomizerError(f"GUI configuration {key} must be an object")
        sections[key] = copy.deepcopy(cast(dict[str, Any], value))
    result = GuiConfig(
        schema_version=version,
        preset=preset,
        spoiler_free=spoiler_free,
        ability_profile=_string(raw, "ability_profile"),
        trainer_profile=_string(raw, "trainer_profile"),
        moves=sections["moves"],
        abilities=sections["abilities"],
        trainers=sections["trainers"],
    )
    validate_gui_config(result)
    return result


def load_gui_config(path: Path) -> GuiConfig:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RandomizerError(f"Cannot read GUI configuration: {exc}") from exc
    return gui_config_from_dict(document)


def save_gui_config(config: GuiConfig, path: Path) -> None:
    validate_gui_config(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(config.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


@contextmanager
def materialize_gui_config(config: GuiConfig) -> Iterator[MaterializedGuiConfig]:
    """Write engine-specific documents to a private temporary directory."""
    validate_gui_config(config)
    with TemporaryDirectory(prefix="sgrand-config-") as temporary:
        root = Path(temporary)
        paths: dict[str, Path] = {}
        for key, document in (
            ("moves", config.moves),
            ("abilities", config.abilities),
            ("trainers", config.trainers),
        ):
            path = root / f"{key}.json"
            path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            paths[key] = path
        yield MaterializedGuiConfig(
            moves=paths["moves"],
            abilities=paths["abilities"],
            trainers=paths["trainers"],
            ability_profile=config.ability_profile,
            trainer_profile=config.trainer_profile,
        )


def validate_gui_config(config: GuiConfig) -> None:
    if config.schema_version != GUI_CONFIG_SCHEMA_VERSION:
        raise RandomizerError(
            f"Unsupported GUI configuration schema {config.schema_version}; "
            f"expected {GUI_CONFIG_SCHEMA_VERSION}"
        )
    if config.preset not in PRESET_NAMES:
        raise RandomizerError(f"Unknown GUI preset {config.preset!r}")
    with TemporaryDirectory(prefix="sgrand-config-validation-") as temporary:
        root = Path(temporary)
        move_path = root / "moves.json"
        ability_path = root / "abilities.json"
        trainer_path = root / "trainers.json"
        move_path.write_text(json.dumps(config.moves), encoding="utf-8")
        ability_path.write_text(json.dumps(config.abilities), encoding="utf-8")
        trainer_path.write_text(json.dumps(config.trainers), encoding="utf-8")
        load_move_config(move_path)
        load_ability_config(ability_path, config.ability_profile)
        load_trainer_config(trainer_path, config.trainer_profile)
