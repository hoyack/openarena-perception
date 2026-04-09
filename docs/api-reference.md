# API Reference

## API Reference

Auto-generated from FastAPI OpenAPI specification.

## Endpoints

**Base URL:** `http://localhost:8420`
**Authentication:** None required (local Pi deployment)
**Content-Type:** `application/json`

---

## Perception

Endpoints for querying the bot's current sensory state.

### GET /perception/state

Return the latest SituationalAwareness snapshot.

**Request:** None

**Response:** `PerceptionStateResponse`

| Field | Type | Description |
|-------|------|-------------|
| tick | int | Perception tick counter |
| timestamp | float | Unix timestamp of snapshot |
| pos | [float, float, float] \| null | Bot position (x, y, z) |
| yaw | float | Current facing angle in degrees |
| current_area | int | AAS area ID |
| health | int \| null | Health points (0-200) |
| armor | int \| null | Armor points (0-200) |
| ammo | int \| null | Current weapon ammo count |
| weapon | string \| null | Current weapon name |
| is_alive | bool | Whether the bot is alive |
| disposition | string | Health state: healthy/wounded/critical/dead |
| armament | string | Ammo state: armed/light/unarmed |
| orientation | string | Nav state: oriented/exploring/lost |
| under_attack | bool | Currently taking damage |
| attacker_direction | int | Direction of last damage source (degrees) |
| seconds_since_damage | float | Time since last hit |
| enemies_visible | int | Number of detected enemies |
| nearest_enemy_distance | string \| null | Distance category to nearest enemy |
| wall_ahead | bool | Wall detected in movement direction |
| wall_score | float | Wall proximity score (0.0 = clear, 1.0 = blocked) |
| open_direction | int | Most open direction (degrees) |
| in_water | bool | Bot is in water |
| tracked_objects | int | Number of tracked objects |
| locked_target | bool | Object tracker has a locked target |
| anomaly_count | int | Motion anomalies detected |
| lockable_anomaly | bool | A lockable motion anomaly exists |
| room_surveyed | bool | Current room has been surveyed |
| room_type | string | Current room classification |
| room_exits | int | Number of exits from current room |
| has_path | bool | Active navigation path exists |
| path_length | int | Steps remaining on current path |
| is_stuck | bool | Bot is stuck |
| is_recovering | bool | Stuck recovery in progress |
| nav_target | string \| null | Current navigation target |
| has_frame | bool | Perception frame available |

**Example:**
```bash
curl http://localhost:8420/perception/state
```

**Error:** `503` if no perception data is available yet.

---

### GET /perception/enemies

Return enemy threat summary from last SituationalAwareness.

**Request:** None

**Response:** `EnemyInfo`

| Field | Type | Description |
|-------|------|-------------|
| enemies_visible | int | Number of detected enemies |
| nearest_enemy_distance | string \| null | Distance category to nearest enemy |
| under_attack | bool | Currently taking damage |

**Example:**
```bash
curl http://localhost:8420/perception/enemies
```

**Error:** `503` if no perception data is available yet.

---

### GET /perception/hud

Return HUD vitals from last SituationalAwareness.

**Request:** None

**Response:** `HudResponse`

| Field | Type | Description |
|-------|------|-------------|
| health | int \| null | Health points |
| armor | int \| null | Armor points |
| ammo | int \| null | Current ammo count |
| weapon | string \| null | Current weapon name |

**Example:**
```bash
curl http://localhost:8420/perception/hud
```

**Error:** `503` if no perception data is available yet.

---

## Navigation

Endpoints for controlling bot movement and pathfinding.

### POST /navigation/goto

Request navigation to an area or named target.

**Request:** `NavigationRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| area_id | int \| null | No | AAS area ID to navigate to |
| target | string \| null | No | Named target (e.g., "MegaHealth", "RedArmor") |

One of `area_id` or `target` must be provided.

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| status | string | "navigating" |
| target | int \| string | The navigation target |

**Example:**
```bash
curl -X POST http://localhost:8420/navigation/goto \
  -H "Content-Type: application/json" \
  -d '{"area_id": 42}'
