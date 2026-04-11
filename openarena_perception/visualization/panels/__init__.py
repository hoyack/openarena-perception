"""Open-Perception UI panels subpackage (Phase 12-02).

Each panel is a self-contained pygame renderer taking a HUDState and a
sub-surface. Panels never reach outside the sub-surface they are handed;
all draw coordinates are (0,0)-relative to the passed surface. This keeps
them independently testable under SDL_VIDEODRIVER=dummy (Pitfall 1).

All colors defined here are RGB (pygame native). BGR constants live in
openarena_perception.visualization.scene (OBJECT_COLORS_BGR) and must
never be mixed with these — the RGB_ prefix prevents Pitfall 2.
"""

from __future__ import annotations

# --- TRON / CRT palette (RGB only — see Pitfall 2) ---------------------
RGB_BG = (20, 20, 30)
RGB_GRID = (40, 40, 55)
RGB_PLAYER = (0, 255, 100)
RGB_PLAYER_TRAIL = (0, 120, 50)
RGB_WAYPOINT_DONE = (80, 80, 80)
RGB_WAYPOINT_NEXT = (255, 200, 0)
RGB_WAYPOINT_FUTURE = (100, 100, 150)
RGB_ITEM_WEAPON = (255, 100, 50)
RGB_ITEM_HEALTH = (50, 255, 50)
RGB_ITEM_ARMOR = (255, 255, 50)
RGB_ITEM_POWERUP = (100, 100, 255)
RGB_ROOM_SURVEYED = (40, 60, 40)
RGB_TEXT = (200, 200, 200)
RGB_TEXT_DIM = (120, 120, 140)
RGB_ALERT = (255, 80, 80)
RGB_OK = (80, 255, 80)
RGB_INTENT_CURRENT = (255, 255, 0)
RGB_INTENT_SUB = (255, 255, 255)
RGB_INTENT_HISTORY = (110, 110, 120)
RGB_INTENT_LABEL = (180, 180, 180)
RGB_PROBLEM_WALL = (255, 60, 60)
RGB_PROBLEM_STUCK = (255, 150, 50)
RGB_PROBLEM_PIN = (200, 80, 255)
RGB_PROBLEM_RESPAWN = (80, 220, 255)
RGB_PROBLEM_ADVISOR = (255, 80, 80)
RGB_PAUSE_BORDER = (80, 150, 255)

# --- Derived layout constants (never hardcode HUD_WIDTH — see Pitfall 4)
PANEL_MINIMAP_W = 400
PANEL_WIREFRAME_W = 600
PANEL_STATS_W = 400
PANEL_HEIGHT = 700
HUD_WIDTH = PANEL_MINIMAP_W + PANEL_WIREFRAME_W + PANEL_STATS_W  # 1400
HUD_HEIGHT = PANEL_HEIGHT

from openarena_perception.visualization.panels.minimap import MinimapPanel  # noqa: E402
from openarena_perception.visualization.panels.wireframe import WireframePanel  # noqa: E402
from openarena_perception.visualization.panels.stats import StatsPanel  # noqa: E402

__all__ = [
    "MinimapPanel",
    "StatsPanel",
    "WireframePanel",
    "RGB_BG",
    "RGB_GRID",
    "RGB_PLAYER",
    "RGB_PLAYER_TRAIL",
    "RGB_WAYPOINT_DONE",
    "RGB_WAYPOINT_NEXT",
    "RGB_WAYPOINT_FUTURE",
    "RGB_ITEM_WEAPON",
    "RGB_ITEM_HEALTH",
    "RGB_ITEM_ARMOR",
    "RGB_ITEM_POWERUP",
    "RGB_ROOM_SURVEYED",
    "RGB_TEXT",
    "RGB_TEXT_DIM",
    "RGB_ALERT",
    "RGB_OK",
    "RGB_INTENT_CURRENT",
    "RGB_INTENT_SUB",
    "RGB_INTENT_HISTORY",
    "RGB_INTENT_LABEL",
    "RGB_PROBLEM_WALL",
    "RGB_PROBLEM_STUCK",
    "RGB_PROBLEM_PIN",
    "RGB_PROBLEM_RESPAWN",
    "RGB_PROBLEM_ADVISOR",
    "RGB_PAUSE_BORDER",
    "PANEL_MINIMAP_W",
    "PANEL_WIREFRAME_W",
    "PANEL_STATS_W",
    "PANEL_HEIGHT",
    "HUD_WIDTH",
    "HUD_HEIGHT",
]
