"""Floating damage/heal numbers that drift upward above entities."""

import time
from dataclasses import dataclass, field

# Duration in seconds for floating text to live
FLOAT_DURATION = 0.6
# How many tiles the text drifts upward over its lifetime
FLOAT_DISTANCE = 2


@dataclass
class FloatingText:
    """A single floating text instance."""
    x: int          # dungeon x
    y: int          # dungeon y
    text: str
    color: tuple
    birth: float = field(default_factory=time.time)
    duration: float = FLOAT_DURATION


class FloatingTextManager:
    """Manages active floating text instances."""

    def __init__(self):
        self._texts: list[FloatingText] = []

    def add(self, x: int, y: int, text: str, color: tuple):
        """Add a new floating text at dungeon coordinates."""
        self._texts.append(FloatingText(x, y, text, color))

    def get_active(self) -> list[tuple[FloatingText, float]]:
        """Return active texts with their progress (0.0 to 1.0). Prunes expired."""
        now = time.time()
        alive = []
        for ft in self._texts:
            elapsed = now - ft.birth
            if elapsed < ft.duration:
                progress = elapsed / ft.duration
                alive.append((ft, progress))
        self._texts = [ft for ft, _ in alive]
        return alive

    def has_active(self) -> bool:
        """Check if any floating texts are still alive."""
        now = time.time()
        self._texts = [ft for ft in self._texts if (now - ft.birth) < ft.duration]
        return len(self._texts) > 0

    def clear(self):
        """Remove all floating texts."""
        self._texts.clear()
