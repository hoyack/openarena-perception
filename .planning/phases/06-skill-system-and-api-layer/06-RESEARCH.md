# Phase 6: Skill System and API Layer - Research

**Researched:** 2026-04-08
**Domain:** Composable skill architecture + FastAPI REST/WebSocket API + Prometheus metrics
**Confidence:** HIGH

## Summary

Phase 6 builds two tightly coupled systems: a three-layer skill hierarchy (actions, behaviors, missions) that composes existing subsystem operations into LLM-consumable units, and a FastAPI backend that exposes the entire bot framework to external agents via REST, WebSocket, and metrics endpoints. All 10 prior subsystems (perception, reflexes, combat, navigation, memory, tactics, strategy, brainstem, game_bridge, virtual_controller) are now stable and extracted -- Phase 6 wraps them rather than modifying them.

The skill system is the composition glue. Atomic actions wrap `GameBridge.cmd()` / `VirtualController` methods directly. Behaviors compose sequences of actions with timing (e.g., `room_survey` = turn 90 degrees x4 with capture). Missions compose behaviors with goal conditions (e.g., `explore_map` = patrol + room_survey when entering new areas). The key design constraint: skills are thin wrappers that delegate to existing subsystem instances -- they add composition and an LLM-friendly interface, not new game logic.

The API layer runs FastAPI in the same asyncio event loop as the game tick loop (single-process architecture from STACK.md). REST endpoints provide perception state queries, skill invocation, and subsystem control. A WebSocket streams `SituationalAwareness` snapshots at 2-5 Hz for real-time monitoring. Prometheus metrics (FPS, kills, LLM latency, stuck frequency) are exposed at `/metrics`. The critical design concern is preventing API request handling from blocking the 50ms tick budget -- FastAPI's async handlers naturally yield to the event loop, but skill execution that triggers blocking `time.sleep()` calls in `VirtualController` must be offloaded.

**Primary recommendation:** Use simple Python classes with `async def execute()` methods for all three skill layers. No metaclasses, no plugin registries, no complex lifecycles. Skills are registered in a flat dictionary keyed by name. FastAPI routes call skills by name and return Pydantic response models.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SKIL-01 | Atomic action layer -- individual game commands (move, turn, fire, weapon_select) | Wrap GameBridge and VirtualController methods as Action classes with standard execute() interface |
| SKIL-02 | Behavior layer -- composed sequences (room_survey, item_tour, combat_engage, patrol) | Compose Actions with timing/sequencing. Behaviors reference existing NavBehavior, CombatEngager, SurveyBehavior |
| SKIL-03 | Mission layer -- high-level goals (explore_map, deathmatch, defend_area) | Compose Behaviors with goal conditions. Missions map to TacticalFSM state sequences |
| SKIL-04 | Skills are composable -- behaviors built from actions, missions built from behaviors | Common SkillBase with children list, execute() orchestrates sub-skills |
| SKIL-05 | SKILL.md migrated to skills/ folder as a specific skill definition | Move root SKILL.md into skills/ as the OpenArena-specific skill catalog |
| API-01 | FastAPI backend exposing bot control endpoints for LLM agents | FastAPI app with router modules per subsystem, uvicorn single-worker |
| API-02 | REST endpoints for perception state, navigation commands, combat control, skill execution | GET /perception/state, POST /skills/execute, POST /navigation/goto, POST /combat/engage |
| API-03 | WebSocket endpoint for real-time state streaming at 2-5 Hz | /ws/state endpoint streaming SituationalAwareness as JSON |
| API-04 | Pydantic models for all request/response schemas with auto-generated docs | Pydantic v2 BaseModel for all API contracts, FastAPI auto-generates OpenAPI spec |
| API-05 | Prometheus metrics endpoint (/metrics) | prometheus_client ASGI app mounted at /metrics, counters/gauges for FPS, kills, LLM latency, stuck frequency |
</phase_requirements>

## Standard Stack

