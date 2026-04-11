"""Centralized HUD JSON schema and atomic writer for OpenArena Perception.

One-way contract: tour / strategic_brain -> HUD file -> open_perception.py reader.
The HUD reader never deserializes back into typed objects -- it treats the JSON
as a plain dict with .get() lookups. Do not rely on tuple identity surviving
the round-trip (see Pitfall 8 in 10-RESEARCH.md).
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

log = logging.getLogger("hud_schema")

# Anchor paths to the project root (this file lives at
# <root>/openarena_perception/hud_schema.py, so parents[1] is the root).
# This avoids the cwd trap flagged in Research Pitfall 5.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
TMP_DIR: Path = PROJECT_ROOT / "tmp"
LOG_DIR: Path = PROJECT_ROOT / "logs"
STATE_FILE: Path = TMP_DIR / "oa_hud_state.json"


def ensure_runtime_dirs() -> None:
    """Create tmp/ and logs/ under the project root if they do not exist.

    Safe to call repeatedly; idempotent. Must be called before write_hud_state().
    """
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def build_hud_payload(
    *,
    sa: Any = None,
    gs: Any = None,
    map_name: str = "",
    brain_state: str | None = None,
    nav: Any = None,
    learned_map: Any = None,
    context: Any = None,
    is_paused_for_assess: bool = False,
    threat_flag: bool = False,
    stair_climb_state: str | None = None,
    swim_edge_state: str | None = None,
    advisor_last_thought: str | None = None,
    last_replan_steps: Any = None,
    tick_rate_fps: float | None = None,
    frame_lag_ms: float | None = None,
    nav_current_step_area: int | None = None,
    extras: Mapping[str, Any] | None = None,
) -> dict:
    """Build the HUD JSON payload as a plain dict.

    Phase 10-01: this function emits the EXISTING superset schema used by
    item_tour._export_hud and strategic_brain._export_hud. No intent fields
    are added here -- Plan 10-02 will extend this function with context
    support.

    All arguments are optional. Missing inputs produce missing keys, which the
    HUD reader tolerates via .get() with defaults. Deques in `extras` MUST be
    pre-converted to lists by the caller (see Pitfall 7).

    Arguments:
        sa: Optional SituationalAwareness-like object. If provided, reads
            .health, .armor, .ammo, .weapon, .pos, .yaw.
        gs: Optional game state. If provided, falls back to its fields when
            sa is missing values.
        map_name: Human-readable map name for the HUD.
        brain_state: Optional string (e.g., "NAVIGATING", "TOURING").
        nav: Optional navigator with .route, .current_area, etc. Currently
            unused by the base payload; reserved for Plan 10-02.
        learned_map: Optional learned map with get_minimap() or similar.
            Passed through verbatim to the "learned_map" key if truthy.
        extras: Additional key/value pairs merged into the payload last
            (overriding any earlier keys). Callers use this to inject
            per-writer fields like route_idx, items_collected, advisor_stats.

    Returns:
        dict suitable for json.dump().
    """
    import time

    now = time.time()
    payload: dict = {
        "timestamp": now,
        "map_name": map_name,
    }
    if brain_state is not None:
        payload["brain_state"] = brain_state

    # Player state from sa (preferred) or gs (fallback). Manual dict build
    # avoids dataclasses.asdict() cost (Phase 06 convention).
    if sa is not None:
        payload["health"] = getattr(sa, "health", None)
        payload["armor"] = getattr(sa, "armor", None)
        payload["ammo"] = getattr(sa, "ammo", None)
        payload["weapon"] = getattr(sa, "weapon", None)
        pos = getattr(sa, "pos", None)
        if pos is not None:
            payload["pos"] = list(pos)
        yaw = getattr(sa, "yaw", None)
        if yaw is not None:
            payload["yaw"] = float(yaw)
    if gs is not None:
        payload.setdefault("health", getattr(gs, "health", None))
        payload.setdefault("armor", getattr(gs, "armor", None))
        payload.setdefault("ammo", getattr(gs, "ammo", None))
        payload.setdefault("weapon", getattr(gs, "weapon", None))

    if learned_map is not None:
        # Passed through as-is; the caller is responsible for whatever
        # serialization shape learned_map uses (mirrors current behavior).
        payload["learned_map"] = learned_map

    # Phase 10: intent context (deques converted to lists per Pitfall 7)
    if context is not None:
        ci = context.current_intent
        payload["intent"] = {
            "macro": str(ci.macro),
            "sub": ci.sub,
            "description": ci.description,
            "started_at": ci.started_at,
            "duration_s": now - ci.started_at,
            "target": list(ci.target) if ci.target is not None else None,
            "target_area": ci.target_area,
            "status": str(ci.status),
        }
        payload["intent_history"] = [
            {
                "macro": str(h.macro),
                "sub": h.sub,
                "description": h.description,
                "started_at": h.started_at,
                "duration_s": now - h.started_at,
                "ended_at": h.started_at,  # HUD only needs relative ordering
            }
            for h in context.intent_history
        ]
        payload["problem_history"] = [
            {
                "kind": p.kind,
                "location": list(p.location),
                "timestamp": p.timestamp,
                "description": p.description,
            }
            for p in context.problem_history
        ]
        payload["area_history"] = list(context.current_area_history)
        cur_step, total_steps = context.path_progress
        payload["path_progress"] = {
            "current_step": cur_step,
            "total_steps": total_steps,
        }
        payload["tick_count"] = context.tick_count

    payload["is_paused_for_assess"] = bool(is_paused_for_assess)
    payload["threat_flag"] = bool(threat_flag)

    # Phase 12-01: verbose telemetry fields. Each key is emitted only when
    # the corresponding kwarg is non-None so existing callers that don't pass
    # these stay byte-for-byte backward-compatible (no new keys appear).
    if stair_climb_state is not None:
        payload["stair_climb_state"] = stair_climb_state
    if swim_edge_state is not None:
        payload["swim_edge_state"] = swim_edge_state
    if advisor_last_thought is not None:
        payload["advisor_last_thought"] = advisor_last_thought
    if last_replan_steps is not None:
        # Normalize deque -> list so json.dump is happy (Pitfall 7).
        payload["last_replan_steps"] = list(last_replan_steps)
    if tick_rate_fps is not None:
        payload["tick_rate_fps"] = float(tick_rate_fps)
    if frame_lag_ms is not None:
        payload["frame_lag_ms"] = float(frame_lag_ms)
    if nav_current_step_area is not None:
        payload["nav_current_step_area"] = int(nav_current_step_area)

    if extras:
        payload.update(extras)

    return payload


def write_hud_state(payload: dict, state_file: Path = STATE_FILE) -> None:
    """Atomically write the HUD payload to disk.

    Uses the tmp + os.replace pattern (existing project convention, see
    item_tour.py:1102-1105). Creates parent directories as needed.

    Raises OSError on write failure (caller decides whether to swallow).
    """
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_file.with_suffix(state_file.suffix + ".tmp")
    try:
        with open(tmp_path, "w") as f:
            json.dump(payload, f)
        os.replace(tmp_path, state_file)
    except OSError as exc:
        log.warning("Failed to write HUD state to %s: %s", state_file, exc)
        raise
