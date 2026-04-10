# Phase 12: Open-Perception UI — Context

**Gathered:** 2026-04-10
**Status:** Ready for planning
**Source:** Session conversation after Phase 11 visual verification + user-approved design picks

<domain>
## Phase Boundary

This phase delivers **Open-Perception** — a single standalone debug/observability app that replaces both the Phase 10 `strategic_hud.py` and the Phase 11 `demo_wireframe_room.py` with one unified window. Three spatial/status views live side-by-side in a 1400×700 three-panel layout. Every metric has exactly one canonical display — no duplication across panels.

**Three outcomes:**

1. **One app, one window, one event loop** — `open_perception.py` at the project root (or `openarena_perception/visualization/open_perception.py` if kept in-package) replaces both legacy apps. It uses pygame for the window and native display, reads the same `./tmp/oa_hud_state.json` state file the existing apps consume, and renders at ~10 Hz (matching the Phase 10 HUD cadence).

2. **Three-panel layout at 1400×700:**
   - **Left panel (400px wide)** — top-down minimap from Phase 10 (learned map cells, wall segments, player marker with yaw arrow, route waypoints, area highlights)
   - **Center panel (600px wide)** — Phase 11 wireframe face-mesh view, first-person perspective, same live pose read from HUD state
   - **Right panel (400px wide)** — vital stats + intent panel + problem history + verbose telemetry (intent macro + sub + duration, threat badge, path progress bar, verbose telemetry rows)

3. **Deduplicated "vital stats" region** — every metric that previously appeared in both HUDs now appears exactly once. The wireframe panel's own HUD chrome is **reduced to decoration only** (corner brackets, crosshair, status bar, depth-faded frame) — NO numeric overlays, NO text. All numbers live in the right panel.

## What's in scope

### Core app
- `open_perception.py` — the new standalone app, pygame-based, reads `./tmp/oa_hud_state.json`, 1400×700 window, 10 FPS tick
- Three-panel layout with clean visual separators (vertical lines at x=400 and x=1000)
- Single canonical render for every displayed metric

### Left panel — minimap (400x700)
- Reuses the Phase 10 minimap rendering logic (top-down projection of learned map + route waypoints + player marker)
- Player marker with heading arrow (derived from `yaw`)
- Route waypoints color-coded by state: done (gray), current (bright yellow), future (dim blue)
- Learned map occupancy cells rendered as subtle background (VISITED/OPEN/WALL/LIQUID color scheme)
- AAS area outlines rendered as faint overlay (from the Phase 11 parser extension that loads area AABBs)
- Area label for current area (`area_NNN`)

### Center panel — wireframe first-person (600x700)
- Embeds `WireframeRoomRenderer` from Phase 11 (imported, not duplicated)
- Uses `AASDepthBackend` with live pose from HUD state
- `draw_room_frame=False` — no holodeck chrome (clean view)
- **HUD chrome is decoration only**: corner brackets, crosshair, `// PERCEPTION ACTIVE` status bar, bottom-right `SRC NxN` text, depth-faded grid fade. NO numeric overlays, NO `FRAME`, NO `HP`, NO `POS`, NO `MODE` text — these belong in the right panel.
- Renders at the panel's own resolution (600×700, pinhole FOV 90° default, configurable at runtime)

