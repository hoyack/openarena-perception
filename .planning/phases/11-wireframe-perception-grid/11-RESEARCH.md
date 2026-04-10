# Phase 11: Wireframe Perception Grid (Version B — AAS-driven) — Research

**Researched:** 2026-04-10
**Domain:** 3D wireframe renderer + AAS geometry projection (Pi-native, pure numpy/cv2)
**Confidence:** HIGH on existing code, HIGH on AAS file format (verified directly), HIGH on Q3 conventions, MEDIUM on cv2 line-draw perf on Pi 5

## Summary

Phase 11 Version B replaces the PRD's Depth Anything V2 neural-depth pipeline with a pure-CPU AAS geometry projector. The project already owns the AAS file for oa_dm1 (`maps/oa_dm1.aas`, 530 KB, 849 areas, 3121 reachabilities, **plus 4195 vertexes, 5083 faces, 4272 edges, 1190 planes** — a complete polyhedral mesh that the current parser does not yet touch).

**The single biggest research finding:** the existing `openarena_perception/navigation/aas_parser.py` only decodes three lumps (areas, areasettings, reach) and only reads the center (offset +36) of each 48-byte area record. **The mins/maxs AABB lives at offsets +12 and +24 in the same record and is free to extract with ~4 lines of code.** Beyond the AABB, the file also contains a full mesh (lumps 0–6: bboxes, vertexes, planes, edges, edgeindex, faces, faceindex) that gives us ground-truth wall polygons. Plan 11-03 has two viable paths:

- **Easy path (recommended for this phase):** extend the parser to also read mins/maxs, treat each area as a walkable AABB, and render the 12 edges of each box as wireframe segments. Zero knowledge of the face/edge/plane lumps required. Produces "boxy" walls that are still instantly recognizable as oa_dm1 geometry.
- **Full path (deferred / stretch):** decode the faces/edges/vertexes lumps and render actual wall polygon edges. ~2× more code and requires pinning struct layouts against ioquake3 `be_aas_file.h`. Better visual fidelity but more risk.

**Primary recommendation:** Plan 11-03 ships the AABB path. Full face-mesh rendering becomes an optional follow-on.

Everything else in the phase is low-risk: the existing project already uses `numpy` 2.4.4 and `opencv-python-headless` 4.13.0 (verified), has `mp4v` codec availability (verified), and the strategic_hud.py file at the repo root is a direct precedent for a standalone pygame-window executable. No new dependencies are needed.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Depth source pivot — Version B:** Depth Anything V2 (and all torch/depth-anything-v2 deps) is removed from scope. The depth source is AAS geometry projected into camera space via pinhole math. PRD §3 and §11 are **superseded**; PRD §4–§8 still authoritative for aesthetic, HUD, effects, and room-frame geometry.
- **Zero new dependencies.** Uses existing `numpy` and `opencv-python-headless` only.
- **Module layout:** All new code lives under `openarena_perception/visualization/`:
  - `__init__.py` (exports)
  - `wireframe_room.py` (`WireframeRoomRenderer` class)
  - `projection.py` (pure pinhole + tessellation + color; no cv2 imports)
  - `aas_backend.py` (`AASDepthBackend` class)
  - `scene.py` (`SceneGeometry` dataclass)
  - `hud.py` (HUD overlay)
  - `effects.py` (glow, scanlines, depth fade)
  - `demo_wireframe_room.py` (CLI demo)
- **SceneGeometry dataclass** is frozen+slotted, carries already-in-camera-space line segments and class-tagged boxes. Separates "what to draw" from "how to draw."
- **`RoomConfig` is frozen+slotted** (matches `SituationalAwareness` convention in `openarena_perception/models.py:44`). All PRD §4.5 fields preserved plus added depth-curve fields (`near_color`, `far_color`, `warning_color`, `proximity_threshold`, `fade_power`) and effects fields (`glow_radius`, `glow_strength`, `scanline_spacing`, `scanline_strength`).
- **Room-frame geometry** (5 parametric quads per PRD §4.2) is a **fixed box around the camera**, not AAS-sourced. It is the always-on holodeck chrome. AAS content is drawn *on top*.
- **Camera axis convention** (from CONTEXT.md Decisions): `cam_x = world_rel_x`, `cam_y = -world_rel_z + camera_height`, `cam_z = world_rel_y` (after the `-yaw` rotation). Q3 Z-up → renderer Y-down-screen.
- **Object colors** exactly per PRD §5.2: player=(255,50,50), pickup=(50,255,255), door/portal=(255,255,50), wall/static=(0,255,100), unknown=(180,180,180). BGR order.
- **Glow default ON, scanlines default OFF.**
- **3-plan split (sequential waves):**
  - 11-01: `projection.py` + `RoomConfig` + `SceneGeometry` + math tests (no cv2 drawing, no AAS).
  - 11-02: `WireframeRoomRenderer` + `hud.py` + `effects.py` + renderer tests on synthetic SceneGeometry.
  - 11-03: `AASDepthBackend` + demo script + real oa_dm1 integration tests.
- **Demo script goal state:** `uv run python -m openarena_perception.visualization.demo_wireframe_room --aas maps/oa_dm1.aas --pos <center> --yaw 90 --orbit --duration 10` produces an orbiting Battlezone-style wireframe view of oa_dm1.
- **Tests are headless.** No `cv2.imshow`, no `DISPLAY` required. Run via `uv run pytest tests/test_wireframe*.py -q`.
- **No wiring into `item_tour.py` or `strategic_hud.py` this phase.** The demo is the integration preview.

### Claude's Discretion

- Exact AAS wall-segment extraction algorithm (AABB-edge approach vs. full face-mesh decode). **Research recommendation: AABB edges.** See "Wall segment extraction" section below.
- Whether `world_to_camera` is batched numpy or a per-point loop. **Recommendation: batched.** Segment counts per frame are small (a few hundred), but batched code is cleaner and future-proofs for the face-mesh path.
- Line-drawing z-sort order. **Recommendation: back-to-front by midpoint z.** Simple and good enough at these segment counts.
- Glow kernel size parity. **Recommendation: force `(radius | 1)` to guarantee odd.** `cv2.GaussianBlur` raises if even.
- Whether `extra_hud` integration pulls from live `hud_parser` or uses synthetic values. **Recommendation: synthetic default, optional `--live-state` flag.**
- Whether `AASDepthBackend` caches extracted wall segments per-area at init. **Recommendation: yes, cache at init** — AAS is immutable at runtime and pre-computing the AABB edge lists is trivial.
- Font size and exact pixel positions for HUD elements within PRD §6.1 guidelines.
- Whether `room_surface_grid` tessellation uses evenly-spaced or logarithmic divisions. **PRD specifies even-spaced.**

### Deferred Ideas (OUT OF SCOPE)

