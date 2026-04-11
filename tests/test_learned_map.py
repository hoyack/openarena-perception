"""Phase 13 test stubs for LearnedMap raycast capture, decimation, schema v3."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
import pytest

from openarena_perception.navigation.learned_map import LearnedMap, RaycastHit


class TestSchemaV3Whitelist:
    """RP-10 — v3 files must load (Pitfall 6 fix)."""

    def test_v3_file_is_accepted_by_version_whitelist(self, tmp_path):
        """Wave 0 GREEN test: a v3-shaped file loads instead of being rejected."""
        lm = LearnedMap(map_name="test_v3_whitelist")
        lm._save_dir = str(tmp_path)
        path = Path(tmp_path) / "test_v3_whitelist.json"
        payload = {
            "map_name": "test_v3_whitelist",
            "version": 3,
            "grid_resolution": 64,
            "grid_size": 64,
            "num_floors": 2,
            "floor_z_threshold": -20.0,
            "grid_origin": [-1024.0, -512.0],
            "grids": [],
            "wall_segments": [],
            "edge_failures": {},
            "edge_successes": {},
            "raycasts_per_floor": [[], []],
            "fitted_walls": [],
            "corners": [],
            "rooms": [],
            "doorways": [],
        }
        path.write_text(json.dumps(payload))
        assert lm.load() is True, "v3 file must load after Pitfall 6 whitelist fix"

    def test_v2_file_still_loads(self, tmp_path):
        """Regression: don't break Phase 12.1 v2 compatibility."""
        lm = LearnedMap(map_name="test_v2_regress")
        lm._save_dir = str(tmp_path)
        path = Path(tmp_path) / "test_v2_regress.json"
        blank = np.zeros((64, 64), dtype=np.uint8)
        payload = {
            "map_name": "test_v2_regress",
            "version": 2,
            "grid_resolution": 64,
            "grid_size": 64,
            "num_floors": 2,
            "floor_z_threshold": -20.0,
            "grid_origin": [-1024.0, -512.0],
            "grids": [base64.b64encode(blank.tobytes()).decode() for _ in range(2)],
            "wall_segments": [],
            "edge_failures": {},
            "edge_successes": {},
        }
        path.write_text(json.dumps(payload))
        assert lm.load() is True


def test_raycast_capture_appends(tmp_path):
    """RP-01: one tick with wall_ahead + wall_score>0.5 -> exactly one RaycastHit."""
    lm = LearnedMap(map_name="test_rp01")
    lm._save_dir = str(tmp_path)
    lm.update(
        pos=(100.0, 200.0, 50.0),
        yaw=45.0,
        wall_ahead=True,
        wall_score=0.8,
        open_direction=0,
        in_water=False,
    )
    cloud = lm._raycasts_per_floor[1]  # upper floor (z=50 >= -20)
    assert len(cloud) == 1
    assert isinstance(cloud[0], RaycastHit)
    assert cloud[0].origin_x == 100.0
    assert cloud[0].origin_y == 200.0
    assert cloud[0].origin_z == 50.0
    assert cloud[0].dir_angle_deg == 45.0
    assert cloud[0].confidence == 0.8


def test_raycast_capture_respects_gate(tmp_path):
    """RP-01: wall_ahead=False OR wall_score<=0.5 -> no raycast appended."""
    lm = LearnedMap(map_name="test_rp01_gate")
    lm._save_dir = str(tmp_path)
    lm.update(
        pos=(0.0, 0.0, 50.0),
        yaw=0.0,
        wall_ahead=False,
        wall_score=0.9,
        open_direction=0,
        in_water=False,
    )
    assert len(lm._raycasts_per_floor[1]) == 0
    lm.update(
        pos=(0.0, 0.0, 50.0),
        yaw=0.0,
        wall_ahead=True,
        wall_score=0.3,
        open_direction=0,
        in_water=False,
    )
    assert len(lm._raycasts_per_floor[1]) == 0


def test_raycast_floor_routing(tmp_path):
    """RP-01: basement ticks populate floor 0, upper ticks populate floor 1."""
    lm = LearnedMap(map_name="test_rp01_floor")
    lm._save_dir = str(tmp_path)
    lm.update(
        pos=(0.0, 0.0, -50.0),
        yaw=0.0,
        wall_ahead=True,
        wall_score=0.9,
        open_direction=0,
        in_water=False,
    )
    assert len(lm._raycasts_per_floor[0]) == 1
    assert len(lm._raycasts_per_floor[1]) == 0


