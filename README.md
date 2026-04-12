# OpenArena Perception

AI bot framework for OpenArena (ioquake3) that combines real-time computer vision, AAS pathfinding, LLM strategic reasoning, and a layered skill system into a competitive deathmatch player. Runs on Raspberry Pi 4/5 hardware.

## Requirements

### Hardware

- **Raspberry Pi 5** (recommended) or **Pi 4** (slower, still functional)
- 4 GB RAM minimum, 8 GB recommended for LLM support
- ARM64 (aarch64) — Raspberry Pi OS Bookworm or later
- X11 display server (Wayland not supported — mss screen capture requires X11)

### Software

- **Python 3.11+** (Pi OS Bookworm ships 3.11; 3.12+ recommended)
- **[uv](https://docs.astral.sh/uv/)** package manager
- **OpenArena** (ioquake3) installed and runnable
- **Tesseract OCR** for HUD number parsing
- **xdotool** for window geometry queries

### Optional

- **[Ollama](https://ollama.com/)** with a model like `gemma3:4b` for LLM strategic reasoning (used by the spatial advisor during tours; not required for `--no-vision` mode)
- **Hailo-8L AI Kit** (Pi 5 M.2 HAT) — planned for future YOLO-based player detection, not currently integrated. The bot uses deterministic HSV color thresholding for enemy detection.

## Installation

### 1. Install system dependencies

```bash
sudo apt update
sudo apt install -y openarena tesseract-ocr xdotool
```

### 2. Install uv (if not present)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. Clone and install

```bash
git clone <repo-url> openarena-perception
cd openarena-perception
uv sync              # Install all dependencies from uv.lock
uv sync --group dev  # Also install dev dependencies (pytest, ruff, hypothesis)
```

### 4. Extract map assets

The bot uses AAS (Area Awareness System) files for pathfinding. These ship inside OpenArena's pk3 archives and are extracted on demand — they are not stored in the repo.

```bash
./scripts/extract_maps.sh
```

This extracts AAS and BSP files for `oa_dm1`, `oa_dm2`, and `oa_rpg3dm2` from your local OpenArena install. Default search paths:

- `/usr/lib/openarena/baseoa`
- `/usr/share/games/openarena/baseoa`
- `~/.openarena/baseoa`

Override with `OA_BASEPATH=/your/path ./scripts/extract_maps.sh` or pass the path as an argument.

## OpenArena Configuration

The bot communicates with OpenArena via a **named pipe** (`oapipe`) for sending commands and **RCON** (UDP port 27960) for server queries. Add these settings to `~/.openarena/baseoa/autoexec.cfg`:

```
// Named pipe for bot command injection (required)
seta com_pipefile "oapipe"

// RCON for server queries (required)
seta sv_cheats "1"
seta rconPassword "botctl"

// Windowed mode for screen capture (required)
seta r_fullscreen "0"
seta r_mode "4"              // 800x600

// Force enemy skins to solid red for HSV detection (required)
seta cg_enemyColors "ff0000"
seta cg_forceModel "1"

// Ensure HUD is visible for OCR (required)
seta cg_draw2D "1"
seta cg_drawFPS "0"          // FPS counter confuses HUD OCR

// Optional: reduce visual clutter
seta r_picmip "2"            // lower textures
seta cg_drawGun "1"          // keep weapon visible
```

## Usage

### Launch the game

```bash
# Start OpenArena on oa_dm1 in developer mode
/usr/lib/ioquake3/ioquake3 \
  +set com_basegame baseoa \
  +set fs_basepath /usr/lib/openarena \
  +set com_homepath .openarena \
  +set com_pipefile oapipe \
  +set sv_cheats 1 \
  +set rconPassword botctl \
  +set r_fullscreen 0 \
  +set r_mode 4 \
  +devmap oa_dm1
```

### Run the bot (item tour)

The primary entry point. The bot navigates between weapon and item pickups using AAS pathfinding with vision-assisted wall avoidance.

```bash
uv run python item_tour.py --no-vision    # AAS pathfinding only (no LLM)
uv run python item_tour.py                # Full mode with LLM spatial advisor
uv run python item_tour.py --all          # Visit ALL items (ammo, shards, etc.)
uv run python item_tour.py --loop         # Loop tours indefinitely
uv run python item_tour.py --category weapon  # Weapons only
```

### Run the HUD (observation panel)

A 760x720 pygame window showing three panels: wireframe 3D view, minimap with fitted walls/rooms, and stats/telemetry.

```bash
uv run python open_perception.py                         # Auto-detect AAS from game state
uv run python open_perception.py --aas maps/oa_dm1.aas   # Explicit AAS file
```

The HUD reads state from `./tmp/oa_hud_state.json` (written by `item_tour.py` each tick). Start the tour first, then the HUD.

### FastAPI server (programmatic control)

```bash
uv run uvicorn openarena_perception.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

Provides REST endpoints and WebSocket streaming for combat, navigation, perception, skills, and strategy subsystems. API docs at `http://localhost:8000/docs`.

## Architecture

```
Screen (mss X11 capture)
  |
  v
PerceptionPipeline.tick()
  +-- HUDParser (tesseract OCR) --> health, armor, ammo, weapon, frags
  +-- PlayerDetector (HSV color) --> enemy bounding boxes
  +-- ObjectTracker (histogram)  --> persistent tracking
  +-- WallDetector (edge/color)  --> wall proximity + open direction
  +-- DamageTracker (flash)      --> incoming attack direction
  |
  v
SituationalAwareness (frozen dataclass, 35+ fields)
  |
  v
TacticalFSM (2-5 Hz decision cycle)
  +-- Commander (item targeting, A* routing)
  +-- FightOrFlight (threat assessment)
  +-- Dispatch to combat/navigation behaviors
  |
  v
AimController (PID w/ lead prediction) / Navigator (A* over AAS graph)
  |
  v
VirtualController --> GameBridge
  +-- Named pipe (movement: +forward, +attack, weapon N)
  +-- RCON UDP (server queries: player positions, scores)
```

### Package structure

| Package | Purpose |
|---------|---------|
| `api/` | FastAPI REST + WebSocket control interface |
| `combat/` | Weapon selection, aim controller, engagement logic |
| `memory/` | 3-layer cognitive memory (working, episodic, semantic) backed by SQLite |
| `navigation/` | AAS pathfinding, learned map, room perception (RANSAC wall fitting) |
| `perception/` | Vision pipeline: capture, HUD OCR, player detection, object tracking |
| `reflexes/` | Subsumption arbiter: death handling, stuck escape, fast overrides |
| `skills/` | 3-layer hierarchy: atomic actions, composed behaviors, missions |
| `strategy/` | LLM-powered strategic reasoning via Ollama |
| `tactics/` | Tactical FSM, goal selection, fight-or-flight, timescale management |
| `visualization/` | Wireframe 3D renderer, minimap panel, stats panel |

### Key data files (runtime, not in repo)

| File | Location | Purpose |
|------|----------|---------|
| HUD state | `./tmp/oa_hud_state.json` | Per-tick game state written by tour, read by HUD |
| Learned maps | `~/.openarena/learned_maps/<map>.json` | Per-map navigation memory (wall cells, edge failures, raycasts, fitted rooms) |
| Game log | `~/.openarena/baseoa/games.log` | Q3 console log for sound event parsing |
| Bot config | `bot.toml` / `.env` | Deployment config (pipe path, RCON, LLM model, skill level) |

## Testing

```bash
uv sync --group dev               # Install test dependencies
uv run pytest -q                  # Run all ~779 tests
uv run pytest tests/test_combat.py -v  # Run a specific test file
uv run pytest -k "navigation" -v  # Run tests matching a keyword
```

The test suite includes unit tests, integration tests, and property-based tests (via Hypothesis). Tests that require game map files (`maps/oa_dm1.aas`) skip gracefully if the maps haven't been extracted.

## Performance

Measured on Raspberry Pi 5 (8 GB) at 800x600:

| Component | Typical time | Notes |
|-----------|-------------|-------|
| Screen capture (mss) | 8-15 ms | X11 native, no GPU |
| HUD OCR (tesseract) | 25-60 ms | Health/armor/ammo/weapon/frags |
| Enemy detection (HSV) | 10-20 ms | Color thresholding, no ML |
| Wall detection | 5-10 ms | Forward-scan edge analysis |
| **Full perception tick** | **50-100 ms (10-20 FPS)** | |
| RANSAC line fitting | 20-50 ms | Runs every 3s, not per tick |
| LLM strategic call | ~2500 ms | Runs every ~4s cycle via Ollama |

## Configuration

Environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `OA_PIPE_PATH` | `~/.openarena/baseoa/oapipe` | Named pipe path |
| `OA_RCON_HOST` | `127.0.0.1` | RCON server address |
| `OA_RCON_PORT` | `27960` | RCON UDP port |
| `OA_RCON_PASSWORD` | `botctl` | RCON password |
| `OA_SCREEN_WIDTH` | `800` | Game window width |
| `OA_SCREEN_HEIGHT` | `600` | Game window height |
| `OA_LLM_MODEL` | `gemma3:4b` | Ollama model for strategic reasoning |
| `OA_BASEPATH` | (auto-detect) | OpenArena baseoa directory |

## License

See LICENSE file.
