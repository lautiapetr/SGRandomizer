"""Application service that composes every randomization pass."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .abilities import transform_species_abilities
from .ability_config import load_ability_config, validate_ability_references
from .constants import DEFAULT_MANIFEST, SUPPORTED_TAG
from .errors import RandomizerError
from .models import PlannedWrite
from .move_config import load_move_config, validate_move_references
from .moves import (
    discover_event_moves,
    transform_level_up_learnsets,
    transform_move_compatibility,
    transform_move_properties,
)
from .rng import RngStreams
from .source import (
    discover_form_locked_abilities,
    load_abilities,
    load_moves,
    load_species,
    parse_items,
    validate_source,
)
from .species import build_species_mapping, choose_starters
from .trainer_config import load_trainer_config, validate_trainer_references
from .trainers import transform_trainers
from .transaction import FileTransaction
from .transforms import (
    replace_starters,
    transform_map_items,
    transform_scripts,
    transform_wild_encounters,
)


class RunMode(StrEnum):
    PREVIEW = "preview"
    APPLY = "apply"


@dataclass(frozen=True)
class Plan:
    report: dict[str, Any]
    writes: tuple[PlannedWrite, ...]
    manifest_path: Path


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _planned_text(path: Path, updated: str) -> PlannedWrite | None:
    original = path.read_bytes()
    encoded = updated.encode("utf-8")
    if original == encoded:
        return None
    return PlannedWrite(path=path, original=original, updated=encoded)


class Randomizer:
    """Plan deterministic source edits, then optionally commit them as one transaction."""

    def __init__(self, transaction: FileTransaction | None = None) -> None:
        self.transaction = transaction or FileTransaction()

    def plan(
        self,
        source: Path,
        seed_text: str,
        mode: RunMode = RunMode.PREVIEW,
        manifest_path: Path | None = None,
        force: bool = False,
        move_config_path: Path | None = None,
        ability_config_path: Path | None = None,
        ability_profile: str | None = None,
        trainer_config_path: Path | None = None,
        trainer_profile: str | None = None,
    ) -> Plan:
        source = source.resolve()
        validate_source(source)
        manifest = (manifest_path or source / DEFAULT_MANIFEST).resolve()
        if mode is RunMode.APPLY and manifest.exists() and not force:
            raise RandomizerError(
                f"Manifest already exists at {manifest}. Restore the checkout first or use --force."
            )

        streams = RngStreams(seed_text)
        species = load_species(source)
        moves = load_moves(source)
        abilities = load_abilities(source)
        move_config = load_move_config(move_config_path)
        validate_move_references(move_config, moves)
        ability_config = load_ability_config(ability_config_path, ability_profile)
        form_locked_abilities = discover_form_locked_abilities(source)
        validate_ability_references(ability_config, abilities, form_locked_abilities)
        trainer_config = load_trainer_config(trainer_config_path, trainer_profile)
        event_moves = discover_event_moves(source, moves)
        protected_moves = move_config.protected_moves | event_moves
        wild_mapping = build_species_mapping(species, streams.stream("wild-species"))
        static_mapping = build_species_mapping(species, streams.stream("static-gift-species"))
        starters = choose_starters(species, streams.stream("starters"))
        items = parse_items(source)
        validate_trainer_references(trainer_config, species, moves, items)
        item_pool = sorted(constant for constant, item in items.items() if item.is_randomizable)
        if not item_pool:
            raise RandomizerError("No randomizable items were found")

        pending: dict[Path, str] = {}
        starter_path = source / "src/ui_birch_case.c"
        starter_text, starter_changes = replace_starters(
            starter_path.read_text(encoding="utf-8"), starters
        )
        pending[starter_path] = starter_text

        wild_path = source / "src/data/wild_encounters.json"
        try:
            wild_raw: dict[str, Any] = json.loads(wild_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise RandomizerError(f"Cannot parse {wild_path}: {exc}") from exc
        wild_raw, wild_changes = transform_wild_encounters(wild_raw, wild_mapping, species)
        pending[wild_path] = json.dumps(wild_raw, ensure_ascii=False, indent=2) + "\n"

        script_files, mon_changes, scripted_item_changes = transform_scripts(
            source,
            static_mapping,
            species,
            items,
            item_pool,
            streams.stream("static-gift-duplicate-resolution"),
            streams.stream("scripted-items"),
        )
        pending.update(script_files)
        map_files, map_item_changes = transform_map_items(
            source, items, item_pool, streams.stream("map-items")
        )
        pending.update(map_files)

        property_output = transform_move_properties(
            source,
            moves,
            move_config,
            protected_moves,
            streams.stream("move-properties"),
        )
        pending.update(property_output.files)
        learnset_output = transform_level_up_learnsets(
            source,
            species,
            moves,
            move_config,
            protected_moves,
            streams.stream("move-level-up-learnsets"),
        )
        pending.update(learnset_output.files)
        compatibility_output = transform_move_compatibility(
            source,
            species,
            moves,
            move_config,
            protected_moves,
            streams.stream("move-tm-tutor-compatibility"),
        )
        pending.update(compatibility_output.files)

        ability_output = transform_species_abilities(
            source,
            species,
            abilities,
            ability_config,
            form_locked_abilities,
            streams.stream("species-abilities"),
            streams.stream("species-innates"),
        )
        pending.update(ability_output.files)

        trainer_output = transform_trainers(
            source,
            species,
            moves,
            items,
            ability_output.ability_assignments,
            starters,
            trainer_config,
            streams.stream("trainers-species"),
            streams.stream("trainers-levels-and-sizes"),
            streams.stream("trainers-themes"),
            streams.stream("trainers-moves"),
            streams.stream("trainers-items"),
        )
        pending[source / "src/data/trainers.party"] = trainer_output.text

        planned_writes = [
            planned
            for path, updated in sorted(pending.items())
            if (planned := _planned_text(path, updated)) is not None
        ]
        write_records = [
            {
                "file": write.path.relative_to(source).as_posix(),
                "before_sha256": sha256_bytes(write.original or b""),
                "after_sha256": sha256_bytes(write.updated),
            }
            for write in planned_writes
        ]
        used_mappings = [
            {"subsystem": subsystem, "from": old, "to": new}
            for subsystem, changes in (("wild", wild_changes), ("static_gift", mon_changes))
            for old, new in sorted(
                {
                    (str(change["from"]), str(change["to"]))
                    for change in changes
                    if change["from"] != change["to"]
                }
            )
        ]
        report: dict[str, Any] = {
            "schema_version": 1,
            "tool": "SGRand",
            "supported_tag": SUPPORTED_TAG,
            "seed_input": seed_text,
            "seed_numeric": streams.numeric_seed,
            "applied": mode is RunMode.APPLY,
            "rng_streams": [
                "wild-species",
                "static-gift-species",
                "static-gift-duplicate-resolution",
                "starters",
                "map-items",
                "scripted-items",
                "move-properties",
                "move-level-up-learnsets",
                "move-tm-tutor-compatibility",
                "species-abilities",
                "species-innates",
                "trainers-species",
                "trainers-levels-and-sizes",
                "trainers-themes",
                "trainers-moves",
                "trainers-items",
            ],
            "rules": {
                "wild_pokemon": "random_similar_strength_follow_evolutions",
                "trainers": trainer_config.profile.name,
                "starters": "nine_distinct_base_species_three_stage_lines",
                "static_pokemon": "random_similar_strength_follow_evolutions",
                "gift_pokemon": "random_similar_strength_follow_evolutions",
                "special_pokemon": "legendary_mythical_ultra_beast_paradox_vanilla",
                "move_effects": "vanilla",
                "abilities": ability_config.profile.name,
                "innates": ability_config.profile.name,
                "field_hidden_gift_items": "random",
                "early_lab_poke_balls": "vanilla_10",
                "key_story_hm_items": "vanilla",
            },
            "counts": {
                "species_available": len(species),
                "item_pool": len(item_pool),
                "files_changed": len(planned_writes),
                "wild_slots_changed": len(wild_changes),
                "static_and_gift_commands_changed": len(mon_changes),
                "map_items_changed": len(map_item_changes),
                "scripted_items_changed": len(scripted_item_changes),
                "level_up_learnsets_changed": learnset_output.report["learnsets"],
                "level_up_slots_changed": learnset_output.report["slots"],
                "compatibility_species_changed": compatibility_output.report["species"],
                "move_properties_changed": property_output.report["moves"],
                "normal_abilities_species_changed": ability_output.report["normal_species_changed"],
                "innates_species_changed": ability_output.report["innate_species_changed"],
                "trainer_species_changed": trainer_output.report["species_changed"],
                "trainers_changed": trainer_output.report["trainers_changed"],
            },
            "move_config": {
                "schema_version": move_config.schema_version,
                "profile": move_config.profile,
                "sha256": move_config.content_sha256,
                "source": move_config.source_label,
                "protected_moves": sorted(protected_moves),
                "event_moves_discovered": sorted(event_moves),
            },
            "moves": {
                "level_up": learnset_output.report,
                "tm_tutor_compatibility": compatibility_output.report,
                "properties": property_output.report,
            },
            "ability_config": {
                "schema_version": ability_config.schema_version,
                "profile": ability_config.profile.name,
                "sha256": ability_config.content_sha256,
                "source": ability_config.source_label,
                "blacklist": sorted(ability_config.blacklist),
                "special_abilities": sorted(ability_config.special_abilities),
            },
            "abilities": ability_output.report,
            "trainer_config": {
                "schema_version": trainer_config.schema_version,
                "profile": trainer_config.profile.name,
                "sha256": trainer_config.content_sha256,
                "source": trainer_config.source_label,
                "blacklist_species": sorted(trainer_config.blacklist_species),
                "blacklist_moves": sorted(trainer_config.blacklist_moves),
                "blacklist_items": sorted(trainer_config.blacklist_items),
            },
            "trainers": trainer_output.report,
            "starters": starter_changes,
            "species_mapping_used": used_mappings,
            "wild_changes": wild_changes,
            "static_and_gift_changes": mon_changes,
            "item_changes": map_item_changes + scripted_item_changes,
            "writes": write_records,
        }
        return Plan(report=report, writes=tuple(planned_writes), manifest_path=manifest)

    def run(
        self,
        source: Path,
        seed_text: str,
        mode: RunMode = RunMode.PREVIEW,
        manifest_path: Path | None = None,
        force: bool = False,
        move_config_path: Path | None = None,
        ability_config_path: Path | None = None,
        ability_profile: str | None = None,
        trainer_config_path: Path | None = None,
        trainer_profile: str | None = None,
    ) -> dict[str, Any]:
        plan = self.plan(
            source,
            seed_text,
            mode,
            manifest_path,
            force,
            move_config_path,
            ability_config_path,
            ability_profile,
            trainer_config_path,
            trainer_profile,
        )
        if mode is RunMode.APPLY:
            if any(write.path == plan.manifest_path for write in plan.writes):
                raise RandomizerError("Manifest path collides with a randomized source file")
            original_manifest = (
                plan.manifest_path.read_bytes() if plan.manifest_path.exists() else None
            )
            manifest_content = (
                json.dumps(plan.report, ensure_ascii=False, indent=2) + "\n"
            ).encode("utf-8")
            writes = (
                *plan.writes,
                PlannedWrite(plan.manifest_path, original_manifest, manifest_content),
            )
            self.transaction.apply(writes)
        return plan.report
