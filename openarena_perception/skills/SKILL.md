# OpenArena Perception -- Skill System

## Three-Layer Skill Hierarchy

Skills compose into three layers, each building on the one below:

```
Mission (goal-directed)
  |-- Behavior (action sequences)
        |-- Action (atomic game commands)
```

### Actions (Layer 1 -- Atomic)

| Skill | Description | Key Params |
|-------|-------------|------------|
| `move` | Move forward or backward | direction, duration |
| `turn` | Turn by degrees (thread-offloaded) | degrees |
| `fire` | Start or stop firing | on |
| `weapon_select` | Select weapon by name | weapon |

### Behaviors (Layer 2 -- Composed Sequences)

| Skill | Description | Composes |
|-------|-------------|----------|
| `patrol` | Patrol through waypoints | move + turn |
| `room_survey` | 360-degree room survey | turn + optional SurveyBehavior |
| `combat_engage` | Engage in combat | CombatEngager delegation |

### Missions (Layer 3 -- Goal-Directed)

| Skill | Description | Composes |
|-------|-------------|----------|
| `explore_map` | Explore the map via patrol | patrol (repeated) |
| `deathmatch` | Hunt and fight enemies | patrol + combat_engage |
| `defend_area` | Defend a map area | patrol (localized) |

## Usage

```python
from openarena_perception.skills.catalog import build_registry

registry = build_registry(ctrl, bridge, engager=engager, survey=survey)
catalog = registry.catalog()  # 10 skills with name, layer, description

result = await registry.execute("patrol", waypoints=[1, 2, 3])
result = await registry.execute("explore_map", max_steps=10)
```

## Skill Protocol

All skills satisfy the `Skill` Protocol (structural typing):
- `name: str` -- unique identifier
- `layer: SkillLayer` -- action / behavior / mission
- `description: str` -- human/LLM-readable description
- `async execute(**params) -> SkillResult` -- run the skill
- `cancel() -> None` -- request cancellation

---

# OpenArena AI Player -- Game-Specific Knowledge

## How to Win

### Architecture
```
Named Pipe (com_pipefile) --> ioquake3 client commands (instant)
RCON UDP ------------------> server state queries (scores, map)
Screen Capture (mss) ------> enemy detection (HSV contours, ~8ms)
                           -> HUD reading (OCR, every ~30 ticks)
Ollama (gemma4:31b-cloud) -> strategic decisions + vision (every ~4s)
```

### Core Principle
**In Quake 3 FFA, aggression wins.** The bot should always be moving forward,
always shooting, always seeking enemies. Don't retreat -- hunt.

### Control Flow
1. **Named pipe** (`~/.openarena/baseoa/oapipe`) injects console commands
   directly into the client buffer with zero overhead: `+forward`, `+attack`,
   `+left`, `-moveleft`, `weapon 7`, etc.
2. **RCON** over UDP (port 27960, password `botctl`) queries scores and
   server state. Round-trip: ~1ms.
3. **Screen capture** via `mss` grabs the game window at 12-15 FPS.
   Enemy detection uses HSV thresholding for red-forced enemy skins.
4. **Aim** uses `+left`/`+right` with dynamic `cl_yawspeed` based on
   how far the enemy is from screen center.

### OpenArena Setup (autoexec.cfg)
```
seta cg_enemyColors "ff0000"    // force enemies red
seta cg_forceModel "1"          // ensure color applies
seta r_fullscreen "0"           // windowed for capture
seta r_mode "4"                 // 800x600
seta r_picmip "2"               // low detail = cleaner detection
seta rconPassword "botctl"      // RCON access
seta sv_cheats "1"              // needed for some commands
seta com_pipefile "oapipe"      // named pipe for command injection
seta cg_drawFPS "0"             // don't confuse OCR
```

### Running
```bash
cd ~/openarena-perception

# Reactive only (no LLM, fastest):
python play.py --launch --no-llm

# With Ollama LLM strategy:
python play.py --launch

# With LLM + vision frames:
python play.py --launch --vision

# Against running OA (start OA manually first):
python play.py --no-llm --fps 12
```

### Tuning for Kills

#### Enemy Detection (config.py)
- `ENEMY_MIN_AREA = 200` -- increase to 400+ to filter small false positives
- `ENEMY_MAX_AREA_FRACTION = 0.15` -- decrease to 0.08 to filter damage flash
- `ENEMY_MORPH_KERNEL = (5, 5)` -- increase to (7,7) for more aggressive noise removal

#### HSV Thresholds (config.py)
- Red detection uses two HSV ranges (red wraps at H=0/180):
  - `enemy_red_lo: (0, 120, 100)-(10, 255, 255)`
  - `enemy_red_hi: (165, 120, 100)-(179, 255, 255)`
- Raise saturation minimum from 120 to 150+ for maps with red textures.

#### Aim (reactive_agent.py)
- `cl_yawspeed` is set dynamically: 120 (close), 250 (medium), 450 (far).
- Fire threshold is `abs_dx < 120` pixels from center.

### Performance (Raspberry Pi 5)
| Component | Time |
|-----------|------|
| Screen capture (mss) | 25-40ms |
| Enemy detection (HSV) | 7-10ms |
| HUD OCR (health+ammo) | ~1800ms (every 30 ticks only) |
| RCON query | ~1ms |
| Pipe command | <0.1ms |
| **Total tick** | **~45ms -> 15-17 FPS** |
