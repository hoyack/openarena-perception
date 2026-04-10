"""Unit tests for openarena_perception.visualization.projection.

Covers Pitfalls 1, 2, 3, 5, 6 from .planning/phases/11-wireframe-perception-grid/11-RESEARCH.md.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from openarena_perception.visualization import RoomConfig, SceneGeometry, OBJECT_COLORS_BGR
from openarena_perception.visualization.projection import (
    NEAR_Z,
    focal_length,
    project_point,
    project_line,
    room_surface_grid,
    project_depth_color,
    cube_edges,
    screen_to_room,
    world_to_camera,
)


def _cfg(**overrides) -> RoomConfig:
    # RoomConfig is frozen; use dataclasses.replace via **overrides pattern.
    from dataclasses import replace
    return replace(RoomConfig(), **overrides)


# --- focal_length ---------------------------------------------------

def test_focal_length_fov_90() -> None:
    assert focal_length(960, 90.0) == pytest.approx(480.0)


def test_focal_length_fov_60() -> None:
    expected = 960 / (2 * math.tan(math.radians(30)))
    assert focal_length(960, 60.0) == pytest.approx(expected)


# --- project_point --------------------------------------------------

def test_project_point_center() -> None:
    cfg = RoomConfig()
    assert project_point(0, 0, 10, cfg) == (480, 300)


def test_project_point_offset_x() -> None:
    cfg = RoomConfig()
    # At z=10 with fx=480: x=1 -> sx = 480 + 48 = 528
    assert project_point(1, 0, 10, cfg) == (528, 300)


def test_project_point_offset_y() -> None:
    cfg = RoomConfig()
    assert project_point(0, 1, 10, cfg) == (480, 348)


def test_project_point_behind_near_plane() -> None:
    cfg = RoomConfig()
    assert project_point(0, 0, 0.05, cfg) is None
    assert project_point(0, 0, -1, cfg) is None
    assert project_point(0, 0, 0.1, cfg) is None  # on plane is "behind"


def test_project_point_rounds_not_truncates() -> None:
    # Pitfall 6: int(round(...)) vs int(...). A small positive offset must
    # round symmetrically, not floor.
    cfg = RoomConfig()
    # 0.6/10 * 480 = 28.8 -> round -> 29
    px = project_point(0.6, 0, 10, cfg)
    assert px is not None and px[0] == 480 + 29


# --- project_line (near-plane clip, Pitfall 3) ----------------------

def test_near_clip_both_behind() -> None:
    cfg = RoomConfig()
    assert project_line((0, 0, -1), (0, 0, -2), cfg) is None


def test_near_clip_one_behind_trims() -> None:
    cfg = RoomConfig()
    res = project_line((0, 0, -5), (0, 0, 10), cfg)
    assert res is not None
    # Trimmed endpoint at z=NEAR_Z, which projects to screen center
    # (since x=y=0 along the segment)
    (sp1, sp2) = res
    assert sp1 == (480, 300)  # clipped end at NEAR_Z, centerline
    assert sp2 == (480, 300)  # far end also centerline


def test_near_clip_exact_plane_treated_as_behind() -> None:
    cfg = RoomConfig()
    # One endpoint exactly at NEAR_Z, other behind -> both behind -> None
    assert project_line((0, 0, NEAR_Z), (0, 0, -1), cfg) is None


def test_project_line_both_in_front() -> None:
    cfg = RoomConfig()
    res = project_line((1, 0, 10), (-1, 0, 10), cfg)
    assert res is not None
    (sp1, sp2) = res
    assert sp1 == (528, 300)
    assert sp2 == (432, 300)


# --- room_surface_grid ----------------------------------------------

def test_room_surface_grid_line_count() -> None:
    segs = room_surface_grid((0, 0, 0), (10, 0, 0), (0, 0, 10), divs_u=4, divs_v=3)
    assert len(segs) == (4 + 1) + (3 + 1)


def test_room_surface_grid_endpoints_on_quad() -> None:
    segs = room_surface_grid((0, 0, 0), (10, 0, 0), (0, 0, 10), divs_u=2, divs_v=2)
    # All points should be inside [0,10] x {0} x [0,10]
    for (p1, p2) in segs:
        for (x, y, z) in (p1, p2):
            assert 0 <= x <= 10
            assert y == 0
            assert 0 <= z <= 10


# --- project_depth_color --------------------------------------------

def test_project_depth_color_warning() -> None:
    cfg = RoomConfig()
    # proximity_threshold defaults to 2.0
    assert project_depth_color(1.0, cfg) == cfg.warning_color


def test_project_depth_color_near() -> None:
    cfg = _cfg(proximity_threshold=0.0)
    r, g, b = project_depth_color(0.0001, cfg)
    nr, ng, nb = cfg.near_color
    assert abs(r - nr) <= 2 and abs(g - ng) <= 2 and abs(b - nb) <= 2


def test_project_depth_color_far() -> None:
    cfg = _cfg(proximity_threshold=0.0)
    assert project_depth_color(cfg.max_depth, cfg) == cfg.far_color


def test_project_depth_color_clamps_beyond_max() -> None:
    cfg = _cfg(proximity_threshold=0.0)
    assert project_depth_color(cfg.max_depth * 10, cfg) == cfg.far_color


# --- cube_edges -----------------------------------------------------

def test_cube_edges_count() -> None:
    assert len(cube_edges(0, 0, 0, 2, 2, 2)) == 12


def test_cube_edges_eight_unique_vertices() -> None:
    segs = cube_edges(0, 0, 0, 2, 2, 2)
    verts = set()
    for (p1, p2) in segs:
        verts.add(p1)
        verts.add(p2)
    assert len(verts) == 8


def test_cube_edges_aabb_bounds() -> None:
    segs = cube_edges(5, 6, 7, 2, 4, 6)
    for (p1, p2) in segs:
        for (x, y, z) in (p1, p2):
            assert 4 <= x <= 6
            assert 4 <= y <= 8
            assert 4 <= z <= 10


# --- world_to_camera (Pitfalls 1 & 2) -------------------------------

def test_world_to_camera_north_facing_north() -> None:
    cam = world_to_camera((0, 100, 0), (0, 0, 0), 90.0, camera_height=0.0)
    assert cam[0] == pytest.approx(0, abs=1e-6)
    assert cam[1] == pytest.approx(0, abs=1e-6)
    assert cam[2] == pytest.approx(100, abs=1e-6)


def test_world_to_camera_east_facing_north() -> None:
    cam = world_to_camera((100, 0, 0), (0, 0, 0), 90.0, camera_height=0.0)
    assert cam[0] == pytest.approx(-100, abs=1e-6)
    assert cam[1] == pytest.approx(0, abs=1e-6)
    assert cam[2] == pytest.approx(0, abs=1e-6)


def test_world_to_camera_up_maps_to_negative_y() -> None:
    # Pitfall 2: world +Z up -> screen -Y up
    cam = world_to_camera((0, 0, 64), (0, 0, 0), 90.0, camera_height=0.0)
    assert cam[0] == pytest.approx(0, abs=1e-6)
    assert cam[1] == pytest.approx(-64, abs=1e-6)
    assert cam[2] == pytest.approx(0, abs=1e-6)


def test_world_to_camera_yaw_zero_faces_east() -> None:
    cam = world_to_camera((100, 0, 0), (0, 0, 0), 0.0, camera_height=0.0)
    assert cam[0] == pytest.approx(0, abs=1e-6)
    assert cam[2] == pytest.approx(100, abs=1e-6)


def test_world_to_camera_batched_ndarray() -> None:
    pts = np.array([[0, 100, 0], [100, 0, 0], [0, 0, 64]], dtype=np.float64)
    cam = world_to_camera(pts, (0, 0, 0), 90.0, camera_height=0.0)
    assert isinstance(cam, np.ndarray)
    assert cam.shape == (3, 3)
    assert cam[0, 2] == pytest.approx(100, abs=1e-6)
    assert cam[1, 0] == pytest.approx(-100, abs=1e-6)
    assert cam[2, 1] == pytest.approx(-64, abs=1e-6)


def test_world_to_camera_camera_height_offset() -> None:
    cam = world_to_camera((0, 100, 0), (0, 0, 0), 90.0, camera_height=56.0)
    assert cam[1] == pytest.approx(56.0, abs=1e-6)


# --- screen_to_room -------------------------------------------------

def test_screen_to_room_centered_box() -> None:
    cfg = RoomConfig()
    x, y, z, w, h, d = screen_to_room((470, 290, 490, 310), cfg, depth_hint=10.0)
    assert x == pytest.approx(0, abs=0.5)
    assert y == pytest.approx(0, abs=0.5)
    assert z == pytest.approx(10.0)
    assert w > 0 and h > 0 and d > 0


# --- Module separation (Pitfall: cv2 leakage) -----------------------

def test_projection_module_has_no_cv2() -> None:
    import openarena_perception.visualization.projection as proj
    # cv2 must not appear in the projection module's globals
    assert "cv2" not in proj.__dict__


# --- SceneGeometry / OBJECT_COLORS_BGR sanity -----------------------

def test_scene_geometry_defaults_empty() -> None:
    sg = SceneGeometry()
    assert sg.walls == ()
    assert sg.boxes == ()


def test_object_colors_bgr_prd_values() -> None:
    assert OBJECT_COLORS_BGR["player"] == (255, 50, 50)
    assert OBJECT_COLORS_BGR["pickup"] == (50, 255, 255)
    assert OBJECT_COLORS_BGR["wall"] == (0, 255, 100)
    assert OBJECT_COLORS_BGR["static"] == (0, 255, 100)
    assert OBJECT_COLORS_BGR["unknown"] == (180, 180, 180)
