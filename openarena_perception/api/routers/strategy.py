"""Strategy REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from openarena_perception.api.deps import BotState, get_bot
from openarena_perception.api.models import StrategyOverrideRequest, StrategyStateResponse

router = APIRouter()


@router.get("/current", response_model=StrategyStateResponse)
async def strategy_current(bot: BotState = Depends(get_bot)) -> StrategyStateResponse:
    """Return current strategy / FSM state."""
    brain_state = "unknown"
    current_action = "idle"
    if bot.fsm is not None:
        state = getattr(bot.fsm, "state", getattr(bot.fsm, "_state", "unknown"))
        if hasattr(state, "value"):
            brain_state = state.value
        else:
            brain_state = str(state)
        current_action = brain_state
    if bot.override_action:
        current_action = bot.override_action
    return StrategyStateResponse(
        current_action=current_action,
        brain_state=brain_state,
    )


@router.post("/override")
async def strategy_override(
    req: StrategyOverrideRequest, bot: BotState = Depends(get_bot)
) -> dict:
    """Override the current strategy action."""
    bot.override_action = req.action
    return {"status": "override_set", "action": req.action}
