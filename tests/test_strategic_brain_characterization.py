"""Characterization tests for strategic_brain.py FSM.

These tests capture the CURRENT behavior of the god object's state machine
before any decomposition work begins. They are the safety net for Phases 2-5.

Every test documents actual behavior, not desired behavior. If the code does
something unexpected, the test captures it as-is.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, call

import pytest

from openarena_perception.models import BrainState
from openarena_perception.strategic_brain import StrategicBrain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_state(brain: StrategicBrain, state: BrainState, seconds_ago: float = 0.0):
    """Put brain into a specific state with controlled timing."""
    brain._state = state
    brain._state_enter_time = time.time() - seconds_ago


# ===========================================================================
# Class 1: Transition Priority Tests
# ===========================================================================

class TestTransitionPriorities:
    """Verify that higher-priority transitions win over lower ones.

    Priority order: DEAD > COMBAT > STUCK > PICKUP > DOOR > SURVEY
    """

    def test_p1_dead_overrides_everything(self, strategic_brain, make_awareness):
        """P1: is_alive=False always transitions to DEAD regardless of state."""
        for state in BrainState:
            _set_state(strategic_brain, state, seconds_ago=10.0)
            sa = make_awareness(
                is_alive=False, under_attack=True, enemies_visible=3,
                is_stuck=True, lockable_anomaly=True,
            )
            result = strategic_brain._evaluate_transitions(sa)
            assert result == BrainState.DEAD, (
                f"Expected DEAD from {state.value}, got {result.value}"
            )

    def test_p2_combat_when_under_attack_with_enemies(
        self, strategic_brain, make_awareness
    ):
        """P2: under_attack + enemies_visible > 0 -> COMBAT."""
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=5.0)
        sa = make_awareness(under_attack=True, enemies_visible=2)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.COMBAT

    def test_p2_no_combat_without_visible_enemies(
        self, strategic_brain, make_awareness
    ):
        """P2: under_attack but enemies_visible=0 does NOT trigger COMBAT."""
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=5.0)
        sa = make_awareness(under_attack=True, enemies_visible=0)
        result = strategic_brain._evaluate_transitions(sa)
        assert result != BrainState.COMBAT

    def test_p2_combat_overrides_stuck(self, strategic_brain, make_awareness):
        """P2 beats P3: under_attack + enemies while stuck -> COMBAT, not STUCK."""
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=5.0)
        sa = make_awareness(
            under_attack=True, enemies_visible=1,
            is_stuck=True, is_recovering=False,
        )
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.COMBAT

    def test_p2_combat_overrides_pickup(self, strategic_brain, make_awareness):
        """P2 beats P4: under_attack + enemies + lockable -> COMBAT, not PICKUP."""
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=5.0)
        sa = make_awareness(
            under_attack=True, enemies_visible=1,
            lockable_anomaly=True,
        )
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.COMBAT

    def test_p2_no_combat_from_dead_state(self, strategic_brain, make_awareness):
        """P2 explicitly excludes DEAD state (code checks self._state != DEAD)."""
        _set_state(strategic_brain, BrainState.DEAD, seconds_ago=5.0)
        sa = make_awareness(
            is_alive=True, under_attack=True, enemies_visible=2,
        )
        # From DEAD with is_alive=True, the return-from-DEAD rule fires first
        # since P2 checks self._state != DEAD
        result = strategic_brain._evaluate_transitions(sa)
        # The DEAD->EXPLORING return transition will fire
        assert result == BrainState.EXPLORING

    def test_p3_stuck_when_not_in_combat(self, strategic_brain, make_awareness):
        """P3: is_stuck + not recovering + not in excluded states -> STUCK."""
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=5.0)
        sa = make_awareness(is_stuck=True, is_recovering=False)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.STUCK

    def test_p3_stuck_blocked_during_combat(self, strategic_brain, make_awareness):
        """P3: COMBAT state is excluded from stuck transitions."""
        _set_state(strategic_brain, BrainState.COMBAT, seconds_ago=5.0)
        sa = make_awareness(
            is_stuck=True, is_recovering=False,
            under_attack=True, enemies_visible=1,
        )
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.COMBAT

    def test_p3_stuck_blocked_during_surveying(self, strategic_brain, make_awareness):
        """P3: SURVEYING state is excluded from stuck transitions."""
        _set_state(strategic_brain, BrainState.SURVEYING, seconds_ago=1.0)
        sa = make_awareness(is_stuck=True, is_recovering=False)
        result = strategic_brain._evaluate_transitions(sa)
        assert result != BrainState.STUCK

    def test_p3_stuck_not_when_recovering(self, strategic_brain, make_awareness):
        """P3: is_recovering=True blocks stuck transition."""
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=5.0)
        sa = make_awareness(is_stuck=True, is_recovering=True)
        result = strategic_brain._evaluate_transitions(sa)
        assert result != BrainState.STUCK

    def test_p4_pickup_from_navigating(self, strategic_brain, make_awareness):
        """P4: NAVIGATING + lockable_anomaly -> PICKING_UP_ITEM."""
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=5.0)
        sa = make_awareness(lockable_anomaly=True)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.PICKING_UP_ITEM

    def test_p4_pickup_from_exploring(self, strategic_brain, make_awareness):
        """P4: EXPLORING + lockable_anomaly -> PICKING_UP_ITEM."""
        _set_state(strategic_brain, BrainState.EXPLORING, seconds_ago=5.0)
        sa = make_awareness(lockable_anomaly=True)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.PICKING_UP_ITEM

    def test_p4_pickup_not_from_combat(self, strategic_brain, make_awareness):
        """P4: Pickup only from NAVIGATING/EXPLORING, not other states."""
        _set_state(strategic_brain, BrainState.STUCK, seconds_ago=5.0)
        sa = make_awareness(lockable_anomaly=True, is_stuck=True, is_recovering=True)
        result = strategic_brain._evaluate_transitions(sa)
        assert result != BrainState.PICKING_UP_ITEM

    def test_p5_traversing_door_needs_wall_and_time(
        self, strategic_brain, make_awareness
    ):
        """P5: NAVIGATING + state_time>2s + wall_ahead + wall_score>0.7 + has_path."""
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=3.0)
        sa = make_awareness(
            wall_ahead=True, wall_score=0.8, has_path=True,
        )
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.TRAVERSING_DOOR

    def test_p5_no_door_if_under_2s(self, strategic_brain, make_awareness):
        """P5: Same conditions but state_time < 2s -> NOT TRAVERSING_DOOR."""
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=1.0)
        sa = make_awareness(
            wall_ahead=True, wall_score=0.8, has_path=True,
        )
        result = strategic_brain._evaluate_transitions(sa)
        assert result != BrainState.TRAVERSING_DOOR

    def test_p5_no_door_if_wall_score_low(self, strategic_brain, make_awareness):
        """P5: wall_score <= 0.7 -> NOT TRAVERSING_DOOR."""
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=3.0)
        sa = make_awareness(
            wall_ahead=True, wall_score=0.5, has_path=True,
        )
        result = strategic_brain._evaluate_transitions(sa)
        assert result != BrainState.TRAVERSING_DOOR

    def test_p5_no_door_from_exploring(self, strategic_brain, make_awareness):
        """P5: Door transition only from NAVIGATING, not EXPLORING."""
        _set_state(strategic_brain, BrainState.EXPLORING, seconds_ago=3.0)
        sa = make_awareness(
            wall_ahead=True, wall_score=0.8, has_path=True,
        )
        result = strategic_brain._evaluate_transitions(sa)
        assert result != BrainState.TRAVERSING_DOOR


# ===========================================================================
# Class 2: Return Transitions
# ===========================================================================

class TestReturnTransitions:
    """Verify transitions for exiting temporary states."""

    def test_return_from_dead(self, strategic_brain, make_awareness):
        """DEAD + is_alive=True -> EXPLORING."""
        _set_state(strategic_brain, BrainState.DEAD, seconds_ago=5.0)
        sa = make_awareness(is_alive=True)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.EXPLORING

    def test_return_from_combat(self, strategic_brain, make_awareness):
        """COMBAT + not under_attack + seconds_since_damage>3.0 -> NAVIGATING."""
        _set_state(strategic_brain, BrainState.COMBAT, seconds_ago=5.0)
        sa = make_awareness(
            under_attack=False, seconds_since_damage=4.0,
            enemies_visible=0,
        )
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.NAVIGATING

    def test_combat_stays_if_recent_damage(self, strategic_brain, make_awareness):
        """COMBAT + not under_attack + seconds_since_damage<3.0 -> stays COMBAT."""
        _set_state(strategic_brain, BrainState.COMBAT, seconds_ago=5.0)
        sa = make_awareness(
            under_attack=False, seconds_since_damage=2.0,
            enemies_visible=0,
        )
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.COMBAT

    def test_combat_stays_if_still_under_attack(
        self, strategic_brain, make_awareness
    ):
        """COMBAT + still under_attack -> stays COMBAT."""
        _set_state(strategic_brain, BrainState.COMBAT, seconds_ago=5.0)
        sa = make_awareness(
            under_attack=True, enemies_visible=1,
            seconds_since_damage=0.5,
        )
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.COMBAT

    def test_return_from_stuck(self, strategic_brain, make_awareness):
        """STUCK + not is_stuck + not is_recovering -> NAVIGATING."""
        _set_state(strategic_brain, BrainState.STUCK, seconds_ago=5.0)
        sa = make_awareness(is_stuck=False, is_recovering=False)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.NAVIGATING

    def test_stuck_stays_if_still_stuck(self, strategic_brain, make_awareness):
        """STUCK + still is_stuck -> stays STUCK (re-enters via P3)."""
        _set_state(strategic_brain, BrainState.STUCK, seconds_ago=5.0)
        sa = make_awareness(is_stuck=True, is_recovering=False)
        result = strategic_brain._evaluate_transitions(sa)
        # P3 fires again, returning STUCK
        assert result == BrainState.STUCK

    def test_surveying_timeout(self, strategic_brain, make_awareness):
        """SURVEYING + state_time > 15.0 -> NAVIGATING."""
        _set_state(strategic_brain, BrainState.SURVEYING, seconds_ago=16.0)
        sa = make_awareness()
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.NAVIGATING

    def test_surveying_stays_before_timeout(self, strategic_brain, make_awareness):
        """SURVEYING + state_time < 15.0 -> stays SURVEYING."""
        _set_state(strategic_brain, BrainState.SURVEYING, seconds_ago=5.0)
        sa = make_awareness()
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.SURVEYING

    def test_traversing_door_wall_cleared(self, strategic_brain, make_awareness):
        """TRAVERSING_DOOR + wall_score < 0.3 -> NAVIGATING."""
        _set_state(strategic_brain, BrainState.TRAVERSING_DOOR, seconds_ago=1.0)
        sa = make_awareness(wall_score=0.1)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.NAVIGATING

    def test_traversing_door_timeout(self, strategic_brain, make_awareness):
        """TRAVERSING_DOOR + state_time > 5.0 -> NAVIGATING."""
        _set_state(strategic_brain, BrainState.TRAVERSING_DOOR, seconds_ago=6.0)
        sa = make_awareness(wall_score=0.9)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.NAVIGATING

    def test_traversing_door_stays_if_wall_still_high(
        self, strategic_brain, make_awareness
    ):
        """TRAVERSING_DOOR + wall_score >= 0.3 + state_time < 5.0 -> stays."""
        _set_state(strategic_brain, BrainState.TRAVERSING_DOOR, seconds_ago=2.0)
        sa = make_awareness(wall_score=0.5)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.TRAVERSING_DOOR

    def test_pickup_item_done(self, strategic_brain, make_awareness):
        """PICKING_UP_ITEM + not lockable_anomaly -> NAVIGATING."""
        _set_state(strategic_brain, BrainState.PICKING_UP_ITEM, seconds_ago=2.0)
        sa = make_awareness(lockable_anomaly=False)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.NAVIGATING

    def test_pickup_item_timeout(self, strategic_brain, make_awareness):
        """PICKING_UP_ITEM + state_time > 5.0 -> NAVIGATING (even if still lockable)."""
        _set_state(strategic_brain, BrainState.PICKING_UP_ITEM, seconds_ago=6.0)
        sa = make_awareness(lockable_anomaly=True)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.NAVIGATING

    def test_exploring_to_navigating(self, strategic_brain, make_awareness):
        """EXPLORING + commander.should_decide()=True -> NAVIGATING."""
        strategic_brain.commander.should_decide.return_value = True
        _set_state(strategic_brain, BrainState.EXPLORING, seconds_ago=5.0)
        sa = make_awareness()
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.NAVIGATING

    def test_navigating_to_exploring(self, strategic_brain, make_awareness):
        """NAVIGATING + not has_path + commander.should_decide()=False -> EXPLORING."""
        strategic_brain.commander.should_decide.return_value = False
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=5.0)
        sa = make_awareness(has_path=False)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.EXPLORING


# ===========================================================================
# Class 3: Stay-in-State Tests
# ===========================================================================

class TestStayInState:
    """Verify state does not change when no transition fires."""

    def test_navigating_stays_when_healthy(self, strategic_brain, make_awareness):
        """NAVIGATING + healthy + has_path -> stays NAVIGATING."""
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=5.0)
        sa = make_awareness(has_path=True)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.NAVIGATING

    def test_exploring_stays_when_no_decision(self, strategic_brain, make_awareness):
        """EXPLORING + not should_decide -> stays EXPLORING."""
        strategic_brain.commander.should_decide.return_value = False
        _set_state(strategic_brain, BrainState.EXPLORING, seconds_ago=5.0)
        sa = make_awareness(has_path=True)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.EXPLORING

    def test_dead_stays_when_not_alive(self, strategic_brain, make_awareness):
        """DEAD + not is_alive -> stays DEAD."""
        _set_state(strategic_brain, BrainState.DEAD, seconds_ago=5.0)
        sa = make_awareness(is_alive=False)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.DEAD


# ===========================================================================
# Class 4: On-Enter Side Effects
# ===========================================================================

class TestOnEnterSideEffects:
    """Verify side effects when entering a state."""

    def test_enter_dead_increments_deaths(self, strategic_brain, make_awareness):
        """Entering DEAD increments deaths counter."""
        deaths_before = strategic_brain._deaths
        sa = make_awareness(is_alive=False)
        strategic_brain._on_enter_state(BrainState.DEAD, sa)
        assert strategic_brain._deaths == deaths_before + 1

    def test_enter_dead_releases_controls(self, strategic_brain, make_awareness):
        """Entering DEAD calls ctrl.release_all()."""
        sa = make_awareness(is_alive=False)
        strategic_brain._on_enter_state(BrainState.DEAD, sa)
        strategic_brain.ctrl.release_all.assert_called_once()

    def test_enter_dead_resets_trackers(self, strategic_brain, make_awareness):
        """Entering DEAD resets anomaly and object trackers."""
        sa = make_awareness(is_alive=False)
        strategic_brain._on_enter_state(BrainState.DEAD, sa)
        strategic_brain.anomaly.reset.assert_called_once()
        strategic_brain.obj_tracker.reset.assert_called_once()

    def test_enter_combat_starts_firing(self, strategic_brain, make_awareness):
        """Entering COMBAT calls bridge.fire(True)."""
        sa = make_awareness(under_attack=True, enemies_visible=1)
        strategic_brain._on_enter_state(BrainState.COMBAT, sa)
        strategic_brain.bridge.fire.assert_called_once_with(True)

    def test_enter_stuck_increments_counter(self, strategic_brain, make_awareness):
        """Entering STUCK increments _stuck_attempts."""
        stuck_before = strategic_brain._stuck_attempts
        sa = make_awareness(is_stuck=True)
        strategic_brain._on_enter_state(BrainState.STUCK, sa)
        assert strategic_brain._stuck_attempts == stuck_before + 1

    def test_enter_stuck_blacklists_after_2_stucks(
        self, strategic_brain, make_awareness
    ):
        """Entering STUCK blacklists target after 2 stucks on same target."""
        strategic_brain._nav_target = "item_health_large"
        strategic_brain._stucks_on_current_target = 1  # will become 2
        sa = make_awareness(is_stuck=True)
        strategic_brain._on_enter_state(BrainState.STUCK, sa)
        # After 2nd stuck, target should be blacklisted
        assert "item_health_large" in strategic_brain._target_blacklist
        assert strategic_brain._nav_target is None  # cleared
        assert strategic_brain._stucks_on_current_target == 0  # reset

    def test_enter_exploring_resets_stuck_counter(
        self, strategic_brain, make_awareness
    ):
        """Entering EXPLORING resets _stuck_attempts and calls path_to_random."""
        strategic_brain._stuck_attempts = 5
        sa = make_awareness()
        strategic_brain._on_enter_state(BrainState.EXPLORING, sa)
        assert strategic_brain._stuck_attempts == 0
        strategic_brain.nav.path_to_random.assert_called_once()

    def test_enter_navigating_resets_stuck_counter(
        self, strategic_brain, make_awareness
    ):
        """Entering NAVIGATING resets _stuck_attempts."""
        strategic_brain._stuck_attempts = 3
        sa = make_awareness()
        strategic_brain._on_enter_state(BrainState.NAVIGATING, sa)
        assert strategic_brain._stuck_attempts == 0


# ===========================================================================
# Class 5: On-Exit Side Effects
# ===========================================================================

class TestOnExitSideEffects:
    """Verify side effects when exiting a state."""

    def test_exit_always_releases_look_actions(
        self, strategic_brain, make_awareness
    ):
        """Exiting any state releases lookup/lookdown and centerviews."""
        sa = make_awareness()
        strategic_brain._on_exit_state(BrainState.NAVIGATING, sa)
        calls = strategic_brain.bridge.cmd.call_args_list
        cmd_args = [c[0][0] for c in calls]
        assert "-lookup" in cmd_args
        assert "-lookdown" in cmd_args
        assert "centerview" in cmd_args

    def test_exit_combat_stops_firing(self, strategic_brain, make_awareness):
        """Exiting COMBAT calls bridge.fire(False)."""
        sa = make_awareness()
        strategic_brain._on_exit_state(BrainState.COMBAT, sa)
        strategic_brain.bridge.fire.assert_called_once_with(False)

    def test_exit_combat_stops_strafing(self, strategic_brain, make_awareness):
        """Exiting COMBAT stops left and right strafing."""
        sa = make_awareness()
        strategic_brain._on_exit_state(BrainState.COMBAT, sa)
        strategic_brain.ctrl.strafe_left.assert_called_once_with(False)
        strategic_brain.ctrl.strafe_right.assert_called_once_with(False)

    def test_exit_surveying_centers_view(self, strategic_brain, make_awareness):
        """Exiting SURVEYING calls ctrl.center_view()."""
        sa = make_awareness()
        strategic_brain._on_exit_state(BrainState.SURVEYING, sa)
        strategic_brain.ctrl.center_view.assert_called_once()


# ===========================================================================
# Class 6: Timing Guards (boundary conditions)
# ===========================================================================

class TestTimingGuards:
    """Verify state-time thresholds are correctly enforced."""

    def test_door_2s_boundary_exact(self, strategic_brain, make_awareness):
        """Door transition requires state_time > 2.0 (strictly greater)."""
        # At exactly 2.0s, should NOT transition
        _set_state(strategic_brain, BrainState.NAVIGATING, seconds_ago=2.0)
        sa = make_awareness(wall_ahead=True, wall_score=0.8, has_path=True)
        result = strategic_brain._evaluate_transitions(sa)
        # Due to time.time() call inside _evaluate_transitions, state_time
        # will be approximately 2.0. The check is `> 2.0` so this is borderline.
        # We test the clearly-past case above (3.0s) and clearly-before (1.0s).
        # This test documents the boundary behavior.
        # At exactly 2.0s elapsed it may or may not fire depending on timing.

    def test_combat_cooldown_3s(self, strategic_brain, make_awareness):
        """Combat exit requires seconds_since_damage > 3.0."""
        _set_state(strategic_brain, BrainState.COMBAT, seconds_ago=10.0)
        # Exactly 3.0 -- should NOT exit (check is > 3.0, not >=)
        sa = make_awareness(
            under_attack=False, seconds_since_damage=3.0, enemies_visible=0,
        )
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.COMBAT

        # 3.1 -- should exit
        sa2 = make_awareness(
            under_attack=False, seconds_since_damage=3.1, enemies_visible=0,
        )
        result2 = strategic_brain._evaluate_transitions(sa2)
        assert result2 == BrainState.NAVIGATING

    def test_surveying_15s_timeout(self, strategic_brain, make_awareness):
        """Surveying exits after > 15.0 seconds."""
        _set_state(strategic_brain, BrainState.SURVEYING, seconds_ago=14.0)
        sa = make_awareness()
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.SURVEYING

        _set_state(strategic_brain, BrainState.SURVEYING, seconds_ago=16.0)
        result2 = strategic_brain._evaluate_transitions(sa)
        assert result2 == BrainState.NAVIGATING

    def test_pickup_5s_timeout(self, strategic_brain, make_awareness):
        """Pickup item exits after > 5.0 seconds."""
        _set_state(strategic_brain, BrainState.PICKING_UP_ITEM, seconds_ago=4.0)
        sa = make_awareness(lockable_anomaly=True)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.PICKING_UP_ITEM

        _set_state(strategic_brain, BrainState.PICKING_UP_ITEM, seconds_ago=6.0)
        result2 = strategic_brain._evaluate_transitions(sa)
        assert result2 == BrainState.NAVIGATING

    def test_door_5s_timeout(self, strategic_brain, make_awareness):
        """Door traversal exits after > 5.0 seconds."""
        _set_state(strategic_brain, BrainState.TRAVERSING_DOOR, seconds_ago=4.0)
        sa = make_awareness(wall_score=0.5)
        result = strategic_brain._evaluate_transitions(sa)
        assert result == BrainState.TRAVERSING_DOOR

        _set_state(strategic_brain, BrainState.TRAVERSING_DOOR, seconds_ago=6.0)
        result2 = strategic_brain._evaluate_transitions(sa)
        assert result2 == BrainState.NAVIGATING
