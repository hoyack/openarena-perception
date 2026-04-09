---
phase: "06"
plan: "02"
subsystem: skills
tags: [behaviors, missions, catalog, composability, skill-system]
dependency_graph:
  requires: [06-01]
  provides: [behaviors, missions, catalog, SKILL.md]
  affects: [api-layer, llm-agent-control]
tech_stack:
  added: []
  patterns: [thin-wrapper-composition, async-cancellation, param-clamping]
key_files:
  created:
    - openarena_perception/skills/behaviors.py
    - openarena_perception/skills/missions.py
    - openarena_perception/skills/catalog.py
    - openarena_perception/skills/SKILL.md
  modified:
    - openarena_perception/skills/__init__.py
    - tests/test_skills.py
decisions:
  - "Behaviors are thin wrappers over atomic actions with async interface + cancellation"
  - "CombatEngageBehavior awaits engager.tick directly (async method)"
  - "Mission params clamped to sensible ranges (T-06-03: max_steps<=100, rounds<=50)"
  - "All mission loops check _cancelled flag with max iteration limits (T-06-04)"
metrics:
  duration: "5min"
  completed: "2026-04-09"
  tasks: 2
  files: 6
---

# Phase 06 Plan 02: Behaviors, Missions, Catalog Summary

Three-layer skill composability chain completed: 4 actions + 3 behaviors + 3 missions registered via build_registry() factory, with param clamping (T-06-03) and cancellation guards (T-06-04).

## What Was Built

### Task 1: Behavior Layer (behaviors.py)
- **PatrolBehavior**: Sequences MoveAction + TurnAction for each waypoint with cancellation between steps
- **RoomSurveyBehavior**: 4x 90-degree turns with optional SurveyBehavior delegation via asyncio.to_thread
- **CombatEngageBehavior**: Delegates to CombatEngager.tick (async) for combat execution
- All behaviors satisfy Skill Protocol (isinstance check), layer=BEHAVIOR
- Each behavior class under 40 lines

### Task 2: Mission Layer + Catalog + SKILL.md
- **ExploreMapMission**: Repeated PatrolBehavior with max_steps clamped to 1-100
- **DeathmatchMission**: Alternates patrol/combat based on enemies_visible, rounds clamped to 1-50
- **DefendAreaMission**: Localized patrol with area_id parameter
- **build_registry()**: Factory creating SkillRegistry with all 10 skills (4 actions + 3 behaviors + 3 missions)
- **SKILL.md**: Migrated to skills/ with three-layer hierarchy documentation header + original game-specific content
- **__init__.py**: Updated to export all behaviors, missions, and build_registry

## Threat Mitigations Applied

| Threat ID | Mitigation |
|-----------|-----------|
| T-06-03 | max_steps clamped <=100, rounds <=50, area_id cast to int |
| T-06-04 | All mission loops check _cancelled between iterations; max iteration limits prevent infinite loops |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CombatEngager.tick is async, needs AsyncMock in test**
- **Found during:** Task 1
- **Issue:** CombatEngager.tick() is `async def`, so MagicMock() cannot be awaited
- **Fix:** Changed test to use AsyncMock for engager.tick
- **Files modified:** tests/test_skills.py

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 (RED) | 7ea1f4d | Failing tests for behavior layer |
| 1 (GREEN) | d4a564d | Implement behavior layer composing actions |
| 2 (RED) | 64ce34d | Failing tests for missions, catalog, SKILL.md |
| 2 (GREEN) | 5b63a22 | Implement missions, catalog, migrate SKILL.md |

## Verification Results

```
$ uv run python -m pytest tests/test_skills.py -x -q
26 passed in 14.46s

$ uv run python -c "from openarena_perception.skills.catalog import build_registry; print('catalog OK')"
catalog OK

$ test -f openarena_perception/skills/SKILL.md
SKILL.md EXISTS
```

## Self-Check: PASSED
