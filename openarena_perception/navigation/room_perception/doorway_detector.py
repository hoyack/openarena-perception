"""Phase 13: Doorway detector -- near-miss wall gaps.

A doorway is a short gap (> gap_min, < gap_max) between two collinear-ish
walls that are NOT already bridged by a corner. Used by Plan 13-05 to
connect rooms or connect a room to "outside" without AAS.
"""
from __future__ import annotations

import itertools
from typing import List, Optional

from openarena_perception.navigation.room_perception._geometry import (
    angle_between,
    nearest_endpoints,
)
from openarena_perception.navigation.room_perception.types import (
    Corner,
    Doorway,
    Wall,
)


class DoorwayDetector:
    """Detect near-miss wall pairs as Doorways."""

    def __init__(self, *, gap_min: float = 4.0, gap_max: float = 96.0) -> None:
        self.gap_min = gap_min
        self.gap_max = gap_max

    def detect(
        self,
        walls: List[Wall],
        corners: Optional[List[Corner]] = None,
    ) -> List[Doorway]:
        """Return Doorways for wall pairs whose nearest endpoints fall in
        (gap_min, gap_max) AND whose directions are near-collinear (not a
        perpendicular corner). Pairs already bridged by a Corner are skipped.
        """
        bridged: set = set()
        if corners:
            for c in corners:
                bridged.add(tuple(sorted((c.wall_a_id, c.wall_b_id))))

        doorways: List[Doorway] = []
        next_id = 1
        for w1, w2 in itertools.combinations(walls, 2):
            key = tuple(sorted((w1.id, w2.id)))
            if key in bridged:
                continue
            p1, p2, dist = nearest_endpoints(w1, w2)
            if not (self.gap_min < dist < self.gap_max):
                continue
            # Only collinear-ish walls count as doorway candidates. A
            # perpendicular pair in the 20..160 band is a (missed) corner,
            # not a doorway.
            angle = angle_between(w1, w2)
            if 20.0 < angle < 160.0:
                continue
            doorways.append(
                Doorway(
                    id=next_id,
                    wall_a_id=w1.id,
                    wall_b_id=w2.id,
                    gap_distance=float(dist),
                    midpoint_x=float((p1[0] + p2[0]) / 2.0),
                    midpoint_y=float((p1[1] + p2[1]) / 2.0),
                )
            )
            next_id += 1
        return doorways
