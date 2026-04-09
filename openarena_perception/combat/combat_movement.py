"""Combat movement patterns (van Waveren thesis Section 13.3).

Circle-strafing, dodging, and positioning based on weapon range.
Extracted from root-level combat.py in Phase 4.
"""

from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING, Optional

from .weapons import WEAPONS

if TYPE_CHECKING:
    from .humanize import HumanizationConfig


class CombatMover:
    """
    Combat movement controller.
    Handles circle-strafing, dodging, positioning based on weapon range.
    Optionally injects movement variability from HumanizationConfig.
    """

    def __init__(
        self,
        humanize_config: HumanizationConfig | None = None,
    ) -> None:
        self._strafe_dir = 1      # 1=right, -1=left
        self._last_switch = 0.0
        self._switch_interval = 0.6
        self._jump_chance = 0.25
        self._last_jump = 0.0
        self._humanize_config = humanize_config

    @property
    def corner_overshoot_px(self) -> float:
        """Corner overshoot in pixels for NavBehavior consumption."""
        if self._humanize_config is not None:
            return self._humanize_config.corner_overshoot_px
        return 0.0

    def get_movement(
        self,
        enemy_distance: float,
        weapon: Optional[str],
        skill: float = 0.7,  # 0.0=stand still, 1.0=expert movement
    ) -> dict:
        """
        Get combat movement commands.
        Returns dict with keys: forward, back, strafe_left, strafe_right, jump
        """
        now = time.time()
        info = WEAPONS.get(weapon) if weapon else None
        optimal = info.optimal_range if info else 400

        result = {
            "forward": False,
            "back": False,
            "strafe_left": False,
            "strafe_right": False,
            "jump": False,
        }

        if skill < 0.2:
            # Low skill: stand and shoot
            return result

        # Positioning: move toward/away to reach optimal range
        if enemy_distance > optimal * 1.3:
            result["forward"] = True
        elif enemy_distance < optimal * 0.6:
            result["back"] = True

        if skill < 0.5:
            # Medium skill: move back and forth only
            return result

        # High skill: circle strafe
        if now - self._last_switch > self._switch_interval:
            if random.random() < 0.4:
                self._strafe_dir *= -1
            self._last_switch = now
            # Vary timing to be unpredictable
            lo, hi = 0.3, 0.8
            if self._humanize_config is not None:
                noise = self._humanize_config.strafe_timing_noise
                lo -= noise / 2
                hi += noise / 2
            self._switch_interval = max(0.15, min(1.5, random.uniform(lo, hi)))

        # Path deviation: occasionally invert strafe direction (HUMN-03)
        strafe_dir = self._strafe_dir
        if (
            self._humanize_config is not None
            and random.random() < self._humanize_config.path_deviation_chance
        ):
            strafe_dir *= -1

        if strafe_dir > 0:
            result["strafe_right"] = True
        else:
            result["strafe_left"] = True

        # Expert: random jumps
        if skill > 0.7 and now - self._last_jump > 0.8:
            if random.random() < self._jump_chance:
                result["jump"] = True
                self._last_jump = now

        return result
