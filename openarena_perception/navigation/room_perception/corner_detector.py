"""Phase 13: Corner detector -- pairwise wall intersection gating.

A corner exists where two fitted walls meet at a non-parallel angle AND
their nearest endpoints are within a proximity threshold (default 32u).
Pure-stdlib, zero new dependencies.
"""
from __future__ import annotations

import itertools
from typing import List

from openarena_perception.navigation.room_perception._geometry import (
    angle_between,
    nearest_endpoints,
)
from openarena_perception.navigation.room_perception.types import Corner, Wall


class CornerDetector:
    """Emit a Corner where two walls meet at an angle (not parallel) with
    nearest endpoints within endpoint_max_dist.
    """

    def __init__(
        self,
        *,
        angle_min: float = 20.0,
        angle_max: float = 160.0,
        endpoint_max_dist: float = 32.0,
    ) -> None:
        self.angle_min = angle_min
        self.angle_max = angle_max
        self.endpoint_max_dist = endpoint_max_dist

    def detect(self, walls: List[Wall]) -> List[Corner]:
        """Return the list of Corners for every eligible wall pair.

        Rule: for each pair (w1, w2):
          - angle_between(w1, w2) in (angle_min, angle_max)  (not parallel / anti-parallel)
          - nearest endpoint distance <= endpoint_max_dist
        Corner position is the midpoint of the two closest endpoints.
        """
        corners: List[Corner] = []
        next_id = 1
        for w1, w2 in itertools.combinations(walls, 2):
            angle = angle_between(w1, w2)
            if not (self.angle_min < angle < self.angle_max):
                continue
            p1, p2, dist = nearest_endpoints(w1, w2)
            if dist > self.endpoint_max_dist:
                continue
            mid_x = (p1[0] + p2[0]) / 2.0
            mid_y = (p1[1] + p2[1]) / 2.0
            corners.append(
                Corner(
                    id=next_id,
                    x=float(mid_x),
                    y=float(mid_y),
                    wall_a_id=w1.id,
                    wall_b_id=w2.id,
                    angle_deg=float(angle),
                    confidence=float(min(w1.confidence, w2.confidence)),
                )
            )
            next_id += 1
        return corners
