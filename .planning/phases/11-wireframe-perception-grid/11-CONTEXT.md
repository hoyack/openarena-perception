# Phase 11: Wireframe Perception Grid — Context

**Gathered:** 2026-04-10
**Status:** Ready for planning
**Source:** PRD Express Path (.planning/phases/11-wireframe-perception-grid/11-PRD.md)

<domain>
## Phase Boundary

This phase delivers a **first-person holodeck-style 3D wireframe debug view** of what the bot "sees" spatially. It is a **visualization / observability layer**, not a gameplay behavior change.

**Three outcomes:**

1. **A renderer module** — `wireframe_room.py` — that builds a perspective-correct wireframe room (5 grid planes: floor, ceiling, left/right walls, back wall) converging to a vanishing point, with depth-faded grid lines and CRT-style glow/scanline effects. Output is a BGR frame suitable for `cv2.imshow`, video recording, or network streaming.

2. **An obstacle overlay system** — detected objects (players, pickups, doors, static geometry) projected from 2D screen-space detections into the 3D room volume using depth samples, rendered as color-coded wireframe boxes. Plus a depth-contour "sonar ping" mode when no discrete detections are available, showing raw depth surface as floating scan lines.

3. **A HUD/telemetry overlay** — frame counter, room/FOV/grid stats, mode indicator, object count, crosshair, status bar, source resolution, corner brackets. Plus an `extra_hud` dict that accepts live bot state (mode, HP, ammo, target, pos, yaw) from the existing perception/game-state pipeline.

**Secondary deliverables (alternate modes per PRD §12):**
- `wireframe_3d.py` — surface mesh renderer (depth map as 3D wireframe surface)
- `wireframe_grid.py` — 2D depth-warped grid (legacy/simple mode)

These are optional alternate visualizations; `wireframe_room.py` is the primary module.

## What's in scope

- Depth estimation integration via **Depth Anything V2** (`depth-anything-v2` package + pytorch), with the `vits` (small, 25M) model as the real-time default. Config exposes `vits`/`vitb`/`vitl` switching.
- `RoomConfig` dataclass with all rendering parameters (dimensions, grid density, FOV, camera offsets, colors, effects toggles)
- Pinhole-camera perspective projection (`fx = width / (2 * tan(FOV/2))`, FOV default 90° matching OpenArena default)
- Depth-based line coloring: near-warning / mid-interpolated / far-faded with `(z/max_z)^fade_power` curve
- 12-edge axis-aligned wireframe cube renderer for obstacle boxes with per-class color mapping (player/pickup/door/wall/unknown)
- `screen_to_room()` unprojection function turning 2D bboxes + depth samples into room-space boxes
- Depth contour projection mode (`render_depth_contours`) for when no discrete detections are available — vertical segments at column intervals, horizontal scan lines between columns
- HUD overlay rendering with all the PRD-specified elements plus the `extra_hud` integration point
- Optional glow/bloom effect (gaussian blur alpha-composited) and optional scanlines effect
- Integration with the existing `openarena_perception` tick loop: takes depth map + 2D detections + game_state, returns a frame
- Video recording support via `cv2.VideoWriter` (mp4v, 30 FPS, 960×600)
- Unit tests for: projection math (pinhole transform), `screen_to_room` unprojection, `RoomConfig` defaults, depth color interpolation curve, wireframe box edge generation, room surface parameterization
- A runnable demo/smoke script that renders a single frame from a static depth map + synthetic obstacles (no live game needed)

## What's out of scope

