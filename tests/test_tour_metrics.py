"""Tour testing with measurable metrics (TEST-05).

Validates the Navigator + RoomSurveyor pipeline with metrics tracking:
  - stuck_count: how many times navigator reported stuck during tour
  - completion_time_s: wall-clock time for tour simulation
  - areas_visited: count of areas the tour successfully visited
  - areas_skipped: count of unreachable/skipped areas
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Set
from unittest.mock import MagicMock, patch

import pytest

from openarena_perception.navigation.aas_parser import AASArea, AASGraph, AASReach
from openarena_perception.navigation.navigator import Navigator
from openarena_perception.navigation.room_surveyor import RoomSurvey, RoomSurveyor


# ---------------------------------------------------------------------------
# Tour metrics dataclass
# ---------------------------------------------------------------------------

@dataclass
class TourMetrics:
    """Tracks measurable quality metrics during a simulated tour."""
    stuck_count: int = 0
    completion_time_s: float = 0.0
    areas_visited: List[int] = field(default_factory=list)
    areas_skipped: List[int] = field(default_factory=list)

    @property
    def total_visited(self) -> int:
        return len(self.areas_visited)

    @property
    def total_skipped(self) -> int:
        return len(self.areas_skipped)


# ---------------------------------------------------------------------------
# Helpers to build mock AAS graphs
# ---------------------------------------------------------------------------

def _build_linear_graph(num_areas: int) -> AASGraph:
    """Build a simple linear graph: 0(dummy) -> 1 -> 2 -> ... -> N-1.

    Each area connects to its neighbors with walk reachability.
    """
    areas = []
    for i in range(num_areas):
        area = AASArea(
            idx=i,
            cx=float(i * 500),
            cy=0.0,
            cz=0.0,
        )
        areas.append(area)

    # Wire neighbors (bidirectional walk edges)
    for i in range(1, num_areas):
        prev = areas[i - 1]
        curr = areas[i]
        # Forward edge
        curr.neighbors.append(i - 1)
        curr.travel_types.append(1)  # TRAVEL_WALK
        curr.reaches.append(AASReach(
            dest_area=i - 1,
            travel_type=1,
            start=(curr.cx, curr.cy, curr.cz),
            end=(prev.cx, prev.cy, prev.cz),
        ))
        # Backward edge
        prev.neighbors.append(i)
        prev.travel_types.append(1)
        prev.reaches.append(AASReach(
            dest_area=i,
            travel_type=1,
            start=(prev.cx, prev.cy, prev.cz),
            end=(curr.cx, curr.cy, curr.cz),
        ))

    return AASGraph(areas=areas, num_areas=num_areas)


def _build_graph_with_island(num_connected: int) -> AASGraph:
    """Build a graph where most areas are connected but the last is isolated.

    The isolated area has a valid index (len(areas)-1) but no neighbor edges,
    so A* cannot reach it from any connected area.
    """
    graph = _build_linear_graph(num_connected)
    island_id = len(graph.areas)  # next valid index
    island = AASArea(
        idx=island_id,
        cx=9999.0,
        cy=9999.0,
        cz=0.0,
    )
    graph.areas.append(island)
    graph.num_areas = len(graph.areas)
    return graph, island_id


def _simulate_tour(
    graph: AASGraph,
    target_areas: List[int],
    force_stuck_at: Set[int] | None = None,
) -> TourMetrics:
    """Simulate a tour through target areas using real Navigator A* logic.

    Uses a mocked GameBridge (no real game needed). The navigator's position
    is teleported along the A* path to simulate movement.

    Args:
        graph: AAS navigation graph.
        target_areas: list of area IDs to visit in order.
        force_stuck_at: set of area IDs where the navigator reports stuck.

    Returns:
        TourMetrics with tour results.
    """
    if force_stuck_at is None:
        force_stuck_at = set()

    bridge = MagicMock()
    bridge.rcon.return_value = ""

    nav = Navigator(bridge, aas_path="")
    nav.graph = graph

    metrics = TourMetrics()
    start_time = time.monotonic()

    # Start at area 1 (skip dummy area 0)
    nav._current_area = 1
    start_area = graph.areas[1]
    nav.pos = (start_area.cx, start_area.cy, start_area.cz)

    for target in target_areas:
        # Check if target is reachable via A*
        path = nav._astar(nav._current_area, target)

        if not path or len(path) < 1:
            metrics.areas_skipped.append(target)
            continue

        # Check forced stuck
        if nav._current_area in force_stuck_at:
            metrics.stuck_count += 1
            # In real tour, stuck recovery would kick in; here we just note it
            # and continue (simulating successful recovery)

        # Teleport along path to simulate traversal
        for area_id in path:
            area = graph.areas[area_id]
            nav._current_area = area_id
            nav.pos = (area.cx, area.cy, area.cz)

        metrics.areas_visited.append(target)

    metrics.completion_time_s = time.monotonic() - start_time
    return metrics


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestTourMetrics:
    """TEST-05: Tour completion with measurable metrics."""

    def test_tour_completes_without_stuck(self):
        """Simulate tour through 5 connected areas with zero stuck events."""
        graph = _build_linear_graph(6)  # areas 0..5
        targets = [2, 3, 4, 5]

        metrics = _simulate_tour(graph, targets)

        assert metrics.stuck_count == 0
        assert metrics.total_visited == len(targets)
        assert set(metrics.areas_visited) == set(targets)
        assert metrics.total_skipped == 0

    def test_tour_records_completion_time(self):
        """Measure wall-clock time for tour simulation; must be positive."""
        graph = _build_linear_graph(6)
        targets = [2, 3, 4, 5]

        metrics = _simulate_tour(graph, targets)

        assert metrics.completion_time_s > 0
        # A simulated tour with no real I/O should be fast
        assert metrics.completion_time_s < 5.0

    def test_tour_stuck_count_incremented(self):
        """Force stuck at one area; stuck_count should be >= 1."""
        graph = _build_linear_graph(6)
        targets = [2, 3, 4, 5]

        metrics = _simulate_tour(graph, targets, force_stuck_at={1})

        assert metrics.stuck_count >= 1
        # Tour should still complete (stuck recovery simulated)
        assert metrics.total_visited == len(targets)

    def test_tour_handles_unreachable_area(self):
        """Tour with an isolated (unreachable) target skips it gracefully."""
        graph, island_id = _build_graph_with_island(num_connected=5)
        # Targets include the unreachable island area
        targets = [2, 3, island_id, 4]

        metrics = _simulate_tour(graph, targets)

        # Island area should be skipped (no path from connected graph)
        assert island_id in metrics.areas_skipped
        # Other areas should be visited
        assert 2 in metrics.areas_visited
        assert 3 in metrics.areas_visited
        assert 4 in metrics.areas_visited
        assert metrics.total_skipped >= 1

    def test_tour_visual_verification_data(self):
        """Verify RoomSurvey data structure has required fields for visual verification."""
        survey = RoomSurvey(
            area_id=5,
            position=(100.0, 200.0, 0.0),
            yaw_at_survey=90.0,
            timestamp=time.time(),
            room_type="corridor",
            exits=[
                {"direction": "N", "type": "doorway", "description": "wide corridor"},
                {"direction": "S", "type": "stairs_down", "description": "descending"},
            ],
            items=[
                {"direction": "E", "type": "health", "description": "large health pack"},
            ],
            vantage_points=[],
            hazards=[],
            recommended_exit="N",
            summary="A long corridor with exits north and south, health pack to the east.",
        )

        # Verify required fields exist for visual verification
        assert survey.area_id == 5
        assert isinstance(survey.items, list)
        assert len(survey.items) > 0
        assert "type" in survey.items[0]
        assert "description" in survey.items[0]
        assert survey.summary != ""
        assert survey.room_type != ""

        # Verify exit data
        assert len(survey.exits) == 2
        assert all("direction" in e for e in survey.exits)
        assert all("type" in e for e in survey.exits)

    def test_tour_metrics_dataclass_defaults(self):
        """TourMetrics initializes with zero/empty defaults."""
        m = TourMetrics()
        assert m.stuck_count == 0
        assert m.completion_time_s == 0.0
        assert m.areas_visited == []
        assert m.areas_skipped == []
        assert m.total_visited == 0
        assert m.total_skipped == 0

    def test_tour_all_areas_visited_in_order(self):
        """Tour visits areas in the requested order."""
        graph = _build_linear_graph(8)
        targets = [2, 4, 6, 7]

        metrics = _simulate_tour(graph, targets)

        assert metrics.areas_visited == targets
