"""
Environmental hazard factory functions.

Hazards use entity_type="hazard" and are created as Entity objects.
The hazard_type field distinguishes between crate, fire, etc.

Custom tile codepoints (injected at startup in nigrl.py):
    0xE000  crate
    0xE001  fire
"""

from entity import Entity

CRATE_CODEPOINT = 0xE000
FIRE_CODEPOINT  = 0xE001


def create_crate(x: int, y: int) -> Entity:
    """A wooden crate that blocks movement. Destroyed on player bump; drops a consumable."""
    return Entity(
        x=x, y=y,
        char=chr(CRATE_CODEPOINT),
        color=(255, 255, 255),
        name="Crate",
        entity_type="hazard",
        hazard_type="crate",
        blocks_movement=True,
    )


def create_fire(x: int, y: int) -> Entity:
    """A fire tile. Passable; ignites entities that stand on it."""
    return Entity(
        x=x, y=y,
        char=chr(FIRE_CODEPOINT),
        color=(255, 255, 255),
        name="Fire",
        entity_type="hazard",
        hazard_type="fire",
        blocks_movement=False,
    )
