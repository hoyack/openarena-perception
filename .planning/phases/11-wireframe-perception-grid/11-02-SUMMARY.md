---
phase: 11-wireframe-perception-grid
plan: 02
subsystem: visualization
tags: [renderer, hud, effects, cv2, holodeck, wireframe, crt, pitfalls-4-5-7-8]
wave: 2
dependency_graph:
  requires:
    - openarena_perception.visualization.RoomConfig
    - openarena_perception.visualization.SceneGeometry
    - openarena_perception.visualization.projection
  provides:
    - openarena_perception.visualization.WireframeRoomRenderer
    - openarena_perception.visualization.effects (apply_glow, apply_scanlines)
    - openarena_perception.visualization.hud (render_hud)
  affects: []
tech_stack:
  added: []
  patterns:
    - "cv2-side modules (renderer/hud/effects) isolated from pure-math modules (projection/config/scene)"
    - "Precomputed room-frame segments at renderer init; fixed in camera space"
    - "Back-to-front segment sort by midpoint z for depth feel"
    - "Odd-kernel forcing via bitwise OR (k | 1) for cv2.GaussianBlur"
key_files:
  created:
    - openarena_perception/visualization/effects.py
    - openarena_perception/visualization/hud.py
    - openarena_perception/visualization/wireframe_room.py
    - tests/test_wireframe_effects.py
    - tests/test_wireframe_hud.py
    - tests/test_wireframe_renderer.py
  modified:
    - openarena_perception/visualization/__init__.py
decisions:
  - "Room-frame segments are precomputed in __init__ and sorted once — they never change with bot pose because the room is in camera space"
  - "Scene walls arrive in camera space already (AAS backend's job in 11-03), so renderer does not call world_to_camera"
  - "Corner brackets use (w - I - 1) to stay inside the frame buffer (avoid off-by-one on right/bottom edge)"
  - "Crosshair writes the exact center pixel after AA lines to guarantee the deterministic pixel-color test"
  - "Renderer returns a new frame each call (np.full) — no buffer reuse, keeps tests independent and avoids stale glow/HUD state"
metrics:
  duration: ~10 min
  tasks_completed: 4
  tests_added: 21
  tests_runtime: 5.97s
  commits: 3
  completed: 2026-04-10
---

# Phase 11 Plan 02: Renderer + HUD + Effects Summary

One-liner: `WireframeRoomRenderer` turns any `SceneGeometry` into a holodeck-styled BGR frame — 5-plane room frame, depth-faded walls, per-class wireframe cubes, CRT glow/scanlines, full PRD §6.1 HUD — all opencv-python-headless safe with 21 new tests that never open a window.

## What Was Built

Wave-2 of Phase 11 Version B. Consumes the pure-math library from 11-01 and the `RoomConfig`/`SceneGeometry` dataclasses, produces a finished frame ready for video writing, streaming, or visual inspection.

1. **`openarena_perception/visualization/effects.py`** — CRT post-processing:
   - `apply_glow(frame, cfg)` — Gaussian blur + additive composite (`cv2.addWeighted`). Kernel size forced odd via `k = cfg.glow_radius | 1` (Pitfall 4). Zero-radius and zero-strength are no-ops. Returns a new frame.
   - `apply_scanlines(frame, cfg)` — numpy multiplicative row-mask darkening every `scanline_spacing`-th row by `scanline_strength`. Preserves uint8.

2. **`openarena_perception/visualization/hud.py`** — PRD §6.1 overlay in place:
   - Top-left fixed block: `FRAME NNNNNN`, `ROOM WxHxD`, `FOV nn GRID GxGxG`, `MODE: …`, `OBJECTS: N`
   - `extra_hud` dict field rendered below fixed block (capped at 10 entries) for bot-state integration
   - Crosshair at center (accent color; center pixel written explicitly after AA)
   - Bottom-left status bar: `// SPATIAL GRID ACTIVE` or `state['status_text']`
   - Bottom-right source resolution: `SRC WxH`, right-aligned via `cv2.getTextSize`
   - 4 L-shaped corner brackets, 20 px arms, 3 px inset, `grid_color`
   - Font: `cv2.FONT_HERSHEY_PLAIN` at scale 0.9 (Pitfall 8 — no TTF/freetype)
   - Honors `cfg.hud=False` by returning the frame unmodified

