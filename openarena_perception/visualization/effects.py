"""CRT-style visual effects: Gaussian glow and scanlines.

Both functions are pure wrappers around OpenCV primitives that return a new
BGR frame. Do not mutate inputs.

Pitfall 4 (RESEARCH.md P7): cv2.GaussianBlur requires an odd kernel; we force
it via `k | 1`.
"""
from __future__ import annotations

import cv2
import numpy as np

from openarena_perception.visualization.config import RoomConfig


def apply_glow(frame: np.ndarray, cfg: RoomConfig) -> np.ndarray:
    """CRT phosphor bloom: blur + additive composite.

    Returns a new frame; does not mutate the input. If glow_radius or
    glow_strength is non-positive, returns the input frame unchanged.
    """
    if cfg.glow_radius <= 0 or cfg.glow_strength <= 0:
        return frame
    k = cfg.glow_radius | 1  # force odd — Pitfall 4
    blurred = cv2.GaussianBlur(frame, (k, k), 0)
    return cv2.addWeighted(frame, 1.0, blurred, cfg.glow_strength, 0)


def apply_scanlines(frame: np.ndarray, cfg: RoomConfig) -> np.ndarray:
    """Horizontal CRT scanline darkening.

    Every cfg.scanline_spacing-th row is darkened by cfg.scanline_strength.
    Output preserves uint8 dtype.
    """
    if cfg.scanline_spacing <= 0 or cfg.scanline_strength <= 0:
        return frame
    h = frame.shape[0]
    mask = np.ones((h, 1, 1), dtype=np.float32)
    mask[:: cfg.scanline_spacing] = 1.0 - cfg.scanline_strength
    out = frame.astype(np.float32) * mask
    return np.clip(out, 0, 255).astype(np.uint8)
