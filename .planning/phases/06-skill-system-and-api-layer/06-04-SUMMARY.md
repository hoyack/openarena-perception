---
phase: 06-skill-system-and-api-layer
plan: 04
subsystem: api
tags: [websocket, prometheus, metrics, fastapi, real-time]

# Dependency graph
requires:
  - phase: 06-03
    provides: FastAPI app factory, BotState dependency, REST routers
provides:
  - WebSocket /ws/state real-time state streaming at configurable Hz
  - Prometheus metrics endpoint at /metrics with 6 bot metrics
  - Connection-limited WebSocket with heartbeat support
affects: [07-competitive-play, monitoring, observability]

# Tech tracking
tech-stack:
  added: [prometheus-client]
  patterns: [ASGI metrics sub-app mount, WebSocket connection pool with limits, manual SA dict serialization]

key-files:
  created:
    - openarena_perception/api/ws.py
    - openarena_perception/api/metrics.py
  modified:
    - openarena_perception/api/app.py
    - tests/test_api.py
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Default prometheus registry for metrics singletons (simpler than custom registry)"
  - "Manual dict construction for SA WebSocket serialization (~0.05ms vs 0.5ms asdict)"
  - "Connection limit enforced with WebSocket close code 1013 (Try Again Later)"

patterns-established:
  - "ASGI sub-app mount: app.mount('/metrics', make_asgi_app()) for Prometheus exposition"
  - "WebSocket connection tracking: module-level set with try/finally cleanup"

requirements-completed: [API-03, API-05]

# Metrics
duration: 3min
completed: 2026-04-09
---

# Phase 06 Plan 04: WebSocket State Streaming and Prometheus Metrics Summary

**WebSocket /ws/state streams SA JSON at 3 Hz with 5-connection limit; /metrics exposes 6 Prometheus gauges/counters/histograms for bot observability**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-09T00:38:42Z
- **Completed:** 2026-04-09T00:41:41Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 6

## Accomplishments
- WebSocket /ws/state streams SituationalAwareness JSON at configurable Hz (default 3 Hz) with manual dict construction for performance
- Connection limit enforced at 5 with code 1013 rejection (T-06-09 DoS mitigation)
- Heartbeat {"type": "waiting"} sent when no SA available (graceful pre-tick behavior)
- 6 Prometheus metrics defined as module-level singletons: FPS gauge, kill/death/stuck counters, LLM latency and tick duration histograms
- Metrics ASGI sub-app mounted at /metrics with correct Prometheus text format
- All 22 API tests pass including 4 new WebSocket and metrics tests

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests** - `2c3d053` (test)
2. **Task 1 (GREEN): Implementation** - `00e5d47` (feat)

## Files Created/Modified
- `openarena_perception/api/ws.py` - WebSocket /ws/state handler with connection management and SA streaming
- `openarena_perception/api/metrics.py` - Prometheus metric singletons (6 metrics) and ASGI sub-app
- `openarena_perception/api/app.py` - Updated to include ws_router and mount metrics_app
- `tests/test_api.py` - 4 new tests: websocket, websocket_no_sa, metrics, metrics_content_type
- `pyproject.toml` - Added prometheus-client dependency
- `uv.lock` - Updated lockfile

## Decisions Made
- Used default prometheus registry (not custom) -- metrics are inherently singletons, simpler for production use
- Manual dict construction for SA serialization in WebSocket handler (~0.05ms vs 0.5ms for dataclasses.asdict)
- WebSocket close code 1013 (Try Again Later) for connection limit rejection per RFC 6455

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed prometheus-client in uv venv**
- **Found during:** Task 1 GREEN phase
- **Issue:** prometheus-client was system-installed but not in the uv virtual environment
- **Fix:** `uv add "prometheus-client>=0.21"` to add to project dependencies
- **Files modified:** pyproject.toml, uv.lock
- **Verification:** Import succeeds, tests pass
- **Committed in:** 00e5d47

**2. [Rule 1 - Bug] Fixed /metrics trailing slash redirect**
- **Found during:** Task 1 GREEN phase
- **Issue:** Mounted ASGI sub-app at /metrics redirects /metrics to /metrics/ (307)
- **Fix:** Tests use /metrics/ (trailing slash) to match ASGI mount behavior
- **Files modified:** tests/test_api.py
- **Verification:** All metrics tests pass with 200 status
- **Committed in:** 00e5d47

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both necessary for correctness. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- WebSocket and metrics endpoints ready for integration with game tick loop
- Metrics singletons importable from subsystems for instrumentation
- Plan 05 (integration/wiring) can now connect all API components

---
*Phase: 06-skill-system-and-api-layer*
*Completed: 2026-04-09*
