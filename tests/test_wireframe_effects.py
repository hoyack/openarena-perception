"""Tests for wireframe effects — Pitfall 4 (cv2.GaussianBlur odd kernel) coverage."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from openarena_perception.visualization import RoomConfig
from openarena_perception.visualization.effects import apply_glow, apply_scanlines


def _cfg(**overrides) -> RoomConfig:
    return replace(RoomConfig(), **overrides)


def test_glow_increases_nonzero_pixel_count() -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[50, 50] = (255, 255, 255)
    before = int(np.count_nonzero(frame))
    out = apply_glow(frame, RoomConfig())
    after = int(np.count_nonzero(out))
    assert after > before  # bloom spread the bright pixel


def test_glow_forces_odd_kernel_with_even_radius() -> None:
    # Pitfall 4: cv2.GaussianBlur with even kernel raises. Must not raise here.
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    out = apply_glow(frame, _cfg(glow_radius=8, glow_strength=0.3))
    assert out.shape == frame.shape
    assert out.dtype == np.uint8


def test_glow_zero_radius_is_noop() -> None:
    frame = np.full((20, 20, 3), 42, dtype=np.uint8)
    out = apply_glow(frame, _cfg(glow_radius=0))
    assert np.array_equal(out, frame)


def test_scanlines_darken_every_nth_row() -> None:
    frame = np.full((30, 30, 3), 200, dtype=np.uint8)
    out = apply_scanlines(frame, _cfg(scanline_spacing=3, scanline_strength=0.5))
    # row 0, 3, 6, ... must be darker than row 1, 2, 4, 5, ...
    for dark_row in (0, 3, 6, 9):
        for light_row in (1, 2, 4, 5):
            assert out[dark_row, 0, 0] < out[light_row, 0, 0]


def test_scanlines_preserve_uint8_dtype() -> None:
    frame = np.full((30, 30, 3), 200, dtype=np.uint8)
    out = apply_scanlines(frame, _cfg(scanline_spacing=2, scanline_strength=0.3))
    assert out.dtype == np.uint8
