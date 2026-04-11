"""RANSAC line fitter for raycast point clouds.

Phase 13 Plan 13-03. Algorithm: iterative seeded RANSAC on 2D points.
Deterministic via np.random.default_rng(seed). Hand-rolled — no scikit-image
or networkx, only numpy + stdlib. Walls merge across fit passes via
collinearity + endpoint-overlap so support_count accumulates instead of
duplicating lines.

Tunables (class defaults in __init__):
  - inlier_threshold: 8 units perpendicular distance
  - min_support:      20 inliers required to emit a wall
  - max_iterations:   1000 RANSAC iterations cap per line
  - fit_interval_s:   3.0 seconds cadence gate (caller can pass now=... for
                      deterministic fake-clock tests)
  - confidence_threshold: 0.4 (walls below this are filtered on emit)

Cadence gate behaviour (fit()):
  Fit runs when ANY of these is true:
    - first call (no prior fit recorded)
    - (now - last_fit_ts) >= fit_interval_s
    - (cloud_size - last_fit_point_count) >= point_count_trigger
  Otherwise returns the cached wall list unchanged so a per-tick caller
  cannot accidentally run RANSAC at 60 Hz. Use fit_now() to bypass.
"""
from __future__ import annotations

import math
import time
from typing import List, Optional

import numpy as np

from openarena_perception.navigation.room_perception.types import Wall


