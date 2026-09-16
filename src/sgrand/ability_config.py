"""Versioned configuration for normal and innate ability randomization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

from .errors import RandomizerError
from .models import Ability

ABILITY_CONFIG_SCHEMA_VERSION = 1
DEFAULT_ABILITY_CONFIG = "abilities-v1.json"
MANDATORY_SPECIES_LOCKED_ABILITIES = frozenset(
    {
        "ABILITY_AS_ONE_ICE_RIDER",
        "ABILITY_AS_ONE_SHADOW_RIDER",
        "ABILITY_BATTLE_BOND",
        "ABILITY_COMMANDER",
        "ABILITY_DISGUISE",
        "ABILITY_EMBODY_ASPECT_CORNERSTONE_MASK",
        "ABILITY_EMBODY_ASPECT_HEARTHFLAME_MASK",
        "ABILITY_EMBODY_ASPECT_TEAL_MASK",
        "ABILITY_EMBODY_ASPECT_WELLSPRING_MASK",
        "ABILITY_FLOWER_GIFT",
        "ABILITY_FORECAST",
        "ABILITY_GULP_MISSILE",
        "ABILITY_HUNGER_SWITCH",
        "ABILITY_ICE_FACE",
        "ABILITY_MULTITYPE",
        "ABILITY_POWER_CONSTRUCT",
        "ABILITY_RKS_SYSTEM",
        "ABILITY_SCHOOLING",
        "ABILITY_SHIELDS_DOWN",
        "ABILITY_STANCE_CHANGE",
        "ABILITY_TERAFORM_ZERO",
        "ABILITY_TERA_SHELL",
        "ABILITY_TERA_SHIFT",
        "ABILITY_ZEN_MODE",
        "ABILITY_ZERO_TO_HERO",
    }
)


@dataclass(frozen=True)
class AbilityRules:
    enabled: bool
    follow_evolutions: bool
    allow_duplicates: bool
    rating_strategy: str
    minimum_ai_rating: int
    maximum_ai_rating: int
    maximum_rating_delta: int
    allow_special_abilities: bool


@dataclass(frozen=True)
class InnateRules(AbilityRules):
    count_mode: str
    fixed_count: int


@dataclass(frozen=True)
class AbilityProfile:
    name: str
    abilities: AbilityRules
    innates: InnateRules


@dataclass(frozen=True)
class AbilityConfig:
    schema_version: int
    default_profile: str
    profile: AbilityProfile
    blacklist: frozenset[str]
    species_locked_abilities: frozenset[str]
    special_abilities: frozenset[str]
    content_sha256: str
    source_label: str


def _object(value: object, context: str, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RandomizerError(f"Ability configuration {context} must be an object")
    result = cast(dict[str, object], value)
    actual = set(result)
    if actual != keys:
        missing = sorted(keys - actual)
        unknown = sorted(actual - keys)
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise RandomizerError(
            f"Invalid keys in ability configuration {context}: {'; '.join(details)}"
        )
    return result


def _boolean(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise RandomizerError(f"Ability configuration {context} must be boolean")
    return value


def _integer(value: object, context: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RandomizerError(f"Ability configuration {context} must be an integer")
    if not minimum <= value <= maximum:
        raise RandomizerError(
            f"Ability configuration {context} must be between {minimum} and {maximum}"
        )
    return value


def _strings(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RandomizerError(f"Ability configuration {context} must be a string array")
    result = tuple(cast(list[str], value))
    if len(result) != len(set(result)):
        raise RandomizerError(f"Ability configuration {context} contains duplicates")
    invalid = [item for item in result if not item.startswith("ABILITY_")]
    if invalid:
        raise RandomizerError(
            f"Ability configuration {context} has invalid constants: {', '.join(invalid)}"
        )
    return result


def _base_rules(raw: dict[str, object], context: str) -> AbilityRules:
    strategy = raw["rating_strategy"]
    if not isinstance(strategy, str) or strategy not in {"similar", "any"}:
        raise RandomizerError(
            f"Ability configuration {context}.rating_strategy must be 'similar' or 'any'"
        )
    minimum = _integer(raw["minimum_ai_rating"], f"{context}.minimum_ai_rating", -20, 20)
    maximum = _integer(raw["maximum_ai_rating"], f"{context}.maximum_ai_rating", -20, 20)
    if minimum > maximum:
        raise RandomizerError(f"Ability configuration {context} rating range is inverted")
    return AbilityRules(
        enabled=_boolean(raw["enabled"], f"{context}.enabled"),
        follow_evolutions=_boolean(raw["follow_evolutions"], f"{context}.follow_evolutions"),
        allow_duplicates=_boolean(raw["allow_duplicates"], f"{context}.allow_duplicates"),
        rating_strategy=strategy,
        minimum_ai_rating=minimum,
        maximum_ai_rating=maximum,
        maximum_rating_delta=_integer(
            raw["maximum_rating_delta"], f"{context}.maximum_rating_delta", 0, 40
        ),
        allow_special_abilities=_boolean(
            raw["allow_special_abilities"], f"{context}.allow_special_abilities"
        ),
    )


def _parse_profile(name: str, value: object) -> AbilityProfile:
    raw = _object(value, f"profiles.{name}", {"abilities", "innates"})
    ability_keys = {
        "enabled",
        "follow_evolutions",
        "allow_duplicates",
        "rating_strategy",
        "minimum_ai_rating",
        "maximum_ai_rating",
        "maximum_rating_delta",
        "allow_special_abilities",
    }
    ability_raw = _object(raw["abilities"], f"profiles.{name}.abilities", ability_keys)
    innate_raw = _object(
        raw["innates"],
        f"profiles.{name}.innates",
        ability_keys | {"count_mode", "fixed_count"},
    )
    count_mode = innate_raw["count_mode"]
    if not isinstance(count_mode, str) or count_mode not in {"vanilla", "fixed"}:
        raise RandomizerError(
            f"Ability configuration profiles.{name}.innates.count_mode must be 'vanilla' or 'fixed'"
        )
    innate_base = _base_rules(innate_raw, f"profiles.{name}.innates")
    return AbilityProfile(
        name=name,
        abilities=_base_rules(ability_raw, f"profiles.{name}.abilities"),
        innates=InnateRules(
            enabled=innate_base.enabled,
            follow_evolutions=innate_base.follow_evolutions,
            allow_duplicates=innate_base.allow_duplicates,
            rating_strategy=innate_base.rating_strategy,
            minimum_ai_rating=innate_base.minimum_ai_rating,
            maximum_ai_rating=innate_base.maximum_ai_rating,
            maximum_rating_delta=innate_base.maximum_rating_delta,
            allow_special_abilities=innate_base.allow_special_abilities,
            count_mode=count_mode,
            fixed_count=_integer(
                innate_raw["fixed_count"], f"profiles.{name}.innates.fixed_count", 0, 3
            ),
        ),
    )


def load_ability_config(path: Path | None = None, profile_name: str | None = None) -> AbilityConfig:
    try:
        if path is None:
            content = files("sgrand").joinpath("configs", DEFAULT_ABILITY_CONFIG).read_bytes()
            source_label = f"embedded:{DEFAULT_ABILITY_CONFIG}"
        else:
            resolved = path.resolve()
            content = resolved.read_bytes()
            source_label = str(resolved)
        document: Any = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RandomizerError(f"Cannot read ability configuration: {exc}") from exc

    raw = _object(
        document,
        "root",
        {
            "schema_version",
            "default_profile",
            "blacklist",
            "species_locked_abilities",
            "special_abilities",
            "profiles",
        },
    )
    version = _integer(raw["schema_version"], "schema_version", 1, 2**31 - 1)
    if version != ABILITY_CONFIG_SCHEMA_VERSION:
        raise RandomizerError(
            f"Unsupported ability configuration schema {version}; "
            f"expected {ABILITY_CONFIG_SCHEMA_VERSION}"
        )
    default_profile = raw["default_profile"]
    if not isinstance(default_profile, str) or not default_profile:
        raise RandomizerError("Ability configuration default_profile must be a non-empty string")
    profiles_raw = raw["profiles"]
    if not isinstance(profiles_raw, dict) or not all(
        isinstance(key, str) and key for key in profiles_raw
    ):
        raise RandomizerError("Ability configuration profiles must be a non-empty object")
    profiles = {
        name: _parse_profile(name, value)
        for name, value in cast(dict[str, object], profiles_raw).items()
    }
    missing_profiles = {"Balanced", "Chaos"} - profiles.keys()
    if missing_profiles:
        raise RandomizerError(
            "Ability configuration must define built-in profiles: "
            + ", ".join(sorted(missing_profiles))
        )
    selected = profile_name or default_profile
    if default_profile not in profiles:
        raise RandomizerError(
            f"Ability configuration default profile {default_profile!r} is not defined"
        )
    if selected not in profiles:
        raise RandomizerError(f"Unknown ability profile {selected!r}")

    locked = frozenset(_strings(raw["species_locked_abilities"], "species_locked_abilities"))
    missing_locked = sorted(MANDATORY_SPECIES_LOCKED_ABILITIES - locked)
    if missing_locked:
        raise RandomizerError(
            "Ability configuration cannot unprotect species-locked abilities: "
            + ", ".join(missing_locked)
        )
    blacklist = frozenset(_strings(raw["blacklist"], "blacklist"))
    special = frozenset(_strings(raw["special_abilities"], "special_abilities"))
    overlap = blacklist & locked
    if overlap:
        raise RandomizerError(
            "Ability configuration blacklist cannot contain protected abilities: "
            + ", ".join(sorted(overlap))
        )
    return AbilityConfig(
        schema_version=version,
        default_profile=default_profile,
        profile=profiles[selected],
        blacklist=blacklist,
        species_locked_abilities=locked,
        special_abilities=special,
        content_sha256=hashlib.sha256(content).hexdigest(),
        source_label=source_label,
    )


def validate_ability_references(
    config: AbilityConfig, abilities: dict[str, Ability], form_locked: frozenset[str]
) -> None:
    referenced = (
        config.blacklist | config.species_locked_abilities | config.special_abilities | form_locked
    )
    unknown = sorted(referenced - abilities.keys())
    if unknown:
        raise RandomizerError(
            "Ability configuration or form tables reference abilities absent from the checkout: "
            + ", ".join(unknown)
        )
