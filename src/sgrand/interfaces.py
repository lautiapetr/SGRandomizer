"""Extension contracts for current and future randomization passes."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Protocol

from .models import PlannedWrite


class RandomizationPass(Protocol):
    """A pass plans deterministic writes without mutating the checkout."""

    name: str

    def plan(self, source: Path, rng: random.Random) -> tuple[list[PlannedWrite], list[object]]:
        """Return proposed writes and serializable audit records."""
        ...


class LevelUpLearnsetsPass(RandomizationPass, Protocol):
    """Contract for level-up move assignment without changing effects."""


class MoveCompatibilityPass(RandomizationPass, Protocol):
    """Contract for TM and tutor compatibility decisions."""


class MovePropertiesPass(RandomizationPass, Protocol):
    """Contract for basic move fields, independent of battle effects."""


class AbilitiesPass(RandomizationPass, Protocol):
    """Contract for regular and hidden ability randomization."""


class InnatesPass(RandomizationPass, Protocol):
    """Contract for independently seeded innate-ability randomization."""


class TrainersPass(RandomizationPass, Protocol):
    """Contract for competitive-syntax trainer-party randomization."""
