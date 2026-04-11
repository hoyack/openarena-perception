---
phase: 13-room-perception-and-wall-reconstruction
plan: 01
subsystem: testing-infrastructure
tags: [testing, infrastructure, schema, wave-0]
wave: 0
requires: []
provides:
  - "Schema v3 forward-compat load path in LearnedMap"
  - "RED test scaffold for RP-01..RP-10"
  - "Synthetic point-cloud fixtures (rect/U/noisy)"
affects:
  - openarena_perception/navigation/learned_map.py
  - tests/conftest.py
  - tests/test_learned_map.py
  - tests/test_room_perception.py
tech-stack:
  added: []
  patterns:
    - "np.random.default_rng(seed) for deterministic test fixtures"
    - "pytest.mark.skip(reason=...) for cross-wave RED stubs"
key-files:
  created:
    - tests/test_learned_map.py
    - tests/test_room_perception.py
  modified:
    - openarena_perception/navigation/learned_map.py
    - tests/conftest.py
decisions:
  - "Pitfall 6 fixed in Wave 0 (not Plan 02) so any downstream v3 save reloads cleanly from day one"
  - "v3 forward-compat block uses _raw suffix on new attributes to avoid collision with typed entities Plan 02 will introduce"
  - "All Wave 1-3 stubs use pytest.mark.skip (not xfail) so full suite stays 100% green until each plan un-skips its row"
metrics:
  duration: ~8min
  tasks: 2
  files: 4
  completed: 2026-04-11
---

# Phase 13 Plan 01: Test Scaffold and Schema v3 Whitelist Summary

Wave 0 test infrastructure for Phase 13 room perception: fixed the `learned_map.load()` v3 version-whitelist bug (Pitfall 6) so downstream plans can persist the new schema without silent reload rejection, created RED test stubs mapped to RP-01..RP-10, and added deterministic synthetic point-cloud fixtures for Wave 1-3 consumption.

## What Shipped

### 1. Pitfall 6 fix — schema v3 load acceptance
- `openarena_perception/navigation/learned_map.py:221`: version whitelist changed from `(1, 2)` to `(1, 2, 3)`.
- New v3 forward-compat block after existing v2 field reads: pulls `raycasts_per_floor`, `fitted_walls`, `corners`, `rooms`, `doorways` with empty defaults into `_raw`-suffixed attributes so later plans can replace them with typed entities without collision.
- Regression test `test_v2_file_still_loads` proves Phase 12.1 v2 files still round-trip.

### 2. RED test stubs
- `tests/test_learned_map.py` — created fresh. 2 green tests (v3 whitelist + v2 regression) + 3 skipped RP-01/02/10 stubs.
- `tests/test_room_perception.py` — created fresh. 7 skipped stubs mapped to RP-03..RP-09 (LineFitter, Corner/Room, HUD).
- Every stub carries a `pytest.mark.skip(reason="Wave N — Plan 13-0X RP-YY")` so downstream plans only need to remove the marker and fill in assertions.

### 3. Synthetic point-cloud fixtures
Appended to existing `tests/conftest.py`:
- `rect_point_cloud` — 280 wall points + 28 outliers (~10%), 4-wall axis-aligned rectangle (0,0)-(512,384), `default_rng(42)`.
- `u_shape_point_cloud` — 3-wall U (left/bottom/right) for PartialRoom tests, `default_rng(123)`.
- `noisy_point_cloud` — 400 pure uniform-random points for "fitter returns 0 walls" guard, `default_rng(7)`.

## Verification Results

```
$ uv run pytest tests/test_learned_map.py tests/test_room_perception.py -q
2 passed, 10 skipped in 0.87s

$ uv run pytest -q
745 passed, 10 skipped in 33.65s
```

Phase 12.1 baseline was 743 passing. Plan 13-01 adds exactly 2 new green tests (the v3 whitelist + v2 regression). No regression.

```
$ grep -n 'version not in (1, 2, 3)' openarena_perception/navigation/learned_map.py
221:            if version not in (1, 2, 3):
```

## Requirements Scaffolded

| Req | Test | Status |
|-----|------|--------|
| RP-01 | `test_raycast_capture_appends` | SKIP (Plan 13-02) |
| RP-02 | `test_raycast_decimation` | SKIP (Plan 13-02) |
| RP-03 | `test_ransac_four_wall_rectangle` | SKIP (Plan 13-03) |
| RP-04 | `test_fit_cadence` | SKIP (Plan 13-03) |
| RP-05 | `test_wall_merge` | SKIP (Plan 13-03) |
| RP-06 | `test_corner_from_two_walls` | SKIP (Plan 13-04) |
| RP-07 | `test_room_from_square` | SKIP (Plan 13-04) |
| RP-08 | `test_partial_room_and_doorway` | SKIP (Plan 13-04) |
| RP-09 | `test_item_ingestion_pip` | SKIP (Plan 13-05) |
| RP-10 | `test_v3_file_is_accepted_by_version_whitelist` + `test_v2_file_still_loads` | PASS |

RP-10 is GREEN in Wave 0. All others are scaffolded RED stubs for downstream waves to un-skip.

## Deviations from Plan

None — plan executed exactly as written. The only minor note: `numpy` import was moved from inside the `test_v2_file_still_loads` method to module level (cleaner and already used by conftest).

## Commits

- `1d1bcc7` fix(13-01): accept schema v3 in learned_map load + RED stubs
- `a46f629` test(13-01): add room perception RED stubs + synthetic fixtures

## Self-Check: PASSED

- FOUND: openarena_perception/navigation/learned_map.py (v3 whitelist + forward-compat block)
- FOUND: tests/test_learned_map.py
- FOUND: tests/test_room_perception.py
- FOUND: tests/conftest.py (3 new fixtures appended)
- FOUND: commit 1d1bcc7
- FOUND: commit a46f629
- VERIFIED: `uv run pytest -q` → 745 passed, 10 skipped (Phase 12.1 baseline 743 + 2 new)
