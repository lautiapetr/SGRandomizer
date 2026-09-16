"""Versioned and strictly validated move-randomization configuration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from .errors import RandomizerError
from .models import Move

MOVE_CONFIG_SCHEMA_VERSION = 1
DEFAULT_MOVE_CONFIG = "moves-v1.json"
MANDATORY_PROTECTED_MOVES = frozenset(
    {
        "MOVE_CUT",
        "MOVE_DIVE",
        "MOVE_FLASH",
        "MOVE_FLY",
        "MOVE_ROCK_CLIMB",
        "MOVE_ROCK_SMASH",
        "MOVE_STRENGTH",
        "MOVE_SURF",
        "MOVE_WATERFALL",
        "MOVE_WHIRLPOOL",
    }
)


@dataclass(frozen=True)
class PowerBand:
    through_level: int
    minimum: int
    maximum: int


@dataclass(frozen=True)
class LearnsetRules:
    enabled: bool
    source_files: tuple[str, ...]
    offensive_percent: int
    stab_percent: int
    category_match_percent: int
    minimum_accuracy: int
    preserve_signature_moves: bool
    early_attack_level: int
    progressive_power: tuple[PowerBand, ...]


@dataclass(frozen=True)
class CompatibilityRules:
    enabled: bool
    tm_percent: int
    tutor_percent: int
    stab_bonus_percent: int
    category_match_bonus_percent: int
    preserve_protected_moves: bool
    preserve_signature_moves: bool


@dataclass(frozen=True)
class PropertyRules:
    enabled: bool
    power_variation_percent: int
    minimum_power: int
    maximum_power: int
    power_step: int
    minimum_accuracy: int
    maximum_accuracy: int
    accuracy_step: int
    minimum_pp: int
    maximum_pp: int
    pp_step: int
    randomize_type: bool
    randomize_category: bool
    types: tuple[str, ...]


@dataclass(frozen=True)
class MoveConfig:
    schema_version: int
    profile: str
    protected_moves: frozenset[str]
    signature_moves: frozenset[str]
    excluded_moves: frozenset[str]
    learnsets: LearnsetRules
    compatibility: CompatibilityRules
    properties: PropertyRules
    content_sha256: str
    source_label: str


def _object(value: object, context: str, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RandomizerError(f"Move configuration {context} must be an object")
    result = cast(dict[str, object], value)
    actual = set(result)
    if actual != keys:
        missing = sorted(keys - actual)
        unknown = sorted(actual - keys)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise RandomizerError(f"Invalid keys in move configuration {context}: {'; '.join(details)}")
    return result


def _integer(value: object, context: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RandomizerError(f"Move configuration {context} must be an integer")
    if not minimum <= value <= maximum:
        raise RandomizerError(
            f"Move configuration {context} must be between {minimum} and {maximum}"
        )
    return value


def _boolean(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise RandomizerError(f"Move configuration {context} must be boolean")
    return value


def _strings(value: object, context: str, prefix: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(entry, str) for entry in value):
        raise RandomizerError(f"Move configuration {context} must be a string array")
    result = tuple(cast(list[str], value))
    if len(set(result)) != len(result):
        raise RandomizerError(f"Move configuration {context} contains duplicates")
    invalid = [entry for entry in result if not entry.startswith(prefix)]
    if invalid:
        raise RandomizerError(
            f"Move configuration {context} has invalid constants: {', '.join(invalid)}"
        )
    return result


def _parse_learnsets(value: object) -> LearnsetRules:
    raw = _object(
        value,
        "learnsets",
        {
            "enabled",
            "source_files",
            "offensive_percent",
            "stab_percent",
            "category_match_percent",
            "minimum_accuracy",
            "preserve_signature_moves",
            "early_attack_level",
            "progressive_power",
        },
    )
    source_files = _strings(raw["source_files"], "learnsets.source_files", "gen_")
    if not source_files or any(
        "/" in name or "\\" in name or not name.endswith(".h") for name in source_files
    ):
        raise RandomizerError("Move configuration learnsets.source_files has an unsafe filename")
    raw_bands = raw["progressive_power"]
    if not isinstance(raw_bands, list) or not raw_bands:
        raise RandomizerError("Move configuration learnsets.progressive_power must be non-empty")
    bands: list[PowerBand] = []
    previous_level = -1
    for index, raw_band in enumerate(raw_bands):
        band = _object(
            raw_band,
            f"learnsets.progressive_power[{index}]",
            {"through_level", "minimum", "maximum"},
        )
        through = _integer(band["through_level"], "progressive_power.through_level", 0, 100)
        minimum = _integer(band["minimum"], "progressive_power.minimum", 1, 250)
        maximum = _integer(band["maximum"], "progressive_power.maximum", 1, 250)
        if through <= previous_level or minimum > maximum:
            raise RandomizerError("Move configuration progressive power bands are not ordered")
        bands.append(PowerBand(through, minimum, maximum))
        previous_level = through
    if bands[-1].through_level != 100:
        raise RandomizerError("The final progressive power band must reach level 100")
    return LearnsetRules(
        enabled=_boolean(raw["enabled"], "learnsets.enabled"),
        source_files=source_files,
        offensive_percent=_integer(raw["offensive_percent"], "learnsets.offensive_percent", 0, 100),
        stab_percent=_integer(raw["stab_percent"], "learnsets.stab_percent", 0, 100),
        category_match_percent=_integer(
            raw["category_match_percent"], "learnsets.category_match_percent", 0, 100
        ),
        minimum_accuracy=_integer(raw["minimum_accuracy"], "learnsets.minimum_accuracy", 1, 100),
        preserve_signature_moves=_boolean(
            raw["preserve_signature_moves"], "learnsets.preserve_signature_moves"
        ),
        early_attack_level=_integer(
            raw["early_attack_level"], "learnsets.early_attack_level", 1, 20
        ),
        progressive_power=tuple(bands),
    )


def _parse_compatibility(value: object) -> CompatibilityRules:
    raw = _object(
        value,
        "compatibility",
        {
            "enabled",
            "tm_percent",
            "tutor_percent",
            "stab_bonus_percent",
            "category_match_bonus_percent",
            "preserve_protected_moves",
            "preserve_signature_moves",
        },
    )
    return CompatibilityRules(
        enabled=_boolean(raw["enabled"], "compatibility.enabled"),
        tm_percent=_integer(raw["tm_percent"], "compatibility.tm_percent", 0, 100),
        tutor_percent=_integer(raw["tutor_percent"], "compatibility.tutor_percent", 0, 100),
        stab_bonus_percent=_integer(
            raw["stab_bonus_percent"], "compatibility.stab_bonus_percent", 0, 100
        ),
        category_match_bonus_percent=_integer(
            raw["category_match_bonus_percent"],
            "compatibility.category_match_bonus_percent",
            0,
            100,
        ),
        preserve_protected_moves=_boolean(
            raw["preserve_protected_moves"], "compatibility.preserve_protected_moves"
        ),
        preserve_signature_moves=_boolean(
            raw["preserve_signature_moves"], "compatibility.preserve_signature_moves"
        ),
    )


def _parse_properties(value: object) -> PropertyRules:
    keys = {
        "enabled",
        "power_variation_percent",
        "minimum_power",
        "maximum_power",
        "power_step",
        "minimum_accuracy",
        "maximum_accuracy",
        "accuracy_step",
        "minimum_pp",
        "maximum_pp",
        "pp_step",
        "randomize_type",
        "randomize_category",
        "types",
    }
    raw = _object(value, "properties", keys)
    minimum_power = _integer(raw["minimum_power"], "properties.minimum_power", 1, 250)
    maximum_power = _integer(raw["maximum_power"], "properties.maximum_power", 1, 250)
    minimum_accuracy = _integer(raw["minimum_accuracy"], "properties.minimum_accuracy", 1, 100)
    maximum_accuracy = _integer(raw["maximum_accuracy"], "properties.maximum_accuracy", 1, 100)
    minimum_pp = _integer(raw["minimum_pp"], "properties.minimum_pp", 1, 64)
    maximum_pp = _integer(raw["maximum_pp"], "properties.maximum_pp", 1, 64)
    if (
        minimum_power > maximum_power
        or minimum_accuracy > maximum_accuracy
        or minimum_pp > maximum_pp
    ):
        raise RandomizerError("Move configuration property ranges are inverted")
    move_types = _strings(raw["types"], "properties.types", "TYPE_")
    if not move_types:
        raise RandomizerError("Move configuration properties.types must be non-empty")
    return PropertyRules(
        enabled=_boolean(raw["enabled"], "properties.enabled"),
        power_variation_percent=_integer(
            raw["power_variation_percent"], "properties.power_variation_percent", 0, 100
        ),
        minimum_power=minimum_power,
        maximum_power=maximum_power,
        power_step=_integer(raw["power_step"], "properties.power_step", 1, 50),
        minimum_accuracy=minimum_accuracy,
        maximum_accuracy=maximum_accuracy,
        accuracy_step=_integer(raw["accuracy_step"], "properties.accuracy_step", 1, 25),
        minimum_pp=minimum_pp,
        maximum_pp=maximum_pp,
        pp_step=_integer(raw["pp_step"], "properties.pp_step", 1, 20),
        randomize_type=_boolean(raw["randomize_type"], "properties.randomize_type"),
        randomize_category=_boolean(raw["randomize_category"], "properties.randomize_category"),
        types=move_types,
    )


def load_move_config(path: Path | None = None) -> MoveConfig:
    try:
        if path is None:
            content = files("sgrand").joinpath("configs", DEFAULT_MOVE_CONFIG).read_bytes()
            source_label = f"embedded:{DEFAULT_MOVE_CONFIG}"
        else:
            resolved = path.resolve()
            content = resolved.read_bytes()
            source_label = str(resolved)
        document: Any = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RandomizerError(f"Cannot read move configuration: {exc}") from exc
    raw = _object(
        document,
        "root",
        {
            "schema_version",
            "profile",
            "protected_moves",
            "signature_moves",
            "excluded_moves",
            "learnsets",
            "compatibility",
            "properties",
        },
    )
    version = _integer(raw["schema_version"], "schema_version", 1, 2**31 - 1)
    if version != MOVE_CONFIG_SCHEMA_VERSION:
        raise RandomizerError(
            f"Unsupported move configuration schema {version}; "
            f"expected {MOVE_CONFIG_SCHEMA_VERSION}"
        )
    profile = raw["profile"]
    if not isinstance(profile, str) or not profile.strip():
        raise RandomizerError("Move configuration profile must be a non-empty string")
    protected = frozenset(_strings(raw["protected_moves"], "protected_moves", "MOVE_"))
    missing_mandatory = sorted(MANDATORY_PROTECTED_MOVES - protected)
    if missing_mandatory:
        raise RandomizerError(
            "Move configuration cannot unprotect progression moves: " + ", ".join(missing_mandatory)
        )
    signature = frozenset(_strings(raw["signature_moves"], "signature_moves", "MOVE_"))
    excluded = frozenset(_strings(raw["excluded_moves"], "excluded_moves", "MOVE_"))
    overlap = (protected & signature) | (protected & excluded) | (signature & excluded)
    if overlap:
        raise RandomizerError(
            "Move configuration protection/signature/exclusion lists overlap: "
            + ", ".join(sorted(overlap))
        )
    learnsets = _parse_learnsets(raw["learnsets"])
    compatibility = _parse_compatibility(raw["compatibility"])
    properties = _parse_properties(raw["properties"])
    if not compatibility.preserve_protected_moves:
        raise RandomizerError("Move configuration must preserve protected TM/tutor compatibility")
    return MoveConfig(
        schema_version=version,
        profile=profile,
        protected_moves=protected,
        signature_moves=signature,
        excluded_moves=excluded,
        learnsets=learnsets,
        compatibility=compatibility,
        properties=properties,
        content_sha256=hashlib.sha256(content).hexdigest(),
        source_label=source_label,
    )


def validate_move_references(config: MoveConfig, moves: dict[str, Move]) -> None:
    referenced = config.protected_moves | config.signature_moves | config.excluded_moves
    unknown = sorted(referenced - moves.keys())
    if unknown:
        raise RandomizerError(
            "Move configuration references moves absent from the checkout: " + ", ".join(unknown)
        )
