---
phase: 12-open-perception-ui
plan: 01
subsystem: hud-schema
tags: [hud, telemetry, navigator, perception-loop, item-tour]
requires:
  - Phase 10 HUD schema (build_hud_payload) + item_tour._export_hud pipeline
  - Phase 10 Navigator.is_climbing_stairs
  - Phase 11 SpatialAdvisor.current_narrative()
provides:
  - build_hud_payload 7 new optional kwargs (verbose telemetry)
  - Navigator.on_replan callback + current_step_area property
  - Navigator.note_swim_edge + swim_edge_state_str (transition-only decay)
  - PerceptionLoop.last_tick_ms public property
  - item_tour._recent_replan_steps deque(maxlen=3)
affects:
  - openarena_perception/hud_schema.py
  - openarena_perception/navigation/navigator.py
  - openarena_perception/loop.py
  - item_tour.py
  - tests/test_hud_schema.py
  - tests/test_navigation.py
tech-stack:
  added: []
  patterns:
    - "deque->list normalization inside build_hud_payload (Pitfall 7)"
    - "transition-only timestamp set for swim-edge state (fixes Pitfall 8 per-tick firing)"
    - "re-entrancy-guarded callback via _in_replan_callback bool"
    - "post-hoc Navigator hook installation from item_tour (mirrors existing _on_area_transition assignment)"
key-files:
  created: []
  modified:
    - openarena_perception/hud_schema.py
    - openarena_perception/navigation/navigator.py
    - openarena_perception/loop.py
    - item_tour.py
    - tests/test_hud_schema.py
    - tests/test_navigation.py
decisions:
  - Navigator replan hook installed post-hoc via attribute assignment, mirroring _on_area_transition pattern, rather than threading on_replan through ReactiveAgent.__init__
  - note_swim_edge is a public method (not just inline mutation) so tests can exercise transition-only behaviour without driving follow_path's reach machinery
  - last_replan_steps kwarg accepts any iterable and normalizes to list inside build_hud_payload; callers may pass deque directly
metrics:
  duration: ~18min
  tasks: 3
  new_tests: 17
  total_tests_passing: 700
  files_modified: 6
requirements:
  - OP-01
  - OP-02
  - OP-03
completed: 2026-04-11
---

# Phase 12 Plan 01: HUD Schema + Verbose Telemetry Wiring Summary

Shipped pure-data extensions so the upcoming Open-Perception UI (Plans 12-02, 12-03) can assume every verbose field is present in `./tmp/oa_hud_state.json` without any backward-compat breakage.

## Task Breakdown

| Task | Commit | Tests Added | Files |
|------|--------|-------------|-------|
| 1. Extend build_hud_payload (7 kwargs) | 9f723d5 | 8 | hud_schema.py, test_hud_schema.py |
| 2. Navigator replan + swim-edge + last_tick_ms | 87ab69a | 8 | navigator.py, loop.py, test_navigation.py |
| 3. item_tour._export_hud verbose fill + integration test | da25eb6 | 1 | item_tour.py, test_hud_schema.py |

## RESEARCH Audit Results

- **A8 — single replan site:** `grep "self\._path = "` returned exactly two hits in `openarena_perception/navigation/navigator.py`:
  - **Line 121** (`path_to_area`): initial path assignment from a fresh A* run. Not a re-plan, so no hook.
  - **Line 182** (`follow_path`, drift-recovery branch): the actual re-plan site. Hook installed immediately after `self._path = new_path[1:]`.
  Confirmed: only one true re-plan site. A8 assumption holds.

- **A4 — advisor.current_narrative() exists:** confirmed at `openarena_perception/strategy/advisor.py:420-421` returning `self._narrative` as `str`. Wired into `item_tour._export_hud` with a try/except fall-through to `None`.

## Hook Installation Site

Navigator replan hook is fired inside `follow_path`, immediately after the new path is assigned and logged:

```
openarena_perception/navigation/navigator.py:182-188
    self._path = new_path[1:]  # skip current area
    log.info("Re-planned path from area %d: %d -> %d steps", ...)
    target_area = self._path[0]
    # Phase 12-01: fire replan hook, guarded against re-entry.
    if self._on_replan is not None and not self._in_replan_callback:
        self._in_replan_callback = True
        try:
            self._on_replan(len(self._path))
        finally:
            self._in_replan_callback = False
```

Non-re-entrancy guaranteed by the `_in_replan_callback` bool — if the callback itself triggers another `follow_path` call that would re-plan, the hook is skipped on the inner invocation.

## item_tour Integration

Rather than thread `on_replan` through `ReactiveAgent.__init__`, the callback is assigned post-hoc (`self.agent.nav._on_replan = self._on_replan_tracked`) in `ItemTour.__init__`, mirroring the pre-existing `self.agent.nav._on_area_transition = ...` pattern already present at line 290. This keeps `ReactiveAgent` untouched.

Verbose field sources installed in `_export_hud`:

| HUD field | Source |
|-----------|--------|
| `stair_climb_state` | `"climbing target_area={N}"` if `nav.is_climbing_stairs` and `nav.current_step_area is not None`, else `"idle"` |
| `swim_edge_state` | `nav.swim_edge_state_str()` or `"clear"` |
| `advisor_last_thought` | `self.advisor.current_narrative()[:80]` (None-safe) |
| `last_replan_steps` | `list(self._recent_replan_steps)` or None |
| `tick_rate_fps` | `self.loop.avg_fps` (note: attribute is `self.loop`, not `self.perception_loop`) |
| `frame_lag_ms` | `self.loop.last_tick_ms` |
| `nav_current_step_area` | `nav.current_step_area` |

## Test Count Delta

- `tests/test_hud_schema.py`: 19 → 28 (+9; 8 new verbose kwargs + 1 integration `test_export_hud_populates_verbose_fields`)
- `tests/test_navigation.py`: 17 → 25 (+8; 7 Navigator telemetry + 1 PerceptionLoop telemetry)
- **Total new tests: 17**
- **Full regression:** 700 passed in 33.13s (`SDL_VIDEODRIVER=dummy uv run pytest -q`)

## Deviations from Plan

### Rule 3 - Blocking issue auto-fixes

**1. Perception loop attribute is `self.loop`, not `self.perception_loop`**
- **Found during:** Task 3 wiring
- **Issue:** Plan spec referenced `self.perception_loop`; the actual ItemTour attribute is `self.loop` (line 381 of item_tour.py).
- **Fix:** Use `self.loop.avg_fps` / `self.loop.last_tick_ms` directly; hasattr/getattr guards still safe-handle construction ordering.

**2. Test graph area-center stub required for non-reentrancy test**
- **Found during:** Task 2 RED/GREEN cycle
- **Issue:** After the re-plan fires, `follow_path` falls through to the "no reachability edge" branch which calls `self.graph.area_center(target_area)`. MagicMock's default return unpacks as 0 values, not a 3-tuple.
- **Fix:** Added `nav.graph.area_center = MagicMock(return_value=(0.0, 0.0, 0.0))` to the test helper.

**3. Initial `_current_area=99` exceeded 50-area fake graph**
- **Found during:** Task 2 test execution
- **Issue:** `area = self.graph.areas[current]` indexed out of range.
- **Fix:** Set `nav._current_area = 5` (a valid off-path index), updated fake `_astar` return path accordingly.

**4. Untracked `openarena_perception/loop.py` committed in Task 2**
- **Note:** `openarena_perception/loop.py` was previously untracked on disk (no git history). Adding `last_tick_ms` introduced the first commit of the whole file. Not a deviation per se — documented here so anyone reviewing `git log openarena_perception/loop.py` sees the full module appear in 87ab69a.

### Auto-fixed bugs

None — the plan spec matched the existing code exactly for Tasks 1 and 2.

### Auth gates

None.

## Pitfalls Addressed

- **P7 (deque JSON serialization):** `build_hud_payload` normalizes `last_replan_steps` via `list(...)` before emission. Verified by `test_build_payload_last_replan_steps_accepts_deque`.
- **P8 (swim edge fires every tick):** `note_swim_edge` only updates `_last_swim_edge_time` when `target_area` differs from `_last_swim_edge_area`. Verified by `test_navigator_swim_edge_state_set_on_transition_only` with frozen `time.monotonic`.
- **Callback-vs-logging for replan tracking:** chose the callback approach (direct function pointer) instead of a `logging.Handler`, matching the RESEARCH recommendation.

## Backward Compatibility

- All 7 new kwargs are keyword-only with default `None` and only emit keys into the payload dict when non-None.
- `test_build_payload_omits_verbose_keys_when_not_passed` and `test_build_payload_explicit_none_equivalent_to_omitted` enforce the contract.
- Existing `test_contract_build_payload_to_strategic_hud_load` continues to pass (strategic_hud.py still receives the same schema plus optional extras it ignores).

## Self-Check: PASSED

Verified the following after SUMMARY write:
- `openarena_perception/hud_schema.py` — FOUND, contains `stair_climb_state`, `swim_edge_state`, `advisor_last_thought`, `last_replan_steps`, `tick_rate_fps`, `frame_lag_ms`, `nav_current_step_area`
- `openarena_perception/navigation/navigator.py` — FOUND, contains `_on_replan`, `current_step_area`, `note_swim_edge`, `swim_edge_state_str`
- `openarena_perception/loop.py` — FOUND, contains `last_tick_ms`
- `item_tour.py` — FOUND, contains `_on_replan_tracked`, `_recent_replan_steps`, all 7 kwargs passed to `build_hud_payload`
- `tests/test_hud_schema.py` — FOUND, 9 new tests
- `tests/test_navigation.py` — FOUND, 8 new tests
- Commits 9f723d5, 87ab69a, da25eb6 — all FOUND via `git log --oneline`
- Full regression: 700/700 passing
