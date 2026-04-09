# Skill Catalog

Complete reference for the OpenArena Perception three-layer skill system.
This is the primary reference for LLM agents composing bot behaviors.

## Skill Architecture

The skill system uses a three-layer hierarchy inspired by robotics behavior composition:

```
  +------------------+
  |    Missions       |   High-level goals with completion criteria
  |  (explore_map,    |   Compose behaviors into strategic objectives
  |   deathmatch,     |
  |   defend_area)    |
  +--------+---------+
           | composes
  +--------v---------+
  |    Behaviors      |   Multi-step sequences with timing
  |  (patrol,         |   Compose actions into tactical patterns
  |   room_survey,    |
  |   combat_engage)  |
  +--------+---------+
           | composes
  +--------v---------+
  |  Atomic Actions   |   Single game commands
  |  (move, turn,     |   Thin wrappers around GameBridge/VirtualController
  |   fire, weapon)   |
  +------------------+
```

### Composition Model

- **Atomic Actions** wrap a single GameBridge or VirtualController call. They are the smallest unit of bot behavior (~0.5-5 seconds).
- **Behaviors** sequence multiple actions with timing and cancellation support. They implement tactical patterns (~5-30 seconds).
- **Missions** compose behaviors with goal conditions. They represent high-level objectives (~30 seconds to minutes).

### Skill Protocol

All skills implement the `Skill` Protocol (PEP 544 structural typing):

```python
@runtime_checkable
class Skill(Protocol):
    name: str              # Unique identifier (e.g., "move", "patrol", "explore_map")
    layer: SkillLayer      # SkillLayer.ACTION | BEHAVIOR | MISSION
    description: str       # Human-readable description for LLM discovery

    async def execute(self, **params: Any) -> SkillResult: ...
    def cancel(self) -> None: ...
```

**SkillResult** is the standard return type:

```python
class SkillResult(BaseModel):
    success: bool          # Whether the skill completed successfully
    message: str = ""      # Human-readable status message
    data: dict[str, Any] = {}  # Skill-specific output data
```

### SkillRegistry

The `SkillRegistry` is a flat dictionary that holds all registered skills:

```python
class SkillRegistry:
    def register(skill: Skill) -> None:
        """Register a skill by its name."""
    def get(name: str) -> Skill | None:
        """Look up a skill by name."""
    def catalog() -> list[dict[str, str]]:
        """Return skill catalog for LLM agent discovery."""
    async def execute(name: str, **params) -> SkillResult:
        """Execute a skill by name with given params."""
```

The default registry is built by `build_registry()` in `skills/catalog.py` with all 10 skills:

```python
registry = build_registry(ctrl=virtual_controller, bridge=game_bridge,
                          engager=combat_engager, survey=survey_behavior)
```

---

## Atomic Actions

### move

**Description:** Move forward or backward for a duration.

**File:** `openarena_perception/skills/actions.py` (`MoveAction`)

**Parameters:**

| Parameter | Type | Default | Constraints | Description |
|-----------|------|---------|-------------|-------------|
| `direction` | `str` | `"forward"` | `"forward"` or `"backward"` only | Movement direction |
| `duration` | `float` | `0.5` | Clamped to 0.0-5.0 seconds | How long to move |

**Duration:** 0.0-5.0 seconds (parameter-controlled)

**Security:** Direction validated against whitelist (T-06-01). Duration clamped to prevent infinite sleep (T-06-02).

**Example:**

```bash
curl -X POST http://localhost:8000/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "move", "params": {"direction": "forward", "duration": 1.0}}'
```

**Response:**
```json
{"success": true, "message": "Moved forward for 1.0s", "data": {}}
```

---

### turn

**Description:** Turn by a specified number of degrees. Offloads blocking `VirtualController.turn_degrees()` to a thread pool via `asyncio.to_thread()`.

**File:** `openarena_perception/skills/actions.py` (`TurnAction`)

**Parameters:**

