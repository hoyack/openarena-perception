"""Unit tests for openarena_perception.navigation.aas_parser helpers.

Plan 12.1-01: areas_on_floor current-floor filter.
"""

from __future__ import annotations

import os

import pytest

from openarena_perception.navigation.aas_parser import (
    AASArea,
    AASGraph,
    areas_on_floor,
    parse_aas,
)


def _mk_area(idx: int, z_lo: float, z_hi: float) -> AASArea:
    return AASArea(
        idx=idx,
        cx=0.0,
        cy=0.0,
        cz=(z_lo + z_hi) / 2,
        mins=(0.0, 0.0, float(z_lo)),
        maxs=(0.0, 0.0, float(z_hi)),
    )


def _mk_graph(*areas: AASArea) -> AASGraph:
    full = [_mk_area(0, 0, 0)] + list(areas)  # dummy area 0
    return AASGraph(areas=full, num_areas=len(full))


def test_areas_on_floor_includes_area_containing_bot_z():
    g = _mk_graph(_mk_area(1, -10, 10))
    assert areas_on_floor(g, 0.0, z_tolerance=24.0) == [1]


def test_areas_on_floor_excludes_area_far_above():
    g = _mk_graph(_mk_area(1, 100, 200))
    assert areas_on_floor(g, 0.0, z_tolerance=24.0) == []


def test_areas_on_floor_excludes_area_far_below():
    g = _mk_graph(_mk_area(1, -200, -100))
    assert areas_on_floor(g, 0.0, z_tolerance=24.0) == []


def test_areas_on_floor_tolerance_band_inclusive():
    # lower edge 20 <= 0 + 24 -> area must be included
    g = _mk_graph(_mk_area(1, 20, 50))
    assert areas_on_floor(g, 0.0, z_tolerance=24.0) == [1]


def test_areas_on_floor_skips_dummy_area_zero():
    # Dummy area 0 has z-range 0..0 which DOES contain bot_z=0.
    # It must still be excluded by the skip-zero convention.
    g = _mk_graph(_mk_area(1, -10, 10))
    result = areas_on_floor(g, 0.0, z_tolerance=24.0)
    assert 0 not in result
    assert result == [1]


def test_areas_on_floor_returns_int_indices():
    g = _mk_graph(_mk_area(1, -10, 10), _mk_area(2, -5, 5))
    result = areas_on_floor(g, 0.0, z_tolerance=24.0)
    assert all(isinstance(i, int) for i in result)
    assert sorted(result) == [1, 2]


def test_areas_on_floor_real_oa_dm1():
    path = "maps/oa_dm1.aas"
    if not os.path.exists(path):
        pytest.skip("oa_dm1.aas not present")
    g = parse_aas(path)
    if g is None:
        pytest.skip("failed to parse oa_dm1.aas")
    a1 = g.areas[1]
    mid_z = (a1.mins[2] + a1.maxs[2]) / 2
    subset = areas_on_floor(g, mid_z, z_tolerance=24.0)
    assert len(subset) >= 1
    # Multi-story map: filter must drop at least one area.
    assert len(subset) < g.num_areas
    assert 1 in subset