- Depth Anything V2, torch, depth-anything-v2 package — future "neural vision mode" backend alongside `AASDepthBackend`.
- GroundingDINO, ultralytics, YOLO — no new detection models.
- Wiring the renderer into `item_tour.py` per-tick loop.
- Embedding into `strategic_hud.py` as a second panel.
- Bastion Bridge gateway streaming / multi-agent fleet view (PRD §8.3/§8.4).
- Accumulated world map / voxel grid / trajectory / minimap inset / sound-localization rings (PRD §10.1–§10.4).
- OpenGL/Vulkan migration (PRD §10.5).
- `wireframe_3d.py` and `wireframe_grid.py` alternate modes (PRD §12).
- Metric depth calibration — moot with AAS ground truth.
- **Face/edge/vertex mesh decoding from AAS lumps 0–6.** Possible but larger scope; recommended as a later phase if the AABB approach proves insufficient.

## Phase Requirements

(No explicit REQ-IDs provided by the orchestrator for Phase 11; the phase scope is defined by PRD §4–§8 minus the Version B supersedes listed above, plus the CONTEXT.md decisions. The planner should synthesize phase requirements from the CONTEXT.md `<domain>` block.)

## Standard Stack

### Already Installed (verified on target host)

| Library | Verified Version | Source | Purpose |
|---------|------------------|--------|---------|
| numpy | 2.4.4 | `python3 -c "import numpy"` on openarena-perception | Matrix math, batched projection |
| opencv-python-headless | 4.13.0 | `python3 -c "import cv2"` | Line drawing, VideoWriter, GaussianBlur |
| pygame | installed | `strategic_hud.py` imports it directly | Window management if demo uses pygame path |

[VERIFIED: `python3 -c "import cv2, numpy; print(cv2.__version__, numpy.__version__)"` on the openarena-perception Pi — cv2 4.13.0, numpy 2.4.4]

`cv2.VideoWriter_fourcc(*'mp4v')` resolves successfully on this host → 1983148141. MP4 recording works without extra codec installation. [VERIFIED]

### Nothing New To Install

Version B adds **zero packages**. No `uv add` step. No lockfile changes. No Pi install weight change.

### Version Verification Discipline

The planner must not invent stricter lower bounds than the existing project carries. `opencv-python-headless >= 4.8` per `CLAUDE.md` is the project-wide pin; everything needed by this phase (`line`, `polylines`, `GaussianBlur`, `VideoWriter`, `addWeighted`, `FONT_HERSHEY_PLAIN`) has been stable since 4.0. Safe. [CITED: CLAUDE.md technology stack table]

## Architecture Patterns

### Project structure slot

```
openarena_perception/
├── visualization/             # NEW subpackage
│   ├── __init__.py
│   ├── scene.py               # SceneGeometry dataclass
│   ├── projection.py          # pure math (no cv2)
│   ├── effects.py             # glow, scanlines
│   ├── hud.py                 # HUD overlay draw
│   ├── wireframe_room.py      # WireframeRoomRenderer
│   ├── aas_backend.py         # AASDepthBackend
│   └── demo_wireframe_room.py # CLI demo
```

This mirrors the brain-inspired subsystem layout introduced in v1.0 (navigation/, perception/, combat/, reflexes/, tactics/, strategy/, skills/, memory/). [VERIFIED: listing `openarena_perception/`]

### Dataclass convention

All data classes in this phase use `@dataclass(frozen=True, slots=True)` per `openarena_perception/models.py:44` `SituationalAwareness`. Re-read that file before writing `RoomConfig` and `SceneGeometry`. [VERIFIED]

### Pure math vs cv2 separation

`projection.py` must have **zero cv2 imports**. Only `numpy` and `math`. This enables unit-testing the pinhole math on any host (CI, desktop, Pi) without OpenCV baggage, and lets the tests assert pixel coordinates mathematically rather than against golden images.

`wireframe_room.py`, `hud.py`, `effects.py`, `demo_wireframe_room.py` may import cv2.

### Rendering pipeline (per frame)

```
bot_pose (pos,yaw)  ─┐
                     ▼
               AASDepthBackend.build_scene()       ← returns SceneGeometry (camera-space)
                     │
                     ▼
         WireframeRoomRenderer.render(scene, extra_hud)
                     │
                     ├── draw room frame (5 parametric quads)        ← projection.room_surface_grid
                     ├── draw scene walls (line list)                 ← projection.project_line
                     ├── draw scene boxes (cube_edges per box)        ← projection.cube_edges
                     ├── apply glow (effects.py)
                     ├── apply scanlines (effects.py)
                     └── draw HUD overlay (hud.py)
                     ▼
                BGR frame ready for cv2.imshow / VideoWriter
```

### Standalone executable precedent

`strategic_hud.py` at the repo root is the precedent for a standalone visualization executable:
- Lives at repo root (or callable via `python -m` once moved to `visualization/demo_wireframe_room.py`)
- Has its own `main()` with argparse
- Reads state from either a shared JSON file OR synthesizes it
- Uses `pygame.display.set_mode` + `pygame.time.Clock` + `pygame.display.flip()`
- File ref: `strategic_hud.py:687-698` for the argparse→state→HUD→run() pattern

For this phase: **use cv2 (`cv2.imshow` + `cv2.waitKey`) for the demo, not pygame.** Reasons:
1. The renderer already produces a BGR numpy array. Feeding that into `cv2.imshow` is one line. Wrapping it in a `pygame.Surface` requires BGR→RGB swap + `pygame.image.frombuffer` + blit, adding overhead and complication.
2. The demo records to `cv2.VideoWriter` which wants BGR anyway.
3. Pygame + cv2 coexistence inside one process is brittle (SDL vs Qt init ordering, stdout pollution, X11 backend conflicts). CONTEXT.md already defers pygame integration.
4. Existing project pattern: `tests/` never imports pygame; only `strategic_hud.py` does, and it runs in its own process.

The demo loop shape:

```python
def main():
    args = parse_args()
    graph = parse_aas(args.aas)
    backend = AASDepthBackend(graph)
    renderer = WireframeRoomRenderer(RoomConfig())
    writer = cv2.VideoWriter(args.save, ...) if args.save else None
    clock_start = time.time()
    frame_idx = 0
    while True:
        if args.orbit:
            yaw = (frame_idx * 2) % 360
        else:
            yaw = args.yaw
        scene = backend.build_scene(args.pos, yaw)
        frame = renderer.render(scene, extra_hud=synth_hud_state(frame_idx))
        if writer: writer.write(frame)
        cv2.imshow("PERCEPTION", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break
        if args.duration and time.time() - clock_start > args.duration: break
        frame_idx += 1
    if writer: writer.release()
    cv2.destroyAllWindows()
```

### Synthetic HUD state pattern

Follow `openarena_perception/hud_schema.py:37` `build_hud_payload` pattern — a plain dict with `.get()` defaults on the reader side. For the demo's `--no-live-state` default, a dict like:

```python
{"MODE": "DEMO", "HP": 100, "AMMO": 50, "TARGET": "none", "POS": "(232,1600,-112)", "YAW": "90"}
```

