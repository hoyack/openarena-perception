"""Shared test fixtures for openarena-perception."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from openarena_perception.models import SituationalAwareness


@pytest.fixture
def mock_navigator():
    """A mocked Navigator with sensible defaults."""
    nav = MagicMock()
    nav.graph = MagicMock()
    nav.has_path = True
    nav._path = [1, 2, 3]
    nav.pos = (100.0, 200.0, 0.0)
    nav.yaw = 90.0
    nav.current_area = 5
    nav.is_stuck = False
    nav.is_recovering = False
    return nav


@pytest.fixture
def mock_bridge():
    """A mocked GameBridge."""
    return MagicMock()


@pytest.fixture
def mock_commander():
    """A mocked Commander that does not trigger decisions."""
    cmd = MagicMock()
    cmd.should_decide.return_value = False
    return cmd


@pytest.fixture
def mock_perception():
    """A mocked Perception module."""
    return MagicMock()


@pytest.fixture
def mock_damage_tracker():
    """A mocked DamageTracker."""
    return MagicMock()


@pytest.fixture
def mock_ctrl():
    """A mocked VirtualController."""
    return MagicMock()


@pytest.fixture
def make_awareness():
    """Factory fixture for SituationalAwareness with sensible defaults."""
    def _make(**overrides) -> SituationalAwareness:
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
    return _make
