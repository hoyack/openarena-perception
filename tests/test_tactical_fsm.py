"""Unit tests for TacticalFSM (TACT-01).

Tests the extracted FSM orchestrator: initialization, state transitions,
enter/exit hooks, and dispatch delegation.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openarena_perception.models import BrainState
from openarena_perception.tactics.fsm import TacticalFSM


def _make_fsm(**overrides):
    """Build a TacticalFSM with all-mocked dependencies."""
    deps = dict(
        arbiter=MagicMock(),
        death_handler=MagicMock(),
        stuck_escape=MagicMock(),
        engager=MagicMock(),
        nav_behavior=MagicMock(),
        survey_behavior=MagicMock(),
        ctrl=MagicMock(),
        anomaly_tracker=MagicMock(),
        obj_tracker=MagicMock(),
    )
    deps.update(overrides)
    return TacticalFSM(**deps), deps


class TestTacticalFSMInit:
    """TacticalFSM starts in EXPLORING state."""

    def test_initial_state_is_exploring(self):
        fsm, _ = _make_fsm()
        assert fsm.state == BrainState.EXPLORING

    def test_state_property_returns_current_state(self):
        fsm, _ = _make_fsm()
        assert fsm.state == fsm._state


class TestEvaluateTransitions:
    """evaluate_transitions delegates to arbiter."""

    def test_delegates_to_arbiter(self, make_awareness):
        fsm, deps = _make_fsm()
        deps["arbiter"].evaluate.return_value = BrainState.COMBAT
        sa = make_awareness()
        result = fsm.evaluate_transitions(sa)
        assert result == BrainState.COMBAT
        deps["arbiter"].evaluate.assert_called_once()
        # Verify correct args: sa, current_state, state_time, **context
        call_args = deps["arbiter"].evaluate.call_args
        assert call_args[0][0] is sa
        assert call_args[0][1] == BrainState.EXPLORING


class TestOnEnterState:
    """on_enter_state dispatches to correct subsystem."""

    def test_enter_dead_calls_death_handler(self, make_awareness):
        fsm, deps = _make_fsm()
        sa = make_awareness(is_alive=False)
        fsm.on_enter_state(BrainState.DEAD, sa)
        deps["death_handler"].on_enter.assert_called_once_with(
            sa, deps["anomaly_tracker"], deps["obj_tracker"]
        )

    def test_enter_combat_calls_engager(self, make_awareness):
        fsm, deps = _make_fsm()
        sa = make_awareness(under_attack=True, enemies_visible=1)
        fsm.on_enter_state(BrainState.COMBAT, sa)
        deps["engager"].on_enter.assert_called_once_with(sa)

    def test_enter_stuck_calls_stuck_escape(self, make_awareness):
        fsm, deps = _make_fsm()
        deps["nav_behavior"].nav_target = "item_health"
        deps["stuck_escape"].on_enter.return_value = "new_target"
        sa = make_awareness(is_stuck=True)
        fsm.on_enter_state(BrainState.STUCK, sa)
        deps["stuck_escape"].on_enter.assert_called_once_with(sa, "item_health")

    def test_enter_stuck_clears_nav_target_on_blacklist(self, make_awareness):
        fsm, deps = _make_fsm()
        deps["nav_behavior"].nav_target = "item_health"
        deps["stuck_escape"].on_enter.return_value = None  # target was blacklisted
        sa = make_awareness(is_stuck=True)
        fsm.on_enter_state(BrainState.STUCK, sa)
        assert deps["nav_behavior"].nav_target is None

    def test_enter_exploring_calls_nav_behavior(self, make_awareness):
        fsm, deps = _make_fsm()
        sa = make_awareness()
        fsm.on_enter_state(BrainState.EXPLORING, sa)
        deps["nav_behavior"].on_enter_exploring.assert_called_once()
        deps["stuck_escape"].reset_stuck_count.assert_called_once()

    def test_enter_navigating_calls_nav_behavior(self, make_awareness):
        fsm, deps = _make_fsm()
        sa = make_awareness()
        fsm.on_enter_state(BrainState.NAVIGATING, sa)
        deps["nav_behavior"].on_enter_navigating.assert_called_once()
        deps["stuck_escape"].reset_stuck_count.assert_called_once()


class TestOnExitState:
    """on_exit_state dispatches to correct subsystem."""

    def test_exit_always_calls_death_handler_on_exit(self, make_awareness):
        fsm, deps = _make_fsm()
        sa = make_awareness()
        fsm.on_exit_state(BrainState.NAVIGATING, sa)
        deps["death_handler"].on_exit.assert_called_once_with(sa)

    def test_exit_combat_calls_engager(self, make_awareness):
        fsm, deps = _make_fsm()
        sa = make_awareness()
        fsm.on_exit_state(BrainState.COMBAT, sa)
        deps["engager"].on_exit.assert_called_once_with(sa)

    def test_exit_surveying_centers_view(self, make_awareness):
        fsm, deps = _make_fsm()
        sa = make_awareness()
        fsm.on_exit_state(BrainState.SURVEYING, sa)
        deps["ctrl"].center_view.assert_called_once()

    def test_exit_surveying_no_ctrl(self, make_awareness):
        """No crash when ctrl is None."""
        fsm, deps = _make_fsm(ctrl=None)
        sa = make_awareness()
        fsm.on_exit_state(BrainState.SURVEYING, sa)  # should not raise


class TestTick:
    """tick() transitions state and dispatches."""

    def test_tick_transitions_and_dispatches(self, make_awareness):
        fsm, deps = _make_fsm()
        deps["arbiter"].evaluate.return_value = BrainState.COMBAT
        deps["engager"].tick = AsyncMock()
        sa = make_awareness(under_attack=True, enemies_visible=1)
        gs = MagicMock()

        asyncio.run(fsm.tick(sa, gs))

        assert fsm.state == BrainState.COMBAT
        deps["engager"].on_enter.assert_called_once()
        deps["engager"].tick.assert_awaited_once()

    def test_tick_no_transition_dispatches_current(self, make_awareness):
        fsm, deps = _make_fsm()
        deps["arbiter"].evaluate.return_value = BrainState.EXPLORING
        deps["nav_behavior"].tick_exploring = AsyncMock()
        sa = make_awareness()
        gs = MagicMock()

        asyncio.run(fsm.tick(sa, gs))

        assert fsm.state == BrainState.EXPLORING
        deps["nav_behavior"].tick_exploring.assert_awaited_once()
