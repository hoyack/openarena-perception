---
phase: 01-foundation-and-characterization
plan: 01
subsystem: infra
tags: [uv, ruff, pytest, pyproject, lockfile]

# Dependency graph
requires: []
provides:
  - "pyproject.toml with all runtime and dev dependencies"
  - "uv.lock for reproducible builds"
  - "ruff linter/formatter configuration"
  - "pytest configuration with test directory scaffold"
  - "Shared test fixtures (mock_navigator, mock_bridge, mock_commander, etc.)"
affects: [01-02, 01-03, 01-04, 01-05, all-future-phases]

# Tech tracking
tech-stack:
  added: [uv, ruff, pytest, pytest-cov, pydantic-settings, structlog]
  patterns: ["uv run for all tool invocations", "dev dependencies in dependency-groups"]

key-files:
  created: [pyproject.toml, uv.lock, tests/__init__.py, tests/conftest.py]
  modified: []

key-decisions:
  - "Used uv add --dev which creates [dependency-groups] instead of [project.optional-dependencies]"
  - "Kept requirements.txt as reference, uv.lock is new source of truth"
  - "Removed uv init artifact main.py"

patterns-established:
  - "uv run pytest for test execution"
  - "uv run ruff for linting and formatting"
  - "Mock fixtures in tests/conftest.py for all major subsystems"

requirements-completed: [FOUND-05, FOUND-06]

# Metrics
duration: 2min
completed: 2026-04-08
---

# Phase 01 Plan 01: Project Tooling Foundation Summary

**uv project with pyproject.toml, ruff linter, pytest framework, and shared test fixtures for all subsystems**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-08T11:48:52Z
- **Completed:** 2026-04-08T11:50:58Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Migrated all dependencies from requirements.txt to pyproject.toml with updated version pins
- Configured ruff (py311 target, E/F/W/I/N/UP/B rules) and pytest (testpaths, verbose output)
- Created test scaffold with 6 shared mock fixtures for major subsystems
- Generated uv.lock (172KB) for reproducible builds

## Task Commits

Each task was committed atomically:

1. **Task 1: Initialize uv project and migrate dependencies** - `f3726ca` (feat)
2. **Task 2: Create test directory scaffold** - `acf9c9e` (feat)

## Files Created/Modified
- `pyproject.toml` - Project metadata, all dependencies, ruff and pytest configuration
- `uv.lock` - Locked dependency versions for reproducible builds
- `tests/__init__.py` - Test package marker
- `tests/conftest.py` - Shared fixtures: mock_navigator, mock_bridge, mock_commander, mock_perception, mock_damage_tracker, mock_ctrl

## Decisions Made
- uv add --dev creates a `[dependency-groups]` section rather than populating `[project.optional-dependencies]` -- this is the modern uv convention and was accepted
- Kept requirements.txt intact as reference per plan instruction
- Removed auto-generated main.py from uv init (boilerplate, not needed)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Removed uv init artifact main.py**
- **Found during:** Task 1
- **Issue:** `uv init` created a boilerplate main.py with hello-world code
- **Fix:** Deleted the file before committing
- **Files modified:** main.py (deleted)
- **Verification:** File no longer exists
- **Committed in:** Not committed (deleted before staging)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Trivial cleanup of auto-generated artifact. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- uv, ruff, and pytest are fully operational via `uv run`
- Test fixtures ready for characterization tests in Plan 02+
- 69 existing ruff findings in codebase (pre-existing, not introduced by this plan) -- available for future cleanup

---
*Phase: 01-foundation-and-characterization*
*Completed: 2026-04-08*
