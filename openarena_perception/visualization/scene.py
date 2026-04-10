"""SceneGeometry — per-frame camera-space 3D primitives for the renderer.

Separates 'what to draw' from 'how to draw'. The AAS backend or any other
depth source produces a SceneGeometry; the renderer consumes it.

Camera-space convention (see projection.world_to_camera):
    +X right, +Y down, +Z forward
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple

Point3 = Tuple[float, float, float]
Segment3 = Tuple[Point3, Point3]
Box = Tuple[str, float, float, float, float, float, float]
# (class_name, x, y, z, w, h, d) — AABB center + full extents.

# PRD §5.2 exact colors, named _BGR to prevent RGB/BGR confusion (Pitfall 5)
OBJECT_COLORS_BGR: Dict[str, Tuple[int, int, int]] = {
    "player":  (255, 50, 50),
    "pickup":  (50, 255, 255),
    "door":    (255, 255, 50),
    "portal":  (255, 255, 50),
    "wall":    (0, 255, 100),
    "static":  (0, 255, 100),
    "unknown": (180, 180, 180),
}


@dataclass(frozen=True, slots=True)
class SceneGeometry:
    """Per-frame 3D primitives in CAMERA space, ready for projection."""
    walls: Tuple[Segment3, ...] = ()
    boxes: Tuple[Box, ...] = ()