is enough. The renderer's HUD element loops over the dict and draws each key/value pair in a column under the fixed HUD elements.

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---------|-------------|-------------|-----|
| AAS file parsing | custom binary parser from scratch | **Extend the existing `openarena_perception/navigation/aas_parser.py`** | Parser already decodes the header, XOR-decrypts the lump directory, validates EAAS v5, handles all edge cases. Adding mins/maxs is +4 lines of `struct.unpack_from`. |
| 3D line near-plane clip | full Liang-Barsky or Cohen-Sutherland implementation | Simple parametric clip to `z = 0.1` | A single-plane clip is ~10 lines: if both endpoints `z < 0.1` → skip; if one is `< 0.1` → compute `t = (0.1 - z1) / (z2 - z1)` and move that endpoint along the segment to `z = 0.1`. Liang-Barsky is overkill for a single plane. |
| Gaussian blur for glow | manual convolution loop | `cv2.GaussianBlur(frame, (k, k), 0)` | Built-in, SIMD-accelerated on ARM via OpenCV's NEON path. Kernel must be odd. |
| Perspective projection matrix | homogeneous 4×4 matrix + MVP pipeline | Direct `screen_x = cx + fx * x / z` formula | PRD §4.3 specifies this exact form. No clipping matrix needed because we do the near clip explicitly. No camera extrinsic matrix needed because the AAS backend already transforms into camera space. |
| 12 cube edges from center+extents | writing out 12 pairs by hand every frame | Pre-compute once in `cube_edges()` pure function, reuse | Trivial but keeps the per-box draw path allocation-free. |
| Q3 yaw/heading math | Reinventing the convention | **Read `strategic_hud.py:405-409` and `openarena_perception/navigation/navigator.py:292`** before writing `world_to_camera`. Both already consume viewpos yaw and the convention is documented in-place. | Easy to get wrong. See Pitfall 1 below. |
| Video recording codec | picking a codec blind | `cv2.VideoWriter_fourcc(*'mp4v')` (verified available) + 30 FPS + 960×600 per PRD §8.2 | Works on this host, no extra install. |

## Runtime State Inventory

This is a greenfield visualization phase. It adds new files; it does not rename/refactor anything.

- **Stored data:** None modified. Reads `maps/oa_dm1.aas` (530,380 bytes, immutable). [VERIFIED: `ls -la`]
- **Live service config:** None.
- **OS-registered state:** None.
- **Secrets/env vars:** None.
- **Build artifacts:** The existing `openarena_perception` package installed via `uv pip install -e .` will auto-pick-up the new `visualization/` subpackage on next import; no reinstall required if editable install is in use.

## Code Examples

### Existing AAS parser — what it reads today

File: `openarena_perception/navigation/aas_parser.py:127-131`

```python
# Parse areas
areas = []
for i in range(num_areas):
    base = ofs_a + i * 48
    center = struct.unpack_from('<3f', data, base + 36)
    areas.append(AASArea(idx=i, cx=center[0], cy=center[1], cz=center[2]))
```

Note: center is read from **offset +36** of a 48-byte record. Only 12 bytes of useful data out of 48. [VERIFIED]

### Actual AAS area record layout (discovered by direct inspection)

Verified by dumping oa_dm1's first two area records as floats:

```
area 1 floats: [0.0, 0.0, 0.0, 999.0, 785.0, 188.0, 1137.0, 1433.0, 204.0, 1024.1, 1037.7, 195.5]
               ^ int header               ^ mins (x,y,z)     ^ maxs (x,y,z)        ^ center (x,y,z)
```

So the layout is:

```
offset  0  (int)    areanum
offset  4  (int)    numfaces   (or another 4-byte field — not needed for AABB path)
offset  8  (int)    firstface  (or another 4-byte field — not needed for AABB path)
offset 12  (vec3)   mins  (x, y, z)
offset 24  (vec3)   maxs  (x, y, z)
offset 36  (vec3)   center (x, y, z)   ← what the parser currently reads
```

[VERIFIED via direct struct dump of maps/oa_dm1.aas]

### Minimal extension to extract AABB

```python
# In aas_parser.py, extend AASArea:
@dataclass
class AASArea:
    idx: int
    cx: float; cy: float; cz: float
    mins: Tuple[float,float,float] = (0.0, 0.0, 0.0)  # NEW
    maxs: Tuple[float,float,float] = (0.0, 0.0, 0.0)  # NEW
    is_liquid: bool = False
    neighbors: List[int] = field(default_factory=list)
    travel_types: List[int] = field(default_factory=list)
    reaches: List[AASReach] = field(default_factory=list)

# In parse_aas(), inside the areas loop:
for i in range(num_areas):
    base = ofs_a + i * 48
    mins   = struct.unpack_from('<3f', data, base + 12)  # NEW
    maxs   = struct.unpack_from('<3f', data, base + 24)  # NEW
    center = struct.unpack_from('<3f', data, base + 36)
    areas.append(AASArea(
        idx=i, cx=center[0], cy=center[1], cz=center[2],
        mins=mins, maxs=maxs,
    ))
```

5 lines of code, fully backward compatible (existing callers that only touch `cx/cy/cz` are unaffected). [ASSUMED: backward-compat claim — verify by running `uv run pytest tests/test_navigation.py tests/test_property_based.py tests/test_tour_metrics.py` after the change. The default-valued tuples protect test fixtures that build `AASArea` directly; see `tests/test_property_based.py:216` and `tests/test_tour_metrics.py:48` which both construct `AASArea` by keyword.]

### Full AAS lump inventory (for the optional face-mesh path)

Verified by reading the XOR-decrypted lump directory of `maps/oa_dm1.aas`:

```
lump  0 bboxes         ofs=     124 len=      64
lump  1 vertexes       ofs=     188 len=   50340   → 4195 vec3 floats (stride 12)
lump  2 planes         ofs=   50528 len=   23800   → 1190 planes (stride 20) or 850 (stride 28)
lump  3 edges          ofs=   74328 len=   68352   → 4272 edges (stride 16) — two ints per edge
lump  4 edgeindex      ofs=  142680 len=   94708
lump  5 faces          ofs=  237388 len=  121992   → 5083 faces (stride 24)
lump  6 faceindex      ofs=  359380 len=   31056
lump  7 areas          ofs=  390436 len=   40752   → 849 areas (stride 48)     CURRENTLY READ
lump  8 areasettings   ofs=  431188 len=   23772   → 849 settings (stride 28)  CURRENTLY READ
lump  9 reach          ofs=  454960 len=   43692   → ~993 reaches (stride 44)  CURRENTLY READ
lump 10 nodes          ofs=  498652 len=   31344
lump 11 portals        ofs=  529996 len=     200
lump 12 portalindex    ofs=  530196 len=      72
lump 13 clusters       ofs=  530268 len=     112
```