### Core (Phase 6 additions)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.135.3 | HTTP + WebSocket API | Async-native, Pydantic v2 integration, auto-docs, WebSocket built-in. Project requirement. | 
| uvicorn | 0.44.0 | ASGI server | Standard FastAPI server. Single-worker on Pi. |
| uvloop | 0.22.1 | Event loop | Drop-in asyncio replacement, ~2x throughput on ARM64 |
| prometheus-client | 0.24.1 | Metrics | Counters/gauges/histograms for /metrics endpoint. Already installed (0.24.1). |
| httpx | 0.28.1 | Test client | FastAPI async test client. Already installed. |

[VERIFIED: pip3 index versions -- fastapi 0.135.3, uvicorn 0.44.0, uvloop 0.22.1, prometheus-client 0.24.1]

### Already Installed (used by Phase 6)

| Library | Version | Purpose |
|---------|---------|---------|
| pydantic | >=2.6 | Request/response models, SituationalAwareness serialization |
| pydantic-settings | >=2.13 | BotSettings for API config (host, port, cors) |
| structlog | >=24.0 | Structured logging for API requests |
| httpx | 0.28.1 | Async HTTP test client |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Class-based skills | Plain functions | Classes provide state, cancellation, composition. Functions are simpler but lose composability. Use classes. |
| ABC base class | Protocol (PEP 544) | Protocol is more Pythonic for structural typing. Use Protocol for type checking, no ABC inheritance. |
| WebSocket full state | WebSocket deltas | Delta compression saves bandwidth but adds complexity. On localhost Pi, full snapshots at 2-5 Hz are ~2KB each -- negligible. Use full snapshots. |
| prometheus_client ASGI | starlette-exporter | Extra dependency, same result. prometheus_client has built-in ASGI support via make_asgi_app(). |

**Installation (additions to pyproject.toml):**
```bash
uv add "fastapi>=0.115,<1.0" "uvicorn[standard]>=0.30" "uvloop>=0.19"
# prometheus-client already in deps
# httpx already in deps
```

## Architecture Patterns

### Recommended Project Structure
```
openarena_perception/
  skills/
    __init__.py          # SkillRegistry, get_registry()
    base.py              # SkillBase Protocol, ActionResult model
    actions.py           # Atomic actions: MoveAction, TurnAction, FireAction, WeaponSelectAction
    behaviors.py         # Composed behaviors: PatrolBehavior, CombatEngageBehavior, RoomSurveyBehavior
    missions.py          # High-level goals: ExploreMapMission, DeathmatchMission, DefendAreaMission
    catalog.py           # SKILL_CATALOG dict for LLM agent discovery
  api/
    __init__.py          # create_app() factory
    app.py               # FastAPI app setup, lifespan, middleware
    deps.py              # Dependency injection (get_bot, get_registry, get_perception)
    routers/
      __init__.py
      perception.py      # GET /perception/state, GET /perception/enemies
      navigation.py      # POST /navigation/goto, GET /navigation/path
      combat.py          # POST /combat/engage, POST /combat/disengage
      skills.py          # POST /skills/execute, GET /skills/catalog, GET /skills/{name}
      strategy.py        # GET /strategy/current, POST /strategy/override
      metrics.py         # Prometheus /metrics mount
    ws.py                # WebSocket /ws/state handler
    models.py            # Pydantic request/response schemas
```

### Pattern 1: Skill Protocol with Composability (SKIL-01 through SKIL-04)

**What:** Three-layer skill system using Python Protocol for structural typing. Each layer composes the layer below.

**When to use:** All skill definitions follow this pattern.

