"""Phase 13 test stubs for LearnedMap raycast capture, decimation, schema v3."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
import pytest

from openarena_perception.navigation.learned_map import LearnedMap


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


@pytest.mark.skip(reason="Wave 1 — Plan 13-02 RP-01")
def test_raycast_capture_appends():
    """RP-01: one tick with wall_ahead=True appends exactly one RaycastHit."""
    raise NotImplementedError


@pytest.mark.skip(reason="Wave 1 — Plan 13-02 RP-02")
def test_raycast_decimation():
    """RP-02: 6000 synthetic hits -> final size == 5000 after decimation."""
    raise NotImplementedError


@pytest.mark.skip(reason="Wave 3 — Plan 13-05 RP-10")
def test_schema_v3_roundtrip():
    """RP-10: save v3 -> reload -> all typed collections preserved byte-stable."""
    raise NotImplementedError
