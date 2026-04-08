# Architecture Patterns

**Domain:** Brain-inspired FPS AI bot management framework
**Researched:** 2026-04-08

## Recommended Architecture

A hybrid of Brooks' subsumption architecture (layered behaviors, lower layers can override higher) with SOAR-inspired cognitive modules (perception, working memory, procedural memory, action). The key insight: **lower layers run fast and handle reflexes; higher layers run slower and handle strategy**. This maps naturally to the existing system where HSV detection runs at 15+ FPS but LLM reasoning runs at 0.25 Hz.

### Architecture: Layered Cognitive Subsumption

```
                    +----------------------------------+
                    |     PREFRONTAL CORTEX            |
                    |  (Strategic Brain / LLM Agent)    |
                    |  ~0.25 Hz (every 4s)             |
                    +----------------------------------+
                              |  goals, strategy
                              v
                    +----------------------------------+
                    |     PARIETAL CORTEX               |
                    |  (Tactical Controller / FSM)      |
                    |  ~2-5 Hz (every tick group)       |
                    +----------------------------------+
                              |  behaviors
                              v
+----------------+  +----------------------------------+  +----------------+
| SENSORY CORTEX |->|     MOTOR CORTEX + CEREBELLUM    |<-| HIPPOCAMPUS    |
| (Perception)   |  |  (Actions / VirtualController)   |  | (Navigation +  |
| 15-20 Hz       |  |  15-20 Hz                        |  |  Memory)       |
+----------------+  +----------------------------------+  +----------------+
        ^                       |                               |
        |                       v                               v
+----------------+  +----------------------------------+  +----------------+
| LIMBIC SYSTEM  |  |     BRAIN STEM                   |  | LONG-TERM      |
| (Reflexes /    |  |  (Game Bridge / I/O)             |  | STORAGE        |
| Threat React)  |  |  Named Pipe + RCON               |  | (DB / Files)   |
| <1ms override  |  +----------------------------------+  +----------------+
+----------------+
```

### Subsumption Priority (lower number = higher priority, can override)

| Priority | System | Trigger | Override Behavior |
|----------|--------|---------|-------------------|
| 0 | Brain Stem (I/O) | Always | Pipe/RCON communication cannot be interrupted |
| 1 | Limbic (Reflexes) | Damage spike, death | Suppresses all higher layers, immediate dodge/respawn |
| 2 | Motor Cortex (Actions) | Combat target acquired | Fires, aims, strafes without waiting for strategy |
| 3 | Sensory Cortex (Perception) | Every frame | Feeds all other systems, never blocked |
| 4 | Hippocampus (Navigation) | No combat target | Pathfinding, exploration, map learning |
| 5 | Parietal (Tactical) | Every N ticks | Selects behaviors, manages FSM transitions |
| 6 | Prefrontal (Strategic) | Every ~4s | Long-term goals, LLM reasoning |

### Component Boundaries

| Component | Brain Region | Responsibility | Communicates With | Tick Rate |
|-----------|-------------|----------------|-------------------|-----------|
| `perception/` | Sensory Cortex | Screen capture, HUD OCR, enemy detection, motion detection, object tracking | All systems (read-only producer) | 15-20 Hz |
| `reflexes/` | Limbic System | Damage reaction, death detection, stuck escape, panic dodge | Motor cortex (direct override) | Event-driven (<1ms) |
| `combat/` | Motor Cortex + Cerebellum | Aim control, weapon selection, fire control, combat movement | Perception (reads), Brain stem (writes commands) | 15-20 Hz |
| `navigation/` | Hippocampus | AAS pathfinding, learned map, room surveys, spatial awareness | Perception (reads), Brain stem (writes movement) | 5-10 Hz |
| `memory/` | Hippocampus + Long-term | Working memory (current state), episodic (match history), semantic (map knowledge) | All systems (read/write) | Async consolidation |
| `tactics/` | Parietal Cortex | FSM state management, behavior selection, fight-or-flight | Reads all, directs combat/navigation | 2-5 Hz |
| `strategy/` | Prefrontal Cortex | LLM reasoning, goal setting, strategic analysis | Tactics (sets goals), Memory (reads/writes) | 0.25 Hz |
| `brainstem/` | Brain Stem | Game bridge, named pipe, RCON, virtual controller | All motor systems (write path) | Always available |

