---
phase: 13-room-perception-and-wall-reconstruction
plan: 06
subsystem: visualization
tags: [minimap, fitted-walls, room-polygons, rp-11, awaiting-human-verification]

requires:
  - phase: 13-05
    provides: LearnedMap.export_for_hud() emits fitted_walls/corners/rooms/doorways/current_room_id
provides:
  - MinimapPanel renders fitted walls (bright green), corners (amber), room polygons (blue alpha-fill + outline)
  - Current room highlight via current_room_id
  - Backward-compat fallback when fitted_walls is empty/missing (no red stubs, no crash)
affects: [live oa_dm1 verification, Phase 13 close-out]

tech-stack:
  added: []
  patterns:
    - "SRCALPHA temp surface for polygon alpha fill blitted at AABB (pygame)"
    - "Order-locked render layering: rooms below walls below corners"

key-files:
  created:
    - .planning/phases/13-room-perception-and-wall-reconstruction/13-06-SUMMARY.md
  modified:
    - openarena_perception/visualization/panels/minimap.py
    - openarena_perception/visualization/panels/__init__.py
    - tests/test_open_perception_panels.py

key-decisions:
  - "Render order locked: AAS overhead -> learned grid cells -> room polygon fills (alpha) -> room outlines -> fitted walls (2px green) -> corners (3px amber) -> surveyed rooms -> items -> trail -> waypoints -> player marker"
  - "Polygon alpha fill via SRCALPHA temp surface blitted at the polygon AABB rather than calling pygame.gfxdraw — keeps the dependency surface flat"
  - "Current room outline = 2px @ (140,200,255), fill alpha 80/255; other rooms = 1px @ (80,140,200), fill alpha 50/255"
  - "Backward compat is total: legacy state with wall_segments populated still produces ZERO red pixels because the render block was DELETED, not gated"
  - "RP-11 status: implementation complete + automated tests green; AWAITING LIVE HUMAN VERIFICATION on oa_dm1 before closing the requirement"

patterns-established:
  - "Phase 13 polygon-fill helper pattern (SRCALPHA AABB blit) is reusable for any future alpha-blended overlay on the minimap"

requirements-completed: []  # RP-11 closes only after live verification

duration: ~10min
completed: 2026-04-11
---

# Phase 13 Plan 13-06: Minimap Render — Fitted Walls Replace Red Stubs Summary

**MinimapPanel now renders Phase 13 fitted walls (bright green), corners (amber), and room polygons (blue alpha fill + outline) in a locked render order; the legacy red `(255,60,60)` wall_segment stub block is deleted; backward compat is verified for both empty fitted_walls and legacy wall_segments states.**

## Status: AWAITING LIVE HUMAN VERIFICATION

This plan is `autonomous: false`. All code is committed and all automated tests pass, but **RP-11 stays open until a human eyeballs the minimap on a live `oa_dm1` tour**. Do NOT mark RP-11 complete in REQUIREMENTS.md until the verification block at the bottom of this document has been signed off.

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-11
- **Tasks:** 1 code task (TDD RED -> GREEN), 1 live human-verify checkpoint (BLOCKED)
- **Files modified:** 3 (1 panel + 1 panel package init + 1 test file)

## Accomplishments

- Added 4 new RGB constants to `panels/__init__.py`: `RGB_FITTED_WALL = (60,220,120)`, `RGB_CORNER = (255,200,60)`, `RGB_ROOM_OUTLINE = (80,140,200)`, `RGB_ROOM_OUTLINE_CUR = (140,200,255)`. All exported via `__all__`.
- **Deleted** the legacy red stub render block at `minimap.py:192-203`. The old `if lm.get("wall_segments"):` -> `pygame.draw.line(surface, (255, 60, 60), ...)` is gone. `grep -n "(255, 60, 60)" openarena_perception/visualization/panels/minimap.py` returns zero matches.
- **Added** the Phase 13 render block in its place, in the locked draw order:
  1. **Room polygon fills** — for each room in `lm["rooms"]`, build screen-space vertices via `_world_to_minimap`, allocate an SRCALPHA temp surface sized to the polygon AABB, draw the polygon at `(*outline_color, fill_alpha)`, blit at `(min_x-1, min_y-1)`.
  2. **Room polygon outlines** — `pygame.draw.polygon` with `width=2 if is_current else 1`. Current-room match is `room.get("id") == current_room_id`.
  3. **Fitted walls** — for each `[id, x1, y1, x2, y2, conf, support, first_seen, last_seen]` in `lm["fitted_walls"]`, project endpoints and draw a 2px line at `RGB_FITTED_WALL`.
  4. **Corners** — for each `[id, x, y, wall_a, wall_b, angle, conf]` in `lm["corners"]`, project (x, y) and draw a filled circle radius 3 at `RGB_CORNER`.
