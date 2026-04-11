"""Tests for HUD overlay — PRD §6.1 coverage."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from openarena_perception import visualization as vis_pkg
from openarena_perception.visualization import RoomConfig
from openarena_perception.visualization.hud import render_hud


def _blank() -> np.ndarray:
    return np.zeros((600, 960, 3), dtype=np.uint8)


def test_hud_top_left_has_text_pixels() -> None:
    frame = _blank()
    render_hud(frame, RoomConfig(), state={"frame": 42, "mode": "DEMO"})
    region = frame[0:120, 0:260]
    assert region.sum() > 0, "HUD top-left block produced no pixels"


def test_hud_crosshair_center_pixel() -> None:
    cfg = RoomConfig()
    frame = _blank()
    render_hud(frame, cfg)
    cx, cy = cfg.width // 2, cfg.height // 2
    assert tuple(int(v) for v in frame[cy, cx]) == cfg.accent_color


def test_hud_all_four_corners_have_brackets() -> None:
    frame = _blank()
    render_hud(frame, RoomConfig())
    h, w = frame.shape[:2]
    assert frame[0:25, 0:25].sum() > 0, "top-left bracket missing"
    assert frame[0:25, w - 25 : w].sum() > 0, "top-right bracket missing"
    assert frame[h - 25 : h, 0:25].sum() > 0, "bottom-left bracket missing"
    assert frame[h - 25 : h, w - 25 : w].sum() > 0, "bottom-right bracket missing"


def test_hud_extra_fields_drawn_below_fixed_block() -> None:
    frame = _blank()
    render_hud(
        frame,
        RoomConfig(),
        state={"frame": 1},
        extra_hud={"HP": 100, "AMMO": 50, "TARGET": "none"},
    )
    # Extras live below the 5 fixed lines — roughly y ∈ [95, 170]
    assert frame[95:170, 0:260].sum() > 0


def test_hud_bottom_right_source_res() -> None:
    frame = _blank()
    render_hud(frame, RoomConfig(), state={"src_width": 640, "src_height": 480})
    h, w = frame.shape[:2]
    assert frame[h - 20 : h, w - 220 : w].sum() > 0


def test_hud_respects_hud_flag_false() -> None:
    frame = _blank()
    render_hud(frame, replace(RoomConfig(), hud=False))
    assert frame.sum() == 0


def test_hud_uses_hershey_font_only() -> None:
    import openarena_perception.visualization.hud as mod

    with open(mod.__file__, "r", encoding="utf-8") as f:
        src = f.read()
    assert "FONT_HERSHEY" in src
    assert "freetype" not in src.lower()
    assert "truetype" not in src.lower()


def test_hud_module_reachable_from_package() -> None:
    # Sanity — the package exposes RoomConfig so the test above can use it.
    assert vis_pkg.RoomConfig is RoomConfig


# --- Phase 12-02: decoration_only mode ----------------------------------


def _small_blank() -> np.ndarray:
    # 300x400 (h,w) — matches the region assertions in the plan.
    return np.zeros((300, 400, 3), dtype=np.uint8)


def _small_cfg() -> RoomConfig:
    return replace(RoomConfig(), width=400, height=300)


def test_render_hud_default_draws_numeric_text() -> None:
    frame = _small_blank()
    render_hud(frame, _small_cfg(), state={"frame": 42, "mode": "DEMO"})
    # FRAME text region: roughly x in [10, 200], y in [10, 35]
    assert frame[10:35, 10:200].sum() > 0, "default mode should draw FRAME text"


def test_render_hud_decoration_only_suppresses_numeric_text() -> None:
    frame = _small_blank()
    render_hud(
        frame,
        _small_cfg(),
        state={"frame": 42, "mode": "DEMO"},
        decoration_only=True,
    )
    # FRAME text region must be untouched (bg only)
    assert frame[10:35, 10:200].sum() == 0, (
        "decoration_only=True must not draw FRAME/ROOM/FOV/MODE/OBJECTS text"
    )
    # But corner brackets must still exist
    assert frame[0:30, 0:30].sum() > 0, (
        "decoration_only=True must still draw top-left corner bracket"
    )


def test_render_hud_decoration_only_suppresses_extra_hud() -> None:
    frame = _small_blank()
    render_hud(
        frame,
        _small_cfg(),
        state={"frame": 1},
        extra_hud={"HP": 100, "AMMO": 50},
        decoration_only=True,
    )
    # Top-left text column should be clean (bg only); extras normally live
    # below the fixed block. Clamp region to avoid the center crosshair.
    assert frame[10:140, 10:180].sum() == 0, (
        "decoration_only=True must not draw extra_hud rows"
    )


def test_wireframe_renderer_forwards_decoration_only() -> None:
    from openarena_perception.visualization.scene import SceneGeometry
    from openarena_perception.visualization.wireframe_room import (
        WireframeRoomRenderer,
    )

    cfg = replace(RoomConfig(), width=400, height=300, glow=False, scanlines=False)
    renderer = WireframeRoomRenderer(cfg)
    empty_scene = SceneGeometry(walls=[], boxes=[])
    frame = renderer.render(
        (0.0, 0.0, 0.0),
        0.0,
        empty_scene,
        extra_hud=None,
        state={"frame": 0, "mode": "DEMO"},
        draw_room_frame=False,
        decoration_only=True,
    )
    # No FRAME text in top-left region
    assert frame[10:35, 10:200].sum() == 0, (
        "WireframeRoomRenderer.render(decoration_only=True) must suppress FRAME text"
    )
    # Corner bracket still present
    assert frame[0:30, 0:30].sum() > 0, (
        "WireframeRoomRenderer.render(decoration_only=True) must keep corner brackets"
    )
