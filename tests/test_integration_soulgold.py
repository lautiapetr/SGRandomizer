from __future__ import annotations

import os
from pathlib import Path

import pytest

from sgrand.engine import Randomizer


@pytest.mark.integration
def test_preview_real_soulgold_checkout() -> None:
    source_text = os.environ.get("SOULGOLD_SOURCE")
    if not source_text:
        pytest.skip("set SOULGOLD_SOURCE to a v.1.1.4 checkout")
    source = Path(source_text)
    observed = (
        "src/data/wild_encounters.json",
        "src/data/moves_info.h",
        "src/data/pokemon/all_learnables.json",
        "src/data/pokemon/level_up_learnsets/gen_7.h",
        "src/data/pokemon/level_up_learnsets/gen_9.h",
        "src/data/pokemon/species_info/gen_1_families.h",
        "src/data/pokemon/species_info/gen_9_families.h",
        "src/data/trainers.party",
    )
    before = {relative: (source / relative).read_bytes() for relative in observed}
    report = Randomizer().run(source, "integration-seed")
    assert report["counts"]["wild_slots_changed"] > 0
    assert report["counts"]["level_up_slots_changed"] > 0
    assert report["counts"]["compatibility_species_changed"] > 0
    assert report["counts"]["move_properties_changed"] > 0
    assert report["counts"]["normal_abilities_species_changed"] > 0
    assert report["counts"]["innates_species_changed"] > 0
    assert report["abilities"]["protected_species"] > 0
    assert report["counts"]["trainers_changed"] > 0
    assert report["trainers"]["sections"] == 630
    assert report["trainers"]["rival_starter_slots"] == 27
    assert report["trainers"]["unresolved_party_entries_preserved"] == 1
    assert report["trainers"]["categories"]["rival"] == 39
    assert report["counts"]["files_changed"] > 0
    assert {relative: (source / relative).read_bytes() for relative in observed} == before


@pytest.mark.integration
def test_chaos_trainer_profile_preserves_one_rival_starter_per_branch() -> None:
    source_text = os.environ.get("SOULGOLD_SOURCE")
    if not source_text:
        pytest.skip("set SOULGOLD_SOURCE to a v.1.1.4 checkout")
    report = Randomizer().run(
        Path(source_text),
        "integration-chaos-trainers",
        trainer_profile="Chaos",
        ability_profile="Chaos",
    )
    assert report["trainer_config"]["profile"] == "Chaos"
    assert report["trainers"]["rival_starter_slots"] == 27
    assert report["trainers"]["pokemon_written"] != 1947
    assert report["trainers"]["categories"]["rival"] == 39
