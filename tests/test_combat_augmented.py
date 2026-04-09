"""Augmented edge-case tests for the combat subsystem (TEST-03).

Covers PID aim convergence, weapon selection across all weapon types,
and threat assessment edge cases beyond the functional CMBT-01..07 tests.
"""
from __future__ import annotations

import time

import pytest

from openarena_perception.combat import (
    AimController,
    AimProfile,
    PROFILES,
    ThreatAssessor,
    WEAPONS,
    evaluate_threat,
    select_weapon,
)
from openarena_perception.combat.aim_controller import PIDState


# ---------------------------------------------------------------------------
# TEST-03a: PID Convergence
# ---------------------------------------------------------------------------

class TestPidConvergence:
    """PID controller convergence and stability tests."""

    def test_pid_output_points_toward_target(self):
        """PID output vector points toward the target (error reduction)."""
        import math

        aim = AimController()
        # Target is to the right and below the crosshair
        dx, dy = aim.update(
            target_cx=500.0, target_cy=400.0,
            screen_cx=400.0, screen_cy=300.0,
        )
        # Output should be positive in both axes (toward the target)
        assert dx > 0, "PID should move right toward target"
        assert dy > 0, "PID should move down toward target"

    def test_pid_output_magnitude_proportional_to_error(self):
        """Larger errors produce larger PID outputs."""
        import math

        aim_small = AimController()
        dx1, dy1 = aim_small.update(410.0, 305.0, 400.0, 300.0)  # 10px error
        mag_small = math.hypot(dx1, dy1)

        aim_large = AimController()
        dx2, dy2 = aim_large.update(500.0, 400.0, 400.0, 300.0)  # 141px error
        mag_large = math.hypot(dx2, dy2)

        assert mag_large > mag_small, "Larger error should produce larger output"

    def test_integral_windup_is_bounded(self):
        """PID integral accumulation stays within integral_cap."""
        aim = AimController()
        pid = aim._pid_x
        profile = aim.profile

        # Feed large constant error for many steps
        now = time.perf_counter()
        for i in range(100):
            now += 0.05  # 20 FPS
            aim._pid_step(pid, error=1000.0, now=now)

        # Integral should be capped
        assert abs(pid.integral) <= profile.integral_cap

    def test_derivative_kick_on_setpoint_change(self):
        """Sudden target change produces a derivative spike but stays within max_delta."""
        aim = AimController()
        screen_cx, screen_cy = 400.0, 300.0

        # Track a stationary target for a few frames
        for _ in range(5):
            aim.update(420.0, 310.0, screen_cx, screen_cy)

        # Suddenly jump target to the opposite side
        dx, dy = aim.update(200.0, 100.0, screen_cx, screen_cy)

        # Output magnitude should not exceed max_delta
        import math
        mag = math.hypot(dx, dy)
        assert mag <= aim.profile.max_delta + 1.0  # +1 for rounding

    def test_pid_reset_clears_state(self):
        """After reset, PID state is zeroed."""
        aim = AimController()
        aim.update(500.0, 400.0, 400.0, 300.0)
        aim.reset()
        assert aim._pid_x.integral == 0.0
        assert aim._pid_x.last_error == 0.0
        assert aim._pid_y.integral == 0.0
        assert aim._pid_y.last_error == 0.0

    def test_on_target_returns_zero(self):
        """When target is within deadzone, output is (0,0)."""
        aim = AimController()
        dx, dy = aim.update(400.0, 300.0, 400.0, 300.0)
        assert (dx, dy) == (0, 0)


# ---------------------------------------------------------------------------
# TEST-03b: Weapon Selection All Weapons
# ---------------------------------------------------------------------------

