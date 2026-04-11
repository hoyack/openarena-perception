---
phase: 13-room-perception-and-wall-reconstruction
plan: 03
subsystem: navigation-room-perception
tags: [navigation, geometry, ransac, wave-1]
wave: 1
requires: [13-01]
provides:
  - "openarena_perception.navigation.room_perception subpackage"
  - "Wall + Corner + Room + PartialRoom + Doorway NamedTuples (Wall is live, others are forward-declared for Plan 13-04)"
  - "LineFitter: seeded RANSAC + SVD endpoint fit + wall merging + cadence gate"
affects:
  - openarena_perception/navigation/room_perception/__init__.py
  - openarena_perception/navigation/room_perception/types.py
  - openarena_perception/navigation/room_perception/line_fitter.py
  - tests/test_room_perception.py
tech-stack:
  added: []
  patterns:
    - "Local np.random.default_rng(seed) — never touches the global RNG state (Plan 13-02 burned us on that pattern)"
    - "SVD principal direction for robust 2D segment endpoint extraction from inliers"
    - "Iterative RANSAC: extract best line, remove inliers, repeat until no line has >= min_support"
    - "OR-trigger cadence gate: (time elapsed) OR (point delta) OR (first call)"
    - "Wall merge preserves existing id and accumulates support_count instead of emitting duplicates"
key-files:
  created:
    - openarena_perception/navigation/room_perception/__init__.py
    - openarena_perception/navigation/room_perception/types.py
    - openarena_perception/navigation/room_perception/line_fitter.py
  modified:
    - tests/test_room_perception.py
decisions:
  - "RANSAC chosen over Hough per 13-RESEARCH.md — handles non-uniform raycast density, gives support_count for free, numpy-only"
  - "Local np.random.default_rng(self._seed) re-seeded on every fit_now() so repeat fits are bit-identical across runs"
  - "SVD (not least-squares regression) for segment direction — robust to outliers that slipped inside the inlier band"
  - "Inlier threshold 8u / min_support 20 / max_iters 1000 — matches RESEARCH budget"
  - "Confidence = min(1.0, support / 100) — saturates at 100 inliers"
  - "Wall merge criteria: angle delta < 10deg (or > 170deg for anti-parallel) AND BOTH candidate endpoints within inlier_threshold of existing line"
  - "On merge, extend endpoints along existing direction (project all 4 endpoints, keep extremes); support_count = sum, first_seen = min, last_seen = now, id preserved"
  - "Cadence gate trigger is OR-ed: first call ever OR (now - last_fit_ts >= fit_interval_s) OR (cloud_len - last_fit_point_count >= point_count_trigger)"
  - "Cadence test: 10 ticks at 1s over a 3s interval fires at t=0, t=3, t=6, t=9 = exactly 4 fits"
  - "Forward-declared Corner/Room/PartialRoom/Doorway placeholders in types.py so Plan 13-04 can drop in without package churn"
metrics:
  duration: ~8min
  tasks: 2
  files: 4
  completed: 2026-04-11
---

# Phase 13 Plan 03: Seeded RANSAC Line Fitter Summary

Delivers the line-fitting half of Phase 13: a new `openarena_perception.navigation.room_perception` subpackage containing an immutable `Wall` NamedTuple and a deterministic seeded-RANSAC `LineFitter` that converts a raycast point cloud into architectural wall segments, with wall merging across successive fit passes and a cadence gate to prevent per-tick invocation.

## What Shipped

### 1. room_perception subpackage (Task 1, commit `e28ddb5`)

- **`openarena_perception/navigation/room_perception/__init__.py`** — re-exports `Wall`, `Corner`, `Room`, `PartialRoom`, `Doorway`.
- **`openarena_perception/navigation/room_perception/types.py`** — 5 `NamedTuple` classes. `Wall` is consumed by `LineFitter` this plan; the other 4 are forward declarations for Plan 13-04 (Corner detection, Room polygon inference, Doorway gap detection) so the package surface is stable from Wave 1 onward.
- Wall field shape locked by 13-CONTEXT.md: `(id, x1, y1, x2, y2, confidence, support_count, first_seen, last_seen)`.
- Smoke test: `from openarena_perception.navigation.room_perception import Wall` succeeds; `Wall(...)` instantiates cleanly; full suite still green (752 passing).

### 2. LineFitter (Task 2, commit `925df57`)

- **`openarena_perception/navigation/room_perception/line_fitter.py`** — ~270 lines, pure numpy + stdlib, zero new dependencies.
- Public API:
  ```python
  LineFitter(seed=42, inlier_threshold=8.0, min_support=20, max_iterations=1000,
             confidence_threshold=0.4, fit_interval_s=3.0, point_count_trigger=500)
  .fit(cloud, now=None) -> list[Wall]       # cadence-gated
  .fit_now(cloud, now=None) -> list[Wall]   # bypass gate
  .walls -> list[Wall]                       # cached read-only
  ```
