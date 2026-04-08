"""Tests for WorkingMemory in-process ring buffer and danger zone tracking."""
from __future__ import annotations

from unittest.mock import patch

from openarena_perception.memory.working import WorkingMemory


class TestAddEvent:
    def test_add_event_appends_to_ring_buffer(self):
        wm = WorkingMemory()
        wm.add_event("kill", {"weapon": "railgun"})
        events = wm.get_recent_events()
        assert len(events) == 1
        assert events[0]["type"] == "kill"
        assert events[0]["weapon"] == "railgun"
        assert "time" in events[0]

    def test_ring_buffer_maxlen(self):
        wm = WorkingMemory()
        for i in range(101):
            wm.add_event("tick", {"i": i})
        assert len(wm.recent_events) == 100
        # Oldest event (i=0) should have been evicted
        events = wm.get_recent_events(limit=100)
        assert events[0]["i"] == 1

    def test_get_recent_events_filter_by_type(self):
        wm = WorkingMemory()
        wm.add_event("kill", {"weapon": "rocket"})
        wm.add_event("death", {"cause": "rail"})
        wm.add_event("kill", {"weapon": "lg"})
        kills = wm.get_recent_events(event_type="kill")
        assert len(kills) == 2
        assert all(e["type"] == "kill" for e in kills)

    def test_get_recent_events_limit(self):
        wm = WorkingMemory()
        for i in range(10):
            wm.add_event("tick", {"i": i})
        events = wm.get_recent_events(limit=3)
        assert len(events) == 3
        # Should be the last 3
        assert events[0]["i"] == 7


class TestReset:
    def test_reset_clears_all(self):
        wm = WorkingMemory()
        wm.kills = 5
        wm.deaths = 3
        wm.add_event("kill")
        wm.visit_area(42)
        wm.mark_danger(42)
        wm.last_death_position = (1.0, 2.0, 3.0)
        wm.last_kill_position = (4.0, 5.0, 6.0)

        wm.reset()

        assert wm.kills == 0
        assert wm.deaths == 0
        assert wm.last_death_position is None
        assert wm.last_kill_position is None
        assert len(wm.recent_events) == 0
        assert len(wm.recently_visited_areas) == 0
        assert len(wm.danger_zones) == 0


class TestVisitArea:
    def test_visit_area_tracks_recent(self):
        wm = WorkingMemory()
        for i in range(25):
            wm.visit_area(i)
        # maxlen=20, so only last 20 retained
        assert len(wm.recently_visited_areas) == 20
        assert wm.recently_visited_areas[0] == 5


class TestDangerZone:
    def test_danger_zone_mark_and_check(self):
        wm = WorkingMemory()
        wm.mark_danger(42)
        assert wm.is_dangerous(42, decay_seconds=30.0) is True

    def test_danger_zone_decay(self):
        wm = WorkingMemory()
        # Mark danger at time=1000.0
        with patch("openarena_perception.memory.working.time.time", return_value=1000.0):
            wm.mark_danger(42)

        # Check at time=1001.0 -- still dangerous (decay_seconds=30)
        with patch("openarena_perception.memory.working.time.time", return_value=1001.0):
            assert wm.is_dangerous(42, decay_seconds=30.0) is True

        # Check at time=1031.0 -- expired (31 > 30)
        with patch("openarena_perception.memory.working.time.time", return_value=1031.0):
            assert wm.is_dangerous(42, decay_seconds=30.0) is False

    def test_danger_zone_unknown_area(self):
        wm = WorkingMemory()
        assert wm.is_dangerous(999) is False


class TestInitialState:
    def test_initial_state(self):
        wm = WorkingMemory()
        assert wm.match_id == ""
        assert wm.map_name == ""
        assert wm.kills == 0
        assert wm.deaths == 0
        assert wm.last_death_position is None
        assert wm.last_kill_position is None
        assert len(wm.recent_events) == 0
        assert len(wm.recently_visited_areas) == 0
        assert len(wm.danger_zones) == 0
