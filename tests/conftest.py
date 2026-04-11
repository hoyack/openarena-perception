"""Shared test fixtures for openarena-perception."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from openarena_perception.models import SituationalAwareness


# ---- Phase 13 room perception fixtures ----

@pytest.fixture
def rect_point_cloud() -> np.ndarray:
    """4-wall axis-aligned rectangle at (0,0)-(512,384) with 10% outliers.
    Returns Nx2 float array of (x, y) samples. Deterministic seed.
    """
    rng = np.random.default_rng(42)
    pts = []
    # Bottom wall y=0, x in [0, 512]
    pts.append(np.column_stack([rng.uniform(0, 512, 80), rng.normal(0, 1.5, 80)]))
    # Top wall y=384
    pts.append(np.column_stack([rng.uniform(0, 512, 80), 384 + rng.normal(0, 1.5, 80)]))
    # Left wall x=0
    pts.append(np.column_stack([rng.normal(0, 1.5, 60), rng.uniform(0, 384, 60)]))
    # Right wall x=512
    pts.append(np.column_stack([512 + rng.normal(0, 1.5, 60), rng.uniform(0, 384, 60)]))
    cloud = np.vstack(pts)
    # 10% outliers scattered in bounding box
    n_out = int(0.1 * len(cloud))
    outliers = np.column_stack(
        [rng.uniform(-50, 562, n_out), rng.uniform(-50, 434, n_out)]
    )
    return np.vstack([cloud, outliers]).astype(np.float64)


@pytest.fixture
def u_shape_point_cloud() -> np.ndarray:
    """3-wall U (left, bottom, right) — should produce PartialRoom, no Room."""
    rng = np.random.default_rng(123)
    pts = []
    pts.append(np.column_stack([rng.uniform(0, 300, 60), rng.normal(0, 1.0, 60)]))
    pts.append(np.column_stack([rng.normal(0, 1.0, 50), rng.uniform(0, 200, 50)]))
    pts.append(np.column_stack([300 + rng.normal(0, 1.0, 50), rng.uniform(0, 200, 50)]))
    return np.vstack(pts).astype(np.float64)


@pytest.fixture
def noisy_point_cloud() -> np.ndarray:
    """Pure noise — line fitter must return 0 walls."""
    rng = np.random.default_rng(7)
    return rng.uniform(-500, 500, size=(400, 2)).astype(np.float64)


@pytest.fixture
def synthetic_frame():
    """A simple 480x640 BGR numpy array for perception tests."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


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


@pytest.fixture
def strategic_brain(mock_bridge, mock_navigator, mock_commander,
                    mock_perception, mock_damage_tracker, mock_ctrl):
    """A StrategicBrain with all dependencies mocked."""
    from openarena_perception.strategic_brain import StrategicBrain
    brain = StrategicBrain(
        bridge=mock_bridge,
        nav=mock_navigator,
        commander=mock_commander,
        perception=mock_perception,
        damage_tracker=mock_damage_tracker,
        ctrl=mock_ctrl,
        obj_tracker=MagicMock(),
        anomaly_tracker=MagicMock(),
        surveyor=MagicMock(),
        spatial=MagicMock(),
        map_name="test",
    )
    return brain