| Parameter | Type | Default | Constraints | Description |
|-----------|------|---------|-------------|-------------|
| `degrees` | `float` | `0.0` | Clamped to -360.0..360.0 | Turn angle (positive = left, negative = right) |

**Duration:** Proportional to degrees and yaw speed (~0.1-2.0 seconds)

**Security:** Degrees clamped to -360..360 (T-06-01).

**Example:**

```bash
curl -X POST http://localhost:8000/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "turn", "params": {"degrees": 90.0}}'
```

**Response:**
```json
{"success": true, "message": "Turned 90.0 degrees", "data": {}}
```

---

### fire

**Description:** Start or stop firing the current weapon. Wraps `GameBridge.fire()`.

**File:** `openarena_perception/skills/actions.py` (`FireAction`)

**Parameters:**

| Parameter | Type | Default | Constraints | Description |
|-----------|------|---------|-------------|-------------|
| `on` | `bool` | `True` | - | `True` to start firing, `False` to stop |

**Duration:** Instant (command sent, returns immediately)

**Example:**

```bash
# Start firing
curl -X POST http://localhost:8000/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "fire", "params": {"on": true}}'

# Stop firing
curl -X POST http://localhost:8000/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "fire", "params": {"on": false}}'
```

**Response:**
```json
{"success": true, "message": "Fire started", "data": {}}
```

---

### weapon_select

**Description:** Select a weapon by name. Wraps `GameBridge.select_weapon_by_name()`.

**File:** `openarena_perception/skills/actions.py` (`WeaponSelectAction`)

**Parameters:**

| Parameter | Type | Default | Constraints | Description |
|-----------|------|---------|-------------|-------------|
| `weapon` | `str` | `"rocket"` | Must be a valid Q3 weapon name | Weapon to select |

**Valid weapon names:** `gauntlet`, `machinegun`, `shotgun`, `grenade`, `rocket`, `lightning`, `railgun`, `plasma`, `bfg`

**Duration:** Instant

**Example:**

```bash
curl -X POST http://localhost:8000/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "weapon_select", "params": {"weapon": "lightning"}}'
```

**Response:**
```json
{"success": true, "message": "Selected lightning", "data": {}}
```

---

## Behaviors

### patrol

**Description:** Patrol through a sequence of waypoints by alternating move-forward and turn actions. Each waypoint step consists of moving forward for 1 second then turning 90 degrees.

**File:** `openarena_perception/skills/behaviors.py` (`PatrolBehavior`)

**Composed from:** `MoveAction` + `TurnAction`

**Parameters:**

| Parameter | Type | Default | Constraints | Description |
|-----------|------|---------|-------------|-------------|
| `waypoints` | `list` | `[1]` | - | List of waypoint identifiers to visit |

**Duration:** ~2 seconds per waypoint (1s move + ~0.5s turn + overhead)

**Cancellation:** Checked between each waypoint. Returns partial completion count.

**Example:**

```bash
curl -X POST http://localhost:8000/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "patrol", "params": {"waypoints": [1, 2, 3, 4]}}'
```

**Response:**
```json
{"success": true, "message": "Patrol completed 4 waypoints", "data": {"waypoints_completed": 4}}
```

---

### room_survey

**Description:** Perform a 360-degree room survey by executing four 90-degree turns. Optionally delegates to `SurveyBehavior` for full LLM-powered room documentation at each direction.

**File:** `openarena_perception/skills/behaviors.py` (`RoomSurveyBehavior`)

**Composed from:** `TurnAction` (x4) + optional `SurveyBehavior` delegation

**Parameters:**

| Parameter | Type | Default | Constraints | Description |
|-----------|------|---------|-------------|-------------|
| `sa` | `SituationalAwareness` | `None` | - | Current game state (passed to SurveyBehavior) |
| `gs` | `GameState` | `None` | - | Game state with frame (passed to SurveyBehavior) |

**Duration:** ~2-15 seconds (fast without survey, slow with LLM vision)

