# Phase 11 Plan Check — Version B (AAS-driven wireframe)

**Checked:** 2026-04-10
**Checker:** gsd-plan-checker
**Plans reviewed:** 11-01 (projection math), 11-02 (renderer + HUD + effects), 11-03 (AAS backend + demo + human-verify checkpoint)

## VERDICT: PASS

If the three plans execute exactly as written, the Phase 11 Version B goal — *Pi-native AAS-driven holodeck wireframe renderer with zero new neural deps* — will be met. Goal-backward trace is clean; every scoped requirement, pitfall, and load-bearing assumption is covered by concrete task steps with runnable verification.

---

## Coverage Summary

### Version B compliance (no Pi-hostile deps) — PASS
- Zero `torch`, `depth-anything-v2`, `ultralytics`, `GroundingDINO` references across all 3 plans and their verify blocks.
- Dependencies are numpy + opencv-python-headless only, matching CONTEXT.md §Decisions.
- `projection.py` is enforced cv2-free by an inline runtime check in 11-01 Task 2 verify, a dedicated test `test_projection_module_has_no_cv2` in 11-01 Task 3, and a docstring in the module.

### 13-pitfall coverage — PASS
| Pitfall | Plan / Task | Evidence |
|---|---|---|
| P1 Q3 yaw direction (CCW from +X) | 11-01 Task 2 `world_to_camera`, Task 3 tests `test_world_to_camera_north_facing_north` / `_east_facing_north` / `_yaw_zero_faces_east` | Sign-correct N/E/up assertions cross-check `navigator.py:292` |
| P2 Z-up ↔ Y-down | 11-01 Task 2 `cam_y = -dz + cam_h`, Task 3 `test_world_to_camera_up_maps_to_negative_y` | Explicit negation + pytest assertion |
| P3 Near-plane clip (z≈0) | 11-01 Task 2 `project_line` parametric clip with `NEAR_Z = 0.1`, Task 3 `test_near_clip_both_behind` / `_one_behind_trims` / `_exact_plane_treated_as_behind` | Three clip cases tested |
| P4 GaussianBlur odd kernel | 11-02 Task 1 `k = cfg.glow_radius \| 1`, `test_glow_forces_odd_kernel_with_even_radius` | Forced odd + explicit even-input test |
| P5 cv2 BGR vs RGB | 11-01 Task 1 `OBJECT_COLORS_BGR` (named suffix) + docstring; 11-02 renderer uses BGR consistently | Named convention prevents confusion |
| P6 Float→int rounding | 11-01 Task 2 `int(np.round(sx))`, Task 3 `test_project_point_rounds_not_truncates` | Round-vs-trunc asserted |
| P7 cv2.imshow needs DISPLAY | 11-02 Task 3 `test_render_module_has_no_imshow_reference` + Task 5 checkpoint | Source string-match test |
| P8 opencv-headless strips imshow | 11-03 Task 3 `_try_imshow` wrapper with cv2.error fallback + `--show` opt-in (default is `--save`) | Graceful degradation; demo defaults to video only |
| P9 mp4v codec availability | 11-03 Task 3 `_open_writer` mp4v → MJPG/.avi fallback with `isOpened()` check | Fallback path documented |
| P10 Hershey font only | 11-02 Task 2 `FONT = cv2.FONT_HERSHEY_PLAIN`, `test_hud_uses_hershey_font_only` | Source-string guard against TTF |
| P11 learned_map walls ≠ ground truth | 11-03 Task 2 `aas_backend.py` docstring explicit "DO NOT read from learned_map.py" | Pitfall documented at point-of-use |
| P12 AASArea backward compat | 11-03 Task 1 tuple defaults `(0.0,0.0,0.0)`, `test_aas_area_default_mins_maxs_backward_compat` + full regression suite (`test_navigation`, `test_property_based`, `test_tour_metrics`) in every wave's verify step | Defaulted fields + regression gate |
| P13 `python -m` module path | 11-03 Task 3 `if __name__ == "__main__": main()` + `--help` invocation in verify | Explicit `python -m ... --help` probe |

### 9-assumption handling — PASS
| # | Assumption | Addressed By |
|---|---|---|
| A1 | AASArea 48-byte layout (mins@+12, maxs@+24, center@+36) | 11-03 Task 1 `test_parse_aas_oa_dm1_mins_maxs_contain_center` (mins ≤ center ≤ maxs over all areas, count > 100) + `_bounds_within_map_range` |
| A2 | AASArea dataclass extension backcompat | Tuple defaults + full regression suite run at every wave |
| A3 | Pi 5 cv2.line timing | `--profile` flag in 11-03 demo with p95 reporting, reviewed in human-verify checkpoint |
| A4 | GaussianBlur cost at k=9 | Same `--profile` path |
| A5 | Camera eye-height 40–56 units | RoomConfig field `camera_height = 40.0` plus backend/renderer ctor parameterization |
| A6 | Q3 yaw CCW from +X | navigator.py:292 cross-ref in 11-01 `<interfaces>` block + sign tests |
| A7 | Face-mesh lumps deferred | Explicit scope exclusion; documented lump inventory comment in parser |
| A8 | Default pose inside walkable area | 11-03 Task 3 `_verify_pos_in_walkable_area` via `nearest_area` + AABB containment, logs warning if outside |
| A9 | headless strips imshow | `_try_imshow` graceful fallback + `--show` opt-in |