- **GPU/CUDA real-time 30+ FPS operation** — this phase does NOT mandate Pi-real-time integration into the live perception loop. The Pi performance issue is documented as a known constraint and deferred to integration work in a later phase. See "Pi Performance Constraint" below.
- **Bastion Bridge / multi-agent gateway rendering** — the PRD §8.3/§8.4 mention this as integration ideas; this phase delivers the renderer module and single-machine support only. Gateway offload is future work.
- **OpenGL/Vulkan renderer** — PRD §10.5; stays CV2/numpy for this phase.
- **Accumulated world map / voxel grid / trajectory visualization / minimap inset / sound localization** — PRD §10.1-§10.4 are explicit future extensions, not this phase.
- **GroundingDINO object detection integration** — PRD mentions it as an option; stick with the existing pytesseract HUD parser + any pre-existing YOLO path the project already has. No new detection model added.
- **ultralytics/YOLO adoption** — only if the project already uses it; don't add a new dep.
- **Wiring into `item_tour.py` live loop** — the renderer must be importable and runnable standalone with a fake depth map. Live integration is demonstrated via the demo script, not hard-wired into the tour script.
- **Metric depth calibration** — DA-V2 output is relative, not metric. The renderer treats it as relative and normalizes 0–1 internally. No absolute-distance accuracy claims.

## Pi Performance Constraint (load-bearing decision)

**This is the biggest tension with the project's CLAUDE.md stack.** The PRD assumes a CUDA-capable GPU for real-time depth inference (~10ms on a 4090). Our project runs on Raspberry Pi 5, which can do DA-V2 `vits` at ~2–5 FPS on CPU at best. This phase **does not attempt to solve the Pi perf problem**.

Instead:
- The renderer module is **GPU-agnostic** — it consumes depth maps, it doesn't care where they came from
- Depth inference is **optional** at runtime — the renderer works with any source of depth data (cached maps, synthetic depth, slow Pi inference, or network-received depth from a gateway)
- Documentation clearly states: this phase ships the renderer; Pi-real-time integration is a separate future phase (likely requires Bastion Bridge offload or much-smaller custom depth model)
- The demo/smoke script runs on Pi using a **cached or synthetic depth map** so CI and development work without GPU
- `torch` + `depth-anything-v2` are **optional dependencies** — importable, wired, but not required for the renderer unit tests to pass. Tests mock the depth inference.

This decision preserves the project's "must maintain 10+ FPS perception loop" constraint by NOT forcing depth inference into the hot path this phase.

</domain>

<decisions>
## Implementation Decisions

### Module Layout

All new code lives under a new subpackage: `openarena_perception/visualization/`.

- `openarena_perception/visualization/__init__.py` — exposes `WireframeRoomRenderer`, `RoomConfig`, `screen_to_room`, object-class color constants
- `openarena_perception/visualization/wireframe_room.py` — primary renderer (PRIMARY module per PRD §12)
- `openarena_perception/visualization/wireframe_3d.py` — surface mesh mode (secondary)
- `openarena_perception/visualization/wireframe_grid.py` — 2D depth-warped grid (secondary)
- `openarena_perception/visualization/depth_backend.py` — Depth Anything V2 wrapper (lazy import of torch/depth_anything_v2), plus a `FakeDepthBackend` for tests/demo
- `openarena_perception/visualization/projection.py` — pure-function pinhole projection helpers (testable without OpenCV window)

Placing under `visualization/` keeps the concern isolated and matches the brain-inspired subsystem layout from v1.0 phases.

### RoomConfig (exact shape per PRD §4.5)

`@dataclass(frozen=True, slots=True)` per project convention (see `openarena_perception/models.py` SituationalAwareness pattern).

Fields (all defaults per PRD):
- `width: int = 960`, `height: int = 600`
- `room_width: float = 10.0`, `room_height: float = 6.0`, `room_depth: float = 20.0`
- `grid_lines_x: int = 16`, `grid_lines_y: int = 10`, `grid_lines_z: int = 20`
- `fov_deg: float = 90.0`
- `cam_x: float = 0.0`, `cam_y: float = 0.0`, `cam_z: float = 0.0`
- `bg_color: tuple[int,int,int] = (0, 0, 0)`
- `grid_color: tuple[int,int,int] = (180, 180, 180)`
- `accent_color: tuple[int,int,int] = (0, 255, 100)`
- `near_color: tuple[int,int,int] = (255, 255, 255)`  # added by planner — not in PRD, needed by §4.4
- `far_color: tuple[int,int,int] = (40, 60, 80)`      # added by planner — needed by §4.4
- `warning_color: tuple[int,int,int] = (0, 80, 255)`  # added for near-obstacle warning per §4.4
- `proximity_threshold: float = 2.0`                   # units; added for §4.4
- `fade_power: float = 0.6`                            # added for §4.4 curve
- `glow: bool = True`, `scanlines: bool = False`, `hud: bool = True`
- `glow_radius: int = 9`, `glow_strength: float = 0.3`  # per §7.1
- `scanline_spacing: int = 3`, `scanline_strength: float = 0.15`  # per §7.2