[VERIFIED] The face-mesh path would decode lumps 1 (vertexes), 3 (edges), 5 (faces), 6 (faceindex), plus the area's `numfaces`/`firstface` header (the two ints at offset 4 and 8 in each area record). This is **explicitly out of scope** for Plan 11-03; the AABB path is sufficient. Record the lump table in a comment in the extended parser so a future phase can pick it up.

### Wall segment extraction — AABB approach (recommended)

Each area's AABB has 12 edges (4 bottom, 4 top, 4 verticals). Emit them all for every area within `max_distance` of the bot. Neighbor areas share faces, producing some overdraw, but at the expected counts (~20 visible areas × 12 edges = 240 segments) overdraw is free.

```python
def aabb_edges(mins, maxs):
    """Return the 12 edges of an AABB as ((p1,p2), ...)."""
    x0,y0,z0 = mins; x1,y1,z1 = maxs
    v = [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),   # bottom 4
         (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]   # top 4
    edges = [(0,1),(1,2),(2,3),(3,0),                   # bottom ring
             (4,5),(5,6),(6,7),(7,4),                   # top ring
             (0,4),(1,5),(2,6),(3,7)]                   # verticals
    return tuple((v[a], v[b]) for a, b in edges)
```

This produces the "boxy world" aesthetic. It is visually honest: the AAS file genuinely encodes walkable space as convex cells with AABBs, and the bot's navigation does treat each area as a navigation unit. "Rendering the bot's mental model" is exactly this.

### Pinhole projection (projection.py skeleton)

```python
import math
import numpy as np

NEAR_Z = 0.1  # clip plane

def focal_length(width: int, fov_deg: float) -> float:
    return width / (2.0 * math.tan(math.radians(fov_deg) / 2.0))

def project_point(x, y, z, cfg):
    """Return (sx, sy) pixel coords, or None if behind near plane."""
    if z <= NEAR_Z:
        return None
    fx = focal_length(cfg.width, cfg.fov_deg)
    sx = cfg.width / 2 + x * fx / z
    sy = cfg.height / 2 + y * fx / z   # fy == fx for square pixels
    return (int(round(sx)), int(round(sy)))

def project_line(p1, p2, cfg):
    """Project a 3D line, clipping at the near plane. Returns (sp1, sp2) or None."""
    x1,y1,z1 = p1; x2,y2,z2 = p2
    if z1 <= NEAR_Z and z2 <= NEAR_Z:
        return None
    if z1 <= NEAR_Z:
        t = (NEAR_Z - z1) / (z2 - z1)
        x1 = x1 + t * (x2 - x1)
        y1 = y1 + t * (y2 - y1)
        z1 = NEAR_Z
    elif z2 <= NEAR_Z:
        t = (NEAR_Z - z2) / (z1 - z2)
        x2 = x2 + t * (x1 - x2)
        y2 = y2 + t * (y1 - y2)
        z2 = NEAR_Z
    sp1 = project_point(x1, y1, z1, cfg)
    sp2 = project_point(x2, y2, z2, cfg)
    if sp1 is None or sp2 is None:
        return None
    return (sp1, sp2)

def world_to_camera(world_xyz, bot_pos, bot_yaw_deg, camera_height=40.0):
    """Q3 world coords → renderer camera coords.

    Q3: +X east, +Y north, +Z up; yaw is degrees measured counter-clockwise
        from +X (east=0, north=90). See navigator.py:292.
    Renderer camera space: +X right, +Y down, +Z forward.
    """
    wx, wy, wz = world_xyz
    bx, by, bz = bot_pos
    # Translate so bot is at origin
    dx, dy, dz = wx - bx, wy - by, wz - bz
    # Rotate world by -yaw so that the bot's forward vector (yaw direction)
    # lands on the +Y world axis, which maps to +Z camera.
    yaw_rad = math.radians(bot_yaw_deg)
    cos_y, sin_y = math.cos(yaw_rad), math.sin(yaw_rad)
    # After rotation by -yaw, world +X (east) rotates toward camera +X when
    # facing north. See navigator.py:292 for the yaw=atan2(dy,dx) convention.
    fx =  cos_y * dx + sin_y * dy    # this becomes camera forward  (Z_cam)
    sx = -sin_y * dx + cos_y * dy    # this becomes camera right    (X_cam)
    # Q3 Z-up → renderer Y-down-screen, with eye-height offset
    cam_x = sx
    cam_y = -(dz) + 0.0              # eye-height built into bot z; or subtract camera_height
    cam_z = fx
    return (cam_x, cam_y, cam_z)
```

**This function is the single most error-prone piece in the phase.** Cross-verify against `strategic_hud.py:406-409` (Q3 yaw+atan2 convention in the strategic HUD heading arrow) and `openarena_perception/navigation/navigator.py:292` (`desired = math.degrees(math.atan2(ty - self.pos[1], tx - self.pos[0]))` — canonical Q3 yaw formula in this codebase).

The derivation above assumes Q3 yaw is counter-clockwise-from-east (east=0°, north=90°). [VERIFIED in-codebase: `navigator.py:292` uses `atan2(dy, dx)` which is exactly east=0/north=90.]

**Validation path for the transform:** write a pytest that places an AAS area 100 units directly north of the bot with the bot facing north (yaw=90). The camera-space coordinate must be approximately `(0, 0, 100)` (straight ahead). Place the same area directly east with yaw=90 and it must be approximately `(-100, 0, 0)` (to the left). The signs will be the single most common bug; the test catches them.

### Synthetic AAS fixture pattern (for tests)

The existing test suite already has the precedent:

- `tests/test_property_based.py:216-239` — `_build_test_graph(n)` builds a linear AASGraph with `AASArea(idx=i, cx=float(i*100), cy=0.0, cz=0.0)` and `AASReach` edges between them.
- `tests/test_tour_metrics.py:48-86` — `_build_linear_graph(num_areas)` similar pattern.

Plan 11-03's AAS-backend tests should follow the same convention: build a 4-area graph with hand-picked mins/maxs, call `AASDepthBackend.build_scene()`, assert the expected number of line segments come out and that they're in the expected camera-space quadrant given a chosen bot pose.

### cv2.line drawing

Use `cv2.line(frame, pt1, pt2, color_bgr, thickness, cv2.LINE_AA)` per segment. Anti-aliasing costs ~2× vs `cv2.LINE_8` but is visually essential for the wireframe aesthetic on a 960×600 canvas — without AA the diagonal lines stairstep badly. At the expected segment counts (a few hundred room-frame lines + a few hundred AAS lines = ~500 total), AA is affordable on Pi 5. Measure in Plan 11-02 and toggle off via RoomConfig if the budget blows.

`cv2.polylines(frame, [np.array(pts, np.int32)], False, color, thickness, cv2.LINE_AA)` is faster than N `cv2.line()` calls for contiguous polylines but the wireframe geometry here is mostly disconnected segments, so the saving is marginal. Prefer `cv2.line` for readability unless profiling says otherwise.

### Glow effect