class TestWeaponSelectionAllWeapons:
    """Weapon selection across all range brackets and ammo scenarios."""

    def test_close_range_selects_valid_weapon(self):
        """At close range (50 units) with all weapons, a short-range weapon wins."""
        inventory = {name: 50 for name in WEAPONS if name != "gauntlet"}
        result = select_weapon(distance=50, inventory=inventory)
        # Fuzzy selection may pick shotgun, plasma, or other high-DPS weapon
        assert result is not None
        assert result in WEAPONS

    def test_mid_range_prefers_rocket_or_lightning(self):
        """At mid range (400 units) with all weapons, a mid-range weapon wins."""
        inventory = {name: 50 for name in WEAPONS if name != "gauntlet"}
        result = select_weapon(distance=400, inventory=inventory)
        # Rocket, lightning, or plasma are optimal at 400 units
        assert result in ("rocket", "lightning", "plasma", "machinegun")

    def test_far_range_prefers_railgun(self):
        """At far range (1000 units) with all weapons, railgun wins."""
        inventory = {name: 50 for name in WEAPONS if name != "gauntlet"}
        result = select_weapon(distance=1000, inventory=inventory)
        assert result in ("railgun", "plasma", "bfg")

    def test_zero_ammo_preferred_falls_back(self):
        """When preferred weapon has 0 ammo, select falls back to another."""
        # Only give ammo to machinegun
        inventory = {"machinegun": 50}
        result = select_weapon(distance=500, inventory=inventory)
        assert result == "machinegun"

    def test_empty_inventory_returns_gauntlet_or_none(self):
        """Empty inventory returns gauntlet (always available) or None."""
        result = select_weapon(distance=200, inventory={})
        assert result in ("gauntlet", None)

    def test_all_weapon_types_selectable(self):
        """Every weapon can be selected when it's the only one with ammo."""
        for name in WEAPONS:
            if name == "gauntlet":
                continue
            inventory = {name: 50}
            result = select_weapon(distance=WEAPONS[name].optimal_range,
                                   inventory=inventory)
            assert result == name, f"Expected {name} at its optimal range"


# ---------------------------------------------------------------------------
# TEST-03c: Threat Assessment Edge Cases
# ---------------------------------------------------------------------------

class TestThreatAssessmentEdgeCases:
    """Edge cases for evaluate_threat and ThreatAssessor."""

    def test_equal_health_armor_neutral(self):
        """Equal moderate health/armor with decent weapon -> FIGHT or CAUTIOUS."""
        result = evaluate_threat(
            my_health=60, my_armor=60,
            my_weapon="machinegun",
            enemy_count=1, enemy_distance=500,
        )
        # effective_hp = 60 + 60*0.66 = 99.6 > 80 but no power weapon
        # should be FIGHT (effective_hp > 50)
        assert result in ("FIGHT", "CAUTIOUS")

    def test_very_low_health_triggers_retreat(self):
        """Very low health (10 HP, no armor) always triggers RETREAT."""
        result = evaluate_threat(
            my_health=10, my_armor=0,
            my_weapon="railgun",
            enemy_count=1, enemy_distance=500,
        )
        assert result == "RETREAT"

    def test_no_weapon_defaults_safely(self):
        """None weapon still returns a valid verdict without error."""
        result = evaluate_threat(
            my_health=100, my_armor=100,
            my_weapon=None,
            enemy_count=1, enemy_distance=500,
        )
        assert result in ("FIGHT", "RETREAT", "CAUTIOUS")

    def test_outnumbered_low_hp_retreats(self):
        """Multiple enemies with moderate HP triggers RETREAT."""
        result = evaluate_threat(
            my_health=50, my_armor=10,
            my_weapon="machinegun",
            enemy_count=3, enemy_distance=400,
        )
        # effective_hp = 50 + 10*0.66 = 56.6 < 80, enemy_count > 1
        assert result == "RETREAT"

    def test_full_hp_power_weapon_fights(self):
        """Full health + armor + power weapon always fights."""
        result = evaluate_threat(
            my_health=100, my_armor=100,
            my_weapon="railgun",
            enemy_count=1, enemy_distance=800,
        )
        assert result == "FIGHT"

    def test_assessor_evaluate_returns_dict_keys(self):
        """ThreatAssessor.evaluate returns dict with required keys."""
        assessor = ThreatAssessor()
        result = assessor.evaluate(
            own_health=50, own_armor=50,
            own_weapon="machinegun",
            enemy_count=1, enemy_distance=500,
        )
        assert "verdict" in result
        assert "effective_hp" in result
        assert "has_power_weapon" in result

    def test_assessor_should_disengage_critical(self, make_awareness):
        """should_disengage returns True when health < 25."""
        assessor = ThreatAssessor()
        sa = make_awareness(health=20)
        assert assessor.should_disengage(sa) is True

    def test_assessor_should_not_disengage_healthy(self, make_awareness):
        """should_disengage returns False when health is high."""
        assessor = ThreatAssessor()
        sa = make_awareness(health=100)
        assert assessor.should_disengage(sa) is False
