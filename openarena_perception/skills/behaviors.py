"""Behavior layer -- thin wrappers composing atomic actions.

Three behaviors that wrap existing subsystems with async interface + cancellation:
  - PatrolBehavior: sequences move+turn for waypoints
  - RoomSurveyBehavior: 4x turn with optional SurveyBehavior delegation
  - CombatEngageBehavior: delegates to CombatEngager.tick
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from .actions import MoveAction, TurnAction
from .base import ComposedBehavior, SkillResult

if TYPE_CHECKING:
    pass


class PatrolBehavior(ComposedBehavior):
    """Patrol through waypoints via move+turn sequences."""

    def __init__(self, ctrl: Any) -> None:
        super().__init__(name="patrol", description="Patrol through waypoints")
        self._ctrl = ctrl
        self._move = MoveAction(ctrl)
        self._turn = TurnAction(ctrl)

    async def execute(self, **params: Any) -> SkillResult:
        waypoints: list = params.get("waypoints") or [1]
        completed = 0
        for _wp in waypoints:
            if self._cancelled:
                return SkillResult(
                    success=False,
                    message="Cancelled",
                    data={"waypoints_completed": completed},
                )
            await self._move.execute(direction="forward", duration=1.0)
            await self._turn.execute(degrees=90.0)
            completed += 1
        return SkillResult(
            success=True,
            message=f"Patrol completed {completed} waypoints",
            data={"waypoints_completed": completed},
        )


class RoomSurveyBehavior(ComposedBehavior):
    """4x 90-degree turn survey, optionally delegating to SurveyBehavior."""

    def __init__(
        self, ctrl: Any, bridge: Any, survey: Any = None
    ) -> None:
        super().__init__(name="room_survey", description="360-degree room survey")
        self._ctrl = ctrl
        self._bridge = bridge
        self._survey = survey
        self._turn = TurnAction(ctrl)

    async def execute(self, **params: Any) -> SkillResult:
        for i in range(4):
            if self._cancelled:
                return SkillResult(success=False, message="Cancelled")
            await self._turn.execute(degrees=90.0)
            if self._survey is not None:
                sa = params.get("sa")
                gs = params.get("gs")
                state_time = 0.1
                await asyncio.to_thread(
                    self._survey.tick, sa, gs, state_time
                )
            await asyncio.sleep(0.05)
        return SkillResult(success=True, message="Room survey completed")


class CombatEngageBehavior(ComposedBehavior):
    """Delegates combat to CombatEngager.tick."""

    def __init__(self, engager: Any, ctrl: Any, bridge: Any) -> None:
        super().__init__(name="combat_engage", description="Engage in combat")
        self._engager = engager
        self._ctrl = ctrl
        self._bridge = bridge

    async def execute(self, **params: Any) -> SkillResult:
        if self._cancelled:
            return SkillResult(success=False, message="Cancelled")
        sa = params.get("sa")
        gs = params.get("gs")
        await self._engager.tick(sa, gs)
        return SkillResult(success=True, message="Combat engagement executed")
