"""Spoiler-safe reports and named build publication."""

from __future__ import annotations

import copy
import json
import re
import shutil
from pathlib import Path
from typing import Any

from .errors import RandomizerError

SPOILER_FIELDS = (
    "starters",
    "species_mapping_used",
    "wild_changes",
    "static_and_gift_changes",
    "item_changes",
)


def redact_spoilers(report: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy with species, item and starter outcomes omitted."""
    redacted = copy.deepcopy(report)
    for key in SPOILER_FIELDS:
        if key in redacted:
            redacted[key] = []
    redacted["spoilers_included"] = False
    return redacted


def output_slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return (normalized or "unnamed")[:64]


def output_stem(profile: str, seed: str) -> str:
    return f"SGRand-{output_slug(profile)}-{output_slug(seed)}"


def format_readable_report(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        f"Semilla: {report['seed_input']} ({report['seed_numeric']})",
        f"Archivos modificados: {counts['files_changed']}",
        f"Encuentros salvajes: {counts['wild_slots_changed']}",
        f"Estáticos y regalos: {counts['static_and_gift_commands_changed']}",
        f"Objetos: {counts['map_items_changed'] + counts['scripted_items_changed']}",
        f"Movimientos de nivel: {counts['level_up_slots_changed']}",
        f"Compatibilidad TM/tutor: {counts['compatibility_species_changed']}",
        f"Habilidades: {counts['normal_abilities_species_changed']}",
        f"Innatas: {counts['innates_species_changed']}",
        f"Equipos de entrenadores: {counts['trainers_changed']}",
    ]
    if report.get("spoilers_included", True):
        lines.append("\nStarters:")
        lines.extend(
            f"  {entry['slot']}: {entry['from']} → {entry['to']}"
            for entry in report.get("starters", [])
        )
    else:
        lines.append("\nModo sin spoilers: resultados específicos omitidos.")
    return "\n".join(lines)


def write_technical_report(
    report: dict[str, Any], output_directory: Path, profile: str, seed: str
) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    target = output_directory / f"{output_stem(profile, seed)}-report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def publish_rom(
    checkout: Path,
    output_directory: Path,
    profile: str,
    seed: str,
    *,
    overwrite: bool = False,
) -> Path:
    source = checkout / "Soulgold.gba"
    if not source.is_file():
        raise RandomizerError(f"Build completed without producing {source}")
    output_directory.mkdir(parents=True, exist_ok=True)
    target = output_directory / f"{output_stem(profile, seed)}.gba"
    if target.exists() and not overwrite:
        raise RandomizerError(f"Output already exists: {target}")
    shutil.copy2(source, target)
    return target