- The rest of the draw method (surveyed rooms, items, trail, waypoints, player marker) is unchanged and still runs after the new block.

## Render Order (locked)

```
1. background fill + grid
2. AAS overhead (current floor only) -- _draw_aas_overhead
3. learned grid cells (OPEN/WALL/VISITED/LIQUID)
4. room polygon FILLS (alpha 50 / 80)              <-- new in 13-06
5. room polygon OUTLINES (1px / 2px for current)   <-- new in 13-06
6. fitted walls (2px bright green)                  <-- new in 13-06
7. corners (3px filled amber)                       <-- new in 13-06
8. surveyed rooms (existing)
9. items (existing)
10. route waypoints + line (existing)
11. trail (existing)
12. player marker + yaw arrow (existing)
13. area label text (existing)
```

## Color Constants

| Constant | RGB | Purpose |
|----------|-----|---------|
| `RGB_FITTED_WALL` | `(60, 220, 120)` | Bright green fitted architectural wall lines |
| `RGB_CORNER` | `(255, 200, 60)` | Amber corner vertex circles |
| `RGB_ROOM_OUTLINE` | `(80, 140, 200)` | Muted blue outline + fill for non-current rooms |
| `RGB_ROOM_OUTLINE_CUR` | `(140, 200, 255)` | Brighter blue outline + fill for the current room |

## Tests Added

In `tests/test_open_perception_panels.py`:

1. **`test_minimap_no_red_stub_color_in_source`** — string-grep guard: `(255, 60, 60)` must not appear in `minimap.py`. Locks the deletion in.
2. **`test_minimap_renders_fitted_walls_corners_rooms`** — builds a v3 HUD state with 4 fitted walls forming a 200x200 box, 4 corners at vertices, 1 room polygon, and `current_room_id=1`. Asserts:
   - Bright green pixels `(60,220,120)` exist (fitted walls drew).
   - Amber pixels `(255,200,60)` exist (corners drew).
   - Blue-dominant pixels exist (current-room polygon fill/outline drew). The pixel-equality check on the outline color was loosened to a blue-dominant scan because the fitted walls overdraw the polygon outline at the same screen coordinates in this synthetic test — the alpha fill still contributes blue-dominant pixels inside the polygon.
3. **`test_minimap_legacy_state_no_fitted_walls_falls_back`** — HUD state with `wall_segments=[]` and no `fitted_walls` key at all. Renders without raising; zero `(255,60,60)` pixels.
4. **`test_minimap_legacy_state_with_wall_segments_no_red_stubs`** — HUD state that still carries legacy `wall_segments` populated. The render must produce **zero** `(255,60,60)` pixels because the red stub render block is deleted, not just gated.

## Task Commits

| # | Phase | Commit | Description |
|---|-------|--------|-------------|
| 1 | RED | `e62a8ba` | test(13-06): add failing RP-11 tests for fitted walls render + red stub removal |
| 2 | GREEN | `60222e1` | feat(13-06): render fitted walls, corners, room polygons; remove red wall_segment stubs |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test refinement] Current-room outline test loosened from exact-color to blue-dominant**
- **Found during:** Task 1 GREEN run
- **Issue:** The synthetic test fixture has fitted walls and the room polygon at exactly the same coordinates (the wall endpoints ARE the polygon vertices). With the locked render order (room outline below fitted walls), the bright-green wall lines overdraw the blue outline. An exact-RGB match on `(140,200,255)` returned 0 pixels.
- **Fix:** Changed the assertion to scan for blue-dominant pixels (`B - R > 30 AND B - G > 0 AND B > 80`) which still proves the room polygon block ran (the alpha fill inside the polygon contributes blue-dominant pixels even when the outline edge is overdrawn). This matches what a human will actually see on a real map: walls live on the polygon edges, but the interior alpha fill is what visually identifies a room.
- **Files modified:** `tests/test_open_perception_panels.py`
- **Verification:** `test_minimap_renders_fitted_walls_corners_rooms` green; the other 3 RP-11 tests still green.
- **Committed in:** `60222e1` (combined with the GREEN implementation since the test was finalized in the same commit cycle)

**Total deviations:** 1 test refinement. No production-code deviations. No new architectural decisions.

## Verification

### Automated (passing)

