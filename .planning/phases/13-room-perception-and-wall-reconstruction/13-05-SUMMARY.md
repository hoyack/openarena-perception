---
phase: 13-room-perception-and-wall-reconstruction
plan: 05
subsystem: navigation
tags: [room-perception, learned-map, hud-schema, stats-panel, cv2, point-in-polygon, visit-count]

requires:
  - phase: 13-02
    provides: LearnedMap raycast cloud + schema v3 persistence
  - phase: 13-03
    provides: LineFitter RANSAC + wall merging
  - phase: 13-04
    provides: CornerDetector, RoomInferrer, DoorwayDetector
provides:
  - LearnedMap.fit_rooms() orchestrator running the full pipeline
  - LearnedMap.note_item() routing items into rooms via cv2.pointPolygonTest
  - LearnedMap.current_room_id() with per-tick PIP cache
  - Visit-count debouncer in update() (outside->inside transition only)
  - export_for_hud() surfacing fitted_walls/corners/rooms/doorways/current_room_id/current_room_items
  - Schema v3 save/load of typed Room/Wall/Corner/Doorway entities
  - build_hud_payload() optional current_room_id + current_room_items kwargs (byte-compatible with Phase 12.1)
  - StatsPanel rows 10-11 (room, room_items) at y=612/626 inside the 700px panel
affects: [13-06 minimap current-room highlight, reactive_agent item ingestion]

tech-stack:
  added: []
  patterns:
    - "Per-tick PIP cache keyed off position change (invalidated by update() + fit_rooms())"
    - "Visit-count debouncer via outside->inside transition detection"
    - "Centroid-match room log preservation across refit passes"
    - "Optional HUD kwargs with conditional emit preserves dedup/byte-stable contract"

key-files:
  created: []
  modified:
    - openarena_perception/navigation/learned_map.py
    - openarena_perception/hud_schema.py
    - openarena_perception/visualization/panels/stats.py
    - tests/test_room_perception.py
    - tests/test_hud_schema.py
    - tests/test_open_perception_panels.py

key-decisions:
  - "CornerDetector endpoint proximity bumped from default 32u to 64u inside fit_rooms() because RANSAC-fit walls terminate at inlier extents, typically undershooting real corners by 10-30u"
  - "Room log (items_seen, visit_count, first_seen_ts, last_visited_ts) carried forward across refit passes by centroid-match with 128u tolerance"
  - "current_room_id cache invalidation is position-driven (invalidated in update() after _prev_pos assignment) rather than time-driven, keeping the PIP cost flat as room count grows"
  - "StatsPanel row 10/11 y-position hardcoded to 612/626 with explicit reset rather than continuing the verbose loop cursor — decouples Phase 13 row layout from verbose-loop internals"

patterns-established:
  - "Per-tick cache invalidation via boolean flag flipped in update()"
  - "Optional kwargs that emit keys only when non-None (dedup contract preserved)"

requirements-completed: [RP-09, RP-12]

duration: 42min
completed: 2026-04-11
---

# Phase 13 Plan 13-05: Room Perception Integration Summary

**LearnedMap gained a fit_rooms() orchestrator, per-room item ingestion, a visit-count debouncer, and a cached current_room_id query; hud_schema.build_hud_payload and StatsPanel surface the new data while preserving the Phase 12.1 byte-identical contract.**

## Performance

- **Duration:** ~42 min
- **Started:** 2026-04-11
- **Completed:** 2026-04-11
- **Tasks:** 2 (both TDD RED -> GREEN, no refactor pass needed)
- **Files modified:** 6 (3 production + 3 test)

## Accomplishments

