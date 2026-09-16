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


class MovesPass(RandomizationPass, Protocol):
    """Reserved contract for move-data randomization."""


class AbilitiesPass(RandomizationPass, Protocol):
    """Reserved contract for regular and hidden ability randomization."""


class InnatesPass(RandomizationPass, Protocol):
    """Reserved contract for innate-ability randomization."""


class TrainersPass(RandomizationPass, Protocol):
    """Reserved contract for trainer and party randomization."""
