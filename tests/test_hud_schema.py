"""Tests for openarena_perception.hud_schema (Phase 10-01)."""
from __future__ import annotations

import json
from collections import deque

import pytest

from openarena_perception import hud_schema
from openarena_perception.hud_schema import (
    LOG_DIR,
    PROJECT_ROOT,
    STATE_FILE,
    TMP_DIR,
    build_hud_payload,
    ensure_runtime_dirs,
    write_hud_state,
)


def test_state_file_is_anchored_to_project_root():
    """STATE_FILE must resolve under PROJECT_ROOT/tmp/, not /tmp/ and not cwd."""
    assert STATE_FILE == PROJECT_ROOT / "tmp" / "oa_hud_state.json"
    # Prove it is NOT the old absolute path
    assert str(STATE_FILE) != "/tmp/oa_hud_state.json"
    # Project root is <repo>/, this file lives in <repo>/openarena_perception/
    assert (PROJECT_ROOT / "openarena_perception" / "hud_schema.py").is_file()


def test_tmp_and_log_dirs_anchored():
    assert TMP_DIR == PROJECT_ROOT / "tmp"
    assert LOG_DIR == PROJECT_ROOT / "logs"


def test_ensure_runtime_dirs_creates_missing_dirs(tmp_path, monkeypatch):
    fake_tmp = tmp_path / "tmp"
    fake_log = tmp_path / "logs"
    monkeypatch.setattr(hud_schema, "TMP_DIR", fake_tmp)
    monkeypatch.setattr(hud_schema, "LOG_DIR", fake_log)
    assert not fake_tmp.exists()
    assert not fake_log.exists()
    ensure_runtime_dirs()
    assert fake_tmp.is_dir()
    assert fake_log.is_dir()
    # Idempotent
    ensure_runtime_dirs()
    assert fake_tmp.is_dir()


def test_build_payload_minimal_has_timestamp_and_map():
    p = build_hud_payload(map_name="q3dm17")
    assert "timestamp" in p
    assert isinstance(p["timestamp"], float)
    assert p["map_name"] == "q3dm17"


def test_build_payload_with_sa_like_object():
    class FakeSA:
        health = 100
        armor = 50
        ammo = 40
        weapon = "rocket"
        pos = (1.0, 2.0, 3.0)
        yaw = 90.0

    p = build_hud_payload(sa=FakeSA(), map_name="q3dm1")
    assert p["health"] == 100
    assert p["armor"] == 50
    assert p["ammo"] == 40
    assert p["weapon"] == "rocket"
    assert p["pos"] == [1.0, 2.0, 3.0]   # list, not tuple
    assert p["yaw"] == 90.0


def test_build_payload_extras_override_and_merge():
    p = build_hud_payload(
        map_name="q3dm1",
        extras={"route_idx": 5, "route_len": 13, "proactive_halts": 2},
    )
    assert p["route_idx"] == 5
    assert p["route_len"] == 13
    assert p["proactive_halts"] == 2


def test_build_payload_deque_must_be_converted_by_caller(tmp_path):
    """Pitfall 7: deques are not JSON serializable. The caller must convert.
    build_hud_payload does not auto-convert -- it trusts the caller. This test
    documents the contract: a raw deque in extras will fail json.dump."""
    p = build_hud_payload(map_name="x", extras={"history": deque([1, 2, 3])})
    # The payload holds the deque verbatim
    assert isinstance(p["history"], deque)
    # And json.dump blows up on it -- proving the contract
    out = tmp_path / "x.json"
    with pytest.raises(TypeError):
        with open(out, "w") as f:
            json.dump(p, f)


# ── Phase 12-01: Verbose telemetry kwargs ───────────────────────────


def test_build_payload_stair_climb_state_roundtrip():
    p = build_hud_payload(map_name="q3dm1", stair_climb_state="climbing target_area=42")
    blob = json.dumps(p)
    restored = json.loads(blob)
    assert restored["stair_climb_state"] == "climbing target_area=42"


def test_build_payload_swim_edge_state_roundtrip():
    p = build_hud_payload(map_name="q3dm1", swim_edge_state="traversing to area 7")
    restored = json.loads(json.dumps(p))
    assert restored["swim_edge_state"] == "traversing to area 7"


def test_build_payload_advisor_last_thought_roundtrip():
    p = build_hud_payload(map_name="q3dm1", advisor_last_thought="watch the lava")
    restored = json.loads(json.dumps(p))
    assert restored["advisor_last_thought"] == "watch the lava"


