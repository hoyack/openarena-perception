---
phase: 05-tactics-and-strategy-extraction
plan: 02
subsystem: tactics
tags: [commander, fight-or-flight, threat-assessment, fsm, refactoring]

# Dependency graph
requires:
  - phase: 04-reflexes-combat-navigation-extraction
    provides: "ThreatAssessor in combat/threat_assess.py, Commander in navigation/commander.py"
  - phase: 05-tactics-and-strategy-extraction/01
    provides: "TacticalFSM in tactics/fsm.py, tactics/ package structure"
provides:
  - "Commander class canonically in tactics/commander.py with backward-compat re-exports"
  - "FightOrFlight wrapper around ThreatAssessor for FSM-level decisions"
  - "tactics/__init__.py exporting TacticalFSM, Commander, ItemMemory, FightOrFlight"
affects: [05-tactics-and-strategy-extraction/03, 05-tactics-and-strategy-extraction/04]

# Tech tracking
tech-stack:
  added: []
  patterns: [re-export stubs for backward compatibility, wrapper pattern for cross-subsystem delegation]

key-files:
  created:
    - openarena_perception/tactics/commander.py
    - openarena_perception/tactics/fight_or_flight.py
  modified:
    - openarena_perception/tactics/__init__.py
    - openarena_perception/navigation/__init__.py
    - openarena_perception/navigation/commander.py
    - openarena_perception/commander.py

key-decisions:
  - "Commander relocated to tactics/ (goal selection, not navigation) with re-export stubs preserving all existing import paths"
  - "FightOrFlight wraps ThreatAssessor via delegation, no logic duplication"

patterns-established:
  - "Re-export stub pattern: deprecated modules re-export from canonical location for backward compat"
  - "Wrapper pattern: tactics/ wraps combat/ assessors without duplicating logic"

requirements-completed: [TACT-02, TACT-03]

# Metrics
duration: 2min
completed: 2026-04-08
---

# Phase 5 Plan 02: Commander Relocation and Fight-or-Flight Wrapper Summary

**Commander moved to tactics/ as canonical location with FightOrFlight wrapper delegating to combat.ThreatAssessor**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-08T21:59:53Z
- **Completed:** 2026-04-08T22:01:22Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Commander class relocated from navigation/ to tactics/ (its logical home as goal selection)
- All three import paths (tactics.commander, navigation.commander, root commander) resolve to the same class
- FightOrFlight wrapper provides FSM-consumable interface around existing ThreatAssessor
- tactics/__init__.py exports all four components: TacticalFSM, Commander, ItemMemory, FightOrFlight
- 52 characterization tests pass unchanged throughout

## Task Commits

Each task was committed atomically:

1. **Task 1: Move Commander to tactics/ with re-export stubs** - `35f5eed` (feat)
2. **Task 2: Create tactics/fight_or_flight.py wrapper and update __init__** - `d2296e2` (feat)

## Files Created/Modified
- `openarena_perception/tactics/commander.py` - Commander class (canonical location, verbatim copy)
- `openarena_perception/tactics/fight_or_flight.py` - FightOrFlight wrapper around ThreatAssessor
- `openarena_perception/tactics/__init__.py` - Updated to export all tactical components
- `openarena_perception/navigation/commander.py` - Deprecated re-export stub
- `openarena_perception/navigation/__init__.py` - Updated import to use tactics.commander
- `openarena_perception/commander.py` - Root re-export stub updated to use tactics.commander

## Decisions Made
- Commander relocated to tactics/ (goal selection is tactical, not navigational) with re-export stubs preserving all existing import paths
- FightOrFlight wraps ThreatAssessor via delegation -- no logic duplication, single source of truth in combat/

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- tactics/ package now has FSM (Plan 01), Commander, and FightOrFlight ready for integration
- Plans 03-04 can wire the LLM strategy brain and reduce strategic_brain.py to thin orchestrator

---
*Phase: 05-tactics-and-strategy-extraction*
*Completed: 2026-04-08*