```

**Error:** `400` if neither `area_id` nor `target` is provided.

---

### GET /navigation/path

Return current navigation state from last SituationalAwareness.

**Request:** None

**Response:** `NavigationStateResponse`

| Field | Type | Description |
|-------|------|-------------|
| has_path | bool | Active navigation path exists |
| path_length | int | Steps remaining on path |
| is_stuck | bool | Bot is stuck |
| nav_target | string \| null | Current navigation target |

**Example:**
```bash
curl http://localhost:8420/navigation/path
```

**Error:** `503` if no perception data is available yet.

---

### POST /navigation/explore

Start random exploration.

**Request:** None

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| status | string | "exploring" |

**Example:**
```bash
curl -X POST http://localhost:8420/navigation/explore
```

---

## Combat

Endpoints for controlling combat engagement.

### POST /combat/engage

Enter combat mode.

**Request:** None

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| status | string | "engaging" |

**Example:**
```bash
curl -X POST http://localhost:8420/combat/engage
```

---

### POST /combat/disengage

Exit combat mode.

**Request:** None

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| status | string | "disengaged" |

**Example:**
```bash
curl -X POST http://localhost:8420/combat/disengage
```

---

### POST /combat/weapon

Select a weapon by name.

**Request:** JSON body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| weapon | string | Yes | Weapon name to select |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| status | string | "selected" or "failed" |
| weapon | string | The requested weapon |

**Example:**
```bash
curl -X POST http://localhost:8420/combat/weapon \
  -H "Content-Type: application/json" \
  -d '{"weapon": "railgun"}'
```

---

## Skills

Endpoints for the three-layer skill system (actions, behaviors, missions).

### POST /skills/execute

Execute a skill by name with given parameters.

**Request:** `SkillExecuteRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | Yes | Skill name from the catalog |
| params | object | No | Key-value parameters for the skill (default: {}) |

**Response:** `SkillExecuteResponse`

| Field | Type | Description |
|-------|------|-------------|
| success | bool | Whether execution succeeded |
| message | string | Human-readable result description |
| data | object \| null | Optional result data |

**Example:**
```bash
curl -X POST http://localhost:8420/skills/execute \
  -H "Content-Type: application/json" \
  -d '{"name": "move_forward", "params": {"duration": 1.0}}'
```

**Error:** `503` if skill registry is not available.

---

### GET /skills/catalog

Return the full skill catalog for LLM agent discovery.

**Request:** None

**Response:** `list[SkillCatalogEntry]`

| Field | Type | Description |
|-------|------|-------------|
| name | string | Skill name |
| layer | string | Skill layer: "action", "behavior", or "mission" |
| description | string | What the skill does |

**Example:**
```bash
curl http://localhost:8420/skills/catalog
```

**Error:** `503` if skill registry is not available.

---

### GET /skills/{name}

Return detail for a single skill by name.

**Request:** Path parameter `name` (string)

**Response:** `SkillCatalogEntry`

| Field | Type | Description |
|-------|------|-------------|
| name | string | Skill name |
| layer | string | Skill layer |
| description | string | What the skill does |

**Example:**
```bash
curl http://localhost:8420/skills/move_forward
```

**Errors:**
- `404` if skill not found
- `503` if skill registry is not available

---

## Strategy

Endpoints for querying and overriding the bot's strategic decisions.

### GET /strategy/current

Return current strategy / FSM state.

**Request:** None

**Response:** `StrategyStateResponse`

| Field | Type | Description |
|-------|------|-------------|
| current_action | string | Active action (may be overridden) |
| brain_state | string | FSM state: dead/combat/stuck/picking_up_item/traversing_door/surveying/navigating/exploring |

**Example:**
```bash
curl http://localhost:8420/strategy/current
```

---

### POST /strategy/override

Override the current strategy action. The override persists until cleared or the FSM transitions.

