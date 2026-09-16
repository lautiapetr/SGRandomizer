"""Independent move-property, level-up and TM/tutor randomization passes."""

from __future__ import annotations

import json
import math
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .errors import RandomizerError
from .models import Move, Species
from .move_config import CompatibilityRules, LearnsetRules, MoveConfig

PHYSICAL = "DAMAGE_CATEGORY_PHYSICAL"
SPECIAL = "DAMAGE_CATEGORY_SPECIAL"
STATUS = "DAMAGE_CATEGORY_STATUS"

LEVEL_ARRAY_RE = re.compile(
    r"(?P<header>static const struct LevelUpMove "
    r"(?P<name>s[A-Za-z0-9_]+LevelUpLearnset)\[\]\s*=\s*\{)"
    r"(?P<body>.*?)(?P<footer>\n\};)",
    re.S,
)
LEVEL_MOVE_RE = re.compile(
    r"(?P<prefix>LEVEL_UP_MOVE\(\s*)(?P<level>\d+)"
    r"(?P<middle>\s*,\s*)(?P<move>MOVE_[A-Z0-9_]+)(?P<suffix>\s*\))"
)
SPECIES_BLOCK_RE = re.compile(r"\[(SPECIES_[A-Z0-9_]+)\]\s*=\s*\{(.*?)(?=\n\s*\[SPECIES_|\Z)", re.S)
MOVE_INFO_BLOCK_RE = re.compile(
    r"(?P<header>^\s*\[(?P<move>MOVE_[A-Z0-9_]+)\]\s*=\s*\n?\s*\{)"
    r"(?P<body>.*?)(?=^\s*\[MOVE_[A-Z0-9_]+\]\s*=|\Z)",
    re.M | re.S,
)


@dataclass(frozen=True)
class MovePassOutput:
    files: dict[Path, str]
    report: dict[str, int]


def _preferred_category(species: list[Species]) -> str | None:
    physical_score = sum(mon.attack for mon in species)
    special_score = sum(mon.special_attack for mon in species)
    if physical_score > special_score:
        return PHYSICAL
    if special_score > physical_score:
        return SPECIAL
    return None


def _chance(rng: random.Random, percent: int) -> bool:
    return rng.randrange(100) < percent


def _power_band(level: int, rules: LearnsetRules) -> tuple[int, int]:
    for band in rules.progressive_power:
        if level <= band.through_level:
            return band.minimum, band.maximum
    raise RandomizerError(f"No progressive power band covers level {level}")


def _learnset_owners(source: Path, species: dict[str, Species]) -> dict[str, list[Species]]:
    owners: dict[str, list[Species]] = defaultdict(list)
    pointer_re = re.compile(r"\.levelUpLearnset\s*=\s*(s[A-Za-z0-9_]+LevelUpLearnset)")
    family_dir = source / "src/data/pokemon/species_info"
    for path in sorted(family_dir.glob("gen_*_families.h")):
        text = path.read_text(encoding="utf-8")
        for constant, block in SPECIES_BLOCK_RE.findall(text):
            mon = species.get(constant)
            pointer = pointer_re.search(block)
            if mon is not None and pointer is not None:
                owners[pointer.group(1)].append(mon)
    return dict(owners)


def discover_event_moves(source: Path, moves: dict[str, Move]) -> frozenset[str]:
    """Protect real move constants referenced by event source scripts."""
    discovered: set[str] = set()
    roots = (source / "data/maps", source / "data/scripts")
    for root in roots:
        for path in sorted((*root.rglob("*.inc"), *root.rglob("*.pory"))):
            text = path.read_text(encoding="utf-8")
            discovered.update(re.findall(r"\bMOVE_[A-Z0-9_]+\b", text))
    return frozenset(discovered & moves.keys())


def _eligible_move_pools(
    moves: dict[str, Move], config: MoveConfig, protected: frozenset[str]
) -> tuple[list[Move], list[Move]]:
    blocked = protected | config.excluded_moves | config.signature_moves
    offensive: list[Move] = []
    status: list[Move] = []
    for move in moves.values():
        if move.constant in blocked:
            continue
        if move.accuracy != 0 and move.accuracy < config.learnsets.minimum_accuracy:
            continue
        if move.is_offensive and move.power > 1:
            offensive.append(move)
        elif move.category == STATUS:
            status.append(move)
    return sorted(offensive, key=lambda move: move.constant), sorted(
        status, key=lambda move: move.constant
    )


