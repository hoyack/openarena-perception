---
phase: 02-perception-extraction
plan: 02
subsystem: perception
tags: [opencv, pipeline, situational-awareness, rate-limiting, attention-priority]

# Dependency graph
requires:
  - phase: 02-perception-extraction plan 01
    provides: All 9 perception modules extracted into perception/ package with re-export stubs
provides:
  - PerceptionPipeline orchestrator class with tick() producing SituationalAwareness
  - build_situational_awareness() standalone mapping function
  - PerceptionPipelineConfig for tick-budget control
affects: [03-perception-testing, 04-combat-nav-reflexes, 05-strategy-extraction]

# Tech tracking
tech-stack:
  added: []
  patterns: [rate-limited perception pipeline, attention-based priority filtering, safe-call error isolation]

key-files:
  created:
    - openarena_perception/perception/pipeline.py
    - openarena_perception/perception/config.py
  modified:
    - openarena_perception/perception/__init__.py

key-decisions:
  - "MotionAnomalyTracker constructed with defaults (no BotSettings injection) -- keeps pipeline decoupled from settings"
  - "Exception isolation via _safe_call() around every detector -- pipeline never crashes on single detector failure"
  - "Death detection compares previous alive state to current -- resets ObjectTracker and MotionAnomalyTracker on transition"

patterns-established:
  - "Safe-call pattern: _safe_call(name, fn, *args) wraps each detector with try/except, logs errors, returns None on failure"
  - "Attention-based priority: combat state dynamically adjusts tracker_interval and anomaly_enabled per tick"
  - "Cached last-values: _last_hud, _last_tracked, _last_anomalies persist between rate-limited runs"

requirements-completed: [PERC-01, PERC-02, PERC-03, PERC-04, PERC-05, PERC-06, PERC-07]

# Metrics
duration: 3min
completed: 2026-04-08
---

# Phase 2 Plan 02: Perception Pipeline Summary

**PerceptionPipeline orchestrator wiring 8 sub-modules with rate-limited tick budgets, attention-based combat priority, and frozen SituationalAwareness output**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-08T12:46:29Z
- **Completed:** 2026-04-08T12:49:30Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- PerceptionPipeline.tick() orchestrates all 8 perception sub-modules (capture, HUD, world, wall, motion, player, tracker, anomaly) into a single frozen SituationalAwareness snapshot
- Rate-limiting prevents expensive operations from running every tick: HUD OCR every 30 ticks, motion/tracker every 2, anomaly every 3
- Attention-based priority adjusts rates during combat: tracker runs every tick, anomaly detection disabled
- Death detection triggers reset on stateful trackers (ObjectTracker, MotionAnomalyTracker)
- build_situational_awareness() correctly maps all detector outputs to the 30+ field frozen dataclass
- All 94 existing tests pass with new exports

## Task Commits

Each task was committed atomically:

1. **Task 1: Create PerceptionPipeline orchestrator and build_situational_awareness** - `f807367` (feat)
2. **Task 2: Update perception/__init__.py exports and verify tests** - `cb1769f` (feat)

## Files Created/Modified
- `openarena_perception/perception/pipeline.py` - PerceptionPipeline class and build_situational_awareness() function
- `openarena_perception/perception/config.py` - PerceptionPipelineConfig frozen dataclass with tick budget parameters
- `openarena_perception/perception/__init__.py` - Added pipeline exports to package public API

## Decisions Made
- MotionAnomalyTracker constructed with defaults rather than injecting BotSettings -- keeps the pipeline decoupled and testable without requiring full settings infrastructure
- Used _safe_call() pattern to wrap every detector invocation with exception isolation -- ensures a single detector failure never crashes the entire pipeline (mitigates T-02-02 DoS threat)
- Death detection uses state transition (was_alive -> not is_alive) rather than polling -- avoids repeated resets on consecutive dead ticks

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Pipeline is ready for testing in Phase 02 Plan 03 (perception tests)
- PerceptionPipeline can be imported and used by any consumer via `from openarena_perception.perception import PerceptionPipeline`
- All sub-modules are wired and rate-limited; integration testing should verify tick budget on Pi hardware

---
*Phase: 02-perception-extraction*
*Completed: 2026-04-08*