def test_build_payload_last_replan_steps_accepts_deque():
    dq = deque([3, 4, 6], maxlen=3)
    p = build_hud_payload(map_name="q3dm1", last_replan_steps=dq)
    # Must serialize cleanly -- Pitfall 7 handled inside build_hud_payload
    blob = json.dumps(p)
    restored = json.loads(blob)
    assert restored["last_replan_steps"] == [3, 4, 6]


def test_build_payload_tick_rate_fps_roundtrip():
    p = build_hud_payload(map_name="q3dm1", tick_rate_fps=12.5)
    restored = json.loads(json.dumps(p))
    assert restored["tick_rate_fps"] == 12.5


def test_build_payload_frame_lag_ms_roundtrip():
    p = build_hud_payload(map_name="q3dm1", frame_lag_ms=42.0)
    restored = json.loads(json.dumps(p))
    assert restored["frame_lag_ms"] == 42.0


def test_build_payload_nav_current_step_area_roundtrip():
    p = build_hud_payload(map_name="q3dm1", nav_current_step_area=299)
    restored = json.loads(json.dumps(p))
    assert restored["nav_current_step_area"] == 299


def test_build_payload_omits_verbose_keys_when_not_passed():
    """Backward-compat: constructing with only map_name must not emit any new keys."""
    p = build_hud_payload(map_name="x")
    for k in (
        "stair_climb_state",
        "swim_edge_state",
        "advisor_last_thought",
        "last_replan_steps",
        "tick_rate_fps",
        "frame_lag_ms",
        "nav_current_step_area",
    ):
        assert k not in p, f"unexpected verbose key {k!r} in backward-compat payload"


def test_export_hud_populates_verbose_fields():
    """Integration: item_tour-style _export_hud flow fills all 7 verbose keys.

    Rather than instantiate the full ItemTour (which requires a running game
    and window capture), this test reconstructs the minimal flow used by
    item_tour._export_hud: a tracked replan callback appends to a deque, then
    build_hud_payload is invoked with all the verbose kwargs sourced from
    mock nav/advisor/loop objects. Asserts every verbose key is present in
    the output with the expected value.
    """
    from unittest.mock import MagicMock

    # Mock navigator exposing the Phase 12-01 API
    nav = MagicMock()
    nav.is_climbing_stairs = True
    nav.current_step_area = 42
    nav.swim_edge_state_str = MagicMock(return_value="traversing to area 9")

    # Mock advisor
    advisor = MagicMock()
    advisor.current_narrative = MagicMock(return_value="watch the lava pit ahead please")

    # Mock loop
    loop_obj = MagicMock()
    loop_obj.avg_fps = 12.5
    loop_obj.last_tick_ms = 42.0

    # Simulate item_tour's replan tracking
    recent = deque(maxlen=3)
    def on_replan_tracked(n: int) -> None:
        recent.append(int(n))
    on_replan_tracked(3)
    on_replan_tracked(4)
    on_replan_tracked(6)

    # Now mirror item_tour._export_hud's verbose block
    stair_climb_state = (
        f"climbing target_area={nav.current_step_area}"
        if nav.is_climbing_stairs and nav.current_step_area is not None
        else "idle"
    )
    swim_edge_state = nav.swim_edge_state_str() or "clear"
    narrative = advisor.current_narrative()
    advisor_thought = narrative[:80] if narrative else None
    tick_rate = loop_obj.avg_fps
    frame_lag = loop_obj.last_tick_ms
    replan_list = list(recent) if recent else None

    payload = build_hud_payload(
        map_name="q3dm1",
        stair_climb_state=stair_climb_state,
        swim_edge_state=swim_edge_state,
        advisor_last_thought=advisor_thought,
        last_replan_steps=replan_list,
        tick_rate_fps=tick_rate,
        frame_lag_ms=frame_lag,
        nav_current_step_area=nav.current_step_area,
    )

    # Must be JSON-serializable end to end
    restored = json.loads(json.dumps(payload))

    assert restored["stair_climb_state"] == "climbing target_area=42"
    assert restored["swim_edge_state"] == "traversing to area 9"
    assert restored["advisor_last_thought"] == "watch the lava pit ahead please"
    assert restored["last_replan_steps"] == [3, 4, 6]
    assert restored["tick_rate_fps"] == 12.5
    assert restored["frame_lag_ms"] == 42.0
    assert restored["nav_current_step_area"] == 42


def test_build_payload_explicit_none_equivalent_to_omitted():
    """Passing None explicitly should behave the same as omitting the kwarg."""
    p = build_hud_payload(
        map_name="x",
        stair_climb_state=None,
        swim_edge_state=None,
        advisor_last_thought=None,
        last_replan_steps=None,
        tick_rate_fps=None,
        frame_lag_ms=None,
        nav_current_step_area=None,
    )
    for k in (
        "stair_climb_state",
        "swim_edge_state",
        "advisor_last_thought",
        "last_replan_steps",
        "tick_rate_fps",
        "frame_lag_ms",
        "nav_current_step_area",
    ):
        assert k not in p


