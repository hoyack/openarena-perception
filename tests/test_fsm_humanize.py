"""Tests for TacticalFSM humanization: reaction delay + hesitation (HUMN-02/06).

TDD RED: These tests define the expected behavior for reaction time delays
and hesitation in TacticalFSM.tick(). They should FAIL before implementation.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openarena_perception.combat.humanize import HumanizationConfig
from openarena_perception.models import BrainState
from openarena_perception.tactics.fsm import TacticalFSM


def _make_fsm(humanize_config=None, **overrides):
    """Build a TacticalFSM with all-mocked dependencies and optional humanization."""
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
    return TacticalFSM(humanize_config=humanize_config, **deps), deps


class TestFSMNoHumanization:
    """Without humanize_config, behavior is identical to original."""

    def test_no_config_immediate_transition(self, make_awareness):
        fsm, deps = _make_fsm(humanize_config=None)
        deps["arbiter"].evaluate.return_value = BrainState.COMBAT
        deps["engager"].tick = AsyncMock()
        sa = make_awareness(under_attack=True, enemies_visible=1)
        gs = MagicMock()

        asyncio.run(fsm.tick(sa, gs))

        assert fsm.state == BrainState.COMBAT
        deps["engager"].on_enter.assert_called_once()

    def test_no_config_no_pending_transition(self, make_awareness):
        fsm, _ = _make_fsm(humanize_config=None)
        assert fsm._pending_transition is None


class TestFSMReactionDelay:
    """With humanize_config, transitions are delayed by reaction time."""

    def test_config_stored(self):
        cfg = HumanizationConfig.from_skill_level(3)
        fsm, _ = _make_fsm(humanize_config=cfg)
        assert fsm._humanize_config is cfg

    def test_pending_transition_created(self, make_awareness):
        cfg = HumanizationConfig.from_skill_level(3)
        fsm, deps = _make_fsm(humanize_config=cfg)
        deps["arbiter"].evaluate.return_value = BrainState.COMBAT
        deps["engager"].tick = AsyncMock()
        deps["nav_behavior"].tick_exploring = AsyncMock()
        sa = make_awareness(under_attack=True, enemies_visible=1)
        gs = MagicMock()

        # First tick: should NOT transition yet (pending)
        asyncio.run(fsm.tick(sa, gs))

        # State should still be EXPLORING because delay hasn't expired
        assert fsm.state == BrainState.EXPLORING
        assert fsm._pending_transition is not None
        assert fsm._pending_transition[0] == BrainState.COMBAT

    def test_transition_executes_after_delay(self, make_awareness):
        cfg = HumanizationConfig.from_skill_level(3)
        fsm, deps = _make_fsm(humanize_config=cfg)
        deps["arbiter"].evaluate.return_value = BrainState.COMBAT
        deps["engager"].tick = AsyncMock()
        deps["nav_behavior"].tick_exploring = AsyncMock()
        sa = make_awareness(under_attack=True, enemies_visible=1)
        gs = MagicMock()

        # First tick: creates pending
        asyncio.run(fsm.tick(sa, gs))
        assert fsm.state == BrainState.EXPLORING

        # Force the pending transition to be in the past
        fsm._pending_transition = (BrainState.COMBAT, time.time() - 1.0)

        # Second tick: delay expired, should transition
        asyncio.run(fsm.tick(sa, gs))
        assert fsm.state == BrainState.COMBAT

    def test_pending_cancelled_if_situation_changes(self, make_awareness):
        cfg = HumanizationConfig.from_skill_level(3)
        fsm, deps = _make_fsm(humanize_config=cfg)
        deps["nav_behavior"].tick_exploring = AsyncMock()
        sa = make_awareness(under_attack=True, enemies_visible=1)
        gs = MagicMock()

        # First tick: pending COMBAT
        deps["arbiter"].evaluate.return_value = BrainState.COMBAT
        asyncio.run(fsm.tick(sa, gs))
        assert fsm._pending_transition is not None
        assert fsm._pending_transition[0] == BrainState.COMBAT

        # Second tick: situation changed to STUCK
        deps["arbiter"].evaluate.return_value = BrainState.STUCK
        asyncio.run(fsm.tick(sa, gs))
        # Pending should be cancelled (different target)
        # State should still be EXPLORING
        assert fsm.state == BrainState.EXPLORING

    def test_pending_cleared_when_state_matches_current(self, make_awareness):
        cfg = HumanizationConfig.from_skill_level(3)
        fsm, deps = _make_fsm(humanize_config=cfg)
        deps["nav_behavior"].tick_exploring = AsyncMock()
        sa = make_awareness()
        gs = MagicMock()

        # Manually set a pending transition
        fsm._pending_transition = (BrainState.COMBAT, time.time() + 10.0)

        # Arbiter says stay in EXPLORING
        deps["arbiter"].evaluate.return_value = BrainState.EXPLORING
        asyncio.run(fsm.tick(sa, gs))

        # Pending should be cleared since new_state == current state
        assert fsm._pending_transition is None


class TestDEADNeverDelayed:
    """CRITICAL: DEAD state transitions are NEVER delayed."""

    def test_dead_delay_is_zero(self):
        cfg = HumanizationConfig.from_skill_level(1)  # Worst skill
        fsm, _ = _make_fsm(humanize_config=cfg)
        delay = fsm._sample_reaction_delay(BrainState.DEAD, BrainState.EXPLORING)
        assert delay == 0.0

    def test_dead_transition_immediate_with_config(self, make_awareness):
        cfg = HumanizationConfig.from_skill_level(1)
        fsm, deps = _make_fsm(humanize_config=cfg)
        deps["arbiter"].evaluate.return_value = BrainState.DEAD
        deps["death_handler"].tick = AsyncMock()
        sa = make_awareness(is_alive=False)
        gs = MagicMock()

        asyncio.run(fsm.tick(sa, gs))

        # DEAD must execute immediately, no pending
        assert fsm.state == BrainState.DEAD
        assert fsm._pending_transition is None


class TestSurpriseBonus:
    """COMBAT entry from non-combat state adds surprise bonus."""

    def test_surprise_bonus_from_exploring(self):
        cfg = HumanizationConfig.from_skill_level(3)
        fsm, _ = _make_fsm(humanize_config=cfg)
        # Sample many times to verify surprise bonus is included
        delays = [
            fsm._sample_reaction_delay(BrainState.COMBAT, BrainState.EXPLORING)
            for _ in range(100)
        ]
        # With surprise bonus, minimum delay should be >= reaction_time_min
        # (surprise bonus is always positive)
        assert all(d >= cfg.reaction_time_min for d in delays)
        # Average should be above reaction_time average (bonus adds on top)
        avg = sum(delays) / len(delays)
        reaction_avg = (cfg.reaction_time_min + cfg.reaction_time_max) / 2
        assert avg > reaction_avg  # surprise bonus pushes it higher

    def test_no_surprise_from_combat_to_combat(self):
        cfg = HumanizationConfig.from_skill_level(3)
        fsm, _ = _make_fsm(humanize_config=cfg)
        # COMBAT -> COMBAT should NOT have surprise bonus
        delays_combat = [
            fsm._sample_reaction_delay(BrainState.COMBAT, BrainState.COMBAT)
            for _ in range(100)
        ]
        delays_exploring = [
            fsm._sample_reaction_delay(BrainState.COMBAT, BrainState.EXPLORING)
            for _ in range(100)
        ]
        # Average from combat should be less than from exploring (no bonus)
        avg_combat = sum(delays_combat) / len(delays_combat)
        avg_exploring = sum(delays_exploring) / len(delays_exploring)
        assert avg_combat < avg_exploring


class TestHesitationDelay:
    """Hesitation delay is added on top of reaction time."""

    def test_hesitation_included_in_delay(self):
        cfg = HumanizationConfig.from_skill_level(3)
        fsm, _ = _make_fsm(humanize_config=cfg)
        delays = [
            fsm._sample_reaction_delay(BrainState.NAVIGATING, BrainState.EXPLORING)
            for _ in range(100)
        ]
        # Total delay should be >= reaction_time_min + hesitation_min
        min_possible = cfg.reaction_time_min + cfg.hesitation_min
        avg = sum(delays) / len(delays)
        assert avg >= min_possible
