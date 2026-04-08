---
phase: 01-foundation-and-characterization
plan: 04
subsystem: testing
tags: [pytest, fsm, characterization-tests, strategic-brain, state-machine]

# Dependency graph
requires:
  - phase: 01-foundation-and-characterization/plan-03
    provides: "SituationalAwareness and BrainState in models.py, conftest.py with make_awareness fixture"
provides:
  - "52-test FSM characterization suite covering all 8 states, transitions, timing guards, and side effects"
  - "strategic_brain fixture with fully mocked dependencies"
affects: [phase-02, phase-03, phase-04, phase-05]

# Tech tracking
tech-stack:
  added: []
  patterns: ["characterization test pattern: capture actual behavior before refactoring", "direct state manipulation via brain._state and brain._state_enter_time for FSM testing"]

key-files:
  created: [tests/test_strategic_brain_characterization.py]
  modified: [tests/conftest.py]

key-decisions:
  - "Used fixture-based factory for make_awareness (existing pattern from Plan 03) rather than plain function"
  - "Mocked all optional StrategicBrain dependencies (obj_tracker, anomaly_tracker, surveyor, spatial) in fixture to prevent real object construction"
  - "Organized tests into 6 classes by concern: priorities, returns, stay-in-state, on-enter, on-exit, timing guards"

patterns-established:
  - "FSM characterization: set brain._state and brain._state_enter_time directly, call _evaluate_transitions(sa), assert result"
  - "Side-effect testing: call _on_enter_state/_on_exit_state directly, assert mock calls"

requirements-completed: [FOUND-07]

# Metrics
duration: 4min
completed: 2026-04-08
---

# Phase 01 Plan 04: FSM Characterization Tests Summary

**52-test safety net covering all 8 FSM states, priority-ordered transitions, timing guards, and on-enter/on-exit side effects for strategic_brain.py**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-08T12:05:01Z
- **Completed:** 2026-04-08T12:09:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Complete characterization of _evaluate_transitions() with 52 passing tests
- Priority ordering verified: DEAD > COMBAT > STUCK > PICKUP > DOOR > SURVEY
- All timing guards tested: 2s (door entry), 3s (combat cooldown), 5s (door/pickup timeout), 15s (survey timeout)
- On-enter side effects captured: death counting, control release, tracker reset, firing start, stuck blacklisting, path_to_random
- On-exit side effects captured: look release, combat stop, survey center view

## Task Commits

Each task was committed atomically:

1. **Task 1: Update conftest.py with strategic_brain fixture** - `63444ff` (chore)
2. **Task 2: Write comprehensive FSM characterization tests** - `f8e54e2` (test)

## Files Created/Modified
- `tests/test_strategic_brain_characterization.py` - 532 lines, 52 tests across 6 classes characterizing all FSM behavior
- `tests/conftest.py` - Added strategic_brain fixture with fully mocked dependencies

## Decisions Made
- Kept existing make_awareness as fixture factory (from Plan 03) rather than converting to plain function as plan suggested -- the factory fixture pattern works identically and maintains consistency
- Mocked all optional StrategicBrain constructor params (obj_tracker, anomaly_tracker, surveyor, spatial) to prevent real object construction that would fail or have real side effects in tests

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed strategic_brain fixture missing optional dependency mocks**
- **Found during:** Task 2 (test_enter_dead_resets_trackers failed)
- **Issue:** StrategicBrain constructor creates real MotionAnomalyTracker and ObjectTracker when not provided, causing mock assertions to fail
- **Fix:** Added obj_tracker, anomaly_tracker, surveyor, spatial as MagicMock() in the strategic_brain fixture
- **Files modified:** tests/conftest.py
- **Verification:** All 52 tests pass
- **Committed in:** f8e54e2 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary fix for test correctness. No scope creep.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- FSM safety net is complete -- all 52 characterization tests pass
- Phase 2+ extraction work can proceed with confidence that any behavioral regression will be caught
- Plan 05 (integration smoke tests) is the final foundation plan

---
*Phase: 01-foundation-and-characterization*
*Completed: 2026-04-08*
