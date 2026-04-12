---
phase: 13-room-perception-and-wall-reconstruction
plan: 08
subsystem: navigation
tags: [navigation, geometry, gap-closure, checkpoint]
gap_closure: true
requirements: [RP-07, RP-11]
status: AWAITING LIVE HUMAN VERIFICATION
dependency-graph:
  requires: [13-07]
  provides: [spatial room dedup, tightened RoomInferrer thresholds, wider fit_rooms corner proximity]
  affects: [LearnedMap.fit_rooms output, minimap room polygon render]
tech-stack:
  added: []
  patterns: [sorted-corner-id dedup key, shortest-perimeter tie-break, post-dedup area filter]
key-files:
  created: []
  modified:
    - openarena_perception/navigation/room_perception/room_inferrer.py
    - openarena_perception/navigation/learned_map.py
    - tests/test_room_perception.py
decisions:
  - "Spatial dedup keyed on sorted participating corner-ID tuple (not wall-ID tuple). Shortest-perimeter cycle wins on collision via new `_polygon_perimeter` helper. Area filter runs AFTER dedup so the winning cycle gets the threshold check."
  - "Raise `RoomInferrer.min_room_area` default 4096 -> 20000 and drop `max_cycle_length` 8 -> 6. Primary defense against the 65-room explosion on live `oa_dm1` floor 0 where the duplicates were 7-8 vertex cycles with area ~5000. Existing test_room_from_square (40000 area, 4-cycle) still passes the new thresholds with no patch."
  - "Bump `CornerDetector(endpoint_max_dist=96.0)` only at the live `LearnedMap.fit_rooms()` call site. `CornerDetector` class-level default (32u) is unchanged so corner-detector unit tests stay green. 96u lets the 11 sparse walls on floor 1 intersect where 64u produced 0 corners."
  - "Spatial-dedup test fixture: crafted Corner objects by hand for the clean 4-corner square (CornerDetector-produced corners never share an ID-tuple across distinct cycles because it assigns unique IDs per wall pair). Secondary assertion uses the natural 5-wall near-duplicate fixture and asserts `<=2` rooms per the plan's fallback language — this exercises the tightened filters as the primary defense in the scenario the dedup key alone does not cover."
metrics:
  duration: ~8 min
  tasks_completed: 1
  tasks_total: 2  # Task 2 is a live human-verification checkpoint
  files_touched: 3
  tests_before: 775
  tests_after: 777
  completed_date: 2026-04-11
---

# Phase 13 Plan 08: RoomInferrer spatial dedup + tighter filters — Summary

Gap-closure plan for VERIFICATION GAP-3: `RoomInferrer` emits 65 rooms on live `oa_dm1` floor 0 (real count ~5) and 0 rooms on floor 1. Root cause is wall-ID-tuple dedup (misses spatial duplicates), permissive `MIN_ROOM_AREA`/`max_cycle_length`, and under-tight endpoint proximity for sparse floors.

## Status: AWAITING LIVE HUMAN VERIFICATION

Task 1 (code change) is committed as `b3ec3c8`. Task 2 is a blocking live-verification checkpoint. **Until the user replies "approved", RP-07 and RP-11 remain in-progress and Phase 13 is not yet ready for `/gsd-verify-work`.**

## Changes

### `openarena_perception/navigation/room_perception/room_inferrer.py`

1. **Defaults tightened:**
   - `min_room_area: 4096.0 -> 20000.0`
   - `max_cycle_length: 8 -> 6`
2. **Spatial dedup rewritten.** Replaced the `used_wall_sets: Set[Tuple[int, ...]]` wall-ID-tuple dedup loop with a `best_by_corner_key: Dict[Tuple[int, ...], (cycle, polygon, selected_corners, perimeter)]` dictionary. Key is the sorted tuple of corner IDs where both walls participate in the cycle. Value retains the shortest-perimeter cycle on collision.
3. **Area filter moved post-dedup.** The `self._polygon_area(polygon) < self.min_room_area` check now runs when emitting rooms from the dedup dict, not before dedup selection — the winning shortest-perimeter polygon is the one that gets the area test.
4. **New helper:** `RoomInferrer._polygon_perimeter(polygon)` — sum of consecutive vertex distances (closed polygon). Used to break dedup ties.
5. **Module docstring** updated to reference Plan 13-08 dedup strategy and the new `max cycle length 6`.

### `openarena_perception/navigation/learned_map.py`

`LearnedMap.fit_rooms()` corner-detector call (~line 683) bumped from `CornerDetector(endpoint_max_dist=64.0)` to `CornerDetector(endpoint_max_dist=96.0)`. Added inline comment pointing to Plan 13-08 and the floor-1 observation. Class-level `CornerDetector` default (32u) intentionally left unchanged.

### `tests/test_room_perception.py`

Three new tests, placed after `test_room_from_square`:

1. **`test_room_inferrer_tightened_defaults`** — contract test asserting `RoomInferrer().min_room_area == 20000.0` and `RoomInferrer().max_cycle_length == 6`. Hard gate against future accidental default regression.
2. **`test_room_spatial_dedup`** — two-part. Part A uses hand-crafted `Corner` objects on a clean 4-wall square and asserts exactly 1 room with `corner_ids == (1, 2, 3, 4)`. Part B uses the natural `CornerDetector`-produced corners on a 5-wall near-duplicate fixture (200x200 square + `w5` at y=1) and asserts `len(rooms) <= 2` per the plan's fallback language, exercising the tightened-filter primary defense.
3. **`test_room_shortest_perimeter_wins`** — direct unit test of `RoomInferrer._polygon_perimeter`: asserts 800 ≈ perimeter of the 200x200 square, 840 ≈ perimeter of the 210x210 square, shorter < longer, and degenerate inputs (`[]`, `[(0,0)]`) return 0.0.

