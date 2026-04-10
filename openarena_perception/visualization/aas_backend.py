"""AASDepthBackend — project nearby AAS face mesh into camera-space segments.

Plan 11-04 (informal gap closure on 11-03): the depth source is now the real
polyhedral face mesh parsed out of the AAS file's lumps 1-6, not the per-area
AABB from Plan 11-03. Each visible face contributes its perimeter edges as
wall segments, which gives actual room/corridor outlines with doorways as
gaps instead of phantom AABB cuboids.

Fallback: if the mesh lumps are empty (synthetic AASGraph from tests, or a
map that failed face decode) the backend falls back to the Plan 11-03 AABB
renderer so every existing hermetic test keeps working.

Pitfall 11: DO NOT read wall segments from learned_map.py — those are
vision-detected, not ground truth. Only use the parsed face mesh (or the
per-area AABB fallback).
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np

from openarena_perception.navigation.aas_parser import AASGraph
from openarena_perception.visualization.projection import NEAR_Z, world_to_camera
from openarena_perception.visualization.scene import SceneGeometry

Point3 = Tuple[float, float, float]
Segment3 = Tuple[Point3, Point3]

# 12 edges of an AABB as index pairs into an 8-vertex corner list (fallback).
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
    """Project nearby AAS face mesh into camera-space wireframe segments.

    When the parsed graph carries a face mesh (Plan 11-04), each area's faces
    are pre-expanded into line-segment endpoints at init. build_scene selects
    faces by distance, rotates them into camera space in a single batched
    transform, and clips against the near plane. When the mesh is empty the
    backend falls back to the Plan 11-03 AABB path.
    """

    def __init__(self, aas_graph: AASGraph, camera_height: float = 40.0) -> None:
        self._graph = aas_graph
        self._camera_height = camera_height

        self._mesh_mode = False
        # --- AABB fallback storage (Plan 11-03, still used when mesh is empty) ---
        self._area_centers = np.empty((0, 3), dtype=np.float64)
        self._area_edges_world = np.empty((0, 24, 3), dtype=np.float64)
        self._area_indices = np.empty((0,), dtype=np.int32)
        # --- Face-mesh storage (Plan 11-04) ---
        # Flat array of segment endpoints in world space, shape (M, 2, 3).
        self._face_segments_world = np.empty((0, 2, 3), dtype=np.float64)
        # Per-face centroid used for distance culling, shape (F, 3).
        self._face_centers = np.empty((0, 3), dtype=np.float64)
        # Slice bounds into _face_segments_world for each face: (F, 2) of
        # (start, end) rows so face i -> segments[start:end].
        self._face_seg_slices = np.empty((0, 2), dtype=np.int32)

        if _has_face_mesh(aas_graph):
            self._build_face_mesh(aas_graph)
            self._mesh_mode = self._face_segments_world.shape[0] > 0

        if not self._mesh_mode:
            self._build_aabb_fallback(aas_graph)

    # ------------------------------------------------------------------ init
    def _build_aabb_fallback(self, aas_graph: AASGraph) -> None:
        centers: list[list[float]] = []
        edges: list[np.ndarray] = []
        idxs: list[int] = []
        for a in aas_graph.areas:
            if a.mins == (0.0, 0.0, 0.0) and a.maxs == (0.0, 0.0, 0.0):
                continue
            corners = _aabb_corners(a.mins, a.maxs)
            area_edges = corners[_AABB_EDGE_INDICES]          # (12, 2, 3)
            edges.append(area_edges.reshape(-1, 3))           # (24, 3)
            centers.append([a.cx, a.cy, a.cz])
            idxs.append(a.idx)
        if centers:
            self._area_centers = np.asarray(centers, dtype=np.float64)
            self._area_edges_world = np.stack(edges, axis=0)
            self._area_indices = np.asarray(idxs, dtype=np.int32)

    def _build_face_mesh(self, aas_graph: AASGraph) -> None:
        """Expand each AAS face into perimeter line-segment endpoints.

        Walls-only filter: a face is kept iff one of frontarea/backarea is 0,
        i.e. one side is solid void. Faces with two non-zero areas are
        interior portals between walkable areas (doorways) and would clutter
        the wireframe with invisible planes. Omitting them yields real
        doorway gaps in the output.
        """
        verts = aas_graph.vertexes         # (V, 3)
        edge_pairs = aas_graph.edges       # (E, 2) int32
        edgeindex = aas_graph.edgeindex    # (EI,) int32, signed refs
        faces = aas_graph.faces            # (F, 6) int32

        if verts.size == 0 or edge_pairs.size == 0 or faces.size == 0:
            return

        num_edges = edge_pairs.shape[0]
        num_verts = verts.shape[0]
        num_faces = faces.shape[0]

        # Pre-resolve every edgeindex entry to a pair of vertex indices so we
        # can slice per-face at run time. Signed refs just indicate traversal
        # direction, which is irrelevant for line rendering — take abs().
        # Handle over-sized/negative refs defensively.
        abs_ei = np.abs(edgeindex).astype(np.int64)
        valid_ei = (abs_ei > 0) & (abs_ei < num_edges)
        # For invalid refs, point at edge 0 (the dummy edge (0, 0)) — they will
        # degenerate into zero-length segments which are harmless.
        safe_ei = np.where(valid_ei, abs_ei, 0)
        ei_verts = edge_pairs[safe_ei]    # (EI, 2) vertex indices

        segments: list[np.ndarray] = []
        centers: list[np.ndarray] = []
        slices: list[Tuple[int, int]] = []

        cursor = 0
        for f in range(num_faces):
            planenum, faceflags, numedges, firstedge, front, back = faces[f]
            # Wall filter: skip internal portal faces between two walkable areas
            if front != 0 and back != 0:
                slices.append((cursor, cursor))
                centers.append(np.zeros(3, dtype=np.float64))
                continue
            if numedges <= 0 or firstedge < 0:
                slices.append((cursor, cursor))
                centers.append(np.zeros(3, dtype=np.float64))
                continue
            end = firstedge + numedges
            if end > ei_verts.shape[0]:
                slices.append((cursor, cursor))
                centers.append(np.zeros(3, dtype=np.float64))
                continue
            vp = ei_verts[firstedge:end]       # (numedges, 2)
            # Clip vertex indices into range defensively
            if vp.max() >= num_verts or vp.min() < 0:
                slices.append((cursor, cursor))
                centers.append(np.zeros(3, dtype=np.float64))
                continue
            v0 = verts[vp[:, 0]]                # (numedges, 3)
            v1 = verts[vp[:, 1]]                # (numedges, 3)
            seg = np.stack([v0, v1], axis=1)    # (numedges, 2, 3)
            segments.append(seg)
            center = (v0.mean(axis=0) + v1.mean(axis=0)) * 0.5
            centers.append(center.astype(np.float64))
            new_cursor = cursor + seg.shape[0]
            slices.append((cursor, new_cursor))
            cursor = new_cursor

        if segments:
            self._face_segments_world = np.concatenate(segments, axis=0).astype(np.float64)
        else:
            self._face_segments_world = np.empty((0, 2, 3), dtype=np.float64)
        self._face_centers = np.asarray(centers, dtype=np.float64)
        self._face_seg_slices = np.asarray(slices, dtype=np.int32)

    # --------------------------------------------------------------- runtime
    def build_scene(
        self,
        bot_pos: Point3,
        bot_yaw: float,
        max_distance: float = 1024.0,
        max_areas: int = 20,
    ) -> SceneGeometry:
        if self._mesh_mode:
            return self._build_scene_mesh(bot_pos, bot_yaw, max_distance, max_areas)
        return self._build_scene_aabb(bot_pos, bot_yaw, max_distance, max_areas)

    def _build_scene_aabb(
        self,
        bot_pos: Point3,
        bot_yaw: float,
        max_distance: float,
        max_areas: int,
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
        near_idx = near_idx[np.argsort(dists[near_idx])][: int(max_areas)]

        selected = self._area_edges_world[near_idx]
        flat_world = selected.reshape(-1, 3)
        cam = world_to_camera(
            flat_world, bot_pos, bot_yaw, camera_height=self._camera_height
        )
        cam = np.asarray(cam).reshape(-1, 2, 3)
        return _cam_segments_to_scene(cam)

    def _build_scene_mesh(
        self,
        bot_pos: Point3,
        bot_yaw: float,
        max_distance: float,
        max_areas: int,
    ) -> SceneGeometry:
        if self._face_segments_world.shape[0] == 0:
            return SceneGeometry()

        bp = np.asarray(bot_pos, dtype=np.float64).reshape(3)

        # Distance filter at face granularity. max_areas is reinterpreted as a
        # face cap multiplier: visible face budget = max_areas * 16 (a typical
        # room/corridor face has ~4-11 edges, so ~20 areas × 16 faces = 320
        # faces, 1000-2000 segments — fits well under the perf budget).
        face_dists = np.linalg.norm(self._face_centers - bp, axis=1)
        # Only consider real faces (slices with non-zero span). Filtered-out
        # faces carry zero-length slices and zero centers.
        starts = self._face_seg_slices[:, 0]
        ends = self._face_seg_slices[:, 1]
        has_segs = ends > starts
        mask = has_segs & (face_dists <= max_distance)
        if not np.any(mask):
            return SceneGeometry()

        candidate_idx = np.where(mask)[0]
        order = np.argsort(face_dists[candidate_idx])
        face_budget = max(int(max_areas) * 16, 16)
        selected_faces = candidate_idx[order][:face_budget]

        # Gather: for each selected face, take its slice of segments. This is
        # a ragged gather, so build an index vector once then a single
        # numpy fancy-index.
        seg_indices: list[np.ndarray] = []
        for fi in selected_faces:
            s = int(starts[fi])
            e = int(ends[fi])
            if e > s:
                seg_indices.append(np.arange(s, e, dtype=np.int64))
        if not seg_indices:
            return SceneGeometry()

        idx = np.concatenate(seg_indices)
        selected_segs = self._face_segments_world[idx]   # (M, 2, 3)
        flat_world = selected_segs.reshape(-1, 3)

        cam = world_to_camera(
            flat_world, bot_pos, bot_yaw, camera_height=self._camera_height
        )
        cam = np.asarray(cam).reshape(-1, 2, 3)
        return _cam_segments_to_scene(cam)


def _has_face_mesh(graph: AASGraph) -> bool:
    return (
        graph.vertexes.size > 0
        and graph.edges.size > 0
        and graph.faces.size > 0
        and graph.edgeindex.size > 0
    )


def _cam_segments_to_scene(cam: np.ndarray) -> SceneGeometry:
    """Shared near-plane cull + tuple packing for both backends."""
    if cam.shape[0] == 0:
        return SceneGeometry()
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
