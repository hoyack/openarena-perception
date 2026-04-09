"""Perception REST endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from openarena_perception.api.deps import BotState, get_bot
from openarena_perception.api.models import (
    EnemyInfo,
    HudResponse,
    PerceptionStateResponse,
)

router = APIRouter()

BotDep = Annotated[BotState, Depends(get_bot)]


@router.get("/state", response_model=PerceptionStateResponse)
async def perception_state(bot: BotDep) -> PerceptionStateResponse:
    """Return the latest SituationalAwareness snapshot."""
    if bot.last_sa is None:
        raise HTTPException(status_code=503, detail="No perception data")
    return PerceptionStateResponse.from_sa(bot.last_sa)


@router.get("/enemies", response_model=EnemyInfo)
async def perception_enemies(bot: BotDep) -> EnemyInfo:
    """Return enemy threat summary from last SA."""
    if bot.last_sa is None:
        raise HTTPException(status_code=503, detail="No perception data")
    sa = bot.last_sa
    return EnemyInfo(
        enemies_visible=sa.enemies_visible,
        nearest_enemy_distance=sa.nearest_enemy_distance,
        under_attack=sa.under_attack,
    )


@router.get("/hud", response_model=HudResponse)
async def perception_hud(bot: BotDep) -> HudResponse:
    """Return HUD vitals from last SA."""
    if bot.last_sa is None:
        raise HTTPException(status_code=503, detail="No perception data")
    sa = bot.last_sa
    return HudResponse(
        health=sa.health,
        armor=sa.armor,
        ammo=sa.ammo,
        weapon=sa.weapon,
    )
