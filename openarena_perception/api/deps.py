"""Dependency injection for the FastAPI layer.

BotState holds references to live subsystem instances.  Routes access
them via ``Depends(get_bot)``.  Tests swap the singleton via ``set_bot()``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    pass


class BotState:
    """Holds references to all bot subsystem instances."""

    def __init__(self) -> None:
        self.perception: Any | None = None  # PerceptionPipeline
        self.fsm: Any | None = None  # TacticalFSM
        self.bridge: Any | None = None  # GameBridge
        self.controller: Any | None = None  # VirtualController
        self.registry: Any | None = None  # SkillRegistry
        self.last_sa: Any | None = None  # SituationalAwareness
        self.override_action: str | None = None  # strategy override


_bot = BotState()


def get_bot() -> BotState:
    """FastAPI dependency -- returns the singleton BotState."""
    return _bot


def set_bot(bot: BotState) -> None:
    """Replace the singleton BotState (for test injection)."""
    global _bot
    _bot = bot
