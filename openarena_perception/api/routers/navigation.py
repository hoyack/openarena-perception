"""Navigation REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from openarena_perception.api.deps import BotState, get_bot
from openarena_perception.api.models import (
    NavigationRequest,
    NavigationStateResponse,
)

router = APIRouter()


@router.post("/goto")
async def navigation_goto(
    req: NavigationRequest, bot: BotState = Depends(get_bot)
) -> dict:
    """Request navigation to an area or named target."""
    target = req.area_id if req.area_id is not None else req.target
    if target is None:
        raise HTTPException(status_code=400, detail="Provide area_id or target")
    return {"status": "navigating", "target": target}


@router.get("/path", response_model=NavigationStateResponse)
async def navigation_path(bot: BotState = Depends(get_bot)) -> NavigationStateResponse:
    """Return current navigation state from last SA."""
    if bot.last_sa is None:
        raise HTTPException(status_code=503, detail="No perception data")
    sa = bot.last_sa
    return NavigationStateResponse(
        has_path=sa.has_path,
        path_length=sa.path_length,
        is_stuck=sa.is_stuck,
        nav_target=sa.nav_target,
    )


@router.post("/explore")
async def navigation_explore(bot: BotState = Depends(get_bot)) -> dict:
    """Start random exploration."""
    return {"status": "exploring"}
