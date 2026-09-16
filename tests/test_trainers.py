from __future__ import annotations

import json
import random
import re
from importlib.resources import files
from pathlib import Path

import pytest

from sgrand.errors import RandomizerError
from sgrand.source import load_moves, load_species, parse_items
from sgrand.trainer_config import (
    DEFAULT_TRAINER_CONFIG,
    load_trainer_config,
    validate_trainer_references,
)
from sgrand.trainers import (
    _forced_rival_species,
    _rival_stages,
    transform_trainers,
)


def starters() -> list[str]:
    return [f"SPECIES_SYNTH_{family}0" for family in "ABCDEFGHI"]


def randomize(
    source: Path,
    seed: int,
    *,
    profile: str = "Balanced",
    config_path: Path | None = None,
    move_seed: int | None = None,
):
    species = load_species(source)
    moves = load_moves(source)
    items = parse_items(source)
    config = load_trainer_config(config_path, profile)
    validate_trainer_references(config, species, moves, items)
    return transform_trainers(
        source,
        species,
        moves,
        items,
        {constant: mon.abilities for constant, mon in species.items()},
        starters(),
        config,
        random.Random(seed),
        random.Random(seed ^ 0x11),
        random.Random(seed ^ 0x22),
        random.Random(move_seed if move_seed is not None else seed ^ 0x33),
        random.Random(seed ^ 0x44),
    )


def configured_path(tmp_path: Path, mutate: object) -> Path:
    document = json.loads(
        files("sgrand").joinpath("configs", DEFAULT_TRAINER_CONFIG).read_text(encoding="utf-8")
    )
    assert callable(mutate)
    mutate(document)
    path = tmp_path / "trainers-config.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def test_balanced_snapshot(synthetic_source: Path) -> None:
    output = transform_trainers(
        synthetic_source,
        load_species(synthetic_source),
        load_moves(synthetic_source),
        parse_items(synthetic_source),
        {constant: mon.abilities for constant, mon in load_species(synthetic_source).items()},
        starters(),
        load_trainer_config(),
        *[random.Random(seed) for seed in range(101, 106)],
    )
    snapshot = Path(__file__).parent / "snapshots/trainers-balanced.party"
    assert output.text == snapshot.read_text(encoding="utf-8")


def test_balanced_properties_across_many_seeds(synthetic_source: Path) -> None:
    species = load_species(synthetic_source)
    config = load_trainer_config()
    learnables = json.loads(
        (synthetic_source / "src/data/pokemon/all_learnables.json").read_text(encoding="utf-8")
    )
    items = parse_items(synthetic_source)
    original = {
        "TRAINER_SYNTH_REGULAR#0": ("SPECIES_SYNTH_A0", "SPECIES_SYNTH_B0"),
        "TRAINER_SYNTH_LEADER#1": ("SPECIES_SYNTH_C1", "SPECIES_SYNTH_D1"),
        "TRAINER_SYNTH_RIVAL#2": ("SPECIES_SYNTH_E1",),
        "TRAINER_SYNTH_BOSS#3": ("SPECIES_SYNTH_F2",),
    }
    categories = {
        "TRAINER_SYNTH_REGULAR#0": "trainers",
        "TRAINER_SYNTH_LEADER#1": "leaders",
        "TRAINER_SYNTH_RIVAL#2": "rival",
        "TRAINER_SYNTH_BOSS#3": "bosses",
    }
    for seed in range(120):
        output = randomize(synthetic_source, seed)
        assert output.report["sections"] == 4
        assert output.report["double_synergy_teams"] == 1
        for key, assigned in output.assignments.items():
            assert len(assigned) == len(original[key])
            assert len(assigned) == len(set(assigned))
            rules = config.profile.categories[categories[key]]
            for before, after in zip(original[key], assigned, strict=True):
                assert abs(species[before].bst - species[after].bst) <= rules.maximum_bst_delta
                if categories[key] != "bosses":
                    assert not species[after].is_special
        assert output.text.count("Name:") == 4
        assert output.text.count("Pic:") == 4
        assert output.text.count("=== TRAINER_") == 4
        for paragraph in re.split(r"\n\s*\n", output.text):
            lines = paragraph.splitlines()
            if not lines or not lines[0].startswith("SPECIES_"):
                continue
            constant = lines[0].split(" @ ", 1)[0]
            authored = {line.removeprefix("- ") for line in lines if line.startswith("- ")}
            assert authored <= set(learnables[constant.removeprefix("SPECIES_")])
            if " @ " in lines[0]:
                assert lines[0].split(" @ ", 1)[1] in items


def test_chaos_team_sizes_levels_and_determinism(synthetic_source: Path) -> None:
    first = randomize(synthetic_source, 73, profile="Chaos")
    second = randomize(synthetic_source, 73, profile="Chaos")
    assert first.text == second.text
    assert first.assignments == second.assignments
    assert all(1 <= len(team) <= 6 for team in first.assignments.values())
    assert len(first.assignments["TRAINER_SYNTH_BOSS#3"]) == 6
    levels = [int(value) for value in re.findall(r"^Level: (\d+)$", first.text, re.M)]
    assert levels
    assert all(2 <= level <= 100 for level in levels)


def test_move_rng_does_not_shift_species_assignments(synthetic_source: Path) -> None:
    first = randomize(synthetic_source, 91, move_seed=1)
    second = randomize(synthetic_source, 91, move_seed=999)
    assert first.assignments == second.assignments
    assert first.text != second.text


def test_rival_starter_progression_is_coherent(synthetic_source: Path) -> None:
    stages = _rival_stages(starters(), load_species(synthetic_source))
    assert stages["CHIKORITA"] == (
        "SPECIES_SYNTH_A0",
        "SPECIES_SYNTH_A1",
        "SPECIES_SYNTH_A2",
    )
    assert (
        _forced_rival_species("TRAINER_RIVAL_CHIKORITA_1", "SPECIES_CHIKORITA", stages)
        == "SPECIES_SYNTH_A0"
    )
    assert (
        _forced_rival_species("TRAINER_RIVAL_CHIKORITA_3", "SPECIES_BAYLEEF", stages)
        == "SPECIES_SYNTH_A1"
    )
    assert (
        _forced_rival_species("TRAINER_RIVAL_CHIKORITA_7", "SPECIES_MEGANIUM", stages)
        == "SPECIES_SYNTH_A2"
    )


def test_configuration_and_structural_validation(synthetic_source: Path, tmp_path: Path) -> None:
    def bad_schema(document: dict[str, object]) -> None:
        document["schema_version"] = 99

    with pytest.raises(RandomizerError, match="Unsupported trainer configuration schema"):
        load_trainer_config(configured_path(tmp_path, bad_schema))

    def unknown_species(document: dict[str, object]) -> None:
        document["blacklist_species"] = ["SPECIES_NOT_REAL"]

    config = load_trainer_config(configured_path(tmp_path, unknown_species))
    with pytest.raises(RandomizerError, match="unknown species"):
        validate_trainer_references(
            config,
            load_species(synthetic_source),
            load_moves(synthetic_source),
            parse_items(synthetic_source),
        )

    party = synthetic_source / "src/data/trainers.party"
    party.write_text("not competitive syntax\n", encoding="utf-8")
    with pytest.raises(RandomizerError, match="No trainer sections"):
        randomize(synthetic_source, 4)
