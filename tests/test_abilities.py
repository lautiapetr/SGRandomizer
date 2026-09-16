from __future__ import annotations

import json
import random
from importlib.resources import files
from pathlib import Path

import pytest

from sgrand.abilities import transform_species_abilities
from sgrand.ability_config import (
    DEFAULT_ABILITY_CONFIG,
    load_ability_config,
    validate_ability_references,
)
from sgrand.errors import RandomizerError
from sgrand.source import (
    discover_form_locked_abilities,
    load_abilities,
    load_species,
)


def configured_path(tmp_path: Path, mutate: object) -> Path:
    document = json.loads(
        files("sgrand").joinpath("configs", DEFAULT_ABILITY_CONFIG).read_text(encoding="utf-8")
    )
    assert callable(mutate)
    mutate(document)
    path = tmp_path / "abilities-config.json"
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path


def randomize(
    source: Path,
    seed: int,
    *,
    profile: str = "Balanced",
    config_path: Path | None = None,
):
    species = load_species(source)
    abilities = load_abilities(source)
    config = load_ability_config(config_path, profile)
    form_locked = discover_form_locked_abilities(source)
    validate_ability_references(config, abilities, form_locked)
    return transform_species_abilities(
        source,
        species,
        abilities,
        config,
        form_locked,
        random.Random(seed),
        random.Random(seed ^ 0xA5A5),
    )


