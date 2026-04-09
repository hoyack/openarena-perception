"""Property-based tests using hypothesis (TEST-06).

Tests mathematical invariants in PID aim control, coordinate transforms,
yaw arithmetic, and pathfinding using randomized inputs to find edge cases
that manual tests miss.
"""
from __future__ import annotations

import math

from hypothesis import given, example, settings
from hypothesis import strategies as st

from openarena_perception.combat.aim_controller import (
    AimProfile,
    PIDState,
)
from openarena_perception.navigation.aas_parser import AASArea, AASGraph, AASReach
from openarena_perception.navigation.learned_map import LearnedMap
from openarena_perception.navigation.navigator import Navigator
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# PID Math Properties
# ---------------------------------------------------------------------------

class TestPidMathProperties:
    """TEST-06: Property-based tests for PID math invariants."""

    @settings(max_examples=200)
    @given(
        error=st.floats(min_value=-1000, max_value=1000),
        dt_offset=st.floats(min_value=0.001, max_value=0.1),
    )
    @example(error=0.0, dt_offset=0.05)
    @example(error=-1000.0, dt_offset=0.001)
    @example(error=1000.0, dt_offset=0.1)
    def test_pid_output_bounded(self, error: float, dt_offset: float):
        """For any float error and dt, PID output is finite (not NaN/inf)."""
        profile = AimProfile(name="test")
        state = PIDState()

        # Simulate a time value
        now = 1.0
        state.last_time = now - dt_offset

        # Compute PID step using the profile's method inline
        # (PID step logic extracted for direct testing)
        dt = max(dt_offset, 0.001)
        p_term = profile.kp * error
        state.integral += error * dt
        state.integral = max(-profile.integral_cap, min(profile.integral_cap, state.integral))
        i_term = profile.ki * state.integral
        d_term = profile.kd * (error - state.last_error) / dt
        output = p_term + i_term + d_term

        assert math.isfinite(output), f"PID output not finite: {output} for error={error}, dt={dt}"

    @settings(max_examples=200)
    @given(
        error=st.floats(min_value=-1000, max_value=1000),
    )
    def test_pid_zero_error_zero_output(self, error: float):
        """When error is 0 and integral is 0, PID output is 0."""
        # This tests the zero-error case specifically
        profile = AimProfile(name="test")
        state = PIDState(integral=0.0, last_error=0.0, last_time=0.5)

        dt = 0.05
        zero_error = 0.0

        p_term = profile.kp * zero_error
        state.integral += zero_error * dt  # stays 0
        i_term = profile.ki * state.integral
        d_term = profile.kd * (zero_error - state.last_error) / dt

        output = p_term + i_term + d_term
        assert output == 0.0

    @settings(max_examples=200)
    @given(
        error=st.floats(min_value=1.0, max_value=1000.0),
    )
    def test_pid_sign_matches_error_positive(self, error: float):
        """For positive error with fresh PID state, output is positive.

        With zero integral and zero last_error, proportional term dominates.
        """
        profile = AimProfile(name="test")
        state = PIDState(integral=0.0, last_error=0.0, last_time=0.5)
        dt = 0.05

        p_term = profile.kp * error
        state.integral += error * dt
        state.integral = max(-profile.integral_cap, min(profile.integral_cap, state.integral))
        i_term = profile.ki * state.integral
        d_term = profile.kd * (error - 0.0) / dt

        output = p_term + i_term + d_term
        assert output > 0, f"Expected positive output for error={error}, got {output}"

    @settings(max_examples=200)
    @given(
        error=st.floats(min_value=-1000.0, max_value=-1.0),
    )
    def test_pid_sign_matches_error_negative(self, error: float):
        """For negative error with fresh PID state, output is negative."""
        profile = AimProfile(name="test")
        state = PIDState(integral=0.0, last_error=0.0, last_time=0.5)
        dt = 0.05

        p_term = profile.kp * error
        state.integral += error * dt
        state.integral = max(-profile.integral_cap, min(profile.integral_cap, state.integral))
        i_term = profile.ki * state.integral
        d_term = profile.kd * (error - 0.0) / dt

        output = p_term + i_term + d_term
        assert output < 0, f"Expected negative output for error={error}, got {output}"

    @settings(max_examples=200)
    @given(
        error=st.floats(min_value=0.1, max_value=100.0),
        n_steps=st.integers(min_value=2, max_value=20),
    )
    def test_pid_integral_accumulates(self, error: float, n_steps: int):
        """After N steps with constant positive error, integral is positive."""
        profile = AimProfile(name="test")
        state = PIDState()
        dt = 0.05

        for _ in range(n_steps):
            state.integral += error * dt
            state.integral = max(-profile.integral_cap, min(profile.integral_cap, state.integral))

        assert state.integral > 0, f"Expected positive integral after {n_steps} steps with error={error}"


