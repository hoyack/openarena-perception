# Configuration Guide

OpenArena Perception uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for type-safe configuration with a clear priority chain.

## Configuration Overview

### Priority Chain

Configuration values are resolved in this order (highest priority first):

1. **Environment variables** -- prefix `OA_` (e.g., `OA_SCREEN_W=1024`)
2. **`.env` file** -- dotenv file in the project root
3. **`bot.toml`** -- TOML configuration file in the project root
4. **Defaults** -- hardcoded in `BotSettings` class

A value set via environment variable always wins over the same key in `.env` or `bot.toml`.

### Environment Variable Naming

All environment variables use the `OA_` prefix. The variable name is the uppercase version of the setting name:

| Setting | Env Var |
|---------|---------|
| `screen_w` | `OA_SCREEN_W` |
| `ollama_model` | `OA_OLLAMA_MODEL` |
| `skill_level` | `OA_SKILL_LEVEL` |

### Example `.env` File

```env
# Display
OA_SCREEN_W=800
OA_SCREEN_H=600

# Game connection
OA_PIPE_PATH=/tmp/openarena_pipe
OA_RCON_PASSWORD=<your-password>
OA_RCON_PORT=27960

# LLM
OA_OLLAMA_MODEL=gemma3:4b
OA_OLLAMA_BASE_URL=http://localhost:11434
OA_LLM_ENABLED=true

# Performance
OA_TICK_BUDGET_MS=50
OA_TARGET_FPS=15

# Humanization
OA_SKILL_LEVEL=3
OA_PERSONALITY=balanced
```

### Example `bot.toml` File

```toml
# OpenArena Perception -- default configuration
# Override with .env or OA_* environment variables

[bot]
screen_w = 800
screen_h = 600
pipe_path = "/tmp/openarena_pipe"
rcon_port = 27960
enemy_color_mode = "red"
ocr_upscale = 3
enemy_min_area = 200
ollama_model = "gemma3:4b"
ollama_base_url = "http://localhost:11434"
llm_enabled = true
map_name = "dm4ish"
aas_dir = "maps"
tick_budget_ms = 50
target_fps = 15
log_json = true
log_level = "INFO"
```

---

## Configuration Parameters

All parameters are defined in `openarena_perception/settings.py` as fields on the `BotSettings` class.

### Display

| Parameter | Env Var | Type | Default | Description |
|-----------|---------|------|---------|-------------|
| `screen_w` | `OA_SCREEN_W` | `int` | `800` | Game window width in pixels. Must match the actual OpenArena resolution. |
| `screen_h` | `OA_SCREEN_H` | `int` | `600` | Game window height in pixels. Must match the actual OpenArena resolution. |

### Game Connection

| Parameter | Env Var | Type | Default | Description |
|-----------|---------|------|---------|-------------|
| `pipe_path` | `OA_PIPE_PATH` | `str` | `/tmp/openarena_pipe` | Path to the named pipe for sending commands to the game engine. |
| `rcon_password` | `OA_RCON_PASSWORD` | `str` | `""` (empty) | RCON password for remote console queries. Set this to match your server config. |
| `rcon_port` | `OA_RCON_PORT` | `int` | `27960` | UDP port for RCON communication with the game server. |

### Perception

| Parameter | Env Var | Type | Default | Description |
|-----------|---------|------|---------|-------------|
| `enemy_color_mode` | `OA_ENEMY_COLOR_MODE` | `str` | `"red"` | Enemy team color for HSV detection. Set to `"red"` or `"blue"` depending on which team the bot is fighting against. |
| `ocr_upscale` | `OA_OCR_UPSCALE` | `int` | `3` | Upscale factor applied to HUD regions before Tesseract OCR. Higher values improve accuracy but cost more CPU. |
| `enemy_min_area` | `OA_ENEMY_MIN_AREA` | `int` | `200` | Minimum contour area (in pixels) to consider as an enemy detection. Filters out noise. |

### LLM

| Parameter | Env Var | Type | Default | Description |
|-----------|---------|------|---------|-------------|
| `ollama_model` | `OA_OLLAMA_MODEL` | `str` | `"gemma3:4b"` | Ollama model name for strategic decisions. Smaller models respond faster; larger models make better decisions. |
| `ollama_base_url` | `OA_OLLAMA_BASE_URL` | `str` | `"http://localhost:11434"` | Base URL for the Ollama API server. |
| `llm_enabled` | `OA_LLM_ENABLED` | `bool` | `true` | Enable or disable LLM strategic reasoning. When disabled, the bot uses rule-based decision-making only. |

