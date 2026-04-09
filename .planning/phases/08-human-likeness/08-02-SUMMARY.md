---
phase: 08-human-likeness
plan: 02
subsystem: tactics, combat
tags: [reaction-time, hesitation, movement-variability, humanization, fsm, strafe-noise]

requires:
  - phase: 08-01
    provides: HumanizationConfig with skill-level parameter mapping
provides:
  - Reaction time delay buffer in TacticalFSM.tick()
  - Hesitation delay on state transitions
  - DEAD state safety invariant (never delayed)
  - Strafe timing noise in CombatMover
  - Path deviation chance for movement variability
  - corner_overshoot_px property for NavBehavior consumption
affects: [08-03, 08-04, 08-05]

tech-stack:
  added: []
  patterns:
    - "Timestamp comparison delay buffer (not sleep/await) for reaction time"
    - "_pending_transition tuple[BrainState, float] for buffered state changes"
    - "TYPE_CHECKING guard for HumanizationConfig imports"

key-files:
  created:
    - tests/test_fsm_humanize.py
    - tests/test_combat_humanize.py
  modified:
    - openarena_perception/tactics/fsm.py
    - openarena_perception/combat/combat_movement.py

key-decisions:
  - "Reaction delay uses timestamp comparison, not sleep/await -- tick loop runs at full speed"
  - "Extracted _execute_transition method from tick() for reuse by delay-aware and immediate paths"
  - "Strafe interval clamped to [0.15, 1.5] to prevent degenerate values (T-08-05)"

patterns-established:
  - "Delay buffer pattern: _pending_transition = (target_state, expire_time) with timestamp check each tick"
  - "Safety invariant: DEAD state always returns 0.0 delay regardless of config"

requirements-completed: [HUMN-02, HUMN-03, HUMN-06]

duration: 4min
completed: 2026-04-09
---

# Phase 8 Plan 02: Reaction Delays & Movement Variability Summary

**Reaction time delay buffer (150-350ms) and hesitation (80-500ms) in TacticalFSM with strafe timing noise and path deviation in CombatMover**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-09T15:47:20Z
- **Completed:** 2026-04-09T15:51:20Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- TacticalFSM buffers state transitions by reaction_time + hesitation delay, using timestamp comparison (no blocking)
- DEAD state transitions are NEVER delayed -- explicit safety invariant with 0.0 return
- COMBAT entry from non-combat state adds surprise bonus delay
- CombatMover strafe timing has noise injection with interval clamped to [0.15, 1.5]
- Path deviation chance occasionally inverts strafe direction for human-like hesitation
- corner_overshoot_px property exposed for NavBehavior (Plan 03)
- All 426 tests pass including 20 new humanization tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Add reaction delay buffer and hesitation to TacticalFSM** - `fd96fc3` (test) + `16e753e` (feat)
2. **Task 2: Add movement variability to CombatMover** - `b46897d` (test) + `f021f5b` (feat)

_Note: TDD tasks have separate test and implementation commits._

## Files Created/Modified
- `openarena_perception/tactics/fsm.py` - Added humanize_config, _pending_transition, _sample_reaction_delay(), _execute_transition()
- `openarena_perception/combat/combat_movement.py` - Added humanize_config, strafe noise, path deviation, corner_overshoot_px property
- `tests/test_fsm_humanize.py` - 12 tests for reaction delay, hesitation, DEAD safety, surprise bonus
- `tests/test_combat_humanize.py` - 8 tests for strafe noise, path deviation, backward compat

## Decisions Made
- Reaction delay uses timestamp comparison, not sleep/await -- tick loop runs at full speed (T-08-03 mitigation)
- Extracted _execute_transition method from tick() for reuse by both immediate and delay-aware paths
- Strafe interval clamped to [0.15, 1.5] to prevent degenerate values (T-08-05 mitigation)
- DEAD state always returns 0.0 delay (T-08-04 mitigation)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- HumanizationConfig now consumed by TacticalFSM (reaction/hesitation) and CombatMover (strafe/deviation)
- corner_overshoot_px property ready for NavBehavior in Plan 03
- All backward compatibility preserved when humanize_config=None

---
*Phase: 08-human-likeness*
*Completed: 2026-04-09*