- Algorithm (iterative RANSAC):
  1. Reseed local `np.random.default_rng(seed)` at the start of every `fit_now()` so repeat fits are bit-identical across runs — **does not** touch global `np.random` state (Plan 13-02 lesson — we got bitten by global RNG pollution there).
  2. Copy cloud into a `remaining` array.
  3. Loop: sample 2 random points, compute vectorized perpendicular distance of all `remaining` points to the infinite line, count inliers within `inlier_threshold`. Pick best sample over `max_iterations` trials.
  4. If best inlier count < `min_support`: break.
  5. Extract best inliers, fit segment endpoints via SVD principal direction + project-to-extents (robust to inlier-band outliers).
  6. Emit Wall if `confidence >= confidence_threshold`, remove inliers from `remaining`, repeat.
  7. Hard cap at 16 lines per fit to avoid pathological loops.
- Wall merge (`_merge_wall`):
  - For each existing wall, check angle delta within 10° (or > 170° for anti-parallel), then check that **both** candidate endpoints have perpendicular offset ≤ `inlier_threshold` from the existing line.
  - On merge: project all 4 endpoints (existing + candidate) onto the existing direction vector, keep the min/max extrema as new endpoints, sum `support_count`, preserve `existing.id`, update `last_seen = now`, keep `first_seen = min(...)`.
  - Merge returns `True` → skip append; `False` → append as new wall with a fresh id.
- Cadence gate in `fit()`:
  - Triggers when ANY of: `self._last_fit_ts is None`, `(now - self._last_fit_ts) >= fit_interval_s`, `(cloud_len - self._last_fit_point_count) >= point_count_trigger`.
  - Otherwise returns cached `self._walls` unchanged so a per-tick caller cannot accidentally run RANSAC at 60 Hz.

### 3. Tests — RP-03, RP-04, RP-05 flip GREEN

`tests/test_room_perception.py` un-skipped RP-03/04/05 and added 2 supporting tests:

| Test | Requirement | Coverage |
|------|-------------|----------|
| `test_ransac_four_wall_rectangle` | RP-03 | `rect_point_cloud` → exactly 4 Walls; each midpoint within 5u of one of the 4 ground-truth boundaries (y=0, y=384, x=0, x=512); two fresh fitters with `seed=42` produce bit-identical endpoints and support counts |
| `test_ransac_noise_only_returns_empty` | RP-03 guard | `noisy_point_cloud` (400 uniform random) → 0 walls (no line has ≥ 20 inliers within 8u) |
| `test_fit_cadence` | RP-04 | Spy on `fit_now`; 10 ticks at 1s over `fit_interval_s=3.0` → exactly 4 real fits (t=0, 3, 6, 9) |
| `test_fit_triggered_by_point_count` | RP-04 | With `fit_interval_s=999, point_count_trigger=500`: first call triggers; same-size repeat does not; 600-point cloud triggers via delta=550 |
| `test_wall_merge` | RP-05 | Calling `fit_now(rect_point_cloud)` twice → still exactly 4 walls; each wall's `support_count` roughly doubles; `last_seen` advances to the second-pass timestamp |

Wave 2/3 stubs (RP-06..RP-09) stay skipped for Plan 13-04 / 13-05.

## Verification Results

```
$ uv run pytest tests/test_room_perception.py -q
5 passed, 4 skipped in 2.16s

$ uv run pytest -q
757 passed, 4 skipped in 41.95s
```

Plan 13-02 baseline was 752 passed / 7 skipped. Plan 13-03:
- Un-skipped 3 stubs (RP-03, RP-04, RP-05) → -3 skipped
- Added 2 new GREEN tests (noise-only, point-count trigger) → +2 passed
- Plus 3 newly-green RP tests → +3 passed
- Net: 752 → 757 passed, 7 → 4 skipped (matches exactly)

Determinism sanity check:
```
$ uv run python -c "from openarena_perception.navigation.room_perception.line_fitter import LineFitter
import numpy as np
rng=np.random.default_rng(42)
pts=np.vstack([np.column_stack([rng.uniform(0,100,50),np.zeros(50)]),np.column_stack([np.zeros(50),rng.uniform(0,100,50)])])
f=LineFitter(); print([w.support_count for w in f.fit_now(pts,now=0.0)])"
[61]
```
Reproducible across runs (same support count output).