- `SDL_VIDEODRIVER=dummy uv run pytest tests/test_open_perception_panels.py -q` -- **27/27 green** (4 new RP-11 tests + 23 prior)
- `grep -n "(255, 60, 60)" openarena_perception/visualization/panels/minimap.py` -- **0 matches** (red stub gone)
- `grep -n "fitted_walls" openarena_perception/visualization/panels/minimap.py` -- 2 matches (lookup + iteration)
- `uv run pytest -q` -- **774 passed, 1 unrelated flaky failure** in `tests/test_humanize.py::test_accuracy_cap_enforced_in_aim_controller` (Perlin-noise stochastic flake; not touched by this plan; same flake seen on baseline)
- Ruff/mypy on Phase 13 touched files: my edits introduce **zero new violations**. Pre-existing `typing.Tuple`/`Optional` style and import-sort warnings in `minimap.py`/`__init__.py` are baseline state from earlier phases (verified via `git stash` baseline check) and out of scope for this plan.

### Live human verification (PENDING -- BLOCKING)

**Status:** AWAITING USER

**Procedure:**

1. Launch the OpenArena game on `oa_dm1` (whichever launcher you normally use).
2. In a terminal at `/home/hoyack/openarena-perception`, run:
   ```bash
   uv run python item_tour.py --no-vision
   ```
   (or whatever the current item_tour invocation is for your environment)
3. In a second terminal, run the HUD:
   ```bash
   uv run python open_perception.py
   ```
4. Let the bot tour for **at least 60-90 seconds** so the raycast cloud accumulates and `fit_rooms()` fires (every ~3 s -> ~30 fits in the window).
5. Visually verify each of the following on the minimap:

   - [ ] **NO red stubs anywhere**. The old `(255,60,60)` perpendicular hash marks are gone.
   - [ ] **Bright green fitted wall lines** appear on top of the learned grid cells after the first 10-15 seconds. They should look like CAD edges, not scattered.
   - [ ] **At least one room polygon** appears as a faint blue outline + interior fill. The polygon brightens (2px outline, 80/255 fill) when the bot is INSIDE.
   - [ ] **Amber dots** appear at line intersections (corners).
   - [ ] **Stats panel rows 10-11** (`room:` and `room_items:`) show real values when the bot is inside a room; placeholder `----` when outside or before any fit.
   - [ ] **FPS holds >= 10** (existing `tick_rate` row).
   - [ ] **No crashes / no tracebacks** on either terminal.
   - [ ] **Phase 12.1 features still work**: AAS overhead visible, current-floor filter correct, trail drawn, waypoints drawn, path progress bar updates.

   On success, the user updates `REQUIREMENTS.md` to mark **RP-11 verified** (or signals the orchestrator to do so) and the orchestrator advances Phase 13 to `/gsd-verify-work`.

   On failure, describe which of the 8 checks failed and what appeared on screen so the deviation can be fixed in a follow-up patch.

## Known Stubs

None. All Phase 13 data surfaces (`fitted_walls`, `corners`, `rooms`, `doorways`, `current_room_id`) are wired into the minimap render. The remaining work is the live eyeball check.

## Threat Flags

None. Pure visualization change inside an existing pygame surface; no network surface, no auth paths, no file access patterns.

## Self-Check: PASSED

Files verified present:
- `openarena_perception/visualization/panels/minimap.py` — has `fitted_walls`, `corners`, `rooms`, `RGB_FITTED_WALL`, `RGB_ROOM_OUTLINE_CUR`
- `openarena_perception/visualization/panels/__init__.py` — has `RGB_FITTED_WALL`, `RGB_CORNER`, `RGB_ROOM_OUTLINE`, `RGB_ROOM_OUTLINE_CUR` in the constants block AND in `__all__`
- `tests/test_open_perception_panels.py` — has `test_minimap_no_red_stub_color_in_source`, `test_minimap_renders_fitted_walls_corners_rooms`, `test_minimap_legacy_state_no_fitted_walls_falls_back`, `test_minimap_legacy_state_with_wall_segments_no_red_stubs`

Commits verified present in `git log`:
- `e62a8ba` test RED
- `60222e1` feat GREEN

Red stub absence verified: `grep -n "(255, 60, 60)" openarena_perception/visualization/panels/minimap.py` -> 0 matches.

---
*Phase: 13-room-perception-and-wall-reconstruction*
*Plan: 06*
*Status: AWAITING LIVE HUMAN VERIFICATION on oa_dm1 — DO NOT MARK COMPLETE*
*Automated work completed: 2026-04-11*