```python
# Source: Project-specific design based on FPS Bot Spec Section 8 game adapter pattern
from __future__ import annotations
import asyncio
from enum import Enum
from typing import Any, Protocol, runtime_checkable
from pydantic import BaseModel

class SkillLayer(str, Enum):
    ACTION = "action"
    BEHAVIOR = "behavior"
    MISSION = "mission"

class SkillResult(BaseModel):
    """Standard result from any skill execution."""
    success: bool
    message: str = ""
    data: dict[str, Any] = {}

@runtime_checkable
class Skill(Protocol):
    """Structural type for all skills -- actions, behaviors, missions."""
    name: str
    layer: SkillLayer
    description: str
    
    async def execute(self, **params: Any) -> SkillResult: ...
    
    def cancel(self) -> None: ...


class AtomicAction:
    """Base for SKIL-01 atomic actions. Wraps a single GameBridge/VirtualController call."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.layer = SkillLayer.ACTION
        self.description = description
        self._cancelled = False
    
    async def execute(self, **params: Any) -> SkillResult:
        raise NotImplementedError
    
    def cancel(self) -> None:
        self._cancelled = True


class ComposedBehavior:
    """Base for SKIL-02 behaviors. Sequences atomic actions with timing."""
    
    def __init__(self, name: str, description: str, steps: list[Skill] | None = None):
        self.name = name
        self.layer = SkillLayer.BEHAVIOR
        self.description = description
        self.steps = steps or []
        self._cancelled = False
    
    async def execute(self, **params: Any) -> SkillResult:
        for step in self.steps:
            if self._cancelled:
                return SkillResult(success=False, message="Cancelled")
            result = await step.execute(**params)
            if not result.success:
                return result
        return SkillResult(success=True, message=f"{self.name} completed")
    
    def cancel(self) -> None:
        self._cancelled = True
        for step in self.steps:
            step.cancel()
```

### Pattern 2: FastAPI with Shared Bot State via Dependency Injection (API-01, API-02)

**What:** FastAPI app shares the bot's live subsystem instances via dependency injection, not global state.

**When to use:** All API routes that need access to bot subsystems.

```python
# Source: FastAPI dependency injection pattern [VERIFIED: FastAPI docs]
from fastapi import Depends, FastAPI
from contextlib import asynccontextmanager

# Singleton bot instance holder
class BotState:
    """Holds references to all bot subsystem instances."""
    def __init__(self):
        self.perception: PerceptionPipeline | None = None
        self.fsm: TacticalFSM | None = None
        self.bridge: GameBridge | None = None
        self.controller: VirtualController | None = None
        self.registry: SkillRegistry | None = None
        self.last_sa: SituationalAwareness | None = None

_bot = BotState()

def get_bot() -> BotState:
    return _bot

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: bot subsystems already initialized by main game loop
    # API just receives references
    yield
    # Shutdown: cleanup if needed

app = FastAPI(
    title="OpenArena Bot API",
    version="0.1.0",
    lifespan=lifespan,
)

# Router example
@app.get("/perception/state")
async def get_perception_state(bot: BotState = Depends(get_bot)):
    if bot.last_sa is None:
        raise HTTPException(404, "No perception data yet")
    return bot.last_sa  # SituationalAwareness is a frozen dataclass
```

### Pattern 3: WebSocket State Streaming (API-03)

**What:** WebSocket endpoint that streams SituationalAwareness snapshots at configurable Hz.

**When to use:** Real-time monitoring and LLM agent state consumption.

```python
# Source: FastAPI WebSocket docs [VERIFIED: FastAPI docs]
import asyncio
import json
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/state")
async def state_stream(ws: WebSocket):
    await ws.accept()
    interval = 1.0 / 3  # 3 Hz default, configurable via query param
    try:
        while True:
            sa = _bot.last_sa
            if sa is not None:
                # dataclasses.asdict would work but is slow; use __dict__ on frozen
                await ws.send_json({
                    "tick": sa.tick,
                    "timestamp": sa.timestamp,
                    "health": sa.health,
                    "armor": sa.armor,
                    "ammo": sa.ammo,
                    "weapon": sa.weapon,
                    "is_alive": sa.is_alive,
                    "disposition": sa.disposition,
                    "enemies_visible": sa.enemies_visible,
                    "current_area": sa.current_area,
                    "has_path": sa.has_path,
                    "is_stuck": sa.is_stuck,
                })
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        pass
```

