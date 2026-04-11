---
slug: 260411-gzi-break-hint-chain
date: 2026-04-11
type: tune
commit: e08ad30
tags: [item_tour, wall-halt, tuning, feedback-loop]
---

# Quick Task: Break Turn-Hold Re-Commit Chain

**One-liner:** Shortened the proactive wall-halt commit window, lengthened the halt throttle, and added a consecutive-same-hint escalation cap so `item_tour` stops chaining turn taps into a full spin.

## Problem

During live Phase 13 verification the bot was holding `turn_right_and_strafe` for 3–5 seconds on wall halts, which at ~140°/s yaw rate is ~420–700° of rotation — a full spin or more. Quick task `260411-gaa` already addressed learned-map-only halts (150 ms hold), but vision-path halts were still committing 0.5 s at a time and chaining indefinitely.

Root cause chain (already diagnosed, not re-investigated here):

```
halt fires → picker sees open_dir>0 → pick turn_right_and_strafe
 → commit 0.5s of turn+strafe (item_tour.py:736-742 re-presses keys every tick)
 → commit expires, ~1 tick of free +forward
 → 0.5s halt throttle elapses → halt re-fires, same open_dir → same hint → renew commit
 → 3-5 chained commits = full spin
```

There was no feedback mechanism for "the picked turn isn't clearing the wall" because the hint was never compared across consecutive fires.

## Changes

All in `item_tour.py`, single commit `e08ad30`:

1. **`_AVOIDANCE_DURATION_VISION: 0.5 → 0.2`** (line 346). Per-tap rotation drops from ~70° to ~28° at the 140°/s rate. `_AVOIDANCE_DURATION_LM` stays at 0.15 s (already correct from task 260411-gaa).
2. **Proactive halt throttle: `> 0.5` → `> 1.0`** (line 758). After a halt commits, the bot gets ≥ 800 ms of free +forward before another halt can fire — real observation window for whether the turn actually cleared the wall.
3. **Consecutive-same-hint cap** (lines 350–355 state, lines ~795–815 cap logic, lines ~862–865 reset). New state `_last_hint_for_halt` / `_consecutive_hint_count` / `_CONSECUTIVE_HINT_CAP = 3`. On the 3rd identical fire, escalate: force `hint = "back_away"` and call `self._goto_next()` to replan from the current position. Counter resets on any halt-free tick.

## Files Modified

- `item_tour.py` (+33 / −2)
- `.planning/quick/260411-gzi-break-hint-chain/SUMMARY.md` (this file)
- `.planning/STATE.md` (Quick Tasks Completed row)

## Verification

- `uv run python -c "import ast; ast.parse(open('item_tour.py').read())"` → OK
- `grep -n "_AVOIDANCE_DURATION_VISION = 0.2" item_tour.py` → match (line 346)
- `grep -n "> 1.0" item_tour.py` → match (line 758, throttle)
- `grep -n "_CONSECUTIVE_HINT_CAP = 3" item_tour.py` → match (line 354)
- `grep -n "HINT ESCALATION" item_tour.py` → match (escalation log line)
- `uv run pytest -q` → 775 passed (matches baseline). A transient flake on `test_accuracy_cap_enforced_in_aim_controller` (hypothesis/RNG-dependent, aim-controller code not touched) cleared on re-run.
- Live eyeball on `oa_dm1` is the acceptance gate for this tuning task — no new unit tests added.

## Non-Goals (explicitly untouched)

- `learned_map.py`
- `_AVOIDANCE_DURATION_LM` (already correct at 0.15 s)
- `_check_proactive_wall` detection logic
- Advisor action handler / `_execute_advisor_action`
- Feature flags
- New unit tests

## Follow-ups

- Watch live runs for `HINT ESCALATION` log lines. Frequent fires would indicate the wall detector + `open_dir` picker still need deeper work (fix paths B/C/E from `.planning/debug/bot-wall-gazing-regression.md`).
- If wall-gazing persists after this, the remaining debug-report fix paths should be scoped as a dedicated follow-up phase, not another quick task.
