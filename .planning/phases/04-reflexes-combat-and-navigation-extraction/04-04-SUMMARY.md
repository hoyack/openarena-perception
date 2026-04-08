---
phase: 04-reflexes-combat-and-navigation-extraction
plan: 04
subsystem: architecture
tags: [fsm, subsumption, orchestrator, delegation, strategic-brain]

# Dependency graph
requires:
  - phase: 04-01
    provides: SubsumptionArbiter, DeathHandler, StuckEscape in reflexes/
  - phase: 04-02
    provides: CombatEngager in combat/
  - phase: 04-03
    provides: NavBehavior, SurveyBehavior in navigation/
provides:
  - Thin orchestrator strategic_brain.py delegating to subsystem modules
  - Property bridges for backward-compatible attribute access
  - was_alive propagation in orchestrator tick (T-04-08 mitigation)
affects: [05-api, 06-testing, 07-competitive]

# Tech tracking
tech-stack:
  added: []
  patterns: [property-bridge delegation, subsumption dispatch, thin orchestrator]

key-files:
  created: []
  modified: [openarena_perception/strategic_brain.py]

key-decisions:
  - "Property bridges on StrategicBrain for backward compat with characterization tests (_deaths, _stuck_attempts, _nav_target, etc.)"
  - "was_alive set in orchestrator tick() before dispatch rather than in each subsystem tick"
  - "DeathHandler.on_exit() called for ALL state exits (not just DEAD) to preserve look-release behavior"
  - "Survey cooldown managed in orchestrator dispatch since SurveyBehavior.tick returns cooldown timestamp"

patterns-established:
  - "Property bridge pattern: StrategicBrain exposes subsystem state via @property for backward compat"
  - "Orchestrator dispatch: if/elif chain over BrainState calling subsystem tick methods"

requirements-completed: [RFLX-04, CMBT-01, CMBT-05, NAV-05, NAV-06]

# Metrics
duration: 3min
completed: 2026-04-08
---

# Phase 4 Plan 4: Strategic Brain Rewiring Summary

**Rewired strategic_brain.py from 681-line god object to 494-line thin orchestrator delegating to reflexes/, combat/, navigation/ subsystems**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-08T14:38:25Z
- **Completed:** 2026-04-08T14:41:22Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Replaced _evaluate_transitions() with SubsumptionArbiter.evaluate() call
- Replaced all 8 _tick_* methods with subsystem dispatch (CombatEngager, NavBehavior, SurveyBehavior, DeathHandler, StuckEscape)
- Replaced _on_enter_state/_on_exit_state with subsystem on_enter/on_exit delegation
- Removed 187 lines of inline behavior code (681 -> 494 lines, 27% reduction)
- All 52 characterization tests pass with zero test modifications
- Full test suite (145 tests) passes
- Zero circular imports between subsystems
- Ruff clean on strategic_brain.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewire strategic_brain.py imports and constructor** - `44c90c8` (feat)
2. **Task 2: Verify full test suite and clean up imports** - `97250c6` (chore)

**Plan metadata:** pending (docs: complete plan)

## Files Created/Modified
- `openarena_perception/strategic_brain.py` - Thin orchestrator delegating to reflexes/, combat/, navigation/ subsystem modules

## Decisions Made
- Used property bridges (@property) on StrategicBrain to maintain backward compatibility with characterization tests that access internal attributes like _deaths, _stuck_attempts, _nav_target
- Set was_alive in orchestrator tick() before dispatch (option b from plan) rather than in each subsystem tick -- simpler and centralized
- DeathHandler.on_exit(sa) called for ALL state exits to preserve the original behavior where look actions are always released
- Survey cooldown returned from SurveyBehavior.tick() and captured in orchestrator, since cooldown is cross-cutting orchestrator state

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed DeathHandler.on_exit call signature**
- **Found during:** Task 1
- **Issue:** Plan specified `self._death_handler.on_exit(sa, self.bridge)` but DeathHandler.on_exit only takes `(self, sa)` -- bridge is stored internally
- **Fix:** Called `self._death_handler.on_exit(sa)` without bridge parameter
- **Files modified:** openarena_perception/strategic_brain.py
- **Verification:** All 52 characterization tests pass
- **Committed in:** 44c90c8

**2. [Rule 2 - Missing Critical] Added property bridges for backward compatibility**
- **Found during:** Task 1
- **Issue:** Characterization tests access internal attributes (_deaths, _stuck_attempts, _stucks_on_current_target, _target_blacklist, _target_failures, _nav_target, _items_collected) directly on StrategicBrain. Removing these attributes would break all on-enter/on-exit tests.
- **Fix:** Added @property and @setter bridges that delegate to subsystem instances
- **Files modified:** openarena_perception/strategic_brain.py
- **Verification:** All 52 characterization tests pass without modification
- **Committed in:** 44c90c8

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both auto-fixes necessary for correctness. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- strategic_brain.py is now a thin orchestrator (494 lines)
- All subsystem modules (reflexes/, combat/, navigation/) are wired and working
- Plan 05 (final cleanup/documentation) can proceed
- Full test suite green (145 tests)

---
*Phase: 04-reflexes-combat-and-navigation-extraction*
*Completed: 2026-04-08*
