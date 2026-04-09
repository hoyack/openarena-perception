"""Skill catalog -- build_registry() factory for the full skill system.

Creates a SkillRegistry with all 10 skills:
  4 actions:   move, turn, fire, weapon_select
  3 behaviors: patrol, room_survey, combat_engage
  3 missions:  explore_map, deathmatch, defend_area
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .actions import FireAction, MoveAction, TurnAction, WeaponSelectAction
from .base import SkillRegistry
from .behaviors import CombatEngageBehavior, PatrolBehavior, RoomSurveyBehavior
from .missions import DeathmatchMission, DefendAreaMission, ExploreMapMission

if TYPE_CHECKING:
    pass


def build_registry(
    ctrl: Any,
    bridge: Any,
    engager: Any = None,
    survey: Any = None,
) -> SkillRegistry:
    """Create a fully-populated SkillRegistry with all 10 skills.

    Args:
        ctrl: VirtualController instance
        bridge: GameBridge instance
        engager: Optional CombatEngager instance (for combat behaviors/missions)
        survey: Optional SurveyBehavior instance (for room survey)

    Returns:
        SkillRegistry with 4 actions + 3 behaviors + 3 missions registered.
    """
    registry = SkillRegistry()

    # Actions (4)
    registry.register(MoveAction(ctrl))
    registry.register(TurnAction(ctrl))
    registry.register(FireAction(bridge))
    registry.register(WeaponSelectAction(bridge))

    # Behaviors (3)
    registry.register(PatrolBehavior(ctrl))
    registry.register(RoomSurveyBehavior(ctrl, bridge, survey=survey))
    registry.register(CombatEngageBehavior(engager, ctrl, bridge))

    # Missions (3)
    registry.register(ExploreMapMission(ctrl, bridge))
    registry.register(DeathmatchMission(ctrl, bridge, engager))
    registry.register(DefendAreaMission(ctrl, bridge))

    return registry
