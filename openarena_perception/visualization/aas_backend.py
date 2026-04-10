"""AASDepthBackend — turn nearby AAS area AABBs into camera-space line segments.

Version B scope (per CONTEXT.md): the depth source is the AAS per-area AABB.
This is the 'AABB path' from RESEARCH.md — each area's 12 edges are emitted
as wall segments. The face-mesh path (decoding AAS lumps 0-6) is deferred.

Pitfall 11: DO NOT read wall segments from learned_map.py — those are
vision-detected, not ground truth. Only use AASGraph.areas[i].mins/maxs.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np

from openarena_perception.navigation.aas_parser import AASGraph
from openarena_perception.visualization.projection import NEAR_Z, world_to_camera
from openarena_perception.visualization.scene import SceneGeometry

Point3 = Tuple[float, float, float]
Segment3 = Tuple[Point3, Point3]

# 12 edges of an AABB as index pairs into an 8-vertex corner list.
_AABB_EDGE_INDICES = np.array(
    [
        [0, 1], [1, 2], [2, 3], [3, 0],   # bottom ring
        [4, 5], [5, 6], [6, 7], [7, 4],   # top ring
        [0, 4], [1, 5], [2, 6], [3, 7],   # verticals
    ],
    dtype=np.int32,
)


def _aabb_corners(mins: Point3, maxs: Point3) -> np.ndarray:
    x0, y0, z0 = mins
    x1, y1, z1 = maxs
    return np.array(
        [
            [x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
            [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1],
        ],
        dtype=np.float64,
    )


class AASDepthBackend:
    """Project nearby AAS area AABBs into camera space as wireframe segments."""

    def __init__(self, aas_graph: AASGraph, camera_height: float = 40.0) -> None:
        self._graph = aas_graph
        self._camera_height = camera_height

        centers: list[list[float]] = []
        edges: list[np.ndarray] = []
        idxs: list[int] = []
        for a in aas_graph.areas:
            # Skip dummy / degenerate records
            if a.mins == (0.0, 0.0, 0.0) and a.maxs == (0.0, 0.0, 0.0):
                continue
            corners = _aabb_corners(a.mins, a.maxs)          # (8, 3)
            area_edges = corners[_AABB_EDGE_INDICES]          # (12, 2, 3)
            # Flatten to (24, 3) — endpoints in interleaved order
            flat = area_edges.reshape(-1, 3)
            edges.append(flat)
            centers.append([a.cx, a.cy, a.cz])
            idxs.append(a.idx)

        if centers:
            self._area_centers = np.asarray(centers, dtype=np.float64)      # (N, 3)
            self._area_edges_world = np.stack(edges, axis=0)                # (N, 24, 3)
            self._area_indices = np.asarray(idxs, dtype=np.int32)
        else:
            self._area_centers = np.empty((0, 3), dtype=np.float64)
            self._area_edges_world = np.empty((0, 24, 3), dtype=np.float64)
            self._area_indices = np.empty((0,), dtype=np.int32)

    def build_scene(
        self,
        bot_pos: Point3,
        bot_yaw: float,
        max_distance: float = 1024.0,
        max_areas: int = 20,
    ) -> SceneGeometry:
        if self._area_centers.shape[0] == 0:
            return SceneGeometry()

        bp = np.asarray(bot_pos, dtype=np.float64).reshape(3)
        deltas = self._area_centers - bp
        dists = np.linalg.norm(deltas, axis=1)

        mask = dists <= max_distance
        if not np.any(mask):
            return SceneGeometry()

        near_idx = np.where(mask)[0]
        # Sort by distance ascending and cap at max_areas
        near_idx = near_idx[np.argsort(dists[near_idx])][: int(max_areas)]

        # Gather selected edges: shape (K, 24, 3) → flatten to (K*24, 3)
        selected = self._area_edges_world[near_idx]
        flat_world = selected.reshape(-1, 3)

        cam = world_to_camera(
            flat_world, bot_pos, bot_yaw, camera_height=self._camera_height
        )
        cam = np.asarray(cam).reshape(-1, 2, 3)   # (K*12, 2, 3) — pairs

        # Cull segments with both endpoints behind the near plane
        z1 = cam[:, 0, 2]
        z2 = cam[:, 1, 2]
        keep_mask = ~((z1 < NEAR_Z) & (z2 < NEAR_Z))
        kept = cam[keep_mask]

        walls: List[Segment3] = []
        for seg in kept:
            p1 = (float(seg[0, 0]), float(seg[0, 1]), float(seg[0, 2]))
            p2 = (float(seg[1, 0]), float(seg[1, 1]), float(seg[1, 2]))
            walls.append((p1, p2))

        return SceneGeometry(walls=tuple(walls), boxes=())
