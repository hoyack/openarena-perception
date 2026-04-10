# Phase 12: Open-Perception UI — Research

**Researched:** 2026-04-10
**Domain:** pygame compositing, HUD schema extensions, legacy file extraction
**Confidence:** HIGH (all findings verified against source; two MEDIUM items around hook wiring)

## Summary

Phase 12 consolidates the Phase 10 `strategic_hud.py` (root file, ~700 lines) and the Phase 11 `demo_wireframe_room.py` (~420 lines) into a new `open_perception.py` root-level app plus a `panels/` subpackage. Both legacy files are **deleted** at the end of the phase.

Three pieces of existing code do the heavy lifting and are directly reusable:
1. **`strategic_hud.StrategicHUD.draw()` lines 290–513** — world-to-minimap projection + learned-map cells + wall segments + route waypoints + player-with-yaw-arrow. Copy verbatim into `panels/minimap.py`, strip the right-side intent panel (`_draw_intent_panel`) and the disposition/status text blocks (those move to `panels/stats.py`).
2. **`strategic_hud.StrategicHUD._draw_intent_panel()` lines 520–658** — intent macro/sub/duration, 2 Hz pause flash, intent history, problem history with color map, path progress bar, threat badge. Copy into `panels/stats.py` and extend with verbose rows.
3. **`demo_wireframe_room._PygameDisplay` lines 109–148** + the live-mode read loop lines 342–394 — BGR→RGB swap, `pygame.surfarray.make_surface(rgb.swapaxes(0,1))`, HUD state polling. The pygame-surface conversion pattern goes into `panels/wireframe.py` unchanged; the HUD state read helpers (`_read_live_state`, `_extract_pose_from_state`) move into the new app's main loop.

**Primary recommendation:** Structure this phase as a pure extraction + merge. There is no new algorithmic work — every piece of rendering already exists. The risk is mechanical (breaking the one test that imports `strategic_hud`, forgetting a docs reference) not algorithmic.

**Critical discovery:** Exactly **one test** imports `strategic_hud`: `tests/test_hud_schema.py:214 test_contract_build_payload_to_strategic_hud_load`. It must be rewritten to import from a new module (or deleted, since an equivalent unit test against the new `HUDState` class in `open_perception.py` can replace it). **No test imports `demo_wireframe_room`.** Clean deletion for the Phase 11 demo.

---

## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Layout** — 1400×700 three-panel: 400 minimap | 600 wireframe | 400 stats. Vertical separators at x=400 and x=1000 (thin 2 px lines in `grid_color`). NOT resizable, NOT fullscreen, fixed size.
2. **File location** — `open_perception.py` at project root (mirrors `strategic_hud.py` precedent).
3. **Module structure** — `openarena_perception/visualization/panels/{__init__,minimap,wireframe,stats}.py`. Each panel class takes `HUDState` + pygame `Surface` sub-rect and draws into it.
4. **Legacy cleanup** — DELETE `strategic_hud.py` and `openarena_perception/visualization/demo_wireframe_room.py` at end of phase.
5. **Deduplication contract** — every metric has exactly ONE display. Wireframe panel: decoration only (brackets, crosshair, `// PERCEPTION ACTIVE`, `SRC NxN`). NO FRAME / HP / POS / MODE / OBJECTS text on the wireframe. Minimap: no HP/POS/YAW/AMMO text (only current area label).
6. **Verbose telemetry (full list)** — stair_climb_state, swim_edge_state, advisor_last_thought, last_replan_steps (deque[3]), tick_rate_fps, frame_lag_ms, proactive_halts, visual_pin_hits, nav_current_step_area.
7. **HUD schema extensions** — all new fields are optional keyword arguments to `build_hud_payload` with safe defaults. Existing tests that pass no new kwargs keep working.
8. **Tick rate** — 10 FPS (`pygame.Clock().tick(10)`), matching Phase 10. No caching between ticks — cheap enough to rebuild every frame.
9. **Interactivity** — READ-ONLY observability. No pause/resume/skip/click. Reverse control channel deferred.
10. **Tests** — headless (`SDL_VIDEODRIVER=dummy`), region spot-checks not golden images, ~15 new tests across panel isolation + app smoke.
11. **Reuse only** — `WireframeRoomRenderer`, `AASDepthBackend`, `RoomConfig`, `projection.py`, `effects.py`, `hud.py` all stay.
12. **Wireframe panel** — `draw_room_frame=False`, `extra_hud=None` (no numeric overlay), AAS loaded once at startup.

### Claude's Discretion

- Exact font sizes/padding/colors (TRON/CRT aesthetic).
- Whether `hud.py` needs `decoration_only=True` kwarg or a new `render_hud_decoration()` function.
- Whether verbose rows with `None` data render blank or hide.
- Status bar at bottom: one line or two.
- Minimap area outlines: from AAS vs from learned map.
- How `last_replan_steps` is captured (callback hook vs log parse).
- Whether `open_perception.py` takes `--aas` or auto-detects from HUD state's `map` field.

### Deferred Ideas (OUT OF SCOPE)

- Interactive controls (pause/resume/skip/click-to-move/yaw override).
- Bidirectional HUD → bot command channel.
- See-through wall occlusion fix.
- Hailo NPU detection overlay in wireframe.
- A* path visualization inside wireframe panel (stays in minimap).
- Configurable / user-resizable layout, fullscreen, window resize.
- Remote/web HUD, multi-bot fleet view, TTS.

---

## Phase Requirements

CONTEXT.md does not assign formal REQ-IDs for Phase 12. Mapping user-stated requirements from CONTEXT.md `<specifics>` to research findings:

| Req (paraphrased) | Research Support |
|---|---|
| Single unified 1400×700 three-panel view | Question 5 (sub-surface pattern) + Question 6 (BGR→pygame) |
| Standalone app | `strategic_hud.py` precedent + `demo_wireframe_room._PygameDisplay` |
| Verbose bot status details | State sources audit (Question 4) — all 9 sources confirmed with exact attribute names |
| Single instance per metric | Question 13 (hud.py decoration-only mode) + dedup contract |
| Name "Open-Perception" | File path locked: `open_perception.py` at root |

---

## Standard Stack

