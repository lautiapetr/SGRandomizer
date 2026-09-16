"""Pure transformations for the phase-1 subsystems."""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

from .constants import PROTECTED_SCRIPTED_ITEM_GIFTS
from .errors import RandomizerError
from .models import Item, Species
from .species import graph_data, safe_species

MON_COMMAND_RE = re.compile(
    r"(?P<prefix>\b(?P<command>givemon|giveegg|setwildbattle)\s*\(?\s*)"
    r"(?P<species>SPECIES_[A-Z0-9_]+)"
)
ITEM_COMMAND_RE = re.compile(
    r"(?P<prefix>\b(?P<command>giveitem|finditem)\s*\(?\s*)(?P<item>ITEM_[A-Z0-9_]+)"
)


def replace_starters(text: str, starters: list[str]) -> tuple[str, list[dict[str, str]]]:
    pattern = re.compile(
        r"(?P<prefix>\[BALL_[A-Z_]+\]\s*=\s*\{)"
        r"(?P<species>SPECIES_[A-Z0-9_]+)"
        r"(?P<suffix>\s*,\s*5\s*,\s*[012]\s*\})"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 9:
        raise RandomizerError(f"Expected 9 starter slots, found {len(matches)}")
    iterator = iter(starters)
    changes: list[dict[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        new = next(iterator)
        changes.append(
            {
                "slot": match.group(0).split("]", 1)[0][1:],
                "from": match.group("species"),
                "to": new,
            }
        )
        return match.group("prefix") + new + match.group("suffix")

    return pattern.sub(replace, text), changes


def transform_wild_encounters(
    raw: dict[str, Any], mapping: dict[str, str], species: dict[str, Species]
) -> tuple[dict[str, Any], list[dict[str, object]]]:
    changes: list[dict[str, object]] = []
    groups = raw.get("wild_encounter_groups", [])
    if not isinstance(groups, list):
        raise RandomizerError("wild_encounter_groups must be an array")
    for group in groups:
        if not isinstance(group, dict):
            continue
        encounters = group.get("encounters", [])
        if not isinstance(encounters, list):
            continue
        for encounter in encounters:
            if not isinstance(encounter, dict):
                continue
            map_name = encounter.get("map", "UNKNOWN")
            for field, info in encounter.items():
                if not field.endswith("_mons") or not isinstance(info, dict):
                    continue
                mons = info.get("mons", [])
                if not isinstance(mons, list):
                    continue
                for slot, mon in enumerate(mons):
                    if not isinstance(mon, dict):
                        continue
                    old = mon.get("species")
                    if not isinstance(old, str) or old not in mapping:
                        continue
                    new = mapping[old]
                    if new == old:
                        continue
                    mon["species"] = new
                    changes.append(
                        {
                            "map": str(map_name),
                            "method": field,
                            "slot": slot,
                            "from": old,
                            "to": new,
                            "bst_delta": species[new].bst - species[old].bst,
                        }
                    )
    return raw, changes


def script_source_files(source: Path) -> list[Path]:
    files: list[Path] = []
    for map_dir in sorted((source / "data/maps").iterdir()):
        if not map_dir.is_dir():
            continue
        pory = map_dir / "scripts.pory"
        inc = map_dir / "scripts.inc"
        if pory.exists():
            files.append(pory)
        elif inc.exists():
            files.append(inc)
    for inc in sorted((source / "data/scripts").glob("*.inc")):
        if inc.name != "debug.inc":
            files.append(inc)
    return files


def normalize_changed_lines(original: str, updated: str) -> str:
    original_lines = original.splitlines(keepends=True)
    updated_lines = updated.splitlines(keepends=True)
    if len(original_lines) != len(updated_lines):
        return updated
    cleaned: list[str] = []
    for old_line, new_line in zip(original_lines, updated_lines, strict=True):
        if old_line == new_line:
            cleaned.append(new_line)
            continue
        newline = "\n" if new_line.endswith("\n") else ""
        body = new_line[:-1] if newline else new_line
        body = body.rstrip(" \t\r")
        indent_match = re.match(r"[ \t]*", body)
        assert indent_match is not None
        indent = indent_match.group(0)
        if "\t" in indent and " " in indent:
            body = indent.expandtabs(4) + body[len(indent) :]
        cleaned.append(body + newline)
    return "".join(cleaned)


def scripted_item_quantity(match: re.Match[str]) -> int:
    line_end = match.string.find("\n", match.end())
    if line_end == -1:
        line_end = len(match.string)
    remainder = match.string[match.end() : line_end]
    quantity = re.match(r"\s*,\s*(\d+)", remainder)
    return int(quantity.group(1)) if quantity else 1


def transform_scripts(
    source: Path,
    mapping: dict[str, str],
    species: dict[str, Species],
    items: dict[str, Item],
    item_pool: list[str],
    duplicate_gift_rng: random.Random,
    scripted_item_rng: random.Random,
) -> tuple[dict[Path, str], list[dict[str, object]], list[dict[str, object]]]:
    changed_files: dict[Path, str] = {}
    mon_changes: list[dict[str, object]] = []
    item_changes: list[dict[str, object]] = []
    children, parents = graph_data(species)

    for path in script_source_files(source):
        relative = path.relative_to(source).as_posix()
        text = path.read_text(encoding="utf-8")
        allow_mon_changes = "LittlerootTown_ProfessorBirchsLab" not in relative

        def replace_mon(
            match: re.Match[str],
            *,
            relative_path: str = relative,
            allow_changes: bool = allow_mon_changes,
        ) -> str:
            old = match.group("species")
            if not allow_changes or old not in species:
                return match.group(0)
            new = mapping.get(old, old)
            if new == old:
                return match.group(0)
            mon_changes.append(
                {
                    "file": relative_path,
                    "command": match.group("command"),
                    "from": old,
                    "to": new,
                    "bst_delta": species[new].bst - species[old].bst,
                }
            )
            return match.group("prefix") + new

        updated = MON_COMMAND_RE.sub(replace_mon, text)
        variable_gifts = set(re.findall(r"\bgivemon\s*\(?\s*(VAR_[A-Z0-9_]+)", text))
        used_targets: set[str] = set()
        for variable in sorted(variable_gifts):
            assignment_re = re.compile(
                rf"\bsetvar\s*\(?\s*{re.escape(variable)}\s*,\s*(SPECIES_[A-Z0-9_]+)"
            )
            for old in sorted(set(assignment_re.findall(text))):
                if old not in species:
                    continue
                old_mon = species[old]
                if old_mon.is_special or "ultra_beast" in old_mon.categories:
                    continue
                new = mapping.get(old, old)
                if new == old or new in used_targets:
                    tolerance = max(40, round(old_mon.bst * 0.12))
                    old_stage = (bool(parents[old]), bool(children[old]))
                    candidates = [
                        constant
                        for constant, mon in species.items()
                        if safe_species(mon)
                        and not mon.is_special
                        and "ultra_beast" not in mon.categories
                        and constant != old
                        and constant not in used_targets
                        and (bool(parents[constant]), bool(children[constant])) == old_stage
                        and abs(old_mon.bst - mon.bst) <= tolerance
                    ]
                    candidates.sort(
                        key=lambda constant: (abs(old_mon.bst - species[constant].bst), constant)
                    )
                    if candidates:
                        best_delta = abs(old_mon.bst - species[candidates[0]].bst)
                        close = [
                            constant
                            for constant in candidates
                            if abs(old_mon.bst - species[constant].bst) <= best_delta + 10
                        ]
                        new = duplicate_gift_rng.choice(close)
                if new == old:
                    continue
                targeted_assignment_re = re.compile(
                    rf"(?P<prefix>\bsetvar\s*\(?\s*{re.escape(variable)}\s*,\s*)"
                    rf"{re.escape(old)}\b"
                )

                def replace_assignment(match: re.Match[str], replacement: str = new) -> str:
                    return match.group("prefix") + replacement

                updated, replacement_count = targeted_assignment_re.subn(
                    replace_assignment,
                    updated,
                )
                if replacement_count == 0:
                    raise RandomizerError(
                        f"Could not update variable-backed gift {variable} in {relative}"
                    )
                used_targets.add(new)
                mon_changes.append(
                    {
                        "file": relative,
                        "command": f"givemon-variable:{variable}",
                        "from": old,
                        "to": new,
                        "bst_delta": species[new].bst - old_mon.bst,
                    }
                )

        def replace_item(match: re.Match[str], *, relative_path: str = relative) -> str:
            old = match.group("item")
            gift = (relative_path, match.group("command"), old, scripted_item_quantity(match))
            if gift in PROTECTED_SCRIPTED_ITEM_GIFTS:
                return match.group(0)
            metadata = items.get(old)
            if metadata is None or not metadata.is_randomizable:
                return match.group(0)
            new = scripted_item_rng.choice(item_pool)
            if new == old and len(item_pool) > 1:
                new = scripted_item_rng.choice(
                    [candidate for candidate in item_pool if candidate != old]
                )
            item_changes.append(
                {"file": relative_path, "command": match.group("command"), "from": old, "to": new}
            )
            return match.group("prefix") + new

        updated = ITEM_COMMAND_RE.sub(replace_item, updated)
        if updated != text:
            changed_files[path] = normalize_changed_lines(text, updated)
    return changed_files, mon_changes, item_changes


def transform_map_items(
    source: Path, items: dict[str, Item], item_pool: list[str], rng: random.Random
) -> tuple[dict[Path, str], list[dict[str, object]]]:
    changed_files: dict[Path, str] = {}
    changes: list[dict[str, object]] = []
    for path in sorted((source / "data/maps").glob("*/map.json")):
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        relative = path.relative_to(source).as_posix()
        changed = False
        object_events = data.get("object_events", [])
        if isinstance(object_events, list):
            for event in object_events:
                if (
                    not isinstance(event, dict)
                    or event.get("graphics_id") != "OBJ_EVENT_GFX_ITEM_BALL"
                ):
                    continue
                old = event.get("trainer_sight_or_berry_tree_id")
                metadata = items.get(old) if isinstance(old, str) else None
                if metadata is None or not metadata.is_randomizable:
                    continue
                new = rng.choice(item_pool)
                if new == old and len(item_pool) > 1:
                    new = rng.choice([candidate for candidate in item_pool if candidate != old])
                event["trainer_sight_or_berry_tree_id"] = new
                changes.append(
                    {
                        "file": relative,
                        "kind": "item_ball",
                        "local_id": event.get("local_id"),
                        "from": old,
                        "to": new,
                    }
                )
                changed = True
        hidden_event_groups = [data.get("hidden_item_events", []), data.get("bg_events", [])]
        for hidden_events in hidden_event_groups:
            if not isinstance(hidden_events, list):
                continue
            for event in hidden_events:
                if not isinstance(event, dict):
                    continue
                if "type" in event and event.get("type") != "hidden_item":
                    continue
                old = event.get("item")
                metadata = items.get(old) if isinstance(old, str) else None
                if metadata is None or not metadata.is_randomizable:
                    continue
                new = rng.choice(item_pool)
                if new == old and len(item_pool) > 1:
                    new = rng.choice([candidate for candidate in item_pool if candidate != old])
                event["item"] = new
                changes.append({"file": relative, "kind": "hidden_item", "from": old, "to": new})
                changed = True
        if changed:
            changed_files[path] = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return changed_files, changes
