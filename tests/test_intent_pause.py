"""Pause-to-assess timing tests (Phase 10-02).

These tests use a PauseGateHarness that mirrors ItemTour's pause-gate logic
in isolation. The harness is byte-equivalent to the gate code in
item_tour._on_state and _apply_intent_transition. If the real ItemTour
implementation drifts, the harness must be updated in the same commit.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from openarena_perception.models import Intent, IntentStatus, MacroIntent


class PauseGateHarness:
    """Minimal stand-in that mirrors ItemTour's pause gate behavior."""

    def __init__(self, pause_duration: float):
        self._intent_pause_until = 0.0
        self._intent_pause_duration = pause_duration
        self._threat_flag = False
        self.release_all_calls = 0
        # Fake nav + gs
        self.nav_is_stuck = False
        self.health = 100
        # Current intent for status tracking
        self.current_intent = Intent(
            macro=MacroIntent.IDLE, sub="", description="",
            started_at=0.0, status=IntentStatus.EXECUTING,
        )
        self.last_paused = False

    @property
    def threat_flag(self) -> bool:
        return self._threat_flag

    def release_all(self):
        self.release_all_calls += 1

    def open_pause(self, now: float):
        """Equivalent to a macro transition firing in ItemTour."""
        if not self.threat_flag:
            self._intent_pause_until = now + self._intent_pause_duration
            self.current_intent = replace(self.current_intent,
                                          status=IntentStatus.PLANNING)
            self.release_all()

    def tick(self, now: float) -> bool:
        """Returns True if the tick was paused (gate returned early)."""
        if now < self._intent_pause_until:
            health_ok = self.health is None or self.health > 0
            if not self.threat_flag and not self.nav_is_stuck and health_ok:
                self.last_paused = True
                return True
            # Emergency break-out
            self._intent_pause_until = 0.0
            if self.current_intent.status == IntentStatus.PLANNING:
                self.current_intent = replace(
                    self.current_intent, status=IntentStatus.EXECUTING
                )
        self.last_paused = False
        return False


def test_pause_opens_and_respects_window():
    h = PauseGateHarness(pause_duration=0.3)
    h.open_pause(now=1000.0)
    assert h._intent_pause_until == pytest.approx(1000.3)
    assert h.release_all_calls == 1
    # Within window → paused
    assert h.tick(now=1000.1) is True
    assert h.tick(now=1000.2) is True
    # release_all called only once on entry (not every tick)
    assert h.release_all_calls == 1


def test_pause_clears_after_window():
    h = PauseGateHarness(pause_duration=0.3)
    h.open_pause(now=1000.0)
    assert h.tick(now=1000.35) is False  # past window
    assert h.tick(now=1000.4) is False


def test_pause_skipped_under_threat():
    h = PauseGateHarness(pause_duration=0.3)
    h._threat_flag = True
    h.open_pause(now=1000.0)
    assert h._intent_pause_until == 0.0   # never set
    assert h.release_all_calls == 0


def test_pause_broken_by_threat_mid_window():
    h = PauseGateHarness(pause_duration=0.3)
    h.open_pause(now=1000.0)
    assert h.tick(now=1000.1) is True
    h._threat_flag = True
    assert h.tick(now=1000.15) is False   # threat breaks out
    assert h._intent_pause_until == 0.0


def test_pause_broken_by_death():
    h = PauseGateHarness(pause_duration=0.3)
    h.open_pause(now=1000.0)
    h.health = 0
    assert h.tick(now=1000.1) is False    # death reflex fires
    assert h._intent_pause_until == 0.0


def test_pause_broken_by_stuck():
    h = PauseGateHarness(pause_duration=0.3)
    h.open_pause(now=1000.0)
    h.nav_is_stuck = True
    assert h.tick(now=1000.1) is False    # stuck reflex fires
    assert h._intent_pause_until == 0.0


def test_pause_status_promoted_on_breakout():
    h = PauseGateHarness(pause_duration=0.3)
    h.open_pause(now=1000.0)
    assert h.current_intent.status == IntentStatus.PLANNING
    h.health = 0
    h.tick(now=1000.1)   # emergency
    assert h.current_intent.status == IntentStatus.EXECUTING
