"""Small immutable domain models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constants import OFFICIAL_CHEAT_ITEM_ID_RANGES, STORY_ITEM_DENYLIST


@dataclass(frozen=True)
class Species:
    constant: str
    name: str
    dex: int
    bst: int
    categories: frozenset[str]
    evolutions: tuple[str, ...]
    types: tuple[str, ...] = ()
    attack: int = 0
    special_attack: int = 0

    @property
    def is_special(self) -> bool:
        return bool(self.categories & {"legendary", "mythical", "paradox"})


@dataclass(frozen=True)
class Item:
    constant: str
    item_id: int
    pocket: str
    important: bool

    @property
    def is_randomizable(self) -> bool:
        return (
            self.constant != "ITEM_NONE"
            and not self.constant.startswith("ITEM_HM_")
            and self.constant not in STORY_ITEM_DENYLIST
            and self.pocket != "POCKET_KEY_ITEMS"
            and not self.important
            and any(start <= self.item_id <= end for start, end in OFFICIAL_CHEAT_ITEM_ID_RANGES)
        )


@dataclass(frozen=True)
class Move:
    constant: str
    power: int
    accuracy: int
    pp: int
    move_type: str
    category: str

    @property
    def is_offensive(self) -> bool:
        return self.category in {
            "DAMAGE_CATEGORY_PHYSICAL",
            "DAMAGE_CATEGORY_SPECIAL",
        }


@dataclass(frozen=True)
class PlannedWrite:
    path: Path
    original: bytes | None
    updated: bytes
