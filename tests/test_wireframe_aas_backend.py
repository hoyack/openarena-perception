"""Tests for AASDepthBackend — hermetic synthetic fixtures + real oa_dm1 smoke."""
from __future__ import annotations

import os
from typing import List, Tuple

import pytest

from openarena_perception.navigation.aas_parser import AASArea, AASGraph, parse_aas
from openarena_perception.visualization import AASDepthBackend, SceneGeometry

OA_DM1_PATH = "maps/oa_dm1.aas"

AreaSpec = Tuple[
    float, float, float,
    Tuple[float, float, float],
    Tuple[float, float, float],
]


def _synthetic_graph(specs: List[AreaSpec]) -> AASGraph:
    """Build a hermetic AASGraph for tests — mirrors the convention used by
    tests/test_property_based.py:_build_test_graph and
    tests/test_tour_metrics.py:_build_linear_graph.
    """
    areas = [AASArea(idx=0, cx=0.0, cy=0.0, cz=0.0)]  # dummy area 0
    for i, (cx, cy, cz, mn, mx) in enumerate(specs, start=1):
        areas.append(AASArea(idx=i, cx=cx, cy=cy, cz=cz, mins=mn, maxs=mx))
    return AASGraph(areas=areas, num_areas=len(areas))


def test_backend_init_skips_dummy_only() -> None:
    g = _synthetic_graph([])
    be = AASDepthBackend(g)
    assert be._area_centers.shape == (0, 3)
    assert be._area_edges_world.shape == (0, 24, 3)


def test_backend_init_precomputes_24_edge_endpoints_per_area() -> None:
    g = _synthetic_graph([
        (50.0, 50.0, 0.0, (0.0, 0.0, 0.0), (100.0, 100.0, 50.0)),
        (200.0, 200.0, 0.0, (150.0, 150.0, 0.0), (250.0, 250.0, 50.0)),
    ])
    be = AASDepthBackend(g)
    assert be._area_centers.shape == (2, 3)
    assert be._area_edges_world.shape == (2, 24, 3)


def test_build_scene_returns_segments_for_close_area() -> None:
    # Area centered 100 units north of bot, bot facing north → area is ahead
    g = _synthetic_graph([
        (0.0, 100.0, 0.0, (-10.0, 90.0, -10.0), (10.0, 110.0, 10.0)),
    ])
    be = AASDepthBackend(g, camera_height=0.0)
    scene = be.build_scene((0.0, 0.0, 0.0), 90.0, max_distance=1000.0)
    assert isinstance(scene, SceneGeometry)
    assert len(scene.walls) > 0
    assert scene.boxes == ()


def test_build_scene_culls_far_areas() -> None:
    g = _synthetic_graph([
        (0.0, 50.0, 0.0, (-10.0, 40.0, -10.0), (10.0, 60.0, 10.0)),
        (0.0, 5000.0, 0.0, (-10.0, 4990.0, -10.0), (10.0, 5010.0, 10.0)),
    ])
    be = AASDepthBackend(g, camera_height=0.0)
    scene = be.build_scene((0.0, 0.0, 0.0), 90.0, max_distance=100.0)
    # Only the near area contributes — at most 12 edges
    assert 0 < len(scene.walls) <= 12


def test_build_scene_culls_behind_camera() -> None:
    # Area entirely south of bot when bot faces north → behind camera
    g = _synthetic_graph([
        (0.0, -200.0, 0.0, (-10.0, -210.0, -10.0), (10.0, -190.0, 10.0)),
    ])
    be = AASDepthBackend(g, camera_height=0.0)
    scene = be.build_scene((0.0, 0.0, 0.0), 90.0, max_distance=1000.0)
    assert scene.walls == ()


def test_build_scene_yaw_rotation_changes_output() -> None:
    g = _synthetic_graph([
        (100.0, 0.0, 0.0, (90.0, -10.0, -10.0), (110.0, 10.0, 10.0)),
    ])
    be = AASDepthBackend(g, camera_height=0.0)
    scene_east = be.build_scene((0.0, 0.0, 0.0), 0.0, max_distance=1000.0)
    scene_north = be.build_scene((0.0, 0.0, 0.0), 90.0, max_distance=1000.0)
    assert scene_east.walls != scene_north.walls


def test_build_scene_max_areas_cap() -> None:
    specs: List[AreaSpec] = []
    for i in range(50):
        cx = float(i * 20)
        specs.append((cx, 100.0, 0.0, (cx - 5, 95, -5), (cx + 5, 105, 5)))
    g = _synthetic_graph(specs)
    be = AASDepthBackend(g, camera_height=0.0)
    scene = be.build_scene((0.0, 0.0, 0.0), 90.0, max_distance=1e6, max_areas=3)
    # At most 3 areas × 12 edges = 36 segments before culling
    assert len(scene.walls) <= 36


def test_build_scene_empty_boxes_version_b() -> None:
    g = _synthetic_graph([
        (0.0, 100.0, 0.0, (-10.0, 90.0, -10.0), (10.0, 110.0, 10.0)),
    ])
    be = AASDepthBackend(g, camera_height=0.0)
    scene = be.build_scene((0.0, 0.0, 0.0), 90.0)
    assert scene.boxes == ()


@pytest.mark.skipif(not os.path.exists(OA_DM1_PATH), reason="maps/oa_dm1.aas not present")
def test_build_scene_oa_dm1_smoke() -> None:
    g = parse_aas(OA_DM1_PATH)
    assert g is not None
    be = AASDepthBackend(g)
    # Pick a real area center as the bot pose
    pose = None
    for area in g.areas[1:]:
        if area.mins != (0.0, 0.0, 0.0):
            pose = (area.cx, area.cy, area.cz)
            break
    if pose is None:
        pytest.skip("no populated area found in oa_dm1")
    scene = be.build_scene(pose, 90.0, max_distance=1024.0, max_areas=20)
    assert len(scene.walls) > 0, "expected non-empty wall list at a real area center"
