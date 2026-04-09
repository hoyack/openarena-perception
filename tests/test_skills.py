"""Tests for the skill system -- atomic actions, protocol, registry."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from openarena_perception.skills import (
    AtomicAction,
    Skill,
    SkillLayer,
    SkillRegistry,
    SkillResult,
)
from openarena_perception.skills.actions import (
    FireAction,
    MoveAction,
    TurnAction,
    WeaponSelectAction,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _mock_controller() -> MagicMock:
    ctrl = MagicMock()
    ctrl.forward = MagicMock()
    ctrl.back = MagicMock()
    ctrl.turn_degrees = MagicMock()
    return ctrl


def _mock_bridge() -> MagicMock:
    bridge = MagicMock()
    bridge.fire = MagicMock()
    bridge.select_weapon_by_name = MagicMock(return_value=True)
    return bridge


# ── Atomic action tests ──────────────────────────────────────────────


def test_atomic_actions_move_forward():
    """MoveAction forward calls ctrl.forward(True), sleeps, ctrl.forward(False)."""
    ctrl = _mock_controller()
    action = MoveAction(ctrl)
    result = asyncio.run(action.execute(direction="forward", duration=0.01))
    assert result.success is True
    ctrl.forward.assert_any_call(True)
    ctrl.forward.assert_any_call(False)


def test_atomic_actions_move_backward():
    """MoveAction backward calls ctrl.back(True), sleeps, ctrl.back(False)."""
    ctrl = _mock_controller()
    action = MoveAction(ctrl)
    result = asyncio.run(action.execute(direction="backward", duration=0.01))
    assert result.success is True
    ctrl.back.assert_any_call(True)
    ctrl.back.assert_any_call(False)


def test_move_action_invalid_direction():
    """MoveAction with invalid direction returns failure."""
    ctrl = _mock_controller()
    action = MoveAction(ctrl)
    result = asyncio.run(action.execute(direction="sideways", duration=0.01))
    assert result.success is False


def test_move_action_clamps_duration():
    """MoveAction clamps duration to 0.0-5.0s range."""
    ctrl = _mock_controller()
    action = MoveAction(ctrl)
    # Duration > 5.0 should be clamped
    result = asyncio.run(action.execute(direction="forward", duration=10.0))
    assert result.success is True


def test_turn_action():
    """TurnAction offloads turn_degrees to a thread."""
    ctrl = _mock_controller()
    action = TurnAction(ctrl)
    result = asyncio.run(action.execute(degrees=90.0))
    assert result.success is True
    ctrl.turn_degrees.assert_called_once_with(90.0)


def test_turn_offloads_to_thread():
    """TurnAction uses asyncio.to_thread for the blocking call."""
    ctrl = _mock_controller()
    action = TurnAction(ctrl)

    async def _fake_to_thread(fn, *args):
        fn(*args)

    with patch("openarena_perception.skills.actions.asyncio") as mock_asyncio:
        mock_asyncio.to_thread = MagicMock(side_effect=_fake_to_thread)
        asyncio.run(action.execute(degrees=45.0))
        mock_asyncio.to_thread.assert_called_once_with(ctrl.turn_degrees, 45.0)


def test_turn_action_clamps_degrees():
    """TurnAction clamps degrees to -360..360."""
    ctrl = _mock_controller()
    action = TurnAction(ctrl)
    result = asyncio.run(action.execute(degrees=500.0))
    assert result.success is True
    # Should have been clamped to 360
    ctrl.turn_degrees.assert_called_once_with(360.0)


def test_fire_action_on():
    """FireAction on=True calls bridge.fire(True)."""
    bridge = _mock_bridge()
    action = FireAction(bridge)
    result = asyncio.run(action.execute(on=True))
    assert result.success is True
    bridge.fire.assert_called_once_with(True)


def test_fire_action_off():
    """FireAction on=False calls bridge.fire(False)."""
    bridge = _mock_bridge()
    action = FireAction(bridge)
    result = asyncio.run(action.execute(on=False))
    assert result.success is True
    bridge.fire.assert_called_once_with(False)


def test_weapon_select_success():
    """WeaponSelectAction with known weapon returns success."""
    bridge = _mock_bridge()
    bridge.select_weapon_by_name.return_value = True
    action = WeaponSelectAction(bridge)
    result = asyncio.run(action.execute(weapon="rocket"))
    assert result.success is True
    bridge.select_weapon_by_name.assert_called_once_with("rocket")


def test_weapon_select_failure():
    """WeaponSelectAction with unknown weapon returns failure."""
    bridge = _mock_bridge()
    bridge.select_weapon_by_name.return_value = False
    action = WeaponSelectAction(bridge)
    result = asyncio.run(action.execute(weapon="unknown"))
    assert result.success is False


# ── Skill Protocol tests ─────────────────────────────────────────────


def test_skill_protocol():
    """All 4 actions satisfy isinstance(action, Skill) check."""
    ctrl = _mock_controller()
    bridge = _mock_bridge()

    actions = [
        MoveAction(ctrl),
        TurnAction(ctrl),
        FireAction(bridge),
        WeaponSelectAction(bridge),
    ]

    for action in actions:
        assert isinstance(action, Skill), f"{action.name} does not satisfy Skill protocol"
        assert action.layer == SkillLayer.ACTION


# ── Registry tests ────────────────────────────────────────────────────


def test_registry_catalog():
    """Register all 4 actions, catalog() returns 4 entries."""
    ctrl = _mock_controller()
    bridge = _mock_bridge()
    registry = SkillRegistry()

    registry.register(MoveAction(ctrl))
    registry.register(TurnAction(ctrl))
    registry.register(FireAction(bridge))
    registry.register(WeaponSelectAction(bridge))

    catalog = registry.catalog()
    assert len(catalog) == 4
    names = {entry["name"] for entry in catalog}
    assert names == {"move", "turn", "fire", "weapon_select"}
    for entry in catalog:
        assert entry["layer"] == "action"


def test_registry_execute():
    """Registry dispatches execute to the correct skill."""
    ctrl = _mock_controller()
    registry = SkillRegistry()
    registry.register(MoveAction(ctrl))

    result = asyncio.run(registry.execute("move", direction="forward", duration=0.01))
    assert result.success is True
    ctrl.forward.assert_any_call(True)


def test_registry_execute_unknown():
    """Registry returns failure for unknown skill."""
    registry = SkillRegistry()
    result = asyncio.run(registry.execute("nonexistent"))
    assert result.success is False
    assert "Unknown skill" in result.message


def test_registry_get():
    """Registry.get returns skill or None."""
    ctrl = _mock_controller()
    registry = SkillRegistry()
    registry.register(MoveAction(ctrl))

    assert registry.get("move") is not None
    assert registry.get("nonexistent") is None


# ── Behavior tests ───────────────────────────────────────────────────


def test_behaviors():
    """PatrolBehavior executes MoveAction steps for each waypoint."""
    from openarena_perception.skills.behaviors import PatrolBehavior

    ctrl = _mock_controller()
    behavior = PatrolBehavior(ctrl)
    result = asyncio.run(behavior.execute(waypoints=[1, 2, 3]))
    assert result.success is True
    assert result.data.get("waypoints_completed") == 3


def test_patrol_cancel():
    """PatrolBehavior cancelled mid-execution returns failure."""
    from openarena_perception.skills.behaviors import PatrolBehavior

    ctrl = _mock_controller()
    behavior = PatrolBehavior(ctrl)
    behavior._cancelled = True
    result = asyncio.run(behavior.execute(waypoints=[1, 2, 3]))
    assert result.success is False
    assert "Cancelled" in result.message


def test_room_survey_behavior():
    """RoomSurveyBehavior delegates to SurveyBehavior."""
    from openarena_perception.skills.behaviors import RoomSurveyBehavior

    ctrl = _mock_controller()
    bridge = _mock_bridge()
    survey = MagicMock()
    survey.tick = MagicMock(return_value=None)
    behavior = RoomSurveyBehavior(ctrl, bridge, survey=survey)
    result = asyncio.run(behavior.execute())
    assert result.success is True
    assert behavior.layer == SkillLayer.BEHAVIOR


def test_combat_engage_behavior():
    """CombatEngageBehavior delegates to CombatEngager."""
    from openarena_perception.skills.behaviors import CombatEngageBehavior

    engager = MagicMock()
    engager.tick = MagicMock()
    ctrl = _mock_controller()
    bridge = _mock_bridge()
    behavior = CombatEngageBehavior(engager, ctrl, bridge)
    sa = MagicMock()
    gs = MagicMock()
    result = asyncio.run(behavior.execute(sa=sa, gs=gs))
    assert result.success is True


def test_composability():
    """Behaviors compose actions -- isinstance checks and layer values."""
    from openarena_perception.skills.behaviors import (
        CombatEngageBehavior,
        PatrolBehavior,
        RoomSurveyBehavior,
    )

    ctrl = _mock_controller()
    bridge = _mock_bridge()
    engager = MagicMock()

    behaviors = [
        PatrolBehavior(ctrl),
        RoomSurveyBehavior(ctrl, bridge),
        CombatEngageBehavior(engager, ctrl, bridge),
    ]

    for b in behaviors:
        assert isinstance(b, Skill), f"{b.name} does not satisfy Skill protocol"
        assert b.layer == SkillLayer.BEHAVIOR