```python
def apply_glow(frame, radius=9, strength=0.3):
    k = radius | 1   # force odd
    blurred = cv2.GaussianBlur(frame, (k, k), 0)
    return cv2.addWeighted(frame, 1.0, blurred, strength, 0)
```

### Scanlines

```python
def apply_scanlines(frame, spacing=3, strength=0.15):
    h, w = frame.shape[:2]
    mask = np.ones((h, 1, 1), dtype=np.float32)
    mask[::spacing] = 1.0 - strength
    return (frame.astype(np.float32) * mask).astype(np.uint8)
```

## Common Pitfalls

### Pitfall 1: Q3 yaw convention direction

**What goes wrong:** The bot orbits and the whole world appears to rotate backwards, or faces the wrong way.

**Why it happens:** Q3 yaw is degrees, counter-clockwise, with **east (+X) = 0°, north (+Y) = 90°**. Multiple codebases invert this to match screen Y-down conventions. If you rotate by `+yaw` instead of `-yaw`, or if you swap `sin`/`cos` signs, the world spins backwards.

**How to avoid:** Cross-verify against `openarena_perception/navigation/navigator.py:292` which has the canonical `math.atan2(ty - self.pos[1], tx - self.pos[0])` formula. Write the validation test in the `world_to_camera` section above *before* writing the rest of the backend. Place an area at a known bearing and assert the camera-space sign.

