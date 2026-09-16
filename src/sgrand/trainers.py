"""Parser and deterministic transformer for competitive-syntax trainer parties."""

from __future__ import annotations

import json
import random
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .errors import RandomizerError
from .models import Item, Move, Species
from .species import safe_species
from .trainer_config import TrainerConfig, TrainerRules

SECTION_RE = re.compile(r"^=== (?P<id>TRAINER_[A-Z0-9_]+) ===[ \t]*$", re.M)
ATTRIBUTE_RE = re.compile(r"^(?P<key>[A-Za-z ]+):[ \t]*(?P<value>.*?)[ \t]*$", re.M)
LEVEL_RE = re.compile(r"^Level:[ \t]*(?P<level>\d+)[ \t]*$", re.M)
ABILITY_RE = re.compile(r"^Ability:[ \t]*.*?$", re.M)
MOVE_LINE_RE = re.compile(r"^- [^\n]*$", re.M)
DOUBLE_SUPPORT_MOVES = frozenset(
    {
        "MOVE_ALLY_SWITCH",
        "MOVE_COACHING",
        "MOVE_FOLLOW_ME",
        "MOVE_HELPING_HAND",
        "MOVE_LIFE_DEW",
        "MOVE_PROTECT",
        "MOVE_RAGE_POWDER",
        "MOVE_REFLECT",
        "MOVE_LIGHT_SCREEN",
        "MOVE_TAILWIND",
        "MOVE_WIDE_GUARD",
    }
)
VANILLA_RIVAL_FAMILIES = {
    "CHIKORITA": {"SPECIES_CHIKORITA", "SPECIES_BAYLEEF", "SPECIES_MEGANIUM"},
    "CYNDAQUIL": {"SPECIES_CYNDAQUIL", "SPECIES_QUILAVA", "SPECIES_TYPHLOSION"},
    "TOTODILE": {"SPECIES_TOTODILE", "SPECIES_CROCONAW", "SPECIES_FERALIGATR"},
}


@dataclass(frozen=True)
class HeaderParts:
    nickname: str | None
    species_text: str
    gender: str
    item_text: str | None


@dataclass(frozen=True)
class PartyPokemon:
    raw: str
    constant: str
    header: HeaderParts
    level: int
    explicit_level: bool
    move_count: int


@dataclass(frozen=True)
class TrainerTransformOutput:
    text: str
    report: dict[str, object]
    assignments: dict[str, tuple[str, ...]]


