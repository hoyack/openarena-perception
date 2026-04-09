"""Tests for ConsoleLogParser, IncrementalLogReader, and GameEvent.

Covers PERC-08: sound/event awareness via Q3 game log parsing.
"""
from __future__ import annotations

import os
import time

import pytest

from openarena_perception.perception.sound_parser import (
    ConsoleLogParser,
    GameEvent,
    IncrementalLogReader,
)


# ---------------------------------------------------------------------------
# GameEvent tests
# ---------------------------------------------------------------------------

class TestGameEvent:
    """GameEvent is a frozen dataclass with required fields."""

    def test_frozen_dataclass(self):
        evt = GameEvent(
            timestamp_game="20:40",
            timestamp_real=1000.0,
            event_type="Kill",
            client_id=1,
            data="Player1 killed Player2 by MOD_ROCKET",
        )
        assert evt.timestamp_game == "20:40"
        assert evt.event_type == "Kill"
        with pytest.raises(AttributeError):
            evt.event_type = "Item"  # type: ignore[misc]

    def test_default_extra_fields(self):
        evt = GameEvent(
            timestamp_game="20:40",
            timestamp_real=1000.0,
            event_type="Item",
            client_id=2,
            data="weapon_rocketlauncher",
        )
        assert evt.killer_id == -1
        assert evt.victim_id == -1
        assert evt.means_of_death == ""
        assert evt.item_name == ""


# ---------------------------------------------------------------------------
# IncrementalLogReader tests
# ---------------------------------------------------------------------------

class TestIncrementalLogReader:
    """IncrementalLogReader reads only new lines from a growing file."""

    def test_reads_new_lines_only(self, tmp_path):
        log_file = tmp_path / "games.log"
        log_file.write_text("20:40 Item: 2 weapon_rocketlauncher\n")

        reader = IncrementalLogReader(str(log_file))
        lines = reader.read_new_lines()
        assert len(lines) == 1
        assert "weapon_rocketlauncher" in lines[0]

        # No new data -> empty
        lines2 = reader.read_new_lines()
        assert lines2 == []

        # Append new line -> only the new line
        with open(str(log_file), "a") as f:
            f.write("20:42 Item: 2 item_armor_body\n")

        lines3 = reader.read_new_lines()
        assert len(lines3) == 1
        assert "item_armor_body" in lines3[0]

    def test_returns_empty_when_no_new_data(self, tmp_path):
        log_file = tmp_path / "games.log"
        log_file.write_text("20:40 Item: 2 weapon_rocketlauncher\n")

        reader = IncrementalLogReader(str(log_file))
        reader.read_new_lines()  # consume
        assert reader.read_new_lines() == []

    def test_detects_file_rotation(self, tmp_path):
        log_file = tmp_path / "games.log"
        log_file.write_text("line1\nline2\nline3\n")

        reader = IncrementalLogReader(str(log_file))
        lines = reader.read_new_lines()
        assert len(lines) == 3

        # Simulate rotation: write shorter content (new file)
        log_file.write_text("new_line1\n")

        lines2 = reader.read_new_lines()
        assert len(lines2) == 1
        assert "new_line1" in lines2[0]

    def test_missing_file_returns_empty(self, tmp_path):
        reader = IncrementalLogReader(str(tmp_path / "nonexistent.log"))
        assert reader.read_new_lines() == []

    def test_reset_rereads_from_start(self, tmp_path):
        log_file = tmp_path / "games.log"
        log_file.write_text("line1\nline2\n")

        reader = IncrementalLogReader(str(log_file))
        reader.read_new_lines()  # consume all
        reader.reset()
        lines = reader.read_new_lines()
        assert len(lines) == 2

    def test_max_bytes_cap(self, tmp_path):
        """T-07-02 mitigation: cap max bytes read per poll."""
        log_file = tmp_path / "games.log"
        # Write more than 64KB
        log_file.write_text("x" * 100_000 + "\n")

        reader = IncrementalLogReader(str(log_file))
        lines = reader.read_new_lines()
        # Should not crash, data may be truncated
        total_chars = sum(len(l) for l in lines)
        assert total_chars <= 65536 + 1024  # allow small overhead


