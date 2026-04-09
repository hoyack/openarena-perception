"""OpenArena Perception -- API subsystem.

Exposes the bot framework to LLM agents via a typed REST API.
"""
from __future__ import annotations

from .app import create_app
from .deps import BotState, get_bot

__all__ = ["create_app", "BotState", "get_bot"]
