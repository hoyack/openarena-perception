---
phase: 04-reflexes-combat-and-navigation-extraction
plan: 03
subsystem: navigation
tags: [aas, pathfinding, learned-map, room-survey, commander, nav-behavior]

# Dependency graph
requires:
  - phase: 01-project-setup
    provides: brain-inspired folder structure with navigation/ stub
provides:
  - navigation/ package with 9 modules (6 moved + 2 behaviors + __init__)
  - NavBehavior with tick_navigating, tick_exploring, tick_door, tick_pickup
  - SurveyBehavior with tick method for room surveys
  - Backward-compatible shims at root for all 6 moved modules
affects: [04-04, 04-05, 05-integration]

# Tech tracking
tech-stack:
  added: []
  patterns: [navigation-subsystem-package, backward-compat-shims, TYPE_CHECKING-imports]

key-files:
  created:
    - openarena_perception/navigation/aas_parser.py
    - openarena_perception/navigation/navigator.py
    - openarena_perception/navigation/learned_map.py
    - openarena_perception/navigation/exit_finder.py
    - openarena_perception/navigation/room_surveyor.py
    - openarena_perception/navigation/commander.py
    - openarena_perception/navigation/nav_behavior.py
    - openarena_perception/navigation/survey_behavior.py
  modified:
    - openarena_perception/navigation/__init__.py
    - openarena_perception/aas_parser.py
    - openarena_perception/navigator.py
    - openarena_perception/learned_map.py
    - openarena_perception/exit_finder.py
    - openarena_perception/room_surveyor.py
    - openarena_perception/commander.py

key-decisions:
  - "Used TYPE_CHECKING imports for brainstem deps in navigation/ (same pattern as reflexes/ and combat/)"
  - "tick_navigating and tick_exploring accept tick_count parameter to avoid coupling to StrategicBrain._tick"
  - "NavBehavior exposes nav_target and blacklist as properties for StrategicBrain integration"

patterns-established:
  - "Navigation behavior extraction: tick methods accept (sa, gs, tick_count) for decoupled state handling"
  - "Backward-compat shims: root files re-export from navigation/ package with DEPRECATED docstring"

requirements-completed: [NAV-01, NAV-02, NAV-03, NAV-04, NAV-05, NAV-06]

# Metrics
duration: 9min
completed: 2026-04-08
---

# Phase 04 Plan 03: Navigation Extraction Summary

**AAS pathfinding, learned map, room surveys, commander, and 2 behavior modules consolidated into navigation/ package with backward-compat shims**

## Performance

- **Duration:** 9 min
- **Started:** 2026-04-08T14:26:57Z
- **Completed:** 2026-04-08T14:36:00Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments
- Moved 6 existing navigation modules (aas_parser, navigator, learned_map, exit_finder, room_surveyor, commander) into navigation/ subdirectory
- Created NavBehavior extracting tick_navigating, tick_exploring, tick_door, tick_pickup from strategic_brain.py
- Created SurveyBehavior extracting tick_surveying with cooldown logic
- All 6 root files converted to thin re-export shims for backward compatibility
- Zero cross-subsystem imports (no reflexes/ or combat/ dependencies)
- All 52 characterization tests pass unchanged

## Task Commits

Each task was committed atomically:

1. **Task 1: Move 6 existing navigation modules into navigation/ and create shims** - `fb9eb8c` (feat)
2. **Task 2: Create NavBehavior and SurveyBehavior, finalize navigation/__init__.py** - `5c9f63f` (feat)

## Files Created/Modified
- `openarena_perception/navigation/aas_parser.py` - AAS nav mesh parser (moved from root)
- `openarena_perception/navigation/navigator.py` - A* pathfinding with viewpos tracking (moved, imports updated)
- `openarena_perception/navigation/learned_map.py` - Occupancy grid and edge failure tracking (moved)
- `openarena_perception/navigation/exit_finder.py` - Scan-and-probe stuck recovery (moved, imports updated)
- `openarena_perception/navigation/room_surveyor.py` - 360-degree LLM room documentation (moved, imports updated)
- `openarena_perception/navigation/commander.py` - Strategic item prioritization (moved)
- `openarena_perception/navigation/nav_behavior.py` - NavBehavior with 4 tick methods + 2 entry hooks
- `openarena_perception/navigation/survey_behavior.py` - SurveyBehavior with tick method
- `openarena_perception/navigation/__init__.py` - Package init re-exporting all 8 public symbols
- `openarena_perception/aas_parser.py` - Backward-compat shim
- `openarena_perception/navigator.py` - Backward-compat shim
- `openarena_perception/learned_map.py` - Backward-compat shim
- `openarena_perception/exit_finder.py` - Backward-compat shim
- `openarena_perception/room_surveyor.py` - Backward-compat shim
- `openarena_perception/commander.py` - Backward-compat shim

## Decisions Made
- Used TYPE_CHECKING imports for VirtualController and SpatialKnowledge in behavior modules (same pattern as reflexes/ and combat/)
- tick_navigating and tick_exploring accept tick_count as explicit parameter to avoid coupling NavBehavior to StrategicBrain._tick counter
- Exposed nav_target, target_blacklist, target_failures, stucks_on_current_target as properties on NavBehavior for integration with StrategicBrain's on_enter_state(STUCK) logic

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- navigation/ package complete with 9 modules, ready for Plan 04 (spatial_map, vision_nav extraction) and Plan 05 (NavigationSubsystem integration)
- Backward-compat shims ensure strategic_brain.py continues working without changes
- NavBehavior and SurveyBehavior ready to be wired into NavigationSubsystem in Plan 05

---
*Phase: 04-reflexes-combat-and-navigation-extraction*
*Completed: 2026-04-08*