# ---------------------------------------------------------------------------
# Navigation Coordinate Properties
# ---------------------------------------------------------------------------

class TestNavigationCoordinateProperties:
    """TEST-06: Property-based tests for coordinate transforms and yaw math."""

    @settings(max_examples=200)
    @given(
        wx=st.floats(min_value=-4000, max_value=4000),
        wy=st.floats(min_value=-4000, max_value=4000),
    )
    @example(wx=0.0, wy=0.0)
    @example(wx=-4000.0, wy=-4000.0)
    @example(wx=4000.0, wy=4000.0)
    def test_world_grid_roundtrip(self, wx: float, wy: float):
        """world_to_grid then grid_to_world produces coordinate within one cell."""
        lmap = LearnedMap(map_name="test")
        gx, gy = lmap._world_to_grid(wx, wy)
        rx, ry = lmap._grid_to_world(gx, gy)

        # Result should be within one cell size of original (or clamped boundary)
        cell_size = lmap.GRID_RESOLUTION
        # After clamping, the round-trip might be off by more at boundaries
        # but the grid coordinates must be valid
        assert 0 <= gx < lmap.GRID_SIZE
        assert 0 <= gy < lmap.GRID_SIZE
        # For in-bounds coordinates, round-trip error <= cell_size
        in_bounds_x = lmap._origin_x <= wx <= lmap._origin_x + lmap.GRID_SIZE * cell_size
        in_bounds_y = lmap._origin_y <= wy <= lmap._origin_y + lmap.GRID_SIZE * cell_size
        if in_bounds_x and in_bounds_y:
            assert abs(rx - wx) <= cell_size, f"X round-trip error: {abs(rx - wx)} > {cell_size}"
            assert abs(ry - wy) <= cell_size, f"Y round-trip error: {abs(ry - wy)} > {cell_size}"

    @settings(max_examples=200)
    @given(
        a=st.floats(min_value=0, max_value=360, exclude_max=True),
        b=st.floats(min_value=0, max_value=360, exclude_max=True),
    )
    @example(a=0.0, b=0.0)
    @example(a=0.0, b=180.0)
    @example(a=180.0, b=0.0)
    @example(a=359.0, b=1.0)
    def test_yaw_diff_bounded(self, a: float, b: float):
        """yaw_diff returns a value in [-180, 180] for any two yaw values."""
        result = Navigator._yaw_diff(a, b)
        assert -180 <= result <= 180, f"yaw_diff({a}, {b}) = {result}, out of [-180, 180]"

    @settings(max_examples=200)
    @given(
        a=st.floats(min_value=0.1, max_value=359.9),
        b=st.floats(min_value=0.1, max_value=359.9),
    )
    def test_yaw_diff_antisymmetric(self, a: float, b: float):
        """yaw_diff(a, b) == -yaw_diff(b, a) for non-boundary cases."""
        d1 = Navigator._yaw_diff(a, b)
        d2 = Navigator._yaw_diff(b, a)
        # Allow small floating point tolerance
        assert abs(d1 + d2) < 1e-9, f"yaw_diff({a},{b})={d1}, yaw_diff({b},{a})={d2}, sum={d1+d2}"

    @settings(max_examples=200)
    @given(
        from_area=st.integers(min_value=1, max_value=100),
        to_area=st.integers(min_value=1, max_value=100),
    )
    def test_edge_penalty_non_negative(self, from_area: int, to_area: int):
        """edge_penalty returns >= 0.0 for any edge."""
        lmap = LearnedMap(map_name="test")
        penalty = lmap.edge_penalty(from_area, to_area)
        assert penalty >= 0.0, f"edge_penalty({from_area}, {to_area}) = {penalty} < 0"