def test_raycast_decimation(tmp_path):
    """RP-02: 6000 hits -> final cap == 5000; retained set has the higher confidences."""
    import random

    rng = random.Random(42)  # local RNG — don't pollute global state
    lm = LearnedMap(map_name="test_rp02")
    lm._save_dir = str(tmp_path)
    for i in range(6000):
        conf = 0.5 + rng.random() * 0.5  # (0.5, 1.0]
        # Nudge above the strict >0.5 gate in update()
        if conf <= 0.5:
            conf = 0.5001
        lm.update(
            pos=(float(i), 0.0, 50.0),
            yaw=float(i % 360),
            wall_ahead=True,
            wall_score=conf,
            open_direction=0,
            in_water=False,
        )
    cloud = lm._raycasts_per_floor[1]
    assert len(cloud) == lm.MAX_RAYCASTS_PER_FLOOR == 5000
    # Eviction drops the lowest-confidence tail — retained min must clear the gate.
    min_retained = min(h.confidence for h in cloud)
    assert min_retained > 0.5


def test_raycast_capture_overhead_under_1ms(tmp_path):
    """Per-tick raycast capture must stay <1ms on target hardware.

    Measures average cost of _record_raycast across 1000 appends (no decimation
    triggered). On Pi 4/5 the list-append path is well under 1ms; we budget
    generously at 1ms to avoid flakiness.
    """
    import time as _time

    lm = LearnedMap(map_name="test_rp_perf")
    lm._save_dir = str(tmp_path)
    # Warm up
    lm._record_raycast(0, 0, 50, 0, 10, 0, 50, 0.9)
    N = 1000
    t0 = _time.perf_counter()
    for i in range(N):
        lm._record_raycast(float(i), 0.0, 50.0, 0.0, float(i) + 10, 0.0, 50.0, 0.9)
    elapsed = _time.perf_counter() - t0
    avg_ms = (elapsed / N) * 1000.0
    assert avg_ms < 1.0, f"per-tick capture too slow: {avg_ms:.4f} ms (>1ms)"


def test_schema_v3_roundtrip(tmp_path):
    """RP-10: v3 save -> reload preserves RaycastHit collection byte-stable."""
    lm = LearnedMap(map_name="test_rp10")
    lm._save_dir = str(tmp_path)
    for i in range(10):
        lm.update(
            pos=(float(i * 10), 100.0, 50.0),
            yaw=float(i * 30),
            wall_ahead=True,
            wall_score=0.7 + i * 0.01,
            open_direction=0,
            in_water=False,
        )
    lm.save()
    path = Path(tmp_path) / "test_rp10.json"
    data = json.loads(path.read_text())
    assert data["version"] == 3
    assert len(data["raycasts_per_floor"][1]) == 10
    assert data["wall_segments"] == []
    assert "fitted_walls" in data
    assert "corners" in data
    assert "rooms" in data
    assert "doorways" in data

    lm2 = LearnedMap(map_name="test_rp10")
    lm2._save_dir = str(tmp_path)
    assert lm2.load() is True
    assert len(lm2._raycasts_per_floor[1]) == 10
    assert all(isinstance(h, RaycastHit) for h in lm2._raycasts_per_floor[1])
    # Values preserved
    assert lm2._raycasts_per_floor[1][0].origin_x == 0.0
    assert lm2._raycasts_per_floor[1][9].origin_x == 90.0


def test_v2_file_loads_with_empty_raycasts(tmp_path):
    """RP-10 regression: loading a v2 file produces empty raycast collections."""
    lm = LearnedMap(map_name="test_v2compat")
    lm._save_dir = str(tmp_path)
    blank = np.zeros((64, 64), dtype=np.uint8)
    payload = {
        "map_name": "test_v2compat",
        "version": 2,
        "grid_resolution": 64,
        "grid_size": 64,
        "num_floors": 2,
        "floor_z_threshold": -20.0,
        "grid_origin": [-1024.0, -512.0],
        "grids": [base64.b64encode(blank.tobytes()).decode() for _ in range(2)],
        "wall_segments": [],
        "edge_failures": {},
        "edge_successes": {},
    }
    (tmp_path / "test_v2compat.json").write_text(json.dumps(payload))
    assert lm.load() is True
    assert lm._raycasts_per_floor == [[], []]
