"""Strategy data contracts (STRT-03).

StrategyAction constrains LLM outputs to exactly 4 actions.
StrategyDecision validates the full response with Pydantic.
"""

from enum import Enum

from pydantic import BaseModel, field_validator


class StrategyAction(str, Enum):
    """Constrained action vocabulary for strategic decisions (STRT-03)."""

    HUNT = "HUNT"
    DEFEND = "DEFEND"
    RETREAT = "RETREAT"
    EXPLORE = "EXPLORE"


class StrategyDecision(BaseModel):
    """Validated LLM strategy response.

    Pydantic validates the JSON, with StrategyAction enum ensuring
    only valid actions are accepted. Fallback on ValidationError.
    """

    action: StrategyAction
    weapon: str | None = None
    target_item: str | None = None
    reasoning: str = ""

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, v: str) -> str:
        """Normalize action strings: strip whitespace, uppercase, map aliases."""
        if isinstance(v, str):
            v = v.strip().upper()
            # Map aliases from old llm_brain.py vocabulary
            alias_map = {"CAMP": "DEFEND", "AMBUSH": "DEFEND", "GRAB_ITEM": "EXPLORE"}
            v = alias_map.get(v, v)
        return v
