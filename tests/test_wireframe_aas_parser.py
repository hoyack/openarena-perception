"""Backward-compat + AABB + face-mesh extraction tests for the AAS parser."""
from __future__ import annotations

import os

import numpy as np
import pytest

from openarena_perception.navigation.aas_parser import AASArea, AASGraph, parse_aas

OA_DM1_PATH = "maps/oa_dm1.aas"


def test_aas_area_default_mins_maxs_backward_compat() -> None:
    # Keyword construction without mins/maxs must still work — Pitfall 12
    area = AASArea(idx=0, cx=1.0, cy=2.0, cz=3.0)
    assert area.mins == (0.0, 0.0, 0.0)
    assert area.maxs == (0.0, 0.0, 0.0)


@pytest.mark.skipif(not os.path.exists(OA_DM1_PATH), reason="maps/oa_dm1.aas not present")
def test_parse_aas_oa_dm1_mins_maxs_contain_center() -> None:
    graph = parse_aas(OA_DM1_PATH)
    assert graph is not None
    assert graph.num_areas > 10
    # Skip area 0 (dummy per aas_parser.nearest_area)
    found = 0
    for a in graph.areas[1:]:
        if a.mins == (0.0, 0.0, 0.0) and a.maxs == (0.0, 0.0, 0.0):
            continue  # possibly a degenerate record
        assert a.mins[0] <= a.cx <= a.maxs[0], (
            f"area {a.idx} x center not in AABB: {a.mins} {a.cx} {a.maxs}"
        )
        assert a.mins[1] <= a.cy <= a.maxs[1], f"area {a.idx} y center not in AABB"
        assert a.mins[2] <= a.cz <= a.maxs[2], f"area {a.idx} z center not in AABB"
        found += 1
    assert found > 100, f"expected most areas to have populated AABBs, got {found}"


@pytest.mark.skipif(not os.path.exists(OA_DM1_PATH), reason="maps/oa_dm1.aas not present")
def test_parse_aas_oa_dm1_bounds_within_map_range() -> None:
    graph = parse_aas(OA_DM1_PATH)
    assert graph is not None
    for a in graph.areas[1:]:
        if a.mins == (0.0, 0.0, 0.0):
            continue
        assert -900 <= a.mins[0] <= 1200
        assert 400 <= a.mins[1] <= 1800
        assert -400 <= a.mins[2] <= 500
        assert -900 <= a.maxs[0] <= 1200
        assert 400 <= a.maxs[1] <= 1800
        assert -400 <= a.maxs[2] <= 500


# --- Plan 11-04: face-mesh lumps (vertexes / edges / planes / faces) ---


def test_aas_graph_default_empty_mesh_arrays_backward_compat() -> None:
    """Synthetic AASGraph (no mesh) must still construct cleanly — this
    mirrors tests/test_property_based.py::_build_test_graph, which builds
    graphs without ever touching the face mesh."""
    areas = [AASArea(idx=0, cx=0.0, cy=0.0, cz=0.0)]
    g = AASGraph(areas=areas, num_areas=1)
    assert g.vertexes.shape == (0, 3)
    assert g.edges.shape == (0, 2)
    assert g.planes.shape == (0, 4)
    assert g.faces.shape == (0, 6)
    assert g.edgeindex.shape == (0,)
    assert g.faceindex.shape == (0,)


def test_aas_area_default_numfaces_firstface_zero() -> None:
    """AASArea default-constructed (no mesh refs) keeps backward compat."""
    a = AASArea(idx=1, cx=1.0, cy=2.0, cz=3.0)
    assert a.numfaces == 0
    assert a.firstface == 0


@pytest.mark.skipif(not os.path.exists(OA_DM1_PATH), reason="maps/oa_dm1.aas not present")
def test_parse_aas_oa_dm1_face_mesh_counts() -> None:
    """Verified counts from a direct binary dump of maps/oa_dm1.aas."""
    g = parse_aas(OA_DM1_PATH)
    assert g is not None
    assert g.vertexes.shape == (4195, 3)
    assert g.edges.shape == (8544, 2)
    assert g.planes.shape == (1190, 4)
    assert g.faces.shape == (5083, 6)
    assert g.edgeindex.shape == (23677,)
    assert g.faceindex.shape == (7764,)


@pytest.mark.skipif(not os.path.exists(OA_DM1_PATH), reason="maps/oa_dm1.aas not present")
def test_parse_aas_oa_dm1_area_face_refs_populated() -> None:
    g = parse_aas(OA_DM1_PATH)
    assert g is not None
    # area 0 is the dummy / invalid record; areas[1] is the first real area.
    a1 = g.areas[1]
    assert a1.numfaces > 0
    assert a1.firstface >= 0
    # firstface + numfaces must stay inside faceindex bounds
    assert a1.firstface + a1.numfaces <= g.faceindex.shape[0]


@pytest.mark.skipif(not os.path.exists(OA_DM1_PATH), reason="maps/oa_dm1.aas not present")
def test_parse_aas_oa_dm1_face_mesh_topology_resolves() -> None:
    """Walk area 1 → faceindex → faces → edgeindex → edges → vertexes and
    assert the resolved vertex positions land inside the area's AABB. This
    is the end-to-end cross-check that every lump offset is correct.
    """
    g = parse_aas(OA_DM1_PATH)
    assert g is not None
    a1 = g.areas[1]
    mins = np.array(a1.mins)
    maxs = np.array(a1.maxs)
    tol = 1.0  # 1 Q3 unit slack for float noise

    face_refs = g.faceindex[a1.firstface : a1.firstface + a1.numfaces]
    assert face_refs.size == a1.numfaces
    for ref in face_refs:
        f_idx = int(abs(ref))
        assert 0 < f_idx < g.faces.shape[0]
        planenum, flags, numedges, firstedge, front, back = g.faces[f_idx]
        assert numedges > 0
        assert firstedge >= 0
        assert firstedge + numedges <= g.edgeindex.shape[0]
        # front/back must refer to area 1 on at least one side
        assert (front == a1.idx) or (back == a1.idx), (
            f"face {f_idx} of area {a1.idx} references front={front}, back={back}"
        )
        edge_refs = g.edgeindex[firstedge : firstedge + numedges]
        for e_ref in edge_refs:
            e_idx = int(abs(e_ref))
            assert 0 < e_idx < g.edges.shape[0]
            v0, v1 = g.edges[e_idx]
            assert 0 <= v0 < g.vertexes.shape[0]
            assert 0 <= v1 < g.vertexes.shape[0]
            p0 = g.vertexes[v0]
            p1 = g.vertexes[v1]
            for p in (p0, p1):
                assert np.all(p >= mins - tol), f"vertex {p} outside area mins {mins}"
                assert np.all(p <= maxs + tol), f"vertex {p} outside area maxs {maxs}"


@pytest.mark.skipif(not os.path.exists(OA_DM1_PATH), reason="maps/oa_dm1.aas not present")
def test_parse_aas_oa_dm1_plane_normals_unit_length() -> None:
    g = parse_aas(OA_DM1_PATH)
    assert g is not None
    normals = g.planes[:, :3]
    lengths = np.linalg.norm(normals, axis=1)
    # All planes should have unit normals; skip plane 0 (dummy)
    assert np.allclose(lengths[1:], 1.0, atol=1e-4)
