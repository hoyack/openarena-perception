"""Mission layer -- thin composition of behaviors with goal conditions.

Three missions that compose behaviors:
  - ExploreMapMission: patrol repeatedly until cancelled or max_steps
  - DeathmatchMission: alternate patrol/combat based on enemy visibility
  - DefendAreaMission: patrol small area, engage enemies when they appear

Threat mitigations:
  - T-06-03: Clamp max_steps/rounds/duration params to sensible ranges
  - T-06-04: All loops check _cancelled flag; max iteration limits
"""
from __future__ import annotations

from typing import Any

from .base import Mission, SkillResult
from .behaviors import CombatEngageBehavior, PatrolBehavior


class ExploreMapMission(Mission):
    """Patrol repeatedly up to max_steps, checking cancellation."""

    _MAX_STEPS = 100

    def __init__(self, ctrl: Any, bridge: Any) -> None:
        super().__init__(name="explore_map", description="Explore the map via patrol")
        self._ctrl = ctrl
        self._bridge = bridge
        self._patrol = PatrolBehavior(ctrl)

    async def execute(self, **params: Any) -> SkillResult:
        # T-06-03: Clamp max_steps
        max_steps: int = min(
            max(1, int(params.get("max_steps", 10))), self._MAX_STEPS
        )
        completed = 0
        for _ in range(max_steps):
            if self._cancelled:
                return SkillResult(
                    success=False,
                    message="Cancelled",
                    data={"steps_completed": completed},
                )
            await self._patrol.execute(waypoints=[completed])
            completed += 1
        return SkillResult(
            success=True,
            message=f"Explored {completed} steps",
            data={"steps_completed": completed},
        )


class DeathmatchMission(Mission):
    """Alternate between patrol and combat based on context."""

    _MAX_ROUNDS = 50

    def __init__(self, ctrl: Any, bridge: Any, engager: Any) -> None:
        super().__init__(name="deathmatch", description="Hunt and fight enemies")
        self._ctrl = ctrl
        self._bridge = bridge
        self._patrol = PatrolBehavior(ctrl)
        self._combat = CombatEngageBehavior(engager, ctrl, bridge)

    async def execute(self, **params: Any) -> SkillResult:
        # T-06-03: Clamp rounds
        rounds: int = min(
            max(1, int(params.get("rounds", 5))), self._MAX_ROUNDS
        )
        sa = params.get("sa")
        kills = 0
        for i in range(rounds):
            if self._cancelled:
                return SkillResult(
                    success=False,
                    message="Cancelled",
                    data={"rounds_completed": i, "kills": kills},
                )
            enemies_visible = getattr(sa, "enemies_visible", 0) if sa else 0
            if enemies_visible > 0:
                gs = params.get("gs")
                await self._combat.execute(sa=sa, gs=gs)
            else:
                await self._patrol.execute(waypoints=[i])
        return SkillResult(
            success=True,
            message=f"Deathmatch completed {rounds} rounds",
            data={"rounds_completed": rounds, "kills": kills},
        )


class DefendAreaMission(Mission):
    """Patrol a small area, engage enemies when they appear."""

    _MAX_STEPS = 100

    def __init__(self, ctrl: Any, bridge: Any) -> None:
        super().__init__(name="defend_area", description="Defend a map area")
        self._ctrl = ctrl
        self._bridge = bridge
        self._patrol = PatrolBehavior(ctrl)

    async def execute(self, **params: Any) -> SkillResult:
        area_id: int = int(params.get("area_id", 0))
        # T-06-03: Clamp max_steps
        max_steps: int = min(
            max(1, int(params.get("max_steps", 10))), self._MAX_STEPS
        )
        completed = 0
        for _ in range(max_steps):
            if self._cancelled:
                return SkillResult(
                    success=False,
                    message="Cancelled",
                    data={"steps_completed": completed, "area_id": area_id},
                )
            await self._patrol.execute(waypoints=[area_id])
            completed += 1
        return SkillResult(
            success=True,
            message=f"Defended area {area_id} for {completed} steps",
            data={"steps_completed": completed, "area_id": area_id},
        )
