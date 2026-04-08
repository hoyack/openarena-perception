"""Unit tests for the navigation subsystem (NAV-01..05).

Tests the extracted modules directly, not through strategic_brain.py.
Uses mocks for GameBridge, Commander, RoomSurveyor, SpatialKnowledge dependencies.

NAV-05 (obstacle avoidance) is also tested in test_combat.py::TestObstacleAvoidanceCombat.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from openarena_perception.navigation import (
    AASGraph,
    Commander,
    LearnedMap,
    NavBehavior,
    Navigator,
    RoomSurveyor,
    SurveyBehavior,
    find_exit,
    parse_aas,
)


# ---------------------------------------------------------------------------
# NAV-01: Pathfinding
# ---------------------------------------------------------------------------

class TestPathfinding:
    """NAV-01: Navigator and AAS parser imports and basic construction."""

    def test_aas_parser_import(self):
        """AASGraph and parse_aas importable from navigation.aas_parser."""
        assert AASGraph is not None
        assert parse_aas is not None
        assert callable(parse_aas)

    def test_pathfinding(self):
        """Navigator with mock bridge can be constructed and has path methods."""
        bridge = MagicMock()
        bridge.rcon.return_value = ""
        nav = Navigator(bridge, aas_path="")

        # Verify the interface exists
        assert hasattr(nav, "path_to_area")
        assert hasattr(nav, "follow_path")
        assert hasattr(nav, "path_to_random")
        assert callable(nav.path_to_area)
        assert callable(nav.follow_path)

    def test_navigator_has_path_property(self):
        """Navigator.has_path reflects path state."""
        bridge = MagicMock()
        bridge.rcon.return_value = ""
        nav = Navigator(bridge, aas_path="")

        # No path initially
        assert nav.has_path is False

    def test_nav_behavior_navigating(self, make_awareness):
        """NavBehavior.tick_navigating calls commander.decide and navigator methods."""
        ctrl = MagicMock()
        navigator = MagicMock()
        navigator.graph = MagicMock()
        navigator.graph.nearest_area.return_value = 5
        navigator.graph.areas = [MagicMock(is_liquid=False) for _ in range(10)]
        navigator.path_to_area.return_value = True
        navigator.follow_path.return_value = None

        # Commander returns a target
        commander = MagicMock()
        commander.should_decide.return_value = True
        target = MagicMock()
        target.classname = "item_health_large"
        target.x = 100.0
        target.y = 200.0
        target.z = 0.0
        target.last_visited = 0.0
        commander.decide.return_value = target

        aas_graph = MagicMock()
        behavior = NavBehavior(ctrl, navigator, commander, aas_graph)

        sa = make_awareness(has_path=False, pos=(100.0, 200.0, 0.0))
        gs = MagicMock()

        asyncio.run(behavior.tick_navigating(sa, gs, tick_count=1))

        commander.decide.assert_called_once()
        ctrl.forward.assert_called_with(True)


# ---------------------------------------------------------------------------
# NAV-02: Stuck detection
# ---------------------------------------------------------------------------

class TestStuckDetection:
    """NAV-02: Navigator stuck detection and exit finder."""

    def test_stuck_detection(self):
        """Navigator.is_stuck property reflects stuck state."""
        bridge = MagicMock()
        bridge.rcon.return_value = ""
        nav = Navigator(bridge, aas_path="")

        # Not stuck initially
        assert nav.is_stuck is False

    def test_navigator_is_recovering(self):
        """Navigator.is_recovering property exists."""
        bridge = MagicMock()
        bridge.rcon.return_value = ""
        nav = Navigator(bridge, aas_path="")

        assert hasattr(nav, "is_recovering")
        assert nav.is_recovering is False

    def test_exit_finder_import(self):
        """find_exit importable from navigation.exit_finder."""
        assert find_exit is not None
        assert callable(find_exit)


# ---------------------------------------------------------------------------
# NAV-03: Learned map
# ---------------------------------------------------------------------------

class TestLearnedMap:
    """NAV-03: LearnedMap construction and edge tracking."""

    def test_learned_map_construction(self):
        """LearnedMap can be constructed with map_name and mock graph."""
        mock_graph = MagicMock()
        mock_graph.areas = []
        lmap = LearnedMap(map_name="test_map", aas_graph=mock_graph)

        assert lmap.map_name == "test_map"

    def test_learned_map_edge_tracking(self):
        """LearnedMap.record_edge_success and record_edge_failure update internal state."""
        lmap = LearnedMap(map_name="test_map")

        # Record success
        lmap.record_edge_success(1, 2)
        # No exception means success

        # Record failure
        lmap.record_edge_failure(3, 4)
        # No exception means success

    def test_learned_map_edge_penalty(self):
        """LearnedMap.edge_penalty returns float penalty for failed edges."""
        lmap = LearnedMap(map_name="test_map")

        # No failures -- zero penalty
        assert lmap.edge_penalty(1, 2) == 0.0

        # After failure -- non-zero penalty
        lmap.record_edge_failure(1, 2)
        assert lmap.edge_penalty(1, 2) > 0.0

    def test_learned_map_edge_penalty_callable(self):
        """edge_penalty method is callable with two area IDs."""
        lmap = LearnedMap(map_name="test_map")
        result = lmap.edge_penalty(10, 20)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# NAV-04: Room surveyor and survey behavior
# ---------------------------------------------------------------------------

class TestRoomSurvey:
    """NAV-04: RoomSurveyor import and SurveyBehavior delegation."""

    def test_room_surveyor_import(self):
        """RoomSurveyor importable from navigation.room_surveyor."""
        assert RoomSurveyor is not None

    def test_survey_behavior(self, make_awareness):
        """SurveyBehavior.tick calls surveyor.perform_survey when state_time < 0.5."""
        surveyor = MagicMock()
        survey_result = MagicMock()
        survey_result.room_type = "corridor"
        survey_result.exits = [{"direction": "north"}]
        survey_result.recommended_exit = "north"
        survey_result.area_id = 5
        surveyor.perform_survey.return_value = survey_result

        spatial = MagicMock()
        behavior = SurveyBehavior(surveyor, spatial)

        sa = make_awareness(current_area=5, pos=(100.0, 200.0, 0.0), yaw=90.0)
        gs = MagicMock()

        result = asyncio.run(behavior.tick(sa, gs, state_time=0.1))

        surveyor.perform_survey.assert_called_once()
        spatial.store_survey.assert_called_once_with(survey_result)
        # Returns cooldown timestamp
        assert result is not None
        assert isinstance(result, float)

    def test_survey_behavior_no_survey_after_timeout(self, make_awareness):
        """SurveyBehavior.tick does NOT call perform_survey when state_time >= 0.5."""
        surveyor = MagicMock()
        spatial = MagicMock()
        behavior = SurveyBehavior(surveyor, spatial)

        sa = make_awareness(current_area=5, pos=(100.0, 200.0, 0.0))
        gs = MagicMock()

        result = asyncio.run(behavior.tick(sa, gs, state_time=1.0))

        surveyor.perform_survey.assert_not_called()
        assert result is None


# ---------------------------------------------------------------------------
# NAV-05: Obstacle avoidance
# ---------------------------------------------------------------------------

class TestObstacleAvoidance:
    """NAV-05: Obstacle avoidance during combat.

    Primary tests are in test_combat.py::TestObstacleAvoidanceCombat.
    This class provides a cross-reference and additional navigation-focused test.
    """

    def test_wall_avoidance_stops_forward(self, make_awareness):
        """When wall_ahead and high wall_score, forward movement stops."""
        ctrl = MagicMock()
        bridge = MagicMock()
        from openarena_perception.combat import CombatMover, CombatEngager
        mover = CombatMover()
        engager = CombatEngager(ctrl, bridge, mover)

        sa = make_awareness(
            wall_ahead=True, wall_score=0.9, open_direction=-1,
            attacker_direction=0, seconds_since_damage=5.0,
        )
        gs = MagicMock()

        asyncio.run(engager.tick(sa, gs))

        ctrl.forward.assert_any_call(False)
        # open_direction=-1 => turn_degrees(-1 * 30) = -30
        ctrl.turn_degrees.assert_any_call(-30)


# ---------------------------------------------------------------------------
# NAV-06: Respawn navigation
# ---------------------------------------------------------------------------

class TestRespawnNavigation:
    """NAV-06: NavBehavior.on_enter_exploring calls navigator.path_to_random."""

    def test_nav_behavior_exploring(self):
        """NavBehavior.on_enter_exploring calls navigator.path_to_random."""
        ctrl = MagicMock()
        navigator = MagicMock()
        commander = MagicMock()
        aas_graph = MagicMock()

        behavior = NavBehavior(ctrl, navigator, commander, aas_graph)
        behavior.on_enter_exploring()

        navigator.path_to_random.assert_called_once()

    def test_nav_behavior_exploring_resets_stuck(self):
        """on_enter_exploring resets stucks_on_current_target to 0."""
        ctrl = MagicMock()
        navigator = MagicMock()
        commander = MagicMock()
        aas_graph = MagicMock()

        behavior = NavBehavior(ctrl, navigator, commander, aas_graph)
        behavior.stucks_on_current_target = 5

        behavior.on_enter_exploring()

        assert behavior.stucks_on_current_target == 0
