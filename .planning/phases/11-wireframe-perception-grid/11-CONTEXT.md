# Phase 11: Wireframe Perception Grid — Context

**Gathered:** 2026-04-10
**Status:** Ready for planning
**Source:** PRD (11-PRD.md) with Version B pivot — AAS-driven depth source instead of neural inference

<domain>
## Phase Boundary

This phase delivers a **first-person holodeck-style 3D wireframe debug view** of what the bot "sees" spatially. It is a **visualization / observability layer**, not a gameplay behavior change.

### The Version B pivot (load-bearing scope decision)

The original PRD (see 11-PRD.md) assumes Depth Anything V2 (DA-V2) monocular neural depth estimation as the depth source. Analysis during context gathering established that DA-V2 inference is the only Pi-hostile component in the entire pipeline (~200-500ms/frame on Pi 5 CPU = 2-5 FPS, vs. 5-15ms/frame for everything else combined).

**We pivot the depth source from DA-V2 to AAS geometry projection.** The bot already has ground-truth 3D wall geometry from the AAS file — it uses it for navigation. Projecting AAS geometry into the current camera view via pinhole math gives us:

- Zero new dependencies (no torch, no depth-anything-v2, no model checkpoints)
- Zero neural inference cost — pure numpy matrix math, Pi-native full-speed
- Metric-accurate depth (AAS is ground truth, DA-V2 is relative)
- **Actually visualizes what the bot perceives** — the bot uses AAS for nav, so AAS-sourced depth matches the bot's mental model, not a neural net's guess
- All of the PRD's aesthetic goals (holodeck grid room, wireframe obstacles, CRT HUD chrome, depth-faded lines) are preserved unchanged

DA-V2 moves to the deferred ideas list as a future "neural vision mode" alternative backend, kept as an option but not a requirement.

### Three outcomes

1. **A renderer module** — `wireframe_room.py` — that builds a perspective-correct wireframe room (5 grid planes: floor, ceiling, left/right walls, back wall) converging to a vanishing point, with depth-faded grid lines and CRT-style glow/scanline effects. Output is a BGR frame suitable for `cv2.imshow`, video recording, or network streaming.

2. **An AAS-driven depth/geometry backend** that queries nearby AAS areas relative to the bot's current position + yaw, extracts wall segments and area bounds, and projects them into camera-space as 3D line primitives. The renderer draws these as wireframe lines, color-coded by distance. Detected objects (players, pickups) are overlaid as color-coded wireframe boxes at their known positions.

3. **A HUD/telemetry overlay** per PRD §6 — frame counter, room/FOV/grid stats, mode indicator, object count, crosshair, status bar, source resolution, corner brackets. Plus an `extra_hud` dict that accepts live bot state (mode, HP, ammo, target, pos, yaw) from the existing perception pipeline.

## What's in scope

- **AAS geometry projection backend** — new module that takes the bot's pose + AAS graph and emits 3D line primitives ready for projection
- `WireframeRoomRenderer` class — consumes pose + scene (3D lines + 3D boxes) and produces a BGR frame
- `RoomConfig` dataclass with all rendering parameters per PRD §4.5 (dimensions, grid density, FOV, camera offsets, colors, effects toggles)
- Pinhole-camera perspective projection (`fx = width / (2 * tan(FOV/2))`, FOV default 90° matching OpenArena default)
- Room geometry per PRD §4.2: 5 parametric quads (floor, ceiling, left/right walls, back wall) tessellated into `divs_u × divs_v` grids — these form the **holodeck frame** around the scene, independent of AAS content
- Depth-based line coloring per PRD §4.4: near-warning / mid-interpolated / far-faded with `(z/max_z)^fade_power` curve
- Pure-function projection helpers (`projection.py`) with `focal_length`, `project_point`, `project_line`, `room_surface_grid`, `project_depth_color`, `cube_edges`, `screen_to_room`
- 12-edge axis-aligned wireframe cube renderer for obstacle boxes with per-class color mapping per PRD §5.2 exactly (`player`=red, `pickup`=cyan, `door`=yellow, `wall`=green, `unknown`=gray)
- HUD overlay rendering with all PRD §6.1 specified elements plus `extra_hud` integration point
- Optional glow/bloom effect (Gaussian blur alpha-composited) and optional scanlines effect per PRD §7
- Integration with existing `openarena_perception.navigation.aas_parser` to read area geometry
- A runnable demo/smoke script that renders a single or looping frame from a static or live bot pose, using the AAS backend. Runs on Pi without any GPU or neural deps.
- Video recording support via `cv2.VideoWriter` (mp4v, 30 FPS, 960×600) per PRD §8.2
- Unit tests for: projection math (pinhole transform), `room_surface_grid` tessellation, depth color interpolation curve, wireframe cube edge generation, AAS-to-camera pose transform, `screen_to_room` unprojection, HUD rendering (asserts text regions have non-bg pixels)

