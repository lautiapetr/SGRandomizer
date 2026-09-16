"""Stable, named random streams."""

from __future__ import annotations

import hashlib
import random


def stable_seed(seed_text: str) -> int:
    try:
        return int(seed_text, 0)
    except ValueError:
        digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
        return int.from_bytes(digest[:16], "big")


class RngStreams:
    """Derive streams by name so one subsystem cannot perturb another."""

    def __init__(self, seed_text: str) -> None:
        self.seed_text = seed_text
        self.numeric_seed = stable_seed(seed_text)

    def stream(self, subsystem: str) -> random.Random:
        material = f"sgrand-v1\0{self.numeric_seed}\0{subsystem}".encode()
        derived = int.from_bytes(hashlib.sha256(material).digest()[:16], "big")
        return random.Random(derived)