def test_write_hud_state_atomic(tmp_path):
    """write_hud_state uses tmp + os.replace; no .tmp left behind on success."""
    target = tmp_path / "out.json"
    write_hud_state({"hello": "world"}, state_file=target)
    assert target.is_file()
    assert json.loads(target.read_text()) == {"hello": "world"}
    assert not (tmp_path / "out.json.tmp").exists()


def test_write_hud_state_creates_parent_dir(tmp_path):
    target = tmp_path / "sub" / "dir" / "out.json"
    assert not target.parent.exists()
    write_hud_state({"k": 1}, state_file=target)
    assert target.is_file()


# ── Phase 10-02: BotContext extension tests ─────────────────────────


from openarena_perception.models import (  # noqa: E402
    BotContext,
    Intent,
    IntentStatus,
    MacroIntent,
    Problem,
)


def _ctx() -> BotContext:
    ci = Intent(
        macro=MacroIntent.TOURING,
        sub="heading to item_health_mega",
        description="Heading to item_health_mega",
        started_at=1000.0,
        target=(232.0, 1600.0, -112.0),
        status=IntentStatus.EXECUTING,
    )
    ctx = BotContext(current_intent=ci)
    ctx.path_progress = (5, 13)
    ctx.tick_count = 42
    ctx.intent_history.append(Intent(
        macro=MacroIntent.AVOIDING_WALL, sub="strafing right",
        description="", started_at=995.0,
    ))
    ctx.problem_history.append(Problem(
        kind="wall_halt", location=(481.0, 1336.0, -93.0),
        timestamp=994.0, description="vision score=0.89",
    ))
    ctx.current_area_history.extend([299, 259, 285, 304, 325])
    return ctx


def test_build_payload_with_context_includes_intent():
    p = build_hud_payload(context=_ctx(), map_name="q3dm1")
    assert "intent" in p
    assert p["intent"]["macro"] == "TOURING"
    assert p["intent"]["sub"] == "heading to item_health_mega"
    assert p["intent"]["target"] == [232.0, 1600.0, -112.0]
    assert p["intent"]["status"] == "executing"
    assert "duration_s" in p["intent"]


def test_build_payload_intent_history_is_list():
    p = build_hud_payload(context=_ctx(), map_name="q3dm1")
    assert isinstance(p["intent_history"], list)
    assert len(p["intent_history"]) == 1
    assert p["intent_history"][0]["macro"] == "AVOIDING_WALL"


def test_build_payload_problem_history_is_list():
    p = build_hud_payload(context=_ctx(), map_name="q3dm1")
    assert isinstance(p["problem_history"], list)
    assert p["problem_history"][0]["kind"] == "wall_halt"
    assert p["problem_history"][0]["location"] == [481.0, 1336.0, -93.0]


def test_build_payload_area_history_is_list():
    p = build_hud_payload(context=_ctx(), map_name="q3dm1")
    assert p["area_history"] == [299, 259, 285, 304, 325]


def test_build_payload_path_progress():
    p = build_hud_payload(context=_ctx(), map_name="q3dm1")
    assert p["path_progress"] == {"current_step": 5, "total_steps": 13}


def test_build_payload_pause_and_threat_flags():
    p = build_hud_payload(
        context=_ctx(), map_name="q3dm1",
        is_paused_for_assess=True, threat_flag=False,
    )
    assert p["is_paused_for_assess"] is True
    assert p["threat_flag"] is False


def test_build_payload_is_json_serializable_with_context():
    """Pitfall 7: deques must be converted to lists BEFORE json.dump."""
    p = build_hud_payload(context=_ctx(), map_name="q3dm1")
    blob = json.dumps(p)   # must not raise
    restored = json.loads(blob)
    assert restored["intent"]["macro"] == "TOURING"
    assert restored["area_history"] == [299, 259, 285, 304, 325]


def test_build_payload_no_context_still_emits_pause_flags():
    """Without context, the pause/threat flags still appear (default False)."""
    p = build_hud_payload(map_name="q3dm1")
    assert p["is_paused_for_assess"] is False
    assert p["threat_flag"] is False
    assert "intent" not in p


# ── Phase 12-03: end-to-end schema contract test ─────────────────────


