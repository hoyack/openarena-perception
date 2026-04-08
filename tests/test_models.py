"""Tests for data contracts (FOUND-08)."""
import dataclasses
import time

import pytest

from openarena_perception.models import BrainState, SituationalAwareness


def make_awareness(**overrides) -> SituationalAwareness:
    """Build a SituationalAwareness with sensible defaults."""
    defaults = dict(
        tick=1, timestamp=time.time(),
        pos=(100.0, 200.0, 0.0), yaw=90.0, current_area=5,
        health=100, armor=50, ammo=30, weapon="machinegun",
        is_alive=True,
        disposition="healthy", armament="armed", orientation="oriented",
        under_attack=False, attacker_direction=0, seconds_since_damage=10.0,
        enemies_visible=0, nearest_enemy_distance=None,
        wall_ahead=False, wall_score=0.0, open_direction=0, in_water=False,
        tracked_objects=0, locked_target=False,
        anomaly_count=0, lockable_anomaly=False,
        room_surveyed=True, room_type="corridor", room_exits=2,
        has_path=True, path_length=5, is_stuck=False, is_recovering=False,
        nav_target="item_health_large",
        has_frame=True,
    )
    defaults.update(overrides)
    return SituationalAwareness(**defaults)


class TestSituationalAwareness:
    def test_frozen_rejects_mutation(self):
        sa = make_awareness()
        with pytest.raises(dataclasses.FrozenInstanceError):
            sa.health = 50

    def test_has_slots(self):
        assert hasattr(SituationalAwareness, "__slots__")

    def test_all_fields_present(self):
        fields = {f.name for f in dataclasses.fields(SituationalAwareness)}
        expected = {
            "tick", "timestamp", "pos", "yaw", "current_area",
            "health", "armor", "ammo", "weapon", "is_alive",
            "disposition", "armament", "orientation",
            "under_attack", "attacker_direction", "seconds_since_damage",
            "enemies_visible", "nearest_enemy_distance",
            "wall_ahead", "wall_score", "open_direction", "in_water",
            "tracked_objects", "locked_target",
            "anomaly_count", "lockable_anomaly",
            "room_surveyed", "room_type", "room_exits",
            "has_path", "path_length", "is_stuck", "is_recovering",
            "nav_target", "has_frame",
        }
        assert fields == expected

    def test_construction_with_defaults(self):
        sa = make_awareness(health=75, under_attack=True)
        assert sa.health == 75
        assert sa.under_attack is True
        assert sa.is_alive is True

    def test_is_dataclass(self):
        assert dataclasses.is_dataclass(SituationalAwareness)


class TestBrainState:
    def test_all_states(self):
        expected = {"dead", "combat", "stuck", "picking_up_item",
                    "traversing_door", "surveying", "navigating", "exploring"}
        actual = {s.value for s in BrainState}
        assert actual == expected

    def test_state_count(self):
        assert len(BrainState) == 8


class TestBackwardCompatibility:
    def test_import_from_strategic_brain(self):
        from openarena_perception.strategic_brain import (
            BrainState as SB_BrainState,
            SituationalAwareness as SB_SA,
        )
        assert SB_BrainState is BrainState
        assert SB_SA is SituationalAwareness
