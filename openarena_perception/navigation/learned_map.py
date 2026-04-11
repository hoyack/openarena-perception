"""
learned_map.py — Self-mapping navigation layer.

The bot builds its own environment map as it explores:
  1. Occupancy Grid: 64x64 cells marking OPEN/WALL/VISITED/LIQUID
  2. Edge Failure Memory: Track which AAS edges fail/succeed -> feeds A* cost
  3. Wall Segments: Detected wall positions stored as line segments for HUD

Updated every tick (~0.5ms). Persisted across sessions.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import os
from enum import IntEnum
from typing import Dict, List, NamedTuple, Optional, Tuple

import numpy as np

from openarena_perception.navigation.room_perception import (
    Corner,
    CornerDetector,
    Doorway,
    DoorwayDetector,
    PartialRoom,
    Room,
    RoomInferrer,
    Wall,
)
from openarena_perception.navigation.room_perception.line_fitter import LineFitter

log = logging.getLogger(__name__)


class CellState(IntEnum):
    UNKNOWN = 0
    OPEN = 1
    WALL = 2
    VISITED = 3
    LIQUID = 4


class RaycastHit(NamedTuple):
    """Single wall observation: where the bot looked from + where the ray hit."""

    origin_x: float
    origin_y: float
    origin_z: float
    dir_angle_deg: float
    hit_x: float
    hit_y: float
    hit_z: float
    confidence: float
    timestamp: float


class LearnedMap:
    """Self-mapping navigation layer. Updated every tick, persisted across sessions."""

    GRID_RESOLUTION = 64    # world units per cell
    GRID_SIZE = 64          # 64x64 grid = 4096x4096 world units
    MERGE_DISTANCE = 48.0   # wall segments closer than this merge
    MAX_SEGMENTS = 500
    MAX_RAYCASTS_PER_FLOOR = 5000   # Phase 13: point cloud cap per floor
    SAVE_INTERVAL = 60.0    # seconds between auto-saves

    def __init__(self, map_name: str = "unknown", aas_graph=None):
        self.map_name = map_name

        # Compute grid origin from AAS bounds (or default)
        self._origin_x = -1024.0
        self._origin_y = -512.0
        if aas_graph and aas_graph.areas:
            xs = [a.cx for a in aas_graph.areas if a.idx > 0]
            ys = [a.cy for a in aas_graph.areas if a.idx > 0]
            if xs and ys:
                cx = (min(xs) + max(xs)) / 2
                cy = (min(ys) + max(ys)) / 2
                half = (self.GRID_SIZE * self.GRID_RESOLUTION) / 2
                self._origin_x = cx - half
                self._origin_y = cy - half

        # Occupancy grid -- separate layer per floor
        # Floor 0 = z < -20 (basement), Floor 1 = z >= -20 (upper)
        self.NUM_FLOORS = 2
        self.FLOOR_Z_THRESHOLD = -20.0
        self._grids = [np.zeros((self.GRID_SIZE, self.GRID_SIZE), dtype=np.uint8)
                        for _ in range(self.NUM_FLOORS)]
        self._current_floor = 1

        # Wall segments: [(x1, y1, x2, y2, confidence, last_seen)]
        # Phase 13: legacy stub path retired — kept as empty writable list for
        # backward compat in save()/load() schemas. New captures go to the
        # raycast point cloud below.
        self._wall_segments: List[List[float]] = []

        # Phase 13: per-floor raycast point cloud mirroring _grids shape.
        # Replaces the _record_wall perpendicular-stub architecture.
        self._raycasts_per_floor: List[List[RaycastHit]] = [
            [] for _ in range(self.NUM_FLOORS)
        ]

        # Phase 13 Plan 13-05: room perception state per floor.
        self._line_fitters: List[LineFitter] = [
            LineFitter(seed=42) for _ in range(self.NUM_FLOORS)
        ]
        self._fitted_walls_per_floor: List[List[Wall]] = [
            [] for _ in range(self.NUM_FLOORS)
        ]
        self._corners_per_floor: List[List[Corner]] = [
            [] for _ in range(self.NUM_FLOORS)
        ]
        self._rooms_per_floor: List[List[Room]] = [
            [] for _ in range(self.NUM_FLOORS)
        ]
        self._partial_rooms_per_floor: List[List[PartialRoom]] = [
            [] for _ in range(self.NUM_FLOORS)
        ]
        self._doorways_per_floor: List[List[Doorway]] = [
            [] for _ in range(self.NUM_FLOORS)
        ]
        self._last_current_room_id: Optional[int] = None
        self._cached_current_room_id: Optional[int] = None
        self._current_room_cache_valid: bool = False

        # Edge failure/success memory
        self._edge_failures: Dict[str, int] = {}
        self._edge_successes: Dict[str, int] = {}

        # Previous position for ray marching
        self._prev_pos: Optional[Tuple[float, float]] = None
        self._last_save = 0.0

        # Stats
        self._updates = 0

        # Persistence path
        self._save_dir = os.path.expanduser("~/.openarena/learned_maps")
        os.makedirs(self._save_dir, exist_ok=True)

    # -- Per-tick update ---------------------------------------------------

    def _get_floor(self, z: float) -> int:
        """Determine which floor level based on Z coordinate."""
        return 0 if z < self.FLOOR_Z_THRESHOLD else 1

    @property
    def _grid(self):
        """Current floor's grid."""
        return self._grids[self._current_floor]

    def update(self, pos: Tuple[float, float, float], yaw: float,
               wall_ahead: bool, wall_score: float, open_direction: int,
               in_water: bool) -> None:
        """Called every tick. Marks grid cells and records walls. ~0.5ms."""
        self._updates += 1
        wx, wy, wz = pos[0], pos[1], pos[2]

        # Detect current floor
        self._current_floor = self._get_floor(wz)

        # Mark current position as VISITED
        gx, gy = self._world_to_grid(wx, wy)
        self._grid[gy, gx] = CellState.VISITED

        # Mark liquid
        if in_water:
            self._grid[gy, gx] = CellState.LIQUID

        # Ray march from previous position to current -- mark all cells as OPEN
        if self._prev_pos:
            self._ray_march(self._prev_pos[0], self._prev_pos[1], wx, wy)
        self._prev_pos = (wx, wy)

        # Phase 13 Plan 13-05: invalidate per-tick current_room_id cache
        # (position changed) and run the visit-count debouncer.
        self._current_room_cache_valid = False
        cur_room_id = self.current_room_id()
        if cur_room_id != self._last_current_room_id:
            if cur_room_id is not None:
                import time as _time

                now_ts = _time.time()
                rooms = self._rooms_per_floor[self._current_floor]
                for idx, r in enumerate(rooms):
                    if r.id == cur_room_id:
                        rooms[idx] = r._replace(
                            visit_count=r.visit_count + 1,
                            last_visited_ts=now_ts,
                            first_seen_ts=r.first_seen_ts or now_ts,
                        )
                        break
            self._last_current_room_id = cur_room_id

        # Wall detection -- mark wall cell ahead
        if wall_ahead and wall_score > 0.5:
            wall_dist = 30.0 + (1.0 - wall_score) * 40.0
            wall_x = wx + wall_dist * math.cos(math.radians(yaw))
            wall_y = wy + wall_dist * math.sin(math.radians(yaw))
            wgx, wgy = self._world_to_grid(wall_x, wall_y)
            if self._grid[wgy, wgx] != CellState.VISITED:
                self._grid[wgy, wgx] = CellState.WALL

            # Phase 13: raycast point cloud capture (replaces _record_wall stubs).
            # The legacy _record_wall method is kept defined-but-unused so any
            # incidental callers remain valid; wall_segments stays empty and
            # serializes as [] in schema v3.
            self._record_raycast(wx, wy, wz, yaw, wall_x, wall_y, wz, wall_score)

        # Auto-save
        import time
        if time.time() - self._last_save > self.SAVE_INTERVAL:
            self.save()
            self._last_save = time.time()

    # -- Edge failure tracking ---------------------------------------------

    def record_edge_success(self, from_area: int, to_area: int) -> None:
        key = self._edge_key(from_area, to_area)
        self._edge_successes[key] = self._edge_successes.get(key, 0) + 1

    def edge_penalty(self, from_area: int, to_area: int) -> float:
        """A* cost penalty for edges that have failed before."""
        # Check symmetric key (both directions share failure data)
        key = self._edge_key(from_area, to_area)
        failures = self._edge_failures.get(key, 0)
        successes = self._edge_successes.get(key, 0)
        if failures == 0:
            return 0.0

        # Also check directional key for one-way detection
        dir_key = f"{from_area}>{to_area}"
        dir_failures = self._edge_failures.get(dir_key, 0)
        if dir_failures >= 3:
            # This specific direction has failed 3+ times -- likely one-way
            return 10000.0  # effectively block this direction

        return 1000.0 * max(0, failures - successes * 0.3)

    def record_edge_failure(self, from_area: int, to_area: int) -> None:
        key = self._edge_key(from_area, to_area)
        self._edge_failures[key] = self._edge_failures.get(key, 0) + 1
        # Also record directional failure for one-way detection
        dir_key = f"{from_area}>{to_area}"
        self._edge_failures[dir_key] = self._edge_failures.get(dir_key, 0) + 1
        log.debug("Edge fail: %d->%d (count=%d, dir=%d)",
                  from_area, to_area,
                  self._edge_failures[key], self._edge_failures[dir_key])

    # -- Grid queries ------------------------------------------------------

    def is_passable(self, wx: float, wy: float) -> bool:
        gx, gy = self._world_to_grid(wx, wy)
        state = self._grid[gy, gx]
        return state in (CellState.UNKNOWN, CellState.OPEN, CellState.VISITED)

    def cell_state(self, wx: float, wy: float) -> int:
        gx, gy = self._world_to_grid(wx, wy)
        return int(self._grid[gy, gx])

    # -- Persistence -------------------------------------------------------

    def save(self) -> None:
        path = os.path.join(self._save_dir, f"{self.map_name}.json")
        try:
            grids_b64 = [base64.b64encode(g.tobytes()).decode() for g in self._grids]
            # Phase 13: legacy _record_wall path is retired — force wall_segments
            # to an empty list so v3 saves never leak stubs to disk.
            self._wall_segments = []
            data = {
                "map_name": self.map_name,
                "version": 3,
                "grid_resolution": self.GRID_RESOLUTION,
                "grid_size": self.GRID_SIZE,
                "num_floors": self.NUM_FLOORS,
                "floor_z_threshold": self.FLOOR_Z_THRESHOLD,
                "grid_origin": [self._origin_x, self._origin_y],
                "grids": grids_b64,
                "wall_segments": self._wall_segments,
                "edge_failures": self._edge_failures,
                "edge_successes": self._edge_successes,
                # Phase 13 — room perception schema v3
                "raycasts_per_floor": [
                    [list(h) for h in floor_cloud]
                    for floor_cloud in self._raycasts_per_floor
                ],
                "fitted_walls": [
                    [list(w) for w in floor_walls]
                    for floor_walls in self._fitted_walls_per_floor
                ],
                "corners": [
                    [list(c) for c in floor_corners]
                    for floor_corners in self._corners_per_floor
                ],
                "rooms": [
                    [
                        {
                            "id": r.id,
                            "polygon_vertices": [list(v) for v in r.polygon_vertices],
                            "bounds": list(r.bounds),
                            "area": r.area,
                            "wall_ids": list(r.wall_ids),
                            "corner_ids": list(r.corner_ids),
                            "doorway_ids": list(r.doorway_ids),
                            "items_seen": [list(item) for item in r.items_seen],
                            "visit_count": r.visit_count,
                            "first_seen_ts": r.first_seen_ts,
                            "last_seen_ts": r.last_seen_ts,
                            "last_visited_ts": r.last_visited_ts,
                            "notes": r.notes,
                        }
                        for r in floor_rooms
                    ]
                    for floor_rooms in self._rooms_per_floor
                ],
                "doorways": [
                    [list(d) for d in floor_doorways]
                    for floor_doorways in self._doorways_per_floor
                ],
            }
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, path)
            total_mapped = sum(int((g > 0).sum()) for g in self._grids)
            log.info("Learned map saved: %s (%d cells mapped, %d walls, %d edges)",
                     path, total_mapped,
                     len(self._wall_segments), len(self._edge_failures))
        except Exception as e:
            log.warning("Failed to save learned map: %s", e)

    def load(self) -> bool:
        path = os.path.join(self._save_dir, f"{self.map_name}.json")
        if not os.path.exists(path):
            return False
        try:
            with open(path) as f:
                data = json.load(f)
            version = data.get("version", 1)
            if version not in (1, 2, 3):
                return False

            self._origin_x = data["grid_origin"][0]
            self._origin_y = data["grid_origin"][1]

            if version == 2 and "grids" in data:
                for i, gb64 in enumerate(data["grids"]):
                    if i < self.NUM_FLOORS:
                        grid_bytes = base64.b64decode(gb64)
                        self._grids[i] = np.frombuffer(
                            grid_bytes, dtype=np.uint8).reshape(
                            self.GRID_SIZE, self.GRID_SIZE).copy()
            elif "grid" in data:
                # v1 compat -- load into upper floor
                grid_bytes = base64.b64decode(data["grid"])
                self._grids[1] = np.frombuffer(
                    grid_bytes, dtype=np.uint8).reshape(
                    self.GRID_SIZE, self.GRID_SIZE).copy()

            self._wall_segments = data.get("wall_segments", [])
            self._edge_failures = data.get("edge_failures", {})
            self._edge_successes = data.get("edge_successes", {})

            # Phase 13 schema v3 — real deserialization of raycast point cloud.
            # Older (v1/v2) files have no raycasts; keep the empty lists that
            # __init__ created. Wall_segments from old files are intentionally
            # NOT round-tripped into raycasts (see CONTEXT.md — user already
            # reset oa_dm1 data for this transition).
            if version >= 3:
                raw_floors = data.get(
                    "raycasts_per_floor", [[] for _ in range(self.NUM_FLOORS)]
                )
                self._raycasts_per_floor = [
                    [RaycastHit(*h) for h in floor_list]
                    for floor_list in raw_floors
                ]

                # Phase 13 Plan 13-05: deserialize typed room-perception entities.
                fw_raw = data.get("fitted_walls", [])
                self._fitted_walls_per_floor = [
                    [Wall(*w) for w in floor_list]
                    for floor_list in fw_raw
                ] if fw_raw else [[] for _ in range(self.NUM_FLOORS)]
                # Pad to NUM_FLOORS if short
                while len(self._fitted_walls_per_floor) < self.NUM_FLOORS:
                    self._fitted_walls_per_floor.append([])

                corners_raw = data.get("corners", [])
                self._corners_per_floor = [
                    [Corner(*c) for c in floor_list]
                    for floor_list in corners_raw
                ] if corners_raw else [[] for _ in range(self.NUM_FLOORS)]
                while len(self._corners_per_floor) < self.NUM_FLOORS:
                    self._corners_per_floor.append([])

                rooms_raw = data.get("rooms", [])
                rooms_loaded: List[List[Room]] = []
                for floor_list in rooms_raw:
                    floor_rooms: List[Room] = []
                    for rd in floor_list:
                        if isinstance(rd, dict):
                            floor_rooms.append(
                                Room(
                                    id=rd.get("id", 0),
                                    polygon_vertices=tuple(
                                        tuple(v) for v in rd.get("polygon_vertices", ())
                                    ),
                                    bounds=tuple(rd.get("bounds", (0, 0, 0, 0))),
                                    area=float(rd.get("area", 0.0)),
                                    wall_ids=tuple(rd.get("wall_ids", ())),
                                    corner_ids=tuple(rd.get("corner_ids", ())),
                                    doorway_ids=tuple(rd.get("doorway_ids", ())),
                                    items_seen=tuple(
                                        tuple(item) for item in rd.get("items_seen", ())
                                    ),
                                    visit_count=int(rd.get("visit_count", 0)),
                                    first_seen_ts=float(rd.get("first_seen_ts", 0.0)),
                                    last_seen_ts=float(rd.get("last_seen_ts", 0.0)),
                                    last_visited_ts=float(rd.get("last_visited_ts", 0.0)),
                                    notes=str(rd.get("notes", "")),
                                )
                            )
                    rooms_loaded.append(floor_rooms)
                self._rooms_per_floor = rooms_loaded if rooms_loaded else [
                    [] for _ in range(self.NUM_FLOORS)
                ]
                while len(self._rooms_per_floor) < self.NUM_FLOORS:
                    self._rooms_per_floor.append([])

                doorways_raw = data.get("doorways", [])
                self._doorways_per_floor = [
                    [Doorway(*d) for d in floor_list]
                    for floor_list in doorways_raw
                ] if doorways_raw else [[] for _ in range(self.NUM_FLOORS)]
                while len(self._doorways_per_floor) < self.NUM_FLOORS:
                    self._doorways_per_floor.append([])

            mapped = sum(int((g > 0).sum()) for g in self._grids)
            log.info("Learned map loaded: %s (%d cells, %d walls, %d failed edges)",
                     self.map_name, mapped,
                     len(self._wall_segments), len(self._edge_failures))
            return True
        except Exception as e:
            log.warning("Failed to load learned map: %s", e)
            return False

    # -- HUD export --------------------------------------------------------

    def export_for_hud(self) -> dict:
        """Export sparse grid + walls for the pygame HUD."""
        # Sparse grid: only non-UNKNOWN cells from CURRENT floor
        cells = []
        grid = self._grids[self._current_floor]
        for gy in range(self.GRID_SIZE):
            for gx in range(self.GRID_SIZE):
                state = int(grid[gy, gx])
                if state != CellState.UNKNOWN:
                    cells.append([gx, gy, state])

        # Wall segments (trim to top 200 by confidence)
        walls = sorted(self._wall_segments, key=lambda s: s[4], reverse=True)[:200]

        # Failed edges with penalty > 0
        failed = []
        for key, count in self._edge_failures.items():
            parts = key.split("_")
            if len(parts) == 2:
                penalty = self.edge_penalty(int(parts[0]), int(parts[1]))
                if penalty > 0:
                    failed.append([int(parts[0]), int(parts[1]), penalty])

        # Aggregate stats across all floors
        total_open = sum(int((g == CellState.OPEN).sum()) for g in self._grids)
        total_wall = sum(int((g == CellState.WALL).sum()) for g in self._grids)
        total_visited = sum(int((g == CellState.VISITED).sum()) for g in self._grids)
        total_liquid = sum(int((g == CellState.LIQUID).sum()) for g in self._grids)

        # Phase 13 Plan 13-05: room perception export
        floor = self._current_floor
        fitted_walls = [list(w) for w in self._fitted_walls_per_floor[floor]]
        corners_out = [list(c) for c in self._corners_per_floor[floor]]
        rooms_out = [
            {
                "id": r.id,
                "polygon_vertices": [list(v) for v in r.polygon_vertices],
                "bounds": list(r.bounds),
                "area": r.area,
                "visit_count": r.visit_count,
                "items_seen": [list(item) for item in r.items_seen],
            }
            for r in self._rooms_per_floor[floor]
        ]
        doorways_out = [list(d) for d in self._doorways_per_floor[floor]]
        cur_room = self.current_room_id()
        cur_items: List[str] = []
        if cur_room is not None:
            for r in self._rooms_per_floor[floor]:
                if r.id == cur_room:
                    cur_items = [item[0] for item in r.items_seen]
                    break

        return {
            "grid_origin": [self._origin_x, self._origin_y],
            "grid_resolution": self.GRID_RESOLUTION,
            "grid_size": self.GRID_SIZE,
            "current_floor": self._current_floor,
            "grid_cells": cells,
            "wall_segments": [[s[0], s[1], s[2], s[3], s[4]] for s in walls],
            "failed_edges": failed,
            "fitted_walls": fitted_walls,
            "corners": corners_out,
            "rooms": rooms_out,
            "doorways": doorways_out,
            "current_room_id": cur_room,
            "current_room_items": cur_items,
            "stats": {
                "open_cells": total_open,
                "wall_cells": total_wall,
                "visited_cells": total_visited,
                "liquid_cells": total_liquid,
                "wall_segments": len(self._wall_segments),
                "failed_edges": len([k for k, v in self._edge_failures.items() if v > 0]),
                "updates": self._updates,
                "current_floor": self._current_floor,
            },
        }

    # -- Internal ----------------------------------------------------------

    def _world_to_grid(self, wx: float, wy: float) -> Tuple[int, int]:
        gx = int((wx - self._origin_x) / self.GRID_RESOLUTION)
        gy = int((wy - self._origin_y) / self.GRID_RESOLUTION)
        gx = max(0, min(self.GRID_SIZE - 1, gx))
        gy = max(0, min(self.GRID_SIZE - 1, gy))
        return (gx, gy)

    def _grid_to_world(self, gx: int, gy: int) -> Tuple[float, float]:
        wx = self._origin_x + (gx + 0.5) * self.GRID_RESOLUTION
        wy = self._origin_y + (gy + 0.5) * self.GRID_RESOLUTION
        return (wx, wy)

    def _ray_march(self, x0: float, y0: float, x1: float, y1: float):
        """Mark cells along a line as OPEN (Bresenham-like)."""
        gx0, gy0 = self._world_to_grid(x0, y0)
        gx1, gy1 = self._world_to_grid(x1, y1)

        dx = abs(gx1 - gx0)
        dy = abs(gy1 - gy0)
        sx = 1 if gx1 > gx0 else -1
        sy = 1 if gy1 > gy0 else -1
        err = dx - dy

        steps = 0
        while steps < 20:  # cap to prevent infinite loop
            if self._grid[gy0, gx0] == CellState.UNKNOWN:
                self._grid[gy0, gx0] = CellState.OPEN
            if gx0 == gx1 and gy0 == gy1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                gx0 += sx
                gx0 = max(0, min(self.GRID_SIZE - 1, gx0))
            if e2 < dx:
                err += dx
                gy0 += sy
                gy0 = max(0, min(self.GRID_SIZE - 1, gy0))
            steps += 1

    def _record_wall(self, px: float, py: float, yaw: float,
                     wall_score: float):
        """Record a wall segment perpendicular to the view direction."""
        import time
        wall_dist = 30.0 + (1.0 - wall_score) * 40.0
        wall_x = px + wall_dist * math.cos(math.radians(yaw))
        wall_y = py + wall_dist * math.sin(math.radians(yaw))

        # Segment perpendicular to view
        perp = yaw + 90
        half_len = self.GRID_RESOLUTION * 0.5
        x1 = wall_x + half_len * math.cos(math.radians(perp))
        y1 = wall_y + half_len * math.sin(math.radians(perp))
        x2 = wall_x - half_len * math.cos(math.radians(perp))
        y2 = wall_y - half_len * math.sin(math.radians(perp))

        # Try to merge with existing segment
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        now = time.time()

        for seg in self._wall_segments:
            smx = (seg[0] + seg[2]) / 2
            smy = (seg[1] + seg[3]) / 2
            dist = math.hypot(mid_x - smx, mid_y - smy)
            if dist < self.MERGE_DISTANCE:
                # Check angle similarity
                seg_angle = math.degrees(math.atan2(seg[3] - seg[1], seg[2] - seg[0]))
                new_angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
                angle_diff = abs(((seg_angle - new_angle + 180) % 360) - 180)
                if angle_diff < 30 or angle_diff > 150:  # parallel (or anti-parallel)
                    seg[4] += 1  # increment confidence
                    seg[5] = now
                    # Extend the segment to cover both
                    seg[0] = min(seg[0], x1)
                    seg[1] = min(seg[1], y1)
                    seg[2] = max(seg[2], x2)
                    seg[3] = max(seg[3], y2)
                    return

        # New segment
        if len(self._wall_segments) < self.MAX_SEGMENTS:
            self._wall_segments.append([x1, y1, x2, y2, 1, now])

    def _record_raycast(
        self,
        ox: float,
        oy: float,
        oz: float,
        yaw: float,
        hx: float,
        hy: float,
        hz: float,
        confidence: float,
    ) -> None:
        """Append a RaycastHit to the current floor's cloud; decimate if over cap.

        Phase 13 point-cloud capture. Per-tick cost is a single list append;
        the sort-based eviction pass only runs when the cloud exceeds
        MAX_RAYCASTS_PER_FLOOR, so amortized cost stays <1ms on target hardware.
        """
        import time

        hit = RaycastHit(
            origin_x=ox,
            origin_y=oy,
            origin_z=oz,
            dir_angle_deg=yaw,
            hit_x=hx,
            hit_y=hy,
            hit_z=hz,
            confidence=confidence,
            timestamp=time.time(),
        )
        cloud = self._raycasts_per_floor[self._current_floor]
        cloud.append(hit)
        if len(cloud) > self.MAX_RAYCASTS_PER_FLOOR:
            # Evict oldest-lowest-confidence: ascending by (confidence, timestamp)
            # — keep the highest-confidence/most-recent tail.
            cloud.sort(key=lambda h: (h.confidence, h.timestamp))
            del cloud[: len(cloud) - self.MAX_RAYCASTS_PER_FLOOR]

    # -- Phase 13 Plan 13-05: room perception orchestration ---------------

    def fit_rooms(self, *, force: bool = False, now: Optional[float] = None) -> None:
        """Run the full room-perception pipeline for the current floor.

        Cadence-gated via LineFitter unless force=True. Populates
        fitted_walls / corners / rooms / partial_rooms / doorways per floor.
        """
        import time as _time

        if now is None:
            now = _time.time()
        floor = self._current_floor
        cloud = self._raycasts_per_floor[floor]
        if len(cloud) < 20:
            return
        fitter = self._line_fitters[floor]
        if force:
            walls = fitter.fit_now(cloud, now=now)
        else:
            walls = fitter.fit(cloud, now=now)
        self._fitted_walls_per_floor[floor] = walls
        self._current_room_cache_valid = False
        # Plan 13-05: bump endpoint proximity to 64u because RANSAC fit walls
        # terminate at inlier extents, which typically undershoot real corners
        # by 10-30u. 32u (CornerDetector default) is fine for hand-crafted
        # walls in unit tests, but too tight for live fitter output.
        # Plan 13-09: keep 64u (Plan 13-08's 96u was a regression -- see
        # .planning/phases/13-.../13-VERIFICATION.md GAP-3 Attempt 1). Add
        # merge_radius=16 to collapse near-duplicate corners at the source.
        # Floor-1 sparseness is a raycast-data-scarcity problem, not a
        # proximity-threshold one.
        corners = CornerDetector(
            endpoint_max_dist=64.0,
            merge_radius=16.0,
        ).detect(walls)
        self._corners_per_floor[floor] = corners
        rooms, partials = RoomInferrer().infer(walls, corners)
        doorways = DoorwayDetector().detect(walls, corners)
        prev_rooms = self._rooms_per_floor[floor]
        rooms = self._preserve_room_log(prev_rooms, rooms)
        self._rooms_per_floor[floor] = rooms
        self._partial_rooms_per_floor[floor] = partials
        self._doorways_per_floor[floor] = doorways

    def _preserve_room_log(
        self, prev: List[Room], new: List[Room]
    ) -> List[Room]:
        """Carry items_seen + visit_count forward across refit by centroid match."""
        if not prev:
            return new
        updated: List[Room] = []
        for r in new:
            xs = [v[0] for v in r.polygon_vertices]
            ys = [v[1] for v in r.polygon_vertices]
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            best: Optional[Room] = None
            best_dist = 128.0
            for p in prev:
                pxs = [v[0] for v in p.polygon_vertices]
                pys = [v[1] for v in p.polygon_vertices]
                pcx = sum(pxs) / len(pxs)
                pcy = sum(pys) / len(pys)
                d = math.hypot(cx - pcx, cy - pcy)
                if d < best_dist:
                    best_dist = d
                    best = p
            if best is not None:
                updated.append(
                    r._replace(
                        items_seen=best.items_seen,
                        visit_count=best.visit_count,
                        first_seen_ts=best.first_seen_ts or r.first_seen_ts,
                        last_visited_ts=best.last_visited_ts,
                    )
                )
            else:
                updated.append(r)
        return updated

    def note_item(self, name: str, x: float, y: float) -> None:
        """Associate an observed item with the first room whose polygon contains (x, y)."""
        import time as _time

        try:
            import cv2
        except ImportError:
            return
        floor = self._current_floor
        rooms = self._rooms_per_floor[floor]
        if not rooms:
            return
        now = _time.time()
        for idx, room in enumerate(rooms):
            poly = np.array(room.polygon_vertices, dtype=np.float32)
            if cv2.pointPolygonTest(poly, (float(x), float(y)), False) >= 0:
                existing_names = {entry[0] for entry in room.items_seen if entry}
                if name not in existing_names:
                    new_items = tuple(list(room.items_seen) + [(name, now)])
                    rooms[idx] = room._replace(
                        items_seen=new_items, last_seen_ts=now
                    )
                return

    def current_room_id(self) -> Optional[int]:
        """Return the room id containing the bot's last known position, or None.

        Per-tick cached: invalidated by update() and fit_rooms(). Subsequent
        calls within the same tick return the cached value so the per-tick
        PIP cost stays flat regardless of how many subsystems query it.
        """
        if self._current_room_cache_valid:
            return self._cached_current_room_id
        if self._prev_pos is None:
            self._cached_current_room_id = None
            self._current_room_cache_valid = True
            return None
        try:
            import cv2
        except ImportError:
            self._cached_current_room_id = None
            self._current_room_cache_valid = True
            return None
        floor = self._current_floor
        rooms = self._rooms_per_floor[floor]
        result: Optional[int] = None
        px = float(self._prev_pos[0])
        py = float(self._prev_pos[1])
        for room in rooms:
            poly = np.array(room.polygon_vertices, dtype=np.float32)
            if cv2.pointPolygonTest(poly, (px, py), False) >= 0:
                result = room.id
                break
        self._cached_current_room_id = result
        self._current_room_cache_valid = True
        return result

    @staticmethod
    def _edge_key(from_area: int, to_area: int) -> str:
        a, b = min(from_area, to_area), max(from_area, to_area)
        return f"{a}_{b}"
