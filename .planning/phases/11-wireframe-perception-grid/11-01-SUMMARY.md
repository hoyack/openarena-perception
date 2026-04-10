---
phase: 11-wireframe-perception-grid
plan: 01
subsystem: visualization
tags: [projection, math, pinhole, room-config, scene-geometry, q3-yaw, near-plane]
wave: 1
dependency_graph:
  requires: []
  provides:
    - openarena_perception.visualization.RoomConfig
    - openarena_perception.visualization.SceneGeometry
    - openarena_perception.visualization.OBJECT_COLORS_BGR
    - openarena_perception.visualization.projection (pure-function math API)
  affects: []
tech_stack:
  added: []
  patterns:
    - "Frozen+slots dataclasses (mirrors models.SituationalAwareness)"
    - "Pure-function math module, zero cv2 dependency"
    - "Batched-numpy + scalar-tuple dual interface for world_to_camera"
key_files:
  created:
    - openarena_perception/visualization/__init__.py
    - openarena_perception/visualization/config.py
    - openarena_perception/visualization/scene.py
    - openarena_perception/visualization/projection.py
    - tests/test_wireframe_projection.py
    - .planning/phases/11-wireframe-perception-grid/deferred-items.md
  modified: []
decisions:
  - "max_depth kept as a separate RoomConfig field from room_depth so the depth-color curve is not coupled to the room frame size"
  - "project_line clips to NEAR_Z + 1e-6 (not exactly NEAR_Z) because project_point rejects z <= NEAR_Z by design"
  - "OBJECT_COLORS_BGR suffixed _BGR to make Pitfall-5 (RGB/BGR swap) impossible to hide"
  - "world_to_camera accepts both 3-tuple and ndarray shape (N, 3) — tuple path returns a tuple, ndarray path returns ndarray"
metrics:
  duration: ~5 min
  tasks_completed: 3
  tests_added: 30
  tests_runtime: 0.44s
  commits: 3
  completed: 2026-04-10
---

# Phase 11 Plan 01: Projection Math + RoomConfig + SceneGeometry Summary

One-liner: Pure-numpy pinhole projection library with Q3-correct world-to-camera transform, near-plane clipping, parametric room tessellation, and depth-color curve — zero cv2 dependency, 30 unit tests locking in every pitfall from the Phase 11 research doc.

## What Was Built

Wave-1 foundation for the Phase 11 wireframe perception grid (Version B, AAS-driven).

1. **`openarena_perception/visualization/config.py`** — `RoomConfig` frozen+slots dataclass with every PRD §4.5 field (canvas, room frame, camera, palette, toggles) plus the CONTEXT.md §Decisions additions (depth curve: `near_color`, `far_color`, `warning_color`, `proximity_threshold`, `fade_power`, `max_depth`; effects: `glow_radius`, `glow_strength`, `scanline_spacing`, `scanline_strength`; plus `camera_height` per RESEARCH A5).

2. **`openarena_perception/visualization/scene.py`** — `SceneGeometry` frozen+slots dataclass (`walls`, `boxes` default to empty tuples — no mutable defaults) and `OBJECT_COLORS_BGR` dict matching PRD §5.2 exactly (`player`, `pickup`, `door`, `portal`, `wall`, `static`, `unknown`).

3. **`openarena_perception/visualization/projection.py`** — Pure-function math module:
   - `focal_length(width, fov_deg)` — pinhole fx
   - `project_point(x, y, z, cfg)` — returns `(int, int)` via `np.round` or `None` if `z <= NEAR_Z`
   - `project_line(p1, p2, cfg)` — near-plane clipping (Liang-Barsky-style parametric trim). Both-behind → `None`. One-behind → trimmed to `NEAR_Z + 1e-6`
   - `room_surface_grid(origin, axis_u, axis_v, divs_u, divs_v)` — parametric quad tessellation returning `(divs_u+1) + (divs_v+1)` iso-line segments
   - `project_depth_color(z, cfg)` — warning below `proximity_threshold`, else lerp `near_color → far_color` by `(z/max_depth)^fade_power`
   - `cube_edges(x, y, z, w, h, d)` — 12 AABB edges as segments
   - `screen_to_room(bbox_2d, cfg, depth_hint)` — Version-B escape hatch for 2D-detection placement
   - `world_to_camera(world_xyz, bot_pos, bot_yaw_deg, camera_height=None)` — Q3 (+X east / +Y north / +Z up, yaw CCW from +X, navigator.py:292 convention) → camera (+X right / +Y down / +Z forward). Accepts 3-tuple **or** numpy `(N, 3)` array.
   - `NEAR_Z = 0.1` module constant.
   - **Zero cv2 imports** (enforced by test).

4. **`tests/test_wireframe_projection.py`** — 30 tests in 0.44s covering:
   - Focal length at two FOVs
   - `project_point` center / x-offset / y-offset / behind-near-plane / sub-pixel rounding
   - `project_line` near-clip both-behind / one-behind-trim / exact-plane-as-behind / both-in-front
   - `room_surface_grid` line count + endpoints on quad
   - `project_depth_color` warning / near / far / clamp
   - `cube_edges` count / 8-unique-vertices / AABB bounds
   - `world_to_camera` at N/E/up bearings, yaw=0, batched ndarray, camera_height offset
   - `screen_to_room` centered box
   - `projection.__dict__` has no `cv2`
   - `SceneGeometry` defaults + `OBJECT_COLORS_BGR` PRD §5.2 values

## Pitfalls Addressed