**Cancellation:** Checked between each 90-degree segment.

**Example:**

```bash
curl -X POST http://localhost:8000/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "room_survey", "params": {}}'
```

**Response:**
```json
{"success": true, "message": "Room survey completed", "data": {}}
```

---

### combat_engage

**Description:** Execute one tick of combat engagement. Delegates to `CombatEngager.tick()` which handles target acquisition, fire control, strafing, and personality-aware engagement.

**File:** `openarena_perception/skills/behaviors.py` (`CombatEngageBehavior`)

**Composed from:** `CombatEngager` delegation

**Parameters:**

| Parameter | Type | Default | Constraints | Description |
|-----------|------|---------|-------------|-------------|
| `sa` | `SituationalAwareness` | `None` | Required for combat logic | Current perception state |
| `gs` | `GameState` | `None` | Required for frame access | Game state with frame |

**Duration:** One tick (~50-100ms)

**Cancellation:** Checked before execution.

**Example:**

```bash
curl -X POST http://localhost:8000/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "combat_engage", "params": {}}'
```

**Response:**
```json
{"success": true, "message": "Combat engagement executed", "data": {}}
```

---

## Missions

### explore_map

**Description:** Explore the map by patrolling repeatedly up to a maximum number of steps. Each step performs one patrol waypoint sequence.

**File:** `openarena_perception/skills/missions.py` (`ExploreMapMission`)

**Composed from:** `PatrolBehavior` (repeated)

**Parameters:**

| Parameter | Type | Default | Constraints | Description |
|-----------|------|---------|-------------|-------------|
| `max_steps` | `int` | `10` | Clamped to 1-100 (T-06-03) | Maximum patrol steps |

**Duration:** ~2-200 seconds (2s per step x max_steps)

**Completion criteria:** All steps completed or cancelled.

**Example:**

```bash
curl -X POST http://localhost:8000/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "explore_map", "params": {"max_steps": 20}}'
```

**Response:**
```json
{"success": true, "message": "Explored 20 steps", "data": {"steps_completed": 20}}
```

---

### deathmatch

**Description:** Hunt and fight enemies by alternating between patrol and combat based on enemy visibility. When enemies are visible, switches to combat engagement; otherwise patrols.

**File:** `openarena_perception/skills/missions.py` (`DeathmatchMission`)

**Composed from:** `PatrolBehavior` + `CombatEngageBehavior` (conditional)

**Parameters:**

| Parameter | Type | Default | Constraints | Description |
|-----------|------|---------|-------------|-------------|
| `rounds` | `int` | `5` | Clamped to 1-50 (T-06-03) | Number of patrol/combat rounds |
| `sa` | `SituationalAwareness` | `None` | Needed for enemy detection | Current perception state |
| `gs` | `GameState` | `None` | Needed for combat | Game state |

**Duration:** ~10-100 seconds (depends on combat frequency)

**Completion criteria:** All rounds completed or cancelled.

**Example:**

```bash
curl -X POST http://localhost:8000/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "deathmatch", "params": {"rounds": 10}}'
```

**Response:**
```json
{"success": true, "message": "Deathmatch completed 10 rounds", "data": {"rounds_completed": 10, "kills": 0}}
```

---

### defend_area

**Description:** Defend a specific map area by patrolling a small region and engaging enemies when they appear.

**File:** `openarena_perception/skills/missions.py` (`DefendAreaMission`)

**Composed from:** `PatrolBehavior` (localized)

**Parameters:**

| Parameter | Type | Default | Constraints | Description |
|-----------|------|---------|-------------|-------------|
| `area_id` | `int` | `0` | AAS area identifier | Area to defend |
| `max_steps` | `int` | `10` | Clamped to 1-100 (T-06-03) | Maximum patrol steps in area |

**Duration:** ~2-200 seconds (2s per step x max_steps)

**Completion criteria:** All steps completed or cancelled.

**Example:**

