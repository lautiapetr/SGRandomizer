"""Versioned configuration for trainer-party randomization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from .errors import RandomizerError
from .models import Item, Move, Species

TRAINER_CONFIG_SCHEMA_VERSION = 1
DEFAULT_TRAINER_CONFIG = "trainers-v1.json"
TRAINER_CATEGORIES = ("trainers", "leaders", "rival", "bosses")


@dataclass(frozen=True)
class TrainerRules:
    enabled: bool
    maximum_bst_delta: int
    level_mode: str
    level_percent: int
    level_offset: int
    fixed_level: int
    minimum_level: int
    maximum_level: int
    team_size_mode: str
    fixed_team_size: int
    minimum_team_size: int
    maximum_team_size: int
    theme_mode: str
    theme_percent: int
    moves_mode: str
    held_items_mode: str
    held_item_percent: int
    allow_legendaries: bool
    legendary_percent: int
    allow_duplicates: bool
    double_synergy: bool


@dataclass(frozen=True)
class TrainerProfile:
    name: str
    categories: dict[str, TrainerRules]


@dataclass(frozen=True)
class TrainerConfig:
    schema_version: int
    default_profile: str
    profile: TrainerProfile
    blacklist_species: frozenset[str]
    blacklist_moves: frozenset[str]
    blacklist_items: frozenset[str]
    held_item_allowlist: frozenset[str]
    boss_classes: frozenset[str]
    content_sha256: str
    source_label: str


RULE_KEYS = {
    "enabled",
    "maximum_bst_delta",
    "level_mode",
    "level_percent",
    "level_offset",
    "fixed_level",
    "minimum_level",
    "maximum_level",
    "team_size_mode",
    "fixed_team_size",
    "minimum_team_size",
    "maximum_team_size",
    "theme_mode",
    "theme_percent",
    "moves_mode",
    "held_items_mode",
    "held_item_percent",
    "allow_legendaries",
    "legendary_percent",
    "allow_duplicates",
    "double_synergy",
}


def _object(value: object, context: str, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RandomizerError(f"Trainer configuration {context} must be an object")
    result = cast(dict[str, object], value)
    actual = set(result)
    if actual != keys:
        missing = sorted(keys - actual)
        unknown = sorted(actual - keys)
        details = (["missing " + ", ".join(missing)] if missing else []) + (
            ["unknown " + ", ".join(unknown)] if unknown else []
        )
        raise RandomizerError(
            f"Invalid keys in trainer configuration {context}: {'; '.join(details)}"
        )
    return result


def _integer(value: object, context: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RandomizerError(f"Trainer configuration {context} must be an integer")
    if not minimum <= value <= maximum:
        raise RandomizerError(
            f"Trainer configuration {context} must be between {minimum} and {maximum}"
        )
    return value


def _boolean(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise RandomizerError(f"Trainer configuration {context} must be boolean")
    return value


def _choice(value: object, context: str, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise RandomizerError(
            f"Trainer configuration {context} must be one of {', '.join(sorted(choices))}"
        )
    return value


def _strings(value: object, context: str, prefix: str | None = None) -> frozenset[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RandomizerError(f"Trainer configuration {context} must be a string array")
    strings = cast(list[str], value)
    if len(strings) != len(set(strings)):
        raise RandomizerError(f"Trainer configuration {context} contains duplicates")
    if prefix is not None and any(not item.startswith(prefix) for item in strings):
        raise RandomizerError(f"Trainer configuration {context} entries must start with {prefix}")
    return frozenset(strings)


def _rules(value: object, context: str) -> TrainerRules:
    raw = _object(value, context, RULE_KEYS)
    minimum_level = _integer(raw["minimum_level"], f"{context}.minimum_level", 1, 100)
    maximum_level = _integer(raw["maximum_level"], f"{context}.maximum_level", 1, 100)
    minimum_team = _integer(raw["minimum_team_size"], f"{context}.minimum_team_size", 1, 6)
    maximum_team = _integer(raw["maximum_team_size"], f"{context}.maximum_team_size", 1, 6)
    if minimum_level > maximum_level:
        raise RandomizerError(f"Trainer configuration {context} level range is inverted")
    if minimum_team > maximum_team:
        raise RandomizerError(f"Trainer configuration {context} team-size range is inverted")
    return TrainerRules(
        enabled=_boolean(raw["enabled"], f"{context}.enabled"),
        maximum_bst_delta=_integer(
            raw["maximum_bst_delta"], f"{context}.maximum_bst_delta", 0, 2000
        ),
        level_mode=_choice(
            raw["level_mode"], f"{context}.level_mode", {"vanilla", "scaled", "fixed"}
        ),
        level_percent=_integer(raw["level_percent"], f"{context}.level_percent", 1, 500),
        level_offset=_integer(raw["level_offset"], f"{context}.level_offset", -99, 99),
        fixed_level=_integer(raw["fixed_level"], f"{context}.fixed_level", 1, 100),
        minimum_level=minimum_level,
        maximum_level=maximum_level,
        team_size_mode=_choice(
            raw["team_size_mode"],
            f"{context}.team_size_mode",
            {"vanilla", "fixed", "range"},
        ),
        fixed_team_size=_integer(raw["fixed_team_size"], f"{context}.fixed_team_size", 1, 6),
        minimum_team_size=minimum_team,
        maximum_team_size=maximum_team,
        theme_mode=_choice(
            raw["theme_mode"], f"{context}.theme_mode", {"none", "vanilla", "random"}
        ),
        theme_percent=_integer(raw["theme_percent"], f"{context}.theme_percent", 0, 100),
        moves_mode=_choice(raw["moves_mode"], f"{context}.moves_mode", {"preserve", "legal"}),
        held_items_mode=_choice(
            raw["held_items_mode"],
            f"{context}.held_items_mode",
            {"preserve", "random", "none"},
        ),
        held_item_percent=_integer(
            raw["held_item_percent"], f"{context}.held_item_percent", 0, 100
        ),
        allow_legendaries=_boolean(raw["allow_legendaries"], f"{context}.allow_legendaries"),
        legendary_percent=_integer(
            raw["legendary_percent"], f"{context}.legendary_percent", 0, 100
        ),
        allow_duplicates=_boolean(raw["allow_duplicates"], f"{context}.allow_duplicates"),
        double_synergy=_boolean(raw["double_synergy"], f"{context}.double_synergy"),
    )


def load_trainer_config(path: Path | None = None, profile_name: str | None = None) -> TrainerConfig:
    try:
        if path is None:
            content = files("sgrand").joinpath("configs", DEFAULT_TRAINER_CONFIG).read_bytes()
            source_label = f"embedded:{DEFAULT_TRAINER_CONFIG}"
        else:
            resolved = path.resolve()
            content = resolved.read_bytes()
            source_label = str(resolved)
        document: Any = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RandomizerError(f"Cannot read trainer configuration: {exc}") from exc

    raw = _object(
        document,
        "root",
        {
            "schema_version",
            "default_profile",
            "blacklist_species",
            "blacklist_moves",
            "blacklist_items",
            "held_item_allowlist",
            "boss_classes",
            "profiles",
        },
    )
    version = _integer(raw["schema_version"], "schema_version", 1, 2**31 - 1)
    if version != TRAINER_CONFIG_SCHEMA_VERSION:
        raise RandomizerError(
            f"Unsupported trainer configuration schema {version}; "
            f"expected {TRAINER_CONFIG_SCHEMA_VERSION}"
        )
    default_profile = raw["default_profile"]
    if not isinstance(default_profile, str) or not default_profile:
        raise RandomizerError("Trainer configuration default_profile must be non-empty")
    profiles_raw = raw["profiles"]
    if not isinstance(profiles_raw, dict) or not profiles_raw:
        raise RandomizerError("Trainer configuration profiles must be a non-empty object")
    profiles: dict[str, TrainerProfile] = {}
    for name, value in cast(dict[str, object], profiles_raw).items():
        profile_raw = _object(value, f"profiles.{name}", set(TRAINER_CATEGORIES))
        profiles[name] = TrainerProfile(
            name=name,
            categories={
                category: _rules(profile_raw[category], f"profiles.{name}.{category}")
                for category in TRAINER_CATEGORIES
            },
        )
    missing = {"Balanced", "Chaos"} - profiles.keys()
    if missing:
        raise RandomizerError(
            "Trainer configuration must define built-in profiles: " + ", ".join(sorted(missing))
        )
    selected = profile_name or default_profile
    if default_profile not in profiles:
        raise RandomizerError(f"Trainer default profile {default_profile!r} is not defined")
    if selected not in profiles:
        raise RandomizerError(f"Unknown trainer profile {selected!r}")
    return TrainerConfig(
        schema_version=version,
        default_profile=default_profile,
        profile=profiles[selected],
        blacklist_species=_strings(raw["blacklist_species"], "blacklist_species", "SPECIES_"),
        blacklist_moves=_strings(raw["blacklist_moves"], "blacklist_moves", "MOVE_"),
        blacklist_items=_strings(raw["blacklist_items"], "blacklist_items", "ITEM_"),
        held_item_allowlist=_strings(raw["held_item_allowlist"], "held_item_allowlist", "ITEM_"),
        boss_classes=_strings(raw["boss_classes"], "boss_classes"),
        content_sha256=hashlib.sha256(content).hexdigest(),
        source_label=source_label,
    )


def validate_trainer_references(
    config: TrainerConfig,
    species: dict[str, Species],
    moves: dict[str, Move],
    items: dict[str, Item],
) -> None:
    checks = (
        (config.blacklist_species, species.keys(), "species"),
        (config.blacklist_moves, moves.keys(), "moves"),
        (config.blacklist_items | config.held_item_allowlist, items.keys(), "items"),
    )
    for referenced, available, label in checks:
        unknown = sorted(referenced - available)
        if unknown:
            raise RandomizerError(
                f"Trainer configuration references unknown {label}: {', '.join(unknown)}"
            )