No new dependencies. Everything is already installed and verified from Phase 10 + 11:

| Library | Current pin | Used for | Verification |
|---|---|---|---|
| pygame | >=2.5 (project convention, used by strategic_hud.py and demo_wireframe_room._PygameDisplay) | Window, sub-surfaces, font rendering, BGR→RGB blit | Used in production in both legacy files [VERIFIED: source] |
| numpy | >=1.26 | Frame arrays | [VERIFIED: CLAUDE.md stack] |
| opencv-python-headless | >=4.8 | Upstream renderer output is BGR ndarray — converted via slice `frame[:, :, ::-1]` | [VERIFIED: `demo_wireframe_room.py:136`] |
| pytest + SDL_VIDEODRIVER=dummy | existing | Headless tests | [VERIFIED: `tests/test_hud_schema.py:227`] |

**Nothing to install.** Plan should NOT add entries to `pyproject.toml`.

---

## Architecture Patterns

### Recommended File Layout

```
openarena-perception/
├── open_perception.py                        # NEW — the app (~200 LOC)
├── openarena_perception/
│   ├── hud_schema.py                         # EXTEND — add 7 new optional kwargs
│   └── visualization/
│       ├── panels/                           # NEW subpackage
│       │   ├── __init__.py                   # exports MinimapPanel, WireframePanel, StatsPanel
│       │   ├── minimap.py                    # ~200 LOC — extracted from strategic_hud
│       │   ├── wireframe.py                  # ~120 LOC — thin wrapper + BGR→pygame
│       │   └── stats.py                      # ~250 LOC — right panel, verbose rows
│       ├── hud.py                            # MAYBE EXTEND — decoration_only mode
│       ├── wireframe_room.py                 # unchanged
│       ├── aas_backend.py                    # unchanged
│       ├── config.py                         # unchanged
│       ├── projection.py                     # unchanged
│       └── effects.py                        # unchanged
├── strategic_hud.py                          # DELETE at end of phase
├── openarena_perception/visualization/demo_wireframe_room.py  # DELETE at end of phase
├── item_tour.py                              # EXTEND — fill 7 new HUD fields + replan hook
└── tests/
    ├── test_hud_schema.py                    # MODIFY — rewrite test_contract_build_payload_to_strategic_hud_load
    ├── test_open_perception.py               # NEW — app smoke test
    ├── test_panels_minimap.py                # NEW — sub-surface render spot-check
    ├── test_panels_wireframe.py              # NEW — BGR→pygame conversion test
    └── test_panels_stats.py                  # NEW — verbose row rendering
```

### Pattern: pygame Sub-Surface Composition

pygame supports `Surface.subsurface(rect)` which returns a view into the parent surface — writes to the sub-surface appear in the parent, and coordinates in the sub-surface are (0,0)-relative to its top-left. This is the clean way to hand each panel its own "canvas":

```python
# open_perception.py main loop sketch
screen = pygame.display.set_mode((1400, 700))

minimap_rect   = pygame.Rect(  0, 0, 400, 700)
wireframe_rect = pygame.Rect(400, 0, 600, 700)
stats_rect     = pygame.Rect(1000, 0, 400, 700)

minimap_surf   = screen.subsurface(minimap_rect)
wireframe_surf = screen.subsurface(wireframe_rect)
stats_surf     = screen.subsurface(stats_rect)

while running:
    state.load()                                  # read ./tmp/oa_hud_state.json
    minimap_panel.draw(state, minimap_surf)       # draws into (0,0..400,700)
    wireframe_panel.draw(state, wireframe_surf)   # draws into (0,0..600,700)
    stats_panel.draw(state, stats_surf)           # draws into (0,0..400,700)
    # Separators drawn on the PARENT, not a sub-surface
    pygame.draw.line(screen, GRID, (400, 0), (400, 700), 2)
    pygame.draw.line(screen, GRID, (1000, 0), (1000, 700), 2)
    pygame.display.flip()
    clock.tick(10)
```

**Gotchas** (verified against pygame docs & Phase 11 `_PygameDisplay`):
- Sub-surfaces share pixel memory with the parent — NO extra copy cost.
- A sub-surface is locked while the parent is locked. Don't hold references across `set_mode` calls (the parent is replaced).
- Clipping is automatic — drawing outside the sub-surface rect is silently clipped.
- `subsurface()` raises `ValueError` if the rect is outside the parent. Guard rails: hardcode the three rects to known-safe values (we do — 400/600/400 = 1400).
- `pygame.draw.line` on the PARENT surface needs absolute coords; on a sub-surface, use sub-relative coords. Don't mix — it's a very easy bug. **Pattern:** separators draw on the parent; all panel content uses sub-relative coords.

### Pattern: BGR → pygame Surface (Phase 11 validated)

`WireframeRoomRenderer.render(...)` returns an `(H, W, 3) uint8` BGR numpy array. To blit into a pygame surface:

```python
# Source: demo_wireframe_room.py:135-139 [VERIFIED]
rgb = bgr_frame[:, :, ::-1]                           # BGR -> RGB view (no copy)
surface = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))  # (W,H,3) order
sub_surface.blit(surface, (0, 0))
```

**Key gotcha:** `pygame.surfarray.make_surface` expects `(W, H, 3)`, NOT `(H, W, 3)`. The `.swapaxes(0, 1)` is mandatory. This is already proven at 960×600 in Phase 11; it will scale fine to 600×700.

**Performance note:** `make_surface` copies the pixel data internally. On Pi 5 at 600×700 = 420K pixels × 3 bytes ≈ 1.3 MB, this is sub-millisecond. Not a bottleneck.

### Pattern: World → Minimap Projection (extract verbatim from strategic_hud)

`strategic_hud.StrategicHUD.world_to_minimap()` lines 275–288 is the canonical Q3-to-pygame projection. Copy into `MinimapPanel` and re-anchor to the sub-surface (0,0):

