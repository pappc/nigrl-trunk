"""
Environmental hazard factory functions.

Hazards use entity_type="hazard" and are created as Entity objects.
The hazard_type field distinguishes between crate, fire, etc.

Custom tile codepoints (injected at startup in nigrl.py):
    0xE000  crate
    0xE001  fire
    0xE002  table
    0xE003  web
"""

from entity import Entity

CRATE_CODEPOINT = 0xE000
FIRE_CODEPOINT  = 0xE001
TABLE_CODEPOINT = 0xE002
WEB_CODEPOINT   = 0xE003


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


def create_rad_bomb_crystal(x: int, y: int, damage: int = 20, fuse: int = 3) -> Entity:
    """A rad bomb crystal. Blocks movement. Detonates after fuse turns in a 5x5 square."""
    crystal = Entity(
        x=x, y=y,
        char="*",
        color=(120, 220, 80),
        name="Rad Crystal",
        entity_type="hazard",
        hazard_type="rad_bomb_crystal",
        blocks_movement=True,
        hazard_duration=fuse,
    )
    crystal.rad_bomb_damage = damage
    return crystal


def create_fire(x: int, y: int, duration: int = 0) -> Entity:
    """A fire tile. Passable; ignites entities that stand on it.

    Args:
        duration: If >0, fire expires after this many turns. 0 = permanent.
    """
    fire = Entity(
        x=x, y=y,
        char=chr(FIRE_CODEPOINT),
        color=(255, 255, 255),
        name="Fire",
        entity_type="hazard",
        hazard_type="fire",
        blocks_movement=False,
    )
    if duration > 0:
        fire.hazard_duration = duration
    return fire


def create_vending_machine(x: int, y: int, stock: list = None) -> Entity:
    """A vending machine hazard. Blocks movement; bump to open shop menu.

    stock: list of (item_id, strain_or_None) tuples representing items for sale.
    """
    vm = Entity(
        x=x, y=y,
        char='V',
        color=(0, 220, 220),
        name="Vending Machine",
        entity_type="hazard",
        hazard_type="vending_machine",
        blocks_movement=True,
        reveals_on_sight=True,
    )
    vm.vending_stock = stock or []
    return vm


def create_venom_pool(x: int, y: int, duration: int = 15) -> Entity:
    """A venom pool hazard. Passable; applies 1 stack of venom per tick to entities standing on it.
    Expires after `duration` turns."""
    return Entity(
        x=x, y=y,
        char="~",
        color=(80, 200, 60),
        name="Venom Pool",
        entity_type="hazard",
        hazard_type="venom_pool",
        blocks_movement=False,
        hazard_duration=duration,
    )


def create_web(x: int, y: int) -> Entity:
    """A cobweb hazard. Passable; sticks entities that walk into it.

    Entities must spend move attempts to escape (50% chance per attempt,
    auto-escape after 5 failures).  The web is destroyed once escaped.
    """
    return Entity(
        x=x, y=y,
        char=chr(WEB_CODEPOINT),
        color=(255, 255, 255),
        name="Web",
        entity_type="hazard",
        hazard_type="web",
        blocks_movement=False,
    )


def create_spider_egg(x: int, y: int) -> Entity:
    """Spider egg from Spider's Nest. Hatches into a Spider Hatchling after 2 turns
    if any enemy is within 3 tiles, otherwise sits dormant."""
    return Entity(
        x=x, y=y,
        char="o",
        color=(180, 180, 120),
        name="Spider Egg",
        entity_type="hazard",
        hazard_type="spider_egg",
        blocks_movement=False,
        hazard_duration=99,  # doesn't expire on its own; hatched by tick logic
    )