- Wired LineFitter -> CornerDetector -> RoomInferrer -> DoorwayDetector into LearnedMap via `fit_rooms()`. One call over a per-floor raycast cloud populates `_fitted_walls_per_floor`, `_corners_per_floor`, `_rooms_per_floor`, `_partial_rooms_per_floor`, and `_doorways_per_floor`.
- Added `note_item(name, x, y)` which routes an observed item into the first Room whose polygon contains (x, y) via `cv2.pointPolygonTest` (first-match wins, duplicate-name dedup).
- Added `current_room_id()` with a per-tick cache invalidated by `update()` and `fit_rooms()`. Across 10 disjoint rooms on x86-64 the averaged cost is ~12 microseconds per call.
- Visit-count debouncer: `update()` now computes the current_room_id after the position update and increments `Room.visit_count` exactly once per outside-to-inside transition — not per tick while inside.
- `export_for_hud()` surfaces six new keys (`fitted_walls`, `corners`, `rooms`, `doorways`, `current_room_id`, `current_room_items`) and now also reports the current_room's items.
- `save()` serializes typed `Wall`, `Corner`, `Room`, `Doorway` entities to schema v3; `load()` round-trips them back into typed `NamedTuple` instances. The `_raw` placeholder attributes introduced by Plan 13-02 are gone.
- `build_hud_payload()` accepts two new optional kwargs (`current_room_id`, `current_room_items`) which emit top-level keys only when non-None. Pre-Phase-13 callers produce byte-identical payloads (test asserts equality after stripping the timestamp).
- `StatsPanel._draw_verbose` appends two rows (row 10 `room`, row 11 `room_items`) at y=612/626. Row 11 ends at y=640, well inside the 700px panel, and the 9 existing verbose rows are untouched. A sanity assert inside `_draw_verbose` guards the panel budget.

## Task Commits

Each task followed TDD (RED -> GREEN) with two commits per task:

1. **Task 1 RED: RP-09 test fixtures** — `76ae303` (test)
2. **Task 1 GREEN: LearnedMap pipeline wiring** — `b25e8b3` (feat)
3. **Task 2 RED: RP-12 test fixtures** — `c94aa86` (test)
4. **Task 2 GREEN: hud_schema + StatsPanel rows** — `df1e2a1` (feat)

## Files Modified

- `openarena_perception/navigation/learned_map.py` — Added imports for the room_perception subpackage; added per-floor `_line_fitters`, `_fitted_walls_per_floor`, `_corners_per_floor`, `_rooms_per_floor`, `_partial_rooms_per_floor`, `_doorways_per_floor`, plus `_last_current_room_id`/`_cached_current_room_id`/`_current_room_cache_valid`. Added `fit_rooms()`, `_preserve_room_log()`, `note_item()`, `current_room_id()`. Wired visit-count debouncer into `update()`. Extended `export_for_hud()` with six new keys. Rewrote the v3 branches of `save()` and `load()` to serialize/deserialize typed entities.
- `openarena_perception/hud_schema.py` — Added `current_room_id` and `current_room_items` kwargs to `build_hud_payload`; they are emitted via a conditional block matching the Phase 12-01 verbose-field pattern.
- `openarena_perception/visualization/panels/stats.py` — After the existing verbose-row loop, explicitly reset `y = 612` and draw rows 10/11 (room, room_items) using the same text/placeholder pattern as the existing 9 verbose rows. Added a sanity assert `y <= 660` so layout regressions surface immediately.
- `tests/test_room_perception.py` — Un-skipped `test_item_ingestion_pip`, added `test_fit_rooms_end_to_end`, `test_visit_count_debouncer`, `test_current_room_id_and_export_for_hud`, `test_update_with_10_rooms_under_1ms`.
- `tests/test_hud_schema.py` — Added `test_current_room_kwargs_backward_compat`, `test_current_room_kwargs_emitted`, `test_current_room_kwargs_none_values_absent`.
- `tests/test_open_perception_panels.py` — Added `test_stats_panel_renders_room_rows`, `test_stats_panel_legacy_state_still_renders_9_verbose_rows`, `test_stats_panel_row_budget_fits_700px`.

## Orchestration Sequence (fit_rooms)