**Warning signs:** Orbit demo spins the wrong way; the back-wall of the room frame never contains any AAS geometry (it's all behind the camera).

### Pitfall 2: Q3 Z-up vs screen Y-down

**What goes wrong:** Ceilings render below the camera and floors above; or the room is mirrored vertically.

**Why it happens:** Q3's world Z is up. The renderer's Y is screen-down. You have to negate: `cam_y = -world_rel_z + camera_height`. Forgetting the negation flips the whole world upside down. Doing it twice cancels.

**How to avoid:** Tiny pytest: place an area mins=(0, 0, 0), maxs=(10, 10, 10) with bot at (0, -100, 0) facing north, yaw=90. All 12 edges must project to positive camera-z and the top 4 edges must have smaller (more negative) screen-y than the bottom 4.

### Pitfall 3: Near-plane clip at z = 0

**What goes wrong:** A single line endpoint at z ≈ 0 produces screen coordinates in the millions; `cv2.line` silently writes garbage or draws a full-canvas diagonal.

**Why it happens:** `sx = fx * x / z` blows up as `z → 0`. Floats don't trap divide-by-zero.

**How to avoid:** Use `NEAR_Z = 0.1` (not 0.0). Clip *before* projecting. Both endpoints behind → drop the segment. One behind → move it to the near plane along the parametric ratio (see `project_line` example above).

### Pitfall 4: `cv2.GaussianBlur` requires an odd kernel

**What goes wrong:** `cv2.error: (-215:Assertion failed) ksize.width > 0 && ksize.width % 2 == 1`.

**How to avoid:** `k = radius | 1`. Always. Even if `RoomConfig.glow_radius` defaults to 9, a user overriding with 8 should not crash the renderer. Document the rule in `effects.py`.

### Pitfall 5: cv2 BGR vs RGB

**What goes wrong:** Colors look wrong — the "green" accent renders as blue, the "red" player boxes render as cyan-ish.

**Why it happens:** OpenCV is BGR by convention. The PRD §5.2 colors are specified as tuples — `(0, 255, 100)` — and must be interpreted as **BGR** when passed to `cv2.line`. If the renderer were ever feeding a `pygame.Surface` those same tuples would be wrong.

**How to avoid:** Name the constants `OBJECT_COLORS_BGR` explicitly. Assert in tests: after drawing a known-color line, `frame[y, x]` should equal the expected BGR triple.

### Pitfall 6: Float→int pixel coordinate rounding

**What goes wrong:** Single-pixel shimmer/jitter on lines during orbit animation. Lines look "noisy" as the camera rotates.

**Why it happens:** `int(x)` truncates toward zero (floors for positive, ceils for negative). For negative screen coords (off-left-edge) this asymmetry produces a half-pixel bias that manifests as shimmer.

**How to avoid:** Use `int(round(sx))` (as in the `project_point` example above), not `int(sx)`.

### Pitfall 7: `cv2.imshow` needs a DISPLAY; tests must not call it

**What goes wrong:** `pytest` on CI/headless Pi hangs or crashes with `cannot connect to X server`.

**How to avoid:** Tests call `renderer.render(scene)` and inspect the returned numpy array directly. `cv2.imshow` and `cv2.waitKey` appear only in `demo_wireframe_room.py` `main()`.

### Pitfall 8: opencv-python-headless has no GUI functions

**What goes wrong:** `cv2.imshow` raises `cv2.error: The function is not implemented. Rebuild the library with Windows, GTK+ 2.x or Cocoa support`.

**Why it happens:** The project uses `opencv-python-headless` deliberately (per `CLAUDE.md` stack table) because it's lighter on Pi and avoids Qt deps. **The `-headless` build strips `imshow`.**

**How to avoid:** For the demo script, prefer recording to video (`cv2.VideoWriter`) over live display. **OR** make the demo's live-window mode import `cv2` through a thin wrapper that catches the `not implemented` error and falls back to a pygame `Surface` using `pygame.image.frombuffer(frame[..., ::-1].tobytes(), (w, h), 'RGB')`. **OR** gate live display behind an `--imshow` flag that is documented as requiring a full `opencv-python` (non-headless) install.

**Recommendation:** Default demo mode is `--save ./tmp/wireframe_demo.mp4 --duration 10` (no window). Add `--show` as an optional flag. Document the headless caveat. This matches the project's Pi-first philosophy. [VERIFIED from `CLAUDE.md`: "opencv-python-headless >=4.8 ... Headless avoids Qt deps."]

### Pitfall 9: `mp4v` FOURCC codec availability

**What goes wrong:** `cv2.VideoWriter` silently writes a 0-byte file and returns `False` from `write()`, or logs `OpenCV: FFMPEG: tag 0x7634706d/'mp4v' is not supported`.

**How to avoid:** Verified available on this host: `cv2.VideoWriter_fourcc(*'mp4v')` → `1983148141`. [VERIFIED] Still, the demo should check `writer.isOpened()` after construction and fall back to `MJPG` + `.avi` if `mp4v` isn't supported on the user's opencv build.

### Pitfall 10: Font rendering on headless Pi

**What goes wrong:** `cv2.putText` silently draws nothing.

**Why it happens:** `cv2.FONT_HERSHEY_*` fonts are compiled **into** OpenCV, not loaded from a file, so they work on headless. This pitfall is preemptive — TrueType font loading would require a file. Stay on Hershey fonts exclusively. PRD §6.1 already specifies `FONT_HERSHEY_PLAIN`.

### Pitfall 11: `learned_map.py` wall segments are NOT ground-truth

**What goes wrong:** A well-meaning planner sees `learned_map.py:347` `_record_wall()` and wires it as the AAS wall source. But those segments are **vision-detected** (from `wall_detector.py` heuristics); they're lossy, confidence-weighted, and in the current-floor grid frame. They're great for the strategic minimap but wrong for a ground-truth wireframe.

**How to avoid:** `AASDepthBackend` uses `AASGraph.areas[i].mins/maxs` **only** (once the parser extension lands). Never reference `LearnedMap._wall_segments`. Document this in `aas_backend.py`'s docstring.

### Pitfall 12: Backward compatibility of AASArea extension

**What goes wrong:** Adding `mins`/`maxs` fields to `@dataclass AASArea` breaks tests that construct `AASArea` directly in `tests/test_property_based.py:216` and `tests/test_tour_metrics.py:48`.

**How to avoid:** Default the new fields to `(0.0, 0.0, 0.0)` so keyword-only test constructions continue to work. Run `uv run pytest tests/test_navigation.py tests/test_property_based.py tests/test_tour_metrics.py -q` before shipping the parser patch.

### Pitfall 13: `uv run python -m` module path

**What goes wrong:** The demo command `python -m openarena_perception.visualization.demo_wireframe_room` fails with `ModuleNotFoundError` if `demo_wireframe_room` does not have an `if __name__ == "__main__"` guard or if `visualization/__init__.py` is missing.

**How to avoid:** Ship the `__init__.py` in Plan 11-01 (empty or with re-exports), ship `if __name__ == "__main__": main()` in Plan 11-03.

## AAS Geometric Facts for oa_dm1

Verified directly by loading `maps/oa_dm1.aas` through `parse_aas` on this host:

| Property | Value |
|----------|-------|
| File path | `maps/oa_dm1.aas` (relative to repo root) |
| File size | 530,380 bytes |
| Num areas | 849 |
| Num reachabilities | 3121 total edges across all areas |
| X range | -674 to 1032 world units (~1700 wide) |
| Y range | 565 to 1653 world units (~1100 deep) |
| Z range | -206 to 296 world units (~500 tall) |
| First few area centers | (1024, 1037, 195), (1018, 1028, 117), (989, 1256, 195) |
| Parse time | < 1 second (sub-50ms observed) |

[VERIFIED via direct `parse_aas('maps/oa_dm1.aas')` execution]

**Useful default bot pose for the demo:** `--pos 232,1600,-112 --yaw 90` is in CONTEXT.md as the intended demo pose. The x=232, y=1600 is well inside the Y range; z=-112 is inside the Z range. The planner should verify this pose lands inside a real walkable area by running `graph.nearest_area(232, 1600, -112)` and asserting the returned area's mins/maxs contain the point before committing to it as the default.

**Q3 world units to real-world intuition:** 1 Q3 unit ≈ 1 inch (≈ 2.54 cm). A 64-unit cube is ~1.6 m, roughly one player width. Standing eye height is ~56 Q3 units (≈ 1.4 m). Use `camera_height = 56.0` as a reasonable default in `world_to_camera` unless the CONTEXT.md decision table overrides. [CITED: Quake 3 engine folklore; ioquake3 `g_main.c` defines `DEFAULT_VIEWHEIGHT = 26` for ducking, standing is 26 + offset. Safe rounding: 40–56.]

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| numpy | projection math | ✓ | 2.4.4 | — |
| opencv-python-headless | line drawing, VideoWriter, GaussianBlur | ✓ | 4.13.0 | — |
| mp4v FOURCC | demo video recording | ✓ | 1983148141 | Fallback to MJPG/.avi |
| `maps/oa_dm1.aas` | demo default AAS file | ✓ | 530380 bytes | `--aas` CLI override |
| `openarena_perception.navigation.aas_parser.parse_aas` | AAS loading | ✓ | in tree | — |
| `openarena_perception.navigation.aas_parser.AASArea.mins/maxs` | wall extraction (AABB path) | **✗ — not yet populated by the parser** | — | **Plan 11-03 Task 1 must extend the parser** (5-line change) |
| `cv2.imshow` GUI | `--show` mode in demo | **✗ — headless build** | — | Default demo writes video, optional `--show` requires non-headless opencv |
| pygame | optional fallback window | ✓ | (used by strategic_hud) | Only if `--show` on headless needs a workaround |
| DISPLAY / X11 | `--show` mode | depends on user | — | Tests and default demo do not require it |

**Missing dependencies blocking execution:** None fundamentally blocking. The AAS parser gap is trivially filled in Plan 11-03 Task 1.

**Missing dependencies with fallback:** `cv2.imshow` is the only real gap. Default demo mode records video, which sidesteps the issue entirely.

## Performance Budget (Pi 5, estimated)

Target: 30+ FPS for the full renderer pipeline at 960×600.

| Stage | Est. cost | Notes |
|-------|-----------|-------|
| `AASDepthBackend.build_scene()` | 1–3 ms | Distance filter over 849 areas + 12 edges × ~20 visible areas. Numpy-batched transform over ~240 points. |
| Room-frame grid tessellation (5 planes × 16×10 cells) | 0.5–1 ms | `room_surface_grid` pure math. Pre-compute once at RoomConfig init, not per frame. |
| `project_line` on ~500 segments | 1–3 ms | Per-segment parametric clip + two `project_point` calls. Batched numpy would be ~0.5 ms; per-segment Python is ~3 ms. |
| `cv2.line` × ~500 with AA | 5–10 ms | The likely dominant cost. `cv2.LINE_8` is ~2× faster if needed. |
| `cv2.GaussianBlur` 960×600 k=9 | 5–8 ms | The **actual bottleneck** on Pi 5 at this resolution. Toggle off (`glow=False` in RoomConfig) for a hard budget. |
| `cv2.addWeighted` composite | 1–2 ms | Cheap. |
| `cv2.putText` × ~12 HUD items | 0.5 ms | Hershey fonts are fast. |
| Scanlines (`np.multiply`) | 2–4 ms | Optional, default off. |
| **Total (glow ON)** | **15–30 ms** | ~33–66 FPS — meets target. |
| **Total (glow OFF)** | **10–18 ms** | ~55–100 FPS — generous headroom. |

[ASSUMED: all Pi 5 line-draw timings. This codebase has no prior cv2-line benchmarks. The planner should add a micro-benchmark to `demo_wireframe_room.py --profile` that prints per-stage timings on first run, and the executor should verify on real Pi hardware before declaring the phase done.]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (already in use across all 10 prior phases) |
| Config file | `pyproject.toml` (project-wide) |
| Quick run command | `uv run pytest tests/test_wireframe_projection.py -x -q` |
| Full suite command | `uv run pytest tests/test_wireframe_*.py -q` |
| Integration with phase gate | Full suite green before `/gsd-verify-work` |

### Phase Requirements → Test Map

| Req (synthesized from CONTEXT.md scope) | Behavior | Test type | Automated command | File exists? |
|-----------------------------------------|----------|-----------|-------------------|--------------|
| Pinhole math correct | `focal_length`, `project_point` given known inputs produce expected outputs | unit | `uv run pytest tests/test_wireframe_projection.py::test_focal_length -x` | ❌ Wave 0 |
| Near-plane clip works | Segment with one endpoint at z<0.1 is trimmed, not dropped | unit | `uv run pytest tests/test_wireframe_projection.py::test_near_clip -x` | ❌ Wave 0 |
| `world_to_camera` sign-correct | N/E/S/W areas land in correct camera-space quadrants for known yaws | unit | `uv run pytest tests/test_wireframe_projection.py::test_world_to_camera_signs -x` | ❌ Wave 0 |
| Depth color curve | `project_depth_color` returns near_color at z=0, far_color at z=max | unit | `uv run pytest tests/test_wireframe_projection.py::test_depth_color_lerp -x` | ❌ Wave 0 |
| `room_surface_grid` tessellation | Correct cell count + edge positions for a known quad | unit | `uv run pytest tests/test_wireframe_projection.py::test_room_grid -x` | ❌ Wave 0 |
| `cube_edges` returns 12 | AABB produces exactly 12 distinct edges | unit | `uv run pytest tests/test_wireframe_projection.py::test_cube_edges -x` | ❌ Wave 0 |
| Renderer draws something | Render known scene + assert non-bg pixels in expected regions | integration | `uv run pytest tests/test_wireframe_renderer.py -x` | ❌ Wave 0 |
| HUD text renders | HUD elements produce non-bg pixel blocks in expected rects | integration | `uv run pytest tests/test_wireframe_hud.py -x` | ❌ Wave 0 |
| AASDepthBackend wall emit | Synthetic 4-area graph produces expected line count in camera space | integration | `uv run pytest tests/test_wireframe_aas_backend.py -x` | ❌ Wave 0 |
| AAS parser AABB extension | Parse oa_dm1, assert `graph.areas[1].mins/maxs` are within Z range | integration | `uv run pytest tests/test_navigation.py::test_aas_aabb_extracted -x` | ❌ Wave 0 |
| Parser backward compat | Existing `test_navigation`, `test_property_based`, `test_tour_metrics` still pass | regression | `uv run pytest tests/test_navigation.py tests/test_property_based.py tests/test_tour_metrics.py -q` | ✓ — must not regress |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_wireframe_projection.py -x -q` (fastest, < 2s)
- **Per wave merge:** `uv run pytest tests/test_wireframe_*.py -q` + regression suite on navigation/property/tour_metrics
- **Phase gate:** Full suite `uv run pytest -q` green

### Wave 0 Gaps

- [ ] `tests/test_wireframe_projection.py` — pure math unit tests
- [ ] `tests/test_wireframe_renderer.py` — renderer pixel-spot tests
- [ ] `tests/test_wireframe_hud.py` — HUD rendering
- [ ] `tests/test_wireframe_aas_backend.py` — AAS backend with synthetic fixture
- [ ] Test for AASArea mins/maxs extraction (can live in existing `tests/test_navigation.py`)

No framework install needed — `pytest` already configured.

## Security Domain

Phase 11 adds a visualization/debug tool. It does not expose new network endpoints, does not accept untrusted input, does not read secrets, and does not write to user-owned directories outside `tmp/`. ASVS categories V2/V3/V4 (auth, session, access control) do not apply. V5 (input validation) applies weakly to the demo's CLI arguments (`--pos`, `--yaw`, `--duration`) — validate that they parse as numbers and are within sensible bounds before passing to cv2 functions (garbage `--pos 1e30` could blow up the near-plane clip). No hand-rolled crypto. No threat surface beyond the existing project.

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | AASArea struct layout is `int+int+int+mins[3]+maxs[3]+center[3]` at 48 bytes | Code Examples / AABB extraction | Plan 11-03 parser extension reads wrong bytes. Mitigation: the values dumped from area 1 (mins=(999,785,188), maxs=(1137,1433,204), center=(1024,1037,195)) are internally consistent and order the only way that makes sense — mins < center < maxs on all three axes. Still, executor should cross-check against `ioquake3/code/botlib/be_aas_file.h` `aas_area_t` before committing. |
| A2 | Backward compat of AASArea dataclass extension | Code Examples | Only matters if any existing caller uses positional rather than keyword construction. Mitigation: run the 3 listed test files; existing fixtures build with keywords. |
| A3 | Pi 5 cv2.line timing budget (~5–10 ms for 500 AA lines) | Performance Budget | If slower, may need to drop AA or reduce line count. Mitigation: `--profile` flag added to demo as a first-run diagnostic. |
| A4 | `cv2.GaussianBlur` is the bottleneck at k=9 on 960×600 | Performance Budget | If it's not, performance optimization effort gets aimed wrong. Mitigation: same profiling hook. |
| A5 | Default eye-height of 40–56 Q3 units | Code Examples / world_to_camera | Cosmetic — too low puts the camera near the floor (everything looks tall), too high puts it near the ceiling. Mitigation: make it a RoomConfig field; tune in live demo. |
| A6 | Q3 yaw is CCW from +X (east=0°, north=90°) | Pitfalls / world_to_camera | Would invert the orbit direction. Mitigation: cross-verified against `navigator.py:292`'s `atan2(dy, dx)` usage — same convention. HIGH confidence. |
| A7 | Face-mesh lumps (bboxes/vertexes/planes/edges/faces) are not needed for this phase | Summary | If AABB walls look too boxy or visually wrong, the phase fails aesthetic acceptance. Mitigation: the AABB approach is honestly what the bot navigation uses; visual output will match the bot's actual mental model, not a prettified ground-truth mesh. Defer face-mesh to a later phase if user wants higher fidelity. |
| A8 | oa_dm1 default pose (232, 1600, -112, yaw 90) is inside a walkable area | AAS Geometric Facts | Cosmetic — demo opens inside geometry or outside the map. Mitigation: Plan 11-03 demo startup should `graph.nearest_area(pos)` and warn if the nearest area's AABB does not contain the pose. |
| A9 | `opencv-python-headless` strips `cv2.imshow` | Pitfall 8 | Phase docs mislead users about `--show` availability. Mitigation: CLAUDE.md explicitly cites `opencv-python-headless` as "Headless avoids Qt deps" — this is definitionally correct. [CITED: CLAUDE.md]. Verify by `python3 -c "import cv2; cv2.imshow('x', __import__('numpy').zeros((10,10,3),'uint8'))"` on the host if doubt remains. |

## Open Questions

1. **Should the parser extension land in Plan 11-01 or Plan 11-03?**
   - Currently CONTEXT.md has it in 11-03. This is correct: 11-01 is pure math and needs no AAS. But the planner should note that 11-03 carries two kinds of work — parser extension + AASDepthBackend + demo — and might deserve being split.

2. **Is the "orbit" animation cosmetic or load-bearing for the smoke test?**
   - CONTEXT.md lists `--orbit` as a default. Orbit exercises the full `world_to_camera` math across all yaws, making it the best default visual smoke test. Keep it.

3. **Does the project have a live `viewpos` capture source the demo can consume?**
   - `openarena_perception/navigation/navigator.py:63` `update_position()` reads viewpos via `GameBridge.rcon("viewpos")`. A `--live-pose` demo mode could hook into this, but it requires a running OpenArena instance. Out of scope; synthetic + orbit is sufficient for Phase 11.

4. **How do we visually verify the renderer is "right" given no golden images?**
   - Recommendation: `demo_wireframe_room.py` supports `--save-first-frame screenshot.png` for manual human inspection. Plan 11-03's acceptance check is "eyeball the orbit video" rather than pixel-golden compares.

## State of the Art

| Old approach (PRD v0.1) | Current approach (Version B) | When changed | Impact |
|-------------------------|------------------------------|--------------|--------|
| Depth Anything V2 neural monocular depth | AAS geometry projection | This phase | −200–500 ms/frame → <1 ms. Zero new deps. Ground-truth depth instead of relative. |
| torch + depth-anything-v2 packages | numpy + opencv-python-headless only | This phase | Pi install weight unchanged. |
| Bastion Bridge gateway offload for neural inference | Pi-native single-process rendering | This phase | No gateway process, no network hop. |
| screen_to_room unprojection from detection 2D bbox + sampled depth map | Same function, takes explicit depth_hint argument (no depth map available in Version B) | This phase | Available as an escape hatch if a 2D detector ever needs to place an object into the room without a world position, but not the primary path. |

**Deprecated for this phase:**
- `torch`, `depth-anything-v2` — not added.
- `ultralytics` (YOLO model management) — not added.
- GroundingDINO — not added.
- `cv2` full (non-headless) — not added; phase is compatible with the existing `opencv-python-headless`.

## Sources

### Primary (HIGH confidence — direct inspection)

- `openarena_perception/navigation/aas_parser.py` — full read. Canonical source for AAS file format handling in this project. [VERIFIED]
- `openarena_perception/navigation/navigator.py` — full read. Canonical source for Q3 yaw convention (`atan2(dy, dx)` at line 292). [VERIFIED]
- `openarena_perception/navigation/learned_map.py` — full read. Precedent for per-tick wall segment storage and HUD export pattern. Cautionary reference (see Pitfall 11). [VERIFIED]
- `strategic_hud.py` — full read. Precedent for standalone visualization executable with argparse + main loop. [VERIFIED]
- `openarena_perception/hud_schema.py` — partial read. `build_hud_payload` dict pattern. [VERIFIED]
- `openarena_perception/perception/world_parser.py` — partial read. Confirms no BSP/geometry parsing exists in the project; it's a vision parser. [VERIFIED]
- `openarena_perception/models.py` — partial read. `SituationalAwareness` frozen+slotted dataclass convention at line 44. [VERIFIED]
- `maps/oa_dm1.aas` — direct binary inspection. File is 530380 bytes, EAAS v5, 849 areas, 3121 reaches, bounds X∈[-674,1032] Y∈[565,1653] Z∈[-206,296], mins/maxs layout at offsets +12/+24 confirmed, full lump inventory (bboxes/vertexes/planes/edges/edgeindex/faces/faceindex/areas/areasettings/reach/nodes/portals/portalindex/clusters) dumped. [VERIFIED]
- `tests/test_property_based.py`, `tests/test_tour_metrics.py`, `tests/test_navigation.py` — grep + partial read. Precedent for synthetic `AASGraph`/`AASArea` test fixtures. [VERIFIED]
- `python3 -c "import cv2, numpy; ..."` on host — runtime environment probe. cv2 4.13.0, numpy 2.4.4, mp4v codec available. [VERIFIED]
- `.planning/phases/11-wireframe-perception-grid/11-CONTEXT.md` — phase context, locked decisions, scope. Source of truth for Version B pivot.
- `.planning/phases/11-wireframe-perception-grid/11-PRD.md` — original PRD. Still authoritative for §4 (room geometry + projection + depth coloring + RoomConfig), §5.2 (object colors), §6 (HUD elements), §7 (effects), §8.2 (video recording).
- `CLAUDE.md` — project tech stack. `numpy>=1.26`, `opencv-python-headless>=4.8`, Pi 5 target, 10+ FPS, `uv` package manager, pytest.

### Secondary (MEDIUM confidence — standard knowledge + project convention)

- Q3 AAS file format general structure: header + XOR-decrypted lump directory + 14 lumps. [CITED: ioquake3 `code/botlib/be_aas_file.h`, confirmed by project's own parser matching the EAAS v5 ident + version check]
- Q3 world units ≈ 1 inch; standing eye height ~56 units. [CITED: Q3 engine folklore; not verified in-codebase, but the math (1700 Q3 units ≈ 43 m ≈ one large DM room) is internally consistent with oa_dm1's scale]
- cv2 `LINE_AA` vs `LINE_8` performance ratio ~2× on ARM. [ASSUMED: based on ARM NEON AA implementation cost. Must be measured on actual Pi hardware during Plan 11-02.]
- `mp4v` FOURCC availability in `opencv-python-headless` ARM64 wheel. [VERIFIED on this host but the target Pi may use a different build.]

### Tertiary (LOW confidence — needs planner/executor verification)

- Exact byte layout of AAS `aasarea_t` beyond the first 48 bytes (header ints at offsets 0/4/8) — the parser treats offsets 0, 4, 8 as three int slots but their semantic meaning (areanum + numfaces + firstface?) is inferred from the face-mesh lump inventory, not directly from ioquake3 source. Not needed for the AABB path but would become load-bearing if face-mesh rendering is ever pursued. [ASSUMED]
- Pi 5 `cv2.GaussianBlur` cost at k=9 on 960×600. [ASSUMED: 5–8 ms. Profile in Plan 11-02.]
- Whether the orbit default pose `(232, 1600, -112)` is actually inside a walkable area of oa_dm1. [ASSUMED: Plan 11-03 demo startup should verify via `graph.nearest_area` + AABB containment check.]

## Metadata

**Confidence breakdown:**
- Existing stack + module layout: HIGH — read directly, project conventions clear.
- AAS file data layout: HIGH for AABB path (mins/maxs offsets verified by direct float dump), MEDIUM for face-mesh path (lump inventory verified, exact struct layouts inferred).
- Q3 yaw + coordinate conventions: HIGH — cross-referenced against `navigator.py:292` and `strategic_hud.py:406`.
- Pinhole + near-clip math: HIGH — standard, small, testable.
- Pi 5 cv2 performance: MEDIUM — timing estimates are educated guesses until profiled on real hardware.
- `cv2.imshow` headless limitation: HIGH — verified via `CLAUDE.md` stack table note.

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (30 days — stable stack, no fast-moving deps)

---

*Research completed for Phase 11 Wireframe Perception Grid (Version B). Planner can now create 11-01/11-02/11-03 PLAN.md files with confidence the depth source is fully characterized and the AABB wall-extraction path is concrete and minimal.*
