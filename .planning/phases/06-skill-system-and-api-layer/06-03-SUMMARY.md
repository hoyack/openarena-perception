---
phase: 06-skill-system-and-api-layer
plan: 03
subsystem: api
tags: [fastapi, pydantic, rest, dependency-injection, httpx]

# Dependency graph
requires:
  - phase: 06-01
    provides: "Skill Protocol, SkillRegistry, AtomicAction, ComposedBehavior, Mission base classes"
provides:
  - "FastAPI app factory with create_app(), lifespan, CORS"
  - "BotState dependency injection (get_bot/set_bot)"
  - "Pydantic v2 request/response models for all endpoints"
  - "5 REST routers: perception, navigation, combat, skills, strategy"
  - "/health, /state/full, /docs top-level endpoints"
  - "18 API integration tests"
affects: [06-04, 06-05]

# Tech tracking
tech-stack:
  added: [fastapi, uvicorn, uvloop]
  patterns: [app-factory, dependency-injection, pydantic-from-sa, asyncio-run-test-wrapper]

key-files:
  created:
    - openarena_perception/api/app.py
    - openarena_perception/api/deps.py
    - openarena_perception/api/models.py
    - openarena_perception/api/routers/__init__.py
    - openarena_perception/api/routers/perception.py
    - openarena_perception/api/routers/navigation.py
    - openarena_perception/api/routers/combat.py
    - openarena_perception/api/routers/skills.py
    - openarena_perception/api/routers/strategy.py
    - tests/test_api.py
  modified:
    - openarena_perception/api/__init__.py
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Used set_bot() explicit call in test helper instead of relying on lifespan (httpx ASGITransport does not trigger lifespan automatically)"
  - "PerceptionStateResponse.from_sa() builds fields manually to avoid slow dataclasses.asdict()"
  - "BotState uses Any type hints to avoid import-time coupling with subsystem modules"
  - "Installed fastapi, uvicorn[standard], uvloop as project dependencies via uv add"

patterns-established:
  - "App factory: create_app(bot) returns configured FastAPI with all routers"
  - "Dependency injection: Depends(get_bot) in route handlers, set_bot() for test swapping"
  - "Test client: httpx AsyncClient + ASGITransport + asyncio.run() wrapper (project convention)"
  - "Pydantic from_sa: classmethod builds response model from frozen dataclass without asdict"

requirements-completed: [API-01, API-02, API-04]

# Metrics
duration: 3min
completed: 2026-04-09
---

# Phase 06 Plan 03: FastAPI REST API Summary

**FastAPI app with 20 routes across 5 routers (perception, navigation, combat, skills, strategy) plus Pydantic v2 typed request/response models and dependency-injected BotState**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-09T00:32:59Z
- **Completed:** 2026-04-09T00:36:15Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments
- FastAPI app factory with lifespan, CORS, and 5 domain routers producing 20 routes
- Full Pydantic v2 model coverage for all API contracts (13 models) with PerceptionStateResponse.from_sa() fast-path
- 18 passing integration tests covering every endpoint including 503/404 error cases and OpenAPI docs

## Task Commits

Each task was committed atomically:

1. **Task 1: Create API app factory, dependency injection, and Pydantic models** - `a362e97` (feat)
2. **Task 2: Implement all REST endpoint routers with tests** - `420a9c8` (test)

## Files Created/Modified
- `openarena_perception/api/app.py` - create_app() factory with lifespan, CORS, router includes, /health, /state/full
- `openarena_perception/api/deps.py` - BotState holder, get_bot/set_bot dependency injection
- `openarena_perception/api/models.py` - 13 Pydantic v2 request/response models
- `openarena_perception/api/__init__.py` - Re-exports create_app, BotState, get_bot
- `openarena_perception/api/routers/__init__.py` - Router package init
- `openarena_perception/api/routers/perception.py` - GET /state, /enemies, /hud
- `openarena_perception/api/routers/navigation.py` - POST /goto, GET /path, POST /explore
- `openarena_perception/api/routers/combat.py` - POST /engage, /disengage, /weapon
- `openarena_perception/api/routers/skills.py` - POST /execute, GET /catalog, GET /{name}
- `openarena_perception/api/routers/strategy.py` - GET /current, POST /override
- `tests/test_api.py` - 18 integration tests for all endpoints
- `pyproject.toml` - Added fastapi, uvicorn[standard], uvloop dependencies

## Decisions Made
- Used set_bot() explicit call in test helper instead of relying on lifespan (httpx ASGITransport does not trigger lifespan)
- PerceptionStateResponse.from_sa() builds fields manually to avoid slow dataclasses.asdict()
- BotState uses Any type hints with TYPE_CHECKING to avoid import-time coupling
- Installed fastapi>=0.115, uvicorn[standard]>=0.30, uvloop>=0.19 as runtime deps

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing fastapi/uvicorn/uvloop dependencies**
- **Found during:** Task 1 (app factory verification)
- **Issue:** fastapi not installed, import fails
- **Fix:** `uv add "fastapi>=0.115,<1.0" "uvicorn[standard]>=0.30" "uvloop>=0.19"`
- **Files modified:** pyproject.toml, uv.lock
- **Verification:** `uv run python -c "from openarena_perception.api import create_app"` succeeds
- **Committed in:** a362e97 (Task 1 commit)

**2. [Rule 1 - Bug] Fixed test client not triggering lifespan**
- **Found during:** Task 2 (TDD RED phase)
- **Issue:** httpx ASGITransport does not trigger FastAPI lifespan, so set_bot() was never called and Depends(get_bot) returned empty BotState
- **Fix:** Added explicit set_bot(b) call in test _client() helper before creating AsyncClient
- **Files modified:** tests/test_api.py
- **Verification:** All 18 tests pass
- **Committed in:** 420a9c8 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both fixes necessary for functionality. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- API layer complete with all 5 routers, ready for Plan 04 (WebSocket + Prometheus metrics mount)
- BotState dependency injection pattern established for future endpoints
- Test infrastructure (httpx AsyncClient + ASGITransport) ready for extension

---
*Phase: 06-skill-system-and-api-layer*
*Completed: 2026-04-09*
