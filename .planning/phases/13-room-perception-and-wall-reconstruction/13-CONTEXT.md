# Phase 13: Room Perception and Wall Reconstruction - Context

**Gathered:** 2026-04-11
**Status:** Ready for planning (research recommended)
**Source:** Design conversation with user after Phase 12.1 live verification revealed the existing `wall_segments` data (500 stubby perpendicular lines) is unusable as architectural geometry.

<domain>
## Phase Boundary

Replace the current stub-based wall recording in `learned_map.py` with a proper perception-to-geometry pipeline so the bot can understand **rooms** and their **walls** from raw observations. Ultimate goal: a bot that plays competitive deathmatch on maps with no AAS file available.

**In scope — the "large" bucket the user selected:**
- **Raycast point cloud capture** — replace `_record_wall()` stubbing with raycasts (origin + direction + hit point, or observation sample), stored as a point cloud that accumulates during play
- **Line fitting** — periodically run RANSAC or Hough transform on the point cloud to extract continuous architectural lines (not stubs). Walls are long straight segments with confidence.
- **Corner detection** — where two fitted lines meet at an angle (not parallel), emit a corner vertex
- **Room polygon inference** — detect closed loops of fitted walls; each closed loop becomes a `Room` entity with a polygon boundary
- **Room knowledge log** — per-room memory: dimensions, items seen inside, entry/exit points (where corners break / openings connect to other rooms), fitted wall geometry, first-seen/last-seen timestamps, visit count
- **Minimap rendering** — replace the cloud of red stubs with clean CAD-style fitted lines; rooms rendered as outlined polygons with fill; the current-room highlighted
- **Phase 13 must NOT break Phase 12.1's current-floor AAS filter or learned-map grid display** — the new fitted geometry renders ON TOP, not INSTEAD OF

**Out of scope (explicit non-goals for Phase 13):**
- Active wall-mapping skills (bot deliberately rotating to sweep walls) — deferred to a later phase
- Multi-story room inference (Phase 12.1's floor filter still governs what's visible; within a floor, rooms are 2D)
- Real-time incremental line fitting at every tick — fitting runs at a slower cadence (e.g. every N seconds or on room-boundary crossing)
- Replacing AAS entirely — AAS + fitted walls coexist during Phase 13. Only after Phase 13 proves out can we consider running with no AAS at all.
- Combat/tactics use of room knowledge — Phase 13 produces the data and the display; using it for pathing/combat is a follow-up phase

</domain>

<decisions>
## Implementation Decisions

### Data capture (replaces current `_record_wall`)
- **LOCKED:** Replace `_record_wall()` perpendicular stubbing. The bot currently emits 64-unit cross-strokes at forward projection points — these are unusable as architectural geometry.
- **LOCKED:** New approach = store **raycasts** — each observation is `(origin_x, origin_y, origin_z, dir_angle_deg, hit_x, hit_y, hit_z, confidence, timestamp)`. Call them "wall hits" or "raycast samples" — a point cloud of wall-hit points along with where the bot was looking from.
- **LOCKED:** Sources of raycast observations — at minimum: the existing `wall_ahead` + `wall_score` from the vision forward-scan. Also consider: perimeter scan from stuck-recovery, optional deliberate side-scan during idle ticks. Exact sources are Claude's discretion, but must be reusing existing perception outputs, not adding new vision work.
- **LOCKED:** Point cloud is per-floor (reuse Phase 12.1 floor threshold) and stored in `learned_map.json` alongside the existing grids and edge memory. Cap total points per floor to prevent unbounded growth (Claude picks the cap — expect ≤ 5000 per floor, with decimation strategy when cap reached).
- **LOCKED:** Backward compatibility — on load, if an older `learned_map.json` has `wall_segments` but no raycast point cloud, IGNORE the old segments (do not try to round-trip stubs into points — user already reset the data for `oa_dm1`). New saves only write the new schema. Keep `wall_segments: []` empty in new saves so older loaders don't crash.

