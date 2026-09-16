from __future__ import annotations

import json
from pathlib import Path

import pytest

from sgrand.errors import RandomizerError
from sgrand.reporting import (
    format_readable_report,
    output_stem,
    publish_rom,
    redact_spoilers,
    write_technical_report,
)


def sample_report() -> dict[str, object]:
    return {
        "seed_input": "seed / unsafe",
        "seed_numeric": 3,
        "spoilers_included": True,
        "starters": [{"slot": 0, "from": "A", "to": "B"}],
        "species_mapping_used": [{"from": "A", "to": "B"}],
        "wild_changes": [1],
        "static_and_gift_changes": [2],
        "item_changes": [3],
        "counts": {
            "files_changed": 1,
            "wild_slots_changed": 2,
            "static_and_gift_commands_changed": 3,
            "map_items_changed": 4,
            "scripted_items_changed": 5,
            "level_up_slots_changed": 6,
            "compatibility_species_changed": 7,
            "normal_abilities_species_changed": 8,
            "innates_species_changed": 9,
            "trainers_changed": 10,
        },
    }


def test_spoiler_redaction_does_not_mutate_input() -> None:
    original = sample_report()
    redacted = redact_spoilers(original)  # type: ignore[arg-type]
    assert redacted["spoilers_included"] is False
    assert redacted["starters"] == []
    assert original["starters"] != []
    assert "Modo sin spoilers" in format_readable_report(redacted)


def test_named_output_and_report(tmp_path: Path) -> None:
    assert output_stem("Balanced", "seed / unsafe") == "SGRand-Balanced-seed-unsafe"
    report = sample_report()
    report_path = write_technical_report(  # type: ignore[arg-type]
        report, tmp_path / "out", "Balanced", "seed / unsafe"
    )
    assert json.loads(report_path.read_text(encoding="utf-8")) == report

    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "Soulgold.gba").write_bytes(b"synthetic-rom-output")
    target = publish_rom(checkout, tmp_path / "out", "Balanced", "seed / unsafe")
    assert target.name == "SGRand-Balanced-seed-unsafe.gba"
    assert target.read_bytes() == b"synthetic-rom-output"
    with pytest.raises(RandomizerError, match="already exists"):
        publish_rom(checkout, tmp_path / "out", "Balanced", "seed / unsafe")