3. **`openarena_perception/visualization/wireframe_room.py`** — `WireframeRoomRenderer` class:
   - `__init__(cfg)` — precomputes the 5-plane room frame via `projection.room_surface_grid` once (floor, ceiling, left/right walls, back wall in PRD §4.2 camera-space convention), sorts back-to-front by midpoint z
   - `render(bot_pos, bot_yaw, scene, extra_hud=None, state=None) -> np.ndarray` — returns a fresh `(H, W, 3)` uint8 BGR frame
   - Draw order: bg fill → room frame → scene walls (sorted) → scene boxes (per-class color from `OBJECT_COLORS_BGR`, fallback `unknown`) → glow → scanlines → HUD
   - Every segment is projected via `projection.project_line` — `None` returns (fully behind near plane) are skipped, so walls behind the camera simply vanish
   - Integer-coerced endpoints into `cv2.line` with `cv2.LINE_AA`
   - Frame counter advanced per call, merged into HUD `state` alongside live `object_count`
   - Zero `cv2.imshow` (enforced by test)

4. **`openarena_perception/visualization/__init__.py`** — extended to re-export `WireframeRoomRenderer`.

5. **21 new headless tests** across 3 files:
   - `test_wireframe_effects.py` (5) — glow spreads a bright pixel, glow forces odd kernel with even radius, glow zero-radius is noop, scanlines darken every nth row, scanlines preserve uint8
   - `test_wireframe_hud.py` (8) — top-left block non-bg, crosshair center pixel exact color, all 4 corner brackets non-bg, extra_hud field rendering, bottom-right source res, `cfg.hud=False` noop, FONT_HERSHEY only / no freetype / no truetype, package export sanity
   - `test_wireframe_renderer.py` (8) — shape/dtype, empty scene still draws room frame, wall in front adds pixels, wall behind camera culled (frame-identical), `player` box color close-match, glow changes output vs no-glow, no `cv2.imshow` in source, HUD object count reflected in top-left differential

## Pitfalls Addressed

| Pitfall | How |
|---|---|
| P4 — Divide-by-zero at z≈0 | Already handled in `project_line` (11-01); renderer skips `None` returns so fully-clipped segments vanish |
| P5 — BGR vs RGB at cv2 boundary | `OBJECT_COLORS_BGR` constant with explicit `_BGR` suffix, passed straight to `cv2.line` |
| P7 — cv2.GaussianBlur odd kernel | `apply_glow` forces `k = cfg.glow_radius \| 1` |
| P8 — Font file bundling | `cv2.FONT_HERSHEY_PLAIN` only; test scans hud.py source for `freetype`/`truetype` substrings |
| P10 — cv2.VideoWriter codec | Not exercised in this plan (deferred to 11-03 demo) |

## Key Decisions

1. **Room frame precomputed in `__init__`** — the holodeck frame is fixed in camera space (camera at origin looking +Z). It never changes per frame, so tessellating it once saves thousands of `room_surface_grid` calls over a 30 FPS run.
2. **Back-to-front z-sort** — simple painter's-algorithm depth feel without a z-buffer; cheap on Pi and visually correct for the wireframe aesthetic where far grid lines should sit behind near ones.
3. **Renderer does not call `world_to_camera`** — scene walls arrive already in camera space. The AAS backend (11-03) owns the world→camera transform. This keeps 11-02 fully testable with hand-crafted scenes and zero navigation dependency.
4. **Corner brackets use `w - I - 1` / `h - I - 1`** — `cv2.line` is exclusive on the right/bottom edge at some anti-alias configurations. Offsetting by 1 keeps the bracket fully inside the buffer so the 4-corner test sees pixels in every corner slice.
5. **Crosshair writes center pixel explicitly** — AA lines can soften the center pixel to a partial accent color. Overwriting `frame[cy, cx]` after the lines is a cheap guarantee for the deterministic HUD test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] HUD docstring tripped the font-file test**
- **Found during:** Task 2 first test run
- **Issue:** The initial docstring contained the words "TrueType or freetype" as prose explaining what the file does NOT use. The `test_hud_uses_hershey_font_only` test does a plain substring check on the source and matched `freetype`.
- **Fix:** Rewrote the docstring to say "No external font files are referenced" without naming the forbidden libraries.
- **Files modified:** `openarena_perception/visualization/hud.py`
- **Commit:** `49d7386`

**2. [Rule 1 — Bug] Renderer docstring tripped the `cv2.imshow` test**
- **Found during:** Task 3 first test run
- **Issue:** The docstring said "no cv2.imshow (tests enforce this)". The `test_render_module_has_no_imshow_reference` test substring-matched the docstring.
- **Fix:** Reworded to "no GUI calls (tests enforce this)".
- **Files modified:** `openarena_perception/visualization/wireframe_room.py`
- **Commit:** `8a6b046`