| Pitfall | How |
|---|---|
| P1 — Q3 Z-up ↔ screen Y-down | `world_to_camera` maps `cam_y = -dz + camera_height` |
| P2 — Yaw sign/units | CCW degrees from +X, cross-verified at 3 bearings against `navigator.py:292` |
| P3 — Near-plane clipping | Parametric trim to `NEAR_Z + 1e-6` in `project_line`; both-behind → `None` |
| P5 — RGB/BGR confusion | `OBJECT_COLORS_BGR` explicit suffix |
| P6 — Float→int rounding | `np.round(...)` then `int(...)` in `project_point` |

## Key Decisions

1. **`max_depth` separate from `room_depth`** — depth-color curve should not force the renderer's room-box size. Gives the downstream renderer freedom to tune the color ramp independently.
2. **`project_line` clips to `NEAR_Z + 1e-6`** — `project_point` defines `z <= NEAR_Z` as behind by design (tested), so a segment clipped exactly to `NEAR_Z` would then be rejected. Adding 1 ppb past the plane lands visually on the clip plane without tripping the boundary.
3. **Dual-interface `world_to_camera`** — tuple-in/tuple-out for scalar tests, ndarray-in/ndarray-out `(N, 3)` for the future AAS backend (Plan 11-03).
4. **`OBJECT_COLORS_BGR` suffix** — the `_BGR` name makes Pitfall 5 (RGB/BGR swap at the cv2 boundary) impossible to hide behind a generic `COLORS` constant.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `project_line` clipped endpoint rejected by `project_point`**
- **Found during:** Task 3 first test run
- **Issue:** `project_line` was clipping the behind-camera endpoint onto `z = NEAR_Z` exactly, but `project_point` is defined to reject `z <= NEAR_Z` (and has a test asserting this). The trimmed endpoint therefore came back as `None` and the whole segment was dropped.
- **Fix:** Clip to `NEAR_Z + 1e-6` instead. Visually identical (division by a nearly-identical z) and keeps both behaviours consistent.
- **Files modified:** `openarena_perception/visualization/projection.py`
- **Commit:** `f6f4ca5`

**2. [Plan-text nit] Task-2 inline smoke-test used `==` on `focal_length`**
- **Found during:** Task 2 verification
- **Issue:** The `<verify>` shell command asserts `focal_length(960, 90.0) == 480.0`. IEEE-754 returns `480.00000000000006` because `tan(π/4) ≠ 1.0`. The authoritative Task-3 pytest correctly uses `pytest.approx(480.0)`.
- **Fix:** Verified with `math.isclose(..., 480.0)` — result is correct to 15 significant figures. Task 3's pytest suite is the source of truth for this assertion and it passes.
- **Files modified:** none (code is correct; only the inline smoke-test in the plan text would have tripped).

## Auth Gates

None — fully autonomous plan.

## Tests

- New: 30 tests in `tests/test_wireframe_projection.py` (0.44s).
- Regression: 37 tests (`test_navigation`, `test_property_based`, `test_tour_metrics`) all green.
- Full suite: 607 passed, 1 pre-existing stochastic failure in `test_humanize.py::test_accuracy_cap_enforced_in_aim_controller` (unrelated to Phase 11, passes in isolation — logged in `deferred-items.md`).

## Commits

| Task | Message | Hash |
|---|---|---|
| 1 | feat(11-01): add RoomConfig, SceneGeometry, OBJECT_COLORS_BGR | `96b69b0` |
| 2 | feat(11-01): add pure-math projection library for wireframe renderer | `ac7bb2c` |
| 3 | test(11-01): add exhaustive unit tests for wireframe projection math | `f6f4ca5` |

## Discoveries Affecting Later Waves (11-02, 11-03)

1. **`project_line` clip boundary is `NEAR_Z + 1e-6`** — Plan 11-02's renderer must not assume clipped endpoints sit on `NEAR_Z` exactly. Use the return value verbatim; do not re-check against `NEAR_Z`.
2. **`world_to_camera` accepts batched `(N, 3)`** — Plan 11-03's AAS backend should push all wall vertices as a single ndarray to avoid Python-loop overhead. The batched path is tested.
3. **`OBJECT_COLORS_BGR` includes both `"portal"` and `"static"` aliases** — Plan 11-02's per-object color lookup should fall back to `OBJECT_COLORS_BGR["unknown"]` for missing classes, not crash.
4. **`RoomConfig.camera_height` defaults to `40.0`** (Q3 eye-height approx) — Plan 11-03's AAS backend should pass this through `world_to_camera(..., camera_height=cfg.camera_height)` instead of 0.
5. **`SceneGeometry.boxes` tuple format is `(class_name, x, y, z, w, h, d)`** with `(x, y, z)` as center and `(w, h, d)` as *full* extents. `cube_edges` expects the same convention — the scene → renderer call is a straight passthrough.

## Known Stubs

None. Every function is fully implemented against its unit tests; there are no placeholder returns, no hardcoded empty collections flowing to UI, and no TODOs.

## Self-Check: PASSED

**Files created:**
- FOUND: `openarena_perception/visualization/__init__.py`
- FOUND: `openarena_perception/visualization/config.py`
- FOUND: `openarena_perception/visualization/scene.py`
- FOUND: `openarena_perception/visualization/projection.py`
- FOUND: `tests/test_wireframe_projection.py`
- FOUND: `.planning/phases/11-wireframe-perception-grid/deferred-items.md`

**Commits:**
- FOUND: `96b69b0` (Task 1)
- FOUND: `ac7bb2c` (Task 2)
- FOUND: `f6f4ca5` (Task 3)

**Verification gates:**
- `uv run pytest tests/test_wireframe_projection.py -x -q` → 30 passed in 0.44s
- `uv run python -c "... 'cv2' not in p.__dict__"` → no cv2 in projection.py
- Regression suites (`test_navigation`, `test_property_based`, `test_tour_metrics`) → 37 passed