### Data Flow

```
PERCEPTION PIPELINE (every frame, ~45ms):
  Screen Capture (mss)
    -> Frame Buffer (shared numpy array)
      -> HUD Parser (OCR, periodic)
      -> World Parser (enemy detection, every frame)
      -> Motion Detector (frame differencing)
      -> Object Tracker (multi-target)
    -> SituationalAwareness dataclass (unified snapshot)

REFLEX ARC (event-driven, <1ms):
  SituationalAwareness
    -> Damage spike detected? -> DODGE (suppress navigation)
    -> Death detected? -> RESPAWN SEQUENCE (suppress all)
    -> Stuck detected? -> EXIT FINDER (suppress navigation)

DECISION PIPELINE (layered, different rates):
  SituationalAwareness
    -> Tactical FSM (2-5 Hz): state transitions, behavior selection
      -> IF combat state: Combat System handles aim/fire/movement
      -> IF navigate state: Navigator handles pathfinding/movement
      -> IF explore state: Explorer handles map discovery
    -> Strategic Brain (0.25 Hz): LLM evaluates situation
      -> Sets: goal, weapon preference, aggression level
      -> Updates: tactical FSM priorities

ACTION PIPELINE (every frame):
  Selected Behavior
    -> Action Composer (resolves conflicts between systems)
    -> VirtualController (translates to pipe commands)
    -> GameBridge (writes to named pipe + RCON)

MEMORY PIPELINE (async, background):
  SituationalAwareness + Action Results
    -> Working Memory (immediate, in-process)
    -> Episodic Buffer (recent events, ring buffer)
    -> Long-term Consolidation (map knowledge, strategies learned)
```

## Recommended Folder Structure

```
openarena_perception/
|
|-- brain/                      # Top-level orchestrator
|   |-- __init__.py
|   |-- tick.py                 # Main tick loop: perception -> decision -> action
|   |-- awareness.py            # SituationalAwareness dataclass (replaces scattered state)
|   `-- config.py               # Unified configuration
|
|-- perception/                 # Sensory Cortex — read-only producers
|   |-- __init__.py
|   |-- capture.py              # Screen capture (mss)
|   |-- hud_parser.py           # OCR for health/armor/ammo/weapon
|   |-- world_parser.py         # HSV enemy detection, bounding boxes
|   |-- motion_detector.py      # Frame differencing, optical flow
|   |-- object_tracker.py       # Multi-object tracking with histograms
|   |-- player_detector.py      # ML-based player detection
|   |-- hailo_detector.py       # NPU-accelerated YOLO detection
|   `-- loop.py                 # Perception loop orchestrator
|
|-- reflexes/                   # Limbic System — fast override behaviors
|   |-- __init__.py
|   |-- damage_response.py      # React to damage spikes (dodge, retreat)
|   |-- death_handler.py        # Respawn sequence
|   |-- stuck_escape.py         # Stuck detection + exit finding
|   `-- threat_reflex.py        # Immediate threat reactions
|
|-- combat/                     # Motor Cortex + Cerebellum — fighting
|   |-- __init__.py
|   |-- aim_controller.py       # PID aim with lead prediction
|   |-- weapon_select.py        # Fuzzy weapon selection
|   |-- fire_control.py         # When and how to fire
|   |-- combat_movement.py      # Circle strafe, dodge, positioning
|   `-- damage_tracker.py       # Track incoming/outgoing damage
|
|-- navigation/                 # Hippocampus — spatial reasoning
|   |-- __init__.py
|   |-- aas_parser.py           # Q3 AAS nav mesh parsing
|   |-- navigator.py            # A* pathfinding on AAS graph
|   |-- learned_map.py          # Occupancy grid, edge costs
|   |-- room_surveyor.py        # 360-degree room documentation
|   |-- spatial_map.py          # Topological map
|   `-- exit_finder.py          # Scan-and-probe for stuck recovery
|
|-- memory/                     # Memory systems — state persistence
|   |-- __init__.py
|   |-- working.py              # Current tick state (in-process, fast)
|   |-- episodic.py             # Recent event buffer (ring buffer)
|   |-- semantic.py             # Map knowledge, item locations, strategies
|   `-- storage.py              # DB/file persistence layer
|
|-- tactics/                    # Parietal Cortex — behavior selection
|   |-- __init__.py
|   |-- fsm.py                  # State machine (DEAD/COMBAT/NAVIGATE/etc.)
|   |-- commander.py            # Item prioritization, respawn timing
|   `-- evaluator.py            # Fight-or-flight, threat assessment
|
|-- strategy/                   # Prefrontal Cortex — LLM reasoning
|   |-- __init__.py
|   |-- llm_brain.py            # Ollama integration
|   |-- strategic_agent.py      # High-level goal setting
|   `-- prompts.py              # LLM prompt templates
|
|-- brainstem/                  # Brain Stem — I/O interface
|   |-- __init__.py
|   |-- game_bridge.py          # Named pipe + RCON communication
|   |-- virtual_controller.py   # Command composition + conflict resolution
|   `-- actions.py              # Atomic action definitions
|
|-- skills/                     # Three-layer skill system
|   |-- __init__.py
|   |-- actions/                # Layer 1: Atomic actions (move_forward, fire, etc.)
|   |   |-- __init__.py
|   |   |-- movement.py
|   |   |-- weapon.py
|   |   `-- look.py
|   |-- behaviors/              # Layer 2: Composed behaviors (patrol, engage, retreat)
|   |   |-- __init__.py
|   |   |-- patrol.py
|   |   |-- engage.py
|   |   `-- retreat.py
|   `-- missions/               # Layer 3: High-level missions (control_area, hunt, survive)
|       |-- __init__.py
|       |-- hunt.py
|       |-- control_area.py
|       `-- survive.py
|
|-- api/                        # FastAPI layer for LLM agent control
|   |-- __init__.py
|   |-- app.py                  # FastAPI application
|   |-- routes/
|   |   |-- perception.py       # GET /perception/state, /perception/frame
|   |   |-- combat.py           # POST /combat/engage, /combat/disengage
|   |   |-- navigation.py       # POST /navigate/to, GET /navigation/map
|   |   |-- skills.py           # POST /skills/execute
|   |   |-- strategy.py         # POST /strategy/goal, GET /strategy/state
|   |   `-- memory.py           # GET /memory/map, /memory/history
|   |-- ws.py                   # WebSocket for real-time state streaming
|   `-- models.py               # Pydantic request/response models
|
`-- tools/                      # Development/debug utilities
    |-- roi_debugger.py
    `-- replay_viewer.py
