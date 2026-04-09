# Subsystem Documentation

OpenArena Perception uses a brain-inspired cognitive architecture with 8 subsystems.
Each subsystem maps to a neuroscience analogue and handles a distinct aspect of bot behavior.

## Subsystem Interaction Map

```
                          +------------------+
                          |     Strategy     |
                          |   (LLM Brain)   |
                          +--------+---------+
                                   |
                            async decisions
                            (~4-5s cycle)
                                   |
                          +--------v---------+
     +------+             |     Tactics      |             +----------+
     |      |  transition |  (TacticalFSM)   | dispatch    |          |
     | Ref- +------------>+  (Commander)     +------------>+ Combat   |
     | lexes|  evaluation |  (FightOrFlight) |             | (Aim,    |
     |      +<------------+                  +------------>+ Engage,  |
     +------+  priority   +--------+---------+  behavior   | Threat)  |
                          override |                       +----------+
                                   |
               +-------------------+-------------------+
               |                                       |
      +--------v---------+                    +--------v---------+
      |   Navigation     |                    |     Memory       |
      |  (Navigator,     |                    |  (Working,       |
      |   LearnedMap,    |                    |   Episodic,      |
      |   RoomSurveyor)  |                    |   Semantic)      |
      +--------+---------+                    +------------------+
               |
      +--------v---------+
      |   Perception      |<--- screen frames (10+ FPS)
      |  (Pipeline,       |
      |   HUD, Players,   |
      |   Motion, Sound)  |
      +--------+---------+
               |
      +--------v---------+
      |   Brainstem       |---> named pipe commands
      |  (GameBridge,     |<--- RCON queries
      |   VirtualCtrl)    |
      +------------------+

  Data flows bottom-up: Brainstem I/O -> Perception -> Tactics -> Strategy
  Control flows top-down: Strategy -> Tactics -> Combat/Navigation -> Brainstem
  Reflexes can override any state transition at any time (subsumption)
```

---

## Perception

**Purpose:** Sensory cortex -- captures screen frames and extracts structured game state
(enemies, HUD values, motion, objects, anomalies, sound events) into an immutable
`SituationalAwareness` snapshot every tick.

**Neuroscience analogue:** Visual cortex + auditory cortex

### Key Classes

| Class | File | Description |
|-------|------|-------------|
| `PerceptionPipeline` | `perception/pipeline.py` | Orchestrates all sub-modules with rate-limiting and attention priority |
| `HUDParser` | `perception/hud_parser.py` | OCR-based extraction of health, armor, ammo, weapon, frags |
| `PlayerDetector` | `perception/player_detector.py` | HSV color thresholding for enemy bounding boxes |
| `ObjectTracker` | `perception/object_tracker.py` | Multi-object tracking with color histograms and templates |
| `MotionDetector` | `perception/motion_detector.py` | Frame differencing and optical flow for movement detection |
| `MotionAnomalyTracker` | `perception/motion_anomaly.py` | Detects unidentified moving objects (potential items/pickups) |
| `DamageTracker` | `perception/damage_tracker.py` | Tracks incoming damage, attacker direction, under-attack state |
| `ConsoleLogParser` | `perception/sound_parser.py` | Parses game log for kills, item pickups, map changes (PERC-08) |
| `Perception` (wall) | `perception/wall_detector.py` | Wall/obstacle detection ahead of the bot |
| `PerceptionPipelineConfig` | `perception/config.py` | Rate-limiting intervals, attention thresholds, tick budget |
| `ScreenCapture` | `perception/capture.py` | mss-based screen grab at 10-22 FPS on Pi |

### Public API

