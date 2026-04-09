---
phase: 07-competitive-features
plan: 02
subsystem: perception, tactics
tags: [sound-awareness, spawn-prediction, item-timing, pipeline-integration]
dependency_graph:
  requires: [07-01]
  provides: [PERC-08-complete, COMP-02-complete]
  affects: [models, pipeline, commander, settings]
tech_stack:
  added: []
  patterns: [TYPE_CHECKING-import, rate-limited-polling, optional-dependency-injection]
key_files:
  created: []
  modified:
    - openarena_perception/models.py
    - openarena_perception/perception/pipeline.py
    - openarena_perception/perception/config.py
    - openarena_perception/settings.py
    - openarena_perception/tactics/commander.py
    - tests/test_models.py
    - tests/test_item_timing.py
decisions:
  - "TYPE_CHECKING import for ConsoleLogParser in pipeline (project convention from Phase 4)"
  - "Sound fields use defaults on SA so existing construction sites don't break"
  - "Commander accepts item_timing as optional kwarg -- zero-impact when absent"
  - "RESPAWN_MEGA corrected from 120.0 to 35.0 per Q3 source RESPAWN_MEGAHEALTH"
metrics:
  duration: 5min
  completed: 2026-04-09
  tasks: 2
  files: 7
---

# Phase 07 Plan 02: Wire Sound Parser + Spawn Prediction Integration Summary

Sound parser wired into perception pipeline with rate-limited polling and 4 SA fields; Commander enhanced with ItemTimingService for spawn-aware item scoring and RESPAWN_MEGA bug fix.

## What Was Done

### Task 1: Extend SituationalAwareness and Wire ConsoleLogParser into Pipeline (PERC-08)

Added 4 sound awareness fields to the frozen SituationalAwareness dataclass with defaults: `sound_events_recent`, `sound_nearby_combat`, `sound_last_pickup_item`, `sound_last_kill_victim`. Added `game_log_path` and `sound_poll_interval` to BotSettings. Added `sound_poll_interval` to PerceptionPipelineConfig. Modified PerceptionPipeline to accept an optional ConsoleLogParser via `sound_parser` kwarg (using TYPE_CHECKING import). Added rate-limited sound polling step (h2) between anomaly detection and death reset. Updated `build_situational_awareness` to derive sound fields from GameEvent list.

**Commit:** 808e139

### Task 2: Integrate ItemTimingService into Commander (COMP-02) [TDD]

**RED:** Wrote 8 new test methods across 5 test classes verifying RESPAWN_MEGA correction, timing-based scoring penalties/boosts, backward compatibility without item_timing, and process_sound_events event forwarding.

**GREEN:** Fixed RESPAWN_MEGA from 120.0 to 35.0 per Q3 source. Added optional `item_timing` parameter to Commander.__init__. Added spawn-prediction scoring in `_find_best_item`: items >5s from spawn get 0.05 penalty, items within 5s get travel-time-matched boost. Added `process_sound_events` method for pipeline to feed events.

**Commits:** e01d764 (RED), afdaac4 (GREEN)

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

77 tests pass across 4 test files:
- tests/test_perception_pipeline.py: 16 passed
- tests/test_models.py: 8 passed
- tests/test_item_timing.py: 34 passed
- tests/test_commander_tactics.py: 19 passed

## Key Decisions

1. **TYPE_CHECKING import for ConsoleLogParser** -- follows project convention from Phase 4 to avoid import-time coupling
2. **Sound fields default to zero/False/None** -- existing SA construction sites continue working without change
3. **Commander item_timing is optional kwarg** -- zero behavior change when not provided, backward compatible
4. **RESPAWN_MEGA = 35.0** -- corrected from 120.0 per verified Q3 source g_items.c RESPAWN_MEGAHEALTH constant

## Self-Check: PASSED

All 5 modified files verified on disk. All 3 commit hashes found in git log.