def nonempty(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(value for value in values if value != "ABILITY_NONE")


def test_balanced_rules_and_follow_evolutions_across_many_seeds(
    synthetic_source: Path,
) -> None:
    species = load_species(synthetic_source)
    abilities = load_abilities(synthetic_source)
    vanilla_counts = {constant: len(mon.innates) for constant, mon in species.items()}
    for seed in range(150):
        output = randomize(synthetic_source, seed)
        for constant in output.ability_assignments:
            main = nonempty(output.ability_assignments[constant])
            innates = output.innate_assignments[constant]
            assert not set(main) & set(innates)
            assert len(main) == len(set(main))
            assert len(innates) == len(set(innates))
            assert len(innates) == vanilla_counts[constant]
            assert all(1 <= abilities[value].ai_rating <= 8 for value in main + innates)
        for family in "ABCDEFGHIJ":
            constants = [f"SPECIES_SYNTH_{family}{stage}" for stage in range(3)]
            main_sets = [nonempty(output.ability_assignments[value]) for value in constants]
            assert main_sets[0] == main_sets[1] == main_sets[2]
            innate_sets = [output.innate_assignments[value] for value in constants]
            assert innate_sets[1][:1] == innate_sets[0]
            assert innate_sets[2][:2] == innate_sets[1]


def test_normal_and_innate_rng_streams_are_independent(synthetic_source: Path) -> None:
    species = load_species(synthetic_source)
    abilities = load_abilities(synthetic_source)
    config = load_ability_config()
    first = transform_species_abilities(
        synthetic_source,
        species,
        abilities,
        config,
        frozenset(),
        random.Random(17),
        random.Random(23),
    )
    second = transform_species_abilities(
        synthetic_source,
        species,
        abilities,
        config,
        frozenset(),
        random.Random(17),
        random.Random(999),
    )
    assert first.ability_assignments == second.ability_assignments
    assert first.innate_assignments != second.innate_assignments


def test_chaos_uses_fixed_innate_count_and_is_deterministic(synthetic_source: Path) -> None:
    first = randomize(synthetic_source, 81, profile="Chaos")
    second = randomize(synthetic_source, 81, profile="Chaos")
    assert first.ability_assignments == second.ability_assignments
    assert first.innate_assignments == second.innate_assignments
    assert all(len(values) == 3 for values in first.innate_assignments.values())
    for constant, innates in first.innate_assignments.items():
        assert not set(nonempty(first.ability_assignments[constant])) & set(innates)


def test_species_locked_ability_preserves_both_domains(synthetic_source: Path) -> None:
    docs_path = synthetic_source / "docs/data/romhack-docs.json"
    document = json.loads(docs_path.read_text(encoding="utf-8"))
    target = document["species"][0]
    target["abilities"] = ["ABILITY_FORECAST"]
    docs_path.write_text(json.dumps(document), encoding="utf-8")
    family_path = synthetic_source / "src/data/pokemon/species_info/gen_1_families.h"
    family_path.write_text(
        family_path.read_text(encoding="utf-8").replace(
            "ABILITY_SYNTH_LOW, ABILITY_NONE, ABILITY_SYNTH_MID",
            "ABILITY_FORECAST, ABILITY_NONE, ABILITY_NONE",
            1,
        ),
        encoding="utf-8",
    )
    form_path = synthetic_source / "src/data/pokemon/form_change_tables.h"
    form_path.write_text(
        "{FORM_CHANGE_BATTLE_WEATHER, SPECIES_SYNTH_A0, 0, ABILITY_FORECAST},\n",
        encoding="utf-8",
    )
    output = randomize(synthetic_source, 7)
    assert output.ability_assignments["SPECIES_SYNTH_A0"] == (
        "ABILITY_FORECAST",
        "ABILITY_NONE",
        "ABILITY_NONE",
    )
    assert output.innate_assignments["SPECIES_SYNTH_A0"] == ("ABILITY_SYNTH_INNATE_A",)


def test_custom_blacklist_and_configuration_validation(
    synthetic_source: Path, tmp_path: Path
) -> None:
    def add_blacklist(document: dict[str, object]) -> None:
        document["blacklist"] = ["ABILITY_SYNTH_ALT_A"]

    path = configured_path(tmp_path, add_blacklist)
    for seed in range(40):
        output = randomize(synthetic_source, seed, config_path=path)
        assigned = {
            value
            for values in (
                *output.ability_assignments.values(),
                *output.innate_assignments.values(),
            )
            for value in values
        }
        assert "ABILITY_SYNTH_ALT_A" not in assigned

    def bad_schema(document: dict[str, object]) -> None:
        document["schema_version"] = 99

    with pytest.raises(RandomizerError, match="Unsupported ability configuration schema"):
        load_ability_config(configured_path(tmp_path, bad_schema))

    def unprotect(document: dict[str, object]) -> None:
        locked = document["species_locked_abilities"]
        assert isinstance(locked, list)
        locked.remove("ABILITY_FORECAST")

    with pytest.raises(RandomizerError, match="cannot unprotect"):
        load_ability_config(configured_path(tmp_path, unprotect))

    def unknown_reference(document: dict[str, object]) -> None:
        document["blacklist"] = ["ABILITY_NOT_IN_CHECKOUT"]

    unknown = load_ability_config(configured_path(tmp_path, unknown_reference))
    with pytest.raises(RandomizerError, match="absent from the checkout"):
        validate_ability_references(
            unknown,
            load_abilities(synthetic_source),
            discover_form_locked_abilities(synthetic_source),
        )


def test_structural_validation_rejects_unresolved_species_storage(
    synthetic_source: Path,
) -> None:
    family_path = synthetic_source / "src/data/pokemon/species_info/gen_1_families.h"
    family_path.write_text(
        family_path.read_text(encoding="utf-8").replace(".abilities =", ".unknown =", 1),
        encoding="utf-8",
    )
    with pytest.raises(RandomizerError, match=r"Cannot resolve active \.abilities storage"):
        randomize(synthetic_source, 5)


def test_engine_reports_separate_streams_and_profile(synthetic_source: Path) -> None:
    from sgrand.engine import Randomizer

    report = Randomizer().run(synthetic_source, "ability-report", ability_profile="Chaos")
    assert "species-abilities" in report["rng_streams"]
    assert "species-innates" in report["rng_streams"]
    assert report["ability_config"]["profile"] == "Chaos"
    assert report["counts"]["normal_abilities_species_changed"] > 0
    assert report["counts"]["innates_species_changed"] > 0
