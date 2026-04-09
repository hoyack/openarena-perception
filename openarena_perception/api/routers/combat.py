"""Combat REST endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from openarena_perception.api.deps import BotState, get_bot

router = APIRouter()

BotDep = Annotated[BotState, Depends(get_bot)]


@router.post("/engage")
async def combat_engage(bot: BotDep) -> dict:
    """Enter combat mode."""
    return {"status": "engaging"}


@router.post("/disengage")
async def combat_disengage(bot: BotDep) -> dict:
    """Exit combat mode."""
    return {"status": "disengaged"}


@router.post("/weapon")
async def combat_weapon(
    body: dict, bot: BotDep
) -> dict:
    """Select a weapon by name."""
    weapon = body.get("weapon", "")
    if bot.bridge is not None and hasattr(bot.bridge, "select_weapon_by_name"):
        ok = bot.bridge.select_weapon_by_name(weapon)
        return {"status": "selected" if ok else "failed", "weapon": weapon}
    return {"status": "selected", "weapon": weapon}
