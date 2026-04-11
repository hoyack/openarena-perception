"""Phase 13: Room inferrer -- hand-rolled simple cycle enumeration.

Given a list of Walls and Corners, find closed polygons (Rooms) and
leftover wall chains (PartialRooms). Uses a bespoke DFS over the
corner-adjacency graph -- max cycle length 6, small graphs typical
(<50 corners), so combinatorial blow-up is not a concern.

Pure-stdlib. No networkx, no shapely, no skimage.
"""
from __future__ import annotations

from typing import Dict, List, Set, Tuple

from openarena_perception.navigation.room_perception.types import (
    Corner,
    PartialRoom,
    Room,
    Wall,
)


class RoomInferrer:
    """Infer Room polygons + PartialRooms from Walls and Corners."""

    def __init__(
        self,
        *,
        min_room_area: float = 20000.0,
        max_room_area: float = 200000.0,
        max_cycle_length: int = 6,
    ) -> None:
        self.min_room_area = min_room_area
        self.max_room_area = max_room_area
        self.max_cycle_length = max_cycle_length

    def infer(
        self, walls: List[Wall], corners: List[Corner]
    ) -> Tuple[List[Room], List[PartialRoom]]:
        if not walls:
            return [], []

        # Wall adjacency: wall -> walls it shares a corner with
        adj: Dict[int, Set[int]] = {w.id: set() for w in walls}
        for c in corners:
            if c.wall_a_id in adj and c.wall_b_id in adj:
                adj[c.wall_a_id].add(c.wall_b_id)
                adj[c.wall_b_id].add(c.wall_a_id)

        # Enumerate simple cycles (wall-id lists) up to max_cycle_length
        cycles = self._find_cycles(adj, self.max_cycle_length)

        # Plan 13-09: centroid-cell dedup. Bucket every candidate cycle by
        # (round(cx/16), round(cy/16)) of its polygon centroid, and keep
        # only the smallest-area cycle per bucket. Robust against upstream
        # near-duplicate corners (the Plan 13-08 regression mode): operates
        # on emitted geometry, not corner IDs.
        CENTROID_CELL = 16.0
        best_by_cell: Dict[
            Tuple[int, int],
            Tuple[List[int], List[Tuple[float, float]], float, Tuple[int, ...]],
        ] = {}

        for cycle in cycles:
            polygon = self._cycle_to_polygon(cycle, corners)
            if len(polygon) < 3:
                continue
            area = self._polygon_area(polygon)
            if area < self.min_room_area:
                # Closed but too small -- not a real room.
                continue
            if area > self.max_room_area:
                # Plan 13-09: reject map-spanning cycles. 500k+ sq unit
                # "rooms" are over-connected-graph artifacts (the visible
                # symptom of the 13-08 regression), not architecture.
                continue
            cx, cy = self._polygon_centroid(polygon)
            cell = (
                int(round(cx / CENTROID_CELL)),
                int(round(cy / CENTROID_CELL)),
            )
            cycle_set = set(cycle)
            corner_ids = tuple(
                c.id
                for c in corners
                if c.wall_a_id in cycle_set and c.wall_b_id in cycle_set
            )
            existing = best_by_cell.get(cell)
            if existing is None or area < existing[2]:
                best_by_cell[cell] = (cycle, polygon, area, corner_ids)

        rooms: List[Room] = []
        next_room_id = 1
        for cell, (cycle, polygon, area, corner_ids) in best_by_cell.items():
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            bounds = (min(xs), min(ys), max(xs), max(ys))
            rooms.append(
                Room(
                    id=next_room_id,
                    polygon_vertices=tuple(
                        (float(x), float(y)) for x, y in polygon
                    ),
                    bounds=tuple(float(v) for v in bounds),
                    area=float(area),
                    wall_ids=tuple(sorted(cycle)),
                    corner_ids=corner_ids,
                    doorway_ids=tuple(),
                    items_seen=tuple(),
                    visit_count=0,
                    first_seen_ts=0.0,
                    last_seen_ts=0.0,
                    last_visited_ts=0.0,
                    notes="",
                )
            )
            next_room_id += 1

        # PartialRoom: connected components of walls NOT inside a closed room
        closed_wall_ids: Set[int] = set()
        for r in rooms:
            closed_wall_ids.update(r.wall_ids)

        partial_rooms: List[PartialRoom] = []
        next_partial_id = 1
        visited: Set[int] = set()
        for w_id in sorted(adj.keys()):
            if w_id in visited or w_id in closed_wall_ids:
                continue
            component = self._bfs_component(w_id, adj)
            visited.update(component)
            # Only report components that could plausibly grow into a room.
            if 2 <= len(component) <= self.max_cycle_length:
                comp_set = set(component)
                corner_ids = tuple(
                    c.id
                    for c in corners
                    if c.wall_a_id in comp_set and c.wall_b_id in comp_set
                )
                partial_rooms.append(
                    PartialRoom(
                        id=next_partial_id,
                        wall_ids=tuple(sorted(component)),
                        corner_ids=corner_ids,
                    )
                )
                next_partial_id += 1

        return rooms, partial_rooms

    # ------------------------------------------------------------------
    # Graph primitives
    # ------------------------------------------------------------------
    def _find_cycles(
        self, adj: Dict[int, Set[int]], max_len: int
    ) -> List[List[int]]:
        """Hand-rolled simple cycle enumeration via DFS.

        Canonicalises each cycle by (a) anchoring the start at the min
        node id in the cycle (we only extend to neighbors > start) and
        (b) deduping on sorted-tuple form. Small graphs -- O(V * 2^V)
        worst-case but in practice V < 50 and cycles are rare.
        """
        cycles: List[List[int]] = []
        seen: Set[Tuple[int, ...]] = set()
        nodes = sorted(adj.keys())
        for start in nodes:
            # DFS stack of (current_node, path_so_far)
            stack: List[Tuple[int, List[int]]] = [(start, [start])]
            while stack:
                node, path = stack.pop()
                if len(path) > max_len:
                    continue
                for neighbor in adj.get(node, ()):
                    if neighbor == start and len(path) >= 3:
                        key = tuple(sorted(path))
                        if key not in seen:
                            seen.add(key)
                            cycles.append(list(path))
                    elif neighbor not in path and neighbor > start:
                        stack.append((neighbor, path + [neighbor]))
        return cycles

    def _cycle_to_polygon(
        self, cycle: List[int], corners: List[Corner]
    ) -> List[Tuple[float, float]]:
        """For each consecutive wall pair in the cycle, look up the shared
        Corner position -- that point is a polygon vertex. If any pair
        does not share a corner, the cycle is not polygon-realisable.
        """
        polygon: List[Tuple[float, float]] = []
        n = len(cycle)
        for i in range(n):
            a = cycle[i]
            b = cycle[(i + 1) % n]
            shared = [
                c
                for c in corners
                if {c.wall_a_id, c.wall_b_id} == {a, b}
            ]
            if not shared:
                return []
            polygon.append((shared[0].x, shared[0].y))
        return polygon

    @staticmethod
    def _polygon_area(polygon: List[Tuple[float, float]]) -> float:
        """Shoelace formula -- unsigned area."""
        n = len(polygon)
        if n < 3:
            return 0.0
        s = 0.0
        for i in range(n):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]
            s += x1 * y2 - x2 * y1
        return abs(s) / 2.0

    @staticmethod
    def _polygon_perimeter(polygon: List[Tuple[float, float]]) -> float:
        """Sum of edge lengths -- tie-breaker for centroid-cell dedup."""
        n = len(polygon)
        if n < 2:
            return 0.0
        total = 0.0
        for i in range(n):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]
            total += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        return total

    @staticmethod
    def _polygon_centroid(
        polygon: List[Tuple[float, float]],
    ) -> Tuple[float, float]:
        """Vertex mean -- cheap and sufficient for centroid-cell bucketing."""
        if not polygon:
            return (0.0, 0.0)
        sx = sum(p[0] for p in polygon)
        sy = sum(p[1] for p in polygon)
        n = len(polygon)
        return (sx / n, sy / n)

    @staticmethod
    def _bfs_component(start: int, adj: Dict[int, Set[int]]) -> List[int]:
        visited: Set[int] = set()
        queue: List[int] = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            for n in adj.get(node, ()):
                if n not in visited:
                    queue.append(n)
        return sorted(visited)