```python
class PerceptionPipeline:
    def __init__(
        pipeline_cfg: PerceptionPipelineConfig = None,
        perception_cfg: PerceptionConfig = None,
        capture: ScreenCapture = None,
        sound_parser: ConsoleLogParser = None,
    ) -> None: ...

    def open(self) -> PerceptionPipeline:
        """Open screen capture. Call before tick()."""

    def close(self) -> None:
        """Release screen capture resource."""

    def tick(
        pos: tuple[float, float, float] = None,
        yaw: float = 0.0,
        area: int = 0,
        nav_state: Any = None,
        spatial: Any = None,
    ) -> SituationalAwareness:
        """Run one perception cycle. Returns frozen snapshot."""

    @property
    def tick_count(self) -> int:
        """Current tick counter value."""

def build_situational_awareness(**kwargs) -> SituationalAwareness:
    """Assemble a frozen SituationalAwareness from detector outputs."""
```

### Data Flow

- **Inputs:** Raw screen frame (800x600 BGR), player position/yaw/area from RCON, nav state, spatial knowledge, game log file
- **Outputs:** Immutable `SituationalAwareness` dataclass (frozen, slotted) containing ~35 fields covering disposition, armament, enemies, navigation, sound events
- **Internal:** Each sub-module runs at configurable intervals via rate-limiting. Combat state triggers attention priority (faster tracker updates, disabled anomaly detection).

### Update Frequency

- **Frame capture + enemy detection + wall detection + damage tracking:** Every tick (~10-22 FPS)
- **HUD OCR:** Every `hud_ocr_interval` ticks (default 3)
- **Motion detection:** Every `motion_interval` ticks (default 2)
- **Object tracking:** Every `tracker_interval` ticks (default 3, or `combat_tracker_interval` = 1 in combat)
- **Anomaly detection:** Every `anomaly_interval` ticks (disabled in combat if `combat_anomaly_enabled` is False)
- **Sound polling:** Every `sound_poll_interval` ticks (default 5)

---

## Reflexes

**Purpose:** Limbic system -- event-driven override layer that can interrupt any state.
Implements subsumption architecture where higher-priority behaviors suppress lower ones.

**Neuroscience analogue:** Amygdala + brainstem reflexes

### Key Classes

| Class | File | Description |
|-------|------|-------------|
| `SubsumptionArbiter` | `reflexes/arbiter.py` | Priority-based state transition evaluator (6 interrupt priorities) |
| `DeathHandler` | `reflexes/death_handler.py` | Death detection, control release, tracker reset, respawn tap |
| `StuckEscape` | `reflexes/stuck_escape.py` | Stuck recovery with target blacklisting (90s timeout) |

### Public API

```python
class SubsumptionArbiter:
    def evaluate(
        sa: SituationalAwareness,
        current_state: BrainState,
        state_time: float,
        **context,
    ) -> BrainState:
        """Return the state that should be active given current awareness.
        Priority: DEAD > COMBAT > STUCK > PICKING_UP_ITEM > TRAVERSING_DOOR > SURVEYING"""

class DeathHandler:
    def __init__(bridge: GameBridge, ctrl: VirtualController) -> None: ...
    def on_enter(sa, anomaly_tracker, obj_tracker) -> None:
        """Increment deaths, release controls, reset trackers."""
    def on_exit(sa) -> None:
        """Release look actions, center view."""
    async def tick(sa, gs) -> None:
        """Release movement, tap +attack for respawn."""
    @property
    def deaths(self) -> int: ...
    @property
    def was_alive(self) -> bool: ...

class StuckEscape:
    def __init__(navigator: Navigator) -> None: ...
    def on_enter(sa, nav_target) -> Optional[str]:
        """Track stucks, blacklist target after 2 failures. Returns updated nav_target."""
    async def tick(sa, gs) -> None:
        """Delegate to Navigator.handle_stuck() for scan-and-probe recovery."""
    def is_blacklisted(target: str) -> bool: ...
    def reset_stuck_count() -> None: ...
```

### Data Flow

- **Inputs:** `SituationalAwareness` snapshot, current FSM state, elapsed state time, context kwargs (survey_cooldown, spatial, commander)
- **Outputs:** `BrainState` enum indicating which state should be active. DeathHandler/StuckEscape produce side-effects via GameBridge commands.

### Update Frequency

