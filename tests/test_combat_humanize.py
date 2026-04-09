"""Tests for CombatMover humanization: strafe noise + path deviation (HUMN-03).

TDD RED: These tests define expected behavior for movement variability
in CombatMover. They should FAIL before implementation.
"""
from __future__ import annotations

import pytest

from openarena_perception.combat.combat_movement import CombatMover
from openarena_perception.combat.humanize import HumanizationConfig


class TestCombatMoverNoConfig:
    """Without humanize_config, behavior is identical to original."""

    def test_no_config_returns_dict(self):
        m = CombatMover()
        r = m.get_movement(400, "rocket launcher", skill=0.8)
        assert isinstance(r, dict)
        assert "forward" in r
        assert "strafe_left" in r

    def test_no_config_corner_overshoot_zero(self):
        m = CombatMover()
        assert m.corner_overshoot_px == 0.0


class TestCombatMoverWithConfig:
    """With humanize_config, movement has noise injected."""

    def test_config_stored(self):
        cfg = HumanizationConfig.from_skill_level(3)
        m = CombatMover(humanize_config=cfg)
        assert m._humanize_config is cfg

    def test_get_movement_returns_dict(self):
        cfg = HumanizationConfig.from_skill_level(1)
        m = CombatMover(humanize_config=cfg)
        r = m.get_movement(400, "rocket launcher", skill=0.8)
        assert isinstance(r, dict)
        assert "forward" in r

    def test_corner_overshoot_from_config(self):
        cfg = HumanizationConfig.from_skill_level(1)
        m = CombatMover(humanize_config=cfg)
        assert m.corner_overshoot_px == 40.0

    def test_corner_overshoot_expert(self):
        cfg = HumanizationConfig.from_skill_level(5)
        m = CombatMover(humanize_config=cfg)
        assert m.corner_overshoot_px == 6.0

    def test_strafe_interval_clamped(self):
        """Strafe interval must stay in [0.15, 1.5] even with high noise."""
        cfg = HumanizationConfig.from_skill_level(1)  # noise=0.3
        m = CombatMover(humanize_config=cfg)
        # Force many strafe switches and verify interval stays clamped
        import time
        m._last_switch = 0.0  # Force switch on next call
        for _ in range(50):
            m._last_switch = 0.0  # Force switch
            m.get_movement(400, "rocket launcher", skill=0.8)
            assert 0.15 <= m._switch_interval <= 1.5, (
                f"Interval {m._switch_interval} out of bounds"
            )

    def test_path_deviation_can_invert_strafe(self):
        """With high path_deviation_chance, some strafes should be inverted."""
        cfg = HumanizationConfig.from_skill_level(1)  # chance=0.30
        m = CombatMover(humanize_config=cfg)
        # Run many iterations and check that strafe direction varies
        directions = set()
        for _ in range(100):
            m._last_switch = 0.0  # Force switch
            m._strafe_dir = 1  # Always start right
            r = m.get_movement(400, "rocket launcher", skill=0.8)
            if r["strafe_left"]:
                directions.add("left")
            if r["strafe_right"]:
                directions.add("right")
        # With 30% deviation chance over 100 iterations, both should appear
        assert len(directions) == 2, f"Expected both directions, got {directions}"
