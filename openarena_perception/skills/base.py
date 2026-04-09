"""Skill system foundation -- Protocol, models, registry.

Three-layer skill hierarchy:
  - AtomicAction (ACTION): wraps a single GameBridge/VirtualController call
  - ComposedBehavior (BEHAVIOR): sequences actions with timing
  - Mission (MISSION): composes behaviors with goal conditions

All skills follow the Skill Protocol (structural typing via PEP 544).
"""
from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable

from pydantic import BaseModel


class SkillLayer(str, Enum):
    """Hierarchy layer for skill classification."""

    ACTION = "action"
    BEHAVIOR = "behavior"
    MISSION = "mission"


class SkillResult(BaseModel):
    """Standard result from any skill execution."""

    success: bool
    message: str = ""
    data: dict[str, Any] = {}


@runtime_checkable
class Skill(Protocol):
    """Structural type for all skills -- actions, behaviors, missions."""

    name: str
    layer: SkillLayer
    description: str

    async def execute(self, **params: Any) -> SkillResult: ...

    def cancel(self) -> None: ...


class AtomicAction:
    """Base for atomic actions. Wraps a single GameBridge/VirtualController call."""

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.layer = SkillLayer.ACTION
        self.description = description
        self._cancelled = False

    async def execute(self, **params: Any) -> SkillResult:
        raise NotImplementedError

    def cancel(self) -> None:
        self._cancelled = True


class ComposedBehavior:
    """Base for behaviors. Sequences atomic actions with timing."""

    def __init__(
        self, name: str, description: str, steps: list[Skill] | None = None
    ) -> None:
        self.name = name
        self.layer = SkillLayer.BEHAVIOR
        self.description = description
        self.steps: list[Skill] = steps or []
        self._cancelled = False

    async def execute(self, **params: Any) -> SkillResult:
        for step in self.steps:
            if self._cancelled:
                return SkillResult(success=False, message="Cancelled")
            result = await step.execute(**params)
            if not result.success:
                return result
        return SkillResult(success=True, message=f"{self.name} completed")

    def cancel(self) -> None:
        self._cancelled = True
        for step in self.steps:
            step.cancel()


class Mission:
    """Base for missions. Composes behaviors with a goal condition."""

    def __init__(
        self,
        name: str,
        description: str,
        behaviors: list[Skill] | None = None,
        goal_condition: Callable[[], bool] | None = None,
    ) -> None:
        self.name = name
        self.layer = SkillLayer.MISSION
        self.description = description
        self.behaviors: list[Skill] = behaviors or []
        self.goal_condition = goal_condition or (lambda: False)
        self._cancelled = False

    async def execute(self, **params: Any) -> SkillResult:
        for behavior in self.behaviors:
            if self._cancelled:
                return SkillResult(success=False, message="Cancelled")
            if self.goal_condition():
                return SkillResult(success=True, message=f"{self.name} goal reached")
            result = await behavior.execute(**params)
            if not result.success:
                return result
        reached = self.goal_condition()
        return SkillResult(
            success=reached,
            message=f"{self.name} {'goal reached' if reached else 'completed without goal'}",
        )

    def cancel(self) -> None:
        self._cancelled = True
        for behavior in self.behaviors:
            behavior.cancel()


class SkillRegistry:
    """Flat dictionary registry. Skills register by name."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill by its name."""
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        """Look up a skill by name."""
        return self._skills.get(name)

    def catalog(self) -> list[dict[str, str]]:
        """Return skill catalog for LLM agent discovery."""
        return [
            {"name": s.name, "layer": s.layer.value, "description": s.description}
            for s in self._skills.values()
        ]

    async def execute(self, name: str, **params: Any) -> SkillResult:
        """Execute a skill by name with given params."""
        skill = self._skills.get(name)
        if not skill:
            return SkillResult(success=False, message=f"Unknown skill: {name}")
        return await skill.execute(**params)
