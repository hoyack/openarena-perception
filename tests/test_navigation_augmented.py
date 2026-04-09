"""Augmented edge-case tests for the navigation subsystem (TEST-02).

Covers A* pathfinding edge cases, stuck detection thresholds, and
learned map edge cases beyond the functional NAV-01..06 tests.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from openarena_perception.navigation import LearnedMap, Navigator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_area(idx: int, cx: float, cy: float, cz: float = 0.0,
               neighbors: list | None = None, travel_types: list | None = None,
               reaches: list | None = None, is_liquid: bool = False):
    """Build a SimpleNamespace mimicking an AASArea."""
    return SimpleNamespace(
        idx=idx, cx=cx, cy=cy, cz=cz,
        neighbors=neighbors or [],
        travel_types=travel_types or [],
        reaches=reaches or [],
        is_liquid=is_liquid,
    )


def _make_graph(areas: list) -> SimpleNamespace:
    """Build a mock AASGraph from a list of area specs."""
    g = SimpleNamespace(
        areas=areas,
        num_areas=len(areas),
    )
    def area_center(idx):
        a = areas[idx]
        return (a.cx, a.cy, a.cz)
    g.area_center = area_center
    def nearest_area(x, y, z):
        best_idx = 0
        best_dist = float("inf")
        for a in areas:
            d = ((a.cx - x) ** 2 + (a.cy - y) ** 2) ** 0.5
            if d < best_dist:
                best_dist = d
                best_idx = a.idx
        return best_idx
    g.nearest_area = nearest_area
    return g


# ---------------------------------------------------------------------------
# TEST-02a: A* Pathfinding Edge Cases
# ---------------------------------------------------------------------------

class TestAStarEdgeCases:
    """Edge cases for Navigator._astar pathfinding."""

    def test_pathfinding_same_area_returns_trivial(self):
        """Pathfinding to the same area returns [area]."""
        bridge = MagicMock()
        bridge.rcon.return_value = ""
        nav = Navigator(bridge, aas_path="")

        # Build a small graph: area 0 (dummy), area 1
        areas = [
            _make_area(0, 0, 0),
            _make_area(1, 100, 100, neighbors=[]),
        ]
        nav.graph = _make_graph(areas)
        nav._current_area = 1

        result = nav._astar(1, 1)
        assert result == [1]

    def test_pathfinding_disconnected_returns_empty(self):
        """Pathfinding to an unreachable area returns empty list."""
        bridge = MagicMock()
        bridge.rcon.return_value = ""
        nav = Navigator(bridge, aas_path="")

        # Two areas with no connections
        areas = [
            _make_area(0, 0, 0),
            _make_area(1, 100, 100, neighbors=[]),
            _make_area(2, 500, 500, neighbors=[]),
        ]
        nav.graph = _make_graph(areas)
        nav._current_area = 1

        result = nav._astar(1, 2)
        assert result == []

    def test_pathfinding_connected_returns_path(self):
        """Pathfinding between connected areas returns valid path."""
        bridge = MagicMock()
        bridge.rcon.return_value = ""
        nav = Navigator(bridge, aas_path="")

        # Three connected areas: 1 -> 2 -> 3
        areas = [
            _make_area(0, 0, 0),
            _make_area(1, 0, 0, neighbors=[2], travel_types=[1]),
            _make_area(2, 100, 0, neighbors=[1, 3], travel_types=[1, 1]),
            _make_area(3, 200, 0, neighbors=[2], travel_types=[1]),
        ]
        nav.graph = _make_graph(areas)
        nav._current_area = 1

        result = nav._astar(1, 3)
        assert len(result) >= 2
        assert result[0] == 1
        assert result[-1] == 3

    def test_swim_allowed_variant_includes_swim_edges(self):
        """_astar_allow_swim allows swim travel types (7, 8)."""
        bridge = MagicMock()
        bridge.rcon.return_value = ""
        nav = Navigator(bridge, aas_path="")

        # Area 1 -> 2 connected only by swim edge (type 7)
        areas = [
            _make_area(0, 0, 0),
            _make_area(1, 0, 0, neighbors=[2], travel_types=[7]),
            _make_area(2, 100, 0, neighbors=[1], travel_types=[7]),
        ]
        nav.graph = _make_graph(areas)

        # Standard A* blocks swim -- should find no path
        result_standard = nav._astar(1, 2)
        assert result_standard == []

        # Swim-allowed A* should find a path
        result_swim = nav._astar_allow_swim(1, 2)
        assert len(result_swim) >= 2
        assert result_swim[-1] == 2


# ---------------------------------------------------------------------------
# TEST-02b: Stuck Detection Thresholds
# ---------------------------------------------------------------------------

class TestStuckDetectionThresholds:
    """Edge cases for Navigator stuck detection."""

    def test_stuck_triggers_after_threshold(self):
        """is_stuck becomes True after STUCK_COUNT consecutive below-threshold moves."""
        bridge = MagicMock()
        bridge.rcon.return_value = ""
        nav = Navigator(bridge, aas_path="")

        # Simulate positions that barely move (below STUCK_THRESHOLD=5.0)
        nav.pos = (100.0, 200.0, 0.0)
        for _ in range(nav.STUCK_COUNT):
            nav._prev_pos = nav.pos
            nav.pos = (100.0 + 1.0, 200.0, 0.0)  # moved 1 unit < 5.0
            nav._check_stuck()

        assert nav.is_stuck is True

    def test_stuck_clears_after_movement(self):
        """is_stuck clears when bot moves more than STUCK_THRESHOLD."""
        bridge = MagicMock()
        bridge.rcon.return_value = ""
        nav = Navigator(bridge, aas_path="")

        # Get stuck first
        nav.pos = (100.0, 200.0, 0.0)
        for _ in range(nav.STUCK_COUNT):
            nav._prev_pos = nav.pos
            nav.pos = (100.0, 200.0, 0.0)  # no movement
            nav._check_stuck()
        assert nav.is_stuck is True

        # Now move significantly
        nav._prev_pos = nav.pos
        nav.pos = (200.0, 300.0, 0.0)  # moved ~141 units
        nav._check_stuck()
        assert nav.is_stuck is False

    def test_zero_distance_counts_as_stuck(self):
        """Zero-distance movement (exact same position) increments stuck."""
        bridge = MagicMock()
        bridge.rcon.return_value = ""
        nav = Navigator(bridge, aas_path="")

        nav.pos = (100.0, 200.0, 0.0)
        nav._prev_pos = (100.0, 200.0, 0.0)
        nav._check_stuck()
        assert nav._stuck_count == 1

    def test_no_prev_pos_does_not_crash(self):
        """_check_stuck with no previous position does not error."""
        bridge = MagicMock()
        bridge.rcon.return_value = ""
        nav = Navigator(bridge, aas_path="")

        nav.pos = (100.0, 200.0, 0.0)
        nav._prev_pos = None
        nav._check_stuck()  # should not raise
        assert nav._stuck_count == 0


# ---------------------------------------------------------------------------
# TEST-02c: Learned Map Edge Cases
# ---------------------------------------------------------------------------

class TestLearnedMapEdgeCases:
    """Edge cases for LearnedMap edge tracking and grid operations."""

    def test_edge_penalty_unknown_edge_returns_zero(self):
        """edge_penalty returns 0.0 for edges with no recorded failures."""
        lmap = LearnedMap(map_name="test_map")
        assert lmap.edge_penalty(100, 200) == 0.0

    def test_edge_penalty_increases_with_failures(self):
        """Penalty increases with more failures on an edge."""
        lmap = LearnedMap(map_name="test_map")
        lmap.record_edge_failure(1, 2)
        p1 = lmap.edge_penalty(1, 2)
        assert p1 > 0.0

        lmap.record_edge_failure(1, 2)
        p2 = lmap.edge_penalty(1, 2)
        assert p2 >= p1

    def test_success_partially_offsets_failure(self):
        """Recording successes reduces penalty below pure failure penalty."""
        lmap = LearnedMap(map_name="test_map")
        lmap.record_edge_failure(1, 2)
        lmap.record_edge_failure(1, 2)
        p_fail = lmap.edge_penalty(1, 2)

        lmap.record_edge_success(1, 2)
        lmap.record_edge_success(1, 2)
        lmap.record_edge_success(1, 2)
        p_with_success = lmap.edge_penalty(1, 2)
        assert p_with_success <= p_fail

    def test_world_to_grid_and_grid_to_world_inverse(self):
        """_world_to_grid and _grid_to_world are approximate inverses."""
        lmap = LearnedMap(map_name="test_map")
        # Start from a grid cell, convert to world, convert back
        gx, gy = 10, 20
        wx, wy = lmap._grid_to_world(gx, gy)
        gx2, gy2 = lmap._world_to_grid(wx, wy)
        assert gx2 == gx
        assert gy2 == gy

    def test_world_to_grid_clamps_to_bounds(self):
        """_world_to_grid clamps coordinates to grid boundaries."""
        lmap = LearnedMap(map_name="test_map")
        # Very far negative should clamp to 0
        gx, gy = lmap._world_to_grid(-999999, -999999)
        assert gx == 0
        assert gy == 0

        # Very far positive should clamp to GRID_SIZE-1
        gx, gy = lmap._world_to_grid(999999, 999999)
        assert gx == lmap.GRID_SIZE - 1
        assert gy == lmap.GRID_SIZE - 1

    def test_is_passable_unknown_cell(self):
        """Unexplored (UNKNOWN) cell is passable -- bot should explore it."""
        lmap = LearnedMap(map_name="test_map")
        # Default grid is all UNKNOWN
        wx, wy = lmap._grid_to_world(32, 32)  # center of grid
        assert lmap.is_passable(wx, wy) is True

    def test_is_passable_wall_cell(self):
        """WALL cell is not passable."""
        from openarena_perception.navigation.learned_map import CellState

        lmap = LearnedMap(map_name="test_map")
        # Manually set a cell to WALL
        lmap._grid[20, 20] = CellState.WALL
        wx, wy = lmap._grid_to_world(20, 20)
        assert lmap.is_passable(wx, wy) is False

    def test_directional_failure_blocks_after_three(self):
        """Three directional failures effectively block the edge."""
        lmap = LearnedMap(map_name="test_map")
        lmap.record_edge_failure(10, 20)
        lmap.record_edge_failure(10, 20)
        lmap.record_edge_failure(10, 20)
        penalty = lmap.edge_penalty(10, 20)
        # After 3 directional failures, penalty should be very high (10000.0)
        assert penalty >= 10000.0
