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
    assert report["counts"]["files_changed"] > 0
    assert {relative: (source / relative).read_bytes() for relative in observed} == before
