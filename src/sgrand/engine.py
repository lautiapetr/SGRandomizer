"""Application service that composes all phase-1 passes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .constants import DEFAULT_MANIFEST, SUPPORTED_TAG
from .errors import RandomizerError
from .models import PlannedWrite
from .rng import RngStreams
from .source import load_species, parse_items, validate_source
from .species import build_species_mapping, choose_starters
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
        wild_mapping = build_species_mapping(species, streams.stream("wild-species"))
        static_mapping = build_species_mapping(species, streams.stream("static-gift-species"))
        starters = choose_starters(species, streams.stream("starters"))
        items = parse_items(source)
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
            ],
            "rules": {
                "wild_pokemon": "random_similar_strength_follow_evolutions",
                "trainers": "vanilla",
                "starters": "nine_distinct_base_species_three_stage_lines",
                "static_pokemon": "random_similar_strength_follow_evolutions",
                "gift_pokemon": "random_similar_strength_follow_evolutions",
                "special_pokemon": "legendary_mythical_ultra_beast_paradox_vanilla",
                "species_moves_abilities_innates": "vanilla",
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
            },
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
    ) -> dict[str, Any]:
        plan = self.plan(source, seed_text, mode, manifest_path, force)
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