def _select_move(
    old: str,
    level: int,
    force_offensive: bool,
    owners: list[Species],
    offensive: list[Move],
    status: list[Move],
    used: set[str],
    rules: LearnsetRules,
    rng: random.Random,
) -> Move:
    want_offensive = force_offensive or _chance(rng, rules.offensive_percent)
    primary = offensive if want_offensive else status
    fallback = status if want_offensive else offensive
    candidates = [move for move in primary if move.constant != old]
    if not candidates:
        candidates = [move for move in fallback if move.constant != old]
    if not candidates:
        raise RandomizerError("No eligible move candidates remain for a level-up learnset")

    if want_offensive and candidates[0].is_offensive:
        minimum, maximum = _power_band(level, rules)
        progressive = [move for move in candidates if minimum <= move.power <= maximum]
        if progressive:
            candidates = progressive

    owner_types = {move_type for mon in owners for move_type in mon.types}
    if owner_types and _chance(rng, rules.stab_percent):
        stab = [move for move in candidates if move.move_type in owner_types]
        if stab:
            candidates = stab

    preferred = _preferred_category(owners)
    if preferred is not None and _chance(rng, rules.category_match_percent):
        matching = [move for move in candidates if move.category == preferred]
        if matching:
            candidates = matching

    unused = [move for move in candidates if move.constant not in used]
    if unused:
        candidates = unused
    return rng.choice(candidates)


def transform_level_up_learnsets(
    source: Path,
    species: dict[str, Species],
    moves: dict[str, Move],
    config: MoveConfig,
    protected: frozenset[str],
    rng: random.Random,
) -> MovePassOutput:
    if not config.learnsets.enabled:
        return MovePassOutput(
            {},
            {
                "files": 0,
                "learnsets": 0,
                "slots": 0,
                "early_guarantees": 0,
                "early_exemptions": 0,
            },
        )
    owners_by_array = _learnset_owners(source, species)
    offensive, status = _eligible_move_pools(moves, config, protected)
    if not offensive or not status:
        raise RandomizerError("Move pools require both offensive and status candidates")

    changed_files: dict[Path, str] = {}
    arrays_changed = 0
    slots_changed = 0
    early_guarantees = 0
    early_exemptions = 0
    blocked_old = protected | config.excluded_moves
    if config.learnsets.preserve_signature_moves:
        blocked_old |= config.signature_moves
    shared_replacements: dict[tuple[str, str], Move] = {}

    for source_index, filename in enumerate(config.learnsets.source_files):
        path = source / "src/data/pokemon/level_up_learnsets" / filename
        if not path.is_file():
            raise RandomizerError(f"Configured level-up source does not exist: {path}")
        original = path.read_text(encoding="utf-8")

        def replace_array(
            array_match: re.Match[str], *, enforce_early_attack: bool = source_index == 0
        ) -> str:
            nonlocal arrays_changed, slots_changed, early_guarantees, early_exemptions
            array_name = array_match.group("name")
            owners = owners_by_array.get(array_name, [])
            if not owners:
                return array_match.group(0)
            body = array_match.group("body")
            slots = list(LEVEL_MOVE_RE.finditer(body))
            if not slots:
                return array_match.group(0)
            early_unmodifiable_attack = (
                any(
                    int(slot.group("level")) <= config.learnsets.early_attack_level
                    and slot.group("move") in blocked_old
                    and (moves.get(slot.group("move")) is not None)
                    and cast(Move, moves.get(slot.group("move"))).is_offensive
                    for slot in slots
                )
                if enforce_early_attack
                else True
            )
            early_candidates = [
                index
                for index, slot in enumerate(slots)
                if int(slot.group("level")) <= config.learnsets.early_attack_level
                and slot.group("move") not in blocked_old
            ]
            early_exempt = (
                enforce_early_attack and not early_unmodifiable_attack and not early_candidates
            )
            if early_exempt:
                early_exemptions += 1
            forced_index = (
                None if early_unmodifiable_attack or early_exempt else early_candidates[0]
            )
            used: set[str] = set()
            slot_index = 0
            local_changes = 0
            final_early_attack = early_unmodifiable_attack

            def replace_slot(slot: re.Match[str]) -> str:
                nonlocal slot_index, local_changes, slots_changed, final_early_attack
                index = slot_index
                slot_index += 1
                old = slot.group("move")
                level = int(slot.group("level"))
                if old in blocked_old:
                    used.add(old)
                    return slot.group(0)
                replacement_key = (array_name, old)
                selected = shared_replacements.get(replacement_key)
                if selected is None:
                    selected = _select_move(
                        old,
                        level,
                        index == forced_index,
                        owners,
                        offensive,
                        status,
                        used,
                        config.learnsets,
                        rng,
                    )
                    shared_replacements[replacement_key] = selected
                used.add(selected.constant)
                if level <= config.learnsets.early_attack_level and selected.is_offensive:
                    final_early_attack = True
                if selected.constant == old:
                    return slot.group(0)
                local_changes += 1
                slots_changed += 1
                return (
                    slot.group("prefix")
                    + slot.group("level")
                    + slot.group("middle")
                    + selected.constant
                    + slot.group("suffix")
                )

            updated_body = LEVEL_MOVE_RE.sub(replace_slot, body)
            if enforce_early_attack and not final_early_attack and not early_exempt:
                raise RandomizerError(f"Early attack guarantee failed for {array_name}")
            if forced_index is not None:
                early_guarantees += 1
            if local_changes:
                arrays_changed += 1
            return array_match.group("header") + updated_body + array_match.group("footer")

        updated = LEVEL_ARRAY_RE.sub(replace_array, original)
        if updated != original:
            changed_files[path] = updated
    return MovePassOutput(
        changed_files,
        {
            "files": len(changed_files),
            "learnsets": arrays_changed,
            "slots": slots_changed,
            "early_guarantees": early_guarantees,
            "early_exemptions": early_exemptions,
        },
    )


