"""WireframeRoomRenderer — holodeck room frame + scene primitives + HUD.

Takes a SceneGeometry (already in camera space) and produces a BGR frame.
No AAS dependency; no GUI calls (tests enforce this); works with
opencv-python-headless.
"""
from __future__ import annotations

from typing import Any, List, Mapping, Optional, Tuple

import cv2
import numpy as np

from openarena_perception.visualization.config import RoomConfig
from openarena_perception.visualization.effects import apply_glow, apply_scanlines
from openarena_perception.visualization.hud import render_hud
from openarena_perception.visualization.projection import (
    cube_edges,
    project_depth_color,
    project_line,
    room_surface_grid,
)
from openarena_perception.visualization.scene import OBJECT_COLORS_BGR, SceneGeometry

Point3 = Tuple[float, float, float]
Segment3 = Tuple[Point3, Point3]


def _build_room_frame_segments(cfg: RoomConfig) -> List[Segment3]:
    """PRD §4.2 — 5 parametric quads tessellated into iso-line segments.

    Room is in CAMERA space: camera at origin looking +Z, +Y down, +X right.
    """
    rw, rh, rd = cfg.room_width, cfg.room_height, cfg.room_depth
    gx, gy, gz = cfg.grid_lines_x, cfg.grid_lines_y, cfg.grid_lines_z

    segs: List[Segment3] = []
    # Floor (at +Y)
    segs += room_surface_grid(
        (-rw / 2, +rh / 2, 0.5), (rw, 0, 0), (0, 0, rd - 0.5), gx, gz
    )
    # Ceiling (at -Y)
    segs += room_surface_grid(
        (-rw / 2, -rh / 2, 0.5), (rw, 0, 0), (0, 0, rd - 0.5), gx, gz
    )
    # Left wall (at -X)
    segs += room_surface_grid(
        (-rw / 2, -rh / 2, 0.5), (0, rh, 0), (0, 0, rd - 0.5), gy, gz
    )
    # Right wall (at +X)
    segs += room_surface_grid(
        (+rw / 2, -rh / 2, 0.5), (0, rh, 0), (0, 0, rd - 0.5), gy, gz
    )
    # Back wall (at +Z)
    segs += room_surface_grid(
        (-rw / 2, -rh / 2, rd), (rw, 0, 0), (0, rh, 0), gx, gy
    )
    return segs


def _seg_midpoint_z(seg: Segment3) -> float:
    return (seg[0][2] + seg[1][2]) / 2.0


class WireframeRoomRenderer:
    """Holodeck-style wireframe renderer.

    Construct once, call `render()` per frame. Room-frame geometry is
    precomputed at init time — it is fixed in camera space and does not
    change with bot pose.
    """

    def __init__(self, cfg: RoomConfig) -> None:
        self.cfg = cfg
        self._room_segments: List[Segment3] = _build_room_frame_segments(cfg)
        # Sort back-to-front by midpoint z so far lines are drawn first
        # and near lines overwrite them.
        self._room_segments.sort(key=_seg_midpoint_z, reverse=True)
        self._frame_counter = 0

    def render(
        self,
        bot_pos: Tuple[float, float, float],
        bot_yaw: float,
        scene: SceneGeometry,
        extra_hud: Optional[Mapping[str, Any]] = None,
        state: Optional[Mapping[str, Any]] = None,
    ) -> np.ndarray:
        cfg = self.cfg
        frame = np.full((cfg.height, cfg.width, 3), cfg.bg_color, dtype=np.uint8)

        # 1. Room frame (already camera space)
        self._draw_segments(frame, self._room_segments, fixed_color=None)

        # 2. Scene walls (camera space — sort back-to-front)
        scene_walls_sorted = sorted(scene.walls, key=_seg_midpoint_z, reverse=True)
        self._draw_segments(frame, scene_walls_sorted, fixed_color=None)

        # 3. Scene boxes (cubes — per-class color)
        for box in scene.boxes:
            cls, bx, by, bz, bw, bh, bd = box
            color = OBJECT_COLORS_BGR.get(cls, OBJECT_COLORS_BGR["unknown"])
            edges = list(cube_edges(bx, by, bz, bw, bh, bd))
            self._draw_segments(frame, edges, fixed_color=color)

        # 4. Effects
        if cfg.glow:
            frame = apply_glow(frame, cfg)
        if cfg.scanlines:
            frame = apply_scanlines(frame, cfg)

        # 5. HUD
        if cfg.hud:
            merged_state = dict(state or {})
            merged_state.setdefault("frame", self._frame_counter)
            merged_state.setdefault(
                "object_count", len(scene.walls) + len(scene.boxes)
            )
            merged_state.setdefault("pos", tuple(bot_pos))
            merged_state.setdefault("yaw", bot_yaw)
            render_hud(frame, cfg, merged_state, extra_hud)

        self._frame_counter += 1
        return frame

    def _draw_segments(
        self,
        frame: np.ndarray,
        segments,
        fixed_color: Optional[Tuple[int, int, int]],
    ) -> None:
        cfg = self.cfg
        for seg in segments:
            sp = project_line(seg[0], seg[1], cfg)
            if sp is None:
                continue
            (sx1, sy1), (sx2, sy2) = sp
            if fixed_color is not None:
                color = fixed_color
            else:
                color = project_depth_color(_seg_midpoint_z(seg), cfg)
            cv2.line(
                frame,
                (int(sx1), int(sy1)),
                (int(sx2), int(sy2)),
                color,
                1,
                cv2.LINE_AA,
            )
