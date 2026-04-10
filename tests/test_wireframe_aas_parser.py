"""Backward-compat + AABB extraction tests for the extended AAS parser."""
from __future__ import annotations

import os

import pytest

from openarena_perception.navigation.aas_parser import AASArea, parse_aas

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
