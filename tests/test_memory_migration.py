"""Tests for JSON-to-SQLite migration of room surveys and learned maps."""
from __future__ import annotations

import base64
import json
import os

import pytest

from openarena_perception.memory.migrate import (
    migrate_all,
    migrate_learned_maps,
    migrate_room_surveys,
)
from openarena_perception.memory.semantic import SemanticMemory
from openarena_perception.memory.storage import create_database

# Path to real room surveys at project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOM_SURVEYS_DIR = os.path.join(PROJECT_ROOT, "room_surveys")


@pytest.fixture()
def db_engine(tmp_path):
    """Create a fresh SQLite database in a temp directory."""
    return create_database(str(tmp_path / "test.db"))


class TestMigrateRoomSurveys:
    def test_migrate_room_surveys(self, db_engine):
        """Import real room_surveys/ dir, verify count matches file count."""
        count = migrate_room_surveys(db_engine, ROOM_SURVEYS_DIR)
        # We know there are 64 survey files
        assert count >= 60

    def test_migrate_room_surveys_data_integrity(self, db_engine):
        """After migration, area_111 has correct position and room_type."""
        migrate_room_surveys(db_engine, ROOM_SURVEYS_DIR)
        sm = SemanticMemory(db_engine)
        survey = sm.get_survey(111)
        assert survey is not None
        assert survey["position_x"] == 659.0
        assert survey["position_y"] == 964.0
        assert survey["position_z"] == 50.0
        assert survey["room_type"] == "jail_cell"

    def test_migrate_empty_dir(self, db_engine, tmp_path):
        """Migration on empty dir returns 0."""
        empty_dir = str(tmp_path / "empty_surveys")
        os.makedirs(empty_dir)
        count = migrate_room_surveys(db_engine, empty_dir)
        assert count == 0


class TestMigrateLearnedMaps:
    def _create_fake_map(self, directory, map_name="dm4"):
        """Create a synthetic learned map JSON file."""
        grid_data = base64.b64encode(b"\x00" * 4096).decode()
        data = {
            "map_name": map_name,
            "version": 2,
            "grid_resolution": 64,
            "grid_size": 64,
            "num_floors": 2,
            "floor_z_threshold": -20.0,
            "grid_origin": [100.0, 200.0],
            "grids": [grid_data, grid_data],
            "wall_segments": [],
            "edge_failures": {},
            "edge_successes": {},
        }
        path = os.path.join(directory, f"{map_name}.json")
        with open(path, "w") as f:
            json.dump(data, f)
        return path

    def test_migrate_learned_maps(self, db_engine, tmp_path):
        maps_dir = str(tmp_path / "learned_maps")
        os.makedirs(maps_dir)
        self._create_fake_map(maps_dir, "dm4")

        count = migrate_learned_maps(db_engine, maps_dir)
        assert count == 1

        sm = SemanticMemory(db_engine)
        result = sm.get_learned_map("dm4")
        assert result is not None
        assert result["map_name"] == "dm4"
        assert result["version"] == 2
        assert result["grid_origin_x"] == 100.0
        # 2 grids of 4096 bytes each = 8192 bytes total
        assert len(result["grids"]) == 8192

    def test_migrate_learned_maps_empty_dir(self, db_engine, tmp_path):
        maps_dir = str(tmp_path / "empty_maps")
        os.makedirs(maps_dir)
        count = migrate_learned_maps(db_engine, maps_dir)
        assert count == 0


class TestMigrateAll:
    def test_migrate_all(self, db_engine, tmp_path):
        """Combined migration with real surveys and synthetic learned map."""
        maps_dir = str(tmp_path / "learned_maps")
        os.makedirs(maps_dir)
        # Create a fake learned map
        grid_data = base64.b64encode(b"\x00" * 4096).decode()
        data = {
            "map_name": "dm4",
            "version": 2,
            "grid_resolution": 64,
            "grid_size": 64,
            "num_floors": 1,
            "floor_z_threshold": -20.0,
            "grid_origin": [0.0, 0.0],
            "grids": [grid_data],
            "wall_segments": [],
            "edge_failures": {},
            "edge_successes": {},
        }
        with open(os.path.join(maps_dir, "dm4.json"), "w") as f:
            json.dump(data, f)

        result = migrate_all(db_engine, ROOM_SURVEYS_DIR, maps_dir)
        assert result["surveys"] >= 60
        assert result["maps"] == 1
