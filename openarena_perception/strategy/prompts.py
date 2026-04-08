"""Prompt templates for LLM strategic reasoning (STRT-02).

Separated from llm_brain.py for testability and swappability.
"""

STRATEGY_PROMPT = """\
You are the strategic brain of an FPS bot playing OpenArena (Quake 3 clone).

Current state:
{state_text}

{vision_note}

Based on this information, decide the bot's next action. Respond with ONLY a JSON object:
{{
  "action": "HUNT" | "DEFEND" | "RETREAT" | "EXPLORE",
  "weapon": null | "rocket" | "lightning" | "railgun" | "shotgun" | "plasma",
  "target_item": null | "health" | "armor" | "mega" | "weapon",
  "reasoning": "1 sentence explanation"
}}

Action meanings:
- HUNT: Aggressively seek and engage enemies
- DEFEND: Hold a strong position, engage targets of opportunity
- RETREAT: Disengage, seek health/armor, avoid fights
- EXPLORE: Roam the map to find weapons, items, and enemies

Consider:
- Health/armor levels (retreat if critical)
- Current weapon vs what's available
- Enemy position and behavior
- Map position advantages\
"""
