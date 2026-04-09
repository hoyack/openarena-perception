# Architecture

## Cognitive Architecture

The bot uses a brain-inspired layered architecture where each layer operates at a different timescale. Higher layers set goals; lower layers execute them in real-time. Reflexes can override any layer instantly.

```
+---------------------------------------------------+
|            Strategy (LLM ~0.25 Hz)                |
|  LLMStrategyBrain -- Ollama gemma3/gemma4         |
|  Long-term goal selection via structured prompts  |
+---------------------------------------------------+
                      |
                      v
+---------------------------------------------------+
|            Tactics (FSM 2-5 Hz)                   |
|  TacticalFSM -- 8-state finite state machine      |
|  Commander -- item timing, goal prioritization    |
|  FightOrFlight -- threat-based engagement calls   |
+---------------------------------------------------+
                      |
                      v
+---------------------------------------------------+
|      Combat / Navigation (10-22 Hz)               |
|  AimController -- PID aim with lead prediction    |
|  CombatMover -- strafe, dodge, circle patterns    |
|  Navigator -- A* over AAS nav mesh                |
|  NavBehavior -- explore, patrol, survey modes     |
+---------------------------------------------------+
                      |
                      v
+---------------------------------------------------+
|      Reflexes (event-driven, <1ms override)       |
|  SubsumptionArbiter -- priority-based interrupt   |
|  DeathHandler -- respawn recovery                 |
|  StuckEscape -- scan-and-probe exit finding       |
+---------------------------------------------------+
                      |
                      v
+---------------------------------------------------+
|        Perception (15+ FPS pipeline)              |
|  ScreenCapture -- mss at 800x600                  |
|  HUDParser -- Tesseract OCR for vitals            |
|  PlayerDetector -- HSV enemy detection            |
|  ObjectTracker -- multi-object color histograms   |
|  MotionAnomalyTracker -- frame differencing       |
|  DamageTracker -- hit direction estimation        |
+---------------------------------------------------+
                      |
                      v
+---------------------------------------------------+
|    Brainstem (game I/O: named pipes + RCON)       |
|  Named pipe -- command injection                  |
|  RCON UDP -- server queries                       |
|  VirtualController -- movement/aim/weapon actions |
+---------------------------------------------------+
```

## Data Flow

Data flows through the architecture as immutable snapshots:

```
  Screen capture (mss)
       |
       v
  PerceptionPipeline.tick()
       |
       +-- HUDParser       -> health, armor, ammo, weapon
       +-- PlayerDetector   -> enemy bounding boxes
       +-- ObjectTracker    -> tracked object persistence
       +-- MotionAnomalyTracker -> motion anomalies
       +-- DamageTracker    -> attack direction
       +-- WallDetector     -> wall proximity
       |
       v
  build_situational_awareness()
       |
       v
  SituationalAwareness (frozen dataclass, ~35 fields)
       |
       +---> TacticalFSM.tick(sa)      -- state transitions
       +---> Commander.should_decide() -- item timing
       +---> CombatEngager.tick(sa)    -- weapon fire
       +---> NavBehavior.tick(sa)      -- pathfinding
       +---> LLMStrategyBrain(sa)      -- goal reasoning
       |
       v
  Skills (actions -> behaviors -> missions)
       |
       v
  VirtualController -> Named Pipe -> OpenArena
```

**Key principle:** `SituationalAwareness` is immutable (`frozen=True, slots=True`). It is rebuilt every tick by `build_situational_awareness()` and consumed by all higher layers. No layer modifies the snapshot -- they produce actions that flow downward through the skill system.

## Subsystem Overview

### Perception (`openarena_perception/perception/`)
Produces `SituationalAwareness` snapshots at 15+ FPS. Contains screen capture (mss), HUD parsing (Tesseract OCR), enemy detection (HSV color thresholding), multi-object tracking (color histograms + template matching), motion anomaly detection (frame differencing + optical flow), damage tracking, and wall detection. Each detector is isolated with `_safe_call()` exception wrapping to prevent cascade failures.

### Reflexes (`openarena_perception/reflexes/`)
Event-driven interrupt layer using subsumption architecture. `SubsumptionArbiter` checks priority-ordered reflexes each tick. `DeathHandler` manages respawn recovery with state resets. `StuckEscape` uses scan-and-probe exit finding when navigation deadlocks. Reflexes override any tactical or strategic decision with <1ms latency.

### Combat (`openarena_perception/combat/`)
Weapon selection via fuzzy distance/ammo/range scoring. `AimController` implements PID-based aim with lead prediction and Perlin noise humanization. `CombatMover` generates strafe and dodge patterns. `CombatEngager` orchestrates the full combat loop. `ThreatAssessor` evaluates engagement priority. `AimHumanizer` adds skill-level-dependent noise, reaction delays, and accuracy caps.

### Navigation (`openarena_perception/navigation/`)
`AASGraph` parses Quake 3 AAS files for area/reachability data. `Navigator` runs A* pathfinding over the nav mesh. `LearnedMap` tracks edge costs and occupancy grids that improve with experience. `RoomSurveyor` performs 360-degree surveys with LLM spatial documentation. `NavBehavior` provides explore, patrol, and survey behavioral modes.