```

## Patterns to Follow

### Pattern 1: Message Bus with Typed Events

The brain subsystems should communicate via a lightweight in-process message bus, not direct imports. This keeps subsystem boundaries clean and enables the subsumption override mechanism.

**What:** A typed event system where producers emit events and consumers subscribe. Events flow through a priority queue so reflexes can preempt strategic decisions.

**When:** All inter-subsystem communication.

**Example:**
```python
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

class Priority(IntEnum):
    REFLEX = 0      # Cannot be overridden
    COMBAT = 1      # Overrides navigation
    NAVIGATION = 2  # Overrides exploration
    TACTICAL = 3    # Overrides strategic
    STRATEGIC = 4   # Lowest priority

@dataclass
class BrainEvent:
    priority: Priority
    source: str          # "perception", "reflexes", "combat", etc.
    event_type: str      # "enemy_detected", "damage_taken", "path_complete"
    data: Any
    timestamp: float

class EventBus:
    """In-process pub/sub with priority preemption."""

    def __init__(self):
        self._subscribers: dict[str, list] = {}
        self._active_priority = Priority.STRATEGIC  # current highest

    def subscribe(self, event_type: str, callback, priority: Priority):
        self._subscribers.setdefault(event_type, []).append((priority, callback))

    def emit(self, event: BrainEvent):
        # Higher-priority events suppress lower-priority active behaviors
        if event.priority < self._active_priority:
            self._active_priority = event.priority
        for priority, callback in self._subscribers.get(event.event_type, []):
            if priority <= self._active_priority:
                callback(event)