### Right panel — vital stats + intent + problems + verbose (400x700)
- **Vital stats block** (top, 120px): HP, armor, ammo, weapon, pos XYZ, yaw
- **Intent block** (next 110px): current intent macro (big 22pt yellow), sub-intent (white 14pt), duration counter, 2Hz flashing blue border during pause-to-assess, threat badge (green "no threat" / red "THREAT")
- **Intent history** (next 100px): 5 most recent intent transitions in dim gray (from `intent_history` deque)
- **Problem history** (next 100px): 5 most recent problem events, color-coded (red wall_halt, orange stuck, purple pin, cyan respawn, red advisor_halt)
- **Path progress** (40px): `Step N / M` text + filled yellow bar, destination area name
- **Verbose telemetry block** (bottom 230px, scrolling/stacked):
  - `stair_climb: <state>` (idle / climbing target_area=N delta=N)
  - `swim_edge: <state>` (clear / traversing to area N)
  - `advisor: <last thought text>` (truncated to 80 chars)
  - `last_replans: 3 → 4 → 6` (last 3 re-plan step counts)
  - `tick_rate: XX.X FPS` (rolling window over last 30 ticks)
  - `frame_lag: Xms` (if >100ms, red warning)
  - `proactive_halts: N` (running counter)
  - `visual_pin_hits: N` (running counter)
  - `nav_current_step: area N` (where the bot's current path step targets)

### HUD payload extensions

`hud_schema.build_hud_payload` grows to include (if not already present):
- `stair_climb_state` — derived from `navigator.is_climbing_stairs` + target area
- `swim_edge_state` — derived from navigator warning events
- `advisor_last_thought` — `advisor.current_narrative()` or similar
- `last_replan_steps` — a deque of last 3 re-plan step counts tracked in `item_tour.py`
- `tick_rate_fps` — rolling-window FPS (probably already computed by the perception loop)
- `frame_lag_ms` — last tick duration
- `nav_current_step_area` — the navigator's path[step_idx] area id

All additions are optional with safe defaults so any existing test that constructs a bare payload still works.

### Legacy cleanup (Decision 1 — Option C)

- `strategic_hud.py` — **deleted**
- `openarena_perception/visualization/demo_wireframe_room.py` — **deleted**
- All references to them in docs, CLAUDE.md, and the GSD workflow prompts are replaced with `open_perception.py` references
- The `_export_hud` method in `item_tour.py` stays as-is — it writes the same state file the new app reads

### Tests

- `tests/test_open_perception.py` — headless test using `SDL_VIDEODRIVER=dummy` that instantiates the app, feeds a synthetic HUD payload, asserts the three panels render without errors and that specific regions of the frame contain expected pixels
- No golden-image tests (brittle); use region spot-checks
- Regression: all existing Phase 10 + Phase 11 tests must still pass after the legacy apps are removed (the tests don't import them, only the apps did, so this should be clean)

## What's out of scope

- **Interactive controls** (Decision 5 — Option A) — read-only observability this phase. No pause/resume/skip-waypoint/click-to-move. The HUD → bot command channel stays deferred to a later phase.
- **Solving the see-through wall problem** — the wireframe panel inherits whatever occlusion quality Phase 11 delivered. Back-face culling / painter's algorithm / BSP occlusion stays deferred.
- **Hailo NPU wiring** — the wireframe still doesn't render Hailo-detected entities as boxes. Separate future work.
- **Adding GroundingDINO / YOLO / any new detection model**
- **Remote/web HUD** — pygame desktop only
- **Multi-bot fleet view** — single bot only
- **A* path visualization in the wireframe** — center panel stays walls-only; the path is shown in the minimap (left panel) instead
- **Configurable layout** — the 400/600/400 split is locked for this phase. No user-resizable panels.
- **Fullscreen mode / window resize handling** — fixed 1400×700

## Layout rendering contract

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          OPEN-PERCEPTION (1400 × 700)                    │
├───────────────────────┬──────────────────────────────┬───────────────────┤
│                       │                              │  VITAL STATS      │
│        MINIMAP        │       WIREFRAME VIEW         │  HP 100  AR 50    │
│                       │      (first-person)          │  POS X,Y,Z       │
│     (top-down)        │                              │  YAW NNN          │
│                       │   ┌─                    ─┐   │                   │
│   • learned map       │                              │  INTENT           │
│   • AAS areas         │         + crosshair          │  ─────────        │
│   • route waypoints   │                              │  TOURING          │
│   • player + yaw arrow│   └─                    ─┘   │  heading to X     │
│                       │                              │  duration: 2.3s   │
│                       │   // PERCEPTION ACTIVE       │                   │
│                       │                SRC 600×700   │  HISTORY          │
│                       │                              │  (5 rows)         │
│                       │                              │                   │
│                       │                              │  PROBLEMS         │
│                       │                              │  (5 rows)         │
│                       │                              │                   │
│                       │                              │  PATH 5/13 ▓▓▓▓▓░ │
│                       │                              │                   │
│                       │                              │  VERBOSE          │
│                       │                              │  stair_climb:     │
│                       │                              │  swim_edge:       │
│                       │                              │  advisor: "..."   │
│                       │                              │  last_replans:    │
│                       │                              │  tick_rate:       │
│                       │                              │  frame_lag:       │
│                       │                              │  halts: N         │
│                       │                              │  vpin: N          │
│                       │                              │  nav_step: area   │
├───────────────────────┴──────────────────────────────┴───────────────────┤
│  Status bar: map name | elapsed | alive/dead | threat flag              │
└──────────────────────────────────────────────────────────────────────────┘
     400px                        600px                        400px
```

Vertical separators at x=400 and x=1000 (thin 2px lines in `grid_color`).

</domain>

<decisions>
## Implementation Decisions

### File location

**`open_perception.py` at project root.** Mirrors the existing `strategic_hud.py` location (Phase 10 precedent). This is the executable users launch directly. It imports from `openarena_perception.visualization` for the wireframe panel and from existing Phase 10 schema code for the HUD state reading.

### Module structure

- `open_perception.py` — the app entry point, pygame main loop, high-level layout/draw orchestrator
- `openarena_perception/visualization/panels/` — new subpackage for the three panel renderers:
  - `panels/__init__.py`
  - `panels/minimap.py` — `MinimapPanel` class, extracted from existing `strategic_hud.py` minimap drawing code (copy and clean, don't try to preserve the old file)
  - `panels/wireframe.py` — `WireframePanel` class, thin wrapper over `WireframeRoomRenderer` + `AASDepthBackend` from Phase 11
  - `panels/stats.py` — `StatsPanel` class, renders the right-side intent + history + problems + verbose telemetry
- Each panel takes a `HUDState` object and a pygame `Surface` (the sub-rect of the main window) and draws into it
- The main app composes them: `minimap.draw(state, subsurface_left); wireframe.draw(state, subsurface_center); stats.draw(state, subsurface_right)`

This split is ~150 lines per panel — manageable, testable, replaceable.

### HUD state reading

Reuse the existing `openarena_perception/hud_schema.py` infrastructure. Import `STATE_FILE` and extend the `HUDState` class if needed to carry the new verbose fields. The wireframe panel needs the `AASGraph` loaded once at startup (cached) plus live `x, y, z, yaw` per frame.

### State file extensions (additive, backward compatible)

`hud_schema.build_hud_payload` gains optional kwargs:
- `stair_climb_state: Optional[str]`
- `swim_edge_state: Optional[str]`
- `advisor_last_thought: Optional[str]`
- `last_replan_steps: Optional[list[int]]` (last 3)
- `tick_rate_fps: Optional[float]`
- `frame_lag_ms: Optional[float]`
- `nav_current_step_area: Optional[int]`

All default to `None`/empty; existing tests that don't pass them continue to work. The `item_tour.py` `_export_hud` call fills them from the navigator + advisor + perception loop state.

### Deduplication contract (Decision 3 — proposal)

**Every metric has exactly one display location.** The right panel owns all numeric/textual state. The wireframe panel has zero text overlay except pure decoration (`// PERCEPTION ACTIVE`, corner brackets, source-resolution label). The minimap has zero text overlay except the area label for the current area.

Concretely, the wireframe panel's `render()` call passes `extra_hud=None` so no numeric HUD text is rendered over the 3D view. The minimap `draw()` does not include `POS`, `YAW`, `HP`, `AMMO` — those live in the right panel.

### Tick rate and rendering cadence

- Open-Perception runs its own 10 FPS loop (matching Phase 10)
- Each tick: read state file, draw three panels into their sub-surfaces, blit, flip
- Wireframe panel rebuilds its scene from the live pose every tick (same as Phase 11 live mode)
- No sub-panel caching — the panels are cheap enough at 10 FPS

### Legacy file deletion (Decision 1 — Option C)

At the end of the phase, the following files are removed:
- `strategic_hud.py`
- `openarena_perception/visualization/demo_wireframe_room.py`

The repo keeps:
- `openarena_perception/visualization/wireframe_room.py` (the renderer, reused by the new panel)
- `openarena_perception/visualization/aas_backend.py` (reused)
- `openarena_perception/visualization/projection.py` (reused)
- `openarena_perception/visualization/scene.py`, `config.py`, `hud.py`, `effects.py` (all reused; `hud.py` may need a new mode that only renders decoration chrome without numbers)

Any test file that imports `strategic_hud` or `demo_wireframe_room` must be updated or removed.

### Verbose telemetry sources (Decision 4 — use possibilities list)

Required state file fields and their sources:

| Field | Source |
|---|---|
| `stair_climb_state` | `navigator.is_climbing_stairs` property (Phase 10 already added) + `navigator._stair_target_area` |
| `swim_edge_state` | Parse navigator `WARNING` events in the tour loop, track last swim edge in `item_tour.py` state |
| `advisor_last_thought` | `advisor.current_narrative()` from Phase 11's advisor extension |
| `last_replan_steps` | `item_tour.py` tracks `deque(maxlen=3)` of recent replan step counts, pushed on each `Re-planned path from area N: X -> Y steps` log event |
| `tick_rate_fps` | `perception.loop` already computes this (`avg tick NN.N ms (X FPS)` log line) — expose as state |
| `frame_lag_ms` | Last tick duration from perception loop |
| `proactive_halts` | `item_tour._proactive_halts` counter (already exists) |
| `visual_pin_hits` | `item_tour._visual_pin_hits` counter (already exists) |
| `nav_current_step_area` | `navigator.path[navigator.step_idx]` if path exists |

### Testing strategy

- **Headless pygame**: all tests set `SDL_VIDEODRIVER=dummy` so pygame runs without a display
- **Synthetic HUD state fixture**: build a realistic payload with all fields populated, feed into each panel's `draw()`, assert the sub-surface has non-bg pixels in expected regions
- **Panel isolation tests**: test each panel independently; the main `open_perception.py` gets a single smoke test that imports it and runs one tick
- **Legacy deletion regression**: grep the test suite for `strategic_hud` and `demo_wireframe_room` references before deleting; update or remove those tests
- **Target test count**: ~15 new tests across panel + app + HUD state extensions

### Claude's Discretion

- Exact font sizes, padding, and colors within the three panels (use tasteful defaults matching the TRON/CRT aesthetic)
- Whether `hud.py` needs a `decoration_only=True` flag or a new `render_hud_decoration()` function for the wireframe panel
- Whether verbose telemetry items that have no data yet (None) render as blank rows or are hidden
- Exact size of the intent macro font in the right panel
- Whether the status bar at the bottom is one line or two
- Whether the minimap's area outlines come from AAS (adds a new renderer path) or the existing learned map (simpler, less accurate)
- How the `last_replan_steps` deque is parsed out of navigator log events (probably via a small callback rather than log-scraping)
- Whether `open_perception.py` supports a `--aas` flag for specifying a different map, or auto-detects from the HUD state's `map` field

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project instructions
- `CLAUDE.md` — tech stack (pygame, opencv-python-headless, numpy, pytest), Pi 5 target, uv package manager

### Existing code to reuse
- `strategic_hud.py` — Phase 10 HUD, **will be deleted**; extract minimap code into `panels/minimap.py`
- `openarena_perception/visualization/demo_wireframe_room.py` — Phase 11 demo, **will be deleted**; extract live-mode HUD state reading into the new app
- `openarena_perception/visualization/wireframe_room.py` — `WireframeRoomRenderer`, reused by `panels/wireframe.py`
- `openarena_perception/visualization/aas_backend.py` — `AASDepthBackend`, reused
- `openarena_perception/visualization/config.py` — `RoomConfig`, reused
- `openarena_perception/visualization/projection.py` — projection math, reused
- `openarena_perception/visualization/hud.py` — HUD overlay helpers; may need a decoration-only mode
- `openarena_perception/hud_schema.py` — HUD payload schema, **extended** with new verbose fields
- `openarena_perception/navigation/navigator.py` — source for `is_climbing_stairs`, `path`, `step_idx`
- `item_tour.py` — source for proactive_halts, visual_pin_hits, replan tracking

### Existing tests that reference deleted files
- Grep for `strategic_hud` and `demo_wireframe_room` in `tests/` — all references must be updated or removed as part of the deletion task

### Phase history
- `.planning/phases/10-intent-system-and-hud-companion/10-03-SUMMARY.md` — Phase 10 HUD companion precedent
- `.planning/phases/11-wireframe-perception-grid/11-03-SUMMARY.md` — Phase 11 wireframe delivery + iteration history

</canonical_refs>

<specifics>
## Specific Ideas

### User-stated requirements (verbatim from session)

1. "lets consolidate the grid frame UI and the disposition ui and mini map into 1 unified view"
2. "This view should be it's own stand alone app"
3. "shows the bots status with verbose details"
4. "lets also consider that the grid line view has redundant things in it so we only need 1 instance of a given metric"
5. "lets name the UI Component Open-Perception"

### Design picks confirmed by user

1. **Legacy apps** — Option C: delete `strategic_hud.py` and `demo_wireframe_room.py` after Open-Perception ships
2. **Layout** — Option D: 3-panel 1400×700 with minimap left, wireframe center, stats/intent/problems right
3. **Deduplication** — Follow proposal: single "vital stats" region, wireframe chrome reduced to decoration only, no numeric overlays in the wireframe panel
4. **Verbose telemetry** — Use the full possibilities list: stair climb, swim edge, advisor last thought, path step, last replans, tick rate, frame lag, proactive halts, visual pin, nav current step
5. **Interactivity** — Option A: read-only observability this phase; control surface stays deferred

### Proposed plan split

- **Plan 12-01**: HUD schema extensions + state source wiring (item_tour.py / navigator.py) — purely data; no new UI
- **Plan 12-02**: `panels/` subpackage + three panel classes with headless tests
- **Plan 12-03**: `open_perception.py` main app + legacy file deletion + final integration + human-verify checkpoint

Each plan atomic, each delivers testable value.

</specifics>

<deferred>
## Deferred Ideas

- **Interactive controls** (pause/resume, skip waypoint, click-to-move, manual yaw override) — explicitly out of scope for Phase 12. Stays available for a future Phase 13+.
- **Bidirectional HUD ↔ bot command channel** — the reverse-channel state file deferred with interactive controls.
- **See-through wall occlusion fix** — back-face culling / painter's algorithm / BSP occlusion stays on the backlog. Phase 12 inherits Phase 11's wireframe occlusion as-is.
- **Hailo NPU detection overlay** — wiring `hailo_detector.py` into `item_tour.py` and rendering detected players/pickups in the wireframe panel.
- **A* path visualization inside the wireframe panel** — the path stays in the minimap only.
- **Configurable layout / user-resizable panels / fullscreen mode**
- **Remote/web HUD / multi-bot fleet view**
- **Voice/TTS status announcements**
- **LLM-driven natural-language intent narration** (beyond the existing advisor text)

</deferred>

---

*Phase: 12-open-perception-ui*
*Context gathered: 2026-04-10 via session conversation (user picked 1=C, 2=D, 3=proposal, 4=full list, 5=A)*