```python
def world_to_minimap(self, wx: float, wy: float) -> tuple[int, int]:
    """Convert Q3 world coords to minimap pixel coords.
    Q3 world: +X=east, +Y=north. Pygame: +X=right, +Y=down.
    Sub-surface relative (0,0 = top-left of the 400x700 panel)."""
    rx = (wx - self.map_min_x) / max(self.map_max_x - self.map_min_x, 1)
    ry = (wy - self.map_min_y) / max(self.map_max_y - self.map_min_y, 1)
    margin_x = 20                                          # was MINIMAP_MARGIN=100 in strategic_hud
    margin_y = 50
    mx = margin_x + int(rx * MINIMAP_SIZE)
    my = margin_y + MINIMAP_SIZE - int(ry * MINIMAP_SIZE)  # invert Y
    return (mx, my)
```

The yaw-arrow math (strategic_hud lines 405–409) is also verbatim:
```python
# Source: strategic_hud.py:405-409 [VERIFIED]
rad = math.radians(s.player_yaw)
ax = px + int(math.cos(rad) * 15)
ay = py - int(math.sin(rad) * 15)  # Y-inverted for pygame
```

This matches `navigator.py:292` canonical `atan2(dy, dx)` convention. Do NOT reinvent.

### Anti-Patterns to Avoid

- **Don't cache WireframeRoomRenderer output frames across ticks.** The bot moves every tick; stale frames defeat the purpose of the live view. Phase 11 already confirmed ~25–40 ms at 960×600; 600×700 scales linearly to ~10–20 ms on Pi 5. Budget fits at 10 FPS.
- **Don't hold per-panel `pygame.Font` handles at module level.** Create in `__init__` after `pygame.init()`. `strategic_hud.py` does this correctly.
- **Don't mix cv2 text rendering with pygame text.** The wireframe panel uses cv2 internally (it's a numpy array) — that's fine inside the wireframe pipeline. The right/left panels use pygame font exclusively. No cross-contamination.
- **Don't import `strategic_hud` or `demo_wireframe_room` from the new code.** They're going away. Extract the code you need.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Minimap projection | New world-to-screen math | Copy `strategic_hud.world_to_minimap` lines 275–288 | Already validated against navigator.py Q3 yaw convention |
| BGR→pygame blit | cv2.imshow, numpy reshape guesswork | Copy `_PygameDisplay.show` lines 126–141 | Handles stride + axes swap correctly |
| HUD state file read | Re-parse JSON from scratch | Extend existing `HUDState.load()` lines 153–235 | Already tolerates missing keys, races, malformed files |
| Intent panel layout (macro/sub/duration/pause flash/history/problems/path bar) | Re-design the layout | Copy `_draw_intent_panel` lines 520–658 verbatim | 138 lines of tuned layout; the only edits are the y-offset origin and adding verbose rows |
| Atomic state write | re-implement tmp+rename | Use `hud_schema.write_hud_state` | Already exists, already tested |
| Yaw-arrow math | cos/sin/atan2 rederivation | Copy `strategic_hud.py:405-409` | See Phase 11 Pitfall 1 — easy to get wrong |

---

## State Source Audit (Question 4)

Every verbose telemetry source verified against actual source code:

| Field | Source path | Exists? | Notes |
|---|---|---|---|
| `stair_climb_state` | `navigator.is_climbing_stairs` (property @ `navigator.py:95-103`) | ✅ [VERIFIED] | Returns `bool`. Backed by `self._stair_climb_active` attribute set by `follow_path`. **The `_stair_target_area` attribute referenced in CONTEXT.md does NOT exist as a stand-alone attribute** — only `_stair_climb_active` (bool) and the current `self._path[0]` (the target area during a climb). **Derivation:** when `is_climbing_stairs` is True, the target area is `navigator._path[0]`. |
| `swim_edge_state` | `navigator.py:198` logs `"Traversing swim edge to area %d (may take damage!)"` via `log.warning` | ⚠️ [VERIFIED but needs hook] | There is NO programmatic callback. Only a log line. **Two options:** (A) Add a new instance attribute `self._last_swim_edge_area: Optional[int] = None` set inside `follow_path` when the swim branch runs — cheap, clean, one line. (B) Install a `logging.Handler` in item_tour that scrapes the message. **Option A is strongly recommended.** |
| `advisor_last_thought` | `advisor.current_narrative()` @ `advisor.py:420-421` | ✅ [VERIFIED] | Returns `str` (the `_narrative` instance attribute). Truncated to 200 chars at set time. Fine to truncate to 80 for display. |
| `last_replan_steps` | Not currently tracked. The log line `"Re-planned path from area %d: %d -> %d steps"` at `navigator.py:183-184` is the only signal. | ⚠️ [VERIFIED but needs wiring] | **Recommended approach:** Add an optional `on_replan: Optional[Callable[[int, int, int], None]]` hook to Navigator, set from item_tour to append to a `deque(maxlen=3)`. Matches existing pattern — Navigator already has `_on_area_transition` callback for area-entry events (`navigator.py:86`). One-line addition in Navigator, 5 lines in item_tour. |
| `tick_rate_fps` | `PerceptionLoop.avg_fps` property @ `loop.py:227-232` | ✅ [VERIFIED] | Already exists. Computes `1/(mean of last 200 tick durations)`. Just needs exposure — `item_tour._export_hud` has access to the loop via `self.agent`. |
| `frame_lag_ms` | `PerceptionLoop._tick_times[-1]` — instance attribute @ `loop.py:83` | ✅ [VERIFIED] | Last entry is the most recent tick duration in seconds. Multiply by 1000 at export time. Expose via a new tiny property `last_tick_ms` to avoid leaking the private list. |
| `proactive_halts` | `item_tour._proactive_halts` @ `item_tour.py:319` | ✅ [VERIFIED] | Already written to HUD extras @ `item_tour.py:1313`. Just needs to be surfaced by the new stats panel. |
| `visual_pin_hits` | `item_tour._visual_pin_hits` @ `item_tour.py:340` | ✅ [VERIFIED] | Already in extras @ `item_tour.py:1314`. |
| `nav_current_step_area` | `navigator._path[0]` when path is not empty | ✅ [VERIFIED] | `_path` is `List[int]` of area indices. `_path[0]` is the current step target. Add a public property `current_step_area: Optional[int]` for cleanliness. |

**Key finding re: item_tour and advisor:** `item_tour.py` does NOT currently import or call `advisor.current_narrative()` (grepped — zero matches). The existing export passes `advisor.stats()` only. This phase needs one new line in `_export_hud` to call `self.advisor.current_narrative()` and include it.