- **SubsumptionArbiter.evaluate():** Every tick (called by TacticalFSM before dispatch)
- **DeathHandler/StuckEscape.tick():** Only while in DEAD/STUCK state respectively

---

## Combat

**Purpose:** Motor cortex + cerebellum -- handles aiming, weapon selection, engagement
decisions, threat assessment, and human-like aim imperfection.

**Neuroscience analogue:** Motor cortex (precise aim) + cerebellum (coordination)

### Key Classes

| Class | File | Description |
|-------|------|-------------|
| `AimController` | `combat/aim_controller.py` | PID-based aim tracking with velocity prediction and weapon profiles |
| `WeaponSelector` (functions) | `combat/weapon_select.py` | Fuzzy weapon selection by distance/ammo, aim lead prediction |
| `CombatMover` | `combat/combat_movement.py` | Combat strafing patterns with randomized intervals |
| `CombatEngager` | `combat/engage.py` | Target acquisition, fire control, personality-aware engagement |
| `ThreatAssessor` | `combat/threat_assess.py` | Fight/retreat/cautious evaluation based on HP, weapon, enemy count |
| `AimHumanizer` | `combat/humanize.py` | Perlin-noise aim drift, skill-level parameters, accuracy cap |
| `HumanizationConfig` | `combat/humanize.py` | Frozen slotted dataclass for humanization tuning |
| `PersonalityProfile` | `combat/humanize.py` | Named personality presets (aggressive, cautious, balanced, etc.) |

### Public API

```python
class AimController:
    def __init__(profile: AimProfile = None, humanize: AimHumanizer = None) -> None: ...
    def update(target_cx, target_cy, screen_cx, screen_cy) -> tuple[int, int]:
        """Compute mouse delta (dx, dy) to track target. Returns (0,0) in deadzone."""
    def set_weapon(weapon_name: str) -> None:
        """Switch aim profile based on weapon type."""
    def reset() -> None:
        """Reset PID state when losing target."""
    @property
    def on_target_ratio(self) -> float: ...

def select_weapon(distance: float, inventory: dict) -> Optional[str]:
    """Fuzzy weapon selection by distance and ammo. Returns weapon name."""

def aim_lead(enemy_x, enemy_y, enemy_vx, enemy_vy, player_x, player_y, weapon) -> tuple[float, float]:
    """Predict aim point for projectile weapons. Hitscan returns position directly."""

def should_preemptive_switch(current_weapon, current_ammo, enemy_dist, inventory) -> Optional[str]:
    """Recommend weapon switch before running out of ammo."""

def evaluate_threat(my_health, my_armor, my_weapon, enemy_count, enemy_distance) -> str:
    """Returns 'FIGHT', 'RETREAT', or 'CAUTIOUS'."""

class CombatEngager:
    def __init__(ctrl, bridge, combat_mover, personality=None) -> None: ...
    def on_enter(sa) -> None: """Start firing."""
    def on_exit(sa) -> None: """Stop firing and strafing."""
    async def tick(sa, gs) -> None: """Execute combat behavior for one tick."""

class AimHumanizer:
    def __init__(cfg: HumanizationConfig) -> None: ...
    def sample(t, target_velocity, target_distance, turn_rate) -> tuple[float, float]:
        """Sample Perlin-noise aim drift. Returns (noise_x, noise_y) in pixels."""
```

### Data Flow

- **Inputs:** Enemy bounding boxes (from Perception), SituationalAwareness (health, armor, weapon, ammo), screen center coordinates
- **Outputs:** Mouse deltas (dx, dy) for aim tracking, weapon switch commands, fire on/off commands, strafe commands via GameBridge
- **Internal:** PID controller per axis with anti-windup. Velocity estimation from 8-sample history with exponential smoothing. Humanization noise injected BEFORE PID to prevent integral windup.

### Update Frequency

- **AimController.update():** Every tick while in COMBAT state (~10-22 Hz)
- **Weapon selection:** On combat entry and when ammo drops below threshold
- **Threat assessment:** Every tick while in COMBAT (drives fight/retreat decision)

---

## Navigation

