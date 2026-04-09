"""Atomic actions -- thin wrappers around GameBridge/VirtualController.

Each action is a single game command with input validation per T-06-01/T-06-02:
  - MoveAction: direction validated, duration clamped to 0.0-5.0s
  - TurnAction: degrees clamped to -360..360
  - FireAction: toggle fire on/off
  - WeaponSelectAction: select weapon by name
"""
from __future__ import annotations

import asyncio
from typing import Any

from .base import AtomicAction, SkillResult


class MoveAction(AtomicAction):
    """Move forward or backward for a duration.

    Wraps VirtualController.forward() / .back() with async sleep.
    """

    _VALID_DIRECTIONS = {"forward", "backward"}
    _MAX_DURATION = 5.0

    def __init__(self, ctrl: Any) -> None:
        super().__init__(name="move", description="Move forward or backward")
        self._ctrl = ctrl

    async def execute(self, **params: Any) -> SkillResult:
        direction: str = params.get("direction", "forward")
        duration: float = params.get("duration", 0.5)

        # T-06-01: Validate direction
        if direction not in self._VALID_DIRECTIONS:
            return SkillResult(
                success=False,
                message=f"Invalid direction: {direction}. Must be forward/backward",
            )

        # T-06-02: Clamp duration to prevent infinite sleep
        duration = max(0.0, min(self._MAX_DURATION, duration))

        fn = self._ctrl.forward if direction == "forward" else self._ctrl.back
        fn(True)
        await asyncio.sleep(duration)
        fn(False)
        return SkillResult(success=True, message=f"Moved {direction} for {duration}s")


class TurnAction(AtomicAction):
    """Turn by degrees. Offloads blocking turn_degrees to thread pool.

    CRITICAL: VirtualController.turn_degrees() uses time.sleep() internally.
    Must use asyncio.to_thread() to avoid blocking the event loop.
    """

    _MAX_DEGREES = 360.0

    def __init__(self, ctrl: Any) -> None:
        super().__init__(name="turn", description="Turn by specified degrees")
        self._ctrl = ctrl

    async def execute(self, **params: Any) -> SkillResult:
        degrees: float = params.get("degrees", 0.0)

        # T-06-01: Clamp degrees to -360..360
        degrees = max(-self._MAX_DEGREES, min(self._MAX_DEGREES, degrees))

        await asyncio.to_thread(self._ctrl.turn_degrees, degrees)
        return SkillResult(success=True, message=f"Turned {degrees} degrees")


class FireAction(AtomicAction):
    """Start or stop firing. Wraps GameBridge.fire()."""

    def __init__(self, bridge: Any) -> None:
        super().__init__(name="fire", description="Start or stop firing")
        self._bridge = bridge

    async def execute(self, **params: Any) -> SkillResult:
        on: bool = params.get("on", True)
        self._bridge.fire(on)
        return SkillResult(
            success=True, message=f"Fire {'started' if on else 'stopped'}"
        )


class WeaponSelectAction(AtomicAction):
    """Select weapon by name. Wraps GameBridge.select_weapon_by_name()."""

    def __init__(self, bridge: Any) -> None:
        super().__init__(name="weapon_select", description="Select a weapon by name")
        self._bridge = bridge

    async def execute(self, **params: Any) -> SkillResult:
        weapon: str = params.get("weapon", "rocket")
        ok = self._bridge.select_weapon_by_name(weapon)
        if ok:
            return SkillResult(success=True, message=f"Selected {weapon}")
        return SkillResult(success=False, message=f"Unknown weapon: {weapon}")
