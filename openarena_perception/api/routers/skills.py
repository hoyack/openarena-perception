"""Skills REST endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from openarena_perception.api.deps import BotState, get_bot
from openarena_perception.api.models import (
    SkillCatalogEntry,
    SkillExecuteRequest,
    SkillExecuteResponse,
)

router = APIRouter()


@router.post("/execute", response_model=SkillExecuteResponse)
async def skills_execute(
    req: SkillExecuteRequest, bot: BotState = Depends(get_bot)
) -> SkillExecuteResponse:
    """Execute a skill by name with given parameters."""
    if bot.registry is None:
        raise HTTPException(status_code=503, detail="Skill registry not available")
    result = await bot.registry.execute(req.name, **req.params)
    return SkillExecuteResponse(
        success=result.success,
        message=result.message,
        data=result.data,
    )


@router.get("/catalog", response_model=list[SkillCatalogEntry])
async def skills_catalog(bot: BotState = Depends(get_bot)) -> list[SkillCatalogEntry]:
    """Return the full skill catalog for LLM agent discovery."""
    if bot.registry is None:
        raise HTTPException(status_code=503, detail="Skill registry not available")
    entries = bot.registry.catalog()
    return [SkillCatalogEntry(**e) for e in entries]


@router.get("/{name}", response_model=SkillCatalogEntry)
async def skills_detail(
    name: str, bot: BotState = Depends(get_bot)
) -> SkillCatalogEntry:
    """Return detail for a single skill by name."""
    if bot.registry is None:
        raise HTTPException(status_code=503, detail="Skill registry not available")
    skill = bot.registry.get(name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {name}")
    return SkillCatalogEntry(
        name=skill.name,
        layer=skill.layer.value,
        description=skill.description,
    )
