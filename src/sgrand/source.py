"""SoulGold checkout validation and metadata loading."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import cast

from .constants import SUPPORTED_TAG
from .errors import RandomizerError
from .models import Item, Species

REQUIRED_PATHS = (
    "docs/data/romhack-docs.json",
    "src/data/wild_encounters.json",
    "src/data/items.h",
    "include/constants/items.h",
    "src/ui_birch_case.c",
    "data/maps",
)


def exact_git_tag(source: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", "HEAD"],
            cwd=source,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def is_git_checkout(source: Path) -> bool:
    return (source / ".git").exists()


def validate_source(source: Path) -> None:
    if not source.is_dir():
        raise RandomizerError(f"Source checkout is not a directory: {source}")
    missing = [
        str(source / relative) for relative in REQUIRED_PATHS if not (source / relative).exists()
    ]
    if missing:
        raise RandomizerError("Not a compatible SoulGold checkout; missing: " + ", ".join(missing))

    if is_git_checkout(source):
        tag = exact_git_tag(source)
        if tag != SUPPORTED_TAG:
            found = tag or "an untagged commit"
            raise RandomizerError(
                f"Expected tag {SUPPORTED_TAG}, found {found}. Refusing an untested layout."
            )


def _string_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(entry for entry in value if isinstance(entry, str))


def _integer(value: object) -> int:
    if isinstance(value, (str, bytes, bytearray, int, float)):
        return int(value)
    return 0


def load_species(source: Path) -> dict[str, Species]:
    docs_path = source / "docs/data/romhack-docs.json"
    try:
        document = json.loads(docs_path.read_text(encoding="utf-8"))
        raw_species = document["species"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RandomizerError(f"Cannot read species metadata from {docs_path}: {exc}") from exc
    if not isinstance(raw_species, list):
        raise RandomizerError(f"Expected a species array in {docs_path}")

    result: dict[str, Species] = {}
    for value in raw_species:
        if not isinstance(value, dict):
            raise RandomizerError(f"Invalid species entry in {docs_path}")
        entry = cast(dict[str, object], value)
        constant = entry.get("constant")
        if not isinstance(constant, str):
            raise RandomizerError(f"Species entry without a constant in {docs_path}")
        evolutions: list[str] = []
        raw_evolutions = entry.get("evolutions", [])
        if isinstance(raw_evolutions, list):
            for raw_evolution in raw_evolutions:
                if isinstance(raw_evolution, dict) and isinstance(raw_evolution.get("target"), str):
                    evolutions.append(cast(str, raw_evolution["target"]))
        categories = frozenset(_string_list(entry.get("categories")))
        result[constant] = Species(
            constant=constant,
            name=str(entry.get("name") or constant),
            dex=_integer(entry.get("dex")),
            bst=_integer(entry.get("bst")),
            categories=categories,
            evolutions=tuple(evolutions),
        )

    block_re = re.compile(r"\[(SPECIES_[A-Z0-9_]+)\]\s*=\s*\{(.*?)(?=\n\s*\[SPECIES_|\Z)", re.S)
    family_dir = source / "src/data/pokemon/species_info"
    for family_file in sorted(family_dir.glob("gen_*_families.h")):
        text = family_file.read_text(encoding="utf-8")
        for match in block_re.finditer(text):
            constant, block = match.groups()
            if ".isUltraBeast = TRUE" not in block or constant not in result:
                continue
            old = result[constant]
            result[constant] = Species(
                constant=old.constant,
                name=old.name,
                dex=old.dex,
                bst=old.bst,
                categories=old.categories | {"ultra_beast"},
                evolutions=old.evolutions,
            )
    if not result:
        raise RandomizerError(f"No species were found in {docs_path}")
    return result


def parse_items(source: Path) -> dict[str, Item]:
    data_path = source / "src/data/items.h"
    constants_path = source / "include/constants/items.h"
    text = data_path.read_text(encoding="utf-8")
    constants_text = constants_path.read_text(encoding="utf-8")
    item_ids = {
        constant: int(value)
        for constant, value in re.findall(
            r"^\s*(ITEM_[A-Z0-9_]+)\s*=\s*(\d+)\s*,", constants_text, re.M
        )
    }
    pattern = re.compile(r"\[(ITEM_[A-Z0-9_]+)\]\s*=\s*\{(.*?)(?=\n\s*\[ITEM_|\Z)", re.S)
    result: dict[str, Item] = {}
    for match in pattern.finditer(text):
        constant, block = match.groups()
        if constant not in item_ids:
            continue
        pocket_match = re.search(r"\.pocket\s*=\s*(POCKET_[A-Z0-9_]+)", block)
        if not pocket_match:
            continue
        important = bool(re.search(r"\.importance\s*=\s*(?:TRUE|1)\b", block))
        result[constant] = Item(constant, item_ids[constant], pocket_match.group(1), important)
    if not result:
        raise RandomizerError(f"No item metadata was found in {data_path}")
    return result