**Key finding re: item_tour and replans:** The current code has NO replan tracking on the item_tour side. The navigator logs but doesn't expose. We must add both the navigator hook and the item_tour `deque(maxlen=3)`.

---

## HUD Schema Extension Pattern (Question 3)

`build_hud_payload` currently takes `sa`, `gs`, `map_name`, `brain_state`, `nav`, `learned_map`, `context`, `is_paused_for_assess`, `threat_flag`, `extras`. The new fields fit cleanly into the existing pattern by adding keyword arguments with `None` defaults:

```python
# hud_schema.py extension sketch [PROPOSED]
def build_hud_payload(
    *,
    sa=None, gs=None, map_name="", brain_state=None,
    nav=None, learned_map=None, context=None,
    is_paused_for_assess=False, threat_flag=False,
    # --- Phase 12 additions ---
    stair_climb_state: Optional[str] = None,
    swim_edge_state: Optional[str] = None,
    advisor_last_thought: Optional[str] = None,
    last_replan_steps: Optional[list[int]] = None,
    tick_rate_fps: Optional[float] = None,
    frame_lag_ms: Optional[float] = None,
    nav_current_step_area: Optional[int] = None,
    extras: Mapping[str, Any] | None = None,
) -> dict:
    ...
    if stair_climb_state is not None:
        payload["stair_climb_state"] = stair_climb_state
    if swim_edge_state is not None:
        payload["swim_edge_state"] = swim_edge_state
    if advisor_last_thought is not None:
        payload["advisor_last_thought"] = advisor_last_thought
    if last_replan_steps is not None:
        payload["last_replan_steps"] = list(last_replan_steps)  # deque->list, Pitfall 7
    if tick_rate_fps is not None:
        payload["tick_rate_fps"] = float(tick_rate_fps)
    if frame_lag_ms is not None:
        payload["frame_lag_ms"] = float(frame_lag_ms)
    if nav_current_step_area is not None:
        payload["nav_current_step_area"] = int(nav_current_step_area)
    ...
```

**Backward-compat contract:** only emit keys when non-None — existing tests that call `build_hud_payload(map_name="q3dm1")` produce the same output (no new keys). Verified against `tests/test_hud_schema.py:203-208 test_build_payload_no_context_still_emits_pause_flags` — the test asserts key presence, not absence.

The ONE test that will break is `test_contract_build_payload_to_strategic_hud_load` @ line 214, because it imports `strategic_hud`. **Rewrite it to instantiate `open_perception.HUDState` instead** (the new app will expose the same class).

---

## Wireframe Panel Embedding (Question 6 + 7)

Minimal wrapper class:

```python
# openarena_perception/visualization/panels/wireframe.py [PROPOSED]
import pygame
from dataclasses import replace
from openarena_perception.visualization import (
    AASDepthBackend, RoomConfig, WireframeRoomRenderer,
)
from openarena_perception.navigation.aas_parser import parse_aas

class WireframePanel:
    def __init__(self, aas_path: str, width: int = 600, height: int = 700):
        graph = parse_aas(aas_path)
        if graph is None:
            raise RuntimeError(f"Failed to parse AAS: {aas_path}")
        cfg = replace(
            RoomConfig(),
            width=width, height=height,
            fov_deg=90.0,
            camera_height=26.0,
            hud=True,  # keep decoration chrome — brackets/crosshair/status bar
            glow=True,
        )
        self._backend = AASDepthBackend(graph, camera_height=cfg.camera_height)
        self._renderer = WireframeRoomRenderer(cfg)
        self._cfg = cfg
        self._frame_idx = 0

    def draw(self, state, surface: pygame.Surface) -> None:
        pos = (state.player_x, state.player_y, state.player_z)
        yaw = state.player_yaw
        scene = self._backend.build_scene(pos, yaw, max_distance=384.0, max_areas=20)
        frame = self._renderer.render(
            pos, yaw, scene,
            extra_hud=None,   # <<< KEY: no numeric overlays per dedup contract
            state={"frame": self._frame_idx,
                   "src_width": self._cfg.width,
                   "src_height": self._cfg.height,
                   "status_text": "// PERCEPTION ACTIVE"},
            draw_room_frame=False,
        )
        # BGR -> RGB -> pygame surface
        rgb = frame[:, :, ::-1]
        pg_frame = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
        surface.blit(pg_frame, (0, 0))
        self._frame_idx += 1
```

