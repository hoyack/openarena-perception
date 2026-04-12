---
phase: 13-room-perception-and-wall-reconstruction
plan: 09
subsystem: navigation/room_perception
status: AWAITING LIVE HUMAN VERIFICATION
gap_closure: true
prior_attempt: "13-08 (reverted in cd65788)"
tags: [navigation, geometry, gap-closure, revert-recovery, checkpoint]
requirements: [RP-07, RP-11]  # remain in-progress until live approval
dependency-graph:
  requires:
    - 13-02 (LineFitter output shape — untouched)
    - 13-04 (CornerDetector / RoomInferrer base — patched)
    - 13-05 (LearnedMap.fit_rooms wiring — patched)
    - 13-07 (item_tour.py fit_rooms call site — untouched)
  provides:
    - "CornerDetector(merge_radius=16) spatial merge at source"
    - "RoomInferrer centroid-cell dedup + MAX_ROOM_AREA cap"
  affects:
    - live minimap room polygon rendering on oa_dm1
    - fit_rooms output shape on all live maps
tech-stack:
  added: []
  patterns:
    - "O(n^2) single-pass spatial merge (non-transitive) for near-duplicate collapse"
    - "centroid-cell bucketing for geometry-level dedup, ID-free"
    - "hard area cap to reject over-connected-graph artifacts"
key-files:
  created: []
  modified:
    - openarena_perception/navigation/room_perception/corner_detector.py
    - openarena_perception/navigation/room_perception/room_inferrer.py
    - openarena_perception/navigation/learned_map.py
    - tests/test_room_perception.py
decisions:
  - "Spatial merge lives in CornerDetector, not RoomInferrer. The near-duplicate fleet must die at the source so downstream dedup can rely on clean IDs."
  - "Centroid-cell dedup uses vertex-mean centroid (not area-weighted). Cheap and sufficient for 16u bucketing."
  - "Third-wall-on-merge is logged once and dropped. Widening Corner NamedTuple is out of scope."
  - "Merge pass is single-pass non-transitive. Adequate for live n<=50 regime."
  - "Keep production max_room_area=200000 default. rect_point_cloud fixture (~196608 sq units) still passes under the cap."
metrics:
  duration: "~20 minutes"
  tasks_completed: 1
  tasks_total: 2
  completed_date: 2026-04-11
  tests_before: 775
  tests_after: 778
  new_tests: 3
---

# Phase 13 Plan 09: Revised GAP-3 Fix (Spatial Corner Merge + Centroid-Cell Dedup) — AWAITING LIVE VERIFICATION

**One-liner:** Attempt 2 at GAP-3 after Plan 13-08 was reverted — spatial corner merge at the source in `CornerDetector`, centroid-cell room dedup in `RoomInferrer`, hard `max_room_area=200000` cap, and revert of the 13-08 endpoint_max_dist 96u bump back to 64u.

## Status

**Task 1 (code + tests)**: complete, committed as `5e5ac66`.
**Task 2 (live human verification)**: BLOCKED — awaiting operator run of `item_tour.py --no-vision` on `oa_dm1`.

RP-07 and RP-11 remain **in-progress** in REQUIREMENTS.md. STATE.md and ROADMAP.md are **not** advanced. The orchestrator owns status progression after the user replies "approved".

## Changes

### 1. `CornerDetector` — spatial merge at source
- New keyword-only `merge_radius: float = 16.0` in `__init__`. Class-level `endpoint_max_dist` default stays at `32.0` (unchanged — unit tests depend on it).
- After the existing pair-enumeration loop, a single-pass O(n²) merge collapses any two corners within `merge_radius` into one. Merged corner uses: midpoint for position, `min()` of confidences, average of angles, and keeps the retained corner's two wall slots. If a collapsed candidate references a third wall, a single `logging.warning` fires per fit pass and the third wall is dropped.
- Corner IDs are reassigned sequentially `1..N` after the merge. Safe because `RoomInferrer` builds its adjacency from `(wall_a_id, wall_b_id)` pairs, not corner IDs.
- `Corner` NamedTuple is **not** widened. Use of `._replace(...)` honors immutability.

### 2. `RoomInferrer` — centroid-cell dedup + MAX_ROOM_AREA
- New defaults: `min_room_area=20000.0` (kept from 13-08), `max_room_area=200000.0` (new), `max_cycle_length=6` (kept from 13-08).
- Dedup is now a `best_by_cell: Dict[(cell_x, cell_y), ...]` keyed on `(round(cx/16), round(cy/16))` of the polygon centroid. Smallest-area cycle per bucket wins.
- 13-08's broken `used_wall_sets` / sorted-corner-ID-tuple approach is **deleted**. It was the visible cause of the 65 → 487 room blowup.
- Area filter now rejects both `area < min_room_area` AND `area > max_room_area`.
- New static helpers: `_polygon_centroid(polygon)` (vertex mean) and `_polygon_perimeter(polygon)` (for future tie-breaker use; currently area alone decides per bucket).
- PartialRoom aggregation is unchanged. It still reads from the emitted `rooms` list's `wall_ids`.

### 3. `LearnedMap.fit_rooms()` — revert endpoint bump, pass merge_radius
- Reverted `CornerDetector(endpoint_max_dist=64.0)` is kept (Plan 13-05 value). 13-08's `96.0` is **fully gone**.
- Now passes `merge_radius=16.0` explicitly (redundant with the new class default but makes the live-call site contract explicit).
- No changes to `RoomInferrer()` call on the next line — new defaults take effect automatically.

