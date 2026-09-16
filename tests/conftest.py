from __future__ import annotations

import json
from pathlib import Path

import pytest

from sgrand.ability_config import load_ability_config
from sgrand.move_config import load_move_config

SYNTHETIC_MOVES = {
    "MOVE_SYNTH_PHYSICAL_LOW": (40, 100, 35, "TYPE_NORMAL", "DAMAGE_CATEGORY_PHYSICAL"),
    "MOVE_SYNTH_PHYSICAL_LOW_ALT": (50, 90, 25, "TYPE_GRASS", "DAMAGE_CATEGORY_PHYSICAL"),
    "MOVE_SYNTH_PHYSICAL_MID": (70, 95, 20, "TYPE_FIRE", "DAMAGE_CATEGORY_PHYSICAL"),
    "MOVE_SYNTH_PHYSICAL_HIGH": (120, 80, 5, "TYPE_ROCK", "DAMAGE_CATEGORY_PHYSICAL"),
    "MOVE_SYNTH_SPECIAL_LOW": (40, 100, 30, "TYPE_GRASS", "DAMAGE_CATEGORY_SPECIAL"),
    "MOVE_SYNTH_SPECIAL_MID": (80, 90, 15, "TYPE_WATER", "DAMAGE_CATEGORY_SPECIAL"),
    "MOVE_SYNTH_SPECIAL_HIGH": (120, 75, 5, "TYPE_PSYCHIC", "DAMAGE_CATEGORY_SPECIAL"),
    "MOVE_SYNTH_STATUS": (0, 100, 20, "TYPE_NORMAL", "DAMAGE_CATEGORY_STATUS"),
    "MOVE_SYNTH_STATUS_ALT": (0, 85, 15, "TYPE_GRASS", "DAMAGE_CATEGORY_STATUS"),
    "MOVE_SYNTH_INACCURATE": (90, 50, 10, "TYPE_FIRE", "DAMAGE_CATEGORY_SPECIAL"),
}


def _species_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    dex = 1
    for family in "ABCDEFGHIJ":
        constants = [f"SPECIES_SYNTH_{family}{stage}" for stage in range(3)]
        for stage, constant in enumerate(constants):
            evolutions = [{"target": constants[stage + 1]}] if stage < 2 else []
            rows.append(
                {
                    "constant": constant,
                    "name": f"Synthetic {family}{stage}",
                    "dex": dex,
                    "bst": 300 + stage * 100 + (ord(family) - ord("A")),
                    "categories": [],
                    "evolutions": evolutions,
                    "types": ["TYPE_GRASS", "TYPE_NORMAL"],
                    "stats": {"atk": 60 + stage * 10, "spa": 50 + stage * 10},
                    "abilities": ["ABILITY_SYNTH_LOW", "ABILITY_SYNTH_MID"],
                    "innates": [
                        "ABILITY_SYNTH_INNATE_A",
                        "ABILITY_SYNTH_INNATE_B",
                        "ABILITY_SYNTH_INNATE_C",
                    ][: stage + 1],
                }
            )
            dex += 1
    rows.extend(
        [
            {
                "constant": "SPECIES_SYNTH_LEGEND",
                "name": "Synthetic Legend",
                "dex": dex,
                "bst": 600,
                "categories": ["legendary"],
                "evolutions": [],
                "types": ["TYPE_PSYCHIC"],
                "stats": {"atk": 100, "spa": 120},
                "abilities": ["ABILITY_SYNTH_HIGH"],
                "innates": ["ABILITY_SYNTH_INNATE_A"],
            },
            {
                "constant": "SPECIES_SYNTH_ULTRA",
                "name": "Synthetic Ultra",
                "dex": dex + 1,
                "bst": 570,
                "categories": [],
                "evolutions": [],
                "types": ["TYPE_BUG"],
                "stats": {"atk": 100, "spa": 100},
                "abilities": ["ABILITY_SYNTH_MID"],
                "innates": ["ABILITY_SYNTH_INNATE_B"],
            },
            {
                "constant": "SPECIES_SYNTH_A0_MEGA",
                "name": "Synthetic Mega",
                "dex": dex + 2,
                "bst": 650,
                "categories": ["mega"],
                "evolutions": [],
                "types": ["TYPE_GRASS"],
                "stats": {"atk": 120, "spa": 120},
                "abilities": ["ABILITY_SYNTH_HIGH"],
                "innates": ["ABILITY_SYNTH_INNATE_C"],
            },
        ]
    )
    return rows