def _normalized(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    ascii_value = ascii_value.upper().replace("'", "").replace(".", "").replace(":", "")
    return re.sub(r"_+", "_", re.sub(r"[^A-Z0-9]+", "_", ascii_value)).strip("_")


def _species_aliases(species: dict[str, Species]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for constant, mon in sorted(species.items()):
        suffix = constant.removeprefix("SPECIES_")
        values = {
            constant,
            suffix,
            suffix.replace("_", " "),
            suffix.replace("_", "-"),
            mon.name,
        }
        for removable_suffix in ("_STANDARD", "_OVERCAST"):
            if suffix.endswith(removable_suffix):
                values.add(suffix.removesuffix(removable_suffix))
        for value in values:
            key = _normalized(value).removeprefix("SPECIES_")
            aliases.setdefault(key, constant)
            aliases.setdefault(key.replace("_", ""), constant)
    return aliases


def _parse_header(line: str) -> HeaderParts:
    clean = line.rstrip(" \t\r\n")
    item_text: str | None = None
    if " @ " in clean:
        clean, item_text = clean.split(" @ ", 1)
        item_text = item_text.strip()
    gender = ""
    gender_match = re.search(r" \(([MF])\)$", clean)
    if gender_match:
        gender = gender_match.group(0)
        clean = clean[: gender_match.start()]
    nickname: str | None = None
    species_text = clean.strip()
    nickname_match = re.fullmatch(r"(.+?) \(([^()]*)\)", species_text)
    if nickname_match:
        nickname = nickname_match.group(1)
        species_text = nickname_match.group(2)
    return HeaderParts(nickname, species_text, gender, item_text)


def _resolve_species(header: HeaderParts, aliases: dict[str, str]) -> str | None:
    key = _normalized(header.species_text).removeprefix("SPECIES_")
    return aliases.get(key) or aliases.get(key.replace("_", ""))


def _parse_pokemon(raw: str, aliases: dict[str, str]) -> PartyPokemon | None:
    lines = raw.splitlines()
    if not lines or not lines[0].strip() or lines[0].lstrip().startswith("/*"):
        return None
    header = _parse_header(lines[0])
    constant = _resolve_species(header, aliases)
    if constant is None:
        return None
    level_match = LEVEL_RE.search(raw)
    return PartyPokemon(
        raw=raw,
        constant=constant,
        header=header,
        level=int(level_match.group("level")) if level_match else 100,
        explicit_level=level_match is not None,
        move_count=len(MOVE_LINE_RE.findall(raw)),
    )


def _trainer_attributes(header: str) -> dict[str, str]:
    return {match.group("key"): match.group("value") for match in ATTRIBUTE_RE.finditer(header)}


def _category(trainer_id: str, attributes: dict[str, str], config: TrainerConfig) -> str:
    trainer_class = attributes.get("Class", "")
    if trainer_class == "Rival" or trainer_id.startswith("TRAINER_RIVAL"):
        return "rival"
    if trainer_class == "Leader":
        return "leaders"
    if trainer_class in config.boss_classes or "BOSS" in trainer_id:
        return "bosses"
    return "trainers"


def _load_learnables(
    source: Path, species: dict[str, Species], moves: dict[str, Move]
) -> dict[str, tuple[str, ...]]:
    path = source / "src/data/pokemon/all_learnables.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RandomizerError(
            f"Cannot parse trainer move legality data from {path}: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise RandomizerError(f"Trainer move legality data must be an object: {path}")
    result: dict[str, tuple[str, ...]] = {}
    for constant in species:
        value = document.get(constant.removeprefix("SPECIES_"))
        if not isinstance(value, list) or not all(isinstance(move, str) for move in value):
            continue
        legal = tuple(sorted({move for move in value if move in moves and move != "MOVE_NONE"}))
        if legal:
            result[constant] = legal
    if not result:
        raise RandomizerError(f"No trainer move legality records were found in {path}")
    return result


def _item_aliases(items: dict[str, Item]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for constant in sorted(items):
        suffix = constant.removeprefix("ITEM_")
        aliases[_normalized(suffix)] = constant
        aliases[_normalized(suffix).replace("_", "")] = constant
    return aliases


def _observed_item_pool(text: str, items: dict[str, Item], config: TrainerConfig) -> list[str]:
    aliases = _item_aliases(items)
    observed: set[str] = set()
    for line in text.splitlines():
        if " @ " not in line:
            continue
        value = line.split(" @ ", 1)[1].strip()
        key = _normalized(value).removeprefix("ITEM_")
        constant = aliases.get(key) or aliases.get(key.replace("_", ""))
        if constant is not None:
            observed.add(constant)
    pool = set(config.held_item_allowlist or observed) - config.blacklist_items
    return sorted(pool)


def _chance(rng: random.Random, percent: int) -> bool:
    return rng.randrange(100) < percent


def _select_theme(
    pokemon: list[PartyPokemon],
    species: dict[str, Species],
    rules: TrainerRules,
    is_double: bool,
    rng: random.Random,
) -> str | None:
    if (rules.theme_mode == "none" or not _chance(rng, rules.theme_percent)) and not (
        is_double and rules.double_synergy
    ):
        return None
    vanilla_types = [move_type for mon in pokemon for move_type in species[mon.constant].types]
    if rules.theme_mode == "vanilla" or (is_double and rules.double_synergy):
        counts = Counter(vanilla_types)
        if counts:
            maximum = max(counts.values())
            return rng.choice(sorted(key for key, value in counts.items() if value == maximum))
    available = sorted(
        {
            move_type
            for mon in species.values()
            if safe_species(mon)
            for move_type in mon.types
            if move_type not in {"TYPE_NONE", "TYPE_MYSTERY"}
        }
    )
    return rng.choice(available) if available else None


def _species_pool(
    species: dict[str, Species],
    learnables: dict[str, tuple[str, ...]],
    config: TrainerConfig,
) -> list[str]:
    return sorted(
        constant
        for constant, mon in species.items()
        if constant in learnables and safe_species(mon) and constant not in config.blacklist_species
    )


def _select_species(
    original: str,
    theme: str | None,
    used: set[str],
    pool: list[str],
    species: dict[str, Species],
    rules: TrainerRules,
    blacklist: frozenset[str],
    rng: random.Random,
) -> str:
    source = species[original]
    want_special = rules.allow_legendaries and _chance(rng, rules.legendary_percent)

    def eligible(constant: str, require_theme: bool, require_special: bool) -> bool:
        candidate = species[constant]
        special = candidate.is_special or "ultra_beast" in candidate.categories
        return (
            abs(candidate.bst - source.bst) <= rules.maximum_bst_delta
            and (rules.allow_duplicates or constant not in used)
            and (not require_theme or theme in candidate.types)
            and special == require_special
        )

    candidates = [
        constant for constant in pool if eligible(constant, theme is not None, want_special)
    ]
    if not candidates and want_special:
        candidates = [constant for constant in pool if eligible(constant, theme is not None, False)]
    if not candidates and theme is not None:
        candidates = [constant for constant in pool if eligible(constant, False, False)]
    if not candidates:
        candidates = [
            constant
            for constant in pool
            if abs(species[constant].bst - source.bst) <= rules.maximum_bst_delta
            and (rules.allow_duplicates or constant not in used)
            and not (species[constant].is_special or "ultra_beast" in species[constant].categories)
        ]
    if not candidates:
        if original not in blacklist and (rules.allow_duplicates or original not in used):
            return original
        raise RandomizerError(
            f"Trainer rules leave no species within {rules.maximum_bst_delta} BST of {original}"
        )
    ranked = sorted(candidates, key=lambda value: (abs(species[value].bst - source.bst), value))
    best_delta = abs(species[ranked[0]].bst - source.bst)
    close = [value for value in ranked if abs(species[value].bst - source.bst) <= best_delta + 25]
    return rng.choice(close[:32])


def _rival_stages(
    starters: list[str], species: dict[str, Species]
) -> dict[str, tuple[str, str, str]]:
    if len(starters) != 9:
        raise RandomizerError("Rival coherence requires exactly nine randomized starters")
    roots = {"CHIKORITA": starters[0], "CYNDAQUIL": starters[1], "TOTODILE": starters[2]}
    result: dict[str, tuple[str, str, str]] = {}
    for branch, root in roots.items():
        first = sorted(target for target in species[root].evolutions if target in species)
        if not first:
            raise RandomizerError(f"Randomized rival starter has no first evolution: {root}")
        middle = first[0]
        second = sorted(target for target in species[middle].evolutions if target in species)
        if not second:
            raise RandomizerError(f"Randomized rival starter has no final evolution: {middle}")
        result[branch] = (root, middle, second[0])
    return result


def _forced_rival_species(
    trainer_id: str,
    original: str,
    stages: dict[str, tuple[str, str, str]],
) -> str | None:
    match = re.fullmatch(r"TRAINER_RIVAL_(CHIKORITA|CYNDAQUIL|TOTODILE)_(\d+)", trainer_id)
    if match is None or original not in VANILLA_RIVAL_FAMILIES[match.group(1)]:
        return None
    encounter = int(match.group(2))
    stage = 0 if encounter == 1 else 1 if encounter <= 3 else 2
    return stages[match.group(1)][stage]


def _team_size(vanilla: int, rules: TrainerRules, rng: random.Random) -> int:
    if rules.team_size_mode == "vanilla":
        return vanilla
    if rules.team_size_mode == "fixed":
        return rules.fixed_team_size
    return rng.randint(rules.minimum_team_size, rules.maximum_team_size)


def _level(original: int, rules: TrainerRules) -> int:
    if rules.level_mode == "fixed":
        value = rules.fixed_level
    elif rules.level_mode == "scaled":
        value = round(original * rules.level_percent / 100) + rules.level_offset
    else:
        value = original
    return max(rules.minimum_level, min(rules.maximum_level, value))


def _legal_moves(
    constant: str,
    count: int,
    is_double: bool,
    support_slot: bool,
    learnables: dict[str, tuple[str, ...]],
    moves: dict[str, Move],
    species: dict[str, Species],
    config: TrainerConfig,
    rng: random.Random,
) -> tuple[str, ...]:
    if count == 0:
        return ()
    pool = [move for move in learnables[constant] if move not in config.blacklist_moves]
    if len(pool) < count:
        raise RandomizerError(f"{constant} has fewer than {count} legal trainer moves")
    selected: list[str] = []
    if is_double and support_slot:
        support = sorted(set(pool) & DOUBLE_SUPPORT_MOVES)
        if support:
            selected.append(rng.choice(support))
    mon = species[constant]
    offensive = [move for move in pool if moves[move].is_offensive]
    stab = [move for move in offensive if moves[move].move_type in mon.types]
    while len(selected) < count:
        candidates = [move for move in stab if move not in selected]
        if not candidates:
            candidates = [move for move in offensive if move not in selected]
        if not candidates:
            candidates = [move for move in pool if move not in selected]
        selected.append(rng.choice(candidates))
        if len(selected) >= 2:
            stab = []
    return tuple(selected)


def _render_pokemon(
    pokemon: PartyPokemon,
    constant: str,
    level: int,
    rules: TrainerRules,
    item: str | None,
    legal_moves: tuple[str, ...],
    abilities: dict[str, tuple[str, ...]],
) -> str:
    newline = "\n" if pokemon.raw.endswith("\n") else ""
    lines = pokemon.raw.rstrip("\n").split("\n")
    header = pokemon.header
    species_part = f"{header.nickname} ({constant})" if header.nickname is not None else constant
    lines[0] = species_part + header.gender + (f" @ {item}" if item is not None else "")
    body = "\n".join(lines)
    if rules.level_mode != "vanilla":
        if LEVEL_RE.search(body):
            body = LEVEL_RE.sub(f"Level: {level}", body, count=1)
        else:
            body = (
                body.split("\n", 1)[0]
                + f"\nLevel: {level}"
                + ("\n" + body.split("\n", 1)[1] if "\n" in body else "")
            )
    if ABILITY_RE.search(body):
        legal_abilities = [
            value for value in abilities.get(constant, ()) if value != "ABILITY_NONE"
        ]
        if not legal_abilities:
            raise RandomizerError(f"No legal normal ability is available for {constant}")
        body = ABILITY_RE.sub(f"Ability: {legal_abilities[0]}", body, count=1)
    if pokemon.move_count and legal_moves:
        iterator = iter(legal_moves)
        body = MOVE_LINE_RE.sub(lambda _match: f"- {next(iterator)}", body)
    return body + newline


def transform_trainers(
    source: Path,
    species: dict[str, Species],
    moves: dict[str, Move],
    items: dict[str, Item],
    abilities: dict[str, tuple[str, ...]],
    starters: list[str],
    config: TrainerConfig,
    species_rng: random.Random,
    level_rng: random.Random,
    theme_rng: random.Random,
    move_rng: random.Random,
    item_rng: random.Random,
) -> TrainerTransformOutput:
    """Transform trainers.party without changing its competitive syntax contract."""
    path = source / "src/data/trainers.party"
    original = path.read_text(encoding="utf-8")
    markers = list(SECTION_RE.finditer(original))
    if not markers:
        raise RandomizerError(f"No trainer sections were found in {path}")
    aliases = _species_aliases(species)
    learnables = _load_learnables(source, species, moves)
    pool = _species_pool(species, learnables, config)
    item_pool = _observed_item_pool(original, items, config)
    if (
        any(
            rules.held_items_mode == "random" and rules.held_item_percent > 0
            for rules in config.profile.categories.values()
        )
        and not item_pool
    ):
        raise RandomizerError("Trainer item rules require a non-empty held-item pool")
    rival_stages = _rival_stages(starters, species)
    canonical_rival_sections = sum(
        bool(
            re.fullmatch(r"TRAINER_RIVAL_(?:CHIKORITA|CYNDAQUIL|TOTODILE)_\d+", marker.group("id"))
        )
        for marker in markers
    )

    output = original[: markers[0].start()]
    assignments: dict[str, tuple[str, ...]] = {}
    counts: Counter[str] = Counter()
    themes = 0
    legal_move_slots = 0
    equipped_items = 0
    rival_starters = 0
    double_teams = 0
    synergy_teams = 0
    unresolved_preserved = 0

    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(original)
        block = original[marker.start() : end]
        parts = re.split(r"(\n(?:[ \t]*\n)+)", block)
        header = parts[0]
        trainer_id = marker.group("id")
        attributes = _trainer_attributes(header)
        category = _category(trainer_id, attributes, config)
        rules = config.profile.categories[category]
        pokemon_indices: list[int] = []
        pokemon: list[PartyPokemon] = []
        for part_index in range(2, len(parts), 2):
            parsed = _parse_pokemon(parts[part_index], aliases)
            if parsed is not None:
                pokemon_indices.append(part_index)
                pokemon.append(parsed)
            elif "Level:" in parts[part_index]:
                unresolved_preserved += 1
        if not pokemon or not rules.enabled:
            output += block
            continue
        if len(pokemon) > 6:
            raise RandomizerError(f"{trainer_id} has more than six party members")
        is_double = (
            attributes.get("Double Battle") == "Yes" or attributes.get("Battle Type") == "Doubles"
        )
        if is_double:
            double_teams += 1
        desired_size = _team_size(len(pokemon), rules, level_rng)
        templates = [pokemon[position % len(pokemon)] for position in range(desired_size)]
        forced_originals = [
            mon
            for mon in pokemon
            if _forced_rival_species(trainer_id, mon.constant, rival_stages) is not None
        ]
        if forced_originals and not any(
            _forced_rival_species(trainer_id, mon.constant, rival_stages) is not None
            for mon in templates
        ):
            templates[-1] = forced_originals[0]
        forced_slot = next(
            (
                slot
                for slot, mon in enumerate(templates)
                if _forced_rival_species(trainer_id, mon.constant, rival_stages) is not None
            ),
            None,
        )
        forced_target = (
            _forced_rival_species(trainer_id, templates[forced_slot].constant, rival_stages)
            if forced_slot is not None
            else None
        )
        theme = _select_theme(pokemon, species, rules, is_double, theme_rng)
        if theme is not None:
            themes += 1
        if is_double and rules.double_synergy:
            synergy_teams += 1
        reserved_forced = {forced_target} if forced_target is not None else set()
        used_species: set[str] = set() if rules.allow_duplicates else set(reserved_forced)
        used_items: set[str] = set()
        rendered: list[str] = []
        selected_constants: list[str] = []
        for slot, template in enumerate(templates):
            forced = forced_target if slot == forced_slot else None
            if forced is not None:
                selected = forced
                rival_starters += 1
            elif rules.moves_mode == "preserve" and template.move_count:
                selected = template.constant
            else:
                slot_pool = pool
                if rules.moves_mode == "legal" and template.move_count:
                    slot_pool = [
                        constant
                        for constant in pool
                        if len(set(learnables[constant]) - config.blacklist_moves)
                        >= template.move_count
                    ]
                selected = _select_species(
                    template.constant,
                    theme,
                    used_species,
                    slot_pool,
                    species,
                    rules,
                    config.blacklist_species,
                    species_rng,
                )
            if not rules.allow_duplicates:
                used_species.add(selected)
            selected_constants.append(selected)
            target_level = _level(template.level, rules)
            if rules.held_items_mode == "preserve":
                held_item = template.header.item_text
            elif rules.held_items_mode == "none" or not _chance(item_rng, rules.held_item_percent):
                held_item = None
            else:
                choices = [item for item in item_pool if not (is_double and item in used_items)]
                if not choices:
                    choices = item_pool
                held_item = item_rng.choice(choices)
                used_items.add(held_item)
                equipped_items += 1
            chosen_moves = (
                _legal_moves(
                    selected,
                    template.move_count,
                    is_double,
                    rules.double_synergy and slot == 0,
                    learnables,
                    moves,
                    species,
                    config,
                    move_rng,
                )
                if (rules.moves_mode == "legal" or forced is not None) and selected in learnables
                else ()
            )
            legal_move_slots += len(chosen_moves)
            rendered.append(
                _render_pokemon(
                    template,
                    selected,
                    target_level,
                    rules,
                    held_item,
                    chosen_moves,
                    abilities,
                )
            )
        if not rules.allow_duplicates and len(selected_constants) != len(set(selected_constants)):
            raise RandomizerError(f"{trainer_id} received duplicate species")
        for slot, (template, selected) in enumerate(
            zip(templates, selected_constants, strict=True)
        ):
            forced = forced_target if slot == forced_slot else None
            if (
                forced is None
                and selected != template.constant
                and abs(species[selected].bst - species[template.constant].bst)
                > rules.maximum_bst_delta
            ):
                raise RandomizerError(f"{trainer_id} violates its BST strength band")
            selected_special = species[selected].is_special or (
                "ultra_beast" in species[selected].categories
            )
            original_special = species[template.constant].is_special or (
                "ultra_beast" in species[template.constant].categories
            )
            if (
                not rules.allow_legendaries
                and selected_special
                and not (selected == template.constant and original_special)
            ):
                raise RandomizerError(f"{trainer_id} received a forbidden special species")
        assignments[f"{trainer_id}#{index}"] = tuple(selected_constants)
        counts[category] += 1
        counts["pokemon"] += len(rendered)
        counts["species_changed"] += sum(
            selected != template.constant
            for selected, template in zip(selected_constants, templates, strict=True)
        )

        if desired_size == len(pokemon):
            for part_index, replacement in zip(pokemon_indices, rendered, strict=True):
                parts[part_index] = replacement
            output += "".join(parts)
        else:
            prefix = parts[0] + (parts[1] if len(parts) > 1 else "\n\n")
            suffix = "\n" if block.endswith("\n") else ""
            output += prefix + "\n\n".join(value.rstrip("\n") for value in rendered) + "\n" + suffix

    if len(SECTION_RE.findall(output)) != len(markers):
        raise RandomizerError("Trainer transformation changed the section count")
    if canonical_rival_sections and rival_starters != canonical_rival_sections:
        raise RandomizerError(
            "Canonical rival teams must contain exactly one coherent starter slot"
        )
    return TrainerTransformOutput(
        text=output,
        assignments=assignments,
        report={
            "sections": len(markers),
            "trainers_changed": sum(counts[category] for category in config.profile.categories),
            "pokemon_written": counts["pokemon"],
            "species_changed": counts["species_changed"],
            "categories": {category: counts[category] for category in config.profile.categories},
            "themed_teams": themes,
            "double_teams": double_teams,
            "double_synergy_teams": synergy_teams,
            "legal_move_slots": legal_move_slots,
            "equipped_items": equipped_items,
            "rival_starter_slots": rival_starters,
            "held_item_pool": len(item_pool),
            "unresolved_party_entries_preserved": unresolved_preserved,
        },
    )