def test_contract_build_payload_to_open_perception_load(tmp_path):
    """End-to-end contract: build_hud_payload output must be parseable by
    open_perception.HUDState.load into a HUDState with populated intent
    fields AND the 7 Phase 12-01 verbose telemetry fields.

    open_perception.py is a standalone app at the repo root — not part of
    the openarena_perception package — so we inject the repo root into
    sys.path before importing it. SDL_VIDEODRIVER=dummy keeps pygame
    headless since open_perception imports pygame at module level.
    """
    import os
    import sys as _sys
    from pathlib import Path as _Path
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    repo_root = _Path(__file__).resolve().parents[1]
    if str(repo_root) not in _sys.path:
        _sys.path.insert(0, str(repo_root))

    import open_perception  # noqa: E402

    ctx = _ctx()
    payload = build_hud_payload(
        context=ctx,
        map_name="q3dm1",
        is_paused_for_assess=True,
        threat_flag=False,
        stair_climb_state="climbing target_area=42",
        swim_edge_state="traversing to area 9",
        advisor_last_thought="watch the lava pit ahead",
        last_replan_steps=[3, 4, 6],
        tick_rate_fps=12.5,
        frame_lag_ms=42.0,
        nav_current_step_area=42,
    )

    # Write to a tmp file (item_tour.py does this via hud_schema.write_hud_state).
    state_file = tmp_path / "hud_state.json"
    state_file.write_text(json.dumps(payload))

    # Load via the new Open-Perception HUDState — same construct-then-load
    # pattern as the legacy strategic_hud.HUDState.
    s = open_perception.HUDState().load(state_file)

    # Contract assertions: intent block round-tripped correctly
    assert s.intent, "intent dict should be populated"
    assert s.intent.get("macro") == "TOURING"
    assert s.intent.get("sub") == "heading to item_health_mega"
    assert s.intent.get("status") == "executing"
    assert s.intent.get("target") == [232.0, 1600.0, -112.0]

    # Intent history is a list (Pitfall 7: deque -> list conversion)
    assert isinstance(s.intent_history, list)
    assert len(s.intent_history) == 1
    assert s.intent_history[0].get("macro") == "AVOIDING_WALL"

    # Problem history color-coding relies on the "kind" key
    assert isinstance(s.problem_history, list)
    assert s.problem_history[0].get("kind") == "wall_halt"

    # Path progress drives the progress bar
    assert s.path_progress.get("current_step") == 5
    assert s.path_progress.get("total_steps") == 13

    # Pause flash border and threat badge flags
    assert s.is_paused_for_assess is True
    assert s.threat_flag is False

    # Area history (recent area transitions)
    assert isinstance(s.area_history, list)
    assert s.area_history == [299, 259, 285, 304, 325]

    # Phase 12-01 verbose telemetry fields round-trip through HUDState
    assert s.stair_climb_state == "climbing target_area=42"
    assert s.swim_edge_state == "traversing to area 9"
    assert s.advisor_last_thought == "watch the lava pit ahead"
    assert s.last_replan_steps == [3, 4, 6]
    assert s.tick_rate_fps == 12.5
    assert s.frame_lag_ms == 42.0
    assert s.nav_current_step_area == 42


# ---- Phase 13 Plan 13-05 RP-12: room perception kwargs ----


def test_current_room_kwargs_backward_compat():
    """RP-12: build_hud_payload without new kwargs is byte-identical to Phase 12.1.

    Two calls with identical inputs produce dicts equal (minus timestamp),
    and the new keys are absent.
    """
    p = build_hud_payload(map_name="test")
    assert "current_room_id" not in p
    assert "current_room_items" not in p

    # Byte-stable for identical inputs (strip timestamps which are time.time()).
    p1 = build_hud_payload(
        map_name="test",
        brain_state="NAVIGATING",
        stair_climb_state="climbing",
        tick_rate_fps=12.0,
    )
    p2 = build_hud_payload(
        map_name="test",
        brain_state="NAVIGATING",
        stair_climb_state="climbing",
        tick_rate_fps=12.0,
    )
    # Strip the one inherently-varying key:
    p1.pop("timestamp", None)
    p2.pop("timestamp", None)
    assert p1 == p2
    assert "current_room_id" not in p1
    assert "current_room_items" not in p1


def test_current_room_kwargs_emitted():
    """RP-12: new kwargs, when provided, emit top-level keys."""
    p = build_hud_payload(
        map_name="test",
        current_room_id=7,
        current_room_items=["rl", "mh", "ya"],
    )
    assert p["current_room_id"] == 7
    assert p["current_room_items"] == ["rl", "mh", "ya"]


def test_current_room_kwargs_none_values_absent():
    """RP-12: explicitly passing None for both kwargs still omits the keys."""
    p = build_hud_payload(
        map_name="test", current_room_id=None, current_room_items=None
    )
    assert "current_room_id" not in p
    assert "current_room_items" not in p
