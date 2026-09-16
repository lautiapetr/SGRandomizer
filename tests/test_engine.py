from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sgrand.engine import Randomizer, RunMode
from sgrand.models import PlannedWrite
from sgrand.rng import RngStreams
from sgrand.source import load_species
from sgrand.species import build_species_mapping, graph_data
from sgrand.transaction import FileTransaction


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_preview_is_deterministic_and_read_only(synthetic_source: Path) -> None:
    before = tree_digest(synthetic_source)
    first = Randomizer().run(synthetic_source, "same-seed")
    second = Randomizer().run(synthetic_source, "same-seed")
    assert first == second
    assert first["applied"] is False
    assert before == tree_digest(synthetic_source)
    assert not (synthetic_source / "soulgold-randomizer-manifest.json").exists()


def test_different_seeds_change_output(synthetic_source: Path) -> None:
    first = Randomizer().run(synthetic_source, "seed-a")
    second = Randomizer().run(synthetic_source, "seed-b")
    assert first["starters"] != second["starters"]
    assert first["species_mapping_used"] != second["species_mapping_used"]


def test_mapping_preserves_evolution_edges_and_specials(synthetic_source: Path) -> None:
    species = load_species(synthetic_source)
    mapping = build_species_mapping(species, RngStreams("mapping").stream("wild-species"))
    children, _ = graph_data(species)
    for parent, source_children in children.items():
        for child in source_children:
            if mapping[parent] == parent and mapping[child] == child:
                continue
            assert mapping[child] in children[mapping[parent]]
    assert mapping["SPECIES_SYNTH_LEGEND"] == "SPECIES_SYNTH_LEGEND"
    assert mapping["SPECIES_SYNTH_ULTRA"] == "SPECIES_SYNTH_ULTRA"


def test_named_rng_streams_are_independent() -> None:
    streams = RngStreams("independent")
    expected_stream = streams.stream("starters")
    expected = [expected_stream.random() for _ in range(3)]
    noisy = streams.stream("wild-species")
    for _ in range(1000):
        noisy.random()
    actual_stream = streams.stream("starters")
    actual = [actual_stream.random() for _ in range(3)]
    assert actual == expected


def test_variable_gift_replacement_is_scoped_to_its_assignment(
    synthetic_source: Path,
) -> None:
    script = synthetic_source / "data/maps/TestMap/scripts.pory"
    script.write_text(
        script.read_text(encoding="utf-8")
        + "script Prize {\n"
        + "  setvar VAR_PRIZE, SPECIES_SYNTH_A0\n"
        + "  givemon VAR_PRIZE\n"
        + "  compare VAR_OTHER, SPECIES_SYNTH_A0\n"
        + "}\n",
        encoding="utf-8",
    )
    plan = Randomizer().plan(synthetic_source, "variable-gift")
    planned = next(write for write in plan.writes if write.path == script).updated.decode()
    assert "setvar VAR_PRIZE, SPECIES_SYNTH_A0" not in planned
    assert "compare VAR_OTHER, SPECIES_SYNTH_A0" in planned


def test_apply_writes_manifest_and_preserves_protected_gift(synthetic_source: Path) -> None:
    report = Randomizer().run(synthetic_source, "apply-seed", RunMode.APPLY)
    manifest_path = synthetic_source / "soulgold-randomizer-manifest.json"
    assert report["applied"] is True
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == report
    lab = (synthetic_source / "data/maps/NewBarkTown_Lab/scripts.pory").read_text()
    assert "giveitem ITEM_POKE_BALL, 10" in lab
    assert tree_digest(synthetic_source)


def test_transaction_rolls_back_every_committed_file(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("old first", encoding="utf-8")
    second.write_text("old second", encoding="utf-8")
    calls = 0

    def fail_once(source: os.PathLike[str] | str, target: os.PathLike[str] | str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected commit failure")
        os.replace(source, target)

    transaction = FileTransaction(replace=fail_once)
    writes = [
        PlannedWrite(first, b"old first", b"new first"),
        PlannedWrite(second, b"old second", b"new second"),
    ]
    with pytest.raises(Exception, match="rolled back"):
        transaction.apply(writes)
    assert first.read_text(encoding="utf-8") == "old first"
    assert second.read_text(encoding="utf-8") == "old second"


def test_apply_preflight_rejects_concurrent_change(synthetic_source: Path) -> None:
    randomizer = Randomizer()
    plan = randomizer.plan(synthetic_source, "race", RunMode.APPLY)
    target = plan.writes[0].path
    target.write_bytes(target.read_bytes() + b"\nexternal change\n")
    with pytest.raises(Exception, match="changed while planning"):
        randomizer.transaction.apply(plan.writes)


def test_cli_preview(synthetic_source: Path) -> None:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sgrand",
            "preview",
            "--source",
            str(synthetic_source),
            "--seed",
            "cli-seed",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert result.returncode == 0, result.stderr
    assert "PREVIEW" in result.stdout
    assert "No files were written" in result.stdout