### Projection math (pure function module)

`openarena_perception/visualization/projection.py` exports:

- `focal_length(width: int, fov_deg: float) -> float` — `width / (2 * tan(radians(fov_deg/2)))`
- `project_point(x: float, y: float, z: float, cfg: RoomConfig) -> tuple[int, int] | None` — returns `None` if z <= 0.1 (behind camera); otherwise `(px, py)` via pinhole with cx=width/2, cy=height/2
- `project_line(p1, p2, cfg) -> tuple[tuple[int,int], tuple[int,int]] | None` — clips to near plane; returns None if both endpoints behind camera
- `room_surface_grid(origin, axis_u, axis_v, divs_u, divs_v) -> list[tuple[p1, p2]]` — generates line segments tessellating a parametric quad; returns (divs_u+1) U-lines + (divs_v+1) V-lines

These are pure; testable without any cv2 call.

### Depth-line coloring (pure function)

`project_depth_color(z: float, cfg: RoomConfig) -> tuple[int,int,int]`:
- If `z < cfg.proximity_threshold`: return `cfg.warning_color`
- Else: `t = min(1.0, (z / cfg.room_depth) ** cfg.fade_power)`; interpolate linearly between `cfg.near_color` (t=0) and `cfg.far_color` (t=1)

Tested independently.

### `screen_to_room()` unprojection

Lives in `projection.py`. Signature per PRD §5.1:
```python
def screen_to_room(
    bbox_2d: tuple[int, int, int, int],
    depth_map: np.ndarray,
    cfg: RoomConfig,
) -> tuple[float, float, float, float, float, float]
```
Returns `(room_x, room_y, z, box_w, box_h, box_d)`. Samples depth at bbox center. Clamps pixel coords to depth_map bounds. `box_d = box_w * 0.5` per PRD. Uses `cfg.room_depth` to scale normalized depth → room-space Z.

### Wireframe cube generator

`cube_edges(x, y, z, w, h, d) -> list[tuple[p1_3d, p2_3d]]` — returns 12 line segments for an axis-aligned box.

### Object class colors (per PRD §5.2, exact)

```python
OBJECT_COLORS = {
    "player":   (255, 50, 50),
    "pickup":   (50, 255, 255),
    "door":     (255, 255, 50),
    "portal":   (255, 255, 50),
    "wall":     (0, 255, 100),
    "static":   (0, 255, 100),
    "unknown":  (180, 180, 180),
}
```

### Depth contour projection (PRD §5.3)

Method `render_depth_contours(depth_map, cfg, num_columns=24, num_rows=12)`:
- Sample depth at `num_columns` evenly-spaced column positions
- At each column, compute mean depth in that column → `z_col`
- Draw a vertical line segment at `(room_x_for_column, floor, z_col)` → `(room_x_for_column, ceiling, z_col)`
- Draw horizontal scan lines at `num_rows` equal Y-intervals connecting adjacent columns at their Z
- Lines colored via `project_depth_color(z, cfg)`

### HUD Overlay (per PRD §6.1 exact)