def _replace_field(block: str, field: str, value: int | str) -> tuple[str, bool]:
    pattern = re.compile(rf"(?m)(?P<prefix>^\s*\.{re.escape(field)}\s*=\s*)[^,\n]+")
    updated, count = pattern.subn(lambda match: match.group("prefix") + str(value), block, count=1)
    return updated, count == 1


def _stepped_values(minimum: int, maximum: int, step: int) -> list[int]:
    first = math.ceil(minimum / step) * step
    return list(range(first, maximum + 1, step))


def transform_move_properties(
    source: Path,
    moves: dict[str, Move],
    config: MoveConfig,
    protected: frozenset[str],
    rng: random.Random,
) -> MovePassOutput:
    if not config.properties.enabled:
        return MovePassOutput(
            {}, {"moves": 0, "power": 0, "accuracy": 0, "pp": 0, "type": 0, "category": 0}
        )
    path = source / "src/data/moves_info.h"
    original = path.read_text(encoding="utf-8")
    blocked = protected | config.signature_moves | config.excluded_moves
    field_counts = {"power": 0, "accuracy": 0, "pp": 0, "type": 0, "category": 0}
    moves_changed = 0

    def replace_block(match: re.Match[str]) -> str:
        nonlocal moves_changed
        constant = match.group("move")
        move = moves.get(constant)
        if move is None or constant in blocked:
            return match.group(0)
        rules = config.properties
        body = match.group("body")
        updated = body

        if move.is_offensive and move.power > 1:
            variation = rules.power_variation_percent / 100
            lower = max(rules.minimum_power, math.ceil(move.power * (1 - variation)))
            upper = min(rules.maximum_power, math.floor(move.power * (1 + variation)))
            values = _stepped_values(lower, upper, rules.power_step)
            if values:
                updated, found = _replace_field(updated, "power", rng.choice(values))
                field_counts["power"] += int(found and updated != body)

        before = updated
        if move.accuracy > 0:
            values = _stepped_values(
                rules.minimum_accuracy, rules.maximum_accuracy, rules.accuracy_step
            )
            updated, found = _replace_field(updated, "accuracy", rng.choice(values))
            field_counts["accuracy"] += int(found and updated != before)

        before = updated
        pp_values = _stepped_values(rules.minimum_pp, rules.maximum_pp, rules.pp_step)
        updated, found = _replace_field(updated, "pp", rng.choice(pp_values))
        field_counts["pp"] += int(found and updated != before)

        before = updated
        if rules.randomize_type:
            updated, found = _replace_field(updated, "type", rng.choice(rules.types))
            field_counts["type"] += int(found and updated != before)

        before = updated
        if rules.randomize_category and move.is_offensive and move.power > 1:
            updated, found = _replace_field(updated, "category", rng.choice((PHYSICAL, SPECIAL)))
            field_counts["category"] += int(found and updated != before)

        if updated != body:
            moves_changed += 1
        return match.group("header") + updated

    updated = MOVE_INFO_BLOCK_RE.sub(replace_block, original)
    files = {path: updated} if updated != original else {}
    return MovePassOutput(files, {"moves": moves_changed, **field_counts})


