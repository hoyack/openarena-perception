"""Tests for EpisodicMemory DB-backed match event storage."""
from __future__ import annotations

import pytest

from openarena_perception.memory.episodic import EpisodicMemory
from openarena_perception.memory.storage import create_database


@pytest.fixture()
def db_engine(tmp_path):
    """Create a fresh SQLite database in a temp directory."""
    return create_database(str(tmp_path / "test.db"))


@pytest.fixture()
def episodic(db_engine):
    """Return an EpisodicMemory backed by a temp DB."""
    return EpisodicMemory(db_engine)


class TestRecordAndRetrieve:
    def test_record_and_retrieve_event(self, episodic):
        episodic.record_event(
            match_id="m1",
            event_type="death",
            map_name="dm4",
            position=(100.0, 200.0, 300.0),
            details={"killer": "bot_a"},
        )
        deaths = episodic.get_deaths("dm4")
        assert len(deaths) == 1
        d = deaths[0]
        assert d["match_id"] == "m1"
        assert d["event_type"] == "death"
        assert d["map_name"] == "dm4"
        assert d["position_x"] == 100.0
        assert d["position_y"] == 200.0
        assert d["position_z"] == 300.0

    def test_get_match_events_ordered(self, episodic):
        for i in range(5):
            episodic.record_event(
                match_id="m1",
                event_type="kill" if i % 2 == 0 else "death",
                map_name="dm4",
            )
        events = episodic.get_match_events("m1")
        assert len(events) == 5
        # Should be ordered by timestamp ascending
        for i in range(len(events) - 1):
            assert events[i]["timestamp"] <= events[i + 1]["timestamp"]

    def test_get_events_by_type(self, episodic):
        episodic.record_event("m1", "kill", "dm4")
        episodic.record_event("m1", "death", "dm4")
        episodic.record_event("m1", "kill", "dm4")

        kills = episodic.get_events_by_type("kill")
        assert len(kills) == 2
        assert all(e["event_type"] == "kill" for e in kills)

    def test_get_deaths_limit(self, episodic):
        for i in range(10):
            episodic.record_event("m1", "death", "dm4", position=(float(i), 0.0, 0.0))
        deaths = episodic.get_deaths("dm4", limit=3)
        assert len(deaths) == 3

    def test_get_death_heatmap(self, episodic):
        # Record several deaths at similar positions (same cluster after rounding)
        for _ in range(5):
            episodic.record_event("m1", "death", "dm4", position=(150.0, 250.0, 50.0))
        heatmap = episodic.get_death_heatmap("dm4")
        assert len(heatmap) >= 1
        # Each entry is (x, y, z, count)
        assert len(heatmap[0]) == 4
        x, y, z, count = heatmap[0]
        assert count == 5

    def test_empty_queries(self, episodic):
        assert episodic.get_deaths("nonexistent") == []
        assert episodic.get_match_events("nope") == []
        assert episodic.get_events_by_type("kill") == []
        assert episodic.get_death_heatmap("nothing") == []

    def test_multiple_maps(self, episodic):
        episodic.record_event("m1", "death", "dm4")
        episodic.record_event("m1", "death", "dm6")
        episodic.record_event("m1", "death", "dm4")

        dm4_deaths = episodic.get_deaths("dm4")
        dm6_deaths = episodic.get_deaths("dm6")
        assert len(dm4_deaths) == 2
        assert len(dm6_deaths) == 1
