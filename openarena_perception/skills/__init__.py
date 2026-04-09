"""OpenArena Perception -- skills subsystem.

Three-layer skill hierarchy: actions, behaviors, missions.
"""
from __future__ import annotations

from .base import (
    AtomicAction,
    ComposedBehavior,
    Mission,
    Skill,
    SkillLayer,
    SkillRegistry,
    SkillResult,
)
from .behaviors import CombatEngageBehavior, PatrolBehavior, RoomSurveyBehavior
from .catalog import build_registry
from .missions import DeathmatchMission, DefendAreaMission, ExploreMapMission

__all__ = [
    "AtomicAction",
    "ComposedBehavior",
    "Mission",
    "Skill",
    "SkillLayer",
    "SkillRegistry",
    "SkillResult",
    "PatrolBehavior",
    "RoomSurveyBehavior",
    "CombatEngageBehavior",
    "ExploreMapMission",
    "DeathmatchMission",
    "DefendAreaMission",
    "build_registry",
]