# ---------------------------------------------------------------------------
# ConsoleLogParser tests
# ---------------------------------------------------------------------------

class TestConsoleLogParser:
    """ConsoleLogParser parses Q3 game log events."""

    def test_parse_kill_event(self, tmp_path):
        log_file = tmp_path / "games.log"
        log_file.write_text(
            "21:07 Kill: 1 2 6: Player1 killed Player2 by MOD_ROCKET\n"
        )
        parser = ConsoleLogParser(str(log_file))
        events = parser.poll()
        assert len(events) == 1
        evt = events[0]
        assert evt.event_type == "Kill"
        assert evt.timestamp_game == "21:07"
        assert evt.killer_id == 1
        assert evt.victim_id == 2
        assert evt.means_of_death == "MOD_ROCKET"

    def test_parse_item_event(self, tmp_path):
        log_file = tmp_path / "games.log"
        log_file.write_text("20:40 Item: 2 weapon_rocketlauncher\n")
        parser = ConsoleLogParser(str(log_file))
        events = parser.poll()
        assert len(events) == 1
        evt = events[0]
        assert evt.event_type == "Item"
        assert evt.client_id == 2
        assert evt.item_name == "weapon_rocketlauncher"

    def test_parse_initgame_event(self, tmp_path):
        log_file = tmp_path / "games.log"
        log_file.write_text(
            r"0:00 InitGame: \g_gametype\0\mapname\q3dm17\sv_maxclients\8" + "\n"
        )
        parser = ConsoleLogParser(str(log_file))
        events = parser.poll()
        assert len(events) == 1
        evt = events[0]
        assert evt.event_type == "InitGame"
        assert evt.client_id == -1

    def test_skips_malformed_lines(self, tmp_path):
        log_file = tmp_path / "games.log"
        log_file.write_text(
            "not a real line\n"
            "\n"
            "garbage data here\n"
            "20:40 Item: 2 weapon_rocketlauncher\n"
            "partial Kill: broken\n"
        )
        parser = ConsoleLogParser(str(log_file))
        events = parser.poll()
        assert len(events) == 1
        assert events[0].event_type == "Item"

    def test_poll_returns_list_of_game_events(self, tmp_path):
        log_file = tmp_path / "games.log"
        log_file.write_text(
            "20:40 Item: 2 weapon_rocketlauncher\n"
            "21:07 Kill: 1 2 6: Player1 killed Player2 by MOD_ROCKET\n"
            "21:15 Item: 3 item_health_mega\n"
        )
        parser = ConsoleLogParser(str(log_file))
        events = parser.poll()
        assert len(events) == 3
        assert all(isinstance(e, GameEvent) for e in events)

    def test_poll_incremental(self, tmp_path):
        log_file = tmp_path / "games.log"
        log_file.write_text("20:40 Item: 2 weapon_rocketlauncher\n")
        parser = ConsoleLogParser(str(log_file))

        events1 = parser.poll()
        assert len(events1) == 1

        # Second poll with no new data
        events2 = parser.poll()
        assert len(events2) == 0

        # Append more
        with open(str(log_file), "a") as f:
            f.write("21:07 Kill: 1 2 6: Player1 killed Player2 by MOD_ROCKET\n")

        events3 = parser.poll()
        assert len(events3) == 1
        assert events3[0].event_type == "Kill"

    def test_reset_delegates_to_reader(self, tmp_path):
        log_file = tmp_path / "games.log"
        log_file.write_text("20:40 Item: 2 weapon_rocketlauncher\n")
        parser = ConsoleLogParser(str(log_file))
        parser.poll()
        parser.reset()
        events = parser.poll()
        assert len(events) == 1

    def test_world_kill_event(self, tmp_path):
        log_file = tmp_path / "games.log"
        log_file.write_text(
            "20:54 Kill: 1022 2 22: <world> killed Isgalamido by MOD_TRIGGER_HURT\n"
        )
        parser = ConsoleLogParser(str(log_file))
        events = parser.poll()
        assert len(events) == 1
        evt = events[0]
        assert evt.killer_id == 1022
        assert evt.victim_id == 2
        assert evt.means_of_death == "MOD_TRIGGER_HURT"
