# Plan 11-03 Summary: AAS Parser Extension + AASDepthBackend + Demo CLI

**Completed:** 2026-04-10
**Status:** Complete — human-verified via live tour
**Commits (auto tasks):** `d391b24`, `6a59dc0`, `c3fb4f6`
**Commits (post-checkpoint iteration):** `13bba73`, `bcb9f42`, `cd4eced`, `d1d0308`, `f697718`

## What was delivered

### Auto tasks (completed before human checkpoint)

- **`openarena_perception/navigation/aas_parser.py`** extended with 5-line AABB read (`mins`/`maxs` at byte offsets +12/+24). Backward compatible via tuple defaults — all 37 existing navigation tests continue to pass.
- **`openarena_perception/visualization/aas_backend.py`** — new `AASDepthBackend` class with:
  - Precomputed per-area AABB edges as `(N, 24, 3)` ndarray in world space
  - `build_scene(bot_pos, bot_yaw, max_distance, max_areas)` — distance-culled batched `world_to_camera` transform
  - Near-plane culling for segments with both endpoints behind camera
- **`openarena_perception/visualization/demo_wireframe_room.py`** — CLI demo with:
  - `--orbit`, `--duration`, `--save` (mp4v default, MJPG/.avi fallback)
  - `--pos` verification via `nearest_area` + AABB containment
  - `--profile` printing p95 per-stage timings
  - Opt-in `--show` (cv2.imshow) with graceful headless fallback
- **3 new test files**: `test_wireframe_aas_parser.py`, `test_wireframe_aas_backend.py`, and end-to-end smoke test against real `maps/oa_dm1.aas`
- Full regression: 100 tests green

### Post-checkpoint iteration (session continuation after initial visual rejection)

The original orbit demo used AABB cuboids for walls, which looked like "floating boxes in space" because:
1. Each area's bounding box has phantom top/bottom faces (not real walls)
2. Adjacent areas overlap at shared boundaries
3. Doorways are invisible (two AABBs overlap at the door)

User rejected this at the human checkpoint: "I want to see what the bot should be seeing." Three iterations followed:

**Iteration 1 — Live pose integration (`13bba73`):**
- Added `--live` flag that polls `./tmp/oa_hud_state.json` for bot `x, y, z, yaw` each frame (uses the Phase 10 HUD state file)
- Added `--no-room` flag to skip the static holodeck frame (it was competing visually with the AAS geometry)
- Added `--show-pygame` flag with a pygame-based display window (works around `opencv-python-headless` stripping `cv2.imshow`)
- Added live HUD extras showing intent macro, sub-intent, area, paused flag, tick counter — same source as Phase 10 strategic HUD

**Iteration 2 — Path B face mesh (`bcb9f42`, `cd4eced`, `d1d0308`):**
- Extended `aas_parser.py` to decode lumps 1-6 (vertexes, planes, edges, edgeindex, faces, faceindex) with verified stride layouts:

  | Lump | Content | Stride | Count (oa_dm1) |
  |------|---------|--------|----------------|
  | 1 | vertexes (vec3 float) | 12 | 4195 |
  | 2 | planes (normal + dist + signbits) | 20 | 1190 |
  | 3 | edges (v0, v1 int32) | 8 | 8544 |
  | 4 | edgeindex (signed int32) | 4 | 23677 |
  | 5 | faces (planenum/flags/numedges/firstedge/front/back) | 24 | 5083 |
  | 6 | faceindex (signed int32) | 4 | 7764 |

- Rewrote `AASDepthBackend._build_scene_mesh` to emit face polygon edges instead of AABB cuboids
- **Wall filter**: a face is rendered only if `frontarea == 0 || backarea == 0` (one side is solid void). Internal portals between walkable areas are filtered out, so **doorways appear as real gaps** in the wireframe. This was the key insight.
- Topology walk test (`test_parse_aas_oa_dm1_face_mesh_topology_resolves`) traces area 1 → faceindex → faces → edgeindex → edges → vertexes and verifies resolved vertex positions land inside the area AABB.
- Face-mesh `build_scene` median ~4.57ms (up from 0.9ms AABB path, still well under 5ms budget)
- Emits 408 wall segments in forward view vs ~240 AABB edges — richer data, same budget
- Research doc's edge stride of 16 was wrong; correct stride is 8 — caught and corrected during implementation
- 168 tests green after face-mesh rewrite

**Iteration 3 — Alignment + size fixes (`f697718`):**
- `camera_height` default 40 → 26 (Q3 `DEFAULT_VIEWHEIGHT` standing eye offset). Fixes floor/ceiling height alignment against the game view.
- `max_distance` default 1024 → 384 units. Dramatically reduces "see-through walls" by culling far geometry that was bleeding through near walls.
- New CLI flags: `--width`, `--height`, `--fov`, `--camera-height` so the user can match OpenArena's exact settings
- `--live` preset default size 320×240 (inset-sized) so the wireframe window fits alongside the game and strategic HUD

### Visual verification

Single-item tour to `item_health_mega` with the three-window setup:
- OpenArena game window
- Phase 10 strategic HUD (1000×700, intent panel, minimap)
- Phase 11 wireframe demo (320×240, face mesh, live pose)

User confirmed: *"it's looking good. the bot seems to be responding pretty well, and the vision seems to be aligned with what the bot sees for the limited frames that it's captured and displayed."*

## Known limitations (deferred to Phase 12)

1. **See-through walls still possible** at the edge of `max_distance=384`. Real occlusion needs back-face culling, painter's algorithm, or BSP hidden-surface removal. Not solved this phase.
2. **Two HUD windows show overlapping metrics** (Phase 10 strategic HUD + Phase 11 wireframe HUD). Deduplication deferred to Phase 12 Open-Perception consolidation.
3. **No direct-path visualization** — the wireframe doesn't show the bot's planned A* path or current waypoint as 3D overlays. Deferred.
4. **No Hailo NPU usage** — the NPU is idle while the wireframe renders. Future phase could wire YOLO person detection via Hailo into `SceneGeometry.boxes`.

## Files changed

### Auto tasks
- `openarena_perception/navigation/aas_parser.py`
- `openarena_perception/visualization/aas_backend.py` (created)
- `openarena_perception/visualization/demo_wireframe_room.py` (created)
- `openarena_perception/visualization/__init__.py`
- `tests/test_wireframe_aas_parser.py` (created)
- `tests/test_wireframe_aas_backend.py` (created)

### Post-checkpoint iteration
- `openarena_perception/visualization/wireframe_room.py` (added `draw_room_frame` param)
- `openarena_perception/visualization/config.py` (camera_height default)
- `openarena_perception/visualization/demo_wireframe_room.py` (live mode, pygame display, CLI flags)
- `openarena_perception/navigation/aas_parser.py` (face mesh lumps)

## Verification (final)

- 168 tests passing: 74 wireframe + 17 navigation + 13 property_based + 7 tour_metrics + 39 intent + 18 hud_schema
- Live visual verification via single-item tour
- Phase 10 still green (all intent/HUD/stuck tests passing)
- No new runtime dependencies (numpy + opencv-python-headless + pygame — all pre-existing)

## What's next

Plan 11-03 closes Phase 11 — Wireframe Perception Grid (Version B). The face-mesh pipeline is the foundation; the remaining UI consolidation work moves to Phase 12 (Open-Perception).
