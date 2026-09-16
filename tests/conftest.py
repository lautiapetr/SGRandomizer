from __future__ import annotations

import json
from pathlib import Path

import pytest


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
            },
            {
                "constant": "SPECIES_SYNTH_ULTRA",
                "name": "Synthetic Ultra",
                "dex": dex + 1,
                "bst": 570,
                "categories": [],
                "evolutions": [],
            },
            {
                "constant": "SPECIES_SYNTH_A0_MEGA",
                "name": "Synthetic Mega",
                "dex": dex + 2,
                "bst": 650,
                "categories": ["mega"],
                "evolutions": [],
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
        "include/constants",
        "data/maps/TestMap",
        "data/maps/NewBarkTown_Lab",
        "data/scripts",
    ]
    for relative in paths:
        (source / relative).mkdir(parents=True, exist_ok=True)

    (source / "docs/data/romhack-docs.json").write_text(
        json.dumps({"species": _species_rows()}), encoding="utf-8"
    )
    (source / "src/data/pokemon/species_info/gen_1_families.h").write_text(
        "[SPECIES_SYNTH_ULTRA] = {\n    .isUltraBeast = TRUE,\n},\n", encoding="utf-8"
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
    (source / "src/data/items.h").write_text(
        "[ITEM_NONE] = { .pocket = POCKET_ITEMS },\n"
        "[ITEM_SYNTH_ALPHA] = { .pocket = POCKET_ITEMS },\n"
        "[ITEM_SYNTH_BETA] = { .pocket = POCKET_MEDICINE },\n"
        "[ITEM_POKE_BALL] = { .pocket = POCKET_POKE_BALLS },\n"
        "[ITEM_SYNTH_KEY] = { .pocket = POCKET_KEY_ITEMS, .importance = TRUE },\n",
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
