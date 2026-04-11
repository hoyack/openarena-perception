---
phase: quick
plan: 260411-gaa-lm-halt-shorter-avoid
subsystem: navigation
tags: [tuning, item-tour, avoidance, learned-map, wall-halt]

requires:
  - phase: debug/bot-wall-gazing-regression
    provides: Fix path D — shorten learned-map-only halt duration to nudge the bot instead of spinning
provides:
  - Halt-reason-aware avoidance hold in item_tour.py (vision 500ms, learned_map 150ms)
affects: [item_tour, future tour verification runs on oa_dm1]

tech-stack:
  added: []
  patterns:
    - Halt-reason-branched timing constants in item_tour tick loop

key-files:
  created: []
  modified:
    - item_tour.py

key-decisions:
  - "Learned-map-only halts use 150ms hold; vision/visual_pin halts keep 500ms"
  - "Unknown halt reasons default to VISION duration (safer, preserves existing behavior)"

patterns-established:
  - "Avoidance-hold duration can be selected per halt_reason at the commit site without restructuring the hold gate"

requirements-completed: []

duration: 3min
completed: 2026-04-11
---

# Quick Plan 260411-gaa-lm-halt-shorter-avoid Summary

**Halt-reason-aware avoidance hold in item_tour — vision halts keep the 500ms hold, learned-map-only halts drop to 150ms so a single false-positive forward-look-ahead trip nudges the bot instead of spinning it 30-60 degrees.**

## Performance

- **Duration:** ~3 min
- **Completed:** 2026-04-11
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Replaced the single `_AVOIDANCE_DURATION = 0.5` constant with two explicit constants:
  `_AVOIDANCE_DURATION_VISION = 0.5` and `_AVOIDANCE_DURATION_LM = 0.15`
- Commit site at ~line 797 branches on `halt_reason == "learned_map"` to select the shorter hold,
  with every other reason (vision, visual_pin, unknown) falling through to the VISION hold
- Inline comments on both constants and commit site reference `.planning/debug/bot-wall-gazing-regression.md` fix path D
- Full pytest suite still green (775 passed, no regressions vs 774 baseline)

## Task Commits

1. **Task 1: Split `_AVOIDANCE_DURATION` into VISION/LM constants + branch at commit site** — `881e508` (tune)
2. **Task 2: Confirm pytest baseline still green** — no commit (verification-only)

## Files Created/Modified

- `item_tour.py` — avoidance hold duration split into VISION/LM constants; commit site branches on `halt_reason`

## Decisions Made

- `halt_reason == "learned_map"` is the only branch that takes the shorter hold. `"vision"`, `"visual_pin"`, and any future/unknown reason default to VISION duration — preserves existing high-confidence behavior and only softens the low-confidence learned-map trigger.
- Hold mechanism at `item_tour.py:707-713` (`if now < self._avoidance_until`) left untouched — only the duration value differs per halt_reason.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None. Edit applied cleanly, grep shows exactly four `_AVOIDANCE_DURATION` matches (two definitions, two commit-site references), no leftover bare `_AVOIDANCE_DURATION` symbol. ast.parse clean.

## Verification

- `grep -n "_AVOIDANCE_DURATION" item_tour.py` → 4 matches (lines 346, 347, 797, 799), all suffixed with `_VISION` or `_LM`
- `python -c "import ast; ast.parse(open('item_tour.py').read())"` → parse OK
- `uv run pytest -q` → 775 passed in 65.76s (baseline 774, zero failures/errors)

## Self-Check: PASSED

- FOUND: item_tour.py modification (grep confirms 4 matches, no bare `_AVOIDANCE_DURATION`)
- FOUND: commit 881e508 in git log

## Next Phase Readiness

Ready for next live verification run on oa_dm1 to measure whether the shorter LM hold reduces the visible "spinning and looking at walls" duty cycle. Companion actions from the debug doc (fix paths A, B, C, E) remain available — particularly A (reset on-disk learned_map state bias) and B (cap/decay edge_penalty).

---
*Plan: quick/260411-gaa-lm-halt-shorter-avoid*
*Completed: 2026-04-11*