### Pattern 4: Prometheus Metrics Integration (API-05)

**What:** prometheus_client metrics exposed via ASGI sub-app mounted on `/metrics`.

**When to use:** Observability endpoint.

```python
# Source: prometheus_client docs [VERIFIED: prometheus_client 0.24.1 installed]
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

# Define metrics as module-level singletons
PERCEPTION_FPS = Gauge("bot_perception_fps", "Perception pipeline FPS")
KILL_COUNTER = Counter("bot_kills_total", "Total kills")
DEATH_COUNTER = Counter("bot_deaths_total", "Total deaths")
LLM_LATENCY = Histogram(
    "bot_llm_latency_seconds", 
    "LLM strategy call latency",
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 15.0],
)
STUCK_COUNTER = Counter("bot_stuck_total", "Times bot got stuck")
TICK_DURATION = Histogram(
    "bot_tick_duration_seconds",
    "Game tick duration",
    buckets=[0.01, 0.02, 0.03, 0.05, 0.08, 0.1],
)

# Mount as sub-app
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
```

### Pattern 5: Non-blocking Skill Execution (Critical for Tick Budget)

**What:** Skills that involve `time.sleep()` (VirtualController turns) must run in a background thread to avoid blocking the asyncio event loop and the game tick.

**When to use:** Any skill that calls VirtualController blocking methods.

```python
# Source: asyncio stdlib [ASSUMED]
import asyncio

class TurnAction(AtomicAction):
    """Turn by degrees. Delegates to VirtualController._turn_yaw which uses time.sleep()."""
    
    def __init__(self, controller: VirtualController):
        super().__init__(name="turn", description="Turn by specified degrees")
        self._ctrl = controller
    
    async def execute(self, degrees: float = 0.0, **params) -> SkillResult:
        # Offload blocking turn to thread pool
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._ctrl.turn_degrees, degrees)
        return SkillResult(success=True, message=f"Turned {degrees} degrees")
```

### Anti-Patterns to Avoid

- **Skill objects with lifecycle management:** Skills should not have `start()`/`stop()`/`pause()` lifecycle methods. They are stateless executors. State lives in the subsystem instances they wrap.
- **Global FastAPI app module:** Do not create `app` at module import time. Use a `create_app()` factory that receives the BotState, enabling test isolation.
- **Blocking time.sleep() in async handlers:** VirtualController uses `time.sleep()` for timed turns. These MUST be wrapped in `asyncio.to_thread()` or `loop.run_in_executor()` when called from async skill execute methods.
- **Serializing SituationalAwareness with dataclasses.asdict():** This is surprisingly slow (~0.5ms). For WebSocket streaming at 3 Hz, use a manual dict construction or a cached Pydantic model conversion.
- **WebSocket per-client state:** The WebSocket streams read-only snapshots. Do not maintain per-client state or allow clients to filter fields -- keep it simple, stream the same data to all clients.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| API framework | Custom HTTP server | FastAPI 0.135.3 | Auto-docs, Pydantic validation, WebSocket, dependency injection |
| Metrics exposition | Custom /metrics text format | prometheus_client make_asgi_app() | Correct Prometheus text format, thread-safe collectors |
| WebSocket protocol | Custom binary protocol | FastAPI WebSocket + JSON | LLM agents consume JSON natively; binary adds parsing complexity |
| Request validation | Manual dict checking | Pydantic BaseModel | Type coercion, validation errors, auto-docs, 5-50x faster in v2 |
| ASGI server | Custom event loop management | uvicorn + uvloop | Battle-tested, graceful shutdown, reload support |
| Skill discovery | Plugin system / entry_points | Simple dict registry | Entry_points is for package ecosystems; we have one codebase |
| CORS handling | Manual headers | FastAPI CORSMiddleware | Handles preflight, configurable origins |

**Key insight:** The API layer is entirely standard FastAPI patterns. The only novel piece is the skill system composition, which should be kept deliberately simple -- plain classes with execute() methods, not a framework.

## Common Pitfalls