```
LearnedMap.fit_rooms(force=?, now=?)
  |
  +-- cloud = self._raycasts_per_floor[current_floor]
  |   if len(cloud) < 20: return   # not enough support to fit
  |
  +-- LineFitter.fit(cloud)        # cadence-gated, or fit_now(cloud) if force
  |     |
  |     returns List[Wall]         # merged across prior passes
  |
  +-- CornerDetector(endpoint_max_dist=64u).detect(walls)
  |     returns List[Corner]
  |
  +-- RoomInferrer().infer(walls, corners)
  |     returns (List[Room], List[PartialRoom])
  |
  +-- DoorwayDetector().detect(walls, corners)
  |     returns List[Doorway]
  |
  +-- _preserve_room_log(prev_rooms, new_rooms)
  |     centroid-match on a 128u radius; carries items_seen, visit_count,
  |     first_seen_ts, last_visited_ts forward into the new Room list.
  |
  +-- Store into self._fitted_walls_per_floor / _corners_per_floor /
      _rooms_per_floor / _partial_rooms_per_floor / _doorways_per_floor
      and invalidate the current_room_id cache.
```

## Items Flow (ReactiveAgent -> rooms)

```
ReactiveAgent observes weapon at (wx, wy)
  -> LearnedMap.note_item("weapon_rocketlauncher", wx, wy)
       -> for room in self._rooms_per_floor[current_floor]:
            if cv2.pointPolygonTest(poly, (wx, wy), False) >= 0:
                first match wins
                if name not already in items_seen:
                    items_seen += (name, time.time())
                break
```

Wiring the ReactiveAgent call-site is left to Plan 13-06 (minimap render plan will also surface the item list per room).

## Visit-count Debouncer

```
update() per tick:
  ...
  self._prev_pos = (wx, wy)
  self._current_room_cache_valid = False         # position changed
  cur = self.current_room_id()                    # may hit rooms list
  if cur != self._last_current_room_id:           # transition occurred
    if cur is not None:
      rooms[idx] = r._replace(
        visit_count = r.visit_count + 1,
        last_visited_ts = now,
        first_seen_ts = r.first_seen_ts or now,
      )
    self._last_current_room_id = cur
```

Entry/exit/re-entry sequence `outside -> inside -> inside -> inside -> outside -> inside` yields `visit_count == 2`, not 3. Tested by `test_visit_count_debouncer`.

## Decisions Made

