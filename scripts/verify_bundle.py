"""Reject game, checkout and generated build artifacts from tracked or packaged files."""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Iterable
from pathlib import Path, PurePath, PurePosixPath

FORBIDDEN_SUFFIXES = frozenset({".elf", ".gba", ".map", ".nds", ".rom", ".sav"})
FORBIDDEN_TOP_LEVEL = frozenset({".work", "AppDir", "build", "dist", "temp"})
SOULGOLD_MARKERS = (
    ("src", "data", "trainers.party"),
    ("src", "data", "wild_encounters.json"),
    ("src", "data", "pokemon", "species_info"),
)


def _contains_sequence(parts: tuple[str, ...], marker: tuple[str, ...]) -> bool:
    width = len(marker)
    return any(parts[index : index + width] == marker for index in range(len(parts) - width + 1))


def find_forbidden(paths: Iterable[PurePath], *, tracked: bool) -> list[str]:
    """Return portable path strings that violate repository/package boundaries."""
    violations: list[str] = []
    for path in paths:
        parts = tuple(path.parts)
        suffix = path.suffix.lower()
        forbidden_root = tracked and bool(parts) and parts[0] in FORBIDDEN_TOP_LEVEL
        checkout_content = any(_contains_sequence(parts, marker) for marker in SOULGOLD_MARKERS)
        if suffix in FORBIDDEN_SUFFIXES or forbidden_root or checkout_content:
            violations.append(path.as_posix())
    return sorted(violations)


def tracked_paths(repository: Path) -> list[PurePosixPath]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    return [PurePosixPath(raw.decode()) for raw in result.stdout.split(b"\0") if raw]


def packaged_paths(root: Path) -> list[PurePath]:
    if not root.is_dir():
        raise ValueError(f"Package directory does not exist: {root}")
    return [path.relative_to(root) for path in root.rglob("*") if path.is_file()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, help="assembled package directory")
    parser.add_argument(
        "--tracked",
        action="store_true",
        help="inspect paths tracked by Git instead of an assembled package",
    )
    arguments = parser.parse_args(argv)
    repository = Path(__file__).resolve().parents[1]
    if arguments.tracked == (arguments.root is not None):
        parser.error("choose exactly one of --tracked or a package directory")
    try:
        paths = tracked_paths(repository) if arguments.tracked else packaged_paths(arguments.root)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        parser.error(str(exc))
    violations = find_forbidden(paths, tracked=arguments.tracked)
    if violations:
        print("Forbidden game or build artifacts detected:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print(f"Package boundary verified ({len(paths)} files checked).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