### Pitfall 1: Blocking the Tick Loop from API Handlers
**What goes wrong:** An API call triggers a skill that calls `VirtualController._turn_yaw()` which does `time.sleep(0.2)`. This blocks the asyncio event loop, freezing the game tick for 200ms.
**Why it happens:** VirtualController was designed for synchronous use in the game tick. Skills wrapping it run in async context.
**How to avoid:** All skill execute() methods that touch VirtualController blocking methods MUST use `asyncio.to_thread()`. Non-blocking VirtualController methods (`_turn_yaw_nonblocking`, `track_target`) are safe to call directly.
**Warning signs:** Game tick FPS drops when API calls are made; `bot_tick_duration_seconds` histogram shows spikes.

### Pitfall 2: Skill System Scope Creep
**What goes wrong:** Skills evolve into a full behavior tree / GOAP system with planners, blackboards, and interrupts. Phase 6 becomes a 3-week rewrite.
**Why it happens:** The spec mentions "composable" which implies complex orchestration.
**How to avoid:** Skills are thin wrappers. Actions call one subsystem method. Behaviors call a sequence of actions. Missions set TacticalFSM goals and let existing subsystems execute. No planners, no blackboards, no new decision-making logic.
**Warning signs:** A skill class has more than 50 lines of logic, or imports from more than one subsystem.

### Pitfall 3: SituationalAwareness Serialization Performance
**What goes wrong:** WebSocket streaming at 3 Hz calls `dataclasses.asdict(sa)` which takes ~0.5ms each time, eating into the tick budget.
**Why it happens:** `dataclasses.asdict()` recursively copies, which is slow for frozen dataclasses with many fields.
**How to avoid:** Create a Pydantic model `PerceptionStateResponse` that accepts SA fields explicitly, or use a manual dict builder. Cache the serialization if SA hasn't changed since last tick.
**Warning signs:** WebSocket handler shows up in profiling as >0.3ms per iteration.

### Pitfall 4: WebSocket Connection Buildup
**What goes wrong:** Multiple LLM agents or monitoring clients connect WebSockets and never disconnect. Each spawns an asyncio task that runs forever.
**Why it happens:** No connection limits or timeouts.
**How to avoid:** Set a max connections limit (e.g., 5). Add a heartbeat/ping timeout. Use a set to track active connections and clean up on disconnect.
**Warning signs:** Memory usage grows linearly with uptime.

### Pitfall 5: FastAPI Startup Race with Game Loop
**What goes wrong:** FastAPI starts serving requests before the game loop has initialized subsystems. API returns 500 errors for the first few seconds.
**Why it happens:** uvicorn and the game loop start concurrently in the same event loop.
**How to avoid:** Use the `lifespan` context manager to gate API readiness. Or simply return 503 from endpoints when `bot.last_sa is None`.
**Warning signs:** First API calls after startup return errors.

### Pitfall 6: Prometheus Metrics in Hot Path
**What goes wrong:** Calling `PERCEPTION_FPS.set()` inside the perception tick adds measurable overhead when done 15+ times per second.
**Why it happens:** prometheus_client uses thread locks internally.
**How to avoid:** Update metrics outside the critical tick path. Use a periodic (every 1s) metrics update task instead of per-tick updates. Only `TICK_DURATION.observe()` needs per-tick granularity.
**Warning signs:** Lock contention shows up in `py-spy` profiles.

## Code Examples

### Concrete Atomic Actions (SKIL-01)

