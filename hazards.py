"""
Environmental hazard factory functions.

Hazards use entity_type="hazard" and are created as Entity objects.
The hazard_type field distinguishes between crate, fire, etc.

Custom tile codepoints (injected at startup in nigrl.py):
    0xE000  crate
    0xE001  fire
    0xE002  table
"""

from entity import Entity

CRATE_CODEPOINT = 0xE000
FIRE_CODEPOINT  = 0xE001
TABLE_CODEPOINT = 0xE002


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


def create_deep_fryer(x: int, y: int) -> Entity:
    """A deep-fryer cooking station. Blocks movement; player bumps to open fry menu.
    Applies upgraded greasy prefix: 3 charges, 3 greasy stacks per charge."""
    return Entity(
        x=x, y=y,
        char="&",
        color=(200, 140, 60),
        name="Deep Fryer",
        entity_type="hazard",
        hazard_type="deep_fryer",
        blocks_movement=True,
    )


def create_table(x: int, y: int) -> Entity:
    """A table that blocks movement but not line of sight. Cannot be destroyed."""
    return Entity(
        x=x, y=y,
        char=chr(TABLE_CODEPOINT),
        color=(255, 255, 255),
        name="Table",
        entity_type="hazard",
        hazard_type="table",
        blocks_movement=True,
        blocks_fov=False,
    )


def create_toxic_creep(x: int, y: int, duration: int = 10, tox_per_turn: int = 5) -> Entity:
    """A toxic creep puddle. Passable; applies toxicity each tick to entities standing on it.
    Expires after `duration` turns."""
    return Entity(
        x=x, y=y,
        char="~",
        color=(150, 200, 50),
        name="Toxic Creep",
        entity_type="hazard",
        hazard_type="toxic_creep",
        blocks_movement=False,
        hazard_duration=duration,
        hazard_tox_per_turn=tox_per_turn,
    )


def create_acid_pool(x: int, y: int, duration: int = 15, damage_per_turn: int = 3) -> Entity:
    """An acid puddle. Passable; deals damage each tick to entities standing on it.
    Expires after `duration` turns."""
    return Entity(
        x=x, y=y,
        char="~",
        color=(100, 255, 50),
        name="Acid Pool",
        entity_type="hazard",
        hazard_type="acid_pool",
        blocks_movement=False,
        hazard_duration=duration,
        hazard_damage_per_turn=damage_per_turn,
    )


def create_rad_bomb_crystal(x: int, y: int, damage: int = 20) -> Entity:
    """A rad bomb crystal. Blocks movement. Detonates after 3 turns in a 5x5 square."""
    crystal = Entity(
        x=x, y=y,
        char="*",
        color=(120, 220, 80),
        name="Rad Crystal",
        entity_type="hazard",
        hazard_type="rad_bomb_crystal",
        blocks_movement=True,
        hazard_duration=3,
    )
    crystal.rad_bomb_damage = damage
    return crystal


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
