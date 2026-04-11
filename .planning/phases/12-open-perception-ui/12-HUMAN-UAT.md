---
status: partial
phase: 12-open-perception-ui
source: [12-VERIFICATION.md]
started: 2026-04-11T00:00:00Z
updated: 2026-04-11T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Live three-panel Open-Perception HUD against a real bot tour
expected: |
  Open two terminals. In #1: `OA_INTENT_PAUSE_MS=500 uv run python item_tour.py --no-vision`
  In #2: `uv run python open_perception.py`
  Visually confirm EVERY item in the 12-03-PLAN Task 3 checklist:
  - Window is 1400x700, titled "Open-Perception"
  - Three visibly separated panels with vertical lines at x=400 and x=1000
  - LEFT panel: minimap with player marker + yaw arrow that moves; route waypoints (dim blue future / bright yellow current / gray done); learned map occupancy; current area label; NO HP/POS/YAW/AMMO text
  - CENTER panel: wireframe face-mesh view updating with bot pose; corner brackets + crosshair + "// PERCEPTION ACTIVE" + "SRC 600x700"; NO FRAME/ROOM/FOV/MODE/OBJECTS text, NO HP/POS overlay
  - RIGHT panel: vital stats (HP/armor/weapon/ammo/pos/yaw), intent block (macro big yellow / sub white / duration), 2Hz blue pause-border flash during pause-to-assess, 5 intent-history rows, 5 color-coded problem-history rows, path progress bar, 9 verbose rows (stair_climb, swim_edge, advisor, last_replans, tick_rate, frame_lag, halts, vpin, nav_step)
  - frame_lag row flashes red when >100ms
  - Every metric appears EXACTLY ONCE across the three panels
  - Wireframe + minimap update simultaneously with bot movement
  - Closing the window with the X button exits cleanly (no traceback)
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
