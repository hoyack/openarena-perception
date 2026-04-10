"""Tests for the pure-function intent transition detector (Phase 10)."""
from __future__ import annotations

from openarena_perception.intent_transitions import (
    TransitionSignals,
    detect_intent_transition,
)
from openarena_perception.models import MacroIntent
from openarena_perception.settings import BotSettings


def _base_signals(**overrides) -> TransitionSignals:
    s = TransitionSignals(
        now=1000.0,
        health=100,
        was_alive_prev_tick=True,
        prev_macro=MacroIntent.TOURING,
        prev_sub="heading to item_health_mega",
        route_target_name="item_health_mega",
    )
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def test_death_triggers_respawning():
    s = _base_signals(health=0)
    out = detect_intent_transition(s)
    assert out is not None
    assert out.macro == MacroIntent.RESPAWNING


def test_respawn_triggers_touring():
    s = _base_signals(
        was_alive_prev_tick=False, health=100, prev_macro=MacroIntent.RESPAWNING,
        prev_sub="waiting for respawn",
    )
    out = detect_intent_transition(s)
    assert out is not None
    assert out.macro == MacroIntent.TOURING
    assert "respawn" in out.sub.lower()


def test_nav_stuck_triggers_recovering():
    s = _base_signals(nav_is_stuck=True)
    out = detect_intent_transition(s)
    assert out is not None
    assert out.macro == MacroIntent.RECOVERING_STUCK


def test_stuck_edge_trigger_no_repeat():
    """Pitfall 3: already in RECOVERING_STUCK -> no new transition."""
    s = _base_signals(
        nav_is_stuck=True,
        prev_macro=MacroIntent.RECOVERING_STUCK,
        prev_sub="navigator stuck",
    )
    assert detect_intent_transition(s) is None


def test_stuck_edge_trigger_no_repeat_twice():
    """Calling twice in a row with same stuck state produces None both times."""
    s = _base_signals(
        nav_is_stuck=True,
        prev_macro=MacroIntent.RECOVERING_STUCK,
        prev_sub="navigator stuck",
    )
    assert detect_intent_transition(s) is None
    assert detect_intent_transition(s) is None


def test_pin_escalation_beats_wall_halt():
    s = _base_signals(halt_reason="visual_pin", pinned=True, pin_escalated=True)
    out = detect_intent_transition(s)
    assert out is not None
    assert out.macro == MacroIntent.RECOVERING_STUCK


def test_wall_halt_triggers_avoiding_wall():
    s = _base_signals(halt_reason="wall_ahead")
    out = detect_intent_transition(s)
    assert out is not None
    assert out.macro == MacroIntent.AVOIDING_WALL
    assert "wall_ahead" in out.sub


def test_advisor_hazard_triggers_reassessing():
    s = _base_signals(advisor_hazard=True, advisor_warning="stairs ahead")
    out = detect_intent_transition(s)
    assert out is not None
    assert out.macro == MacroIntent.REASSESSING_POSITION


def test_stair_climb_triggers_climbing():
    s = _base_signals(nav_is_climbing_stairs=True)
    out = detect_intent_transition(s)
    assert out is not None
    assert out.macro == MacroIntent.CLIMBING_STAIRS


def test_stair_climb_ends_reverts_to_touring():
    s = _base_signals(
        nav_is_climbing_stairs=False,
        prev_macro=MacroIntent.CLIMBING_STAIRS,
        prev_sub="climbing",
    )
    out = detect_intent_transition(s)
    assert out is not None
    assert out.macro == MacroIntent.TOURING


def test_route_advance_is_sub_only():
    s = _base_signals(
        route_target_name="item_quad",
        prev_sub="heading to item_health_mega",
    )
    out = detect_intent_transition(s)
    assert out is not None
    assert out.macro == MacroIntent.TOURING
    assert "item_quad" in out.sub
    # Macro unchanged — caller can detect this to skip pause
    assert out.macro == MacroIntent.TOURING


def test_no_transition_when_prev_already_matches():
    s = _base_signals(
        route_target_name="item_health_mega",
        prev_sub="heading to item_health_mega",
    )
    assert detect_intent_transition(s) is None


# -- Navigator.is_climbing_stairs property ----------------------------


def test_navigator_is_climbing_stairs_missing_attr():
    class FakeNav:
        pass
    from openarena_perception.navigation.navigator import Navigator
    # Use getattr semantics by borrowing the property from Navigator
    f = FakeNav()
    assert Navigator.is_climbing_stairs.fget(f) is False  # type: ignore[arg-type]


def test_navigator_is_climbing_stairs_false():
    class FakeNav:
        _stair_climb_active = False
    from openarena_perception.navigation.navigator import Navigator
    f = FakeNav()
    assert Navigator.is_climbing_stairs.fget(f) is False  # type: ignore[arg-type]


def test_navigator_is_climbing_stairs_true():
    class FakeNav:
        _stair_climb_active = True
    from openarena_perception.navigation.navigator import Navigator
    f = FakeNav()
    assert Navigator.is_climbing_stairs.fget(f) is True  # type: ignore[arg-type]


# -- Settings.intent_pause_ms -----------------------------------------


def _make_settings(**env):
    # Bypass the lru_cache singleton for test isolation
    return BotSettings(**env)


def test_intent_pause_ms_default(monkeypatch):
    monkeypatch.delenv("OA_INTENT_PAUSE_MS", raising=False)
    s = BotSettings()
    assert s.intent_pause_ms == 300


def test_intent_pause_ms_custom(monkeypatch):
    monkeypatch.setenv("OA_INTENT_PAUSE_MS", "500")
    s = BotSettings()
    assert s.intent_pause_ms == 500


def test_intent_pause_ms_clamped_negative(monkeypatch):
    monkeypatch.setenv("OA_INTENT_PAUSE_MS", "-10")
    s = BotSettings()
    assert s.intent_pause_ms == 0


def test_intent_pause_ms_clamped_high(monkeypatch):
    monkeypatch.setenv("OA_INTENT_PAUSE_MS", "9999")
    s = BotSettings()
    assert s.intent_pause_ms == 5000


def test_intent_pause_ms_invalid_fallback(monkeypatch):
    monkeypatch.setenv("OA_INTENT_PAUSE_MS", "abc")
    s = BotSettings()
    assert s.intent_pause_ms == 300
