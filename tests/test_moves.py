from __future__ import annotations

import json
import random
import re
from importlib.resources import files
from pathlib import Path

import pytest

from sgrand.engine import Plan, Randomizer
from sgrand.errors import RandomizerError
from sgrand.move_config import DEFAULT_MOVE_CONFIG, load_move_config
from sgrand.moves import (
    LEVEL_MOVE_RE,
    discover_event_moves,
    transform_level_up_learnsets,
    transform_move_compatibility,
    transform_move_properties,
)
from sgrand.source import load_moves, load_species


def planned_text(plan: Plan, path: Path) -> str:
    return next(write.updated.decode() for write in plan.writes if write.path == path)


def configured_path(tmp_path: Path, **learnset_overrides: object) -> Path:
    document = json.loads(
        files("sgrand").joinpath("configs", DEFAULT_MOVE_CONFIG).read_text(encoding="utf-8")
    )
    document["learnsets"].update(learnset_overrides)
    path = tmp_path / "moves-config.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def move_constants(text: str) -> list[tuple[int, str]]:
    return [
        (int(match.group("level")), match.group("move")) for match in LEVEL_MOVE_RE.finditer(text)
    ]


def test_move_passes_are_separate_and_manifested(synthetic_source: Path) -> None:
    plan = Randomizer().plan(synthetic_source, "move-separation")
    relative = {write.path.relative_to(synthetic_source).as_posix() for write in plan.writes}
    assert "src/data/moves_info.h" in relative
    assert "src/data/pokemon/level_up_learnsets/gen_7.h" in relative
    assert "src/data/pokemon/level_up_learnsets/gen_9.h" in relative
    assert "src/data/pokemon/all_learnables.json" in relative
    assert plan.report["moves"]["level_up"]["slots"] > 0
    assert plan.report["moves"]["tm_tutor_compatibility"]["species"] > 0
    assert plan.report["moves"]["properties"]["moves"] > 0
    assert plan.report["move_config"]["schema_version"] == 1


def test_properties_never_change_effects_or_protected_moves(synthetic_source: Path) -> None:
    path = synthetic_source / "src/data/moves_info.h"
    original = path.read_text(encoding="utf-8")
    updated = planned_text(Randomizer().plan(synthetic_source, "properties"), path)
    assert re.findall(r"\.effect\s*=\s*([^,]+)", updated) == re.findall(
        r"\.effect\s*=\s*([^,]+)", original
    )
    block = re.compile(r"\[MOVE_CUT\].*?(?=\n\[MOVE_|\Z)", re.S)
    assert block.search(updated).group(0) == block.search(original).group(0)  # type: ignore[union-attr]


def test_event_references_extend_protected_moves(synthetic_source: Path) -> None:
    event = synthetic_source / "data/scripts/move_event.inc"
    event.write_text("buffermovename STR_VAR_1, MOVE_SYNTH_PHYSICAL_LOW\n", encoding="utf-8")
    moves = load_moves(synthetic_source)
    assert "MOVE_SYNTH_PHYSICAL_LOW" in discover_event_moves(synthetic_source, moves)
    plan = Randomizer().plan(synthetic_source, "event-protection")
    assert "MOVE_SYNTH_PHYSICAL_LOW" in plan.report["move_config"]["protected_moves"]


def test_signature_moves_remain_in_their_original_learnset(synthetic_source: Path) -> None:
    path = synthetic_source / "src/data/pokemon/level_up_learnsets/gen_9.h"
    path.write_text(
        path.read_text(encoding="utf-8").replace("MOVE_SYNTH_STATUS", "MOVE_VOLT_TACKLE", 1),
        encoding="utf-8",
    )
    config = load_move_config()
    output = transform_level_up_learnsets(
        synthetic_source,
        load_species(synthetic_source),
        load_moves(synthetic_source),
        config,
        config.protected_moves,
        random.Random(7),
    )
    assert "LEVEL_UP_MOVE( 1, MOVE_VOLT_TACKLE)" in output.files[path]


