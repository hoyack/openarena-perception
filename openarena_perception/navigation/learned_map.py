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
            # incidental callers remain valid; wall_segments stays empty.
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
            data = {
                "map_name": self.map_name,
                "version": 2,
                "grid_resolution": self.GRID_RESOLUTION,
                "grid_size": self.GRID_SIZE,
                "num_floors": self.NUM_FLOORS,
                "floor_z_threshold": self.FLOOR_Z_THRESHOLD,
                "grid_origin": [self._origin_x, self._origin_y],
                "grids": grids_b64,
                "wall_segments": self._wall_segments,
                "edge_failures": self._edge_failures,
                "edge_successes": self._edge_successes,
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

            # Phase 13 schema v3 — Plan 02 extends this with real deserialization.
            # Wave 0 stub: accept v3 files by reading keys with empty defaults
            # so cross-session reload works even before Plan 02 ships.
            if version >= 3:
                self._raycasts_per_floor_raw = data.get(
                    "raycasts_per_floor", [[] for _ in range(self.NUM_FLOORS)]
                )
                self._fitted_walls_raw = data.get("fitted_walls", [])
                self._corners_raw = data.get("corners", [])
                self._rooms_raw = data.get("rooms", [])
                self._doorways_raw = data.get("doorways", [])

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

        return {
            "grid_origin": [self._origin_x, self._origin_y],
            "grid_resolution": self.GRID_RESOLUTION,
            "grid_size": self.GRID_SIZE,
            "current_floor": self._current_floor,
            "grid_cells": cells,
            "wall_segments": [[s[0], s[1], s[2], s[3], s[4]] for s in walls],
            "failed_edges": failed,
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

    @staticmethod
    def _edge_key(from_area: int, to_area: int) -> str:
        a, b = min(from_area, to_area), max(from_area, to_area)
        return f"{a}_{b}"