Grep smoke checks:
```
$ grep -n "class Wall" openarena_perception/navigation/room_perception/types.py
11:class Wall(NamedTuple):

$ grep -n "default_rng(self._seed)" openarena_perception/navigation/room_perception/line_fitter.py
91:        self._rng = np.random.default_rng(self._seed)

$ grep -n "self.fit_interval_s" openarena_perception/navigation/room_perception/line_fitter.py
76:        time_elapsed = (
77:            self._last_fit_ts is None
78:            or (now - self._last_fit_ts) >= self.fit_interval_s
...

$ grep -n "_merge_wall" openarena_perception/navigation/room_perception/line_fitter.py
104:            if not self._merge_wall(raw, now):
196:    def _merge_wall(self, candidate: Wall, now: float) -> bool:
```

## RANSAC Parameter Choices

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `inlier_threshold` | 8.0 units | Matches RESEARCH.md budget; tight enough to distinguish adjacent walls on oa_dm1, loose enough to absorb raycast noise |
| `min_support` | 20 inliers | Filters spurious lines in noise-only clouds (test_ransac_noise_only_returns_empty verifies) |
| `max_iterations` | 1000 | High enough for the 4-wall rect fixture (280 wall points) to always find all 4 dominant lines; RESEARCH.md budget |
| `confidence_threshold` | 0.4 | Walls with <40 inliers never emit — prevents "candidate" lines from polluting Plan 13-04 corner detection |
| `fit_interval_s` | 3.0 seconds | Per Pi tick budget: 10+ FPS loop cannot afford RANSAC per tick; 3s cadence leaves room for point-count trigger to fire earlier on heavy capture bursts |
| `point_count_trigger` | 500 | Forces a re-fit when ≥500 new raycasts accumulate even if less than 3s elapsed — keeps the wall set fresh during aggressive exploration |
| Max walls per fit | 16 (internal cap) | Safety against pathological loops; oa_dm1 rooms have 4-8 walls typically |

## Merge Heuristic Details

Two passes of RANSAC over the same cloud would naively produce 2N walls. The merge heuristic collapses those duplicates:

1. **Angle gate** — direction vector angles must be within 10° or within 10° of 180° (anti-parallel). Wider than typical noise, tighter than corner angles.
2. **Perpendicular gate** — BOTH candidate endpoints must lie within `inlier_threshold` (8u) of the existing line. A candidate grazing one end of an existing wall at a slight angle fails this and gets appended as a new wall.
3. **Merge action** — project `(existing.x1, existing.y1, existing.x2, existing.y2, candidate.x1, candidate.y1, candidate.x2, candidate.y2)` onto the existing direction; the new endpoints are the min/max extrema. Support counts sum, id is preserved from existing, `first_seen` takes the older timestamp, `last_seen` advances to `now`, confidence grows (`existing.confidence + 0.2 * candidate.confidence`, capped at 1.0).

Empirically, a second pass over `rect_point_cloud` merges all 4 walls in-place (test verifies `len == 4` and `support_count >= 2 * first_pass_support - 5`).

## What Plan 13-04 Can Now Consume

`LineFitter().fit_now(lm._raycasts_per_floor[floor], now=t)` returns `list[Wall]` ready for corner detection:

- Each `Wall` has stable `id`, `(x1,y1)-(x2,y2)` endpoints, `confidence`, `support_count`.
- Walls returned are already filtered by `confidence_threshold` so low-evidence candidates don't pollute corner graphs.
- Calling fit twice merges instead of duplicating — Plan 13-04 can call fit repeatedly without worrying about exploding wall counts.
- Forward-declared `Corner`, `Room`, `PartialRoom`, `Doorway` tuples in `types.py` are ready for Plan 13-04 to import and populate.

## Deviations from Plan

None — plan executed exactly as written. Only minor editorial change: in the test file the cadence-gate test was adjusted to include `"first call"` triggering explicitly (the plan allowed either 3 or 4 fits; we converged on 4 since the first call always triggers when `_last_fit_ts is None`).

## Commits

- `e28ddb5` feat(13-03): create room_perception package with Wall/Corner/Room types
- `925df57` feat(13-03): implement seeded RANSAC LineFitter with merge + cadence gate

## Self-Check: PASSED

- FOUND: openarena_perception/navigation/room_perception/__init__.py
- FOUND: openarena_perception/navigation/room_perception/types.py (class Wall at line 11)
- FOUND: openarena_perception/navigation/room_perception/line_fitter.py (class LineFitter, default_rng(self._seed), self.fit_interval_s, _merge_wall all present)
- FOUND: tests/test_room_perception.py (RP-03/04/05 un-skipped + 2 new tests)
- FOUND: commit e28ddb5 (Task 1)
- FOUND: commit 925df57 (Task 2)
- VERIFIED: `uv run pytest tests/test_room_perception.py -q` → 5 passed, 4 skipped
- VERIFIED: `uv run pytest -q` → 757 passed, 4 skipped (Plan 13-02 baseline 752 + 5 new)
- VERIFIED: determinism smoke (`LineFitter().fit_now(...)` returns identical support counts across runs)