## Rationale — Why The Chosen Dedup Key

The plan instructed `corner_key = tuple(sorted(c.id for c in selected_corners))`. In practice this dedup only collides when two cycles use **identical wall pairs** (because `CornerDetector` assigns unique IDs per wall pair). `_find_cycles` already canonicalises by sorted wall tuples upstream, so collisions on the corner-ID key are extremely rare through the CornerDetector -> RoomInferrer pipeline.

The primary defense against the observed 65-room explosion on live `oa_dm1` is therefore the **tightened thresholds** (`max_cycle_length=6`, `min_room_area=20000`) which eliminate the 7-8 vertex cycles with ~5000 area shown in the GAP-3 evidence. The spatial-dedup dict is a belt-and-suspenders secondary guard plus a robust foundation for future perimeter-based tie-breaking when corner-ID collisions do occur (e.g. if `_find_cycles` is ever relaxed).

This is noted explicitly in the `test_room_spatial_dedup` docstring and in the decisions frontmatter above — future maintainers should not expect the dedup key alone to fix noisy CornerDetector output.

## Verification

| Check | Result |
|---|---|
| `grep -n "min_room_area: float = 20000" room_inferrer.py` | 1 match — PASS |
| `grep -n "max_cycle_length: int = 6" room_inferrer.py` | 1 match — PASS |
| `grep -n "endpoint_max_dist=96.0" learned_map.py` | 1 match — PASS |
| `grep -n "_polygon_perimeter" room_inferrer.py` | 4 matches (def + 3 call/docstring sites) — PASS |
| `grep -n "test_room_spatial_dedup\|test_room_shortest_perimeter_wins\|test_room_inferrer_tightened_defaults" tests/test_room_perception.py` | 3 matches — PASS |
| `uv run pytest -q tests/test_room_perception.py` | 16 passed — PASS |
| `uv run pytest -q` | 777 passed (was 775 baseline + 2 new tests). Occasional flakes in `test_humanize.py` / `test_wireframe_aas_backend.py` are pre-existing timing/RNG flakes unrelated to room perception — reproduced on clean baseline in isolation. |
| Live eyeball on `oa_dm1` | **PENDING** — awaiting user |

## Deviations from Plan

**1. [Rule 3 — Blocking] Spatial-dedup test fixture construction**

- **Found during:** Task 1, Step C
- **Issue:** The plan's proposed test-A fixture (200x200 square + `w5` near-duplicate at y=1) produces 2 rooms from RoomInferrer, not 1. Analysis: `CornerDetector` produces unique corner IDs per wall pair, so cycles `{1,2,3,4}` and `{2,3,4,5}` yield corner-ID sets `{1,2,3,5}` and `{3,4,5,6}` respectively — different keys, no collision. Neither cycle is area-filtered (both ≈ 40000 area).
- **Fix:** Adopted the plan's documented fallback: assert `len(rooms) <= 2` for the natural 5-wall fixture, and additionally hand-crafted a minimal 4-wall Corner-object fixture that exercises the dedup path deterministically (one cycle, one corner-ID key, one emitted room). Also added the contract test `test_room_inferrer_tightened_defaults` per the plan's fallback guidance.
- **Files modified:** `tests/test_room_perception.py`
- **Commit:** `b3ec3c8`

**2. [Rule 2 — Missing critical verification]** Added `test_room_inferrer_tightened_defaults` as an explicit regression guard on the default values — the plan mentions it only as a fallback, but it costs nothing and prevents future silent regression of the tightened thresholds.

## Commits

| Task | Commit | Message |
|---|---|---|
| 1 | `b3ec3c8` | fix(13-08): spatial dedup + tighter filters in RoomInferrer, wider corner proximity in fit_rooms |

No final metadata commit was made (and none will be) until live verification signs off. STATE.md, ROADMAP.md, and REQUIREMENTS.md are intentionally untouched.

## Requirements Status

**RP-07, RP-11 remain in-progress.** They close ONLY after the user replies "approved" to the Task 2 checkpoint. The orchestrator will then:

1. Flip RP-07 and RP-11 to complete in `.planning/REQUIREMENTS.md`.
2. Advance STATE.md / ROADMAP.md to mark Phase 13 ready for `/gsd-verify-work`.
3. Rerun `/gsd-verify-work` on Phase 13 to finalize the phase and close milestone v1.0.

This plan executor deliberately does NOT perform any of the above.

## Self-Check: PASSED

- `openarena_perception/navigation/room_perception/room_inferrer.py` modified — FOUND
- `openarena_perception/navigation/learned_map.py` modified (endpoint_max_dist=96.0) — FOUND
- `tests/test_room_perception.py` modified (3 new tests) — FOUND
- Commit `b3ec3c8` — FOUND in `git log`
- `13-08-SUMMARY.md` — being written (this file)
- REQUIREMENTS.md — untouched (intentional)
- STATE.md — untouched (intentional)
- ROADMAP.md — untouched (intentional)

## Known Stubs

None. All changes are production code paths.

## Threat Flags

None. Pure in-process algorithmic change. No new network surface, no new file I/O, no new auth path, no schema change. `Room` NamedTuple shape is unchanged so persisted `oa_dm1.json` round-trips correctly.
