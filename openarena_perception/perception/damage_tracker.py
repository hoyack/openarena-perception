"""
damage_tracker.py — Detect when we take damage and respond.

In Q3, when you take damage:
  - Health drops between frames
  - A red damage indicator flash appears on screen
  - The direction indicator shows which side the damage came from

We detect damage by monitoring health via HUD OCR or viewpos,
then scan the frame for the red damage flash direction to
determine where the attacker is.

When taking damage: snap aim toward attacker, fire, strafe to dodge.
This is reactive combat — we fight back when attacked.
"""

import cv2
import numpy as np
import time
import logging
from typing import Optional, Tuple

log = logging.getLogger(__name__)


class DamageTracker:
    """
    Detects damage events and determines attacker direction.
    """

    def __init__(self):
        self._last_health: Optional[int] = None
        self._taking_damage = False
        self._damage_time = 0.0
        self._damage_direction = 0  # -1=left, 0=front, 1=right
        self._combat_timeout = 3.0  # stay in combat mode for N seconds after damage

    def update(self, health: Optional[int], frame: Optional[np.ndarray]) -> bool:
        """
        Update with current health and frame.
        Returns True if we're in "under attack" mode.
        """
        now = time.time()

        # Health-based damage detection
        if health is not None and self._last_health is not None:
            if health < self._last_health:
                damage = self._last_health - health
                self._taking_damage = True
                self._damage_time = now
                log.info("DAMAGE! -%d HP (now %d)", damage, health)

                # Detect damage direction from frame (red flash)
                if frame is not None:
                    self._damage_direction = self._detect_damage_direction(frame)

        self._last_health = health

        # Stay in combat mode for a few seconds after taking damage
        if self._taking_damage and now - self._damage_time > self._combat_timeout:
            self._taking_damage = False

        return self._taking_damage

    @property
    def is_under_attack(self) -> bool:
        return self._taking_damage

    @property
    def attacker_direction(self) -> int:
        """Direction of last damage: -1=left, 0=front/unknown, 1=right"""
        return self._damage_direction

    @property
    def seconds_since_damage(self) -> float:
        if self._damage_time == 0:
            return float('inf')
        return time.time() - self._damage_time

    def _detect_damage_direction(self, frame: np.ndarray) -> int:
        """
        Q3 shows a red flash on the side the damage came from.
        Compare red intensity on left vs right side of frame.
        """
        h, w = frame.shape[:2]
        mid_y1, mid_y2 = int(h * 0.2), int(h * 0.8)

        # Extract red channel intensity in left vs right strips
        left_strip = frame[mid_y1:mid_y2, :w//4, 2]  # red channel
        right_strip = frame[mid_y1:mid_y2, 3*w//4:, 2]

        left_red = float(left_strip.mean())
        right_red = float(right_strip.mean())

        # Stronger red flash = damage direction
        diff = right_red - left_red
        if abs(diff) < 5:
            return 0  # front or unknown
        elif diff > 0:
            return 1  # right
        else:
            return -1  # left
