"""Tests for item name pluralization."""

import pytest
from items import _pluralize, build_inventory_display_name


class TestPluralize:
    """Test the _pluralize function with English rules."""

    def test_regular_s(self):
        assert _pluralize("Chicken") == "Chickens"
        assert _pluralize("Muffin") == "Muffins"
        assert _pluralize("Corn Dog") == "Corn Dogs"

    def test_already_ends_in_s(self):
        assert _pluralize("Hot Cheetos") == "Hot Cheetos"
        assert _pluralize("Leftovers") == "Leftovers"
        assert _pluralize("Light Rounds") == "Light Rounds"
        assert _pluralize("Heinz Baked Beans") == "Heinz Baked Beans"
        assert _pluralize("Asbestos") == "Asbestos"

    def test_ch_sh_x_z_endings(self):
        assert _pluralize("BIC Torch") == "BIC Torches"
        assert _pluralize("XL BIC Torch") == "XL BIC Torches"
        assert _pluralize("Monkey Wrench") == "Monkey Wrenches"
        assert _pluralize("Metal Lunchbox") == "Metal Lunchboxes"

    def test_consonant_y(self):
        assert _pluralize("Fry Daddy") == "Fry Daddies"

    def test_vowel_y_unchanged(self):
        assert _pluralize("Rad Away") == "Rad Aways"

    def test_fe_ending(self):
        assert _pluralize("Knife") == "Knives"

    def test_parenthetical(self):
        assert _pluralize("Pack of Cones (20)") == "Pack of Cones (20)"

    def test_explicit_override(self):
        assert _pluralize("Knife", "knife") == "Knives"


class TestBuildInventoryDisplayName:
    """Test build_inventory_display_name with pluralization."""

    def test_joint_with_strain_singular(self):
        result = build_inventory_display_name("joint", "Jungle Boyz", 1)
        assert result == "1 Joint Jungle Boyz"

    def test_joint_with_strain_plural(self):
        result = build_inventory_display_name("joint", "Jungle Boyz", 3)
        assert result == "3 Joints Jungle Boyz"

    def test_joint_dosidos_plural(self):
        result = build_inventory_display_name("joint", "Dosidos", 3)
        assert result == "3 Joints Dosidos"

    def test_joint_og_kush_plural(self):
        result = build_inventory_display_name("joint", "OG Kush", 2)
        assert result == "2 Joints OG Kush"

    def test_weed_nug_plural(self):
        result = build_inventory_display_name("weed_nug", "OG Kush", 3)
        assert result == "3g Nugs OG Kush"

    def test_weed_nug_singular(self):
        result = build_inventory_display_name("weed_nug", "OG Kush", 1)
        assert result == "1g Nug OG Kush"

    def test_kush(self):
        result = build_inventory_display_name("kush", "OG Kush", 3)
        assert result == "3g OG Kush"

    def test_regular_item_plural(self):
        result = build_inventory_display_name("chicken", None, 3)
        assert result == "3 Chickens"

    def test_regular_item_singular(self):
        result = build_inventory_display_name("chicken", None, 1)
        assert result == "1 Chicken"

    def test_no_strain_no_mangling(self):
        result = build_inventory_display_name("blue_meth_joint", None, 2)
        assert result == "2 Blue Meth Joints"