### 4. Regression tests — three new in `tests/test_room_perception.py`
- `test_corner_spatial_merge`: fixture of 4 near-parallel walls producing raw near-duplicate corners. Asserts `merge_radius=16` collapses them and `merge_radius=0` does not. Verifies no two merged corners within 16u.
- `test_room_centroid_cell_dedup`: 200×200 square + diagonal chord, hand-built corners. Asserts no two emitted rooms share centroid within 32u.
- `test_room_max_area_cap`: 1M sq unit cycle. Asserts default `RoomInferrer()` rejects it (0 rooms) and `max_room_area=2_000_000` accepts it (1 room).

These tests would have caught the 13-08 regression pre-live.

## Rationale — Why 13-08 Failed and What's Different Here

Plan 13-08 applied dedup **at the wrong layer**. It keyed by `tuple(sorted(cycle))` of corner IDs, assuming two cycles through "the same" corner would share IDs. Measured reality on oa_dm1 floor 0 disproved this:

- `CornerDetector` was emitting **near-duplicate corners** (2–8u apart) at slightly different midpoints because the "nearest endpoint pair" calculation varied by a few units across wall-pair enumerations. 45 corners clustered into ~10–15 spatial groups of 2–4 corners, each with a **distinct ID**.
- Dedup by corner-ID tuple was therefore useless. Cycles hitting structurally-the-same corner landed on different ID tuples and both were emitted.
- `endpoint_max_dist` 64→96 made the corner over-generation **worse**, not better (30 → 45 corners on floor 0).
- No MAX_ROOM_AREA cap let 500k+ sq unit map-spanning cycles slip through.

Result: 65 rooms → 487 rooms, 8411 centroid-pair collisions within 32u.

**What's different in 13-09:**
1. Dedup is now **spatial at the corner level**, not at the ID-tuple level. The near-duplicate fleet dies at the source in `CornerDetector`.
2. Room dedup is now **geometry-based** (centroid cells), robust against any upstream ID noise.
3. `max_room_area` caps absurd cycles that over-connected graphs produce.
4. `endpoint_max_dist` is **reverted** to 64u. 13-08's 96u was the direct cause of the 30→45 corner explosion.
5. A regression test suite pins each of these behaviors so the next version of this bug is caught pre-live.

## Verification

| Check | Expected | Actual |
|---|---|---|
| `corner_detector.py` has `merge_radius` kwarg | present | ✅ |
| `corner_detector.py` `endpoint_max_dist` class default | `32.0` unchanged | ✅ |
| `room_inferrer.py` `min_room_area` default | `20000.0` | ✅ |
| `room_inferrer.py` `max_room_area` default | `200000.0` | ✅ |
| `room_inferrer.py` `max_cycle_length` default | `6` | ✅ |
| `room_inferrer.py` centroid-cell dedup | `CENTROID_CELL = 16.0` present | ✅ |
| `learned_map.py` fit_rooms `endpoint_max_dist` | `64.0` (NOT 96) | ✅ |
| `learned_map.py` fit_rooms passes `merge_radius=16` | present | ✅ |
| 3 new regression tests | present and passing | ✅ |
| `uv run pytest -q tests/test_room_perception.py` | 16 pass | ✅ 16/16 |
| `uv run pytest -q` | ≥ 774 pass | ✅ 778/778 |
| Live: floor 0 corner count after merge | 10–25 | ⏳ pending |
| Live: floor 0 room count after dedup | ≤ ~10 | ⏳ pending |
| Live: no overlapping polygon plex on minimap | visually clean | ⏳ pending |
| Live: stats rows 10/11 populate in fitted rooms | real values | ⏳ pending |

## Deviations from Plan

None. Plan 13-09 was executed exactly as written:
- Step A–G from the `<action>` block applied verbatim.
- `rect_point_cloud` fixture (~196608 sq units) passed under `max_room_area=200000` default without needing Option A fallback. Production default stays tight at 200000.
- No architectural changes needed (no Rule 4 triggers).
- No auth gates.

## Commits

- `5e5ac66` — fix(13-09): spatial corner merge + centroid-cell room dedup + MAX_ROOM_AREA (retry of 13-08)

## Requirements Status

- **RP-07** (room inference): unit tests pass including 3 new regressions. Live behavior on `oa_dm1` is **unverified** — remains **in-progress** until operator approves.
- **RP-11** (live minimap visual on `oa_dm1`): unverified — remains **in-progress** until operator approves.

Do NOT flip these in REQUIREMENTS.md yet. The orchestrator owns that after "approved".

## Known Stubs

None. All four file changes are live production code paths exercised by Plan 13-07's tick-loop `fit_rooms` wiring. No placeholder data, no dead hooks.

## Threat Flags

None. Pure in-process algorithmic work — no new network endpoints, no new file paths, no new auth surfaces, no schema changes. Saved `oa_dm1.json` `rooms_per_floor` / `corners_per_floor` shapes are byte-compatible with the Plan 13-05 schema.

## Self-Check

- File `openarena_perception/navigation/room_perception/corner_detector.py`: FOUND, contains `merge_radius` (verified via commit diff: 75 insertions including merge pass).
- File `openarena_perception/navigation/room_perception/room_inferrer.py`: FOUND, contains `max_room_area` and `CENTROID_CELL`.
- File `openarena_perception/navigation/learned_map.py`: FOUND, contains `merge_radius=16.0` and `endpoint_max_dist=64.0`.
- File `tests/test_room_perception.py`: FOUND, contains all three new test function names.
- Commit `5e5ac66`: FOUND in `git log --oneline -3`.
- `uv run pytest -q`: **778 passed** in 88s, zero failures.

## Self-Check: PASSED
