"""Tests for ItemTimingService, ItemTimer, classify_item, and RESPAWN_TIMES.

Covers COMP-01: item timing with spawn prediction using verified Q3 constants.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from openarena_perception.perception.sound_parser import GameEvent
from openarena_perception.tactics.item_timing import (
    RESPAWN_TIMES,
    ItemTimer,
    ItemTimingService,
    classify_item,
)


# ---------------------------------------------------------------------------
# RESPAWN_TIMES constant tests
# ---------------------------------------------------------------------------

class TestRespawnTimes:
    """Respawn constants must match verified Q3 source values."""

    def test_weapon_respawn(self):
        assert RESPAWN_TIMES["weapon"] == 5.0

    def test_ammo_respawn(self):
        assert RESPAWN_TIMES["ammo"] == 40.0

    def test_health_respawn(self):
        assert RESPAWN_TIMES["health"] == 35.0

    def test_armor_respawn(self):
        assert RESPAWN_TIMES["armor"] == 25.0

    def test_mega_respawn(self):
        """MegaHealth is 35s (not 120s like powerups)."""
        assert RESPAWN_TIMES["mega"] == 35.0

    def test_powerup_respawn(self):
        assert RESPAWN_TIMES["powerup"] == 120.0

    def test_holdable_respawn(self):
        assert RESPAWN_TIMES["holdable"] == 60.0


# ---------------------------------------------------------------------------
# classify_item tests
# ---------------------------------------------------------------------------

class TestClassifyItem:
    """classify_item maps Q3 item names to respawn categories."""

    def test_mega_health(self):
        assert classify_item("item_health_mega") == "mega"

    def test_weapon(self):
        assert classify_item("weapon_rocketlauncher") == "weapon"
        assert classify_item("weapon_railgun") == "weapon"
        assert classify_item("weapon_lightning") == "weapon"

    def test_armor_body(self):
        assert classify_item("item_armor_body") == "armor"

    def test_armor_combat(self):
        assert classify_item("item_armor_combat") == "armor"

    def test_armor_shard(self):
        assert classify_item("item_armor_shard") == "armor"

    def test_health(self):
        assert classify_item("item_health") == "health"
        assert classify_item("item_health_large") == "health"
        assert classify_item("item_health_small") == "health"

    def test_ammo(self):
        assert classify_item("ammo_rockets") == "ammo"
        assert classify_item("ammo_shells") == "ammo"

    def test_powerups(self):
        assert classify_item("item_quad") == "powerup"
        assert classify_item("item_haste") == "powerup"
        assert classify_item("item_enviro") == "powerup"
        assert classify_item("item_flight") == "powerup"
        assert classify_item("item_invis") == "powerup"
        assert classify_item("item_regen") == "powerup"

    def test_unknown_defaults_to_health(self):
        assert classify_item("item_unknown_thing") == "health"


# ---------------------------------------------------------------------------
# ItemTimer tests
# ---------------------------------------------------------------------------

class TestItemTimer:
    """ItemTimer tracks a single item's respawn cycle."""

    def test_predicted_spawn_time(self):
        timer = ItemTimer(
            item_name="item_health_mega",
            category="mega",
            respawn_seconds=35.0,
            last_pickup_time=1000.0,
        )
        assert timer.predicted_spawn_time == 1035.0

    def test_predicted_spawn_time_never_picked(self):
        timer = ItemTimer(
            item_name="weapon_rocketlauncher",
            category="weapon",
            respawn_seconds=5.0,
        )
        assert timer.predicted_spawn_time == 0.0  # never seen -> assume available

    @patch("openarena_perception.tactics.item_timing.time")
    def test_seconds_until_spawn(self, mock_time):
        mock_time.time.return_value = 1020.0
        timer = ItemTimer(
            item_name="item_health_mega",
            category="mega",
            respawn_seconds=35.0,
            last_pickup_time=1000.0,
        )
        assert timer.seconds_until_spawn == 15.0  # 1035 - 1020

    @patch("openarena_perception.tactics.item_timing.time")
    def test_seconds_until_spawn_already_available(self, mock_time):
        mock_time.time.return_value = 1040.0
        timer = ItemTimer(
            item_name="item_health_mega",
            category="mega",
            respawn_seconds=35.0,
            last_pickup_time=1000.0,
        )
        assert timer.seconds_until_spawn == 0.0

    @patch("openarena_perception.tactics.item_timing.time")
    def test_is_available_true(self, mock_time):
        mock_time.time.return_value = 1040.0
        timer = ItemTimer(
            item_name="item_health_mega",
            category="mega",
            respawn_seconds=35.0,
            last_pickup_time=1000.0,
        )
        assert timer.is_available is True

    @patch("openarena_perception.tactics.item_timing.time")
    def test_is_available_false(self, mock_time):
        mock_time.time.return_value = 1010.0
        timer = ItemTimer(
            item_name="item_health_mega",
            category="mega",
            respawn_seconds=35.0,
            last_pickup_time=1000.0,
        )
        assert timer.is_available is False


