"""RoomConfig — rendering parameters for the wireframe room.

Source: PRD §4.5 with CONTEXT.md §Decisions additions for depth-curve and effects.
Convention: mirrors openarena_perception.models.SituationalAwareness (frozen+slots).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True, slots=True)
class RoomConfig:
    # Canvas
    width: int = 960
    height: int = 600

    # Room frame (world-space box around the camera, per PRD §4.2)
    room_width: float = 10.0
    room_height: float = 6.0
    room_depth: float = 20.0
    grid_lines_x: int = 16
    grid_lines_y: int = 10
    grid_lines_z: int = 20

    # Camera
    fov_deg: float = 90.0
    cam_x: float = 0.0
    cam_y: float = 0.0
    cam_z: float = 0.0
    camera_height: float = 26.0   # Q3 DEFAULT_VIEWHEIGHT standing eye offset

    # Palette (BGR order — see Pitfall 5)
    bg_color: Tuple[int, int, int] = (0, 0, 0)
    grid_color: Tuple[int, int, int] = (180, 180, 180)
    accent_color: Tuple[int, int, int] = (0, 255, 100)

    # Depth curve (CONTEXT.md §Decisions)
    near_color: Tuple[int, int, int] = (255, 255, 255)
    far_color: Tuple[int, int, int] = (40, 60, 80)
    warning_color: Tuple[int, int, int] = (0, 80, 255)
    proximity_threshold: float = 2.0
    fade_power: float = 0.6
    max_depth: float = 20.0  # color curve reference; not coupled to room_depth

    # Effects (PRD §7)
    glow: bool = True
    scanlines: bool = False
    glow_radius: int = 9
    glow_strength: float = 0.3
    scanline_spacing: int = 3
    scanline_strength: float = 0.15

    # Toggles
    hud: bool = True