def test_legacy_sources_share_replacements_for_common_moves(synthetic_source: Path) -> None:
    config = load_move_config()
    output = transform_level_up_learnsets(
        synthetic_source,
        load_species(synthetic_source),
        load_moves(synthetic_source),
        config,
        config.protected_moves,
        random.Random(19),
    )
    gen9 = synthetic_source / "src/data/pokemon/level_up_learnsets/gen_9.h"
    gen7 = synthetic_source / "src/data/pokemon/level_up_learnsets/gen_7.h"
    assert move_constants(output.files[gen9]) == move_constants(output.files[gen7])


def test_configuration_rejects_unknown_schema_and_unprotected_hm(tmp_path: Path) -> None:
    raw = json.loads(
        files("sgrand").joinpath("configs", DEFAULT_MOVE_CONFIG).read_text(encoding="utf-8")
    )
    raw["schema_version"] = 99
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RandomizerError, match=r"Unsupported.*schema"):
        load_move_config(invalid)

    raw["schema_version"] = 1
    raw["protected_moves"].remove("MOVE_SURF")
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RandomizerError, match="cannot unprotect"):
        load_move_config(invalid)

    raw["protected_moves"].append("MOVE_SURF")
    raw["compatibility"]["preserve_protected_moves"] = False
    invalid.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RandomizerError, match="must preserve protected"):
        load_move_config(invalid)


def test_property_rules_hold_across_many_seeds(synthetic_source: Path, tmp_path: Path) -> None:
    config = load_move_config(
        configured_path(
            tmp_path,
            offensive_percent=100,
            stab_percent=100,
            category_match_percent=100,
        )
    )
    species = load_species(synthetic_source)
    moves = load_moves(synthetic_source)
    gen9 = synthetic_source / "src/data/pokemon/level_up_learnsets/gen_9.h"
    for seed in range(200):
        output = transform_level_up_learnsets(
            synthetic_source,
            species,
            moves,
            config,
            config.protected_moves,
            random.Random(seed),
        )
        learned = move_constants(output.files[gen9])
        assert any(level <= 5 and moves[move].is_offensive for level, move in learned)
        for level, constant in learned:
            move = moves[constant]
            assert move.is_offensive
            assert move.move_type in {"TYPE_GRASS", "TYPE_NORMAL"}
            assert move.category == "DAMAGE_CATEGORY_PHYSICAL"
            assert move.accuracy == 0 or move.accuracy >= config.learnsets.minimum_accuracy
            band = next(
                entry
                for entry in config.learnsets.progressive_power
                if level <= entry.through_level
            )
            assert band.minimum <= move.power <= band.maximum


def test_property_and_compatibility_invariants_across_many_seeds(
    synthetic_source: Path,
) -> None:
    config = load_move_config()
    species = load_species(synthetic_source)
    moves = load_moves(synthetic_source)
    properties_path = synthetic_source / "src/data/moves_info.h"
    compatibility_path = synthetic_source / "src/data/pokemon/all_learnables.json"
    original_compatibility = json.loads(compatibility_path.read_text(encoding="utf-8"))
    for seed in range(100):
        properties = transform_move_properties(
            synthetic_source,
            moves,
            config,
            config.protected_moves,
            random.Random(seed),
        )
        text = properties.files[properties_path]
        status_block = re.search(r"\[MOVE_SYNTH_STATUS\].*?(?=\n\[MOVE_|\Z)", text, re.S)
        assert status_block is not None
        assert ".power = 0," in status_block.group(0)
        assert ".category = DAMAGE_CATEGORY_STATUS," in status_block.group(0)
        for accuracy in map(int, re.findall(r"\.accuracy\s*=\s*(\d+)", text)):
            assert accuracy == 0 or accuracy >= config.properties.minimum_accuracy

        compatibility = transform_move_compatibility(
            synthetic_source,
            species,
            moves,
            config,
            config.protected_moves,
            random.Random(seed),
        )
        updated = json.loads(compatibility.files[compatibility_path])
        for species_name, old_moves in original_compatibility.items():
            for protected in config.protected_moves:
                assert (protected in updated[species_name]) == (protected in old_moves)
