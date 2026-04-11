"""WireframePanel — first-person wireframe view for Open-Perception.

Thin wrapper over WireframeRoomRenderer + AASDepthBackend. Constructs
both once in __init__ and reuses across frames (Phase 11 pattern).

Deduplication contract: renders with extra_hud=None, draw_room_frame=False,
decoration_only=True — no numeric overlays, only TRON decoration chrome
(corner brackets, crosshair, status bar, SRC label).

Pitfall 2 (BGR/RGB): WireframeRoomRenderer returns a BGR ndarray; we
convert via ``frame[:, :, ::-1]`` then ``swapaxes(0, 1)`` so pygame sees
(width, height, RGB). A dedicated test stubs the renderer with a
known-BGR frame to verify channel order round-trips correctly.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pygame

from openarena_perception.visualization.aas_backend import AASDepthBackend
from openarena_perception.visualization.config import RoomConfig
from openarena_perception.visualization.wireframe_room import WireframeRoomRenderer


class WireframePanel:
    """First-person face-mesh wireframe panel."""

    def __init__(self, aas_graph: Any, width: int = 600, height: int = 700) -> None:
        cfg = replace(
            RoomConfig(),
            width=width,
            height=height,
            fov_deg=90.0,
            camera_height=26.0,
            hud=True,  # keep decoration chrome
            glow=False,  # cheaper on Pi; app can toggle later
            scanlines=False,
        )
        self._cfg = cfg
        self._backend = AASDepthBackend(aas_graph, camera_height=cfg.camera_height)
        self._renderer = WireframeRoomRenderer(cfg)
        self._frame_idx = 0

    def draw(self, state: Any, surface: pygame.Surface) -> None:
        cfg = self._cfg
        pos = (
            float(getattr(state, "player_x", 0.0)),
            float(getattr(state, "player_y", 0.0)),
            float(getattr(state, "player_z", 0.0)),
        )
        yaw = float(getattr(state, "player_yaw", 0.0))
        scene = self._backend.build_scene(pos, yaw, max_distance=384.0, max_areas=20)
        frame = self._renderer.render(
            pos,
            yaw,
            scene,
            extra_hud=None,
            state={
                "frame": self._frame_idx,
                "src_width": cfg.width,
                "src_height": cfg.height,
                "status_text": "// PERCEPTION ACTIVE",
            },
            draw_room_frame=False,
            decoration_only=True,
        )
        # BGR -> RGB -> pygame (Pitfall 2)
        rgb = frame[:, :, ::-1]
        pg_frame = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
        surface.blit(pg_frame, (0, 0))
        self._frame_idx += 1
