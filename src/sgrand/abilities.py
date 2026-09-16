"""Independent normal-ability and innate-ability randomization."""

from __future__ import annotations

import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import median_low

from .ability_config import AbilityConfig, AbilityRules, InnateRules
from .errors import RandomizerError
from .models import Ability, Species

ABILITY_RE = re.compile(r"ABILITY_[A-Z0-9_]+")
ENTRY_RE = re.compile(r"^\s*\[(SPECIES_[A-Z0-9_]+)\]\s*=", re.M)
FIELD_RE_TEMPLATE = r"\.{field}\s*=\s*(?P<rhs>\{{[^}}]*\}}|[A-Z][A-Z0-9_]*)"


@dataclass(frozen=True, order=True)
class SourceSpan:
    path: Path
    start: int
    end: int


@dataclass(frozen=True)
class FieldCandidate:
    spans: tuple[SourceSpan, ...]
    values: tuple[str, ...]


@dataclass(frozen=True)
class SpeciesAbilityRecord:
    constant: str
    path: Path
    abilities: tuple[str, ...]
    innates: tuple[str, ...]
    ability_spans: tuple[SourceSpan, ...]
    innate_spans: tuple[SourceSpan, ...]
    innate_insert: SourceSpan
    structurally_protected: bool


@dataclass(frozen=True)
class AbilityTransformOutput:
    files: dict[Path, str]
    ability_assignments: dict[str, tuple[str, ...]]
    innate_assignments: dict[str, tuple[str, ...]]
    report: dict[str, object]


