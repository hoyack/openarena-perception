---
phase: 04-reflexes-combat-and-navigation-extraction
plan: 01
subsystem: reflexes
tags: [subsumption, fsm, death-handler, stuck-escape, arbiter, reflex-arc]

requires:
  - phase: 01-foundation
    provides: "Characterization tests, BrainState enum, SituationalAwareness dataclass"
  - phase: 02-perception-pipeline
    provides: "Perception subsystem extraction pattern (re-exports, __init__.py)"
provides:
  - "SubsumptionArbiter with priority-ordered evaluate() for state transitions"
  - "DeathHandler for death detection, state reset, respawn tap"
  - "StuckEscape for stuck recovery delegation with target blacklisting"
  - "Clean reflexes/ package with re-exports"
affects: [04-02, 04-03, 04-04, 04-05, 05-orchestrator]

tech-stack:
  added: []
  patterns: ["Subsumption arbiter pattern: evaluate() returns BrainState from SituationalAwareness", "Reflex handler pattern: on_enter/on_exit/tick methods with SA + context injection"]

key-files:
  created:
    - openarena_perception/reflexes/arbiter.py
    - openarena_perception/reflexes/death_handler.py
    - openarena_perception/reflexes/stuck_escape.py
  modified:
    - openarena_perception/reflexes/__init__.py

key-decisions:
  - "SubsumptionArbiter accepts **context kwargs for survey/commander/spatial checks rather than storing references"
  - "DeathHandler.was_alive uses property setter so other states can mark bot alive"
  - "StuckEscape.on_enter returns updated nav_target (None if blacklisted) instead of mutating external state"

patterns-established:
  - "Reflex modules import only from models.py and brainstem modules -- no cross-subsystem imports"
  - "TYPE_CHECKING imports for GameBridge/VirtualController/Navigator to avoid import-time coupling"

requirements-completed: [RFLX-01, RFLX-02, RFLX-03, RFLX-04]

duration: 2min
completed: 2026-04-08
---

# Phase 4 Plan 1: Reflexes Extraction Summary

**SubsumptionArbiter with exact priority chain, DeathHandler with respawn tap, StuckEscape with 90s target blacklisting -- all extracted from strategic_brain.py into reflexes/ package**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-08T14:16:01Z
- **Completed:** 2026-04-08T14:18:30Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Extracted all priority transition logic from _evaluate_transitions() into SubsumptionArbiter.evaluate()
- Extracted death handling (state reset, tracker reset, respawn tap) into DeathHandler
- Extracted stuck recovery delegation and target blacklist logic into StuckEscape
- All 145 tests pass (52 characterization + 93 others), zero cross-subsystem imports

## Task Commits

Each task was committed atomically:

1. **Task 1: Create SubsumptionArbiter in reflexes/arbiter.py** - `9fea50c` (feat)
2. **Task 2: Create DeathHandler and StuckEscape, update reflexes/__init__.py** - `93d6611` (feat)

## Files Created/Modified
- `openarena_perception/reflexes/arbiter.py` - SubsumptionArbiter with priority-ordered evaluate() preserving exact _evaluate_transitions() logic
- `openarena_perception/reflexes/death_handler.py` - DeathHandler with on_enter/on_exit/tick for death detection and respawn
- `openarena_perception/reflexes/stuck_escape.py` - StuckEscape with on_enter/tick/is_blacklisted/reset_stuck_count and target blacklisting
- `openarena_perception/reflexes/__init__.py` - Clean re-exports of all three reflex classes

## Decisions Made
- SubsumptionArbiter uses **context kwargs for optional dependencies (surveyor, spatial, commander) rather than constructor injection -- keeps the arbiter stateless and testable
- DeathHandler.was_alive exposed as property with setter so _tick_combat and other states can set was_alive = True without reaching into private state
- StuckEscape.on_enter returns the (possibly None) nav_target rather than mutating external state directly -- cleaner interface for the orchestrator

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Reflexes subsystem complete and ready for integration in Plan 04-04 (thin orchestrator)
- Combat extraction (Plan 04-02) and navigation extraction (Plan 04-03) can proceed in parallel
- Characterization tests remain green as safety net for subsequent extractions

---
*Phase: 04-reflexes-combat-and-navigation-extraction*
*Completed: 2026-04-08*