**AAS loading decision (Claude's discretion):** Use `--aas` CLI flag with auto-detect fallback. Default to `maps/oa_dm1.aas`. If `--aas` not given, try to read `state.map_name` from the HUD state file and look for `maps/{map_name}.aas`; if that fails, fall back to `maps/oa_dm1.aas`. This preserves the Phase 11 demo precedent (`--aas` default of `maps/oa_dm1.aas`) while supporting multi-map sessions.

**Note on `hud=True` + `extra_hud=None`:** `render_hud()` @ `hud.py:61-130` draws FRAME/ROOM/FOV/MODE/OBJECTS text UNCONDITIONALLY when `cfg.hud=True`, regardless of whether `extra_hud` is provided. This violates the dedup contract. See Question 13 for the fix.

---

## Question 13: hud.py Decoration-Only Mode

**Current behavior** (`hud.py:61-130`): when `cfg.hud=True`, renders:
1. `FRAME NNNNNN` top-left text ← **must go**
2. `ROOM WxHxD` ← **must go**
3. `FOV N GRID XxYxZ` ← **must go**
4. `MODE: XXX` ← **must go**
5. `OBJECTS: N` ← **must go**
6. Optional `extra_hud` dict rows ← already suppressed by passing `extra_hud=None`
7. Crosshair ← **keep**
8. Bottom-left `// SPATIAL GRID ACTIVE` status bar ← **keep (replace text)**
9. Bottom-right `SRC WxH` ← **keep**
10. Corner brackets ← **keep**

**Recommended fix (minimal invasive change):** Add a `decoration_only: bool = False` parameter to `render_hud`. When True, skip steps 1–6 entirely and only draw steps 7–10. This is ~4 lines of diff and preserves existing behavior. Plumb the flag through `WireframeRoomRenderer.render(..., decoration_only=False)` so the panel can pass it through.

Alternative rejected: A new `render_hud_decoration()` function duplicates 40% of the code. A config flag on `RoomConfig` couples the policy to the config singleton in a way that prevents per-call overrides. The kwarg is cleanest.

```python
# hud.py change [PROPOSED — ~4 LOC]
def render_hud(frame, cfg, state=None, extra_hud=None, decoration_only=False):
    if not cfg.hud:
        return frame
    state = state or {}
    h, w = frame.shape[:2]

    if not decoration_only:
        # [existing lines 73-111: FRAME/ROOM/FOV/MODE/OBJECTS/extra_hud text]
        ...

    _draw_crosshair(frame, cfg)
    # bottom-left status bar, bottom-right SRC, corner brackets (existing)
    ...
    return frame
```

Then `WireframeRoomRenderer.render` accepts and forwards `decoration_only`. One line added to the renderer signature, one call site in `panels/wireframe.py`.

---

## Color Scheme (Question 12)

Unify around the Phase 10 palette plus Phase 11 wireframe accents. The strategic_hud.py constants lines 52–82 are the canonical TRON/CRT palette:

| Purpose | BGR (cv2) | RGB (pygame) | Source |
|---|---|---|---|
| Background | (20, 20, 30) | (20, 20, 30) | strategic_hud.py:52 `BG` |
| Grid / separators | (40, 40, 55) | (40, 40, 55) | strategic_hud.py:53 `GRID` |
| Player | — | (0, 255, 100) | strategic_hud.py:54 `PLAYER` (matches `RoomConfig.accent_color`) |
| Intent current (yellow) | — | (255, 255, 0) | strategic_hud.py:72 `INTENT_CURRENT` |
| Intent history dim | — | (110, 110, 120) | strategic_hud.py:74 `INTENT_HISTORY` |
| Wall halt / ALERT | — | (255, 80, 80) | strategic_hud.py:68 `ALERT_COLOR` |
| OK / threat-clear | — | (80, 255, 80) | strategic_hud.py:69 `OK_COLOR` |
| Pause flash border | — | (80, 150, 255) | strategic_hud.py:81 `PAUSE_BORDER` |
| Wireframe grid color | (180, 180, 180) BGR | — | RoomConfig.grid_color |
| Wireframe accent | (0, 255, 100) BGR | — | RoomConfig.accent_color |

**Critical color gotcha:** pygame uses RGB tuples; cv2/RoomConfig uses BGR. The Phase 11 CLAUDE.md and RoomConfig comment (`# Palette (BGR order — see Pitfall 5)`) both flag this. When `strategic_hud.py` and `RoomConfig` both list `(0, 255, 100)` for "green accent", they're lucky — green is symmetric. But (20, 20, 30) BG is also symmetric. Still: document the palette once in `panels/__init__.py` with explicit `RGB_` prefix and use that throughout. Don't cross-import from `RoomConfig` for pygame drawing.

---

## Pi Performance Budget (Question 11)

Target: 10 FPS = 100 ms per tick. Back-of-envelope:

| Stage | Expected ms | Evidence |
|---|---|---|
| HUD state file read (JSON ~10 KB) | <1 | Phase 10 profiling; `.get()` tolerant parse |
| Minimap draw (cells + walls + route + player) | 3–5 | Phase 10 HUD at 10 FPS on Pi with similar content, no reports of frame drops |
| Wireframe panel build_scene + render @ 600×700 | 15–25 | Phase 11 measured 25–40 ms @ 960×600 on Pi 5 (`11-03-SUMMARY.md`), scales ~linearly with pixel count; 600×700 is ~73% of 960×600 |
| BGR→pygame surface conversion | <2 | `make_surface` on ~1.3 MB |
| Stats panel (pygame text rendering ~30 strings) | 3–5 | pygame font.render is ~0.1 ms per string with sysfont monospace |
| Separators + flip | <2 | — |
| **Total estimated** | **25–40 ms** | **comfortably under 100 ms budget** |

**Headroom for 10 FPS:** ~60 ms. No caching needed.

**Assumption flag:** Phase 11 timing was measured with `--profile` mode. The Pi 5 measurements I cite come from `11-03-SUMMARY.md`. [ASSUMED] scaling is linear with pixel count — not strictly true for glow blur (kernel-size dependent) but close enough. If the executor observes frame drops, disable `glow` in the wireframe panel config (save ~5 ms).

---

## Common Pitfalls

### Pitfall 1: Mixing Sub-Surface and Parent Coordinates
**What goes wrong:** Drawing a separator line at `(400, 0)` on the minimap sub-surface instead of the parent screen, or trying to blit the wireframe at `(400, 0)` on the parent instead of `(0, 0)` on the sub-surface.
**Prevention:** Single rule — separators on parent (absolute coords), panel content on sub-surface (relative coords). Enforce in code review.

### Pitfall 2: Silently Wrong BGR/RGB Colors
**What goes wrong:** Importing a color constant from `RoomConfig` (BGR) and using it in `pygame.draw.circle` (RGB). A color like `(180, 180, 180)` (gray) is symmetric and the bug stays hidden until someone uses orange or teal.
**Prevention:** All pygame colors defined as module-level `RGB_*` constants in `panels/__init__.py`. Never import from `RoomConfig` into the panel classes.

### Pitfall 3: Pygame Font Cache After Window Close
**What goes wrong:** Creating `pygame.font.SysFont` once at module import, then the font handle becomes invalid after `pygame.quit()`. A test that reinitializes pygame (e.g., two tests in sequence) crashes on the second one.
**Prevention:** Fonts created in `Panel.__init__` and freed in `Panel.close()`. Each test creates a fresh panel instance.

### Pitfall 4: `subsurface()` ValueError on Resize
**What goes wrong:** Pygame raises `ValueError` if a sub-surface's rect extends outside the parent. If someone changes HUD_WIDTH to 1200 but leaves the panel rects at 400+600+400=1400, the stats panel crashes at subsurface creation.
**Prevention:** Layout constants (`PANEL_MINIMAP_W=400`, `PANEL_WIREFRAME_W=600`, `PANEL_STATS_W=400`, `HUD_WIDTH=PANEL_MINIMAP_W+PANEL_WIREFRAME_W+PANEL_STATS_W`) derived not hardcoded twice.

### Pitfall 5: `extra_hud=None` Doesn't Suppress All Numeric Text
**What goes wrong:** Setting `extra_hud=None` only removes the optional MODE/HP/AMMO/POS/YAW rows added by the caller. It does NOT remove the hardcoded FRAME/ROOM/FOV/MODE/OBJECTS block that `render_hud` draws unconditionally (`hud.py:78-102`). The wireframe panel still shows those unless `decoration_only=True` is plumbed through.
**Prevention:** Question 13 fix — add the `decoration_only` kwarg. Without it, the dedup contract is silently broken.

### Pitfall 6: Missing Test Import Update
**What goes wrong:** `tests/test_hud_schema.py:233 import strategic_hud` breaks at collection time when the file is deleted. The whole test session red-balls.
**Prevention:** Delete files AFTER rewriting the test. Task order matters — add `test_open_perception.py` and update `test_hud_schema.py` BEFORE `rm strategic_hud.py`. See Legacy Deletion Checklist below.

### Pitfall 7: Log-Based Replan Tracking Swallows Events
**What goes wrong:** If the planner picks the "install a `logging.Handler` to scrape messages" approach, and another test suite reconfigures logging mid-run (e.g., `caplog` fixture), the handler is detached and replan events are lost silently.
**Prevention:** Use the callback-hook approach (Option A in Question 4 source audit) — direct function pointer, not logging-dependent.

### Pitfall 8: Swim Edge "Traversal" Fires Every Tick
**What goes wrong:** If `navigator.follow_path` is in a swim area, the `log.warning` at line 198 fires every single tick. A state attribute `_last_swim_edge_area` naively set to `target_area` would mean `swim_edge_state` is "permanently traversing" and never clears.
**Prevention:** Track (area_id, timestamp) and clear after 2 seconds of no new swim event. Or: set the attribute only on the TRANSITION into a swim area, not every tick.

### Pitfall 9: State File Stale Between App Start and Bot Start
**What goes wrong:** User launches `open_perception.py` before `item_tour.py`. The state file doesn't exist → `HUDState.load` silently returns with defaults → minimap shows (0,0) and wireframe panel builds scene from origin (which may be inside AAS area 0, the dummy area). Confusing.
**Prevention:** `HUDState` already tolerates missing files (strategic_hud.py:233 bare `except Exception: pass`). Add a "WAITING FOR BOT" status bar when `state_file` doesn't exist yet.

### Pitfall 10: Map Bounds Auto-Detect Flicker on Load
**What goes wrong:** `strategic_hud.HUDState.load` lines 217–231 recomputes `map_min_x/max_x/min_y/max_y` from current-frame items and route. Between ticks, the minimap scale jitters. On the old narrow HUD this was tolerable; on a 400px-wide panel it's noticeable.
**Prevention:** Compute bounds once at first load and latch. Or: use AAS area bounding boxes as the canonical extent (requires pulling from `graph.areas[*].mins/maxs`).

---

## Code Examples

### Existing code to extract: Minimap draw (strategic_hud.py:290–410)

The entire `StrategicHUD.draw()` method up to line 410 (before the "Info panel below minimap" block at line 412) is the minimap code. Lines to copy:
- 291–310: BG + rect + grid lines
- 312–333: Learned map occupancy cells
- 335–344: Learned map wall segments
- 346–351: Surveyed rooms
- 352–368: Items on map
- 370–394: Route waypoints + connecting lines
- 396–400: Player trail
- 402–409: Player position + yaw arrow

**Lines to NOT copy** (they move to stats panel):
- 411–513: Info panel below minimap (disposition/HP/armor/weapon/objective/status/brain/stats/tracked objects)
- 515–516: Right-side intent panel call

### Existing code to extract: Intent panel (strategic_hud.py:520–658)

The entire `_draw_intent_panel` method is the basis for `panels/stats.py`. Keep the structure, but:
- Remove `x_offset` math — use sub-surface (0, 0)
- Extend after "PATH" block with 9 verbose rows (stair_climb / swim_edge / advisor / last_replans / tick_rate / frame_lag / halts / vpin / nav_step)
- Add a "VITAL STATS" block ABOVE "INTENT" (HP/AR/ammo/weapon/pos/yaw) — extracted from lines 415–442 of the info-panel code

### Existing code to extract: Live state poll (demo_wireframe_room.py:161–207)

`_read_live_state` and `_extract_pose_from_state` functions move into `open_perception.py` main loop. They already tolerate races and malformed files.

---

## State of the Art

| Old Approach | New Approach | Impact |
|---|---|---|
| Two separate windows (strategic_hud.py + demo_wireframe_room.py --live --show-pygame) | Single unified 1400×700 window | User gets one screen; dedup of state reads |
| Each app reads the state file independently | One `HUDState.load()` per tick in open_perception.py | Half the file reads |
| Wireframe shows FRAME/MODE/HP/POS overlay text | Decoration-only (brackets/crosshair) | Dedup contract — stats live in right panel |
| No verbose telemetry (stair climb, swim edge, replans) | Right panel surfaces 9 new verbose rows | Better debugging of nav failures |

---

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|---|---|---|
| A1 | `PerceptionLoop.avg_fps` property exists and is accurate | State Source Audit | LOW — verified @ `loop.py:227-232`, just cite it |
| A2 | Pi 5 wireframe render scales ~linearly with pixel count (600×700 ≈ 0.73× of 960×600 timing) | Performance Budget | LOW — glow kernel adds nonlinearity; mitigation: disable glow if budget exceeded |
| A3 | `_stair_target_area` attribute CONTEXT.md refers to does NOT exist — only `_stair_climb_active` bool exists | State Source Audit | MEDIUM — plan must derive target area from `_path[0]` at export time rather than expect an existing attribute. Without this catch, wiring code would raise `AttributeError`. |
| A4 | `item_tour.py` does NOT currently call `advisor.current_narrative()` — new integration point | State Source Audit | LOW — grepped, no matches; confirmed new code |
| A5 | Pygame sub-surface drawing is O(1) setup (pixel memory shared with parent) | Architecture Patterns | LOW — documented pygame behavior |
| A6 | TRON palette from strategic_hud.py lines 52–82 is the canonical aesthetic | Color Scheme | LOW — user approved the Phase 10 look and specifically asked to "consolidate" not "redesign" |
| A7 | Deleting `demo_wireframe_room.py` breaks zero tests | Test Migration | LOW — grep returned zero test matches |
| A8 | The log line `"Re-planned path from area %d: %d -> %d steps"` is the only replan signal | State Source Audit | MEDIUM — verified via grep but might be other code paths in navigator that replan without logging; planner should audit for additional `self._path = ...` assignments before committing to the hook point |
| A9 | `hud.py` `decoration_only` flag approach is cleaner than a new function | Question 13 | LOW — 4 LOC diff, easy to revisit if the `if not decoration_only` block gets ugly |
| A10 | Budgeted stats panel text rendering at 3–5 ms for ~30 strings is realistic on Pi | Performance Budget | LOW — pygame font render is well-characterized; if wrong, caching rendered text surfaces between ticks is a trivial fix |

**None of the assumptions block planning.** A3 and A8 are the two MEDIUM items that need verification during implementation (not before planning).

---

## Open Questions

1. **`--aas` CLI flag vs auto-detect from state.map_name**
   - Recommendation: Support both. Default to auto-detect with `maps/oa_dm1.aas` fallback, allow `--aas PATH` override.
   - Rationale: User may run on different maps across sessions; hardcoding is annoying, requiring the flag every time is annoying.

2. **Should `test_contract_build_payload_to_strategic_hud_load` be deleted or rewritten?**
   - Recommendation: **Rewrite** to target a new `open_perception.HUDState` class. The contract (build_hud_payload output is parseable by the HUD reader) is valuable — don't lose it. ~5 line edit: change import path and class name.

3. **Should the verbose rows with `None` data render blank or hide?**
   - Recommendation: Render as dimmed placeholders (`"stair_climb: ----"`) so the layout doesn't shift tick-to-tick. Layout stability > information density at 10 FPS.

4. **AAS area outlines in minimap — AAS source or learned map?**
   - Recommendation: Defer — use learned map only for this phase (already working in Phase 10). Adding AAS area outline rendering is new code for a minor visual improvement; belongs in a future polish phase.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| pygame | panels, app | ✓ | installed (used by strategic_hud.py & demo_wireframe_room._PygameDisplay) | — |
| numpy | wireframe | ✓ | >=1.26 | — |
| opencv-python-headless | wireframe | ✓ | >=4.8 | — |
| maps/oa_dm1.aas | wireframe AAS backend | ✓ | present (also oa_dm2.aas, oa_rpg3dm2.aas) | — |
| SDL_VIDEODRIVER=dummy | tests | ✓ | stdlib env var | — |

**Nothing blocking.**

---

## Validation Architecture

### Test Framework
| Property | Value |
|---|---|
| Framework | pytest >=8.0, pytest-asyncio >=0.24 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (inherit from project) |
| Quick run command | `SDL_VIDEODRIVER=dummy uv run pytest tests/test_open_perception.py tests/test_panels_*.py -x` |
| Full suite command | `SDL_VIDEODRIVER=dummy uv run pytest` |

### Phase Requirements → Test Map

| Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|
| 1400×700 window opens, three sub-surfaces constructable | unit | `pytest tests/test_open_perception.py::test_app_init -x` | ❌ Wave 0 |
| `HUDState` reads the extended payload with all 7 new fields | unit | `pytest tests/test_hud_schema.py::test_verbose_fields_roundtrip -x` | ❌ Wave 0 (extend existing file) |
| `build_hud_payload` omits new keys when kwargs not passed (backward compat) | unit | `pytest tests/test_hud_schema.py::test_build_payload_no_context_still_emits_pause_flags` | ✅ exists, re-verify |
| Minimap panel draws non-bg pixels in expected regions (player marker, waypoints) | unit | `pytest tests/test_panels_minimap.py -x` | ❌ Wave 0 |
| Wireframe panel converts BGR array to pygame surface and blits without error | unit | `pytest tests/test_panels_wireframe.py::test_bgr_to_pygame -x` | ❌ Wave 0 |
| Wireframe panel passes `decoration_only=True`, no FRAME/MODE/OBJECTS text visible | unit (pixel region check) | `pytest tests/test_panels_wireframe.py::test_no_numeric_overlay -x` | ❌ Wave 0 |
| Stats panel renders verbose rows when all 7 new fields populated | unit | `pytest tests/test_panels_stats.py::test_verbose_rows_populated -x` | ❌ Wave 0 |
| Stats panel renders placeholder rows when verbose fields are None | unit | `pytest tests/test_panels_stats.py::test_verbose_rows_none_placeholder -x` | ❌ Wave 0 |
| `navigator` replan hook fires on `_astar` re-plan in `follow_path` | unit | `pytest tests/test_navigation.py::test_replan_hook -x` | ❌ Wave 0 (extend existing file) |
| `navigator._last_swim_edge_area` is set when follow_path traverses a swim edge | unit | `pytest tests/test_navigation.py::test_swim_edge_state_exposed -x` | ❌ Wave 0 |
| `hud.py` decoration_only mode skips FRAME/ROOM/FOV/MODE/OBJECTS text | unit (pixel region) | `pytest tests/test_wireframe_hud.py::test_decoration_only_suppresses_numeric_text` | ❌ Wave 0 (likely new file) |
| One-tick smoke test of `open_perception.main()` with a synthetic state file | integration | `pytest tests/test_open_perception.py::test_one_tick_smoke -x` | ❌ Wave 0 |
| Legacy deletion: `strategic_hud.py` gone, no test imports it | meta | `pytest tests/test_hud_schema.py::test_contract_build_payload_to_open_perception_load` | ⚠️ MODIFY existing |

### Sampling Rate
- **Per task commit:** `SDL_VIDEODRIVER=dummy uv run pytest tests/test_panels_*.py tests/test_open_perception.py tests/test_hud_schema.py -x` (~3 seconds target)
- **Per plan merge:** `SDL_VIDEODRIVER=dummy uv run pytest tests/test_panels_*.py tests/test_open_perception.py tests/test_hud_schema.py tests/test_navigation.py tests/test_wireframe_*.py -x`
- **Phase gate:** `SDL_VIDEODRIVER=dummy uv run pytest` (full suite green before `/gsd-verify-work`)

### Wave 0 Gaps
- [ ] `tests/test_open_perception.py` — new file, covers app init and one-tick smoke
- [ ] `tests/test_panels_minimap.py` — new file, sub-surface pixel spot-checks
- [ ] `tests/test_panels_wireframe.py` — new file, BGR→pygame conversion + no-overlay verification
- [ ] `tests/test_panels_stats.py` — new file, verbose row population + placeholder behavior
- [ ] `tests/test_hud_schema.py` — MODIFY: rewrite `test_contract_build_payload_to_strategic_hud_load` to import from the new `open_perception` module; add `test_verbose_fields_roundtrip`
- [ ] `tests/test_navigation.py` — EXTEND with replan-hook and swim-edge-state tests
- [ ] `tests/test_wireframe_hud.py` (maybe; or extend existing wireframe test file) — test `decoration_only` flag

Framework install: none needed (pytest + pygame + numpy already present).

---

## Security Domain

Not applicable for Phase 12. No new external inputs, no authentication surface, no network endpoints. The HUD state file is a local trusted file written by the same user running the app. Existing project patterns apply:
- `json.load` on local file — already wrapped in bare `except` in strategic_hud.py:233 (tolerates malformed/races). Defense-in-depth: the new app should use the same tolerant pattern. No arbitrary code execution path.
- No user input fields. No subprocess.
- `SDL_VIDEODRIVER=dummy` env var in tests — trusted, standard pattern.

---

## Legacy Deletion Checklist

**Files to delete (end of phase only):**
- [ ] `/home/hoyack/openarena-perception/strategic_hud.py`
- [ ] `/home/hoyack/openarena-perception/openarena_perception/visualization/demo_wireframe_room.py`

**References to update BEFORE deletion (grep verified):**

**Test files (1 file, 1 test):**
- [ ] `tests/test_hud_schema.py:214-279` — rewrite `test_contract_build_payload_to_strategic_hud_load`. Change `import strategic_hud` → `import open_perception` (or `from openarena_perception.visualization.panels import ...`). Rename test to `test_contract_build_payload_to_open_perception_load`.

**Docs (.md files) — grep matches that are historical and should NOT be edited:**
- `.planning/STATE.md:197` — historical log entry, leave as-is
- `.planning/phases/10-*/*.md` — Phase 10 history, leave as-is
- `.planning/phases/11-*/*.md` — Phase 11 history, leave as-is
- `.planning/phases/12-open-perception-ui/12-CONTEXT.md` — intentional reference, leave as-is

**Docs (.md files) — grep matches that SHOULD be edited:**
- None found. `CLAUDE.md` does NOT reference either file (grepped, zero matches).

**Shell scripts:**
- None found. Grep of `**.sh` returned zero matches.

**map_explorer.py reference:** Grep flagged `map_explorer.py` as containing `strategic_hud` or `demo_wireframe_room`. **Not yet audited** — the planner should verify whether it's a hard import or just a comment/docstring. Likely safe but check during planning.

**Python package entry points:**
- `openarena_perception/visualization/__init__.py` — verify it does NOT re-export anything from `demo_wireframe_room`. The `demo_wireframe_room` module uses `from openarena_perception.visualization import (AASDepthBackend, RoomConfig, WireframeRoomRenderer)` (line 27) — the import direction is demo→package, not package→demo. Safe.

**Order of operations for the legacy deletion task:**
1. Write the new `open_perception.py` + `panels/*.py`
2. Write the new tests (`test_open_perception.py`, `test_panels_*.py`)
3. Rewrite `test_hud_schema.py::test_contract_build_payload_to_strategic_hud_load`
4. Audit `map_explorer.py`, fix if it imports either file
5. Run full test suite, verify green
6. `rm strategic_hud.py openarena_perception/visualization/demo_wireframe_room.py`
7. Run full test suite again — must still be green
8. Commit as atomic change

---

## Sources

### Primary (HIGH confidence) — all read directly in this research session
- `strategic_hud.py` (all 699 lines) — [VERIFIED: source]
- `openarena_perception/visualization/demo_wireframe_room.py` (all 423 lines) — [VERIFIED: source]
- `openarena_perception/hud_schema.py` (all 180 lines) — [VERIFIED: source]
- `openarena_perception/visualization/hud.py` (all 131 lines) — [VERIFIED: source]
- `openarena_perception/visualization/wireframe_room.py` (lines 60–140) — [VERIFIED: source]
- `openarena_perception/visualization/config.py` (all 54 lines) — [VERIFIED: source]
- `openarena_perception/navigation/navigator.py` (lines 85–220) — [VERIFIED: source]
- `openarena_perception/loop.py` (all 237 lines) — [VERIFIED: source]
- `openarena_perception/strategy/advisor.py` (excerpts around `current_narrative`) — [VERIFIED: source]
- `item_tour.py` (lines 315–345, 1269–1325) — [VERIFIED: source]
- `tests/test_hud_schema.py` (lines 200–280) — [VERIFIED: source]

### Secondary (MEDIUM confidence)
- Phase 11 timing data from `.planning/phases/11-wireframe-perception-grid/11-03-SUMMARY.md` — historical record, no re-benchmark in this session

### Assumptions (LOW)
- Pygame sub-surface is O(1) — documented stdlib behavior, not re-verified here

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new deps, everything already in production
- Architecture / patterns: HIGH — sub-surface + BGR→pygame are both proven (Phase 11) or documented (pygame stdlib)
- Pitfalls: HIGH — 10 pitfalls directly derived from source-code inspection
- State source audit: HIGH for 7/9 sources, MEDIUM for 2 (stair target area derivation, replan hook wiring point) — flagged in assumption log

**Research date:** 2026-04-10
**Valid until:** ~2026-05-10 (30 days; stable stack, no fast-moving deps in this phase)

## RESEARCH COMPLETE
