"""Tests for SemanticMemory DB-backed persistent map knowledge."""
from __future__ import annotations

import pytest

from openarena_perception.memory.semantic import SemanticMemory
from openarena_perception.memory.storage import create_database


@pytest.fixture()
def db_engine(tmp_path):
    """Create a fresh SQLite database in a temp directory."""
    return create_database(str(tmp_path / "test.db"))


@pytest.fixture()
def semantic(db_engine):
    """Return a SemanticMemory backed by a temp DB."""
    return SemanticMemory(db_engine)


# ── Room survey tests ────────────────────────────────────────────


class TestSurvey:
    def test_save_and_get_survey(self, semantic):
        semantic.save_survey(
            area_id=42,
            map_name="dm4",
            position=(100.0, 200.0, 300.0),
            yaw=90.0,
            timestamp=1000.0,
            room_type="corridor",
            exits=[{"direction": "N"}],
            items=[],
            summary="A narrow hallway",
        )
        result = semantic.get_survey(42, "dm4")
        assert result is not None
        assert result["area_id"] == 42
        assert result["map_name"] == "dm4"
        assert result["position_x"] == 100.0
        assert result["room_type"] == "corridor"
        assert result["summary"] == "A narrow hallway"

    def test_survey_upsert(self, semantic):
        semantic.save_survey(
            area_id=42, map_name="dm4", position=(1.0, 2.0, 3.0),
            yaw=0.0, timestamp=100.0, room_type="room",
        )
        semantic.save_survey(
            area_id=42, map_name="dm4", position=(10.0, 20.0, 30.0),
            yaw=180.0, timestamp=200.0, room_type="arena",
        )
        result = semantic.get_survey(42, "dm4")
        assert result is not None
        assert result["position_x"] == 10.0
        assert result["room_type"] == "arena"
        assert result["timestamp"] == 200.0

    def test_get_all_surveys_by_map(self, semantic):
        semantic.save_survey(area_id=1, map_name="dm4", position=(0, 0, 0), yaw=0, timestamp=0)
        semantic.save_survey(area_id=2, map_name="dm4", position=(0, 0, 0), yaw=0, timestamp=0)
        semantic.save_survey(area_id=3, map_name="dm6", position=(0, 0, 0), yaw=0, timestamp=0)

        dm4 = semantic.get_all_surveys("dm4")
        dm6 = semantic.get_all_surveys("dm6")
        assert len(dm4) == 2
        assert len(dm6) == 1
        assert all(s["map_name"] == "dm4" for s in dm4)

    def test_get_survey_not_found(self, semantic):
        assert semantic.get_survey(9999, "dm4") is None

    def test_get_all_surveys_no_filter(self, semantic):
        semantic.save_survey(area_id=1, map_name="dm4", position=(0, 0, 0), yaw=0, timestamp=0)
        semantic.save_survey(area_id=2, map_name="dm6", position=(0, 0, 0), yaw=0, timestamp=0)
        all_surveys = semantic.get_all_surveys()
        assert len(all_surveys) == 2


# ── Learned map tests ────────────────────────────────────────────


class TestLearnedMap:
    def _make_grids(self, size=4096):
        return b"\x00" * size

    def test_save_and_get_learned_map(self, semantic):
        grids = self._make_grids(8192)
        semantic.save_learned_map(
            map_name="dm4",
            version=2,
            grid_resolution=64,
            grid_size=64,
            num_floors=2,
            floor_z_threshold=-20.0,
            grid_origin=(100.0, 200.0),
            grids_bytes=grids,
            wall_segments=[],
            edge_failures={},
            edge_successes={},
        )
        result = semantic.get_learned_map("dm4")
        assert result is not None
        assert result["map_name"] == "dm4"
        assert result["version"] == 2
        assert result["grid_resolution"] == 64
        assert result["num_floors"] == 2
        assert result["grid_origin_x"] == 100.0
        assert result["grids"] == grids

    def test_learned_map_upsert(self, semantic):
        semantic.save_learned_map(
            map_name="dm4", version=1, grid_resolution=32, grid_size=32,
            num_floors=1, floor_z_threshold=-10.0, grid_origin=(0, 0),
            grids_bytes=b"\x01" * 1024, wall_segments=[], edge_failures={},
            edge_successes={},
        )
        semantic.save_learned_map(
            map_name="dm4", version=2, grid_resolution=64, grid_size=64,
            num_floors=2, floor_z_threshold=-20.0, grid_origin=(50, 50),
            grids_bytes=b"\x02" * 2048, wall_segments=[], edge_failures={},
            edge_successes={},
        )
        result = semantic.get_learned_map("dm4")
        assert result is not None
        assert result["version"] == 2
        assert result["grid_resolution"] == 64
        assert result["grids"] == b"\x02" * 2048

    def test_learned_map_not_found(self, semantic):
        assert semantic.get_learned_map("nonexistent") is None


# ── Item location tests ──────────────────────────────────────────


class TestItems:
    def test_record_and_get_items(self, semantic):
        semantic.record_item(
            map_name="dm4",
            item_type="weapon",
            item_name="railgun",
            area_id=10,
            position=(100.0, 200.0, 50.0),
        )
        items = semantic.get_items("dm4")
        assert len(items) == 1
        assert items[0]["item_name"] == "railgun"
        assert items[0]["pickup_count"] == 1

    def test_item_pickup_count_increments(self, semantic):
        for _ in range(3):
            semantic.record_item(
                map_name="dm4", item_type="weapon", item_name="railgun",
                area_id=10, position=(100.0, 200.0, 50.0),
            )
        items = semantic.get_items("dm4")
        assert len(items) == 1
        assert items[0]["pickup_count"] == 3

    def test_get_items_filter_by_type(self, semantic):
        semantic.record_item("dm4", "weapon", "railgun", 10, (0, 0, 0))
        semantic.record_item("dm4", "health", "mega_health", 20, (1, 1, 1))
        semantic.record_item("dm4", "weapon", "rocket_launcher", 30, (2, 2, 2))

        weapons = semantic.get_items("dm4", item_type="weapon")
        health = semantic.get_items("dm4", item_type="health")
        assert len(weapons) == 2
        assert len(health) == 1
        assert all(i["item_type"] == "weapon" for i in weapons)

    def test_get_items_empty_map(self, semantic):
        assert semantic.get_items("nonexistent") == []
