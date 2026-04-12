# openarena_perception

Pixel-based game state perception loop for **OpenArena (ioquake3)**,
optimized for **Raspberry Pi (Raspbian, X11)**.

Produces a structured `GameState` every tick:

```
HP:87 | AR:50 | AMO:32 | WPN:Railgun | F/D:5/2 | ENE:1 | 🎯ON_TARGET
```

---

## Architecture

```
ScreenCapture (mss)
      │
      ▼
 ┌────────────┐   ┌─────────────────────────────────┐
 │  HUDParser │   │         WorldParser              │
 │            │   │                                  │
 │  health    │   │  HSV threshold → enemy mask      │
 │  armor     │   │  Contour analysis → BoundingBox  │
 │  ammo      │   │  Screen-angle, distance estimate │
 │  weapon    │   │  Crosshair overlap detection     │
 │  frags     │   └─────────────────────────────────┘
 │  deaths    │
 └────────────┘
      │                    │
      └────────────────────┘
                │
                ▼
           GameState
         (dataclass, JSON-serializable)
                │
                ▼
        Your Agent / OpenClaw
```

---

## Quick Install (Pi)

```bash
# System dependencies
sudo apt update
sudo apt install -y tesseract-ocr xdotool python3-pip

# Python packages
pip install -r requirements.txt
```

---

## Critical OpenArena Setup

**These cvars make detection orders of magnitude more reliable.**
Add to `~/.openarena/baseoa/autoexec.cfg`:

```
// Force enemy model skins to solid red — enables reliable HSV detection
seta cg_enemyColors "ff0000"
seta cg_forceModel "1"

// Run in windowed mode so mss can capture the window cleanly
seta r_fullscreen "0"
seta r_mode "4"          // 800x600  (use 6 for 1024x768, -1 for custom)

// Optional: reduce visual clutter for cleaner detection
seta r_picmip "2"        // lower texture detail
seta cg_drawGun "1"      // keep weapon visible for template matching

// Ensure HUD is visible
seta cg_draw2D "1"
seta cg_drawFPS "0"      // disable FPS counter (can confuse HUD OCR)
```

After setting these, **verify** by running the ROI debugger (see Calibration below).

---

## Usage

### 1 — Sync (simple loop)

```python
from openarena_perception import build_config, PerceptionLoop

cfg  = build_config("800x600")          # or 1024x768, 1280x720, etc.
loop = PerceptionLoop(cfg, target_fps=20)

with loop:
    while True:
        state = loop.tick()
        print(state.summary())
        # state.health, state.enemies, state.crosshair_on_enemy ...
```

### 2 — Async (agent integration)

```python
from openarena_perception import build_config, PerceptionLoop, GameState

async def on_state(state: GameState):
    if state.crosshair_on_enemy and state.ammo > 0:
        await agent.fire()
    elif state.enemies:
        await agent.aim_at(state.nearest_enemy.screen_angle)

cfg  = build_config("800x600")
loop = PerceptionLoop(cfg, on_state=on_state, target_fps=20)
await loop.run_async()
```

### 3 — Minimal example with decision stub

```bash
python openarena_perception/example_agent.py --res 800x600 --fps 20
```

---

## Calibration (Required First Run)

The default ROI coordinates are tuned for OA's default HUD at 800x600.
**Always verify with the ROI debugger before deploying.**

```bash
# With OA running at 800x600:
python -m openarena_perception.tools.roi_debugger --res 800x600

# Controls:
#   H  — toggle HUD ROI boxes
#   E  — toggle enemy color mask
#   S  — save frame to debug_frame.png
#   Q  — quit
```

Adjust `DEFAULT_ROIS` in `config.py` until the colored rectangles
align with the health/armor/ammo digits on screen.

---

## Weapon Template Creation

Weapon detection uses template matching. To create templates:

1. Run the ROI debugger and press **S** while each weapon is equipped.
2. Open `debug_frame.png`, manually crop the weapon icon region.
3. Save as `weapon_templates/<weapon_name>.png`
   (e.g., `weapon_templates/railgun.png`).

Valid names: `gauntlet`, `machinegun`, `shotgun`, `grenade`, `rocket`,
`lightning`, `railgun`, `plasma`, `bfg`.

---

## GameState Reference

```python
state.health          # int | None  — 0-200
state.armor           # int | None  — 0-200
state.ammo            # int | None  — 0-999
state.weapon          # str | None  — "Railgun", "Rocket Launcher", etc.
state.frags           # int | None
state.deaths          # int | None
state.enemies         # List[EnemyContact]
state.crosshair_on_enemy  # bool
state.nearest_enemy   # EnemyContact | None  (largest pixel mass)
state.low_health      # bool  (health < 30)
state.low_ammo        # bool  (ammo < 10)
state.is_alive        # bool
state.to_dict()       # JSON-serializable dict
state.summary()       # one-line string

# EnemyContact fields:
enemy.bbox             # BoundingBox(x, y, w, h, cx, cy)
enemy.screen_angle     # float — degrees from crosshair (0=up, CW+)
enemy.distance_estimate  # "near" | "mid" | "far"
enemy.confidence       # 0.0–1.0
enemy.pixel_mass       # raw pixel count
```

---

## Performance on Pi 4

| Component       | Typical time |
|-----------------|-------------|
| Screen capture  | 8–15 ms     |
| Enemy detection | 10–20 ms    |
| HUD OCR (all)   | 25–60 ms    |
| **Total tick**  | **45–95 ms → 10–22 FPS** |

**Tips to hit 20 FPS:**
- Run OA at 800x600 (smaller frame = faster capture + CV)
- Use `--mode window` (captures only the game window, not full desktop)
- Reduce OCR upscale: `cfg = build_config("800x600", ocr_upscale=2)`
- If enemy detection is sufficient, disable weapon OCR
  (set `weapon_templates_dir` to a nonexistent path)

---

## Notes on Minimap

OpenArena (base) has **no minimap/radar**. If you add mods that include
a minimap (e.g., CPMA, Generations Arena), add a custom `minimap_roi`
in `config.py` and a parser in `hud_parser.py`.

---

## Integration with OpenClaw

```python
# In your OpenClaw agent node, import and wire:
from openarena_perception import build_config, PerceptionLoop, GameState

cfg  = build_config("800x600")
loop = PerceptionLoop(cfg, on_state=openclaw_dispatch, target_fps=20)
asyncio.ensure_future(loop.run_async())
```

`openclaw_dispatch` receives a `GameState` and can call any registered
MCP tool (mouse move, key press, etc.) based on the parsed state.
