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
    before = (source / "src/data/wild_encounters.json").read_bytes()
    report = Randomizer().run(source, "integration-seed")
    assert report["counts"]["wild_slots_changed"] > 0
    assert report["counts"]["files_changed"] > 0
    assert (source / "src/data/wild_encounters.json").read_bytes() == before