`render_hud(frame: np.ndarray, cfg: RoomConfig, state: dict, extra_hud: dict | None)`:
- Top-left: `FRAME {tick:06d}`, `ROOM {W}x{H}x{D}`, `FOV {fov}  GRID {gx}x{gy}x{gz}`, `MODE: {mode}`, `OBJECTS: {n}`
- Center: simple crosshair (20px lines)
- Bottom-left: `// SPATIAL GRID ACTIVE`
- Bottom-right: `SRC {src_w}x{src_h}` (uses depth_map shape)
- All 4 corners: `L`-shaped brackets (DOS chrome)
- Below standard HUD rows: render each `extra_hud` key-value pair on its own line in the same accent color

Font: `cv2.FONT_HERSHEY_PLAIN` at scale 0.9 (monospace-ish, small, matches the aesthetic). No custom fonts.

### Visual Effects (per PRD §7)

**Glow/Bloom:**
- `cv2.GaussianBlur(frame, (cfg.glow_radius|1, cfg.glow_radius|1), 0)`
- `cv2.addWeighted(frame, 1.0, blurred, cfg.glow_strength, 0)`
- Applied after all line drawing, before scanlines

**Scanlines:**
- Create black horizontal mask at `cfg.scanline_spacing` intervals
- `cv2.addWeighted(frame, 1.0 - cfg.scanline_strength, mask, cfg.scanline_strength, 0)`

**Depth fade** is already handled by `project_depth_color`; no post-processing step.

### Depth backend abstraction

`openarena_perception/visualization/depth_backend.py`:

```python
class DepthBackend(Protocol):
    def infer(self, frame: np.ndarray) -> np.ndarray: ...  # HxW float32

class FakeDepthBackend:
    """Returns a fixed synthetic depth map. Used by tests + Pi-safe demo."""
    def __init__(self, shape=(480, 640)): ...
    def infer(self, frame): ...

class DepthAnythingV2Backend:
    """Real Depth Anything V2 wrapper. torch/depth_anything_v2 imported lazily in __init__."""
    def __init__(self, model_size="vits", device="cuda", checkpoint_path="..."): ...
    def infer(self, frame): ...
```

The renderer accepts either — it only depends on the `DepthBackend` Protocol. Unit tests use `FakeDepthBackend` exclusively.

**Import strategy:** `torch` and `depth_anything_v2` are imported inside `DepthAnythingV2Backend.__init__` with a try/except that raises a clear "install torch + depth-anything-v2 to use this backend" error. This keeps the renderer module importable on Pi without the heavy deps present.

### Dependency policy (load-bearing)

- **Add** `torch` and `depth-anything-v2` as **optional dependencies** via `pyproject.toml` optional-dependencies group `visualization-gpu` (or equivalent uv syntax)
- **Do NOT add** them to the default install. Pi installs stay lean.
- **numpy**, **opencv-python** are already in the stack — no new core deps
- Document install instructions in the demo script header

### Demo script

`openarena_perception/visualization/demo_wireframe_room.py`:
- CLI args: `--depth-source {fake, file, live}`, `--save {path.mp4}`, `--loop`, `--duration {seconds}`
- Default: `--depth-source fake --duration 5` — renders 150 frames of synthetic scene (fake depth + synthetic obstacles) and either shows via `cv2.imshow` or writes to `./tmp/wireframe_demo.mp4`
- `file` mode: loads a depth map from disk (numpy `.npy`)
- `live` mode: spawns DA-V2 backend + mss screen capture (requires full optional deps) — this is the integration preview, not wired to item_tour
- Runnable on Pi with `--depth-source fake`

### Tests (headless, no display required)

`tests/test_wireframe_projection.py` — pinhole math, room_surface_grid, cube_edges, project_depth_color, screen_to_room
`tests/test_wireframe_renderer.py` — renders a known fixture scene with FakeDepthBackend into a numpy frame, asserts specific pixels are the expected color (not a golden-file comparison, just spot checks)
`tests/test_wireframe_depth_backend.py` — FakeDepthBackend returns correct shape/dtype; DepthAnythingV2Backend import error has a clear message when deps are missing
`tests/test_wireframe_hud.py` — HUD renders into a blank frame, asserts text regions have non-bg pixels

