#!/usr/bin/env python3
"""Unit tests for the SoulGold source-data randomizer."""

from __future__ import annotations

import importlib.util
import json
import random
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1]
SPEC = importlib.util.spec_from_file_location("soulgold_randomizer", HERE / "randomize.py")
assert SPEC and SPEC.loader
R = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = R
SPEC.loader.exec_module(R)


class RandomizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.species = R.load_species(SOURCE)
        cls.items = R.parse_items(SOURCE)

    def test_starters_are_distinct_three_stage_base_species(self) -> None:
        pool = set(R.starter_pool(self.species))
        starters = R.choose_starters(self.species, random.Random(12345))
        self.assertEqual(len(starters), 9)
        self.assertEqual(len(set(starters)), 9)
        self.assertTrue(set(starters) <= pool)
        self.assertTrue(all(270 <= self.species[constant].bst <= 360 for constant in starters))

    def test_special_species_are_never_replaced(self) -> None:
        mapping = R.build_species_mapping(self.species, random.Random(12345))
        for constant, mon in self.species.items():
            if mon.is_special or "ultra_beast" in mon.categories:
                self.assertEqual(mapping[constant], constant, constant)

    def test_follow_evolutions_uses_target_evolution_edges(self) -> None:
        children, _ = R.graph_data(self.species)
        mapping = R.build_species_mapping(self.species, random.Random(24680))
        for parent, source_children in children.items():
            for child in source_children:
                if mapping[parent] == parent and mapping[child] == child:
                    continue
                self.assertIn(
                    mapping[child],
                    children[mapping[parent]],
                    f"{parent}->{child} became {mapping[parent]}->{mapping[child]}",
                )

    def test_similar_strength_bound_across_seeds(self) -> None:
        for seed in range(10):
            mapping = R.build_species_mapping(self.species, random.Random(seed))
            for old, new in mapping.items():
                if old == new:
                    continue
                delta = abs(self.species[old].bst - self.species[new].bst)
                tolerance = max(40, round(self.species[old].bst * 0.12))
                self.assertLessEqual(delta, tolerance, f"seed={seed} {old}->{new}")

    def test_item_pool_matches_official_ranges_and_excludes_progression(self) -> None:
        pool = [item for item in self.items.values() if item.is_randomizable]
        self.assertGreater(len(pool), 400)
        for item in pool:
            self.assertNotEqual(item.pocket, "POCKET_KEY_ITEMS")
            self.assertFalse(item.important)
            self.assertFalse(item.constant.startswith("ITEM_HM_"))
            self.assertNotIn(item.constant, R.STORY_ITEM_DENYLIST)
            self.assertTrue(
                any(start <= item.item_id <= end for start, end in R.OFFICIAL_CHEAT_ITEM_ID_RANGES)
            )

    def test_preview_is_deterministic_and_does_not_write(self) -> None:
        manifest = SOURCE / "manifest-that-must-not-exist.json"
        before = (SOURCE / "src/data/wild_encounters.json").read_bytes()
        first = R.run(SOURCE, "same-seed", False, False, manifest)
        second = R.run(SOURCE, "same-seed", False, False, manifest)
        self.assertEqual(first["starters"], second["starters"])
        self.assertEqual(first["species_mapping_used"], second["species_mapping_used"])
        self.assertEqual(first["item_changes"], second["item_changes"])
        self.assertEqual(before, (SOURCE / "src/data/wild_encounters.json").read_bytes())
        self.assertFalse(manifest.exists())

    def test_different_seeds_change_outputs(self) -> None:
        first = R.run(SOURCE, "seed-a", False, False, SOURCE / "unused-a.json")
        second = R.run(SOURCE, "seed-b", False, False, SOURCE / "unused-b.json")
        self.assertNotEqual(first["starters"], second["starters"])
        self.assertNotEqual(first["species_mapping_used"], second["species_mapping_used"])
        self.assertNotEqual(first["item_changes"], second["item_changes"])

    def test_wild_legendary_slots_remain_identical(self) -> None:
        original = json.loads((SOURCE / "src/data/wild_encounters.json").read_text(encoding="utf-8"))
        mapping = R.build_species_mapping(self.species, random.Random(54321))
        transformed, _ = R.transform_wild_encounters(original, mapping, self.species)
        for group in transformed.get("wild_encounter_groups", []):
            for encounter in group.get("encounters", []):
                for key, info in encounter.items():
                    if not key.endswith("_mons") or not isinstance(info, dict):
                        continue
                    for mon in info.get("mons", []):
                        constant = mon.get("species")
                        if constant in self.species and (
                            self.species[constant].is_special
                            or "ultra_beast" in self.species[constant].categories
                        ):
                            self.assertEqual(mapping[constant], constant)

    def test_early_lab_poke_balls_remain_vanilla(self) -> None:
        manifest = R.run(SOURCE, "protect-early-balls", False, False, SOURCE / "unused.json")
        protected_file = "data/maps/NewBarkTown_Lab/scripts.pory"
        self.assertFalse(
            any(
                change["file"] == protected_file
                and change["command"] == "giveitem"
                and change["from"] == "ITEM_POKE_BALL"
                for change in manifest["item_changes"]
            )
        )
        lab_script = (SOURCE / protected_file).read_text(encoding="utf-8")
        self.assertRegex(lab_script, r"giveitem\s*\(?\s*ITEM_POKE_BALL\s*,\s*10")


if __name__ == "__main__":
    unittest.main(verbosity=2)