# ---------------------------------------------------------------------------
# ItemTimingService tests
# ---------------------------------------------------------------------------

class TestItemTimingService:
    """ItemTimingService manages timers for all tracked items."""

    def test_record_pickup_creates_timer(self):
        svc = ItemTimingService()
        svc.record_pickup("weapon_rocketlauncher", pickup_time=1000.0)
        timer = svc.get_timer("weapon_rocketlauncher")
        assert timer is not None
        assert timer.item_name == "weapon_rocketlauncher"
        assert timer.category == "weapon"
        assert timer.respawn_seconds == 5.0
        assert timer.last_pickup_time == 1000.0
        assert timer.pickup_count == 1

    def test_record_pickup_updates_existing(self):
        svc = ItemTimingService()
        svc.record_pickup("weapon_rocketlauncher", pickup_time=1000.0)
        svc.record_pickup("weapon_rocketlauncher", pickup_time=1005.0)
        timer = svc.get_timer("weapon_rocketlauncher")
        assert timer is not None
        assert timer.last_pickup_time == 1005.0
        assert timer.pickup_count == 2

    def test_process_events_item_events(self):
        svc = ItemTimingService()
        events = [
            GameEvent(
                timestamp_game="20:40",
                timestamp_real=1000.0,
                event_type="Item",
                client_id=2,
                data="20:40 Item: 2 weapon_rocketlauncher",
                item_name="weapon_rocketlauncher",
            ),
            GameEvent(
                timestamp_game="20:42",
                timestamp_real=1002.0,
                event_type="Item",
                client_id=2,
                data="20:42 Item: 2 item_armor_body",
                item_name="item_armor_body",
            ),
        ]
        svc.process_events(events)
        assert svc.get_timer("weapon_rocketlauncher") is not None
        assert svc.get_timer("item_armor_body") is not None

    def test_process_events_initgame_resets(self):
        svc = ItemTimingService()
        svc.record_pickup("weapon_rocketlauncher", pickup_time=1000.0)
        assert svc.get_timer("weapon_rocketlauncher") is not None

        events = [
            GameEvent(
                timestamp_game="0:00",
                timestamp_real=2000.0,
                event_type="InitGame",
                client_id=-1,
                data="0:00 InitGame: ...",
            ),
        ]
        svc.process_events(events)
        assert svc.get_timer("weapon_rocketlauncher") is None

    def test_reset_all_clears_timers(self):
        svc = ItemTimingService()
        svc.record_pickup("weapon_rocketlauncher", pickup_time=1000.0)
        svc.record_pickup("item_armor_body", pickup_time=1000.0)
        svc.reset_all()
        assert svc.get_timer("weapon_rocketlauncher") is None
        assert svc.get_timer("item_armor_body") is None

    def test_get_timer_returns_none_for_unknown(self):
        svc = ItemTimingService()
        assert svc.get_timer("nonexistent_item") is None

    @patch("openarena_perception.tactics.item_timing.time")
    def test_get_upcoming_sorted(self, mock_time):
        mock_time.time.return_value = 1010.0
        svc = ItemTimingService()
        # Weapon spawns at 1005 (already available), armor at 1025, mega at 1035
        svc.record_pickup("weapon_rocketlauncher", pickup_time=1000.0)
        svc.record_pickup("item_armor_body", pickup_time=1000.0)
        svc.record_pickup("item_health_mega", pickup_time=1000.0)

        upcoming = svc.get_upcoming(limit=5)
        # weapon is already available (seconds_until=0) -> excluded
        # armor: 1025 - 1010 = 15s
        # mega: 1035 - 1010 = 25s
        assert len(upcoming) == 2
        assert upcoming[0].item_name == "item_armor_body"
        assert upcoming[1].item_name == "item_health_mega"

    def test_record_pickup_default_time(self):
        """record_pickup without explicit time uses time.time()."""
        svc = ItemTimingService()
        with patch("openarena_perception.tactics.item_timing.time") as mock_time:
            mock_time.time.return_value = 5000.0
            svc.record_pickup("weapon_railgun")
        timer = svc.get_timer("weapon_railgun")
        assert timer is not None
        assert timer.last_pickup_time == 5000.0