### Navigation

| Parameter | Env Var | Type | Default | Description |
|-----------|---------|------|---------|-------------|
| `map_name` | `OA_MAP_NAME` | `str` | `"dm4ish"` | Current map name. Used to load the correct AAS navigation file. |
| `aas_dir` | `OA_AAS_DIR` | `str` | `"maps"` | Directory containing AAS (Area Awareness System) navigation mesh files. |

### Performance

| Parameter | Env Var | Type | Default | Description |
|-----------|---------|------|---------|-------------|
| `tick_budget_ms` | `OA_TICK_BUDGET_MS` | `int` | `50` | Maximum milliseconds allowed per perception tick. The pipeline will skip non-critical detectors if the budget is exceeded. |
| `target_fps` | `OA_TARGET_FPS` | `int` | `15` | Target frames per second for the perception loop. Pi 4 typically achieves 10-15 FPS; Pi 5 can reach 20+. |

### Logging

| Parameter | Env Var | Type | Default | Description |
|-----------|---------|------|---------|-------------|
| `log_json` | `OA_LOG_JSON` | `bool` | `true` | Output logs in JSON format (for machine parsing) or human-readable format. |
| `log_level` | `OA_LOG_LEVEL` | `str` | `"INFO"` | Logging verbosity. One of: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

### Game Log

| Parameter | Env Var | Type | Default | Description |
|-----------|---------|------|---------|-------------|
| `game_log_path` | `OA_GAME_LOG_PATH` | `str` | `"~/.openarena/baseoa/games.log"` | Path to the Q3 server game log file. Used for sound awareness (kill/hit/pickup events). |
| `sound_poll_interval` | `OA_SOUND_POLL_INTERVAL` | `int` | `8` | Poll the game log every N perception ticks. At 15 FPS, 8 ticks is approximately 2 Hz. |

### Humanization

| Parameter | Env Var | Type | Default | Description |
|-----------|---------|------|---------|-------------|
| `skill_level` | `OA_SKILL_LEVEL` | `int` | `3` | Unified skill difficulty (1-5) affecting aim noise, reaction time, hesitation, and decision quality. Validated: must be between 1 and 5. |
| `personality` | `OA_PERSONALITY` | `str` | `"balanced"` | Bot personality preset. One of: `aggressive`, `cautious`, `balanced`, `grudge`. Affects combat aggression, caution, weapon preference, and grudge tracking. |

### Database

| Parameter | Env Var | Type | Default | Description |
|-----------|---------|------|---------|-------------|
| `db_path` | `OA_DB_PATH` | `str` | `"~/.openarena/bot.db"` | Path to the SQLite database file for persistent state (surveys, maps, metrics). |

### API

| Parameter | Env Var | Type | Default | Description |
|-----------|---------|------|---------|-------------|
| `api_host` | `OA_API_HOST` | `str` | `"127.0.0.1"` | Host address for the FastAPI server. Use `0.0.0.0` to allow external connections. |
| `api_port` | `OA_API_PORT` | `int` | `8420` | Port for the FastAPI server. |
| `api_ws_hz` | `OA_API_WS_HZ` | `float` | `3.0` | WebSocket update frequency in Hz. How often the bot state is pushed to connected WebSocket clients. |
| `api_ws_max_connections` | `OA_API_WS_MAX_CONNECTIONS` | `int` | `5` | Maximum simultaneous WebSocket connections. New connections beyond this limit are rejected with close code 1013. |

---

## Subsystem Configurations

Beyond the central `BotSettings`, several subsystems have their own configuration dataclasses. These are constructed in code (not from env vars) but are tunable by modifying constructor arguments or using factory methods.

### PerceptionPipelineConfig

**File:** `openarena_perception/perception/config.py`

