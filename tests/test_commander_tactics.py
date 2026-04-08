"""Unit tests for Commander (TACT-02).

Tests priority-based goal selection, item priority rankings,
and decision timing.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from openarena_perception.tactics.commander import Commander, ItemMemory


# Standard test items
_ITEMS = [
    ("item_health_large", 100.0, 100.0, 0.0),
    ("weapon_rocketlauncher", 200.0, 200.0, 0.0),
    ("item_armor_body", 300.0, 300.0, 0.0),
    ("item_health_mega", 400.0, 400.0, 0.0),
]


class TestCommanderDecide:
    """Commander.decide() returns correct target by priority."""

    def test_critical_health_returns_health_item(self):
        """hp < 30 -> returns health item (SURVIVE priority)."""
        cmd = Commander(_ITEMS)
        result = cmd.decide(health=20, armor=0, ammo=30, pos_x=0, pos_y=0, enemies_visible=0)
        assert result is not None
        assert "health" in result.classname

    def test_healthy_returns_weapon_or_armor(self):
        """Full health -> returns weapon or armor (ARM/ARMOR priority)."""
        cmd = Commander(_ITEMS)
        result = cmd.decide(health=100, armor=0, ammo=30, pos_x=0, pos_y=0, enemies_visible=0)
        assert result is not None
        # Should pick a weapon or armor (most valuable items when healthy)
        assert "weapon" in result.classname or "armor" in result.classname or "mega" in result.classname

    def test_empty_items_returns_none(self):
        """No items -> returns None (explore)."""
        cmd = Commander([])
        result = cmd.decide(health=100, armor=0, ammo=30, pos_x=0, pos_y=0, enemies_visible=0)
        assert result is None

    def test_low_health_returns_health_or_armor(self):
        """hp < 60 -> returns health or armor (HEAL priority)."""
        cmd = Commander(_ITEMS)
        result = cmd.decide(health=40, armor=0, ammo=30, pos_x=0, pos_y=0, enemies_visible=0)
        assert result is not None
        assert "health" in result.classname or "armor" in result.classname


class TestItemPriority:
    """Commander._item_priority ranks items correctly."""

    def test_mega_highest_priority(self):
        assert Commander._item_priority("item_health_mega") == 5.0

    def test_rocket_launcher_high(self):
        assert Commander._item_priority("weapon_rocketlauncher") == 4.0

    def test_lightning_gun_high(self):
        assert Commander._item_priority("weapon_lightning") == 3.5

    def test_body_armor_medium(self):
        assert Commander._item_priority("armor_body") == 3.0

    def test_generic_weapon_medium(self):
        assert Commander._item_priority("weapon_shotgun") == 2.5

    def test_health_large(self):
        assert Commander._item_priority("health_large") == 2.0

    def test_health_small_low(self):
        assert Commander._item_priority("health_small") == 0.7

    def test_ammo_baseline(self):
        assert Commander._item_priority("ammo_rockets") == 1.0

    def test_unknown_item(self):
        assert Commander._item_priority("item_unknown") == 0.5


class TestShouldDecide:
    """Commander.should_decide respects decision_interval."""

    def test_should_decide_after_interval(self):
        cmd = Commander(_ITEMS)
        cmd._last_decision_time = 0.0  # long ago
        assert cmd.should_decide() is True

    def test_should_not_decide_before_interval(self):
        cmd = Commander(_ITEMS)
        import time
        cmd._last_decision_time = time.time()  # just now
        assert cmd.should_decide() is False
