# Wireframe Perception Grid — Technical Specification

**Project:** OpenClaw FPS Bot — Spatial Visualization Module
**Author:** Brandon / Hoyack Technology & Automation Consultancy
**Version:** 0.1.0
**Date:** April 2026

---

## 1. Purpose

The Wireframe Perception Grid provides a real-time, first-person 3D wireframe rendering of the environment as perceived by the bot's depth estimation pipeline. It serves as the primary spatial awareness debug view and, optionally, as a forward-facing visualization of the bot's "understanding" of the game world.

The aesthetic target is a holodeck-style perspective grid room — floor, ceiling, and walls rendered as receding wireframe planes — with detected geometry (obstacles, players, pickups) projected into the room as green wireframe objects. Think Battlezone (1980), TRON lightcycle grid, or the Danger Room from X-Men.

---

## 2. System Context

The module sits between the perception pipeline and the bot's decision layer. It consumes depth frames and object detections, and outputs a rendered BGR image each tick.

Pipeline:
Screen Capture (mss) -> Depth Estimation (Depth Anything V2 vits/vitb) -> Depth Map HxW float32
                     -> Object Detection (YOLO / GroundingDINO / pytesseract) -> 2D bboxes
Both feed: Wireframe Perception Grid renderer (Room Grid + Obstacle Overlay + Depth Contour + HUD)
Output: BGR frame via cv2.imshow / streaming / recording

---

## 3. Depth Estimation Backend

### 3.1 Primary: Depth Anything V2
- Repository: DepthAnything/Depth-Anything-V2
- License: Apache-2.0 (Small), CC-BY-NC-4.0 (Base/Large/Giant)
- Model tiers: vits (25M, ~120 FPS 4090, real-time), vitb (98M, ~60 FPS, high quality), vitl (335M, ~30 FPS, offline)
- Integration via depth_anything_v2.dpt.DepthAnythingV2, infer_image returns HxW float32 numpy (relative depth)

### 3.2 Alternative: DepthFM
- Repository: CompVis/depth-fm
- Single-step inference via flow matching; benchmark against DA-V2 for the OpenArena frame size and GPU.

### 3.3 Raspberry Pi Considerations
- DA-V2 vits on CPU at ~2-5 FPS depending on input resolution
- Options: downsample 256x256, quantize INT8 via ONNX Runtime, run every Nth frame with interpolation, offload to gateway via Bastion Bridge

---

## 4. Wireframe Room Renderer

### 4.1 Core Concept
Five grid planes (floor, ceiling, left wall, right wall, back wall) as wireframe grids converging to a vanishing point. Camera at near end looking forward (+Z). Detected geometry overlaid as colored wireframe boxes or depth contour lines.

### 4.2 Room Geometry
Coordinate system: X left/right, Y up/down (screen), Z near/far
Default dimensions: Width 10 (X: -5..+5), Height 6 (Y: -3..+3), Depth 20 (Z: 0.5..20)
Each surface is a parametric quad (origin + two axis vectors) tessellated into a grid of divs_u x divs_v cells.

Surface table:
- Floor: origin (-W/2, +H/2, 0.5), axis_u (W,0,0), axis_v (0,0,D-0.5)
- Ceiling: origin (-W/2, -H/2, 0.5), axis_u (W,0,0), axis_v (0,0,D-0.5)
- Left Wall: origin (-W/2, -H/2, 0.5), axis_u (0,H,0), axis_v (0,0,D-0.5)
- Right Wall: origin (+W/2, -H/2, 0.5), axis_u (0,H,0), axis_v (0,0,D-0.5)
- Back Wall: origin (-W/2, -H/2, D), axis_u (W,0,0), axis_v (0,H,0)

### 4.3 Perspective Projection
Pinhole camera model: fx = screen_width / (2 * tan(FOV/2)), fy=fx
screen_x = cx + (world_x * fx / world_z); screen_y = cy + (world_y * fy / world_z)
Default FOV 90 deg to match OpenArena default.

### 4.4 Depth-Based Line Coloring
- Near (Z < proximity_threshold): warning color red/orange (close obstacle)
- Mid-range: interpolated near_color (bright white/green) -> far_color (dim gray/blue)
- Far (approaching back wall): faded to near-black
- Curve: t = (z / max_depth)^fade_power

### 4.5 Configuration Dataclass (RoomConfig)
width=960, height=600
room_width=10.0, room_height=6.0, room_depth=20.0
grid_lines_x=16, grid_lines_y=10, grid_lines_z=20
fov_deg=90.0, cam_x/y/z=0.0
bg_color=(0,0,0), grid_color=(180,180,180), accent_color=(0,255,100)
glow=True, scanlines=False, hud=True

---

## 5. Obstacle Overlay System

### 5.1 Wireframe Boxes
Detected objects as 12-edge axis-aligned cubes inside room volume. Box = (x, y, z, width, height, depth) in room coordinates.
screen_to_room(bbox_2d, depth_map, room_config): samples depth at detection center, unprojects via pinhole model to room X/Y, estimates box size from pixel extent (box_d = box_w * 0.5).