**Request:** `StrategyOverrideRequest`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| action | string | Yes | Action to force (e.g., "attack", "defend", "explore", "retreat", "heal") |

**Response:**

| Field | Type | Description |
|-------|------|-------------|
| status | string | "override_set" |
| action | string | The override action |

**Example:**
```bash
curl -X POST http://localhost:8420/strategy/override \
  -H "Content-Type: application/json" \
  -d '{"action": "retreat"}'
```

---

## System

Health check and full state endpoints.

### GET /health

API health check.

**Request:** None

**Response:** `HealthResponse`

| Field | Type | Description |
|-------|------|-------------|
| status | string | "ok" |
| version | string | API version (e.g., "0.1.0") |

**Example:**
```bash
curl http://localhost:8420/health
```

---

### GET /state/full

Full bot state combining FSM and perception.

**Request:** None

**Response:** `BotFullStateResponse`

| Field | Type | Description |
|-------|------|-------------|
| brain_state | string | Current FSM state |
| perception | PerceptionStateResponse \| null | Latest perception snapshot (null if not yet available) |
| score | object \| null | Score data (null if not tracked) |

**Example:**
```bash
curl http://localhost:8420/state/full
```

---

## WebSocket

Real-time bot state streaming over WebSocket.

### WS /ws/state

Streams `SituationalAwareness` JSON at configurable frequency (default 3 Hz).

**Connection:**
```bash
websocat ws://localhost:8420/ws/state
```

**Configuration:**
- `api_ws_hz`: Update frequency in Hz (default: 3.0, set via `OA_API_WS_HZ`)
- `api_ws_max_connections`: Maximum concurrent connections (default: 5, set via `OA_API_WS_MAX_CONNECTIONS`)

**Message format** (when perception data available):
```json
{
  "tick": 1234,
  "timestamp": 1712345678.9,
  "health": 100,
  "armor": 50,
  "ammo": 25,
  "weapon": "railgun",
  "is_alive": true,
  "disposition": "healthy",
  "enemies_visible": 1,
  "current_area": 42,
  "has_path": true,
  "is_stuck": false,
  "under_attack": false,
  "pos": [512.0, 256.0, 64.0],
  "yaw": 180.0,
  "nav_target": "RedArmor"
}
```

**Heartbeat** (when no perception data):
```json
{"type": "waiting"}
```

**Connection limit:** When the maximum connection count is reached, new connections receive WebSocket close code `1013` (Try Again Later).

---

## Metrics

Prometheus metrics endpoint for monitoring and alerting.

### GET /metrics

Returns metrics in Prometheus text exposition format.

**Available metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `bot_perception_fps` | Gauge | Perception pipeline frames per second |
| `bot_kills_total` | Counter | Total kills since startup |
| `bot_deaths_total` | Counter | Total deaths since startup |
| `bot_llm_latency_seconds` | Histogram | LLM strategy call latency (buckets: 0.5s, 1s, 2s, 4s, 8s, 15s) |
| `bot_stuck_total` | Counter | Times the bot got stuck |
| `bot_tick_duration_seconds` | Histogram | Game tick duration (buckets: 10ms, 20ms, 30ms, 50ms, 80ms, 100ms) |

**Example:**
```bash
curl http://localhost:8420/metrics
```

**Response format:** Prometheus text exposition (`text/plain; version=0.0.4`)

```
# HELP bot_perception_fps Perception pipeline FPS
# TYPE bot_perception_fps gauge
bot_perception_fps 15.2

# HELP bot_kills_total Total kills
# TYPE bot_kills_total counter
bot_kills_total 7.0

# HELP bot_llm_latency_seconds LLM strategy call latency
# TYPE bot_llm_latency_seconds histogram
bot_llm_latency_seconds_bucket{le="0.5"} 0.0
bot_llm_latency_seconds_bucket{le="4.0"} 3.0
...
```

**Note:** The `/metrics` endpoint is mounted as a separate ASGI sub-application using `prometheus_client.make_asgi_app()`.