**Purpose:** Hippocampus (spatial) -- AAS-based pathfinding, self-mapping, room surveys,
and movement execution through the game world.

**Neuroscience analogue:** Hippocampus (spatial memory + navigation)

### Key Classes

| Class | File | Description |
|-------|------|-------------|
| `Navigator` | `navigation/navigator.py` | AAS pathfinding with A*, viewpos tracking, stuck recovery |
| `AASGraph` | `navigation/aas_parser.py` | Parsed Quake 3 AAS navigation mesh (areas, reachability edges) |
| `LearnedMap` | `navigation/learned_map.py` | Self-mapping: 64x64 occupancy grid, edge failure memory, wall segments |
| `RoomSurveyor` | `navigation/room_surveyor.py` | 360-degree LLM-powered room documentation with vision analysis |
| `NavBehavior` | `navigation/nav_behavior.py` | Tick-level navigation/exploration behavior with Commander integration |
| `SurveyBehavior` | `navigation/survey_behavior.py` | Survey state machine for coordinating room survey execution |

### Public API

```python
class Navigator:
    def __init__(bridge: GameBridge, aas_path: str = "", bsp_path: str = "") -> None: ...
    def update_position() -> None:
        """Query viewpos via RCON. Updates pos, yaw, current_area."""
    def path_to_area(target: int) -> bool:
        """A* from current area to target. Returns True if path found."""
    def path_to_random() -> bool:
        """Path to a random connected area for exploration."""
    def follow_path() -> Optional[int]:
        """Two-phase path following (steer to start, steer to end). Returns travel type."""
    def handle_stuck(capture_fn=None) -> None:
        """Smart stuck recovery: wall dodge -> exit finder -> skip waypoint."""
    @property
    def is_stuck(self) -> bool: ...
    @property
    def has_path(self) -> bool: ...
    @property
    def current_area(self) -> int: ...

class LearnedMap:
    def __init__(map_name: str, aas_graph=None) -> None: ...
    def update_position(x, y, z) -> None:
        """Mark cells as visited along movement path."""
    def record_edge(from_area, to_area, success) -> None:
        """Track edge traversal success/failure for A* cost adjustment."""
    def edge_penalty(from_area, to_area) -> float:
        """Return learned cost penalty for an edge."""

class RoomSurveyor:
    def survey_room(area_id, pos, yaw) -> dict:
        """Perform 360-degree survey with LLM vision analysis.
        Captures 8 compass + up/down screenshots, sends to Ollama."""
```

### Data Flow

- **Inputs:** Player position/yaw from RCON, AAS file (parsed at init), frame captures (for room surveys), learned edge costs
- **Outputs:** Navigation commands via GameBridge (+forward, +left/+right, cl_yawspeed, +moveup), path state (has_path, path_length, is_stuck), room survey JSON documents
- **Internal:** A* pathfinding with learned edge costs and swim-edge avoidance. Two-phase path following using AAS reachability start/end vectors. Closed-loop steering with proportional yaw speed.

### Update Frequency

- **Navigator.update_position():** Every 0.2s (POS_INTERVAL)
- **Navigator.follow_path():** Every tick while in NAVIGATING/EXPLORING state
- **LearnedMap.update_position():** Every tick (~0.5ms)
- **RoomSurveyor:** On-demand when entering unsurveyed area (SURVEYING state)

---

## Memory

**Purpose:** Hippocampus + long-term storage -- three-layer cognitive memory backed by SQLite.
Working memory is in-process, episodic and semantic are database-persistent.

**Neuroscience analogue:** Working memory (prefrontal cortex) + episodic memory (hippocampus) + semantic memory (neocortex)

### Key Classes

| Class | File | Description |
|-------|------|-------------|
| `WorkingMemory` | `memory/working.py` | In-process mutable state: ring buffer events, danger zones, area visits |
| `EpisodicMemory` | `memory/episodic.py` | DB-backed match event history (kills, deaths, engagements) |
| `SemanticMemory` | `memory/semantic.py` | DB-backed persistent map knowledge (surveys, learned maps, items) |
| `create_database` | `memory/storage.py` | SQLite engine factory with WAL mode, PRAGMAs, table creation |
| `get_engine` | `memory/storage.py` | Cached engine lookup by path |