### 5.2 Object Classes & Colors
- Player: (255, 50, 50) red hostile
- Pickup: (50, 255, 255) cyan health/ammo/armor
- Door/Portal: (255, 255, 50) yellow navigable
- Wall/Static: (0, 255, 100) green environmental
- Unknown: (180, 180, 180) gray

### 5.3 Depth Contour Projection
When depth map without discrete detections: project contours as floating wireframe scan lines. Sample depth at column intervals, vertical segments floor->ceiling at average depth Z, horizontal lines connect adjacent columns. "Sonar ping" effect.

---

## 6. HUD Overlay

### 6.1 Elements
- Frame counter (top-left): FRAME 000042
- Room dimensions (top-left): ROOM 10x6x20
- FOV + grid density (top-left): FOV 90 GRID 16x10x20
- Mode indicator (top-left): MODE: PATROL / COMBAT
- Object count (top-left): OBJECTS: 3
- Crosshair (center): simple cross
- Status bar (bottom-left): // SPATIAL GRID ACTIVE
- Source resolution (bottom-right): SRC 640x480
- Corner brackets (all corners): DOS-style UI chrome

### 6.2 Custom HUD Fields
renderer.render(depth_map, obstacles, extra_hud={MODE, HP, AMMO, TARGET, POS, YAW, ...}) displays extras below standard HUD. This is the integration point for bot state.

---

## 7. Visual Effects

### 7.1 Glow / Bloom
Gaussian blur of canvas alpha-composited back onto itself. CRT phosphor bloom. Controlled by glow_radius, glow_strength.

### 7.2 Scanlines
Optional horizontal black lines at configurable pixel interval, alpha-composited at low strength. CRT raster simulation.

### 7.3 Depth Fade
Grid lines fade bright (near) -> dim (far). Curve: (z/max_z)^fade_power. fade_power<1 compresses fade toward far end (more visible lines), >1 fades aggressively.

---

## 8. Integration with Existing Project

### 8.1 Perception Loop
In perception tick: screen = capture_screen(); depth = depth_model.infer_image(screen); detections = detect_objects(screen); game_state = parse_hud(screen); obstacles = [screen_to_room(d.bbox, depth, room_cfg) for d in detections]; wireframe = renderer.render(depth_map=depth, obstacles=obstacles, extra_hud=game_state.to_dict()); cv2.imshow("PERCEPTION", wireframe)

### 8.2 Recording
cv2.VideoWriter to perception_log.mp4 at 30 FPS (960x600 mp4v).

### 8.3 Streaming via Bastion Bridge
For Pi agents, compress depth map (JPEG low quality) and send over Bastion Bridge. Gateway renders wireframe and displays on operator console.

### 8.4 Multi-Agent Fleet View
1-Gateway-to-N-Agent: gateway tiles wireframe views from multiple agents into a single monitoring dashboard.

---

## 9. Performance Targets

| Component | Target | Budget (ms @ 30 FPS) |
|-----------|--------|----------------------|
| Screen capture | < 5ms | 5 |
| Depth estimation (vits) | < 10ms (4090) | 10 |
| Object detection | < 15ms | 15 |
| Wireframe render | < 3ms | 3 |
| Total per frame | < 33ms | 33 |

Wireframe render is pure CPU (numpy + OpenCV line drawing). At very high grid densities, move grid to GPU via OpenGL instanced line draws.

---

## 10. Future Extensions

### 10.1 Accumulated World Map
Persistent voxel grid / occupancy map accumulates geometry over time. Wireframe room shows complete mental model, not just current FOV. Pairs with nav/pathfinding layer.

### 10.2 Trajectory Visualization
Planned bot path + predicted enemy positions as wireframe lines/tubes inside the room. Passive debug -> active tactical display.

### 10.3 Minimap Overhead View
Top-down orthographic wireframe of accumulated occupancy map. HUD inset in corner of main wireframe view.

### 10.4 Sound Localization
Audio cues as expanding wireframe rings or directional indicators inside room volume.

### 10.5 Real-Time OpenGL Renderer
Migrate CV2 line drawing to OpenGL/Vulkan for GPU-accelerated rendering at higher densities. Enables real-time viewpoint rotation (detached camera for spectating bot perception from any angle).

---

## 11. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| numpy | >= 1.24 | array math, projection |
| opencv-python | >= 4.8 | line drawing, image output |
| torch | >= 2.0 | depth model inference |
| depth-anything-v2 | latest | monocular depth estimation |
| ultralytics | >= 8.0 | YOLO object detection (optional) |

---

## 12. File Manifest

- wireframe_room.py — Room renderer (holodeck grid + obstacle overlay) — PRIMARY module for this spec
- wireframe_3d.py — Surface mesh renderer (depth map as 3D wireframe) — alternative mode
- wireframe_grid.py — 2D depth-warped grid (legacy / simple mode) — alternative mode
