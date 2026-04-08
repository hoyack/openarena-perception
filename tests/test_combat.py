"""Unit tests for the combat subsystem (CMBT-01..07).

Tests the extracted modules directly, not through strategic_brain.py.
Uses mocks for GameBridge, VirtualController dependencies.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from openarena_perception.combat import (
    AimController,
    CombatEngager,
    CombatMover,
    PROFILES,
    ThreatAssessor,
    WEAPONS,
    evaluate_threat,
    select_weapon,
    should_preemptive_switch,
)


# ---------------------------------------------------------------------------
# CMBT-01: Target acquisition
# ---------------------------------------------------------------------------

class TestTargetAcquisition:
    """CMBT-01: CombatEngager snaps aim toward attacker."""

    def test_target_acquisition(self, make_awareness):
        """CombatEngager.tick() calls ctrl.turn_degrees when attacker_direction != 0
        and seconds_since_damage < 0.3."""
        ctrl = MagicMock()
        bridge = MagicMock()
        mover = CombatMover()
        engager = CombatEngager(ctrl, bridge, mover)

        sa = make_awareness(
            attacker_direction=-1,
            seconds_since_damage=0.1,
            wall_ahead=False,
        )
        gs = MagicMock()

        asyncio.run(engager.tick(sa, gs))

        # attacker_direction=-1 => turn_degrees(-(-1)*15) = turn_degrees(15)
        ctrl.turn_degrees.assert_any_call(15)

    def test_no_snap_when_no_attacker(self, make_awareness):
        """No turn when attacker_direction is 0."""
        ctrl = MagicMock()
        bridge = MagicMock()
        mover = CombatMover()
        engager = CombatEngager(ctrl, bridge, mover)

        sa = make_awareness(
            attacker_direction=0,
            seconds_since_damage=0.1,
            wall_ahead=False,
        )
        gs = MagicMock()

        asyncio.run(engager.tick(sa, gs))

        # turn_degrees may be called for wall avoidance but not for snap
        # Check no call with 15 or -15
        for call in ctrl.turn_degrees.call_args_list:
            assert call.args[0] not in (15, -15), "Should not snap when attacker_direction=0"


# ---------------------------------------------------------------------------
# CMBT-02: Aim controller
# ---------------------------------------------------------------------------

class TestAimController:
    """CMBT-02: AimController construction and profiles."""

    def test_aim_controller_exists(self):
        """AimController can be constructed with default profile."""
        aim = AimController()
        assert aim is not None
        assert aim.profile is not None

    def test_aim_profiles(self):
        """PROFILES dict contains at least 'rail', 'rocket', 'default'."""
        assert "railgun" in PROFILES
        assert "rocket" in PROFILES
        assert "default" in PROFILES

    def test_aim_controller_update(self):
        """AimController.update returns (dx, dy) tuple."""
        aim = AimController()
        result = aim.update(target_cx=400, target_cy=300,
                            screen_cx=400, screen_cy=300)
        assert isinstance(result, tuple)
        assert len(result) == 2
        # On-target (deadzone) should return (0, 0)
        assert result == (0, 0)

    def test_aim_controller_off_target(self):
        """AimController.update returns non-zero deltas when off target."""
        aim = AimController()
        result = aim.update(target_cx=500, target_cy=400,
                            screen_cx=400, screen_cy=300)
        assert isinstance(result, tuple)
        # Should have non-zero movement
        assert result[0] != 0 or result[1] != 0


# ---------------------------------------------------------------------------
# CMBT-03: Weapon selection by range
# ---------------------------------------------------------------------------

class TestWeaponSelect:
    """CMBT-03: Fuzzy weapon selection based on range and ammo."""

    def test_weapon_select_close_range(self):
        """select_weapon prefers shotgun at very close range (50 units = optimal)."""
        # Give shotgun lots of ammo and only shotgun + gauntlet available
        inventory = {"shotgun": 50}
        result = select_weapon(distance=50, inventory=inventory)
        assert result == "shotgun"

    def test_weapon_select_long_range(self):
        """select_weapon returns railgun at long range with railgun ammo."""
        # Only railgun has ammo at this range
        inventory = {"railgun": 50}
        result = select_weapon(distance=1000, inventory=inventory)
        assert result == "railgun"

    def test_weapon_select_no_ammo(self):
        """select_weapon handles empty inventory gracefully."""
        result = select_weapon(distance=500, inventory={})
        # Should return gauntlet (always available) or None
        assert result in ("gauntlet", None)


# ---------------------------------------------------------------------------
# CMBT-04: Combat movement
# ---------------------------------------------------------------------------

class TestCombatMovement:
    """CMBT-04: CombatMover returns movement dict with strafe and jump keys."""

    def test_combat_mover_movement(self):
        """CombatMover.get_movement returns dict with strafe_left, strafe_right, jump."""
        mover = CombatMover()
        move = mover.get_movement(300, "machinegun", 0.9)

        assert isinstance(move, dict)
        assert "strafe_left" in move
        assert "strafe_right" in move
        assert "jump" in move
        assert "forward" in move
        assert "back" in move
        # All values should be booleans
        for key in ("strafe_left", "strafe_right", "jump", "forward", "back"):
            assert isinstance(move[key], bool), f"{key} should be bool"

    def test_combat_mover_low_skill(self):
        """Low skill produces minimal movement."""
        mover = CombatMover()
        move = mover.get_movement(300, "machinegun", 0.1)
        # Low skill = stand and shoot
        assert move["strafe_left"] is False
        assert move["strafe_right"] is False
        assert move["jump"] is False


# ---------------------------------------------------------------------------
# CMBT-05: Engage/disengage
# ---------------------------------------------------------------------------

class TestEngageDisengage:
    """CMBT-05: Combat entry/exit and disengage thresholds."""

    def test_engage_on_enter(self, make_awareness):
        """CombatEngager.on_enter() calls bridge.fire(True)."""
        ctrl = MagicMock()
        bridge = MagicMock()
        mover = CombatMover()
        engager = CombatEngager(ctrl, bridge, mover)
        sa = make_awareness()

        engager.on_enter(sa)

        bridge.fire.assert_called_once_with(True)

    def test_engage_disengage(self, make_awareness):
        """CombatEngager.on_exit() calls bridge.fire(False) and releases strafes."""
        ctrl = MagicMock()
        bridge = MagicMock()
        mover = CombatMover()
        engager = CombatEngager(ctrl, bridge, mover)
        sa = make_awareness()

        engager.on_exit(sa)

        bridge.fire.assert_called_once_with(False)
        ctrl.strafe_left.assert_called_once_with(False)
        ctrl.strafe_right.assert_called_once_with(False)

    def test_threat_should_disengage(self, make_awareness):
        """ThreatAssessor.should_disengage returns True when health < 25."""
        assessor = ThreatAssessor()
        sa = make_awareness(health=20)

        assert assessor.should_disengage(sa) is True

    def test_threat_should_not_disengage_healthy(self, make_awareness):
        """ThreatAssessor.should_disengage returns False when health is high."""
        assessor = ThreatAssessor()
        sa = make_awareness(health=100)

        assert assessor.should_disengage(sa) is False


# ---------------------------------------------------------------------------
# CMBT-06: Preemptive weapon switch
# ---------------------------------------------------------------------------

class TestPreemptiveSwitch:
    """CMBT-06: Recommend weapon switch when ammo critically low."""

    def test_preemptive_weapon_switch(self):
        """should_preemptive_switch returns alternative weapon when ammo <= 2."""
        inventory = {"rocket": 50, "machinegun": 0, "railgun": 10}
        result = should_preemptive_switch(
            current_weapon="machinegun",
            current_ammo=1,
            enemy_dist=400,
            inventory=inventory,
        )
        assert result is not None
        assert result != "machinegun"
        assert result in inventory

    def test_no_switch_when_plenty_ammo(self):
        """should_preemptive_switch returns None when ammo > 2."""
        result = should_preemptive_switch(
            current_weapon="machinegun",
            current_ammo=50,
            enemy_dist=400,
            inventory={"rocket": 50},
        )
        assert result is None

    def test_no_switch_when_no_inventory(self):
        """should_preemptive_switch returns None when no inventory provided."""
        result = should_preemptive_switch(
            current_weapon="machinegun",
            current_ammo=1,
            enemy_dist=400,
            inventory=None,
        )
        assert result is None


# ---------------------------------------------------------------------------
# CMBT-07: Threat assessment
# ---------------------------------------------------------------------------

class TestThreatAssessment:
    """CMBT-07: ThreatAssessor evaluates engagement recommendation."""

    def test_threat_assessment(self):
        """ThreatAssessor.evaluate returns dict with engagement recommendation."""
        assessor = ThreatAssessor()
        result = assessor.evaluate(
            own_health=100, own_armor=50,
            own_weapon="railgun",
            enemy_count=1, enemy_distance=500,
        )
        assert isinstance(result, dict)
        assert "verdict" in result
        assert result["verdict"] in ("FIGHT", "RETREAT", "CAUTIOUS")
        assert "effective_hp" in result
        assert "has_power_weapon" in result

    def test_evaluate_threat_func(self):
        """evaluate_threat function returns string threat verdict."""
        result = evaluate_threat(
            my_health=100, my_armor=50,
            my_weapon="railgun",
            enemy_count=1, enemy_distance=500,
        )
        assert result in ("FIGHT", "RETREAT", "CAUTIOUS")

    def test_evaluate_threat_retreat_low_hp(self):
        """evaluate_threat returns RETREAT at very low effective HP."""
        result = evaluate_threat(
            my_health=15, my_armor=0,
            my_weapon="machinegun",
            enemy_count=1, enemy_distance=300,
        )
        assert result == "RETREAT"

    def test_evaluate_threat_fight_strong(self):
        """evaluate_threat returns FIGHT with high HP and power weapon."""
        result = evaluate_threat(
            my_health=100, my_armor=100,
            my_weapon="railgun",
            enemy_count=1, enemy_distance=500,
        )
        assert result == "FIGHT"


# ---------------------------------------------------------------------------
# NAV-05: Obstacle avoidance during combat (cross-ref from test_navigation.py)
# ---------------------------------------------------------------------------

class TestObstacleAvoidanceCombat:
    """NAV-05: CombatEngager turns away when wall_ahead=True, wall_score>0.7."""

    def test_obstacle_avoidance(self, make_awareness):
        """CombatEngager.tick turns away when wall_ahead=True, wall_score>0.7."""
        ctrl = MagicMock()
        bridge = MagicMock()
        mover = CombatMover()
        engager = CombatEngager(ctrl, bridge, mover)

        sa = make_awareness(
            wall_ahead=True,
            wall_score=0.9,
            open_direction=1,
            attacker_direction=0,
            seconds_since_damage=5.0,
        )
        gs = MagicMock()

        asyncio.run(engager.tick(sa, gs))

        # Should stop forward movement and turn toward open space
        ctrl.forward.assert_any_call(False)
        # open_direction=1 => turn_degrees(1 * 30) = 30
        ctrl.turn_degrees.assert_any_call(30)
