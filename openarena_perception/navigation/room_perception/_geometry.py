"""Phase 13: shared geometry helpers for room perception detectors.

Private module -- no public exports. Both corner_detector.py and
doorway_detector.py import from here so the math lives in exactly one place.
"""
from __future__ import annotations

import math
from typing import Tuple

from openarena_perception.navigation.room_perception.types import Wall


def nearest_endpoints(
    w1: Wall, w2: Wall
) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
    """Return the closest endpoint pair (e1, e2, distance) between two walls."""
    ends_1 = [(w1.x1, w1.y1), (w1.x2, w1.y2)]
    ends_2 = [(w2.x1, w2.y1), (w2.x2, w2.y2)]
    best: Tuple[Tuple[float, float], Tuple[float, float], float] = (
        ends_1[0],
        ends_2[0],
        float("inf"),
    )
    for e1 in ends_1:
        for e2 in ends_2:
            d = math.hypot(e1[0] - e2[0], e1[1] - e2[1])
            if d < best[2]:
                best = (e1, e2, d)
    return best


def angle_between(w1: Wall, w2: Wall) -> float:
    """Return the unsigned angle (degrees, 0..180) between two wall directions."""
    a1 = math.degrees(math.atan2(w1.y2 - w1.y1, w1.x2 - w1.x1))
    a2 = math.degrees(math.atan2(w2.y2 - w2.y1, w2.x2 - w2.x1))
    return abs(((a1 - a2 + 180) % 360) - 180)
