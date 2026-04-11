"""Phase 13: Corner detector -- pairwise wall intersection gating.

A corner exists where two fitted walls meet at a non-parallel angle AND
their nearest endpoints are within a proximity threshold (default 32u).
Pure-stdlib, zero new dependencies.
"""
from __future__ import annotations

import itertools
import logging
from typing import List

from openarena_perception.navigation.room_perception._geometry import (
    angle_between,
    nearest_endpoints,
)
from openarena_perception.navigation.room_perception.types import Corner, Wall

_log = logging.getLogger(__name__)


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
        merge_radius: float = 16.0,
    ) -> None:
        self.angle_min = angle_min
        self.angle_max = angle_max
        self.endpoint_max_dist = endpoint_max_dist
        self.merge_radius = merge_radius

    def detect(self, walls: List[Wall]) -> List[Corner]:
        """Return the list of Corners for every eligible wall pair.

        Rule: for each pair (w1, w2):
          - angle_between(w1, w2) in (angle_min, angle_max)  (not parallel / anti-parallel)
          - nearest endpoint distance <= endpoint_max_dist
        Corner position is the midpoint of the two closest endpoints.

        After pair enumeration, if merge_radius > 0, collapse corners
        whose positions are within merge_radius of each other into a
        single merged corner (Plan 13-09 — kills the near-duplicate
        fleet that broke Plan 13-08's corner-ID-tuple dedup).
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

        # Plan 13-09: spatial merge pass. CornerDetector's pair enumeration
        # emits near-duplicate corners at slightly different midpoints when
        # the same two walls' "nearest endpoint" calculation varies by a few
        # units. Collapse corners within merge_radius into one, using the
        # midpoint of each merged cluster. Single-pass non-transitive merge;
        # adequate for live n<=50 regime on Pi.
        if self.merge_radius > 0.0 and corners:
            merged: List[Corner] = []
            third_wall_dropped = False
            for c in corners:
                absorbed = False
                for i, m in enumerate(merged):
                    dx = c.x - m.x
                    dy = c.y - m.y
                    if (dx * dx + dy * dy) ** 0.5 < self.merge_radius:
                        # Merge: midpoint, min confidence, average angle.
                        new_x = (m.x + c.x) / 2.0
                        new_y = (m.y + c.y) / 2.0
                        new_conf = min(m.confidence, c.confidence)
                        new_angle = (m.angle_deg + c.angle_deg) / 2.0
                        # Corner NamedTuple only has two wall slots. If the
                        # incoming corner references a third wall beyond
                        # {m.wall_a_id, m.wall_b_id}, log once per fit pass
                        # and drop the third reference. Widening the tuple
                        # is out of scope (Plan 13-09 non-goal).
                        incoming_walls = {c.wall_a_id, c.wall_b_id}
                        existing_walls = {m.wall_a_id, m.wall_b_id}
                        if not incoming_walls.issubset(existing_walls):
                            extra = incoming_walls - existing_walls
                            if not third_wall_dropped:
                                _log.warning(
                                    "CornerDetector.merge: third wall(s) %s "
                                    "at merged corner (%.1f, %.1f) ignored; "
                                    "Corner slots full",
                                    sorted(extra), new_x, new_y,
                                )
                                third_wall_dropped = True
                        merged[i] = m._replace(
                            x=new_x,
                            y=new_y,
                            confidence=new_conf,
                            angle_deg=new_angle,
                        )
                        absorbed = True
                        break
                if not absorbed:
                    merged.append(c)
            # Reassign sequential ids 1..N so downstream code sees a tidy
            # set. RoomInferrer builds adjacency from (wall_a_id, wall_b_id)
            # pairs, not corner ids, so reassignment is safe.
            corners = [m._replace(id=i + 1) for i, m in enumerate(merged)]

        return corners