def _tm_moves(source: Path) -> frozenset[str]:
    text = (source / "include/constants/tms_hms.h").read_text(encoding="utf-8")
    return frozenset(f"MOVE_{name}" for name in re.findall(r"\bF\(([A-Z0-9_]+)\)", text))


def _tutor_moves(source: Path, special: dict[str, object]) -> frozenset[str]:
    tutors: set[str] = set()
    extra = special.get("extraTutors", [])
    if isinstance(extra, list):
        tutors.update(entry for entry in extra if isinstance(entry, str))
    dedicated = special.get("dedicatedTutors", {})
    if isinstance(dedicated, dict):
        tutors.update(entry for entry in dedicated if isinstance(entry, str))
    marker_re = re.compile(
        r"special ChooseMonForMoveTutor|chooseboxmon SELECT_PC_MON_MOVE_TUTOR|"
        r"call MoveTutor_EventScript_Open(?:PartyMenu|Box)"
    )
    for path in sorted(
        (*((source / "data/maps").rglob("*.inc")), *((source / "data/scripts").rglob("*.inc")))
    ):
        text = path.read_text(encoding="utf-8")
        if not marker_re.search(text):
            continue
        tutors.update(re.findall(r"setvar VAR_0x8005, (MOVE_[A-Z0-9_]+)", text))
        tutors.update(re.findall(r"move_tutor (MOVE_[A-Z0-9_]+)", text))
    return frozenset(tutors)


def transform_move_compatibility(
    source: Path,
    species: dict[str, Species],
    moves: dict[str, Move],
    config: MoveConfig,
    protected: frozenset[str],
    rng: random.Random,
) -> MovePassOutput:
    if not config.compatibility.enabled:
        return MovePassOutput(
            {}, {"species": 0, "added": 0, "removed": 0, "tm_decisions": 0, "tutor_decisions": 0}
        )
    path = source / "src/data/pokemon/all_learnables.json"
    special_path = source / "src/data/pokemon/special_movesets.json"
    try:
        raw_document: Any = json.loads(path.read_text(encoding="utf-8"))
        special_raw: Any = json.loads(special_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RandomizerError(f"Cannot parse move compatibility inputs: {exc}") from exc
    if not isinstance(raw_document, dict) or not isinstance(special_raw, dict):
        raise RandomizerError("Move compatibility inputs must be JSON objects")
    document = cast(dict[str, object], raw_document)
    special = cast(dict[str, object], special_raw)
    tms = _tm_moves(source) & moves.keys()
    tutors = _tutor_moves(source, special) & moves.keys()
    universals = special.get("universalMoves", [])
    universal_moves = (
        {entry for entry in universals if isinstance(entry, str)}
        if isinstance(universals, list)
        else set()
    )
    teachable = (tms | tutors) - universal_moves
    rules: CompatibilityRules = config.compatibility
    changed_species = added = removed = tm_decisions = tutor_decisions = 0
    output: dict[str, object] = {}

    for name, raw_learnables in document.items():
        if (
            not isinstance(name, str)
            or not isinstance(raw_learnables, list)
            or not all(isinstance(entry, str) for entry in raw_learnables)
        ):
            raise RandomizerError(f"Invalid compatibility entry for {name!r}")
        original = set(cast(list[str], raw_learnables))
        mon = species.get(f"SPECIES_{name}")
        if mon is None:
            output[name] = raw_learnables
            continue
        updated = set(original)
        preferred = _preferred_category([mon])
        for constant in sorted(teachable):
            if constant in config.excluded_moves:
                continue
            if constant in protected and rules.preserve_protected_moves:
                continue
            if constant in config.signature_moves and rules.preserve_signature_moves:
                continue
            move = moves[constant]
            if constant in tms:
                chance = rules.tm_percent
                tm_decisions += 1
            else:
                chance = rules.tutor_percent
                tutor_decisions += 1
            if move.move_type in mon.types:
                chance += rules.stab_bonus_percent
            if preferred is not None and move.category == preferred:
                chance += rules.category_match_bonus_percent
            if _chance(rng, min(100, chance)):
                updated.add(constant)
            else:
                updated.discard(constant)
        if updated != original:
            changed_species += 1
            added += len(updated - original)
            removed += len(original - updated)
        output[name] = sorted(updated)

    updated_text = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    original_text = path.read_text(encoding="utf-8")
    files = {path: updated_text} if updated_text != original_text else {}
    return MovePassOutput(
        files,
        {
            "species": changed_species,
            "added": added,
            "removed": removed,
            "tm_decisions": tm_decisions,
            "tutor_decisions": tutor_decisions,
        },
    )