```

### Pattern 2: SituationalAwareness as Immutable Snapshot

**What:** Every tick produces a single immutable `SituationalAwareness` dataclass that all systems read. No system mutates it. This prevents race conditions and makes the perception-to-action pipeline debuggable.

**When:** Every tick of the main loop.

**Example:**
```python
@dataclass(frozen=True)
class SituationalAwareness:
    tick: int
    timestamp: float
    # Position
    pos: tuple[float, float, float] | None
    yaw: float
    current_area: int
    # Vitals
    health: int | None
    armor: int | None
    ammo: int | None
    weapon: str | None
    # Enemies
    enemies: tuple[EnemyContact, ...]
    nearest_enemy_dist: float | None
    # Navigation
    is_stuck: bool
    path_progress: float
    # Anomalies
    damage_delta: int
    motion_anomalies: tuple
    # Raw frame reference (not copied, just a reference)
    frame_id: int
```

### Pattern 3: Tick Budget Allocation

**What:** Each tick has a time budget (~45ms for 20 FPS). Subsystems get allocated portions. If perception takes too long, tactical evaluation is skipped that tick. Reflexes never get cut.

**When:** Main loop orchestration.

**Example:**
```python
TICK_BUDGET_MS = 50  # 20 FPS target

BUDGET_ALLOCATION = {
    "perception": 25,    # 50% — non-negotiable
    "reflexes": 2,       # 4% — fast, event-driven
    "combat": 10,        # 20% — aim/fire when in combat
    "navigation": 8,     # 16% — pathfinding when not in combat
    "tactical": 3,       # 6% — FSM transitions
    "strategic": 0,      # 0% — runs on separate async task
    "memory": 2,         # 4% — working memory update
}
```

### Pattern 4: FastAPI as External Observer, Not Tick Driver

**What:** FastAPI runs in the same asyncio event loop as the game tick loop but does NOT drive ticks. The tick loop runs independently at its target FPS. FastAPI endpoints read the latest SituationalAwareness snapshot and can enqueue commands for the next tick.

**When:** API integration.

**Example:**
```python
import asyncio
from fastapi import FastAPI

app = FastAPI()
brain = None  # Set during startup

@app.on_event("startup")
async def startup():
    global brain
    brain = BrainController(config)
    asyncio.create_task(brain.run_tick_loop())  # Independent tick loop

@app.get("/perception/state")
async def get_state():
    return brain.latest_awareness.to_dict()

@app.post("/skills/execute")
async def execute_skill(skill: SkillRequest):
    brain.enqueue_command(skill)  # Queued for next tick
    return {"status": "queued"}

@app.websocket("/ws/state")
async def state_stream(websocket):
    await websocket.accept()
    while True:
        state = await brain.state_updated.wait()
        await websocket.send_json(brain.latest_awareness.to_dict())
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: God Object Brain
**What:** Putting all logic in `strategic_brain.py` (current state: 700+ lines importing everything).
**Why bad:** Untestable, unreadable, every change risks breaking unrelated behavior. The current `StrategicBrain` is the god object.
**Instead:** Each brain region is its own module. The main tick loop composes them. `brain/tick.py` is a thin orchestrator (~100 lines) that calls subsystems in order.

### Anti-Pattern 2: Direct Cross-Subsystem Imports
**What:** `combat.py` importing from `navigation.py` or `strategy/` importing from `reflexes/`.
**Why bad:** Creates circular dependencies and tight coupling. Cannot test subsystems in isolation.
**Instead:** Subsystems communicate only through: (a) SituationalAwareness (read), (b) EventBus (pub/sub), (c) Action queue (write). No direct imports between peer subsystems.

### Anti-Pattern 3: Blocking LLM Calls in Tick Loop
**What:** Waiting for Ollama response (4+ seconds) in the main tick loop.
**Why bad:** Freezes all perception, combat, and navigation for 4 seconds. Bot stands still and dies.
**Instead:** LLM runs on a separate asyncio task. Writes results to a shared `StrategyGoal` that the tactical layer reads when available. Stale strategy is better than no perception.

### Anti-Pattern 4: Mutable Shared State
**What:** Multiple systems writing to the same GameState dict.
**Why bad:** Race conditions, impossible to debug, state corruption.
**Instead:** Immutable SituationalAwareness produced by perception. Each subsystem has its own internal state. Commands flow through action queue.

## Build Order (Dependencies)

The brain-inspired restructure should proceed in this order, based on dependency analysis:

```
Phase 1: Foundation (no dependencies)
  brainstem/     <- Already exists as game_bridge + virtual_controller
  brain/config   <- Already exists as config.py
  brain/awareness <- Already exists as SituationalAwareness in strategic_brain

Phase 2: Perception (depends on: brainstem)
  perception/    <- Already exists as capture + hud_parser + world_parser + loop
  
Phase 3: Memory (depends on: perception)
  memory/        <- Partially exists as learned_map + room surveys on disk

Phase 4: Reflexes + Combat (depends on: perception, brainstem)
  reflexes/      <- Extract from strategic_brain damage/stuck handling
  combat/        <- Already exists as combat.py + aim_controller

Phase 5: Navigation (depends on: perception, brainstem, memory)
  navigation/    <- Already exists as navigator + aas_parser + exit_finder

Phase 6: Tactics (depends on: all above)
  tactics/       <- Extract FSM from strategic_brain

Phase 7: Strategy (depends on: tactics, memory)
  strategy/      <- Already exists as llm_brain + strategic_agent

Phase 8: Skills (depends on: combat, navigation, brainstem)
  skills/        <- New system: actions -> behaviors -> missions

Phase 9: API (depends on: all above)
  api/           <- New system: FastAPI + WebSocket
```

**Rationale:** Each phase produces a testable, runnable subsystem. Phases 1-2 give you a working perception pipeline. Phase 4 gives you a bot that can fight. Phase 5 gives you a bot that can navigate. Phase 6 ties them together. Phase 7 adds intelligence. Phase 8 adds composability. Phase 9 adds external control.

## Scalability Considerations

| Concern | Current (Pi 5) | With Hailo NPU | Desktop |
|---------|----------------|-----------------|---------|
| Perception FPS | 15-17 FPS (HSV) | 60+ FPS (YOLOv6n) | 60+ FPS |
| LLM latency | ~4s (gemma4:31b) | ~4s (same) | <1s (larger models) |
| Memory storage | JSON/pickle files | JSON/pickle files | SQLite/PostgreSQL |
| API throughput | Sufficient (single consumer) | Sufficient | Could serve multiple agents |
| Tick budget | 45-50ms | 20-30ms | 10-15ms |

The architecture supports scaling by swapping implementations within fixed interfaces. The perception module can switch from HSV to YOLO without any other module knowing. The strategy module can switch from gemma4 to GPT-4 without affecting tactics.

## Communication Protocol Summary

```
+-- Read-only data flow (SituationalAwareness) -------->
|
|  perception -> [awareness snapshot] -> ALL SYSTEMS read it
|
+-- Event-driven signals (EventBus) -------------------->
|
|  any system -> EventBus -> subscribed systems
|  Examples: "enemy_detected", "damage_taken", "path_blocked"
|
+-- Command queue (Action Pipeline) -------------------->
|
|  any system -> ActionQueue -> VirtualController -> GameBridge
|  Priority-based: reflexes override combat override navigation
|
+-- Async background (Strategy + Memory) --------------->
|
|  LLM task runs independently, writes StrategyGoal
|  Memory consolidation runs independently, writes to DB
```

## Sources

- [Soar Cognitive Architecture](https://soar.eecs.umich.edu/) - SOAR decision cycle, working memory, procedural/semantic/episodic memory
- [Subsumption Architecture - Wikipedia](https://en.wikipedia.org/wiki/Subsumption_architecture) - Brooks' layered behavior architecture with priority override
- [Neural Brain: Neuroscience-inspired Framework](https://arxiv.org/html/2505.07634v1) - Sensing, Function, Memory, Hardware modules
- [Brain-Inspired AI Agent: The Way Towards AGI](https://arxiv.org/html/2412.08875v1) - Modular brain-region mapping for AI agents
- [FastAPI Async/Await](https://fastapi.tiangolo.com/async/) - Event loop integration patterns
- [Game AI Planning: GOAP, Utility, and Behavior Trees](https://tonogameconsultants.com/game-ai-planning/) - Hybrid AI decision systems
- [OpenAI Five Architecture](https://cdn.openai.com/research-covers/openai-five/network-architecture.pdf) - Observation embedding, action heads, LSTM core
- Existing codebase: `ARCHITECTURE.md`, `SKILL.md`, `strategic_brain.py` import graph analysis