All tests use headless mode (`cv2.imwrite` or direct array assertions, no `cv2.imshow`). Run via `uv run pytest tests/test_wireframe*.py -q`.

### Integration point into existing code

**Minimal wiring into item_tour.py** — NONE in this phase. The integration is a demo script only. Item_tour integration is deferred to a future phase.

**Soft integration into strategic_hud.py** — NONE. The wireframe view is a separate window/executable, not embedded in the existing pygame HUD.

The existing `openarena_perception/perception/` modules (game_state, hud_parser) are consumed by the demo as-is via their public API — no modifications.

### Claude's Discretion

- Exact pyproject.toml optional-deps syntax (uv-specific vs PEP 621 standard — use whatever matches existing file)
- Line-drawing order (draw back-wall-first for depth-sorting, or just z-sort all segments — pick based on simplicity)
- Glow kernel size parity handling (OpenCV requires odd kernel sizes)
- Whether `wireframe_3d.py` and `wireframe_grid.py` are thin stubs that delegate to `wireframe_room.py` or independent renderers — preference: stubs with `NotImplementedError` for this phase and full implementations deferred
- Checkpoint file storage for DA-V2 weights — download path vs manual instructions (preference: document manual download in demo script header, don't auto-download)
- Whether to add a `pytest.ini` marker for "requires-torch" tests — probably not, just skip if torch import fails via `pytest.importorskip`
- Font size and exact pixel positions for HUD elements within PRD §6.1 guidelines — use tasteful defaults
- Whether `render()` method takes kwargs or a single `RenderInput` dataclass — preference: kwargs for ergonomics, dataclass for the demo CLI

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project instructions and constraints
- `CLAUDE.md` — project tech stack (numpy, opencv-python-headless, mss already present), hardware target (Pi 5, 10+ FPS perception loop), package manager (uv), lint (ruff), tests (pytest + pytest-asyncio)
- `.planning/STATE.md` — current project state, milestone v1.0 verifying, Phase 10 code merged pending human verify
- `.planning/phases/11-wireframe-perception-grid/11-PRD.md` — the source PRD this CONTEXT.md was generated from; MUST be cross-referenced for any detail not captured here

### Existing perception infrastructure (integration consumers)
- `openarena_perception/perception/capture.py` — mss screen capture (existing, reuse)
- `openarena_perception/perception/hud_parser.py` — pytesseract HUD parser (existing, reuse for extra_hud data)
- `openarena_perception/perception/pipeline.py` — PerceptionPipeline orchestrator (how modules plug into the tick budget — reference only; no modifications this phase)
- `openarena_perception/perception/models.py` — SituationalAwareness shape; game state can be converted to extra_hud dict
- `openarena_perception/models.py` — frozen+slotted dataclass convention; RoomConfig follows this

### Depth Anything V2 reference
- https://github.com/DepthAnything/Depth-Anything-V2 — canonical repo; check README for latest install/checkpoint instructions
- License check: Apache-2.0 for `vits` (safe for this project); CC-BY-NC-4.0 for `vitb`/`vitl`/`vitg` (non-commercial — acceptable since this is a research/debug tool)

### DepthFM alternative (optional benchmark target)
- https://github.com/CompVis/depth-fm — research claim of single-step inference via flow matching

### Existing build/test infrastructure
- `pyproject.toml` — uv dependency declaration; optional-dependencies group pattern
- `tests/conftest.py` — pytest fixtures (reference for mocking patterns)

</canonical_refs>

<specifics>
## Specific Ideas

### User-stated acceptance criteria (from PRD §1 + inline discussion)

1. **Aesthetic target is explicit**: Battlezone (1980), TRON lightcycle grid, or the Danger Room — holodeck perspective room with receding wireframe grid planes converging to a vanishing point
2. **Green accent color** for obstacle overlays (default `(0, 255, 100)`) — matches TRON/Matrix aesthetic
3. **Depth-fade from bright near → dim far** provides natural depth cue even without color monitors
4. **HUD chrome is DOS-style** — frame counters, corner brackets, monospace-ish font, status bars
5. **Crosshair at center** — simple cross, not reticle
6. **OpenArena FOV is 90°** — camera FOV should match game FOV for geometric accuracy

### Exact PRD sections → deliverables

- §3 → `depth_backend.py` module + optional deps
- §4.1-4.2 → `wireframe_room.py` room geometry
- §4.3 → `projection.py` pinhole
- §4.4 → `project_depth_color` in `projection.py`
- §4.5 → `RoomConfig` dataclass
- §5.1-5.2 → `screen_to_room` + `cube_edges` + `OBJECT_COLORS` constant
- §5.3 → `render_depth_contours` method
- §6 → `render_hud` method
- §7 → glow/scanline/fade effects
- §8.1 → demo script
- §8.2 → demo script `--save` flag
- §8.3, §8.4, §10.* → explicitly deferred (see Deferred Ideas)
- §9 → performance targets documented; wireframe render itself is <3ms CPU budget (Pi-achievable); depth inference is NOT this phase's responsibility
- §11 → pyproject.toml optional-deps
- §12 → three files; `wireframe_room.py` is primary, other two are stubs this phase

### Execution order preference

- **Plan 11-01**: Pure projection math module + RoomConfig + tests (zero external deps, all numpy)
- **Plan 11-02**: WireframeRoomRenderer + HUD + effects + renderer tests (builds on 11-01, uses cv2 + FakeDepthBackend)
- **Plan 11-03**: DepthAnythingV2 backend + demo script + optional-deps wiring + stubs for wireframe_3d.py / wireframe_grid.py

3 plans, sequential wave dependencies. Each plan atomic, each delivers testable value.

</specifics>

<deferred>
## Deferred Ideas

### Explicit deferrals from PRD §10

- **§10.1 Accumulated World Map** — voxel grid / occupancy map that accumulates over time. Future phase (likely Phase 12+) pairing with nav/pathfinding.
- **§10.2 Trajectory Visualization** — planned path + predicted enemy positions as wireframe lines inside the room. Future phase after threat tracking.
- **§10.3 Minimap Overhead View** — top-down orthographic wireframe inset. Could merge with Phase 10 HUD minimap as a separate mode.
- **§10.4 Sound Localization** — expanding wireframe rings for audio cues. Requires an audio analysis pipeline that doesn't exist yet.
- **§10.5 Real-Time OpenGL Renderer** — migrate CV2 line drawing to OpenGL/Vulkan with detached camera for spectating from any angle. Future phase; keep CV2 for now.

### Deferrals introduced during context gathering

- **Pi-real-time integration into `item_tour.py` perception loop** — the Pi can't run DA-V2 at the required 10+ FPS. Deferred until either: (a) a smaller custom depth model exists, or (b) Bastion Bridge gateway offload is implemented. This phase ships the renderer; Pi integration is future work.
- **Bastion Bridge / gateway streaming (PRD §8.3)** — requires network infrastructure that doesn't exist yet. Future phase.
- **Multi-agent fleet dashboard (PRD §8.4)** — requires multi-bot setup. Not planned for current milestone.
- **GroundingDINO integration** — PRD mentions as option; not added this phase.
- **ultralytics/YOLO addition** — only if already present; don't introduce as new dep.
- **Metric depth calibration** — DA-V2 output is relative; no metric accuracy claim.
- **Full implementations of `wireframe_3d.py` and `wireframe_grid.py`** — these are listed in PRD §12 as alternate modes. This phase ships stubs; full implementations deferred.
- **Auto-download of DA-V2 checkpoints** — manual download documented in demo script header.

</deferred>

---

*Phase: 11-wireframe-perception-grid*
*Context gathered: 2026-04-10 via PRD Express Path (.planning/phases/11-wireframe-perception-grid/11-PRD.md)*
