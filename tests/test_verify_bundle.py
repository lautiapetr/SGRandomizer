from __future__ import annotations

from pathlib import PurePosixPath

from scripts.verify_bundle import find_forbidden


def test_bundle_verifier_accepts_randomizer_assets() -> None:
    paths = [
        PurePosixPath("sgrand/gui/assets/app.svg"),
        PurePosixPath("sgrand/configs/moves-v1.json"),
        PurePosixPath("SGRand.exe"),
    ]
    assert find_forbidden(paths, tracked=False) == []


def test_bundle_verifier_rejects_game_and_checkout_content() -> None:
    paths = [
        PurePosixPath("Soulgold.gba"),
        PurePosixPath("src/data/trainers.party"),
        PurePosixPath("share/save.sav"),
    ]
    assert find_forbidden(paths, tracked=False) == [
        "Soulgold.gba",
        "share/save.sav",
        "src/data/trainers.party",
    ]


def test_tracked_verifier_rejects_ignored_work_roots() -> None:
    paths = [PurePosixPath(".work/source/README.md"), PurePosixPath("temp/output/report.json")]
    assert find_forbidden(paths, tracked=True) == [
        ".work/source/README.md",
        "temp/output/report.json",
    ]