@pytest.fixture
def synthetic_source(tmp_path: Path) -> Path:
    source = tmp_path / "synthetic-soulgold"
    paths = [
        "docs/data",
        "src/data/pokemon/species_info",
        "src/data/pokemon/level_up_learnsets",
        "include/constants",
        "data/maps/TestMap",
        "data/maps/NewBarkTown_Lab",
        "data/scripts",
    ]
    for relative in paths:
        (source / relative).mkdir(parents=True, exist_ok=True)

    move_config = load_move_config()
    ability_config = load_ability_config()
    configured_moves = (
        move_config.protected_moves | move_config.signature_moves | move_config.excluded_moves
    )
    move_values = dict(SYNTHETIC_MOVES)
    for constant in configured_moves:
        move_values.setdefault(
            constant,
            (50, 100, 15, "TYPE_NORMAL", "DAMAGE_CATEGORY_PHYSICAL"),
        )
    move_rows = {
        constant: {
            "constant": constant,
            "power": values[0],
            "accuracy": values[1],
            "pp": values[2],
            "type": values[3],
            "category": values[4],
        }
        for constant, values in move_values.items()
    }
    species_rows = _species_rows()
    (source / "docs/data/romhack-docs.json").write_text(
        json.dumps({"species": species_rows, "moves": move_rows}), encoding="utf-8"
    )

    def ability_slots(row: dict[str, object]) -> list[str]:
        configured = [str(value) for value in row["abilities"]]  # type: ignore[union-attr]
        return (
            [configured[0], "ABILITY_NONE", configured[1]]
            if len(configured) == 2
            else [configured[0], "ABILITY_NONE", "ABILITY_NONE"]
        )

    species_blocks = "\n".join(
        f"[{row['constant']}] = {{\n"
        "    .abilities = { "
        + ", ".join(ability_slots(row))
        + " },\n"
        + "    .innates = { "
        + ", ".join(str(value) for value in row["innates"])
        + " },\n"
        "    .levelUpLearnset = sSyntheticLevelUpLearnset,\n"
        + ("    .isUltraBeast = TRUE,\n" if row["constant"] == "SPECIES_SYNTH_ULTRA" else "")
        + "},"
        for row in species_rows
    )
    (source / "src/data/pokemon/species_info/gen_1_families.h").write_text(
        species_blocks + "\n", encoding="utf-8"
    )
    synthetic_abilities = {
        "ABILITY_NONE": 0,
        "ABILITY_SYNTH_LOW": 2,
        "ABILITY_SYNTH_MID": 5,
        "ABILITY_SYNTH_HIGH": 8,
        "ABILITY_SYNTH_ALT_A": 1,
        "ABILITY_SYNTH_ALT_B": 3,
        "ABILITY_SYNTH_ALT_C": 4,
        "ABILITY_SYNTH_ALT_D": 6,
        "ABILITY_SYNTH_ALT_E": 7,
        "ABILITY_SYNTH_INNATE_A": 2,
        "ABILITY_SYNTH_INNATE_B": 5,
        "ABILITY_SYNTH_INNATE_C": 7,
    }
    for constant in ability_config.species_locked_abilities | ability_config.special_abilities:
        synthetic_abilities.setdefault(constant, 5)
    (source / "src/data/abilities.h").write_text(
        "const struct AbilityInfo gAbilitiesInfo[] =\n{\n"
        + "\n".join(
            f"    [{constant}] =\n    {{\n        .aiRating = {rating},\n    }},"
            for constant, rating in sorted(synthetic_abilities.items())
        )
        + "\n};\n",
        encoding="utf-8",
    )
    (source / "src/data/pokemon/form_change_tables.h").write_text(
        "// Synthetic fixture has no form-dependent abilities.\n", encoding="utf-8"
    )
    learnset = (
        "#define LEVEL_UP_MOVE(lvl, moveLearned) {.move = moveLearned, .level = lvl}\n"
        "#define LEVEL_UP_END {.move = LEVEL_UP_MOVE_END, .level = 0}\n\n"
        "static const struct LevelUpMove sSyntheticLevelUpLearnset[] = {\n"
        "    LEVEL_UP_MOVE( 1, MOVE_SYNTH_STATUS),\n"
        "    LEVEL_UP_MOVE( 4, MOVE_SYNTH_PHYSICAL_LOW),\n"
        "    LEVEL_UP_MOVE(12, MOVE_SYNTH_SPECIAL_MID),\n"
        "    LEVEL_UP_MOVE(40, MOVE_SYNTH_PHYSICAL_HIGH),\n"
        "    LEVEL_UP_END\n"
        "};\n"
    )
    for generation in (7, 9):
        (source / f"src/data/pokemon/level_up_learnsets/gen_{generation}.h").write_text(
            learnset, encoding="utf-8"
        )
    move_info = "\n\n".join(
        f"[{constant}] =\n{{\n"
        f"    .effect = EFFECT_HIT,\n"
        f"    .power = {values[0]},\n"
        f"    .type = {values[3]},\n"
        f"    .accuracy = {values[1]},\n"
        f"    .pp = {values[2]},\n"
        f"    .category = {values[4]},\n"
        "},"
        for constant, values in move_values.items()
    )
    (source / "src/data/moves_info.h").write_text(move_info + "\n", encoding="utf-8")
    tm_moves = sorted(set(SYNTHETIC_MOVES) | move_config.protected_moves)
    continuation = "\\"
    (source / "include/constants/tms_hms.h").write_text(
        f"#define FOREACH_TM(F) {continuation}\n"
        + f" {continuation}\n".join(f"    F({move.removeprefix('MOVE_')})" for move in tm_moves)
        + "\n",
        encoding="utf-8",
    )
    learnables = {
        str(row["constant"]).removeprefix("SPECIES_"): sorted(move_values) for row in species_rows
    }
    (source / "src/data/pokemon/all_learnables.json").write_text(
        json.dumps(learnables, indent=2) + "\n", encoding="utf-8"
    )
    (source / "src/data/pokemon/special_movesets.json").write_text(
        json.dumps(
            {
                "universalMoves": [],
                "signatureTeachables": [],
                "dedicatedTutors": {},
                "extraTutors": ["MOVE_SYNTH_STATUS_ALT"],
                "speciesTeachables": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (source / "include/constants/items.h").write_text(
        "enum {\n"
        " ITEM_NONE = 0,\n"
        " ITEM_SYNTH_ALPHA = 1,\n"
        " ITEM_SYNTH_BETA = 2,\n"
        " ITEM_POKE_BALL = 3,\n"
        " ITEM_SYNTH_KEY = 4,\n"
        "};\n",
        encoding="utf-8",
    )
    (source / "include/constants/species.h").write_text(
        "// Synthetic species constants have no aliases.\n", encoding="utf-8"
    )
    (source / "src/data/items.h").write_text(
        "[ITEM_NONE] = { .pocket = POCKET_ITEMS },\n"
        "[ITEM_SYNTH_ALPHA] = { .pocket = POCKET_ITEMS },\n"
        "[ITEM_SYNTH_BETA] = { .pocket = POCKET_MEDICINE },\n"
        "[ITEM_POKE_BALL] = { .pocket = POCKET_POKE_BALLS },\n"
        "[ITEM_SYNTH_KEY] = { .pocket = POCKET_KEY_ITEMS, .importance = TRUE },\n",
        encoding="utf-8",
    )
    (source / "src/data/trainers.party").write_text(
        "=== TRAINER_SYNTH_REGULAR ===\n"
        "Name: Regular\n"
        "Class: Youngster\n"
        "Pic: Youngster\n"
        "Gender: Male\n"
        "Music: Male\n"
        "Double Battle: No\n"
        "AI: Basic Trainer\n\n"
        "SPECIES_SYNTH_A0 @ ITEM_SYNTH_ALPHA\n"
        "Level: 12\n"
        "Ability: ABILITY_SYNTH_LOW\n"
        "IVs: 0 HP / 0 Atk / 0 Def / 0 SpA / 0 SpD / 0 Spe\n"
        "- MOVE_SYNTH_PHYSICAL_LOW\n"
        "- MOVE_SYNTH_STATUS\n\n"
        "SPECIES_SYNTH_B0\n"
        "Level: 13\n"
        "IVs: 0 HP / 0 Atk / 0 Def / 0 SpA / 0 SpD / 0 Spe\n\n"
        "=== TRAINER_SYNTH_LEADER ===\n"
        "Name: Leader\n"
        "Class: Leader\n"
        "Pic: Leader\n"
        "Gender: Female\n"
        "Music: Female\n"
        "Double Battle: Yes\n"
        "AI: Smart Trainer\n\n"
        "SPECIES_SYNTH_C1 @ ITEM_SYNTH_ALPHA\n"
        "Level: 30\n"
        "Ability: ABILITY_SYNTH_MID\n"
        "IVs: 20 HP / 20 Atk / 20 Def / 20 SpA / 20 SpD / 20 Spe\n"
        "- MOVE_SYNTH_STATUS_ALT\n"
        "- MOVE_SYNTH_SPECIAL_MID\n\n"
        "SPECIES_SYNTH_D1\n"
        "Level: 30\n"
        "IVs: 20 HP / 20 Atk / 20 Def / 20 SpA / 20 SpD / 20 Spe\n"
        "- MOVE_SYNTH_PHYSICAL_MID\n"
        "- MOVE_SYNTH_STATUS\n\n"
        "=== TRAINER_SYNTH_RIVAL ===\n"
        "Name: {RIVAL}\n"
        "Class: Rival\n"
        "Pic: Rival\n"
        "Gender: Male\n"
        "Music: Rival\n"
        "Double Battle: No\n"
        "AI: Smart Trainer\n\n"
        "SPECIES_SYNTH_E1\n"
        "Level: 28\n"
        "IVs: 15 HP / 15 Atk / 15 Def / 15 SpA / 15 SpD / 15 Spe\n"
        "- MOVE_SYNTH_PHYSICAL_MID\n\n"
        "=== TRAINER_SYNTH_BOSS ===\n"
        "Name: Boss\n"
        "Class: Champion\n"
        "Pic: Champion\n"
        "Gender: Male\n"
        "Music: Champion\n"
        "Double Battle: No\n"
        "AI: Smart Trainer\n\n"
        "SPECIES_SYNTH_F2 @ ITEM_SYNTH_ALPHA\n"
        "Level: 60\n"
        "IVs: 31 HP / 31 Atk / 31 Def / 31 SpA / 31 SpD / 31 Spe\n"
        "- MOVE_SYNTH_PHYSICAL_HIGH\n"
        "- MOVE_SYNTH_SPECIAL_HIGH\n",
        encoding="utf-8",
    )
    wild = {
        "wild_encounter_groups": [
            {
                "label": "gSynthetic",
                "for_maps": True,
                "encounters": [
                    {
                        "map": "MAP_TEST",
                        "base_label": "gTest",
                        "land_mons": {
                            "encounter_rate": 20,
                            "mons": [
                                {"min_level": 2, "max_level": 3, "species": "SPECIES_SYNTH_A0"},
                                {"min_level": 5, "max_level": 5, "species": "SPECIES_SYNTH_A1"},
                                {
                                    "min_level": 50,
                                    "max_level": 50,
                                    "species": "SPECIES_SYNTH_LEGEND",
                                },
                                {
                                    "min_level": 50,
                                    "max_level": 50,
                                    "species": "SPECIES_SYNTH_ULTRA",
                                },
                            ],
                        },
                    }
                ],
            }
        ]
    }
    (source / "src/data/wild_encounters.json").write_text(
        json.dumps(wild, indent=2) + "\n", encoding="utf-8"
    )
    slot_names = ("ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE")
    starters = "\n".join(
        f"[BALL_SYNTH_{slot}] = {{SPECIES_SYNTH_{family}0, 5, {index % 3}}},"
        for index, (slot, family) in enumerate(zip(slot_names, "ABCDEFGHI", strict=True))
    )
    (source / "src/ui_birch_case.c").write_text(starters + "\n", encoding="utf-8")
    (source / "data/maps/TestMap/scripts.pory").write_text(
        "script Test {\n"
        "  givemon SPECIES_SYNTH_A0, 5\n"
        "  giveegg SPECIES_SYNTH_LEGEND\n"
        "  giveitem ITEM_SYNTH_ALPHA\n"
        "  finditem ITEM_SYNTH_BETA\n"
        "}\n",
        encoding="utf-8",
    )
    (source / "data/maps/NewBarkTown_Lab/scripts.pory").write_text(
        "script Supplies {\n  giveitem ITEM_POKE_BALL, 10\n}\n", encoding="utf-8"
    )
    (source / "data/scripts/static_pokemon.inc").write_text(
        "setwildbattle SPECIES_SYNTH_B0, 20\n", encoding="utf-8"
    )
    (source / "data/maps/TestMap/map.json").write_text(
        json.dumps(
            {
                "object_events": [
                    {
                        "local_id": "LOCALID_ITEM",
                        "graphics_id": "OBJ_EVENT_GFX_ITEM_BALL",
                        "trainer_sight_or_berry_tree_id": "ITEM_SYNTH_ALPHA",
                    }
                ],
                "bg_events": [{"type": "hidden_item", "item": "ITEM_SYNTH_BETA"}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (source / "data/maps/NewBarkTown_Lab/map.json").write_text(
        '{"object_events": [], "bg_events": []}\n', encoding="utf-8"
    )
    return source