class _UnionFind:
    def __init__(self, values: set[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[max(left_root, right_root)] = min(left_root, right_root)

    def groups(self) -> list[list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for value in sorted(self.parent):
            grouped[self.find(value)].append(value)
        return [grouped[key] for key in sorted(grouped)]


def _without_empty_slots(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(value for value in values if value != "ABILITY_NONE")


def _macro_definitions(text: str) -> dict[str, list[tuple[int, int, str]]]:
    result: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    lines = text.splitlines(keepends=True)
    offset = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^\s*#\s*define\s+([A-Z][A-Z0-9_]*)", line)
        if not match:
            offset += len(line)
            index += 1
            continue
        start = offset
        name = match.group(1)
        body = line
        offset += len(line)
        index += 1
        while body.rstrip().endswith("\\") and index < len(lines):
            body += lines[index]
            offset += len(lines[index])
            index += 1
        result[name].append((start, offset, body))
    return result


def _literal_field_candidates(
    path: Path, text: str, start: int, end: int, field: str
) -> list[FieldCandidate]:
    pattern = re.compile(FIELD_RE_TEMPLATE.format(field=field), re.S)
    result: list[FieldCandidate] = []
    for match in pattern.finditer(text, start, end):
        rhs = match.group("rhs")
        if not rhs.startswith("{"):
            continue
        values = tuple(ABILITY_RE.findall(rhs))
        if values or field == "innates":
            result.append(
                FieldCandidate((SourceSpan(path, match.start("rhs"), match.end("rhs")),), values)
            )
    return result


def _macro_field_candidates(
    path: Path,
    text: str,
    macros: dict[str, list[tuple[int, int, str]]],
    name: str,
    field: str,
    seen: frozenset[str] = frozenset(),
) -> list[FieldCandidate]:
    if name in seen:
        return []
    result: list[FieldCandidate] = []
    for start, end, body in macros.get(name, []):
        direct = _literal_field_candidates(path, text, start, end, field)
        if direct:
            result.extend(direct)
            continue
        nested = sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]+\b", body)) & macros.keys())
        for nested_name in nested:
            result.extend(
                _macro_field_candidates(path, text, macros, nested_name, field, seen | {name})
            )
    return result


def _macro_value_candidates(
    macros: dict[str, list[tuple[int, int, str]]],
    name: str,
    seen: frozenset[str] = frozenset(),
) -> list[tuple[str, ...]]:
    if name in seen:
        return []
    result: list[tuple[str, ...]] = []
    for _start, _end, body in macros.get(name, []):
        values = tuple(ABILITY_RE.findall(body))
        if values:
            result.append(values)
            continue
        nested = sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]+\b", body)) & macros.keys())
        for nested_name in nested:
            result.extend(_macro_value_candidates(macros, nested_name, seen | {name}))
    return result


def _entry_field_candidates(
    path: Path,
    text: str,
    macros: dict[str, list[tuple[int, int, str]]],
    start: int,
    end: int,
    field: str,
) -> tuple[list[FieldCandidate], int | None]:
    pattern = re.compile(FIELD_RE_TEMPLATE.format(field=field), re.S)
    direct: list[FieldCandidate] = []
    direct_line_end: int | None = None
    for match in pattern.finditer(text, start, end):
        rhs = match.group("rhs")
        span = SourceSpan(path, match.start("rhs"), match.end("rhs"))
        if rhs.startswith("{"):
            direct.append(FieldCandidate((span,), tuple(ABILITY_RE.findall(rhs))))
        else:
            expanded = _macro_field_candidates(path, text, macros, rhs, field)
            if expanded:
                direct.extend(FieldCandidate((span,), candidate.values) for candidate in expanded)
            else:
                direct.extend(
                    FieldCandidate((span,), values)
                    for values in _macro_value_candidates(macros, rhs)
                )
        direct_line_end = text.find("\n", match.end()) + 1
    if direct:
        return direct, direct_line_end

    block = text[start:end]
    macro_names = sorted(set(re.findall(r"\b[A-Z][A-Z0-9_]+\b", block)) & macros.keys())
    indirect: list[FieldCandidate] = []
    insertion_line_end: int | None = None
    for name in macro_names:
        candidates = _macro_field_candidates(path, text, macros, name, field)
        if candidates:
            indirect.extend(candidates)
            if insertion_line_end is None:
                token_match = re.search(rf"\b{re.escape(name)}\b", text[start:end])
                if token_match:
                    insertion_line_end = text.find("\n", start + token_match.end()) + 1
        invocation = re.search(rf"\b{re.escape(name)}\s*\((.*?)\)", block, re.S)
        if invocation:
            arguments = [argument.strip() for argument in invocation.group(1).split(",")]
            for _macro_start, _macro_end, body in macros[name]:
                signature = re.match(rf"^\s*#\s*define\s+{re.escape(name)}\s*\(([^)]*)\)", body)
                initializer = re.search(rf"\.{field}\s*=\s*\{{([^}}]*)\}}", body, re.S)
                if not signature or not initializer:
                    continue
                parameters = [parameter.strip() for parameter in signature.group(1).split(",")]
                if len(parameters) != len(arguments):
                    continue
                substitutions = dict(zip(parameters, arguments, strict=True))
                values: list[str] = []
                valid = True
                for part in initializer.group(1).split(","):
                    value = substitutions.get(part.strip(), part.strip())
                    ability = ABILITY_RE.fullmatch(value)
                    if ability:
                        values.append(ability.group(0))
                    else:
                        valid = False
                        break
                if valid:
                    indirect.append(FieldCandidate((), tuple(values)))
    return indirect, insertion_line_end


def _matching_candidates(
    candidates: list[FieldCandidate], expected: tuple[str, ...], main: bool
) -> list[FieldCandidate]:
    result: list[FieldCandidate] = []
    for candidate in candidates:
        actual = _without_empty_slots(candidate.values) if main else candidate.values
        if actual == expected:
            result.append(candidate)
    unique: dict[tuple[SourceSpan, ...], FieldCandidate] = {}
    for candidate in result:
        unique[candidate.spans] = candidate
    return list(unique.values())


def parse_species_ability_records(
    source: Path, species: dict[str, Species]
) -> tuple[dict[str, SpeciesAbilityRecord], dict[Path, str]]:
    """Resolve effective docs metadata back to the real species-info storage."""
    paths = sorted((source / "src/data/pokemon/species_info").glob("gen_*_families.h"))
    texts = {path: path.read_text(encoding="utf-8") for path in paths}
    constants_text = (source / "include/constants/species.h").read_text(encoding="utf-8")
    aliases = dict(
        re.findall(
            r"^\s*#define\s+(SPECIES_[A-Z0-9_]+)\s+(SPECIES_[A-Z0-9_]+)\s*$",
            constants_text,
            re.M,
        )
    )
    records: dict[str, SpeciesAbilityRecord] = {}
    for path, text in texts.items():
        macros = _macro_definitions(text)
        for marker in ENTRY_RE.finditer(text):
            source_constant = marker.group(1)
            constant = source_constant
            seen_aliases: set[str] = set()
            while constant not in species and constant in aliases and constant not in seen_aliases:
                seen_aliases.add(constant)
                constant = aliases[constant]
            mon = species.get(constant)
            if mon is None or not mon.abilities:
                continue
            remainder = text[marker.end() :]
            if remainder.lstrip().startswith("{"):
                closing = re.search(r"^ {0,4}\},\s*$", remainder, re.M)
                if closing is None:
                    raise RandomizerError(f"Cannot find the end of {source_constant} in {path}")
                end = marker.end() + closing.end()
            else:
                newline = text.find("\n", marker.end())
                end = len(text) if newline < 0 else newline + 1
            main_candidates, ability_line_end = _entry_field_candidates(
                path, text, macros, marker.start(), end, "abilities"
            )
            matching_main = _matching_candidates(main_candidates, mon.abilities, main=True)
            if not matching_main:
                raise RandomizerError(
                    f"Cannot resolve active .abilities storage for {constant} in {path}"
                )
            main_values = matching_main[0].values
            main_spans = tuple(
                sorted({span for candidate in matching_main for span in candidate.spans})
            )

            innate_candidates, macro_line_end = _entry_field_candidates(
                path, text, macros, marker.start(), end, "innates"
            )
            matching_innates = _matching_candidates(innate_candidates, mon.innates, main=False)
            if mon.innates and not matching_innates:
                raise RandomizerError(
                    f"Cannot resolve active .innates storage for {constant} in {path}"
                )
            innate_spans = tuple(
                sorted({span for candidate in matching_innates for span in candidate.spans})
            )
            innate_values = matching_innates[0].values if matching_innates else ()
            insert_at = ability_line_end or macro_line_end
            if insert_at is None:
                raise RandomizerError(f"Cannot locate an innate insertion point for {constant}")
            records[constant] = SpeciesAbilityRecord(
                constant=constant,
                path=path,
                abilities=main_values,
                innates=innate_values,
                ability_spans=main_spans,
                innate_spans=innate_spans,
                innate_insert=SourceSpan(path, insert_at, insert_at),
                structurally_protected=not main_spans or (bool(mon.innates) and not innate_spans),
            )
    missing = sorted(
        constant for constant, mon in species.items() if mon.abilities and constant not in records
    )
    if missing:
        raise RandomizerError(
            "Species documentation cannot be mapped to species_info storage: "
            + ", ".join(missing[:20])
        )
    return records, texts


def _groups(
    records: dict[str, SpeciesAbilityRecord],
    species: dict[str, Species],
    field: str,
    follow_evolutions: bool,
    protected: set[str],
) -> list[list[str]]:
    mutable = set(records) - protected
    union = _UnionFind(mutable)
    by_span: dict[SourceSpan, list[str]] = defaultdict(list)
    for constant in mutable:
        spans = (
            records[constant].ability_spans
            if field == "abilities"
            else records[constant].innate_spans
        )
        for span in spans:
            by_span[span].append(constant)
    for owners in by_span.values():
        for owner in owners[1:]:
            union.union(owners[0], owner)
    if follow_evolutions:
        for constant in sorted(mutable):
            for target in species[constant].evolutions:
                if target in mutable:
                    union.union(constant, target)
    return union.groups()


def _candidate_pool(
    abilities: dict[str, Ability],
    config: AbilityConfig,
    rules: AbilityRules,
    locked: frozenset[str],
) -> list[str]:
    blocked = config.blacklist | locked | {"ABILITY_NONE"}
    if not rules.allow_special_abilities:
        blocked |= config.special_abilities
    return sorted(
        constant
        for constant, ability in abilities.items()
        if constant not in blocked
        and rules.minimum_ai_rating <= ability.ai_rating <= rules.maximum_ai_rating
    )


def _choose_sequence(
    count: int,
    rating_targets: list[int],
    pool: list[str],
    abilities: dict[str, Ability],
    rules: AbilityRules,
    excluded: set[str],
    rng: random.Random,
) -> tuple[str, ...]:
    chosen: list[str] = []
    for index in range(count):
        eligible = [
            constant
            for constant in pool
            if constant not in excluded and (rules.allow_duplicates or constant not in chosen)
        ]
        if rules.rating_strategy == "similar":
            target = rating_targets[min(index, len(rating_targets) - 1)]
            similar = [
                constant
                for constant in eligible
                if abs(abilities[constant].ai_rating - target) <= rules.maximum_rating_delta
            ]
            if similar:
                eligible = similar
        if not eligible:
            raise RandomizerError(
                "Ability rules leave no valid candidate; widen ratings or reduce exclusions"
            )
        chosen.append(rng.choice(eligible))
    return tuple(chosen)


def _rating_targets(
    constants: list[str],
    records: dict[str, SpeciesAbilityRecord],
    abilities: dict[str, Ability],
    field: str,
    count: int,
) -> list[int]:
    sequences = []
    for constant in constants:
        values = records[constant].abilities if field == "abilities" else records[constant].innates
        sequences.append(
            [abilities[value].ai_rating for value in values if value != "ABILITY_NONE"]
        )
    result: list[int] = []
    for index in range(count):
        ratings = [sequence[index] for sequence in sequences if index < len(sequence)]
        result.append(int(median_low(ratings)) if ratings else 0)
    return result or [0]


def _main_assignments(
    records: dict[str, SpeciesAbilityRecord],
    species: dict[str, Species],
    abilities: dict[str, Ability],
    config: AbilityConfig,
    locked: frozenset[str],
    protected: set[str],
    rng: random.Random,
) -> dict[str, tuple[str, ...]]:
    result = {constant: record.abilities for constant, record in records.items()}
    rules = config.profile.abilities
    if not rules.enabled:
        return result
    pool = _candidate_pool(abilities, config, rules, locked)
    for group in _groups(records, species, "abilities", rules.follow_evolutions, protected):
        count = max(
            sum(value != "ABILITY_NONE" for value in records[constant].abilities)
            for constant in group
        )
        targets = _rating_targets(group, records, abilities, "abilities", count)
        selected = _choose_sequence(count, targets, pool, abilities, rules, set(), rng)
        for constant in group:
            index = 0
            values: list[str] = []
            for vanilla in records[constant].abilities:
                if vanilla == "ABILITY_NONE":
                    values.append(vanilla)
                else:
                    values.append(selected[index])
                    index += 1
            result[constant] = tuple(values)
    return result


def _innate_assignments(
    records: dict[str, SpeciesAbilityRecord],
    species: dict[str, Species],
    abilities: dict[str, Ability],
    config: AbilityConfig,
    locked: frozenset[str],
    protected: set[str],
    main: dict[str, tuple[str, ...]],
    rng: random.Random,
) -> dict[str, tuple[str, ...]]:
    result = {constant: record.innates for constant, record in records.items()}
    rules: InnateRules = config.profile.innates
    if not rules.enabled:
        return result
    pool = _candidate_pool(abilities, config, rules, locked)
    for group in _groups(records, species, "innates", rules.follow_evolutions, protected):
        if rules.count_mode == "vanilla":
            counts = {constant: len(records[constant].innates) for constant in group}
        else:
            counts = {constant: rules.fixed_count for constant in group}
        count = max(counts.values(), default=0)
        if count == 0:
            for constant in group:
                result[constant] = ()
            continue
        excluded = {
            value for constant in group for value in main[constant] if value != "ABILITY_NONE"
        }
        targets = _rating_targets(group, records, abilities, "innates", count)
        selected = _choose_sequence(count, targets, pool, abilities, rules, excluded, rng)
        for constant in group:
            result[constant] = selected[: counts[constant]]
    return result


def _render_initializer(values: tuple[str, ...]) -> str:
    return "{ " + ", ".join(values) + " }"


def _protected_closure(
    records: dict[str, SpeciesAbilityRecord], locked: frozenset[str]
) -> set[str]:
    protected = {
        constant
        for constant, record in records.items()
        if record.structurally_protected or set(record.abilities + record.innates) & locked
    }
    protected_spans = {
        span
        for constant in protected
        for span in records[constant].ability_spans + records[constant].innate_spans
    }
    return {
        constant
        for constant, record in records.items()
        if constant in protected
        or bool(set(record.ability_spans + record.innate_spans) & protected_spans)
    }


def transform_species_abilities(
    source: Path,
    species: dict[str, Species],
    abilities: dict[str, Ability],
    config: AbilityConfig,
    form_locked: frozenset[str],
    ability_rng: random.Random,
    innate_rng: random.Random,
) -> AbilityTransformOutput:
    records, texts = parse_species_ability_records(source, species)
    locked = config.species_locked_abilities | form_locked
    protected = _protected_closure(records, locked)
    main = _main_assignments(records, species, abilities, config, locked, protected, ability_rng)
    innates = _innate_assignments(
        records, species, abilities, config, locked, protected, main, innate_rng
    )

    replacements: dict[SourceSpan, str] = {}
    for constant, record in records.items():
        if main[constant] != record.abilities:
            rendered = _render_initializer(main[constant])
            for span in record.ability_spans:
                previous = replacements.setdefault(span, rendered)
                if previous != rendered:
                    raise RandomizerError(
                        "Shared ability storage received inconsistent assignments"
                    )
        if innates[constant] != record.innates:
            rendered = _render_initializer(innates[constant])
            targets = record.innate_spans
            if not targets:
                targets = (record.innate_insert,)
                rendered = f"        .innates = {rendered},\n"
            for span in targets:
                previous = replacements.setdefault(span, rendered)
                if previous != rendered:
                    raise RandomizerError("Shared innate storage received inconsistent assignments")

    by_path: dict[Path, list[tuple[SourceSpan, str]]] = defaultdict(list)
    for span, replacement in replacements.items():
        by_path[span.path].append((span, replacement))
    output_files: dict[Path, str] = {}
    for path, edits in by_path.items():
        updated = texts[path]
        for span, replacement in sorted(edits, key=lambda item: item[0].start, reverse=True):
            updated = updated[: span.start] + replacement + updated[span.end :]
        if updated != texts[path]:
            output_files[path] = updated

    for constant in records:
        if set(main[constant]) & set(innates[constant]):
            raise RandomizerError(f"{constant} repeats a normal ability as an innate")
        if any(value not in abilities for value in main[constant] + innates[constant]):
            raise RandomizerError(f"{constant} references an undefined ability after planning")
        if constant in protected and (
            main[constant] != records[constant].abilities
            or innates[constant] != records[constant].innates
        ):
            raise RandomizerError(f"Protected form abilities changed for {constant}")
        if config.profile.innates.count_mode == "vanilla" and len(innates[constant]) != len(
            records[constant].innates
        ):
            raise RandomizerError(f"Vanilla innate count changed for {constant}")

    ability_changed = sum(main[key] != records[key].abilities for key in records)
    innate_changed = sum(innates[key] != records[key].innates for key in records)
    return AbilityTransformOutput(
        files=output_files,
        ability_assignments=main,
        innate_assignments=innates,
        report={
            "species_records": len(records),
            "normal_species_changed": ability_changed,
            "innate_species_changed": innate_changed,
            "protected_species": len(protected),
            "form_table_locked_abilities": sorted(form_locked),
            "species_locked_abilities": sorted(locked),
        },
    )
