"""Unit tests for the reflexes subsystem (RFLX-01..04, NAV-06).

Tests the extracted modules directly, not through strategic_brain.py.
Uses mocks for GameBridge, VirtualController, Navigator, ObjectTracker,
and MotionAnomalyTracker dependencies.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest

from openarena_perception.models import BrainState, SituationalAwareness
from openarena_perception.reflexes import SubsumptionArbiter, DeathHandler, StuckEscape


# ---------------------------------------------------------------------------
# RFLX-01: Damage response
# ---------------------------------------------------------------------------

class TestDamageResponse:
    """RFLX-01: Arbiter returns COMBAT when under attack with visible enemies."""

    def test_damage_response(self, make_awareness):
        """Arbiter returns COMBAT when under_attack=True, enemies_visible>0,
        and current_state is not DEAD."""
        arbiter = SubsumptionArbiter()
        sa = make_awareness(under_attack=True, enemies_visible=2)
        result = arbiter.evaluate(sa, BrainState.NAVIGATING, state_time=1.0)
        assert result == BrainState.COMBAT

    def test_damage_response_not_when_dead(self, make_awareness):
        """Arbiter does NOT return COMBAT when is_alive=False (DEAD takes priority)."""
        arbiter = SubsumptionArbiter()
        sa = make_awareness(under_attack=True, enemies_visible=2, is_alive=False)
        result = arbiter.evaluate(sa, BrainState.NAVIGATING, state_time=1.0)
        assert result == BrainState.DEAD

    def test_damage_response_under_1ms(self, make_awareness):
        """RFLX-01: arbiter.evaluate() completes in under 1ms."""
        arbiter = SubsumptionArbiter()
        sa = make_awareness(under_attack=True, enemies_visible=1)

        # Warm up
        arbiter.evaluate(sa, BrainState.NAVIGATING, state_time=1.0)

        # Measure
        start = time.perf_counter()
        for _ in range(100):
            arbiter.evaluate(sa, BrainState.NAVIGATING, state_time=1.0)
        elapsed = (time.perf_counter() - start) / 100

        assert elapsed < 0.001, f"evaluate() took {elapsed*1000:.3f}ms, expected < 1ms"


# ---------------------------------------------------------------------------
# RFLX-02: Death handling
# ---------------------------------------------------------------------------

class TestDeathHandling:
    """RFLX-02: DeathHandler death counter, control release, and respawn tap."""

    def test_death_handler_enters(self):
        """DeathHandler.on_enter() increments deaths counter, calls ctrl.release_all()."""
        bridge = MagicMock()
        ctrl = MagicMock()
        handler = DeathHandler(bridge, ctrl)
        anomaly_tracker = MagicMock()
        obj_tracker = MagicMock()

        sa = MagicMock()
        assert handler.deaths == 0

        handler.on_enter(sa, anomaly_tracker, obj_tracker)

        assert handler.deaths == 1
        ctrl.release_all.assert_called_once()
        anomaly_tracker.reset.assert_called_once()
        obj_tracker.reset.assert_called_once()

    def test_death_handler_tick_respawn(self):
        """DeathHandler.tick() sends +attack/-attack tap when was_alive transitions to False."""
        bridge = MagicMock()
        ctrl = MagicMock()
        handler = DeathHandler(bridge, ctrl)
        handler.was_alive = True

        sa = MagicMock()
        gs = MagicMock()

        asyncio.run(handler.tick(sa, gs))

        assert handler.was_alive is False
        bridge.release_all.assert_called_once()
        bridge.cmd.assert_any_call("+attack")
        bridge.cmd.assert_any_call("-attack")

    def test_death_handler_multiple_deaths(self):
        """Death counter increments on each on_enter call."""
        bridge = MagicMock()
        ctrl = MagicMock()
        handler = DeathHandler(bridge, ctrl)
        sa = MagicMock()
        at = MagicMock()
        ot = MagicMock()

        handler.on_enter(sa, at, ot)
        handler.on_enter(sa, at, ot)
        handler.on_enter(sa, at, ot)

        assert handler.deaths == 3


# ---------------------------------------------------------------------------
# RFLX-03: Stuck escape with blacklisting
# ---------------------------------------------------------------------------

class TestStuckEscape:
    """RFLX-03: StuckEscape blacklists after 2 stucks on same target."""

    def test_stuck_escape_blacklist(self):
        """StuckEscape.on_enter() blacklists target after 2 stucks on same target."""
        navigator = MagicMock()
        escape = StuckEscape(navigator)
        sa = MagicMock()

        # First stuck on same target -- should NOT blacklist
        result1 = escape.on_enter(sa, nav_target="item_health_large")
        assert result1 == "item_health_large"
        assert "item_health_large" not in escape.target_blacklist

        # Second stuck on same target -- should blacklist and return None
        result2 = escape.on_enter(sa, nav_target="item_health_large")
        assert result2 is None
        assert "item_health_large" in escape.target_blacklist

    def test_stuck_escape_tick_delegates(self):
        """StuckEscape.tick() calls navigator.handle_stuck()."""
        navigator = MagicMock()
        escape = StuckEscape(navigator)
        sa = MagicMock()
        sa.has_frame = True
        gs = MagicMock()
        gs.frame = MagicMock()

        asyncio.run(escape.tick(sa, gs))

        navigator.handle_stuck.assert_called_once()

    def test_is_blacklisted(self):
        """is_blacklisted returns True for recently blacklisted targets."""
        navigator = MagicMock()
        escape = StuckEscape(navigator)
        sa = MagicMock()

        # Trigger blacklist
        escape.on_enter(sa, nav_target="item_armor")
        escape.on_enter(sa, nav_target="item_armor")

        assert escape.is_blacklisted("item_armor") is True
        assert escape.is_blacklisted("item_health") is False

    def test_stuck_attempts_counter(self):
        """Each on_enter increments stuck_attempts."""
        navigator = MagicMock()
        escape = StuckEscape(navigator)
        sa = MagicMock()

        escape.on_enter(sa, nav_target=None)
        escape.on_enter(sa, nav_target=None)

        assert escape.stuck_attempts == 2


# ---------------------------------------------------------------------------
# RFLX-04: Priority ordering
# ---------------------------------------------------------------------------

class TestPriorityOrdering:
    """RFLX-04: Subsumption priority DEAD > COMBAT > STUCK."""

    def test_priority_dead_highest(self, make_awareness):
        """Arbiter returns DEAD regardless of other conditions when is_alive=False."""
        arbiter = SubsumptionArbiter()
        sa = make_awareness(
            is_alive=False,
            under_attack=True,
            enemies_visible=3,
            is_stuck=True,
            is_recovering=False,
        )
        result = arbiter.evaluate(sa, BrainState.NAVIGATING, state_time=1.0)
        assert result == BrainState.DEAD

    def test_priority_combat_over_stuck(self, make_awareness):
        """Arbiter returns COMBAT over STUCK when both conditions true."""
        arbiter = SubsumptionArbiter()
        sa = make_awareness(
            under_attack=True,
            enemies_visible=1,
            is_stuck=True,
            is_recovering=False,
        )
        result = arbiter.evaluate(sa, BrainState.NAVIGATING, state_time=1.0)
        assert result == BrainState.COMBAT

    def test_priority_stuck_not_from_combat(self, make_awareness):
        """Arbiter does NOT return STUCK when current_state is COMBAT."""
        arbiter = SubsumptionArbiter()
        sa = make_awareness(
            is_stuck=True,
            is_recovering=False,
            under_attack=False,
            enemies_visible=0,
        )
        result = arbiter.evaluate(sa, BrainState.COMBAT, state_time=1.0)
        assert result != BrainState.STUCK

    def test_stuck_from_navigating(self, make_awareness):
        """Arbiter returns STUCK from NAVIGATING state."""
        arbiter = SubsumptionArbiter()
        sa = make_awareness(
            is_stuck=True,
            is_recovering=False,
        )
        result = arbiter.evaluate(sa, BrainState.NAVIGATING, state_time=1.0)
        assert result == BrainState.STUCK


# ---------------------------------------------------------------------------
# NAV-06: Respawn to exploring
# ---------------------------------------------------------------------------

class TestRespawnToExploring:
    """NAV-06: Arbiter returns EXPLORING when current_state=DEAD and is_alive=True."""

    def test_respawn_to_exploring(self, make_awareness):
        """Arbiter returns EXPLORING when respawned (DEAD state, is_alive=True)."""
        arbiter = SubsumptionArbiter()
        sa = make_awareness(is_alive=True)
        result = arbiter.evaluate(sa, BrainState.DEAD, state_time=1.0)
        assert result == BrainState.EXPLORING
