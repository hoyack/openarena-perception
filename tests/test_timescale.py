"""Tests for TimescaleConfig and rate_limited decorator (COMP-03)."""

import time
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest

from openarena_perception.tactics.timescale import (
    DEFAULT_TIMESCALE,
    TimescaleConfig,
    rate_limited,
)


class TestTimescaleConfigDefaults:
    """TimescaleConfig has correct default Hz values."""

    def test_perception_hz(self):
        ts = TimescaleConfig()
        assert ts.perception_hz == 15.0

    def test_reflex_hz(self):
        ts = TimescaleConfig()
        assert ts.reflex_hz == 15.0

    def test_combat_hz(self):
        ts = TimescaleConfig()
        assert ts.combat_hz == 15.0

    def test_tactics_hz(self):
        ts = TimescaleConfig()
        assert ts.tactics_hz == 15.0

    def test_commander_hz(self):
        ts = TimescaleConfig()
        assert ts.commander_hz == 0.33

    def test_strategy_hz(self):
        ts = TimescaleConfig()
        assert ts.strategy_hz == 0.2

    def test_sound_poll_hz(self):
        ts = TimescaleConfig()
        assert ts.sound_poll_hz == 2.0

    def test_item_timing_hz(self):
        ts = TimescaleConfig()
        assert ts.item_timing_hz == 1.0


class TestTimescaleConfigFrozen:
    """TimescaleConfig is frozen (immutable)."""

    def test_frozen_raises_on_assignment(self):
        ts = TimescaleConfig()
        with pytest.raises(FrozenInstanceError):
            ts.perception_hz = 30.0


class TestTimescaleConfigIntervalSeconds:
    """interval_seconds returns 1/hz for a given layer."""

    def test_commander_interval(self):
        ts = TimescaleConfig()
        interval = ts.interval_seconds("commander")
        assert abs(interval - (1.0 / 0.33)) < 0.01

    def test_perception_interval(self):
        ts = TimescaleConfig()
        interval = ts.interval_seconds("perception")
        assert abs(interval - (1.0 / 15.0)) < 0.001

    def test_unknown_layer_raises(self):
        ts = TimescaleConfig()
        with pytest.raises(ValueError, match="Unknown layer"):
            ts.interval_seconds("nonexistent")


class TestTimescaleConfigTicksPerCall:
    """ticks_per_call returns base_hz / layer_hz, rounded."""

    def test_sound_poll_at_15hz(self):
        ts = TimescaleConfig()
        # 15 / 2 = 7.5 -> rounds to 8
        ticks = ts.ticks_per_call("sound_poll", base_hz=15.0)
        assert ticks == 8

    def test_item_timing_at_15hz(self):
        ts = TimescaleConfig()
        # 15 / 1 = 15
        ticks = ts.ticks_per_call("item_timing", base_hz=15.0)
        assert ticks == 15

    def test_perception_at_15hz(self):
        ts = TimescaleConfig()
        # 15 / 15 = 1
        ticks = ts.ticks_per_call("perception", base_hz=15.0)
        assert ticks == 1

    def test_unknown_layer_raises(self):
        ts = TimescaleConfig()
        with pytest.raises(ValueError, match="Unknown layer"):
            ts.ticks_per_call("nonexistent")


class TestRateLimited:
    """rate_limited decorator enforces minimum time between calls."""

    def test_skips_calls_within_interval(self):
        @rate_limited(min_interval_seconds=1.0)
        def my_func():
            return "called"

        with patch("openarena_perception.tactics.timescale.time") as mock_time:
            mock_time.time.return_value = 100.0
            result1 = my_func()
            assert result1 == "called"

            mock_time.time.return_value = 100.5  # 0.5s later, within 1.0s
            result2 = my_func()
            assert result2 is None

    def test_allows_calls_after_interval(self):
        @rate_limited(min_interval_seconds=1.0)
        def my_func():
            return "called"

        with patch("openarena_perception.tactics.timescale.time") as mock_time:
            mock_time.time.return_value = 100.0
            result1 = my_func()
            assert result1 == "called"

            mock_time.time.return_value = 101.1  # 1.1s later, past 1.0s
            result2 = my_func()
            assert result2 == "called"

    def test_returns_none_when_skipped(self):
        @rate_limited(min_interval_seconds=2.0)
        def my_func():
            return 42

        with patch("openarena_perception.tactics.timescale.time") as mock_time:
            mock_time.time.return_value = 0.0
            my_func()  # first call succeeds

            mock_time.time.return_value = 1.0  # within 2.0s
            result = my_func()
            assert result is None  # not stale value, explicit None


class TestDefaultTimescale:
    """DEFAULT_TIMESCALE is a module-level TimescaleConfig instance."""

    def test_is_timescale_config(self):
        assert isinstance(DEFAULT_TIMESCALE, TimescaleConfig)

    def test_has_default_values(self):
        assert DEFAULT_TIMESCALE.perception_hz == 15.0
        assert DEFAULT_TIMESCALE.commander_hz == 0.33
        assert DEFAULT_TIMESCALE.strategy_hz == 0.2