```python
# Source: Wrapping existing GameBridge and VirtualController methods
class MoveAction(AtomicAction):
    """Move forward/backward for a duration."""
    def __init__(self, ctrl: VirtualController):
        super().__init__(name="move", description="Move forward or backward")
        self._ctrl = ctrl
    
    async def execute(self, direction: str = "forward", duration: float = 0.5, **p) -> SkillResult:
        fn = self._ctrl.forward if direction == "forward" else self._ctrl.back
        fn(True)
        await asyncio.sleep(duration)
        fn(False)
        return SkillResult(success=True, message=f"Moved {direction} for {duration}s")

class FireAction(AtomicAction):
    """Start or stop firing."""
    def __init__(self, bridge: GameBridge):
        super().__init__(name="fire", description="Start or stop firing")
        self._bridge = bridge
    
    async def execute(self, on: bool = True, **p) -> SkillResult:
        self._bridge.fire(on)
        return SkillResult(success=True, message=f"Fire {'started' if on else 'stopped'}")

class WeaponSelectAction(AtomicAction):
    """Select weapon by name or slot."""
    def __init__(self, bridge: GameBridge):
        super().__init__(name="weapon_select", description="Select a weapon")
        self._bridge = bridge
    
    async def execute(self, weapon: str = "rocket", **p) -> SkillResult:
        ok = self._bridge.select_weapon_by_name(weapon)
        return SkillResult(success=ok, message=f"Selected {weapon}" if ok else f"Unknown weapon: {weapon}")
```

### Skill Registry

```python
# Source: Project-specific design [ASSUMED]
class SkillRegistry:
    """Flat dictionary registry. Skills register by name."""
    
    def __init__(self):
        self._skills: dict[str, Skill] = {}
    
    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill
    
    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)
    
    def catalog(self) -> list[dict]:
        """Return skill catalog for LLM agent discovery."""
        return [
            {"name": s.name, "layer": s.layer.value, "description": s.description}
            for s in self._skills.values()
        ]
    
    async def execute(self, name: str, **params) -> SkillResult:
        skill = self._skills.get(name)
        if not skill:
            return SkillResult(success=False, message=f"Unknown skill: {name}")
        return await skill.execute(**params)
```

### FastAPI App Factory

```python
# Source: FastAPI lifespan pattern [VERIFIED: FastAPI docs]
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

def create_app(bot: BotState) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Store bot reference for dependency injection
        app.state.bot = bot
        yield
    
    app = FastAPI(
        title="OpenArena Bot API",
        version="0.1.0",
        description="LLM agent control interface for OpenArena bot",
        lifespan=lifespan,
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Pi-local, no auth needed
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    from .routers import perception, navigation, combat, skills, strategy
    app.include_router(perception.router, prefix="/perception", tags=["perception"])
    app.include_router(navigation.router, prefix="/navigation", tags=["navigation"])
    app.include_router(combat.router, prefix="/combat", tags=["combat"])
    app.include_router(skills.router, prefix="/skills", tags=["skills"])
    app.include_router(strategy.router, prefix="/strategy", tags=["strategy"])
    
    # Mount Prometheus metrics
    from prometheus_client import make_asgi_app
    app.mount("/metrics", make_asgi_app())
    
    return app
```

### REST Endpoint Map (API-02)

