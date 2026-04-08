---
phase: 03-memory-and-persistence
plan: 01
subsystem: database
tags: [sqlite, sqlalchemy-core, alembic, wal-mode, schema-migrations]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: pydantic-settings BotSettings, uv package management, project structure
provides:
  - SQLAlchemy Core metadata with 4 table definitions (room_surveys, learned_maps, match_events, item_locations)
  - WAL-mode SQLite engine factory (create_database, get_engine)
  - BotSettings.db_path configuration field
  - Alembic migration infrastructure with initial migration 001
affects: [03-02, 03-03, 06-api-layer]

# Tech tracking
tech-stack:
  added: [sqlalchemy-2.0, aiosqlite-0.22, alembic-1.18]
  patterns: [sqlalchemy-core-tables, wal-mode-pragmas, engine-caching, alembic-settings-integration]

key-files:
  created:
    - openarena_perception/memory/schema.py
    - openarena_perception/memory/storage.py
    - alembic.ini
    - alembic/env.py
    - alembic/versions/001_initial_schema.py
  modified:
    - pyproject.toml
    - openarena_perception/settings.py

key-decisions:
  - "Used SQLAlchemy Core (not ORM) for lightweight table definitions on Pi hardware"
  - "Engine cache keyed by resolved absolute path prevents duplicate engines"
  - "Alembic env.py resolves db_path from BotSettings with fallback to alembic.ini URL"

patterns-established:
  - "SQLAlchemy Core tables defined in schema.py with shared metadata object"
  - "WAL mode + busy_timeout + cache_size PRAGMAs set via SQLAlchemy connect event listener"
  - "Manual Alembic migrations (not autogenerate) for explicit schema control"

requirements-completed: [MEM-01, MEM-05]

# Metrics
duration: 3min
completed: 2026-04-08
---

# Phase 03 Plan 01: SQLite Schema and Alembic Setup Summary

**SQLAlchemy Core schema with 4 memory tables, WAL-mode engine factory, and Alembic migration infrastructure**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-08T13:25:27Z
- **Completed:** 2026-04-08T13:28:14Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Defined 4 SQLAlchemy Core tables: room_surveys, learned_maps, match_events, item_locations with indexes and constraints
- Created WAL-mode engine factory with PRAGMA tuning (journal_mode=WAL, synchronous=NORMAL, cache_size=-8000, busy_timeout=5000)
- Added db_path to BotSettings with OA_DB_PATH env var override (default ~/.openarena/bot.db)
- Configured Alembic with initial migration 001 that creates all tables

## Task Commits

Each task was committed atomically:

1. **Task 1: Install deps, create schema.py and storage.py** - `396a49d` (feat)
2. **Task 2: Configure Alembic with initial migration** - `b5cc5e1` (feat)

## Files Created/Modified
- `openarena_perception/memory/schema.py` - SQLAlchemy Core table definitions with MetaData
- `openarena_perception/memory/storage.py` - Engine factory with WAL mode and caching
- `openarena_perception/settings.py` - Added db_path field to BotSettings
- `pyproject.toml` - Added aiosqlite, sqlalchemy, alembic dependencies
- `alembic.ini` - Alembic configuration with SQLite URL
- `alembic/env.py` - Custom env importing schema metadata and settings
- `alembic/versions/001_initial_schema.py` - Initial migration creating all 4 tables

## Decisions Made
- Used SQLAlchemy Core (not ORM) for lightweight table definitions -- matches research recommendation for Pi performance
- Engine cache uses resolved absolute path as key to prevent duplicate engines for same file
- Alembic env.py wraps settings import in try/except for robustness when running outside full environment

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Schema and storage foundation ready for 03-02 (semantic memory) and 03-03 (working/episodic memory)
- All 4 tables defined and migratable via `alembic upgrade head`
- Engine factory ready for use by memory subsystem modules

---
*Phase: 03-memory-and-persistence*
*Completed: 2026-04-08*