class LineFitter:
    """Seeded RANSAC line fitter with wall merging + cadence gate."""

    def __init__(
        self,
        *,
        seed: int = 42,
        inlier_threshold: float = 8.0,
        min_support: int = 20,
        max_iterations: int = 1000,
        confidence_threshold: float = 0.4,
        fit_interval_s: float = 3.0,
        point_count_trigger: int = 500,
    ) -> None:
        self._seed = seed
        # Local RNG — never touch np.random global state (Plan 13-02 lesson).
        self._rng = np.random.default_rng(seed)
        self.inlier_threshold = inlier_threshold
        self.min_support = min_support
        self.max_iterations = max_iterations
        self.confidence_threshold = confidence_threshold
        self.fit_interval_s = fit_interval_s
        self.point_count_trigger = point_count_trigger

        self._walls: List[Wall] = []
        self._last_fit_ts: Optional[float] = None
        self._last_fit_point_count: int = 0
        self._next_wall_id: int = 1

    # ------------------------------------------------------------------
    @property
    def walls(self) -> List[Wall]:
        """Return a shallow copy of the current wall list."""
        return list(self._walls)

    # ------------------------------------------------------------------
    def fit(self, cloud, now: Optional[float] = None) -> List[Wall]:
        """Cadence-gated fit. See module docstring for trigger rules."""
        if now is None:
            now = time.time()
        cloud_len = len(cloud) if cloud is not None else 0
        time_elapsed = (
            self._last_fit_ts is None
            or (now - self._last_fit_ts) >= self.fit_interval_s
        )
        points_added = (
            cloud_len - self._last_fit_point_count
        ) >= self.point_count_trigger
        if not (time_elapsed or points_added):
            return list(self._walls)
        return self.fit_now(cloud, now=now)

    def fit_now(self, cloud, now: Optional[float] = None) -> List[Wall]:
        """Force-fit, bypass cadence gate. Reseeds RNG for reproducibility."""
        if now is None:
            now = time.time()
        # Reset RNG so each fit_now call is reproducible given the same seed.
        self._rng = np.random.default_rng(self._seed)

        points = self._to_xy_array(cloud)
        cloud_len = len(cloud) if cloud is not None else len(points)
        if len(points) < self.min_support:
            self._last_fit_ts = now
            self._last_fit_point_count = cloud_len
            return list(self._walls)

        new_walls_raw = self._ransac_lines(points, now)
        for raw in new_walls_raw:
            if not self._merge_wall(raw, now):
                self._walls.append(raw)

        self._last_fit_ts = now
        self._last_fit_point_count = cloud_len
        return list(self._walls)

    # ------------------------------------------------------------------
    def _to_xy_array(self, cloud) -> np.ndarray:
        """Accept list[RaycastHit], list[tuple], or Nx2+ numpy array."""
        if isinstance(cloud, np.ndarray):
            if cloud.ndim == 2 and cloud.shape[1] >= 2:
                return cloud[:, :2].astype(np.float64)
            raise ValueError(f"Unexpected cloud shape {cloud.shape}")
        if not cloud:
            return np.empty((0, 2), dtype=np.float64)
        first = cloud[0]
        if hasattr(first, "hit_x"):
            return np.array(
                [(h.hit_x, h.hit_y) for h in cloud], dtype=np.float64
            )
        return np.array(cloud, dtype=np.float64)[:, :2]

    def _ransac_lines(self, points: np.ndarray, now: float) -> List[Wall]:
        """Iteratively extract lines until no line has >= min_support inliers."""
        remaining = points.copy()
        results: List[Wall] = []
        max_lines = 16  # safety cap — avoids pathological infinite loops
        while len(remaining) >= self.min_support and len(results) < max_lines:
            best_inlier_mask: Optional[np.ndarray] = None
            best_count = 0
            n = len(remaining)
            for _ in range(self.max_iterations):
                i, j = self._rng.integers(0, n, size=2)
                if i == j:
                    continue
                p1 = remaining[i]
                p2 = remaining[j]
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                length = math.hypot(dx, dy)
                if length < 1e-6:
                    continue
                # Perpendicular distance from each point to infinite line
                # through p1-p2. Vectorized: |(p - p1) x d| / |d|.
                deltas = remaining - p1
                cross = deltas[:, 0] * dy - deltas[:, 1] * dx
                dist = np.abs(cross) / length
                mask = dist <= self.inlier_threshold
                count = int(mask.sum())
                if count > best_count:
                    best_count = count
                    best_inlier_mask = mask
            if best_count < self.min_support or best_inlier_mask is None:
                break

            inliers = remaining[best_inlier_mask]
            wall = self._line_from_inliers(inliers, support=best_count, now=now)
            if wall is not None and wall.confidence >= self.confidence_threshold:
                results.append(wall)
            # Remove inliers from remaining cloud before next line extraction.
            remaining = remaining[~best_inlier_mask]
        return results

    def _line_from_inliers(
        self, inliers: np.ndarray, support: int, now: float
    ) -> Optional[Wall]:
        """Fit a segment to the inlier extent via SVD principal direction."""
        if len(inliers) < 2:
            return None
        centroid = inliers.mean(axis=0)
        centered = inliers - centroid
        # SVD of centered points; first right-singular vector = direction.
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        direction = vh[0]
        # Project inliers onto the direction, take min/max -> segment endpoints.
        projections = centered @ direction
        t_min = float(projections.min())
        t_max = float(projections.max())
        p_start = centroid + t_min * direction
        p_end = centroid + t_max * direction
        confidence = min(1.0, support / 100.0)  # 100+ inliers saturates
        wall = Wall(
            id=self._next_wall_id,
            x1=float(p_start[0]),
            y1=float(p_start[1]),
            x2=float(p_end[0]),
            y2=float(p_end[1]),
            confidence=confidence,
            support_count=support,
            first_seen=now,
            last_seen=now,
        )
        self._next_wall_id += 1
        return wall

    def _merge_wall(self, candidate: Wall, now: float) -> bool:
        """Try to merge candidate into an existing wall.

        Merge criteria: direction vectors within ~10 degrees AND perpendicular
        offset of both endpoints < inlier_threshold. On merge: extend endpoints
        along the existing direction and accumulate support_count.
        """
        cand_dx = candidate.x2 - candidate.x1
        cand_dy = candidate.y2 - candidate.y1
        cand_len = math.hypot(cand_dx, cand_dy)
        if cand_len < 1e-6:
            return False
        cand_ang = math.degrees(math.atan2(cand_dy, cand_dx))

        for idx, existing in enumerate(self._walls):
            ex_dx = existing.x2 - existing.x1
            ex_dy = existing.y2 - existing.y1
            ex_len = math.hypot(ex_dx, ex_dy)
            if ex_len < 1e-6:
                continue
            ex_ang = math.degrees(math.atan2(ex_dy, ex_dx))
            ang_diff = abs(((cand_ang - ex_ang + 180.0) % 360.0) - 180.0)
            if not (ang_diff < 10.0 or ang_diff > 170.0):
                continue

            # Perpendicular offset of candidate endpoints to existing line
            def perp(px: float, py: float) -> float:
                return abs(
                    (px - existing.x1) * ex_dy - (py - existing.y1) * ex_dx
                ) / ex_len

            if perp(candidate.x1, candidate.y1) > self.inlier_threshold:
                continue
            if perp(candidate.x2, candidate.y2) > self.inlier_threshold:
                continue

            # Merge: project all 4 endpoints onto existing direction,
            # keep the two extremes, accumulate support.
            origin = np.array([existing.x1, existing.y1], dtype=np.float64)
            direction = np.array([ex_dx, ex_dy], dtype=np.float64) / ex_len
            xs = (existing.x1, existing.x2, candidate.x1, candidate.x2)
            ys = (existing.y1, existing.y2, candidate.y1, candidate.y2)
            t_vals = [
                float((np.array([x, y], dtype=np.float64) - origin) @ direction)
                for x, y in zip(xs, ys)
            ]
            t_min = min(t_vals)
            t_max = max(t_vals)
            new_start = origin + t_min * direction
            new_end = origin + t_max * direction
            merged = Wall(
                id=existing.id,  # preserve existing id
                x1=float(new_start[0]),
                y1=float(new_start[1]),
                x2=float(new_end[0]),
                y2=float(new_end[1]),
                confidence=min(
                    1.0, existing.confidence + candidate.confidence * 0.2
                ),
                support_count=existing.support_count + candidate.support_count,
                first_seen=min(existing.first_seen, candidate.first_seen),
                last_seen=now,
            )
            self._walls[idx] = merged
            return True
        return False