### Public API

```python
class WorkingMemory:
    """Mutable in-process memory. Never touches database."""
    match_id: str
    map_name: str
    deaths: int
    kills: int
    recent_events: deque  # ring buffer, maxlen=100
    danger_zones: dict[int, float]  # area_id -> danger_score
    recently_visited_areas: deque  # maxlen=20

    def add_event(event_type: str, data: dict = None) -> None:
        """Append event to ring buffer with timestamp."""

class EpisodicMemory:
    def __init__(engine: Engine) -> None: ...
    def record_event(match_id, event_type, map_name, position=None, details=None) -> None:
        """Insert match event with current timestamp."""

class SemanticMemory:
    def __init__(engine: Engine) -> None: ...
    def save_survey(area_id, map_name, position, yaw, timestamp, room_type, exits, items, vantage_points, hazards, recommended_exit) -> None:
        """Upsert room survey data."""

def create_database(db_path: str) -> Engine:
    """Create SQLite DB with WAL mode, all tables, and performance PRAGMAs."""
```

### Data Flow

- **Inputs:** Events from game loop (kills, deaths, area transitions), room survey results, learned map data
- **Outputs:** Historical data for Commander goal selection, danger zone weights for navigation, survey data for RoomSurveyor
- **Internal:** SQLAlchemy Core (not ORM) for lightweight queries. WAL journal mode with busy_timeout=5000 and cache_size=-8000. Upsert pattern uses try-insert/except-IntegrityError-then-update.

### Update Frequency

- **WorkingMemory:** Updated every tick (in-process, ~0 cost)
- **EpisodicMemory:** On events (kill, death, engagement) -- sparse writes
- **SemanticMemory:** On room survey completion, learned map save (every 60s)

---

## Tactics

**Purpose:** Prefrontal cortex (executive) -- FSM state management, goal selection,
fight-or-flight decisions. Orchestrates which behavior runs each tick.

**Neuroscience analogue:** Prefrontal cortex (executive function + planning)

### Key Classes

| Class | File | Description |
|-------|------|-------------|
| `TacticalFSM` | `tactics/fsm.py` | State machine orchestrator: transition evaluation, enter/exit hooks, dispatch |
| `Commander` | `tactics/commander.py` | Strategic goal selection: item routes, enemy avoidance, survival priority |
| `FightOrFlight` | `tactics/fight_or_flight.py` | Wraps ThreatAssessor for stateful fight/retreat decisions |
| `ItemTimingService` | `tactics/item_timing.py` | Item spawn prediction using verified Q3 respawn constants |

### FSM States

| State | Description |
|-------|-------------|
| `DEAD` | Bot is dead. Release controls, tap +attack to respawn |
| `COMBAT` | Under attack with visible enemies. Aim, fire, strafe |
| `STUCK` | Movement blocked. Scan-and-probe recovery |
| `SURVEYING` | New unsurveyed room. 360-degree LLM survey |
| `NAVIGATING` | Following A* path to Commander-selected target |
| `EXPLORING` | No target. Random area exploration |
| `TRAVERSING_DOOR` | Wall obstruction while navigating |
| `PICKING_UP_ITEM` | Motion anomaly detected (potential item pickup) |

### Public API