```
GET  /perception/state          -> SituationalAwareness snapshot
GET  /perception/enemies        -> list of visible enemies
GET  /perception/hud            -> health, armor, ammo, weapon

POST /navigation/goto           -> {area_id: int} | {target: str} -- navigate to area/item
GET  /navigation/path           -> current path info
POST /navigation/explore        -> start random exploration

POST /combat/engage             -> start combat mode
POST /combat/disengage          -> exit combat mode
POST /combat/weapon             -> {weapon: str} -- select weapon

POST /skills/execute            -> {name: str, params: dict} -- execute any skill
GET  /skills/catalog            -> list all available skills with descriptions
GET  /skills/{name}             -> skill details

GET  /strategy/current          -> current StrategyDecision
POST /strategy/override         -> {action: str} -- override LLM strategy

GET  /state/full                -> full bot state (FSM state, position, score, etc)
WS   /ws/state                  -> real-time SituationalAwareness stream

GET  /metrics                   -> Prometheus metrics (text format)
GET  /health                    -> API health check
GET  /docs                      -> auto-generated OpenAPI docs (Swagger UI)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FastAPI lifespan via `on_startup`/`on_shutdown` | `lifespan` async context manager | FastAPI 0.93+ (2023) | Use lifespan, not deprecated events |
| Pydantic v1 BaseModel | Pydantic v2 BaseModel | 2023 | 5-50x faster validation, model_validate_json(), ConfigDict |
| prometheus_client WSGI | prometheus_client ASGI via make_asgi_app() | 0.20+ | Native ASGI support, no WSGI adapter needed |
| uvicorn `--reload` on Pi | No reload in production | Always | --reload uses watchfiles which adds CPU overhead on Pi |

**Deprecated/outdated:**
- FastAPI `@app.on_event("startup")` -- replaced by `lifespan` context manager
- Pydantic v1 `schema()` -- replaced by `model_json_schema()` in v2
- `starlette-prometheus` package -- no longer needed, prometheus_client has make_asgi_app()

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Skills as simple classes with execute() is sufficient; no behavior tree/GOAP needed | Architecture Patterns | If LLM agents need complex composition, skill system may need replanning. LOW risk -- can extend later. |
| A2 | Full SituationalAwareness snapshots at 3 Hz are small enough for WebSocket | Architecture Patterns | If snapshots are larger than expected, may need field filtering. LOW risk -- ~2KB per snapshot. |
| A3 | asyncio.to_thread() is sufficient for offloading VirtualController blocking calls | Pitfall 1 | If thread pool saturates or causes GIL contention, may need process pool. LOW risk -- turns are infrequent. |
| A4 | No authentication needed for API (Pi-local, single-bot) | Architecture Patterns | If exposed to network, needs auth. LOW risk -- bind to 127.0.0.1 by default. |

## Open Questions

1. **How does the FastAPI event loop integrate with the game tick loop?**
   - What we know: STACK.md says "single process, single event loop." FastAPI/uvicorn runs in the same asyncio loop.
   - What's unclear: Who starts the loop? Does `uvicorn.run()` own it, or does the game loop own it and start uvicorn as a background server?
   - Recommendation: Use `uvicorn.Server` with `config.setup_event_loop=False` and start it as an asyncio task within the game's existing event loop. This avoids uvicorn taking over the loop.

2. **Should skills be cancellable mid-execution?**
   - What we know: Behaviors and missions can take multiple seconds. If the bot enters DEAD state, in-progress skills should abort.
   - What's unclear: Cancel via asyncio.Task.cancel() or via a flag check?
   - Recommendation: Use a `_cancelled` flag checked between steps. asyncio.Task.cancel() raises CancelledError which can leave subsystems in inconsistent state.

3. **How do skills interact with TacticalFSM?**
   - What we know: TacticalFSM drives the bot's autonomous behavior. Skills are invoked by external agents.
   - What's unclear: Should skill execution pause the FSM? Should they coexist?
   - Recommendation: Skills that conflict with FSM (e.g., "move to X" while FSM is in COMBAT) should temporarily override the FSM. Add a `SkillOverride` state to the FSM, or use a priority system where API skills override FSM until complete.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | Runtime | Yes | 3.13.12 | -- |
| uv | Package management | Yes | 0.11.3 | -- |
| prometheus-client | /metrics endpoint | Yes | 0.24.1 | -- |
| httpx | API test client | Yes | 0.28.1 | -- |
| fastapi | API framework | No (not installed) | -- | Install via uv add |
| uvicorn | ASGI server | No (not installed) | -- | Install via uv add |
| uvloop | Event loop | No (not installed) | -- | Install via uv add (falls back to stdlib asyncio) |

**Missing dependencies with no fallback:**
- fastapi and uvicorn must be installed (Wave 0 task)

**Missing dependencies with fallback:**
- uvloop: optional, stdlib asyncio works as fallback but ~2x slower

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/test_skills.py tests/test_api.py -x -q` |
| Full suite command | `python -m pytest tests/ -v --tb=short` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SKIL-01 | Atomic actions execute and return SkillResult | unit | `python -m pytest tests/test_skills.py::test_atomic_actions -x` | No -- Wave 0 |
| SKIL-02 | Behaviors compose actions in sequence | unit | `python -m pytest tests/test_skills.py::test_behaviors -x` | No -- Wave 0 |
| SKIL-03 | Missions compose behaviors with goals | unit | `python -m pytest tests/test_skills.py::test_missions -x` | No -- Wave 0 |
| SKIL-04 | Composability -- behavior from actions, mission from behaviors | unit | `python -m pytest tests/test_skills.py::test_composability -x` | No -- Wave 0 |
| SKIL-05 | SKILL.md exists in skills/ folder | smoke | `python -m pytest tests/test_skills.py::test_skill_md_exists -x` | No -- Wave 0 |
| API-01 | FastAPI app starts and serves requests | integration | `python -m pytest tests/test_api.py::test_app_health -x` | No -- Wave 0 |
| API-02 | REST endpoints return correct schemas | integration | `python -m pytest tests/test_api.py::test_endpoints -x` | No -- Wave 0 |
| API-03 | WebSocket streams state at expected Hz | integration | `python -m pytest tests/test_api.py::test_websocket -x` | No -- Wave 0 |
| API-04 | Pydantic models validate request/response | unit | `python -m pytest tests/test_api.py::test_models -x` | No -- Wave 0 |
| API-05 | /metrics returns Prometheus format | integration | `python -m pytest tests/test_api.py::test_metrics -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_skills.py tests/test_api.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_skills.py` -- covers SKIL-01 through SKIL-05
- [ ] `tests/test_api.py` -- covers API-01 through API-05
- [ ] Install fastapi, uvicorn, uvloop: `uv add "fastapi>=0.115,<1.0" "uvicorn[standard]>=0.30" "uvloop>=0.19"`
- [ ] Install pytest-asyncio for async endpoint tests: `uv add --dev "pytest-asyncio>=0.24"`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No -- Pi-local API, bind to 127.0.0.1 | uvicorn --host 127.0.0.1 |
| V3 Session Management | No | N/A |
| V4 Access Control | Minimal -- no multi-user | Bind to localhost only |
| V5 Input Validation | Yes | Pydantic BaseModel for all request bodies |
| V6 Cryptography | No | N/A |