### Line fitting
- **LOCKED:** Periodically (not per tick) run a line-fitting pass over the point cloud. Exact cadence is Claude's discretion — expect every N seconds OR on room-boundary crossing OR explicit `fit_now()` API.
- **LOCKED:** Algorithm = RANSAC or Hough. Claude picks based on research; RANSAC is generally better for noisy outdoors data, Hough for binary grids. Publish the choice in PLAN.md with reasoning.
- **LOCKED:** Output of fitting = list of `Wall` objects: `(x1, y1, x2, y2, confidence, support_count, first_seen, last_seen)`. "Support count" = how many raycast samples agree with this line.
- **LOCKED:** Walls must merge across fitting passes — a new pass shouldn't produce disconnected duplicates of an existing wall. Merging key: collinearity + proximity + overlap of x/y ranges.
- **LOCKED:** Walls have a confidence threshold below which they're treated as "candidate" and not rendered / not used for room inference. Claude picks the threshold.

### Corner detection
- **LOCKED:** A corner exists where two fitted walls meet at an angle NOT close to 0°/180° (i.e. they're not parallel) AND their endpoints are within a proximity threshold (e.g. 32 units).
- **LOCKED:** Each corner is `(x, y, wall_a_id, wall_b_id, angle_deg, confidence)`.
- **LOCKED:** Corners are first-class entities, not just computed at render time — they form the vertices of room polygons.

### Room polygon inference
- **LOCKED:** A `Room` is a closed loop of walls connected by corners. Detection: walk the corner graph looking for cycles.
- **LOCKED:** Minimum room size (to avoid tiny noise polygons): Claude picks — expect ~64×64 or larger.
- **LOCKED:** Rooms are inferred lazily, not every frame. Trigger: after a line-fitting pass that added/modified walls OR on explicit API call.
- **LOCKED:** Open doorways — where two walls ALMOST meet but leave a gap (<~96 units) — create a `Doorway` entity connecting two rooms OR one room to "outside". This is how the bot understands room-to-room connectivity without AAS.
- **LOCKED:** Rooms that cannot be closed (only 2 or 3 walls found so far) remain as `PartialRoom` and do not participate in polygon rendering.

### Room knowledge log
- **LOCKED:** Per `Room`: `id, polygon_vertices, bounds (min/max xy), area (sq units), walls[], corners[], doorways[], items_seen[], visit_count, first_seen_ts, last_seen_ts, last_visited_ts, notes (freeform)`
- **LOCKED:** `items_seen` = what items (weapons/health/armor/powerup) the bot has spotted WHILE INSIDE the room's polygon. Reuses existing item-on-map data from ReactiveAgent. Stored with timestamps.
- **LOCKED:** Per-room data persists in `learned_map.json` alongside walls/corners/doorways/raycasts. Versioned schema — Phase 12 loaders that don't know about rooms should gracefully skip the new fields (they already do for unknown keys).
- **LOCKED:** A new `current_room_id` field is exported via the HUD payload so the stats panel can show which room the bot is in. If no room matches, fall back to area label. Adding this field to `hud_schema.build_hud_payload` as an optional kwarg is required — do NOT break the dedup contract.

### Minimap rendering
- **LOCKED:** Fitted walls rendered as clean bright-green-ish lines (NOT the current `(255,60,60)` red stubs), drawn ON TOP of the learned grid cells but UNDER the trail and waypoints.
- **LOCKED:** Corners rendered as small filled circles at vertex positions.
- **LOCKED:** Room polygons rendered as faint outline + 20% alpha fill. Current room (where the bot stands) gets a brighter outline/fill.
- **LOCKED:** Backward compat — if no fitted walls exist yet (new data not yet produced), fall back silently to the Phase 12.1 display.
- **LOCKED:** Dedup contract from Phase 12 still holds — no duplicate metrics across panels. The new `current_room_id` shows ONCE in stats, not in minimap text.
- **LOCKED:** Red stub rendering (current `wall_segments` draw at lines 192-203 of `minimap.py`) is REMOVED entirely. It served its purpose; it's noise now.

### HUD stats panel impact
- **LOCKED:** Stats panel gets 2 new rows: `room` (current room id or "—") and `room_items` (brief summary like "rl,sg,health" of what's been seen in current room). Both optional, sit below the existing verbose rows. Do NOT exceed panel height — if no room space, bump font size of a less-important verbose row.
- **LOCKED:** 9-verbose-row contract from Phase 12 still intact; these are ADDITIONS at 10 and 11, not replacements.

### Testing strategy
- **LOCKED:** Every new subsystem has unit tests: raycast capture (point cloud grows/decimates correctly), line fitting (known synthetic point clouds produce expected lines), corner detection (given 2 lines → expected corner or nothing), room polygon inference (given walls+corners → expected room or PartialRoom), doorway detection (adjacent rooms with gap → doorway).
- **LOCKED:** Integration test: feed a recorded tour's raycasts (or synthetic ones matching oa_dm1 ground truth) and verify the fitted walls match the known oa_dm1 architecture within a tolerance. Claude picks how to source ground truth — can be a manually-authored fixture file.
- **LOCKED:** Panel isolation tests: MinimapPanel must still render cleanly with EITHER new-schema data OR legacy empty-walls data (backward compat).
- **LOCKED:** Live visual verification checkpoint: run `item_tour.py --no-vision` and eyeball that fitted walls replace the red stubs and rooms are inferred on `oa_dm1`.

### Non-functional constraints
- **LOCKED:** Must maintain Pi 4/5 perception loop 10+ FPS — line fitting runs at a slower cadence, not per tick. Keep per-tick raycast capture <1ms.
- **LOCKED:** Persistence format must be forward-compatible with the Phase 12.1 grids/edge-failure data (same JSON file).
- **LOCKED:** Must not regress 743 passing tests from Phase 12.1.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The data source to replace
- `openarena_perception/navigation/learned_map.py:347-397` — current `_record_wall()` perpendicular stub method (REPLACING)
- `openarena_perception/navigation/learned_map.py:100-136` — `update()` per-tick entry point (wire new capture in here)
- `openarena_perception/navigation/learned_map.py:257-302` — `export_for_hud()` (extend with new fields)
- `openarena_perception/navigation/learned_map.py:185-255` — `save()` / `load()` (versioned schema, extend)

### Where the red stubs get drawn (REMOVING)
- `openarena_perception/visualization/panels/minimap.py:192-203` — current `wall_segments` render block (REMOVE entirely)
- `openarena_perception/visualization/panels/minimap.py:162-163` — `_draw_aas_overhead` call site (new fitted-walls draw happens AFTER this, BEFORE trail)

### HUD schema (additions only)
- `openarena_perception/hud_schema.py` — `build_hud_payload()` accepts optional kwargs; add `current_room_id` and `current_room_items` as optional fields; do NOT break the 7 Phase 12.1 verbose fields

### AAS integration (unchanged but coexisting)
- `openarena_perception/navigation/aas_parser.py:316` — `areas_on_floor()` from Phase 12.1 (coexists with new fitted walls)
- `openarena_perception/navigation/wireframe_aas_backend.py` — existing AAS backend (no changes expected)

### Stats panel (additions only)
- `openarena_perception/visualization/panels/stats.py` — 9 verbose rows are sacred; add 2 more at rows 10 and 11 without reflowing existing ones

### Tests (reference the existing patterns)
- `tests/test_learned_map.py` — add new tests here for raycast capture / line fitting / rooms (create file if missing)
- `tests/test_open_perception_panels.py` — panel backward-compat test
- `maps/oa_dm1.aas` — test fixture for ground truth comparison

### Earlier phases for context
- `.planning/phases/12.1-open-perception-ui-polish-square-wireframe-minimap-reflowed-/12.1-CONTEXT.md` — explicit "room learning deferred to Phase 13+"
- `.planning/phases/12-open-perception-ui/12-CONTEXT.md` — original Open-Perception scope
- `.planning/phases/02-perception-extraction` — perception module structure
- `.planning/phases/04-reflexes-combat-and-navigation-extraction` — navigation module structure (learned_map lives here)

</canonical_refs>

<specifics>
## Specific Ideas

- **Raycast record format (suggestion, not locked):**
  ```
  class RaycastHit(NamedTuple):
      origin_x: float
      origin_y: float
      origin_z: float
      dir_angle_deg: float
      hit_x: float
      hit_y: float
      confidence: float      # from wall_score
      timestamp: float
  ```
  Stored in `learned_map._raycasts_per_floor: List[List[RaycastHit]]` symmetrically to `_grids`.

- **Line fitting: RANSAC outline:**
  1. Pick 2 random points from the cloud
  2. Fit a line through them
  3. Count inliers within 8 units perpendicular distance
  4. If inlier count > threshold, emit a Wall; remove inliers; repeat
  5. Stop when no line gets enough support
  6. Pros: handles outliers well, simple, O(n*iters) per fit. Cons: non-deterministic. Seed RNG for reproducibility in tests.

- **Line fitting: Hough alternative:**
  1. Rasterize point cloud to a bitmap
  2. Run Hough line transform (OpenCV has one ready)
  3. Filter by length + confidence
  4. Pros: deterministic, uses existing OpenCV dependency. Cons: coarser than RANSAC on continuous data.

- **Corner detection pseudocode:**
  ```
  for w1, w2 in combinations(walls, 2):
      angle = angle_between(w1, w2)
      if not (20 < angle < 160): continue  # skip parallel
      p = nearest_endpoint_pair(w1, w2)
      if distance(p) > 32: continue  # too far apart
      corner = midpoint(p)
      emit Corner(corner, w1.id, w2.id, angle, min_conf(w1, w2))
  ```

- **Room inference pseudocode:**
  ```
  graph = build_corner_graph(corners)  # adjacency via shared walls
  for cycle in find_simple_cycles(graph, max_len=8):
      polygon = [corner.xy for corner in cycle]
      if area(polygon) < MIN_ROOM_AREA: continue
      room = Room(polygon=polygon, walls=[w for w in cycle.walls])
      rooms.append(room)
  ```
  Cycles should be simple (no repeats) and short (≤8 walls) to avoid combinatorial blow-up.

- **Per-room item ingestion:** when a new item is observed by ReactiveAgent, check `point_in_polygon(item.pos, room.polygon)` for each room and append if matched.

- **Current room detection:** every N ticks, check `point_in_polygon(bot.pos, room.polygon)` for each room. First match wins. Export `current_room_id` in HUD.

</specifics>

<deferred>
## Deferred Ideas

- **Active wall-mapping skill** (deliberate side-sweeps to complete partial rooms) — belongs in a later phase focused on skills
- **Room-aware pathing** (A* prefers staying in known rooms) — belongs in a navigation phase after Phase 13 ships
- **Room-aware combat** (take cover behind fitted walls, predict enemy routes) — belongs in a combat/tactics phase
- **Multi-story room graph** (3D rooms with vertical doorways) — requires proper 3D fitting; defer until 2D per-floor is solid
- **Replacing AAS entirely** — prove out fitted walls for a few phases first, then revisit
- **Wall material classification** (glass / metal / wood) — out of scope, vision-heavy
- **Enemy room belief** (which room is an enemy likely in) — memory/tactics phase
- **Persistent room naming by player** (user can label rooms via LLM) — LLM integration concern

</deferred>

---

*Phase: 13-room-perception-and-wall-reconstruction*
*Context gathered: 2026-04-11 from design conversation after Phase 12.1 live verification*
*Scope: LARGE (user explicitly chose B3 option — raycasts + fitting + corners + rooms + room log)*
