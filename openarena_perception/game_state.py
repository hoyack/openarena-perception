"""
game_state.py — OpenArena GameState data model
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
import time
import numpy as np


@dataclass
class BoundingBox:
    """Screen-space bounding box (pixels)."""
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2

    @property
    def area(self) -> int:
        return self.w * self.h

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h,
                "cx": self.cx, "cy": self.cy}


@dataclass
class EnemyContact:
    """A detected enemy in screen space."""
    bbox: BoundingBox
    confidence: float          # 0.0–1.0 color match confidence
    pixel_mass: int            # number of matching pixels
    screen_angle: float        # degrees from crosshair center (0=center)
    distance_estimate: str     # "near" | "mid" | "far" based on bbox area

    def to_dict(self) -> dict:
        return {
            "bbox": self.bbox.to_dict(),
            "confidence": round(self.confidence, 3),
            "pixel_mass": self.pixel_mass,
            "screen_angle": round(self.screen_angle, 1),
            "distance_estimate": self.distance_estimate,
        }


@dataclass
class GameState:
    """
    Complete game state derived from a single frame.
    All fields are None when detection failed / data unavailable.
    """
    # ── Timing ─────────────────────────────────────────────────────────────
    timestamp: float = field(default_factory=time.time)
    frame_id: int = 0

    # ── Player vitals ───────────────────────────────────────────────────────
    health: Optional[int] = None          # 0–200
    armor: Optional[int] = None           # 0–200
    ammo: Optional[int] = None            # 0–999
    weapon: Optional[str] = None          # weapon name or None

    # ── Score ───────────────────────────────────────────────────────────────
    frags: Optional[int] = None
    deaths: Optional[int] = None

    # ── World perception ────────────────────────────────────────────────────
    enemies: List[EnemyContact] = field(default_factory=list)
    crosshair_on_enemy: bool = False      # True if any enemy bbox overlaps center
    nearest_enemy: Optional[EnemyContact] = None

    # ── Derived flags ───────────────────────────────────────────────────────
    low_health: bool = False              # health < 30
    low_ammo: bool = False               # ammo < 10
    is_alive: bool = True                # health > 0

    # ── Raw frame (optional, for downstream use) ────────────────────────────
    frame: Optional[np.ndarray] = None

    def __post_init__(self):
        if self.health is not None:
            self.low_health = self.health < 30
            self.is_alive = self.health > 0
        if self.ammo is not None:
            self.low_ammo = self.ammo < 10
        if self.enemies:
            self.nearest_enemy = max(self.enemies, key=lambda e: e.pixel_mass)
            cx = self.frame.shape[1] // 2 if self.frame is not None else 0
            cy = self.frame.shape[0] // 2 if self.frame is not None else 0
            self.crosshair_on_enemy = any(e.bbox.contains(cx, cy) for e in self.enemies)

    def to_dict(self, include_frame: bool = False) -> dict:
        d = {
            "timestamp": self.timestamp,
            "frame_id": self.frame_id,
            "health": self.health,
            "armor": self.armor,
            "ammo": self.ammo,
            "weapon": self.weapon,
            "frags": self.frags,
            "deaths": self.deaths,
            "enemies": [e.to_dict() for e in self.enemies],
            "crosshair_on_enemy": self.crosshair_on_enemy,
            "nearest_enemy": self.nearest_enemy.to_dict() if self.nearest_enemy else None,
            "low_health": self.low_health,
            "low_ammo": self.low_ammo,
            "is_alive": self.is_alive,
        }
        if include_frame and self.frame is not None:
            d["frame_shape"] = self.frame.shape
        return d

    def summary(self) -> str:
        parts = [
            f"HP:{self.health or '?'}",
            f"AR:{self.armor or '?'}",
            f"AMO:{self.ammo or '?'}",
            f"WPN:{self.weapon or '?'}",
            f"F/D:{self.frags or 0}/{self.deaths or 0}",
            f"ENE:{len(self.enemies)}",
        ]
        if self.crosshair_on_enemy:
            parts.append("🎯ON_TARGET")
        if self.low_health:
            parts.append("⚠️LOW_HP")
        return " | ".join(parts)