```bash
curl -X POST http://localhost:8000/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "defend_area", "params": {"area_id": 42, "max_steps": 15}}'
```

**Response:**
```json
{"success": true, "message": "Defended area 42 for 15 steps", "data": {"steps_completed": 15, "area_id": 42}}
```

---

## Triggering Skills via API

All skills are accessible through the `/skills` REST endpoints provided by the FastAPI backend.

### List Available Skills

```bash
curl http://localhost:8000/skills/catalog
```

**Response:**
```json
[
  {"name": "move", "layer": "action", "description": "Move forward or backward"},
  {"name": "turn", "layer": "action", "description": "Turn by specified degrees"},
  {"name": "fire", "layer": "action", "description": "Start or stop firing"},
  {"name": "weapon_select", "layer": "action", "description": "Select a weapon by name"},
  {"name": "patrol", "layer": "behavior", "description": "Patrol through waypoints"},
  {"name": "room_survey", "layer": "behavior", "description": "360-degree room survey"},
  {"name": "combat_engage", "layer": "behavior", "description": "Engage in combat"},
  {"name": "explore_map", "layer": "mission", "description": "Explore the map via patrol"},
  {"name": "deathmatch", "layer": "mission", "description": "Hunt and fight enemies"},
  {"name": "defend_area", "layer": "mission", "description": "Defend a map area"}
]
```

### Execute a Skill

```bash
curl -X POST http://localhost:8000/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "<skill_name>", "params": {<skill_params>}}'
```

### Cancel a Running Skill

```bash
curl -X POST http://localhost:8000/skills/cancel \
  -H "Content-Type: application/json" \
  -d '{"name": "<skill_name>"}'
```

---

## Creating Custom Skills

To add a new skill, implement the `Skill` Protocol and register it with the `SkillRegistry`.

### Step 1: Choose the Layer

- **AtomicAction** -- if your skill wraps a single game command (instant or timed)
- **ComposedBehavior** -- if your skill sequences multiple actions
- **Mission** -- if your skill composes behaviors with a goal condition

### Step 2: Implement the Base Class

```python
from openarena_perception.skills.base import AtomicAction, SkillResult

class DodgeAction(AtomicAction):
    """Quick strafe dodge to avoid incoming fire."""

    def __init__(self, ctrl) -> None:
        super().__init__(name="dodge", description="Quick strafe dodge")
        self._ctrl = ctrl

    async def execute(self, **params) -> SkillResult:
        direction = params.get("direction", "left")
        duration = min(max(0.1, params.get("duration", 0.3)), 1.0)

        fn = self._ctrl.strafe_left if direction == "left" else self._ctrl.strafe_right
        fn(True)
        await asyncio.sleep(duration)
        fn(False)
        return SkillResult(success=True, message=f"Dodged {direction}")
```

### Step 3: Register in the Catalog

Add to `build_registry()` in `skills/catalog.py`:

```python
from .my_actions import DodgeAction

def build_registry(ctrl, bridge, engager=None, survey=None):
    registry = SkillRegistry()
    # ... existing registrations ...
    registry.register(DodgeAction(ctrl))
    return registry
```

### Step 4: Input Validation

Follow the threat mitigation patterns:
- **T-06-01:** Validate string parameters against whitelists
- **T-06-02:** Clamp numeric parameters to sensible ranges (prevent infinite sleep/loops)
- **T-06-03:** Clamp iteration counts for behaviors and missions (max 50-100)
- **T-06-04:** Check `self._cancelled` flag in all loops

### Design Guidelines

1. Skills should be **stateless** between executions (reset internal state on each `execute()`)
2. Use `asyncio.to_thread()` for any blocking calls (e.g., `time.sleep()` in VirtualController)
3. Always return a `SkillResult` -- never raise exceptions from `execute()`
4. Support cancellation by checking `self._cancelled` between steps
5. Keep atomic actions under 5 seconds duration
6. Keep behaviors under 30 seconds duration
7. Missions should have clear completion criteria or bounded iteration limits