```python
class TacticalFSM:
    def __init__(
        arbiter: SubsumptionArbiter,
        death_handler: DeathHandler,
        stuck_escape: StuckEscape,
        engager: CombatEngager,
        nav_behavior: NavBehavior,
        survey_behavior: SurveyBehavior = None,
        ctrl: VirtualController = None,
        anomaly_tracker: MotionAnomalyTracker = None,
        obj_tracker: ObjectTracker = None,
        humanize_config: HumanizationConfig = None,
    ) -> None: ...

    async def tick(sa, gs, tick_count=0, **context) -> Optional[float]:
        """Evaluate transitions, handle state change (with optional reaction delay), dispatch behavior."""

    def evaluate_transitions(sa, **context) -> BrainState:
        """Priority-ordered transition evaluation via SubsumptionArbiter."""

    @property
    def state(self) -> BrainState: ...
    @property
    def state_enter_time(self) -> float: ...

class Commander:
    def __init__(items: list[tuple[str, float, float, float]], item_timing=None) -> None: ...
    def decide(sa, pos, current_area, spatial) -> Optional[str]:
        """Pick next navigation target based on health/armor/ammo and item timing."""
    def should_decide() -> bool:
        """Check if DECISION_INTERVAL (3s) has elapsed."""

class ItemTimingService:
    def on_pickup(event: GameEvent) -> None:
        """Record item pickup timestamp."""
    def predict_spawn(item_name: str) -> Optional[float]:
        """Predict next spawn time based on Q3 respawn constants."""
```

### Data Flow

- **Inputs:** `SituationalAwareness` from Perception, context kwargs (spatial, commander, survey_cooldown), StrategyDecision from LLM
- **Outputs:** State transitions triggering enter/exit hooks on subsystems, behavior dispatch to Combat/Navigation/Reflexes handlers
- **Internal:** Reaction delay buffer (HUMN-02/06) uses timestamp comparison, not sleep. Pending transitions are cancelled if situation changes before delay expires. DEAD transitions are always immediate.

### Update Frequency

- **TacticalFSM.tick():** Every tick (transition evaluation + behavior dispatch)
- **Commander.decide():** Every 3 seconds (DECISION_INTERVAL)
- **ItemTimingService:** On item pickup events (event-driven)

---

## Strategy

**Purpose:** Higher-order reasoning -- LLM-powered strategic decisions via Ollama.
Operates on a slower cycle (~4-5s) for macro-level strategy while tactics handles
per-tick decisions.

**Neuroscience analogue:** Prefrontal cortex (long-term planning + reasoning)

### Key Classes

| Class | File | Description |
|-------|------|-------------|
| `LLMStrategyBrain` | `strategy/llm_brain.py` | Async Ollama client with structured prompts and Pydantic validation |
| `StrategyAction` | `strategy/models.py` | Enum of valid LLM actions: EXPLORE, HUNT, RETREAT, DEFEND, PATROL |
| `StrategyDecision` | `strategy/models.py` | Pydantic model: action + reasoning + optional weapon recommendation |

### Public API

```python
class LLMStrategyBrain:
    def __init__(
        model: str = "gemma4:31b-cloud",
        decision_interval: float = 5.0,
        vision_interval: float = 10.0,
    ) -> None: ...

    def should_decide() -> bool:
        """Check if enough time elapsed for a new decision."""

    async def decide(sa: SituationalAwareness) -> StrategyDecision:
        """Query Ollama for strategic decision. Falls back to rule-based on failure.
        Validates response with Pydantic. Strips markdown fences. 10s timeout."""

    def record_frame(frame: np.ndarray) -> None:
        """Store latest frame for periodic vision queries."""

    @property
    def last_decision(self) -> Optional[StrategyDecision]: ...
    @property
    def decision_count(self) -> int: ...
```

### Data Flow

- **Inputs:** `SituationalAwareness` snapshot (converted to human-readable text), optional screen frame (JPEG-encoded, 512px max)
- **Outputs:** `StrategyDecision` containing action enum + reasoning text + optional weapon recommendation
- **Internal:** Lazy `AsyncClient` initialization. 10-second timeout on LLM calls (T-05-04). Markdown fence stripping. Alias mapping normalizes old vocabulary (CAMP/AMBUSH -> DEFEND, GRAB_ITEM -> EXPLORE). Rule-based fallback: critical health -> RETREAT, enemies visible -> HUNT, else -> EXPLORE.

### Update Frequency

- **LLMStrategyBrain.decide():** Every ~5 seconds (decision_interval)
- **Vision frame attachment:** Every ~10 seconds (vision_interval)
- **Latency:** ~2-4 seconds per LLM call on Pi with gemma4:31b-cloud via Ollama

