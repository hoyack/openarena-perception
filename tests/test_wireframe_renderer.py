"""Renderer pixel spot-checks with synthetic SceneGeometry (no AAS)."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from openarena_perception.visualization import (
    OBJECT_COLORS_BGR,
    RoomConfig,
    SceneGeometry,
    WireframeRoomRenderer,
)


def _renderer(**overrides) -> WireframeRoomRenderer:
    return WireframeRoomRenderer(
        replace(RoomConfig(), hud=False, glow=False, **overrides)
    )


def test_render_returns_correct_shape_and_dtype() -> None:
    r = _renderer()
    frame = r.render((0, 0, 0), 0.0, SceneGeometry())
    assert frame.shape == (600, 960, 3)
    assert frame.dtype == np.uint8


def test_render_empty_scene_still_draws_room_frame() -> None:
    r = _renderer()
    frame = r.render((0, 0, 0), 0.0, SceneGeometry())
    # Room frame alone must produce non-bg pixels
    assert frame.sum() > 0


def test_render_wall_in_front_of_camera_adds_pixels() -> None:
    r = _renderer()
    empty = r.render((0, 0, 0), 0.0, SceneGeometry())
    scene = SceneGeometry(walls=(((-2, 0, 10), (2, 0, 10)),))
    with_wall = r.render((0, 0, 0), 0.0, scene)
    assert int(with_wall.sum()) > int(empty.sum())


def test_render_wall_behind_camera_is_culled() -> None:
    r = _renderer()
    empty = r.render((0, 0, 0), 0.0, SceneGeometry())
    scene = SceneGeometry(walls=(((-2, 0, -10), (2, 0, -10)),))
    culled = r.render((0, 0, 0), 0.0, scene)
    assert np.array_equal(empty, culled)


def test_render_box_uses_player_color() -> None:
    r = _renderer()
    empty = r.render((0, 0, 0), 0.0, SceneGeometry())
    scene = SceneGeometry(boxes=(("player", 0.0, 0.0, 8.0, 2.0, 3.0, 2.0),))
    frame = r.render((0, 0, 0), 0.0, scene)
    target = np.array(OBJECT_COLORS_BGR["player"], dtype=np.int32)
    diff = np.abs(frame.astype(np.int32) - target)
    close_mask = diff.sum(axis=-1) < 60
    assert int(close_mask.sum()) > 0, "no pixel close to player color"
    assert not np.array_equal(frame, empty)


def test_render_glow_changes_output() -> None:
    r_noglow = WireframeRoomRenderer(replace(RoomConfig(), hud=False, glow=False))
    r_glow = WireframeRoomRenderer(replace(RoomConfig(), hud=False, glow=True))
    scene = SceneGeometry(walls=(((-2, 0, 10), (2, 0, 10)),))
    a = r_noglow.render((0, 0, 0), 0.0, scene)
    b = r_glow.render((0, 0, 0), 0.0, scene)
    assert not np.array_equal(a, b)


def test_render_module_has_no_imshow_reference() -> None:
    import openarena_perception.visualization.wireframe_room as mod

    with open(mod.__file__, "r", encoding="utf-8") as f:
        src = f.read()
    assert "cv2.imshow" not in src


def test_render_hud_reflects_object_count() -> None:
    r_with_hud = WireframeRoomRenderer(replace(RoomConfig(), hud=True, glow=False))
    scene_empty = SceneGeometry()
    scene_full = SceneGeometry(
        walls=(((-2, 0, 10), (2, 0, 10)), ((0, -2, 10), (0, 2, 10))),
        boxes=(("player", 0, 0, 8, 2, 3, 2),),
    )
    a = r_with_hud.render((0, 0, 0), 0.0, scene_empty)
    b = r_with_hud.render((0, 0, 0), 0.0, scene_full)
    # HUD top-left differs because OBJECTS count text changed
    assert not np.array_equal(a[0:120, 0:260], b[0:120, 0:260])