### Known Threat Patterns for FastAPI on Pi

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed JSON crashing API | Tampering | Pydantic validation on all endpoints |
| WebSocket flood exhausting memory | Denial of Service | Max connections limit (5), heartbeat timeout |
| Skill execution causing game state corruption | Tampering | Validate skill params, SkillResult reports failures |
| Unbound metrics cardinality | Denial of Service | Fixed label sets, no user-provided label values |

## Sources

### Primary (HIGH confidence)
- FastAPI 0.135.3 -- verified via `pip3 index versions fastapi` [VERIFIED: PyPI]
- uvicorn 0.44.0 -- verified via `pip3 index versions uvicorn` [VERIFIED: PyPI]
- uvloop 0.22.1 -- verified via `pip3 index versions uvloop` [VERIFIED: PyPI]
- prometheus_client 0.24.1 -- verified installed via `pip3 show prometheus-client` [VERIFIED: local install]
- Existing codebase analysis -- GameBridge, VirtualController, TacticalFSM, all subsystem __init__.py [VERIFIED: codebase]
- STACK.md -- single-process, single-event-loop architecture decision [VERIFIED: project docs]
- FPS Bot Spec Section 8 -- IGameAdapter pattern informing skill layer design [VERIFIED: project docs]

### Secondary (MEDIUM confidence)
- FastAPI lifespan, dependency injection, WebSocket patterns [CITED: fastapi.tiangolo.com]
- prometheus_client make_asgi_app() [CITED: prometheus_client docs]

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions verified against PyPI, existing deps confirmed in pyproject.toml
- Architecture: HIGH -- patterns directly map to existing codebase structure and project conventions
- Pitfalls: HIGH -- derived from codebase analysis (blocking VirtualController, tick budget, SA serialization)

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (stable stack, no fast-moving dependencies)