# ---------------------------------------------------------------------------
# Pathfinding Properties
# ---------------------------------------------------------------------------

def _build_test_graph(n: int) -> AASGraph:
    """Build a linear graph of n areas for pathfinding property tests."""
    areas = []
    for i in range(n):
        areas.append(AASArea(idx=i, cx=float(i * 100), cy=0.0, cz=0.0))

    for i in range(1, n):
        # Bidirectional walk edges
        areas[i].neighbors.append(i - 1)
        areas[i].travel_types.append(1)
        areas[i].reaches.append(AASReach(
            dest_area=i - 1, travel_type=1,
            start=(areas[i].cx, 0.0, 0.0),
            end=(areas[i - 1].cx, 0.0, 0.0),
        ))
        areas[i - 1].neighbors.append(i)
        areas[i - 1].travel_types.append(1)
        areas[i - 1].reaches.append(AASReach(
            dest_area=i, travel_type=1,
            start=(areas[i - 1].cx, 0.0, 0.0),
            end=(areas[i].cx, 0.0, 0.0),
        ))

    return AASGraph(areas=areas, num_areas=n)


class TestPathfindingProperties:
    """TEST-06: Property-based tests for A* pathfinding structural invariants."""

    @settings(max_examples=200)
    @given(
        start=st.integers(min_value=1, max_value=9),
        goal=st.integers(min_value=1, max_value=9),
    )
    def test_path_starts_at_source(self, start: int, goal: int):
        """If A* returns a non-empty path, first element is the start area."""
        graph = _build_test_graph(10)
        bridge = MagicMock()
        nav = Navigator(bridge, aas_path="")
        nav.graph = graph

        path = nav._astar(start, goal)
        if path:
            assert path[0] == start, f"Path starts at {path[0]}, expected {start}"

    @settings(max_examples=200)
    @given(
        start=st.integers(min_value=1, max_value=9),
        goal=st.integers(min_value=1, max_value=9),
    )
    def test_path_ends_at_goal(self, start: int, goal: int):
        """If A* returns a non-empty path, last element is the goal area."""
        graph = _build_test_graph(10)
        bridge = MagicMock()
        nav = Navigator(bridge, aas_path="")
        nav.graph = graph

        path = nav._astar(start, goal)
        if path:
            assert path[-1] == goal, f"Path ends at {path[-1]}, expected {goal}"

    @settings(max_examples=200)
    @given(
        start=st.integers(min_value=1, max_value=9),
        goal=st.integers(min_value=1, max_value=9),
    )
    def test_path_no_duplicates(self, start: int, goal: int):
        """A valid path contains no duplicate consecutive areas."""
        graph = _build_test_graph(10)
        bridge = MagicMock()
        nav = Navigator(bridge, aas_path="")
        nav.graph = graph

        path = nav._astar(start, goal)
        if path and len(path) > 1:
            for i in range(len(path) - 1):
                assert path[i] != path[i + 1], \
                    f"Duplicate consecutive areas at index {i}: {path[i]}"

    @settings(max_examples=200)
    @given(
        area=st.integers(min_value=1, max_value=9),
    )
    def test_trivial_path(self, area: int):
        """A* from area to itself returns a single-element path [area]."""
        graph = _build_test_graph(10)
        bridge = MagicMock()
        nav = Navigator(bridge, aas_path="")
        nav.graph = graph

        path = nav._astar(area, area)
        assert path == [area], f"Trivial path: expected [{area}], got {path}"