### Dependency chain & file overlap — PASS
- Waves strictly sequential: 11-01 `depends_on: []`, 11-02 `depends_on: [11-01]`, 11-03 `depends_on: [11-01, 11-02]`.
- Shared file `openarena_perception/visualization/__init__.py` is touched by all 3 plans; edits are purely additive (each wave adds more re-exports), so sequential execution has no conflict.
- No circular / forward references.

### Pi-native performance posture — PASS
- Every verify command is `uv run ...`, matching project convention.
- Demo defaults to video recording (no X11 required), `--show` is opt-in, `--profile` surfaces per-stage timings so any Pi-hardware regressions are visible at the checkpoint.
- Room-frame segments precomputed once in `WireframeRoomRenderer.__init__` rather than per-frame.
- `AASDepthBackend.__init__` precomputes all area edges as ndarray `(N, 24, 3)` for batched numpy transform.

### Scope creep — PASS
- No DA-V2 / torch / neural deps.
- No `item_tour.py` wiring (explicit note in 11-03).
- No `strategic_hud.py` embedding.
- No `wireframe_3d.py` / `wireframe_grid.py` stubs.
- No GroundingDINO or YOLO.
- Face-mesh AAS lump decoding explicitly deferred (documented in parser comment for future phase).

### Rollback — PASS
All 3 plans provide concrete rollback commands (`rm` + `git checkout --`) that do not touch unrelated files.

### World→camera math validation — PASS
11-01 Task 3 asserts the transform at all three canonical bearings requested:
- North (`test_world_to_camera_north_facing_north`) — bot facing N, target N → `(0, 0, 100)`
- East (`test_world_to_camera_east_facing_north`) — bot facing N, target E → `(-100, 0, 0)`
- Up (`test_world_to_camera_up_maps_to_negative_y`) — target Z+ → `(0, -64, 0)`

Plus batched ndarray path + yaw=0 case + camera_height offset.

### Human-verify checkpoint quality — PASS
11-03 Task 5:
- Concrete steps for opening the video (xdg-open / vlc / scp / still-frame extraction via ffmpeg).
- Explicit visual checklist: holodeck frame, gradient colors, HUD elements enumerated, crosshair, corner brackets, bottom bars, glow.
- Red-flag symptoms mapped 1:1 to math pitfalls (P1 yaw sign, P2 Z-up, P3 near clip, P5 BGR, P10 font, A8 pose-inside-area).
- Orbit frame checkpoints at 0°/180°/270° exercise the full yaw math.
- Profile review step covers A3/A4 perf assumptions.
- Clear resume-signal grammar: approved / issues: / reroll pose:X,Y,Z.

---

## Plan-Level Detail

| Plan | Wave | Tasks | Files Modified | Status |
|---|---|---|---|---|
| 11-01 | 1 | 3 auto (tdd) | 5 (subpackage skeleton + projection.py + tests) | Valid |
| 11-02 | 2 | 4 auto (3 tdd + 1 regression) | 7 (effects + hud + renderer + __init__ + 3 test files) | Valid |
| 11-03 | 3 | 4 auto + 1 checkpoint:human-verify (blocking) | 6 (parser ext + aas_backend + demo + __init__ + 2 test files) | Valid |

---

## Optional Improvements (non-blocking)

1. **`math_isfinite` helper in demo (11-03 Task 3)** — the demo defines a local wrapper `math_isfinite` at the bottom of the module that imports `math` inside the function. Minor cosmetic smell; a top-level `import math` and direct `math.isfinite` would be cleaner. Not worth blocking.

2. **Parser regression test naming** — `test_parse_aas_oa_dm1_mins_maxs_contain_center` is good, but an additional assertion that area 0's mins/maxs remain defaulted `(0,0,0)` (dummy area) would document intent more explicitly. Low-value.

3. **Scene-wall depth color continuity** — the renderer's scene-wall draw path uses `project_depth_color(midpoint_z, cfg)`. Because Plan 03 rescales `max_depth` to 2048 and `proximity_threshold` to 64, close walls will correctly flash warning color. Verified correct by inspection. No change needed; flagged only so the executor doesn't forget the rescale when orchestrating.

4. **Optional: add a tiny `test_demo_help_runs` subprocess test** in a future iteration to catch Pitfall 13 regressions in CI without a live AAS file. Currently it's a shell check in the verify block only — acceptable but not ideal.

5. **Frame-counter wraparound** — `WireframeRoomRenderer._frame_counter` increments forever; at ~30 FPS this overflows `%06d` HUD format after ~9 hours of continuous rendering. Purely cosmetic, deferrable indefinitely.

None of these block execution.

---

## Summary

The plan trio is exemplary: goal-backward traceable, pitfall-complete, assumption-pinned, cv2/math cleanly separated, headless-safe, Pi-friendly, backward-compatible with the existing parser, and ending in a high-quality human-verify checkpoint that exercises the full transform pipeline visually. No revisions required.

Proceed to execution with `/gsd-execute-phase 11`.

## CHECK COMPLETE