Both are the same shape: the test is a cheap source-text scan, not an AST walk, so any prose that names the forbidden symbol counts. Future plans should phrase docstring warnings without the literal forbidden string.

## Auth Gates

None — fully autonomous plan.

## Tests

- **New:** 21 tests in 3 files (effects/hud/renderer).
- **Regression:** 11-01's 30 projection tests still green. Legacy `test_navigation`, `test_property_based`, `test_tour_metrics` all green.
- **Combined suite run:** `uv run pytest tests/test_wireframe_projection.py tests/test_wireframe_effects.py tests/test_wireframe_hud.py tests/test_wireframe_renderer.py tests/test_navigation.py tests/test_property_based.py tests/test_tour_metrics.py -q` → **88 passed in 5.97s**.
- **Smoke render:** `WireframeRoomRenderer(RoomConfig()).render((0,0,0), 0.0, SceneGeometry(walls=(((-2,0,10),(2,0,10)),)))` → shape `(600, 960, 3)`, dtype `uint8`, non-zero sum 27,668,858 (holodeck frame + wall + HUD + glow).

## Commits

| Task | Message | Hash |
|---|---|---|
| 1 | feat(11-02): add glow and scanline CRT effects | `fcec5a3` |
| 2 | feat(11-02): add HUD overlay with PRD section 6.1 elements | `49d7386` |
| 3 | feat(11-02): add WireframeRoomRenderer holodeck renderer | `8a6b046` |

## Discoveries Affecting Wave 3 (11-03)

1. **Scene walls must arrive in camera space.** The renderer does NOT call `world_to_camera`. Plan 11-03's `AASDepthBackend.build_scene()` must run the Q3 world → camera transform itself (using `projection.world_to_camera` — the batched `(N, 3)` path is the efficient route).
2. **`camera_height` lives on `RoomConfig`** (default 40.0). The backend should pass it through as `world_to_camera(..., camera_height=cfg.camera_height)`.
3. **Room frame dimensions are too small for Q3 units by default.** `RoomConfig` defaults to `room_width=10, room_height=6, room_depth=20` which is correct for synthetic tests but will be dwarfed by AAS walls in Q3 units (hundreds per tile). Plan 11-03 should construct a custom config with `replace(cfg, room_width=1024, room_height=512, room_depth=2048, max_depth=2048)` or similar for the AAS demo. The plan text already hints at this.
4. **Renderer sorts scene walls every frame.** If 11-03 pushes hundreds of AAS segments per tick the sort is cheap but worth noting — Python `sorted` on a list-of-tuples at N=1000 is sub-millisecond on Pi 5.
5. **Box tuple format is `(class, x, y, z, w, h, d)` with `(x,y,z)` as CENTER and `(w,h,d)` as full extents** (matches `cube_edges`). The backend must follow this convention when emitting detected-object boxes.
6. **`OBJECT_COLORS_BGR.get(cls, OBJECT_COLORS_BGR["unknown"])` fallback is in place** — 11-03 does not need to pre-validate class names.
7. **Frame counter is internal state on the renderer.** A new `WireframeRoomRenderer` instance per call would reset `FRAME 000000`. Plan 11-03's demo script must hold ONE renderer across the loop.

## Known Stubs

None. Every method is fully implemented and tested. The only deferred behavior is the AAS-driven scene construction, which is explicitly Plan 11-03's scope.

## Self-Check: PASSED

**Files created:**
- FOUND: `openarena_perception/visualization/effects.py`
- FOUND: `openarena_perception/visualization/hud.py`
- FOUND: `openarena_perception/visualization/wireframe_room.py`
- FOUND: `tests/test_wireframe_effects.py`
- FOUND: `tests/test_wireframe_hud.py`
- FOUND: `tests/test_wireframe_renderer.py`

**Files modified:**
- FOUND: `openarena_perception/visualization/__init__.py` (re-exports `WireframeRoomRenderer`)

**Commits:**
- FOUND: `fcec5a3` (Task 1 — effects)
- FOUND: `49d7386` (Task 2 — hud)
- FOUND: `8a6b046` (Task 3 — renderer)

**Verification gates:**
- `uv run pytest tests/test_wireframe_effects.py -x -q` → 5 passed
- `uv run pytest tests/test_wireframe_hud.py -x -q` → 8 passed
- `uv run pytest tests/test_wireframe_renderer.py -x -q` → 8 passed
- Full wireframe + legacy regression (88 tests) → all passed in 5.97s
- Smoke import + render → `(600, 960, 3)` uint8, sum 27,668,858
