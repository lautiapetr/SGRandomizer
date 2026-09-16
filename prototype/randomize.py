#!/usr/bin/env python3
"""Deterministic source-data randomizer for Pokemon SoulGold v1.1.4."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SUPPORTED_TAG = "v.1.1.4"
DEFAULT_MANIFEST = "soulgold-randomizer-manifest.json"
SPECIAL_CATEGORIES = frozenset({"legendary", "mythical", "paradox"})

# IDs exposed by the project's official v1.0.4.5 cheat database. The v1.1.4
# source adds four newer items after this range, but they have not yet been
# verified by that database. Keeping the pool to these ranges also excludes
# unused species-specific Mega Stones, Z-Crystals, and story-only IDs.
OFFICIAL_CHEAT_ITEM_ID_RANGES = (
    (1, 291),
    (339, 356),
    (392, 412),
    (418, 704),
    (760, 773),
    (794, 816),
    (891, 925),
)

# These either gate progression, unlock a mandatory system, or are used by a
# story script even when their pocket/importance metadata changes in a future
# source revision. The metadata checks below protect the rest automatically.
STORY_ITEM_DENYLIST = frozenset(
    {
        "ITEM_AURORA_TICKET",
        "ITEM_BASEMENT_KEY",
        "ITEM_BECKONING_BELL",
        "ITEM_BICYCLE",
        "ITEM_CARD_KEY",
        "ITEM_CLEAR_BELL",
        "ITEM_COIN_CASE",
        "ITEM_DARK_CRYSTAL",
        "ITEM_DEVON_GOODS",
        "ITEM_DEVON_SCOPE",
        "ITEM_DOWSING_MACHINE",
        "ITEM_EON_TICKET",
        "ITEM_EXP_SHARE",
        "ITEM_GS_BALL",
        "ITEM_JADE_ORB",
        "ITEM_LETTER",
        "ITEM_LIBERTY_PASS",
        "ITEM_LIFT_KEY",
        "ITEM_LOST_ITEM",
        "ITEM_MACH_BIKE",
        "ITEM_MACHINE_PART",
        "ITEM_MAGMA_EMBLEM",
        "ITEM_MEGA_RING",
        "ITEM_METEORITE",
        "ITEM_MYSTERY_EGG",
        "ITEM_OAKS_PARCEL",
        "ITEM_OLD_SEA_MAP",
        "ITEM_PASS",
        "ITEM_POKE_FLUTE",
        "ITEM_POWDER_JAR",
        "ITEM_RAINBOW_PASS",
        "ITEM_RAINBOW_WING",
        "ITEM_RED_ORB",
        "ITEM_ROOM_1_KEY",
        "ITEM_ROOM_2_KEY",
        "ITEM_ROOM_4_KEY",
        "ITEM_ROOM_6_KEY",
        "ITEM_SCANNER",
        "ITEM_SCOPE_LENS_STORY",
        "ITEM_SECRET_KEY",
        "ITEM_SECRET_POTION",
        "ITEM_SILPH_SCOPE",
        "ITEM_SILVER_WING",
        "ITEM_SS_TICKET",
        "ITEM_STORAGE_KEY",
        "ITEM_SQUIRTBOTTLE",
        "ITEM_TEACHY_TV",
        "ITEM_TOWN_MAP",
        "ITEM_TRI_PASS",
        "ITEM_VS_SEEKER",
        "ITEM_WAILMER_PAIL",
    }
)

# Scripted supplies that are part of the early-game baseline rather than
# optional rewards. Keep these exact gifts vanilla while still allowing other
# Poké Balls in field pickups and later rewards to be randomized.
PROTECTED_SCRIPTED_ITEM_GIFTS = frozenset(
    {
        ("data/maps/NewBarkTown_Lab/scripts.pory", "giveitem", "ITEM_POKE_BALL", 10),
        ("data/maps/NewBarkTown_Lab/scripts.inc", "giveitem", "ITEM_POKE_BALL", 10),
    }
)

# Battle-only and cosmetic forms should not be generated as ordinary wild
# Pokemon. Regional forms and stable alternate forms are intentionally allowed.
UNSAFE_SPECIES_PARTS = (
    "_MEGA",
    "_GMAX",
    "_PRIMAL",
    "_TOTEM",
    "_ETERNAMAX",
    "_BLADE",
    "_BUSTED",
    "_SCHOOL",
    "_NOICE_FACE",
    "_HANGRY",
    "_CROWNED",
    "_RAPID_STRIKE_GMAX",
    "_SINGLE_STRIKE_GMAX",
)


class RandomizerError(RuntimeError):
    """A validation or transformation error safe to show to the user."""


@dataclass(frozen=True)
class Species:
    constant: str
    name: str
    dex: int
    bst: int
    categories: frozenset[str]
    evolutions: tuple[str, ...]

    @property
    def is_special(self) -> bool:
        return bool(self.categories & SPECIAL_CATEGORIES)


@dataclass(frozen=True)
class Item:
    constant: str
    item_id: int
    pocket: str
    important: bool

    @property
    def is_randomizable(self) -> bool:
        return (
            self.constant != "ITEM_NONE"
            and not self.constant.startswith("ITEM_HM_")
            and self.constant not in STORY_ITEM_DENYLIST
            and self.pocket != "POCKET_KEY_ITEMS"
            and not self.important
            and any(start <= self.item_id <= end for start, end in OFFICIAL_CHEAT_ITEM_ID_RANGES)
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="SoulGold source checkout")
    parser.add_argument("--seed", required=True, help="Text or integer seed")
    parser.add_argument("--apply", action="store_true", help="Write changes; default is preview only")
    parser.add_argument("--force", action="store_true", help="Allow replacing an existing manifest")
    parser.add_argument(
        "--manifest",
        type=Path,
        help=f"Report path (default: SOURCE/{DEFAULT_MANIFEST})",
    )
    return parser.parse_args(argv)


def stable_seed(seed_text: str) -> int:
    try:
        return int(seed_text, 0)
    except ValueError:
        digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
        return int.from_bytes(digest[:16], "big")


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


def validate_source(source: Path) -> None:
    required = (
        source / "docs/data/romhack-docs.json",
        source / "src/data/wild_encounters.json",
        source / "src/data/items.h",
        source / "src/ui_birch_case.c",
        source / "data/maps",
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RandomizerError("Not a compatible SoulGold checkout; missing: " + ", ".join(missing))

    tag = exact_git_tag(source)
    if tag is not None and tag != SUPPORTED_TAG:
        raise RandomizerError(f"Expected tag {SUPPORTED_TAG}, found {tag}. Refusing an untested layout.")


def load_species(source: Path) -> dict[str, Species]:
    docs_path = source / "docs/data/romhack-docs.json"
    raw = json.loads(docs_path.read_text(encoding="utf-8"))["species"]
    result: dict[str, Species] = {}
    for entry in raw:
        constant = entry["constant"]
        result[constant] = Species(
            constant=constant,
            name=entry["name"],
            dex=int(entry.get("dex") or 0),
            bst=int(entry.get("bst") or 0),
            categories=frozenset(entry.get("categories") or ()),
            evolutions=tuple(
                evo["target"] for evo in entry.get("evolutions", ()) if evo.get("target")
            ),
        )

    # The docs classify Legendary/Mythical/Paradox species but not Ultra Beasts.
    block_re = re.compile(r"\[(SPECIES_[A-Z0-9_]+)\]\s*=\s*\{(.*?)(?=\n\s*\[SPECIES_|\Z)", re.S)
    for family_file in sorted((source / "src/data/pokemon/species_info").glob("gen_*_families.h")):
        text = family_file.read_text(encoding="utf-8")
        for match in block_re.finditer(text):
            constant, block = match.groups()
            if ".isUltraBeast = TRUE" in block and constant in result:
                old = result[constant]
                result[constant] = Species(
                    constant=old.constant,
                    name=old.name,
                    dex=old.dex,
                    bst=old.bst,
                    categories=old.categories | {"ultra_beast"},
                    evolutions=old.evolutions,
                )
    return result


def safe_species(species: Species) -> bool:
    if species.dex <= 0 or species.bst <= 0 or "mega" in species.categories:
        return False
    for part in UNSAFE_SPECIES_PARTS:
        if part == "_MEGA":
            # Do not mistake SPECIES_MEGANIUM for a Mega form.
            if re.search(r"_MEGA(?:_|$)", species.constant):
                return False
        elif part in species.constant:
            return False
    return True


def graph_data(species: dict[str, Species]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    children: dict[str, set[str]] = {constant: set() for constant in species}
    parents: dict[str, set[str]] = {constant: set() for constant in species}
    for constant, mon in species.items():
        for target in mon.evolutions:
            if target in species:
                children[constant].add(target)
                parents[target].add(constant)
    return children, parents


def components(
    species: dict[str, Species], children: dict[str, set[str]], parents: dict[str, set[str]]
) -> list[set[str]]:
    eligible = {constant for constant, mon in species.items() if safe_species(mon)}
    pending = set(eligible)
    result: list[set[str]] = []
    while pending:
        start = min(pending)
        queue = [start]
        component: set[str] = set()
        while queue:
            current = queue.pop()
            if current not in pending:
                continue
            pending.remove(current)
            component.add(current)
            queue.extend((children[current] | parents[current]) & pending)
        result.append(component)
    return result


def component_depths(
    component: set[str], children: dict[str, set[str]], parents: dict[str, set[str]]
) -> dict[str, int]:
    roots = sorted(node for node in component if not (parents[node] & component))
    if not roots:
        roots = [min(component)]
    depths = {root: 0 for root in roots}
    queue = deque(roots)
    while queue:
        node = queue.popleft()
        for child in sorted(children[node] & component):
            depth = depths[node] + 1
            if child not in depths or depth < depths[child]:
                depths[child] = depth
                queue.append(child)
    for node in component:
        depths.setdefault(node, 0)
    return depths


def family_signature(
    component: set[str], depths: dict[str, int], species: dict[str, Species]
) -> tuple[int, tuple[int, ...]]:
    max_depth = max(depths.values(), default=0)
    medians: list[int] = []
    for depth in range(max_depth + 1):
        values = sorted(species[node].bst for node in component if depths[node] == depth)
        medians.append(values[len(values) // 2])
    return max_depth, tuple(medians)


def build_species_mapping(species: dict[str, Species], rng: random.Random) -> dict[str, str]:
    children, parents = graph_data(species)
    families = components(species, children, parents)
    depth_by_family = {id(family): component_depths(family, children, parents) for family in families}
    family_by_species = {node: family for family in families for node in family}

    candidate_families = [
        family
        for family in families
        if not any(species[node].is_special or "ultra_beast" in species[node].categories for node in family)
    ]
    by_depth: dict[int, list[set[str]]] = defaultdict(list)
    for family in candidate_families:
        depths = depth_by_family[id(family)]
        by_depth[max(depths.values(), default=0)].append(family)

    mapping: dict[str, str] = {}
    for source_family in sorted(families, key=lambda family: min(family)):
        source_depths = depth_by_family[id(source_family)]
        if any(
            species[node].is_special or "ultra_beast" in species[node].categories
            for node in source_family
        ):
            mapping.update({node: node for node in source_family})
            continue

        source_signature = family_signature(source_family, source_depths, species)
        depth = source_signature[0]
        candidates = by_depth.get(depth) or candidate_families
        scored: list[tuple[int, str, set[str]]] = []
        for candidate in candidates:
            if candidate is source_family and len(candidates) > 1:
                continue
            candidate_depths = depth_by_family[id(candidate)]
            candidate_signature = family_signature(candidate, candidate_depths, species)
            strength_compatible = True
            for source_node in source_family:
                same_stage = [
                    node for node in candidate if candidate_depths[node] == source_depths[source_node]
                ]
                if children[source_node] & source_family:
                    same_stage = [node for node in same_stage if children[node] & candidate]
                if not same_stage:
                    strength_compatible = False
                    break
                best_delta = min(
                    abs(species[source_node].bst - species[node].bst) for node in same_stage
                )
                tolerance = max(40, round(species[source_node].bst * 0.12))
                if best_delta > tolerance:
                    strength_compatible = False
                    break
            if not strength_compatible:
                continue
            depth_penalty = abs(source_signature[0] - candidate_signature[0]) * 1000
            width = min(len(source_signature[1]), len(candidate_signature[1]))
            bst_penalty = sum(
                abs(source_signature[1][idx] - candidate_signature[1][idx]) for idx in range(width)
            )
            size_penalty = abs(len(source_family) - len(candidate)) * 25
            scored.append((depth_penalty + bst_penalty + size_penalty, min(candidate), candidate))
        scored.sort(key=lambda row: (row[0], row[1]))
        if not scored:
            mapping.update({node: node for node in source_family})
            continue

        # Pick among close families so the result is random without sacrificing
        # similar strength. A 45-point window excludes obviously unbalanced lines.
        best_score = scored[0][0]
        close = [row for row in scored if row[0] <= best_score + 45][:24]
        target_family = rng.choice(close)[2]
        target_depths = depth_by_family[id(target_family)]

        target_roots = [node for node in target_family if not (parents[node] & target_family)]
        for source_node in sorted(source_family, key=lambda node: (source_depths[node], node)):
            source_parents = sorted(parents[source_node] & source_family)
            if source_parents:
                direct_children = {
                    child
                    for source_parent in source_parents
                    for child in children[mapping[source_parent]] & target_family
                }
                same_stage = sorted(direct_children)
            else:
                same_stage = sorted(target_roots)
            if not same_stage:
                same_stage = [
                    node for node in target_family if target_depths[node] == source_depths[source_node]
                ]
            if children[source_node] & source_family:
                evolvable = [node for node in same_stage if children[node] & target_family]
                if evolvable:
                    same_stage = evolvable
            if not same_stage:
                same_stage = list(target_family)
            ranked = sorted(
                same_stage,
                key=lambda node: (abs(species[source_node].bst - species[node].bst), node),
            )
            best_delta = abs(species[source_node].bst - species[ranked[0]].bst)
            close_nodes = [
                node
                for node in ranked
                if abs(species[source_node].bst - species[node].bst) <= best_delta + 10
            ]
            mapping[source_node] = rng.choice(close_nodes)

    # Constants filtered as unsafe are never generated; leave them stable if
    # they are referenced by a gift or static script.
    for constant in species:
        mapping.setdefault(constant, constant)
    return mapping


def starter_pool(species: dict[str, Species]) -> list[str]:
    children, parents = graph_data(species)
    pool: list[str] = []
    for constant, mon in species.items():
        if not safe_species(mon) or mon.is_special or "ultra_beast" in mon.categories:
            continue
        if parents[constant]:
            continue
        first = children[constant]
        if not first:
            continue
        second = {grandchild for child in first for grandchild in children[child]}
        if not second:
            continue
        # Every path must have a second evolution. This excludes misleading
        # partially branched families while allowing true three-stage branches.
        if any(not children[child] for child in first):
            continue
        if any(children[grandchild] for grandchild in second):
            continue
        pool.append(constant)
    return sorted(pool)


def choose_starters(species: dict[str, Species], rng: random.Random) -> list[str]:
    pool = starter_pool(species)
    # Original SoulGold starters range roughly around normal starter BST. Use a
    # generous floor to exclude early-route three-stage bugs from the starter pool.
    pool = [constant for constant in pool if 270 <= species[constant].bst <= 360]
    if len(pool) < 9:
        raise RandomizerError(f"Only {len(pool)} valid three-stage starter candidates were found")
    return rng.sample(pool, 9)


def parse_items(source: Path) -> dict[str, Item]:
    text = (source / "src/data/items.h").read_text(encoding="utf-8")
    constants_text = (source / "include/constants/items.h").read_text(encoding="utf-8")
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
    return result


def replace_starters(text: str, starters: list[str]) -> tuple[str, list[dict[str, str]]]:
    pattern = re.compile(
        r"(?P<prefix>\[BALL_[A-Z_]+\]\s*=\s*\{)(?P<species>SPECIES_[A-Z0-9_]+)(?P<suffix>\s*,\s*5\s*,\s*[012]\s*\})"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 9:
        raise RandomizerError(f"Expected 9 starter slots, found {len(matches)}")
    iterator = iter(starters)
    changes: list[dict[str, str]] = []

    def repl(match: re.Match[str]) -> str:
        new = next(iterator)
        changes.append({"slot": match.group(0).split("]", 1)[0][1:], "from": match.group("species"), "to": new})
        return match.group("prefix") + new + match.group("suffix")

    return pattern.sub(repl, text), changes


def transform_wild_encounters(
    raw: dict[str, Any], mapping: dict[str, str], species: dict[str, Species]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    changes: list[dict[str, Any]] = []
    groups = raw.get("wild_encounter_groups", [])
    for group in groups:
        for encounter in group.get("encounters", []):
            map_name = encounter.get("map", "UNKNOWN")
            for field, info in encounter.items():
                if not field.endswith("_mons") or not isinstance(info, dict):
                    continue
                for slot, mon in enumerate(info.get("mons", [])):
                    old = mon.get("species")
                    if old not in mapping:
                        continue
                    new = mapping[old]
                    if new == old:
                        continue
                    mon["species"] = new
                    changes.append(
                        {
                            "map": map_name,
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
    """Clean whitespace only on lines whose content was transformed."""
    original_lines = original.splitlines(keepends=True)
    updated_lines = updated.splitlines(keepends=True)
    if len(original_lines) != len(updated_lines):
        return updated
    cleaned: list[str] = []
    for old_line, new_line in zip(original_lines, updated_lines):
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


MON_COMMAND_RE = re.compile(
    r"(?P<prefix>\b(?P<command>givemon|giveegg|setwildbattle)\s*\(?\s*)(?P<species>SPECIES_[A-Z0-9_]+)"
)
ITEM_COMMAND_RE = re.compile(
    r"(?P<prefix>\b(?P<command>giveitem|finditem)\s*\(?\s*)(?P<item>ITEM_[A-Z0-9_]+)"
)


def scripted_item_quantity(match: re.Match[str]) -> int:
    """Return the literal quantity following an item command (default: one)."""
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
    mon_rng: random.Random,
    rng: random.Random,
) -> tuple[dict[Path, str], list[dict[str, Any]], list[dict[str, Any]]]:
    changed_files: dict[Path, str] = {}
    mon_changes: list[dict[str, Any]] = []
    item_changes: list[dict[str, Any]] = []
    children, parents = graph_data(species)

    for path in script_source_files(source):
        relative = path.relative_to(source).as_posix()
        text = path.read_text(encoding="utf-8")

        # The active nine-starter UI is randomized separately. These old lab
        # fallback scripts must stay aligned with their original flow.
        allow_mon_changes = "LittlerootTown_ProfessorBirchsLab" not in relative

        def mon_repl(match: re.Match[str]) -> str:
            old = match.group("species")
            if not allow_mon_changes or old not in species:
                return match.group(0)
            new = mapping.get(old, old)
            if new == old:
                return match.group(0)
            mon_changes.append(
                {
                    "file": relative,
                    "command": match.group("command"),
                    "from": old,
                    "to": new,
                    "bst_delta": species[new].bst - species[old].bst,
                }
            )
            return match.group("prefix") + new

        updated = MON_COMMAND_RE.sub(mon_repl, text)

        # Some prize/gift menus put a species in a variable and pass that
        # variable to givemon. Replace every reference to those menu choices in
        # one pass so their switch cases and displayed names remain consistent.
        variable_gifts = set(
            re.findall(r"\bgivemon\s*\(?\s*(VAR_[A-Z0-9_]+)", text)
        )
        variable_replacements: dict[str, str] = {}
        used_targets: set[str] = set()
        for variable in sorted(variable_gifts):
            assignment_re = re.compile(
                rf"\bsetvar\s*\(?\s*{re.escape(variable)}\s*,\s*(SPECIES_[A-Z0-9_]+)"
            )
            for old in assignment_re.findall(text):
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
                        new = mon_rng.choice(close)
                if new == old:
                    continue
                variable_replacements[old] = new
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

        if variable_replacements:
            constants_re = re.compile(
                r"\b(" + "|".join(map(re.escape, sorted(variable_replacements, key=len, reverse=True))) + r")\b"
            )
            updated = constants_re.sub(lambda match: variable_replacements[match.group(1)], updated)

        def item_repl(match: re.Match[str]) -> str:
            old = match.group("item")
            gift = (relative, match.group("command"), old, scripted_item_quantity(match))
            if gift in PROTECTED_SCRIPTED_ITEM_GIFTS:
                return match.group(0)
            metadata = items.get(old)
            if metadata is None or not metadata.is_randomizable:
                return match.group(0)
            new = rng.choice(item_pool)
            if new == old and len(item_pool) > 1:
                new = rng.choice([candidate for candidate in item_pool if candidate != old])
            item_changes.append(
                {"file": relative, "command": match.group("command"), "from": old, "to": new}
            )
            return match.group("prefix") + new

        updated = ITEM_COMMAND_RE.sub(item_repl, updated)
        if updated != text:
            changed_files[path] = normalize_changed_lines(text, updated)

    return changed_files, mon_changes, item_changes


def transform_map_items(
    source: Path, items: dict[str, Item], item_pool: list[str], rng: random.Random
) -> tuple[dict[Path, str], list[dict[str, Any]]]:
    changed_files: dict[Path, str] = {}
    changes: list[dict[str, Any]] = []
    for path in sorted((source / "data/maps").glob("*/map.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        relative = path.relative_to(source).as_posix()
        changed = False

        for event in data.get("object_events", []):
            if event.get("graphics_id") != "OBJ_EVENT_GFX_ITEM_BALL":
                continue
            old = event.get("trainer_sight_or_berry_tree_id")
            metadata = items.get(old)
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

        for event in data.get("hidden_item_events", []):
            old = event.get("item")
            metadata = items.get(old)
            if metadata is None or not metadata.is_randomizable:
                continue
            new = rng.choice(item_pool)
            if new == old and len(item_pool) > 1:
                new = rng.choice([candidate for candidate in item_pool if candidate != old])
            event["item"] = new
            changes.append(
                {
                    "file": relative,
                    "kind": "hidden_item",
                    "from": old,
                    "to": new,
                }
            )
            changed = True

        if changed:
            changed_files[path] = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return changed_files, changes


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(source: Path, seed_text: str, apply: bool, force: bool, manifest_path: Path) -> dict[str, Any]:
    validate_source(source)
    if apply and manifest_path.exists() and not force:
        raise RandomizerError(
            f"Manifest already exists at {manifest_path}. Restore the checkout first or use --force."
        )

    seed = stable_seed(seed_text)
    # Separate streams keep one subsystem stable if another gains a new entry.
    species_rng = random.Random(seed ^ 0x53504543494553)
    starter_rng = random.Random(seed ^ 0x53544152544552)
    item_rng = random.Random(seed ^ 0x4954454D53)
    gift_rng = random.Random(seed ^ 0x4749465453)

    species = load_species(source)
    mapping = build_species_mapping(species, species_rng)
    starters = choose_starters(species, starter_rng)
    items = parse_items(source)
    item_pool = sorted(constant for constant, item in items.items() if item.is_randomizable)
    if not item_pool:
        raise RandomizerError("No randomizable items were found")

    pending: dict[Path, str] = {}

    starter_path = source / "src/ui_birch_case.c"
    starter_original = starter_path.read_text(encoding="utf-8")
    starter_text, starter_changes = replace_starters(starter_original, starters)
    pending[starter_path] = starter_text

    wild_path = source / "src/data/wild_encounters.json"
    wild_raw = json.loads(wild_path.read_text(encoding="utf-8"))
    wild_raw, wild_changes = transform_wild_encounters(wild_raw, mapping, species)
    pending[wild_path] = json.dumps(wild_raw, ensure_ascii=False, indent=2) + "\n"

    script_files, mon_changes, scripted_item_changes = transform_scripts(
        source, mapping, species, items, item_pool, gift_rng, item_rng
    )
    pending.update(script_files)
    map_files, map_item_changes = transform_map_items(source, items, item_pool, item_rng)
    pending.update(map_files)

    # Omit unchanged writes and provide checksums for auditability.
    writes: list[dict[str, str]] = []
    for path in sorted(pending):
        original = path.read_text(encoding="utf-8")
        updated = pending[path]
        if original == updated:
            continue
        writes.append(
            {
                "file": path.relative_to(source).as_posix(),
                "before_sha256": sha256_text(original),
                "after_sha256": sha256_text(updated),
            }
        )
        if apply:
            path.write_text(updated, encoding="utf-8")

    used_mapping = sorted(
        {
            (change["from"], change["to"])
            for change in wild_changes + mon_changes
            if change["from"] != change["to"]
        }
    )
    manifest: dict[str, Any] = {
        "tool": "SoulGold Semi-Randomizer",
        "supported_tag": SUPPORTED_TAG,
        "seed_input": seed_text,
        "seed_numeric": seed,
        "applied": apply,
        "rules": {
            "wild_pokemon": "random_similar_strength_follow_evolutions",
            "trainers": "vanilla",
            "starters": "nine_distinct_base_species_three_stage_lines",
            "static_pokemon": "random_similar_strength_follow_evolutions",
            "gift_pokemon": "random_similar_strength_follow_evolutions",
            "special_pokemon": "legendary_mythical_ultra_beast_paradox_vanilla",
            "species_data": "vanilla",
            "field_hidden_gift_items": "random",
            "early_lab_poke_balls": "vanilla_10",
            "key_story_hm_items": "vanilla",
        },
        "counts": {
            "species_available": len(species),
            "item_pool": len(item_pool),
            "files_changed": len(writes),
            "wild_slots_changed": len(wild_changes),
            "static_and_gift_commands_changed": len(mon_changes),
            "map_items_changed": len(map_item_changes),
            "scripted_items_changed": len(scripted_item_changes),
        },
        "starters": starter_changes,
        "species_mapping_used": [{"from": old, "to": new} for old, new in used_mapping],
        "wild_changes": wild_changes,
        "static_and_gift_changes": mon_changes,
        "item_changes": map_item_changes + scripted_item_changes,
        "writes": writes,
    }
    if apply:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    source = args.source.resolve()
    manifest = (args.manifest or source / DEFAULT_MANIFEST).resolve()
    try:
        report = run(source, args.seed, args.apply, args.force, manifest)
    except RandomizerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    mode = "APPLIED" if args.apply else "PREVIEW"
    print(f"SoulGold randomizer {mode}")
    print(f"Seed: {report['seed_input']} ({report['seed_numeric']})")
    print("Starters:")
    for starter in report["starters"]:
        print(f"  {starter['slot']}: {starter['from']} -> {starter['to']}")
    counts = report["counts"]
    print(
        "Changes: "
        f"{counts['wild_slots_changed']} wild slots, "
        f"{counts['static_and_gift_commands_changed']} static/gift Pokemon, "
        f"{counts['map_items_changed'] + counts['scripted_items_changed']} items, "
        f"{counts['files_changed']} files"
    )
    if args.apply:
        print(f"Manifest: {manifest}")
    else:
        print("No files were written. Add --apply to write this seed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
