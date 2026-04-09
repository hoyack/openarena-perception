"""WebSocket /ws/state handler with connection management.

Streams SituationalAwareness JSON at configurable Hz (default 3 Hz).
Enforces a max_connections limit (default 5) and cleans up on disconnect.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from openarena_perception.settings import get_settings

from .deps import get_bot

_active_connections: set[WebSocket] = set()

ws_router = APIRouter()


@ws_router.websocket("/ws/state")
async def state_stream(ws: WebSocket) -> None:
    """Stream bot state as JSON at ~api_ws_hz frequency."""
    settings = get_settings()

    # Enforce connection limit (T-06-09 DoS mitigation)
    if len(_active_connections) >= settings.api_ws_max_connections:
        await ws.close(code=1013)  # Try Again Later
        return

    await ws.accept()
    _active_connections.add(ws)

    interval = 1.0 / settings.api_ws_hz

    try:
        while True:
            bot = get_bot()
            sa = bot.last_sa

            if sa is not None:
                # Manual dict construction -- fast path (~0.05ms vs 0.5ms for asdict)
                await ws.send_json(
                    {
                        "tick": sa.tick,
                        "timestamp": sa.timestamp,
                        "health": sa.health,
                        "armor": sa.armor,
                        "ammo": sa.ammo,
                        "weapon": sa.weapon,
                        "is_alive": sa.is_alive,
                        "disposition": sa.disposition,
                        "enemies_visible": sa.enemies_visible,
                        "current_area": sa.current_area,
                        "has_path": sa.has_path,
                        "is_stuck": sa.is_stuck,
                        "under_attack": sa.under_attack,
                        "pos": list(sa.pos) if sa.pos else None,
                        "yaw": sa.yaw,
                        "nav_target": sa.nav_target,
                    }
                )
            else:
                # Heartbeat when no SA available
                await ws.send_json({"type": "waiting"})

            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        pass
    finally:
        _active_connections.discard(ws)