### Memory (`openarena_perception/memory/`)
SQLite persistence layer using SQLAlchemy Core (not ORM). Stores room surveys, learned map data, match metrics, and replay events. WAL mode with busy_timeout=5000ms and cache_size=-8000 for Pi performance. Migrations via Alembic.

### Tactics (`openarena_perception/tactics/`)
`TacticalFSM` is an 8-state finite state machine (DEAD, COMBAT, STUCK, PICKING_UP_ITEM, TRAVERSING_DOOR, SURVEYING, NAVIGATING, EXPLORING). `Commander` manages item timing (MegaHealth 35s, Red Armor 25s) and goal prioritization. `FightOrFlight` wraps `ThreatAssessor` to make engagement/disengagement decisions.

### Strategy (`openarena_perception/strategy/`)
`LLMStrategyBrain` calls Ollama (gemma3:4b or gemma4:31b-cloud) at ~0.25 Hz for high-level goal selection. Uses structured prompts with current game state and receives validated `StrategyAction` responses (ATTACK, DEFEND, EXPLORE, RETREAT, HEAL). Alias mapping normalizes old vocabulary. Lazy `AsyncClient` initialization avoids import-time side effects.

### Skills (`openarena_perception/skills/`)
Three-layer composable hierarchy. `AtomicAction` (layer 1): single game commands (move, turn, fire, weapon_switch). `ComposedBehavior` (layer 2): multi-step sequences (patrol, room_survey, combat_engage). `Mission` (layer 3): long-running objectives (deathmatch, defend_area, explore_map). `SkillRegistry` provides discovery and execution for LLM agents.

### API (`openarena_perception/api/`)
FastAPI application with 5 REST routers (perception, navigation, combat, skills, strategy), WebSocket state streaming at configurable Hz, and Prometheus metrics. Local-only deployment on Pi -- no authentication required. See the [API Reference](api-reference.md) for endpoint details.

## Multi-Timescale Architecture

Each layer operates at a different frequency, matching its computational cost and decision horizon:

| Layer | Frequency | Latency Budget | Decision Horizon | Key Components |
|-------|-----------|----------------|-------------------|----------------|
| Strategy | ~0.25 Hz (4s cycle) | 2-8s (LLM call) | Minutes | LLMStrategyBrain |
| Tactics | 2-5 Hz | 10-50ms | Seconds | TacticalFSM, Commander |
| Combat | 10-22 Hz | 5-10ms | Immediate | AimController, CombatMover |
| Navigation | 10-22 Hz | 5-10ms | Seconds | Navigator, NavBehavior |
| Reflexes | Event-driven | <1ms | Instant | SubsumptionArbiter |
| Perception | 15+ FPS | 30-60ms | Current frame | PerceptionPipeline |
| Brainstem | On-demand | <1ms | Immediate | Named pipe, RCON |

**Design constraint:** The entire tick loop (perception through action) must complete within 50ms (`tick_budget_ms`) on Pi hardware to maintain 15+ FPS.

## Key Design Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Single process, single event loop** | All subsystems share one asyncio loop. No multiprocessing overhead on Pi's 4 cores. Simpler debugging. |
| 2 | **SQLAlchemy Core, not ORM** | Lightweight query building without ORM overhead. Raw SQL for hot paths. Pi memory constraints. |
| 3 | **TYPE_CHECKING imports for brainstem deps** | Avoids import-time coupling between subsystems. Brainstem deps only needed at runtime for type hints. |
| 4 | **Frozen slotted dataclasses** | `SituationalAwareness` is immutable -- prevents accidental mutation across layers. Slots save memory. |
| 5 | **Subsumption architecture for reflexes** | Priority-based interrupt model. Higher-priority reflexes (death, stuck) override lower-priority behaviors. |
| 6 | **LLM at 0.25 Hz, not per-tick** | LLM calls take 2-8s on Pi. Strategic decisions don't need per-tick updates. Tactics FSM handles moment-to-moment. |
| 7 | **pydantic-settings with env > .env > TOML** | Type-safe configuration chain. Environment variables override for deployment flexibility. |
| 8 | **Exception isolation via _safe_call()** | Each perception detector wrapped in try/except. One failing detector doesn't crash the pipeline. |
| 9 | **Named pipe + RCON (no mouse/keyboard)** | Direct game engine communication. More reliable than input simulation. Works headless. |
| 10 | **Three-layer skill hierarchy** | Actions compose into behaviors, behaviors into missions. LLM agents can operate at any abstraction level. |

## Module Dependency Graph

Import direction is strictly downward. No circular dependencies between subsystems.

```
strategy/
    |
    v
tactics/
    |
    +----------+----------+
    |          |          |
    v          v          v
combat/   navigation/  skills/
    |          |          |
    +-----+----+----------+
          |
          v
      reflexes/
          |
          v
      perception/
          |
          v
      models.py (SituationalAwareness, BrainState)
          |
          v
      settings.py (BotSettings)
          |
          v
      memory/ (SQLite persistence)

api/ ---> all subsystems (read-only queries via BotState)
```

**Rules:**
- Lower layers never import from higher layers
- `models.py` and `settings.py` are leaf dependencies (imported by everyone, import nothing from the project)
- `api/` reads bot state but does not drive the tick loop
- `TYPE_CHECKING` imports are used when a module needs type hints from a peer but not runtime coupling
