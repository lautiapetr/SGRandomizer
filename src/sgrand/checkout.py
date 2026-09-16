"""Selection validation and opt-in download of the supported SoulGold checkout."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .errors import RandomizerError
from .process import CommandSpec, run_command
from .source import validate_source

SOULGOLD_REPOSITORY = "https://github.com/Eemeliri/soulgold.git"
SOULGOLD_TAG = "v.1.1.4"


def checkout_clone_command(destination: Path) -> CommandSpec:
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise RandomizerError(f"Download destination must be empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    return CommandSpec(
        (
            "git",
            "clone",
            "--branch",
            SOULGOLD_TAG,
            "--depth",
            "1",
            "--single-branch",
            SOULGOLD_REPOSITORY,
            ".",
        ),
        cwd=destination,
    )


def download_checkout(
    destination: Path,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    on_line: Callable[[str], None] = lambda _line: None,
    on_progress: Callable[[int], None] = lambda _value: None,
) -> None:
    command = checkout_clone_command(destination)
    run_command(command, cancelled=cancelled, on_line=on_line, on_progress=on_progress)
    validate_source(destination)