1. **CornerDetector proximity bumped to 64u inside fit_rooms()** — The default 32u works for hand-crafted unit-test walls, but RANSAC fits over the `rect_point_cloud` fixture produce walls whose endpoints undershoot the real corners by up to ~35u (inlier extent trimming). 64u reliably closes the 4-wall rectangle into 4 corners and 1 Room without inducing false positives on the noisy_point_cloud fixture.
2. **Centroid-match room log preservation** — A refit can produce a slightly different polygon for the same architectural room (new inliers, drifted endpoints). Matching rooms by centroid within 128u and carrying `items_seen` / `visit_count` forward preserves per-room memory across refits without needing stable room IDs from the inferrer.
3. **Position-driven cache invalidation** — The per-tick cache is invalidated whenever `update()` assigns a new `_prev_pos`, not on a time basis. This means multiple in-tick queries (e.g. `update()` debouncer + `export_for_hud()`) share a single PIP pass.
4. **Explicit y-reset in StatsPanel rows 10/11** — Rather than letting the verbose loop cursor flow into the new rows, `_draw_verbose` explicitly sets `y = 612` before drawing rows 10/11. This decouples Phase 13 row layout from the 9-row verbose internals and makes the backward-compat test's "y budget" check trivial.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CornerDetector default threshold too tight for real RANSAC output**
- **Found during:** Task 1 (`test_fit_rooms_end_to_end` assertion `len(corners) == 4`)
- **Issue:** With the conftest `rect_point_cloud` fixture, LineFitter produces 4 walls but their endpoints are up to ~35u apart at the corners (over the default `endpoint_max_dist=32u`). Corner count landed at 3, breaking downstream room inference.
- **Fix:** Bumped the CornerDetector proximity threshold to 64u inside `fit_rooms()` only (the detector's default stays 32u for hand-crafted unit tests). Restored corner count to 4 and room count to 1.
- **Files modified:** `openarena_perception/navigation/learned_map.py`
- **Verification:** `test_fit_rooms_end_to_end` green; `test_ransac_four_wall_rectangle` (direct detector usage) still green.
- **Committed in:** `b25e8b3`

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for correctness — the plan's end-to-end assertion depends on the real pipeline producing 4 corners and 1 Room from the fixture. No scope creep.

## Issues Encountered

- **Flaky perf test in unrelated subsystem.** `tests/test_wireframe_aas_backend.py::test_mesh_build_scene_perf_under_budget` failed once during the full-suite run (12.2ms vs 5ms budget) but passes in isolation. Pre-existing flake unrelated to Plan 13-05 changes. Logged here as a deferred item; not fixed in this plan.

## Performance Measurements

- `test_update_with_10_rooms_under_1ms` on x86-64: averaged ~12 microseconds per `current_room_id()` call (budget 1 ms). Cache invalidation pattern keeps PIP cost flat as room count grows because each query runs a single linear scan with early termination at first match. On Pi 4/5 we expect roughly 5-10x slower, still well inside the 1ms budget.
- `test_raycast_capture_overhead_under_1ms` (Plan 13-02 carryover) still green.

## Known Stubs

None. `fit_rooms()`, `note_item()`, `current_room_id()`, and the new HUD kwargs are all live. The remaining Phase 13 work (minimap visual + Reactive Agent `note_item` call-site + live checkpoint) is owned by Plan 13-06.

## Threat Flags

None. Changes are internal to the navigation subsystem and the HUD payload shape. No new network surface, no new auth paths, no new file access patterns.

## Verification

- `uv run pytest tests/test_room_perception.py tests/test_learned_map.py tests/test_hud_schema.py -q` — green (22 + 9 + 34 = 65 tests)
- `SDL_VIDEODRIVER=dummy uv run pytest tests/test_open_perception_panels.py -q` — green (23 tests)
- `uv run pytest -q` — 770 passed, 1 flaky unrelated perf test (AAS mesh build perf budget — passes in isolation)
- `grep -n "def fit_rooms" openarena_perception/navigation/learned_map.py` — matches
- `grep -n "cv2.pointPolygonTest" openarena_perception/navigation/learned_map.py` — 2 matches (note_item + current_room_id)
- `grep -n "current_room_id" openarena_perception/hud_schema.py` — matches
- `grep -n "current_room_id" openarena_perception/visualization/panels/stats.py` — matches
- Baseline before Plan 13-05: 761 tests. After Plan 13-05: 771 tests collected (5 new RP-09 + 5 new RP-12, minus the un-skipped placeholder which was already counted). Matches expected delta.

## Next Phase Readiness

**Plan 13-06 can begin immediately.** The MinimapPanel needs to:

- Draw `fitted_walls` from `export_for_hud()` as clean green-ish lines (NOT red stubs)
- Draw `corners` as small filled circles
- Draw `rooms` as faint-outlined 20%-alpha polygons; the `current_room_id` gets a brighter outline
- Remove the legacy `wall_segments` red-stub render block (lines 192-203 of minimap.py)
- Wire ReactiveAgent's item-observation callback into `learned_map.note_item(...)` so the per-room `items_seen` log actually populates during live play
- Run the live checkpoint (`item_tour.py --no-vision`) on oa_dm1 to verify fitted walls + room polygons render cleanly

All data surfaces are in place — Plan 13-06 is purely presentation + one small wiring change.

## Self-Check: PASSED

Files verified present:
- `openarena_perception/navigation/learned_map.py` — has `def fit_rooms`, `def note_item`, `def current_room_id`, 2x `cv2.pointPolygonTest`
- `openarena_perception/hud_schema.py` — has `current_room_id` kwarg + emit block
- `openarena_perception/visualization/panels/stats.py` — has `current_room_id` row handling at y=612/626
- `tests/test_room_perception.py` — has new RP-09 tests
- `tests/test_hud_schema.py` — has new RP-12 tests
- `tests/test_open_perception_panels.py` — has new RP-12 tests

Commits verified present:
- `76ae303` test RED Task 1
- `b25e8b3` feat GREEN Task 1
- `c94aa86` test RED Task 2
- `df1e2a1` feat GREEN Task 2

---
*Phase: 13-room-perception-and-wall-reconstruction*
*Plan: 05*
*Completed: 2026-04-11*
