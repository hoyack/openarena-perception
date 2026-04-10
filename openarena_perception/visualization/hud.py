"""HUD overlay rendering — PRD §6.1 exact elements.

Pitfall 8: all text uses cv2.FONT_HERSHEY_PLAIN (compiled into OpenCV,
not loaded from a file). No external font files are referenced.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

import cv2
import numpy as np

from openarena_perception.visualization.config import RoomConfig

FONT = cv2.FONT_HERSHEY_PLAIN
FONT_SCALE = 0.9
FONT_THICK = 1
LINE_H = 14


def _put(
    frame: np.ndarray,
    text: str,
    org: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    cv2.putText(frame, text, org, FONT, FONT_SCALE, color, FONT_THICK, cv2.LINE_AA)


def _draw_corner_brackets(frame: np.ndarray, cfg: RoomConfig) -> None:
    h, w = frame.shape[:2]
    L = 20  # bracket arm length
    I = 3  # inset
    c = cfg.grid_color
    # top-left
    cv2.line(frame, (I, I), (I + L, I), c, 1, cv2.LINE_AA)
    cv2.line(frame, (I, I), (I, I + L), c, 1, cv2.LINE_AA)
    # top-right
    cv2.line(frame, (w - I - 1, I), (w - I - 1 - L, I), c, 1, cv2.LINE_AA)
    cv2.line(frame, (w - I - 1, I), (w - I - 1, I + L), c, 1, cv2.LINE_AA)
    # bottom-left
    cv2.line(frame, (I, h - I - 1), (I + L, h - I - 1), c, 1, cv2.LINE_AA)
    cv2.line(frame, (I, h - I - 1), (I, h - I - 1 - L), c, 1, cv2.LINE_AA)
    # bottom-right
    cv2.line(
        frame, (w - I - 1, h - I - 1), (w - I - 1 - L, h - I - 1), c, 1, cv2.LINE_AA
    )
    cv2.line(
        frame, (w - I - 1, h - I - 1), (w - I - 1, h - I - 1 - L), c, 1, cv2.LINE_AA
    )


def _draw_crosshair(frame: np.ndarray, cfg: RoomConfig) -> None:
    cx, cy = cfg.width // 2, cfg.height // 2
    cv2.line(frame, (cx - 5, cy), (cx + 5, cy), cfg.accent_color, 1, cv2.LINE_AA)
    cv2.line(frame, (cx, cy - 5), (cx, cy + 5), cfg.accent_color, 1, cv2.LINE_AA)
    # Guarantee center pixel is accent (AA line may soften it)
    frame[cy, cx] = cfg.accent_color


def render_hud(
    frame: np.ndarray,
    cfg: RoomConfig,
    state: Optional[Mapping[str, Any]] = None,
    extra_hud: Optional[Mapping[str, Any]] = None,
) -> np.ndarray:
    """Draw PRD §6.1 HUD overlay onto frame in place. Returns the same frame."""
    if not cfg.hud:
        return frame
    state = state or {}
    h, w = frame.shape[:2]

    # Top-left fixed block
    x0 = 8
    y = 16
    txt_color = cfg.grid_color

    _put(frame, f"FRAME {int(state.get('frame', 0)):06d}", (x0, y), txt_color)
    y += LINE_H
    _put(
        frame,
        f"ROOM {cfg.room_width:g}x{cfg.room_height:g}x{cfg.room_depth:g}",
        (x0, y),
        txt_color,
    )
    y += LINE_H
    _put(
        frame,
        f"FOV {cfg.fov_deg:g} GRID {cfg.grid_lines_x}x{cfg.grid_lines_y}x{cfg.grid_lines_z}",
        (x0, y),
        txt_color,
    )
    y += LINE_H
    _put(frame, f"MODE: {state.get('mode', 'DEMO')}", (x0, y), cfg.accent_color)
    y += LINE_H
    _put(
        frame,
        f"OBJECTS: {int(state.get('object_count', 0))}",
        (x0, y),
        txt_color,
    )
    y += LINE_H

    # Extra HUD fields (bot state integration point)
    if extra_hud:
        y += 4
        for i, (k, v) in enumerate(extra_hud.items()):
            if i >= 10:
                break
            _put(frame, f"{k}: {v}", (x0, y), cfg.accent_color)
            y += LINE_H

    # Crosshair
    _draw_crosshair(frame, cfg)

    # Bottom-left status bar
    status = state.get("status_text", "// SPATIAL GRID ACTIVE")
    _put(frame, status, (x0, h - 10), cfg.accent_color)

    # Bottom-right source resolution
    src_w = int(state.get("src_width", cfg.width))
    src_h = int(state.get("src_height", cfg.height))
    src_txt = f"SRC {src_w}x{src_h}"
    (tw, _th), _ = cv2.getTextSize(src_txt, FONT, FONT_SCALE, FONT_THICK)
    _put(frame, src_txt, (w - tw - 10, h - 10), txt_color)

    # Corner brackets
    _draw_corner_brackets(frame, cfg)

    return frame
