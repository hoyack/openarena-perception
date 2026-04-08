---
phase: 04-reflexes-combat-and-navigation-extraction
plan: 02
subsystem: combat
tags: [weapon-selection, pid-aim, combat-movement, threat-assessment, subsumption]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: characterization tests, combat/__init__.py stub with importlib hack
  - phase: 04-01
    provides: reflexes/ subsystem with SubsumptionArbiter, TYPE_CHECKING import pattern
provides:
  - combat/weapons.py with WeaponInfo dataclass and WEAPONS dict
  - combat/weapon_select.py with fuzzy selection, aim_lead, preemptive switch
  - combat/aim_controller.py with PID AimController and weapon profiles
  - combat/combat_movement.py with CombatMover circle strafe and dodge
  - combat/engage.py with CombatEngager tick/on_enter/on_exit
  - combat/threat_assess.py with ThreatAssessor evaluate and should_disengage
  - Backward-compatible shims at root combat.py and aim_controller.py
affects: [04-03-navigation, 05-tactics, strategic_brain]

# Tech tracking
tech-stack:
  added: []
  patterns: [TYPE_CHECKING imports for brainstem deps, re-export shim pattern]

key-files:
  created:
    - openarena_perception/combat/weapons.py
    - openarena_perception/combat/weapon_select.py
    - openarena_perception/combat/aim_controller.py
    - openarena_perception/combat/combat_movement.py
    - openarena_perception/combat/engage.py
    - openarena_perception/combat/threat_assess.py
  modified:
    - openarena_perception/combat/__init__.py
    - openarena_perception/combat.py
    - openarena_perception/aim_controller.py

key-decisions:
  - "Moved evaluate_threat to threat_assess.py in Task 1 (not Task 2) so root combat.py shim works immediately"
  - "Used TYPE_CHECKING imports for GameBridge/VirtualController to avoid import-time coupling (same pattern as 04-01)"
  - "ThreatAssessor.should_disengage parses nearest_enemy_distance string field with category-to-float mapping"

patterns-established:
  - "Combat subpackage re-export: all 11 public symbols available from openarena_perception.combat"
  - "Root-level shim files: thin re-exports replacing importlib hacks for backward compat"

requirements-completed: [CMBT-01, CMBT-02, CMBT-03, CMBT-04, CMBT-05, CMBT-06, CMBT-07]

# Metrics
duration: 4min
completed: 2026-04-08
---

# Phase 4 Plan 2: Combat Subsystem Extraction Summary

**Combat subsystem consolidated into 6 modules under combat/ with fuzzy weapon selection, PID aim, engagement logic, and threat assessment -- all backward-compatible via root shims**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-08T14:20:17Z
- **Completed:** 2026-04-08T14:24:57Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Split root combat.py (232 lines) into 4 focused modules: weapons, weapon_select, combat_movement, threat_assess
- Moved root aim_controller.py (263 lines) into combat/aim_controller.py with full PID system
- Created CombatEngager with obstacle avoidance (NAV-05) and target snap (CMBT-01)
- Created ThreatAssessor with should_disengage for fight-or-flight decisions (CMBT-05)
- Added should_preemptive_switch for low-ammo weapon switching (CMBT-06)
- Replaced importlib hack in combat/__init__.py with clean re-exports
- All 52 characterization tests pass throughout

## Task Commits

Each task was committed atomically:

1. **Task 1: Move existing combat modules into combat/ subpackage** - `620c60b` (feat)
2. **Task 2: Create CombatEngager and ThreatAssessor, finalize combat/__init__.py** - `9228359` (feat)

## Files Created/Modified
- `openarena_perception/combat/weapons.py` - WeaponInfo dataclass and WEAPONS dict (pure data)
- `openarena_perception/combat/weapon_select.py` - Fuzzy weapon selection, aim_lead, preemptive switch
- `openarena_perception/combat/aim_controller.py` - PID aim controller with weapon profiles
- `openarena_perception/combat/combat_movement.py` - CombatMover circle strafe and dodge patterns
- `openarena_perception/combat/engage.py` - CombatEngager with tick/on_enter/on_exit from _tick_combat
- `openarena_perception/combat/threat_assess.py` - evaluate_threat + ThreatAssessor with should_disengage
- `openarena_perception/combat/__init__.py` - Clean re-exports of all 11 public symbols (replaced importlib hack)
- `openarena_perception/combat.py` - Backward-compat re-export shim (replaced 232-line module)
- `openarena_perception/aim_controller.py` - Backward-compat re-export shim (replaced 263-line module)

## Decisions Made
- Moved evaluate_threat to threat_assess.py in Task 1 so root combat.py shim could import it immediately, then added ThreatAssessor class wrapper in Task 2
- Used TYPE_CHECKING imports for GameBridge and VirtualController in engage.py (same pattern proven in 04-01 reflexes extraction)
- ThreatAssessor.should_disengage parses nearest_enemy_distance string with category-to-float mapping since SituationalAwareness stores it as Optional[str]

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created evaluate_threat in threat_assess.py during Task 1**
- **Found during:** Task 1 (root combat.py shim creation)
- **Issue:** Plan's combat.py shim imports from threat_assess.evaluate_threat, but threat_assess.py was planned for Task 2
- **Fix:** Moved evaluate_threat() to threat_assess.py as part of Task 1, then added ThreatAssessor class in Task 2
- **Files modified:** openarena_perception/combat/threat_assess.py
- **Verification:** All imports succeed, characterization tests pass
- **Committed in:** 620c60b (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary reordering to avoid circular dependency. No scope change.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Combat subsystem fully consolidated in combat/ package
- Ready for 04-03 navigation extraction (no cross-dependencies)
- strategic_brain.py can wire CombatEngager.tick into its dispatch table in Phase 5

---
*Phase: 04-reflexes-combat-and-navigation-extraction*
*Completed: 2026-04-08*