Controls tick-level rate limiting for the perception pipeline. Detectors that are expensive (like OCR) run less frequently than cheap ones (like color detection).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hud_ocr_interval` | `int` | `30` | Run HUD OCR every N ticks. At 15 FPS, 30 ticks is ~2 seconds. Tesseract takes ~1800ms per call. |
| `motion_interval` | `int` | `2` | Run motion detection every N ticks. |
| `tracker_interval` | `int` | `2` | Run multi-object tracker every N ticks. |
| `anomaly_interval` | `int` | `3` | Run anomaly detection every N ticks. |
| `combat_tracker_interval` | `int` | `1` | Tracker interval during combat (every tick for maximum responsiveness). |
| `combat_anomaly_enabled` | `bool` | `false` | Whether to run anomaly detection during combat. Disabled by default to save CPU. |
| `sound_poll_interval` | `int` | `8` | Poll game log every N ticks (~2 Hz at 15 FPS). |
| `reset_on_death` | `bool` | `true` | Reset tracker state when the bot dies. |

**Factory method:** `PerceptionPipelineConfig.from_timescale(ts)` derives intervals from a `TimescaleConfig` instance.

### TimescaleConfig

**File:** `openarena_perception/tactics/timescale.py`

Defines the multi-timescale decision architecture -- explicit Hz rates for each cognitive layer. The bot operates at multiple speeds: fast reflexes, medium-speed tactics, and slow strategic decisions.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `perception_hz` | `float` | `15.0` | Perception loop frequency. Set by hardware capability. |
| `reflex_hz` | `float` | `15.0` | Reflex layer (dodge, retreat) runs at perception rate. |
| `combat_hz` | `float` | `15.0` | Combat layer (aim, fire, weapon switch) runs at perception rate. |
| `tactics_hz` | `float` | `15.0` | Tactical FSM transitions run at perception rate. |
| `commander_hz` | `float` | `0.33` | Commander goal selection (~every 3 seconds). |
| `strategy_hz` | `float` | `0.2` | LLM strategy calls (~every 5 seconds, bounded by LLM latency). |
| `sound_poll_hz` | `float` | `2.0` | Game log polling frequency. |
| `item_timing_hz` | `float` | `1.0` | Item respawn prediction recalculation. |

**Helper methods:**
- `interval_seconds(layer)` -- returns minimum seconds between calls
- `ticks_per_call(layer, base_hz)` -- returns tick interval for rate limiting

### HumanizationConfig

**File:** `openarena_perception/combat/humanize.py`

All humanization parameters derived from skill level. Use `HumanizationConfig.from_skill_level(1-5)` to construct.

| Parameter | Type | Skill 1 (Novice) | Skill 3 (Default) | Skill 5 (Expert) | Description |
|-----------|------|------|---------|------|-------------|
| `aim_noise_base` | `float` | 25.0 | 12.0 | 4.0 | Base Perlin noise amplitude for aim drift (pixels). |
| `aim_noise_velocity_scale` | `float` | 0.15 | 0.08 | 0.03 | How much target velocity increases aim noise. |
| `aim_noise_distance_scale` | `float` | 0.10 | 0.06 | 0.02 | How much target distance increases aim noise. |
| `aim_noise_turn_scale` | `float` | 0.08 | 0.04 | 0.02 | How much bot turn rate increases aim noise. |
| `max_accuracy` | `float` | 0.25 | 0.50 | 0.70 | Hard cap on accuracy (sliding window feedback). 70% is the absolute ceiling. |
| `reaction_time_min` | `float` | 0.35s | 0.20s | 0.12s | Fastest possible reaction to new threats. |
| `reaction_time_max` | `float` | 0.55s | 0.35s | 0.22s | Slowest reaction time. Actual value is randomized in range. |
| `reaction_surprise_bonus` | `float` | 0.15s | 0.10s | 0.04s | Extra delay when surprised (enemy appears suddenly). |
| `hesitation_min` | `float` | 0.25s | 0.12s | 0.05s | Minimum hesitation before state transitions. |
| `hesitation_max` | `float` | 0.50s | 0.30s | 0.12s | Maximum hesitation before state transitions. |
| `corner_overshoot_px` | `float` | 40.0 | 20.0 | 6.0 | Pixels of overshoot when turning corners. |
| `path_deviation_chance` | `float` | 0.30 | 0.12 | 0.03 | Probability of deviating from optimal path. |
| `strafe_timing_noise` | `float` | 0.3 | 0.18 | 0.06 | Noise added to strafe direction change intervals. |
| `decision_noise` | `float` | 0.40 | 0.20 | 0.05 | Probability of making a suboptimal tactical decision. |

### PersonalityProfile

**File:** `openarena_perception/combat/humanize.py`

Bot personality presets that affect combat behavior and decision preferences.

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Preset name identifier. |
| `aggression` | `float` | Aggression level (0.0-1.0). Higher values push the bot to engage. |
| `caution` | `float` | Caution level (0.0-1.0). Higher values make the bot retreat and avoid danger. |
| `weapon_preference` | `str` | Preferred weapon type (e.g., `"rocket"`, `"railgun"`, `"lightning"`). |
| `grudge_factor` | `float` | Grudge tracking intensity (0.0-1.0). Higher values make the bot target players who killed it. |

**Available presets:**

| Preset | Aggression | Caution | Weapon | Grudge |
|--------|-----------|---------|--------|--------|
| `aggressive` | 0.9 | 0.2 | rocket | 0.6 |
| `cautious` | 0.3 | 0.8 | railgun | 0.2 |
| `balanced` | 0.5 | 0.5 | lightning | 0.4 |
| `grudge` | 0.7 | 0.3 | rocket | 0.9 |

---

## Tuning Guide

### Pi Hardware Tuning

**CPU overload symptoms:** FPS drops below 10, tick budget exceeded warnings in logs, laggy bot movement.

- **Lower `tick_budget_ms`** from 50 to 30-40. The pipeline will skip non-critical detectors (anomaly, motion) when the budget is tight.
- **Lower `target_fps`** from 15 to 10-12. This reduces CPU pressure from screen capture and processing.
- **Increase `hud_ocr_interval`** in `PerceptionPipelineConfig` from 30 to 45-60. OCR is the most expensive single operation (~1800ms).
- **Disable `combat_anomaly_enabled`** (default is already `false`). Anomaly detection during combat wastes cycles that should go to tracking and aiming.
- **Set `OA_LLM_ENABLED=false`** if not running Ollama locally. LLM calls consume memory and CPU even when waiting for responses.

**Pi 4 vs Pi 5:**
- Pi 4: Expect 10-12 FPS. Use `tick_budget_ms=40`, `target_fps=10`.
- Pi 5: Expect 15-20 FPS. Default settings work well. Can increase `target_fps=20` if stable.

### Bot Difficulty Tuning

The `skill_level` parameter (1-5) is the primary difficulty control. It affects all humanization subsystems simultaneously:

| Skill Level | Name | Aim Noise | Reaction Time | Max Accuracy | Decision Noise |
|-------------|------|-----------|---------------|--------------|----------------|
| 1 | Novice | 25px drift | 350-550ms | 25% | 40% bad calls |
| 2 | Beginner | 18px drift | 280-450ms | 35% | 30% bad calls |
| 3 | Intermediate | 12px drift | 200-350ms | 50% | 20% bad calls |
| 4 | Advanced | 7px drift | 150-280ms | 60% | 10% bad calls |
| 5 | Expert | 4px drift | 120-220ms | 70% cap | 5% bad calls |

The `personality` parameter adjusts combat style independently of skill:
- `aggressive` -- rushes enemies, prefers rockets, moderate grudge
- `cautious` -- maintains distance, prefers railgun, low grudge
- `balanced` -- adapts to situation, prefers lightning gun
- `grudge` -- hunts players who killed it, very persistent

### LLM Model Selection

The `ollama_model` setting controls which model handles strategic decisions (goal selection, threat assessment, tactical adaptation).

| Model | Speed (Pi 5) | Quality | Best For |
|-------|-------------|---------|----------|
| `gemma3:1b` | ~1-2s | Basic | Testing, low-resource Pi 4 |
| `gemma3:4b` | ~3-4s | Good | Default, balanced speed/quality |
| `gemma4:12b` | ~8-12s | Very Good | Desktop or Pi 5 with patience |
| `gemma4:31b` | ~20-30s | Excellent | Desktop only, best decisions |

**Recommendations:**
- For Pi 4: Use `gemma3:1b` or disable LLM entirely (`OA_LLM_ENABLED=false`)
- For Pi 5: Use `gemma3:4b` (default) -- good balance of speed and decision quality
- For desktop: Use `gemma4:12b` or larger for best strategic play
- Strategy calls happen every ~5 seconds (`strategy_hz=0.2`), so a 3-4 second response is fine