## What's out of scope

- **Depth Anything V2 / torch / depth-anything-v2 package** — not added this phase. Deferred to future "neural vision mode." The PRD §3 and §11 dependency table are NOT authoritative for this phase — they describe the original plan; Version B supersedes them.
- **GroundingDINO, ultralytics, YOLO** — no new detection models. Consume whatever the existing project already detects.
- **Wiring into `item_tour.py` live tick loop** — the demo/smoke script is the integration preview. Live per-tick rendering in the tour is deferred (it's a nice-to-have for later after we verify the renderer works standalone).
- **Soft integration into `strategic_hud.py`** — the wireframe view is a separate window/executable, not embedded in the existing Phase 10 pygame HUD.
- **Bastion Bridge / multi-agent gateway rendering** — PRD §8.3/§8.4; deferred.
- **Accumulated world map / voxel grid / trajectory visualization / minimap inset / sound localization** — PRD §10.1-§10.4; explicit future extensions.
- **OpenGL/Vulkan renderer** — PRD §10.5; stays CV2/numpy.
- **Full implementations of `wireframe_3d.py` and `wireframe_grid.py`** — PRD §12 lists these as alternate modes; this phase ships `wireframe_room.py` only. The other two may exist as empty stubs for future work or not at all.
- **Metric depth calibration from screen space** — Version B uses AAS ground truth, so there's nothing to calibrate. The `screen_to_room` helper still exists per PRD §5.1 for the rare case where a 2D detection needs unprojecting, but it's not the primary depth path.

## Why Version B actually matches the user's stated goal

The user's problem statement from this session (paraphrased): *"I want to be able to see what's going on better. I want the HUD to ultimately be a forward-facing visualization of the bot's understanding of the game world."*

The bot's understanding of the game world is:
- **AAS geometry** (walls, areas, reachabilities) — used for nav
- **Detected objects** (enemies, pickups, HUD parse) — used for combat
- **Learned map** (occupancy grid from wall_detector.py) — used for edge penalties

The bot's understanding does NOT include a monocular depth estimate. DA-V2 would render what the bot *could* perceive if it had a neural depth estimator, not what it *does* perceive. Version B renders the actual mental model.

</domain>

<decisions>
## Implementation Decisions

### Module Layout

All new code lives under a new subpackage: `openarena_perception/visualization/`.

- `openarena_perception/visualization/__init__.py` — exposes `WireframeRoomRenderer`, `RoomConfig`, `AASDepthBackend`, `SceneGeometry`, object-class color constants
- `openarena_perception/visualization/wireframe_room.py` — primary renderer (`WireframeRoomRenderer` class)
- `openarena_perception/visualization/projection.py` — pure-function pinhole projection + surface tessellation + color interpolation (no cv2 imports here)
- `openarena_perception/visualization/aas_backend.py` — `AASDepthBackend` class that queries the loaded `AASGraph` given bot pose and emits `SceneGeometry` (3D line primitives + 3D boxes)
- `openarena_perception/visualization/scene.py` — `SceneGeometry` dataclass holding the per-frame line and box primitives the renderer draws
- `openarena_perception/visualization/hud.py` — HUD overlay (frame counter, corner brackets, extras) — split from renderer for testability
- `openarena_perception/visualization/effects.py` — glow, scanlines, depth fade — split for testability
- `openarena_perception/visualization/demo_wireframe_room.py` — CLI demo that loads the AAS, synthesizes or reads a bot pose, renders frames

Placing under `visualization/` keeps the concern isolated and matches the brain-inspired subsystem layout from v1.0 phases.

### SceneGeometry dataclass

```python
@dataclass(frozen=True, slots=True)
class SceneGeometry:
    """Per-frame 3D primitives ready for projection.
    Coordinates are in the bot's CAMERA space (already rotated into view):
      X: left (-) to right (+)
      Y: up (-) to down (+)
      Z: forward (+)
    """
    walls: tuple[tuple[tuple[float, float, float], tuple[float, float, float]], ...]
    # ^ list of (p1, p2) 3D line segments for wall edges
    boxes: tuple[tuple[str, float, float, float, float, float, float], ...]
    # ^ list of (class_name, x, y, z, w, h, d) for obstacle/object cubes
```

This separates "what to draw" from "how to draw." The AAS backend produces a `SceneGeometry`; the renderer consumes it. Tests can produce synthetic `SceneGeometry` without any AAS file.

### AASDepthBackend

```python
class AASDepthBackend:
    def __init__(self, aas_graph: AASGraph):
        self._aas = aas_graph

    def build_scene(
        self,
        bot_pos: tuple[float, float, float],
        bot_yaw: float,
        max_distance: float = 1024.0,
        max_areas: int = 20,
    ) -> SceneGeometry:
        """Return 3D primitives in CAMERA space for nearby AAS geometry.
        - Find areas within max_distance of bot_pos
        - Extract wall segments (area boundaries where no reachability edge exists)
        - Transform world coords -> camera coords via yaw rotation
        - Return as SceneGeometry
        """
```

Key implementation points:
- The AAS graph already exposes area centers and bounds; we extract wall segments from area geometry
- Transform is just a 2D rotation by `-yaw` around the bot position, then translate by `-bot_pos`
- Z-up (Quake) vs Y-up (screen) convention: Quake uses Z-up; the renderer uses Y-down-screen. Swap axes in the transform: `cam_x = world_rel_x`, `cam_y = -world_rel_z + camera_height`, `cam_z = world_rel_y`
- Cull segments behind the camera (`cam_z <= 0.1`)
- Optionally cull segments outside the view frustum

### RoomConfig (per PRD §4.5)

`@dataclass(frozen=True, slots=True)` per project convention (see `openarena_perception/models.py` SituationalAwareness pattern).

All PRD-specified fields preserved exactly. Added fields for the depth color curve (not in PRD but required by §4.4):
- `near_color: tuple[int,int,int] = (255, 255, 255)` — bright white near
- `far_color: tuple[int,int,int] = (40, 60, 80)` — dim blue far
- `warning_color: tuple[int,int,int] = (0, 80, 255)` — orange for close obstacles
- `proximity_threshold: float = 2.0` — warning trigger distance
- `fade_power: float = 0.6` — curve exponent for depth fade

Plus the glow/scanline parameters from PRD §7:
- `glow_radius: int = 9`, `glow_strength: float = 0.3`
- `scanline_spacing: int = 3`, `scanline_strength: float = 0.15`

### Projection math (pure functions in `projection.py`)

- `focal_length(width: int, fov_deg: float) -> float`
- `project_point(x, y, z, cfg) -> tuple[int, int] | None` — returns None if z ≤ 0.1 (behind camera)
- `project_line(p1_3d, p2_3d, cfg) -> tuple[tuple[int,int], tuple[int,int]] | None` — with near-plane clipping
- `room_surface_grid(origin, axis_u, axis_v, divs_u, divs_v) -> list[tuple[p1_3d, p2_3d]]` — tessellates a parametric quad into line segments
- `project_depth_color(z, cfg) -> tuple[int,int,int]` — near-warning / lerp / far-faded per PRD §4.4
- `cube_edges(x, y, z, w, h, d) -> list[tuple[p1_3d, p2_3d]]` — 12 line segments for axis-aligned box
- `screen_to_room(bbox_2d, cfg, depth_hint) -> tuple[...]` — per PRD §5.1 but using a provided depth_hint rather than sampling a depth map (since Version B has no depth map). Used for the 2D-detection-to-3D-box path when a detection comes from screen-space classifiers without known world coordinates.
- `world_to_camera(world_pos, bot_pos, bot_yaw) -> tuple[float,float,float]` — 2D yaw rotation + translation + Q3 axis remap (Z-up → Y-down-screen)

All pure; testable without cv2.

### Room grid vs scene geometry

The **room grid** (5 parametric planes per PRD §4.2) is drawn in a **fixed world-space box around the camera** — it's the Battlezone/Danger Room aesthetic chrome. It does NOT come from AAS; it's the always-on holodeck frame.

The **scene geometry** from `AASDepthBackend.build_scene()` is drawn on top as the actual bot-world content. The room frame provides depth cues and aesthetic; the AAS lines provide the "what the bot sees."

Both use the same projection math and depth-color function.

### Object colors (per PRD §5.2 exact)

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

### HUD Overlay (per PRD §6.1 exact)

All elements as specified. `cv2.FONT_HERSHEY_PLAIN` at scale 0.9. `extra_hud` dict is the integration point for game state data from the existing `perception/hud_parser.py` output.

### Visual Effects (per PRD §7)

- **Glow**: `cv2.GaussianBlur` with odd kernel + `cv2.addWeighted` composite
- **Scanlines**: alpha-blend horizontal line mask
- **Depth fade**: handled in `project_depth_color`, no post-processing step

Glow default ON, scanlines default OFF.

### Dependency policy (Version B)

- **Zero new dependencies** — uses existing `numpy` and `opencv-python-headless` from the project stack
- `torch` and `depth-anything-v2` are NOT added
- Pi install weight unchanged

### Demo script

`openarena_perception/visualization/demo_wireframe_room.py`:

- CLI args:
  - `--aas <path>` — path to AAS file (default: repo's oa_dm1 AAS)
  - `--pos x,y,z` — static bot pose (default: an interesting spot in oa_dm1)
  - `--yaw <deg>` — bot facing (default: 0)
  - `--orbit` — animate the bot yawing in a circle at the pose (fun visual test)
  - `--pose-file <path>` — read a stream of (t, pos, yaw) from a JSON log and play back
  - `--save <path.mp4>` — record to video
  - `--duration <seconds>` — limit runtime
  - `--no-glow`, `--no-hud` — disable effects for screenshots
- Default: `--pos <center of oa_dm1>` `--orbit` `--duration 10` — renders 300 frames orbiting, saves to `./tmp/wireframe_demo.mp4`
- Runnable on Pi without any GPU

### Tests (headless, no display)

- `tests/test_wireframe_projection.py` — pinhole math, room_surface_grid, cube_edges, project_depth_color, screen_to_room, world_to_camera transform
- `tests/test_wireframe_aas_backend.py` — build_scene() with a synthetic AAS fixture (small hand-crafted graph); assert expected wall segments emitted
- `tests/test_wireframe_renderer.py` — render a known SceneGeometry fixture; assert specific pixels are the expected color (spot checks, not golden files)
- `tests/test_wireframe_hud.py` — HUD renders into a blank frame; assert text regions have non-bg pixels

All tests run headless via `uv run pytest tests/test_wireframe*.py -q`. No cv2.imshow, no DISPLAY required.

### Integration point into existing code

**Minimal wiring into `item_tour.py`**: NONE in this phase. Integration happens via the demo script.

**Soft integration into `strategic_hud.py`**: NONE. Separate executable.

**Reads from existing code**:
- `openarena_perception.navigation.aas_parser.AASGraph` — AAS file loader (already exists)
- `openarena_perception.perception.game_state` / `hud_parser` — for `extra_hud` dict content in the demo, optional

### Execution order (3-plan split)

- **Plan 11-01**: Pure projection math module + RoomConfig + SceneGeometry + tests (zero external deps beyond numpy; no cv2 drawing yet, no AAS yet)
- **Plan 11-02**: WireframeRoomRenderer + HUD + effects + renderer tests (builds on 11-01; uses cv2 line drawing and synthetic SceneGeometry fixtures)
- **Plan 11-03**: AASDepthBackend + demo script + AAS-backed integration tests (builds on 11-02; uses real AAS file for oa_dm1)

3 plans, sequential waves. Each plan atomic, each delivers testable value on its own.

### Claude's Discretion

- Exact AAS wall-segment extraction algorithm — the AAS format doesn't directly encode "walls" as segments; they're implicit in area bounds where no reachability edge crosses. Derivation strategy is up to the planner/executor (likely: iterate area edges, emit segment if not crossed by a reachability, dedupe shared edges between neighboring areas).
- Whether to use `numpy` batched matrix operations or a per-point loop in `world_to_camera` — prefer batched for readability and future perf
- Line-drawing order (back-wall first for depth sorting, or z-sort all segments) — pick based on visual result
- Glow kernel size parity handling (OpenCV requires odd kernel sizes)
- Whether the `extra_hud` integration in the demo pulls from `hud_parser` live or uses synthetic state — prefer synthetic for the default demo (no OpenArena dependency), optional `--live-state` flag for real capture
- Whether to cache the extracted wall segments per-area on AASDepthBackend init (probably yes — AAS doesn't change at runtime)
- Font size and exact pixel positions for HUD elements within PRD §6.1 guidelines — use tasteful defaults
- Whether room_surface_grid tessellation uses evenly-spaced or logarithmic divisions — evenly-spaced per PRD

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project instructions and constraints
- `CLAUDE.md` — tech stack (numpy, opencv-python-headless, mss already present), Pi 5 target, 10+ FPS perception loop, uv package manager, pytest
- `.planning/STATE.md` — current state, milestone v1.0 verifying, Phase 10 complete with live-run validation
- `.planning/phases/11-wireframe-perception-grid/11-PRD.md` — original PRD; cross-reference for detail on aesthetic intent, HUD elements (§6.1), effects (§7), object colors (§5.2), room geometry (§4.2). **Version B pivot supersedes §3 (depth backend) and §11 (torch deps).**
- `.planning/phases/10-intent-system-and-hud-companion/10-03-SUMMARY.md` — Phase 10 HUD companion precedent for standalone pygame window + render loop pattern

### Existing AAS infrastructure (the depth source for Version B)
- `openarena_perception/navigation/aas_parser.py` — AAS file loader, `AASGraph` class with areas, reachabilities, bounds. This is the source of truth for the depth backend.
- `openarena_perception/navigation/navigator.py` — existing consumer of AASGraph; reference for how area geometry is queried
- `openarena_perception/navigation/learned_map.py` — occupancy grid and wall segment storage; reference for wall data model

### Existing perception infrastructure (for `extra_hud` integration)
- `openarena_perception/perception/capture.py` — mss screen capture
- `openarena_perception/perception/hud_parser.py` — pytesseract HUD parser; output shape maps to `extra_hud` dict
- `openarena_perception/perception/pipeline.py` — PerceptionPipeline orchestrator (reference only; no modifications this phase)
- `openarena_perception/models.py` — frozen+slotted dataclass convention; `RoomConfig` and `SceneGeometry` follow this

### Existing visualization precedent
- `strategic_hud.py` — standalone pygame HUD; reference for how a separate visualization executable lives in the project
- `openarena_perception/hud_schema.py` — `build_hud_payload` pattern from Phase 10; possibly reused for the wireframe HUD's `extra_hud` dict if convenient

### PRD reference sections (still authoritative for Version B)
- PRD §4.2 — Room geometry (5 parametric quads, exact dimensions)
- PRD §4.3 — Perspective projection (pinhole)
- PRD §4.4 — Depth-based line coloring
- PRD §4.5 — RoomConfig fields
- PRD §5.1-§5.2 — Obstacle boxes, `screen_to_room`, `OBJECT_COLORS`
- PRD §5.3 — Depth contour projection (interpreted in Version B as "optionally render a ground-plane grid from AAS area spans" — implementation detail deferred to planner)
- PRD §6 — HUD overlay (all elements)
- PRD §7 — Visual effects
- PRD §8.2 — Recording (mp4v)

### PRD reference sections superseded by Version B
- **PRD §3 — Depth estimation backend (DA-V2 / DepthFM)** — NOT USED this phase; replaced by `AASDepthBackend`
- **PRD §3.3 — Pi considerations** — moot; no depth inference on Pi
- **PRD §8.3 — Bastion Bridge streaming** — not needed; Pi-native rendering
- **PRD §11 — Dependencies (torch, depth-anything-v2, ultralytics)** — NOT added; stay on existing numpy + opencv

</canonical_refs>

<specifics>
## Specific Ideas

### Aesthetic targets (from PRD §1, preserved)

- Battlezone (1980) wireframe perspective
- TRON lightcycle grid
- Danger Room from X-Men
- Holodeck perspective room with receding wireframe grid planes
- Green accent color `(0, 255, 100)` for obstacle overlays
- Depth-fade bright-near → dim-far
- DOS-style HUD chrome (corner brackets, monospace font, status bars)
- Simple crosshair at center
- OpenArena FOV 90° default

### Execution order preference

Sequential waves, one plan per wave:

- **Wave 1 / Plan 11-01**: `projection.py` (pure functions) + `RoomConfig` + `SceneGeometry` dataclass + full unit tests for the math. Zero cv2 drawing, zero AAS. Deliverable: a testable math library.
- **Wave 2 / Plan 11-02**: `wireframe_room.py` (`WireframeRoomRenderer`) + `hud.py` + `effects.py` + demo script skeleton that accepts a synthetic `SceneGeometry`. Deliverable: a runnable standalone renderer that draws a hand-crafted scene.
- **Wave 3 / Plan 11-03**: `aas_backend.py` (`AASDepthBackend`) + real oa_dm1 AAS integration + full demo script + AAS-backed tests. Deliverable: running the demo on the Pi with the real AAS file shows a holodeck view of oa_dm1 walls around a given bot pose.

Each wave merges before the next starts. Each wave is independently testable and reviewable.

### Goal state for user visual verification

After Plan 11-03 lands, running:
```bash
uv run python -m openarena_perception.visualization.demo_wireframe_room \
    --aas /usr/lib/openarena/baseoa/maps/oa_dm1.aas \
    --pos 232,1600,-112 \
    --yaw 90 \
    --orbit \
    --duration 10
```
should produce a pygame/cv2 window showing a Battlezone/TRON-style wireframe room, with oa_dm1's actual wall geometry projected into it, the camera orbiting the given pose over 10 seconds, with CRT glow and HUD chrome. This is the "I can see what the bot sees" outcome.

</specifics>

<deferred>
## Deferred Ideas

### PRD §10 (explicit future extensions)
- **§10.1 Accumulated World Map** — voxel grid / occupancy map accumulating over time
- **§10.2 Trajectory Visualization** — planned path + predicted enemy positions
- **§10.3 Minimap Overhead View** — top-down orthographic wireframe inset
- **§10.4 Sound Localization** — expanding wireframe rings for audio cues
- **§10.5 Real-Time OpenGL Renderer** — migrate to GPU for higher density + detached camera

### Version B pivot deferrals
- **Depth Anything V2 / DepthFM backends** — future "neural vision mode" as an alternative `DepthBackend` implementation sitting alongside `AASDepthBackend`. Useful if you want to see what a pure-vision perception looks like vs. the bot's actual AAS-based model.
- **`torch` / `depth-anything-v2` package** — added only if/when neural backend is revisited
- **Bastion Bridge gateway offload** — only needed if neural backend is revisited
- **GroundingDINO / ultralytics / YOLO detection** — only if new detection capabilities are added in a different phase
- **Metric depth calibration** — moot with AAS ground truth

### Integration deferrals
- **Wiring into `item_tour.py` live tick loop** — per-tick rendering during the tour. Nice-to-have for future phase; this phase ships standalone demo only.
- **Embedded into `strategic_hud.py` as a second panel** — pygame+cv2 coexistence is tricky; keep the wireframe view as its own executable for now.
- **Multi-agent fleet dashboard** — requires multi-bot setup.
- **`wireframe_3d.py` and `wireframe_grid.py` full implementations** — alternate modes listed in PRD §12; this phase ships `wireframe_room.py` only.

### Nice-to-haves not committed
- Auto-generated floor plan overlay from AAS (top-down) — could be a later phase
- Animated "scanning" effect where wall segments fade in from near to far
- Sound-reactive depth pulsing (if audio is added)

</deferred>

---

*Phase: 11-wireframe-perception-grid*
*Context gathered: 2026-04-10 via PRD Express Path + Version B pivot (AAS-driven depth instead of neural inference)*
