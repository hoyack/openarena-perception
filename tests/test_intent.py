"""Tests for Phase 10 Intent / Problem / BotContext data model."""
from __future__ import annotations

from collections import deque
from dataclasses import FrozenInstanceError, replace

import pytest

from openarena_perception.models import (
    BotContext,
    Intent,
    IntentStatus,
    MacroIntent,
    Problem,
)


def test_macro_intent_is_strenum():
    assert MacroIntent.TOURING == "TOURING"
    assert str(MacroIntent.TOURING) == "TOURING"
    assert f"{MacroIntent.TOURING}" == "TOURING"
    # All 8 members present
    assert {m.name for m in MacroIntent} == {
        "IDLE", "TOURING", "CLIMBING_STAIRS", "AVOIDING_WALL",
        "RECOVERING_STUCK", "REASSESSING_POSITION", "RESPAWNING",
        "PAUSING_TO_ASSESS",
    }


def test_intent_status_values():
    assert IntentStatus.PLANNING == "planning"
    assert IntentStatus.EXECUTING == "executing"
    assert IntentStatus.COMPLETED == "completed"
    assert IntentStatus.FAILED == "failed"


def test_intent_construction_and_frozen():
    i = Intent(
        macro=MacroIntent.TOURING,
        sub="heading to item_health_mega",
        description="Heading",
        started_at=1000.0,
    )
    assert i.status == IntentStatus.EXECUTING
    with pytest.raises(FrozenInstanceError):
        i.macro = MacroIntent.IDLE  # type: ignore[misc]


def test_intent_duration():
    i = Intent(macro=MacroIntent.TOURING, sub="", description="", started_at=1000.0)
    assert i.duration(1005.5) == pytest.approx(5.5)


def test_intent_replace_creates_new():
    i = Intent(macro=MacroIntent.TOURING, sub="a", description="", started_at=0.0)
    j = replace(i, status=IntentStatus.COMPLETED)
    assert j.status == IntentStatus.COMPLETED
    assert i.status == IntentStatus.EXECUTING


def test_problem_construction():
    p = Problem(
        kind="wall_halt",
        location=(1.0, 2.0, 3.0),
        timestamp=100.0,
        description="score 0.89",
    )
    assert p.kind == "wall_halt"
    assert p.location == (1.0, 2.0, 3.0)


def _initial_intent() -> Intent:
    return Intent(macro=MacroIntent.IDLE, sub="", description="", started_at=0.0)


def test_bot_context_defaults():
    ctx = BotContext(current_intent=_initial_intent())
    assert ctx.tick_count == 0
    assert ctx.path_progress == (0, 0)
    assert isinstance(ctx.intent_history, deque)
    assert ctx.intent_history.maxlen == 5
    assert ctx.problem_history.maxlen == 5
    assert ctx.current_area_history.maxlen == 10


def test_bot_context_push_intent_evicts():
    ctx = BotContext(current_intent=_initial_intent())
    for i in range(7):
        new = Intent(
            macro=MacroIntent.TOURING,
            sub=f"s{i}",
            description="",
            started_at=float(i),
        )
        ctx.push_intent(new)
    assert ctx.current_intent.sub == "s6"
    assert len(ctx.intent_history) == 5  # evicted oldest
    subs = [i.sub for i in ctx.intent_history]
    assert subs == ["s1", "s2", "s3", "s4", "s5"]


def test_bot_context_is_not_frozen():
    """Pitfall 2: BotContext holds mutable deques; must NOT be frozen."""
    ctx = BotContext(current_intent=_initial_intent())
    new = Intent(
        macro=MacroIntent.TOURING, sub="x", description="", started_at=1.0
    )
    ctx.current_intent = new
    assert ctx.current_intent is new


def test_record_area_dedupes():
    ctx = BotContext(current_intent=_initial_intent())
    ctx.record_area(10)
    ctx.record_area(10)  # same, should not dupe
    ctx.record_area(11)
    assert list(ctx.current_area_history) == [10, 11]


def test_record_area_ignores_nonpositive():
    ctx = BotContext(current_intent=_initial_intent())
    ctx.record_area(0)
    ctx.record_area(-5)
    assert len(ctx.current_area_history) == 0


def test_record_problem_appends_and_evicts():
    ctx = BotContext(current_intent=_initial_intent())
    for i in range(7):
        ctx.record_problem(Problem(
            kind="stuck",
            location=(float(i), 0.0, 0.0),
            timestamp=float(i),
            description=f"p{i}",
        ))
    assert len(ctx.problem_history) == 5
    descs = [p.description for p in ctx.problem_history]
    assert descs == ["p2", "p3", "p4", "p5", "p6"]
