---
phase: 01-foundation-and-characterization
plan: 05
subsystem: infra
tags: [cleanup, gitignore, deduplication, testing]

# Dependency graph
requires:
  - phase: 01-foundation-and-characterization (plans 01-04)
    provides: package structure, brain directories, entry points using openarena_perception imports
provides:
  - Clean root directory with no duplicate .py files between root and openarena_perception/
  - .gitignore covering .env, __pycache__, build artifacts
  - Regression test preventing future root/package duplication
affects: [all future phases - clean file structure prevents import confusion]

# Tech tracking
tech-stack:
  added: []
  patterns: [single-source-of-truth for package modules, entry-point scripts at root only]

key-files:
  created:
    - .gitignore
    - tests/test_no_duplicates.py
  modified: []

key-decisions:
  - "Package versions of all 6 duplicated files are canonical; root copies deleted"
  - "Root config.py had divergent values (ENEMY_MIN_AREA=200 vs 300, enemy_scan ROI y=0.08 vs 0.05) and more comments; package version preferred as play.py already uses it"
  - "roi_debugger.py kept at root per plan scope (identical to tools/ copy but listed as entry-point to preserve)"

patterns-established:
  - "No .py file should exist in both project root and openarena_perception/ package"
  - "Root-level .py files are entry-point scripts only"

requirements-completed: [FOUND-02]

# Metrics
duration: 2min
completed: 2026-04-08
---

# Phase 01 Plan 05: Duplicate Resolution Summary

**Removed 6 duplicate root-level Python scripts, added .gitignore with .env protection, and regression test preventing future duplication**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-08T12:09:10Z
- **Completed:** 2026-04-08T12:11:20Z
- **Tasks:** 2
- **Files modified:** 2 created, 6 deleted

## Accomplishments
- Deleted 6 root-level duplicate scripts (config.py, capture.py, loop.py, hud_parser.py, game_state.py, world_parser.py) that duplicated openarena_perception/ package modules
- Created .gitignore with .env, __pycache__/, *.pyc, *.pkl, build artifacts, and tool caches
- Added test_no_duplicates.py with 4 tests: no root/package overlap, entry points preserved, .gitignore coverage
- Full test suite (94 tests) passes green

## Task Commits

Each task was committed atomically:

1. **Task 1: Audit and remove duplicate root-level scripts** - `c1a9bd0` (chore)
2. **Task 2: Write test verifying no duplicate files** - `5776d8a` (test)

## Files Created/Modified
- `.gitignore` - New file: .env, __pycache__/, build artifacts, tool caches
- `tests/test_no_duplicates.py` - 4 tests verifying no root/package duplication and .gitignore completeness
- `config.py` (DELETED) - Root duplicate, package version canonical (had divergent ROI values)
- `capture.py` (DELETED) - Root duplicate, package version newer (244 vs 238 lines)
- `loop.py` (DELETED) - Root duplicate, package version newer (236 vs 222 lines)
- `hud_parser.py` (DELETED) - Root duplicate, identical to package (219 lines)
- `game_state.py` (DELETED) - Root duplicate, identical to package (138 lines)
- `world_parser.py` (DELETED) - Root duplicate, identical to package (225 lines)

## Decisions Made
- Package versions are canonical for all 6 files; root config.py had more comments and slightly different tuning values (ENEMY_MIN_AREA=200 vs 300, enemy_scan ROI y range) but play.py already uses the package version
- The 3 identical files (hud_parser.py, game_state.py, world_parser.py) were simple deletions with no divergence

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- The 6 duplicate files were never tracked by git (repo was initialized with only .planning/ and tests/), so deletions are filesystem-only operations. The .gitignore creation is the tracked artifact.

## Known Stubs

None.

## Next Phase Readiness
- Phase 01 (Foundation and Characterization) is now complete with all 5 plans executed
- Clean package structure ready for Phase 02 extraction work
- All 94 tests passing as regression safety net

---
*Phase: 01-foundation-and-characterization*
*Completed: 2026-04-08*