---

## Brainstem

**Purpose:** Medulla + spinal cord -- lowest-level I/O interface between the bot framework
and the game engine. All game commands flow through here.

**Neuroscience analogue:** Brainstem (autonomic I/O) + spinal cord (motor output)

### Key Classes

| Class | File | Description |
|-------|------|-------------|
| `GameBridge` | `game_bridge.py` | Named pipe + RCON UDP communication with ioquake3 |
| `VirtualController` | `virtual_controller.py` | Pipe-only controller: aim, movement, actions (no desktop mouse) |

### Public API

```python
class GameBridge:
    def __init__(
        pipe_path: str = "~/.openarena/baseoa/oapipe",
        rcon_host: str = "127.0.0.1",
        rcon_port: int = 27960,
        rcon_password: str = "botctl",
        our_name: str = "UnnamedPlayer",
    ) -> None: ...

    def open() -> None: """Open pipe and UDP socket."""
    def close() -> None: """Close pipe and socket."""
    def cmd(command: str) -> None: """Send command via named pipe (instant)."""
    def rcon(command: str) -> str: """Send RCON query via UDP. Returns response text."""
    def fire(on: bool) -> None: """Toggle +attack/-attack."""
    def move_forward(on: bool) -> None: """Toggle +forward/-forward."""
    def action_start(action: str) -> None: """Send +{action}."""
    def action_stop(action: str) -> None: """Send -{action}."""
    def release_all() -> None: """Release all held actions."""
    def select_weapon_by_name(name: str) -> bool: """Select weapon by Q3 name."""

class VirtualController:
    def __init__(bridge: GameBridge, screen_w: int = 800, screen_h: int = 600) -> None: ...
    def aim_at_pixel(target_x: int, target_y: int) -> None:
        """Turn to aim crosshair at screen pixel position."""
    def aim_offset(dx_px: int, dy_px: int) -> None:
        """Apply pixel offset as calibrated pipe turn commands."""
    def turn_degrees(degrees: float) -> None:
        """Turn by exact degrees using timed +left/+right."""
    def forward(on: bool) -> None: ...
    def back(on: bool) -> None: ...
    def strafe_left(on: bool) -> None: ...
    def strafe_right(on: bool) -> None: ...
    def center_view() -> None: """Reset view pitch to center."""
    def release_all() -> None: """Release all held keys."""
```

### Data Flow

- **Inputs:** Commands from all upper subsystems (Combat aim deltas, Navigation steering, Reflex control release, Tactics respawn tap)
- **Outputs:** Named pipe commands to ioquake3 client console (+forward, +attack, cl_yawspeed, weapon N), RCON UDP queries (viewpos, getstatus)
- **Internal:** Named pipe (com_pipefile) is the primary control channel -- zero network overhead, instant command injection. RCON UDP is used only for state queries. VirtualController converts pixel offsets to calibrated timed turns using FOV constants (90 deg H / 73.74 deg V at 800x600).

### Update Frequency

- **GameBridge.cmd():** Multiple times per tick (movement + aim + actions)
- **GameBridge.rcon():** Every 0.2s for viewpos, less frequently for getstatus
- **VirtualController.turn_degrees():** Blocking call with time.sleep() (offloaded to thread pool via asyncio.to_thread in skill layer)

### Calibration Constants

| Constant | Value | Source |
|----------|-------|--------|
| Horizontal FOV | 90.0 deg | Q3 default `cg_fov` |
| Vertical FOV | 73.74 deg | Derived from 4:3 aspect ratio |
| Deg/pixel horizontal | 0.1125 | 90.0 / 800 |
| Deg/pixel vertical | 0.1229 | 73.74 / 600 |
| Fine yaw speed | 80 deg/s | Small corrections (<10 deg) |
| Medium yaw speed | 200 deg/s | Medium turns (10-45 deg) |
| Fast yaw speed | 400 deg/s | Large turns (>45 deg) |
