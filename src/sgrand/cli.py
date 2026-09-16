"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .constants import DEFAULT_MANIFEST
from .engine import Randomizer, RunMode
from .errors import RandomizerError


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Randomize a SoulGold v.1.1.4 source checkout")
    commands = root.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("preview", "calculate and report a seed without writing"),
        ("apply", "apply a seed transactionally and write a manifest"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--source", type=Path, required=True, help="SoulGold source checkout")
        command.add_argument("--seed", required=True, help="text or integer seed")
        command.add_argument(
            "--moves-config",
            type=Path,
            help="versioned move-randomization JSON (default: embedded moves-v1.json)",
        )
        command.add_argument(
            "--abilities-config",
            type=Path,
            help="versioned ability JSON (default: embedded abilities-v1.json)",
        )
        command.add_argument(
            "--ability-profile",
            help="ability profile name (default: configuration default, Balanced)",
        )
        command.add_argument(
            "--trainers-config",
            type=Path,
            help="versioned trainer JSON (default: embedded trainers-v1.json)",
        )
        command.add_argument(
            "--trainer-profile",
            help="trainer profile name (default: configuration default, Balanced)",
        )
        if name == "apply":
            command.add_argument(
                "--manifest", type=Path, help=f"report path (default: SOURCE/{DEFAULT_MANIFEST})"
            )
            command.add_argument(
                "--force", action="store_true", help="replace an existing manifest"
            )
    return root


def _print_report(report: dict[str, Any], mode: RunMode, manifest: Path | None) -> None:
    print(f"SoulGold randomizer {mode.value.upper()}")
    print(f"Seed: {report['seed_input']} ({report['seed_numeric']})")
    print("Starters:")
    for starter in report["starters"]:
        print(f"  {starter['slot']}: {starter['from']} -> {starter['to']}")
    counts = report["counts"]
    print(
        "Changes: "
        f"{counts['wild_slots_changed']} wild slots, "
        f"{counts['static_and_gift_commands_changed']} static/gift Pokemon, "
        f"{counts['map_items_changed'] + counts['scripted_items_changed']} items, "
        f"{counts['files_changed']} source files"
    )
    print(
        "Abilities: "
        f"{counts['normal_abilities_species_changed']} normal sets, "
        f"{counts['innates_species_changed']} innate sets "
        f"({report['ability_config']['profile']})"
    )
    print(
        "Trainers: "
        f"{counts['trainers_changed']} teams, "
        f"{counts['trainer_species_changed']} species slots "
        f"({report['trainer_config']['profile']})"
    )
    if mode is RunMode.APPLY:
        print(f"Manifest: {manifest}")
    else:
        print("No files were written. Use the apply command to write this seed.")
    move_counts = report["counts"]
    print(
        "Moves: "
        f"{move_counts['level_up_slots_changed']} level-up slots, "
        f"{move_counts['compatibility_species_changed']} compatibility sets, "
        f"{move_counts['move_properties_changed']} property records"
    )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    mode = RunMode(args.command)
    source = args.source.resolve()
    manifest = getattr(args, "manifest", None)
    manifest = (manifest or source / DEFAULT_MANIFEST).resolve() if mode is RunMode.APPLY else None
    try:
        report = Randomizer().run(
            source,
            args.seed,
            mode,
            manifest,
            bool(getattr(args, "force", False)),
            args.moves_config,
            args.abilities_config,
            args.ability_profile,
            args.trainers_config,
            args.trainer_profile,
        )
    except RandomizerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _print_report(report, mode, manifest)
    return 0
