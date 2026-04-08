"""DEPRECATED: Use openarena_perception.strategy.llm_brain.LLMStrategyBrain instead.

llm_brain.py — LLM-powered strategic brain (replaces Q3's AI Network FSM).

The van Waveren thesis describes the AI Network as a hardcoded FSM with
nodes for different situations (battle_fight, battle_chase, battle_retreat,
seek_ltg, seek_nbg). We replace this with an LLM that can:

1. See the game screen (vision) and understand spatial context
2. Reason about tactical situations the FSM can't handle
3. Adapt strategy based on game state trends
4. Make nuanced weapon/positioning decisions

Runs every ~4 seconds via Ollama (gemma4:31b-cloud).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

BRAIN_PROMPT = """\
You are the strategic brain of an FPS bot playing OpenArena (Quake 3 clone).

Current state:
{state_text}

{vision_note}

Based on this information, decide the bot's next action. Respond with ONLY a JSON object:
{{
  "action": "HUNT" | "RETREAT" | "CAMP" | "AMBUSH" | "GRAB_ITEM",
  "target_item": null | "rocketlauncher" | "mega" | "lightning" | "armor" | etc,
  "weapon": null | "rocket" | "lightning" | "railgun" | "shotgun" | etc,
  "movement": "aggressive" | "defensive" | "evasive" | "careful",
  "reasoning": "1 sentence explanation"
}}

Action meanings:
- HUNT: Seek and engage enemies aggressively
- RETREAT: Disengage, seek health/armor, avoid fights
- CAMP: Hold a strong position (near power items or choke point)
- AMBUSH: Set up near an item the enemy will come for
- GRAB_ITEM: Navigate to a specific item

Consider:
- Health/armor levels (retreat if critical)
- Current weapon vs what's available
- Enemy position and behavior patterns
- Item respawn timing
- Map position advantages\
"""


@dataclass
class GameSnapshot:
    timestamp: float
    health: Optional[int]
    armor: Optional[int]
    ammo: Optional[int]
    weapon: Optional[str]
    pos_x: float
    pos_y: float
    pos_z: float
    enemy_count: int
    is_alive: bool
    frags: int = 0
    deaths: int = 0


class LLMBrain:
    """
    Strategic brain using Ollama vision LLM.
    Replaces the hardcoded AI Network FSM from the Q3 bot.
    """

    def __init__(
        self,
        model: str = "gemma4:31b-cloud",
        decision_interval: float = 5.0,
        vision_interval: float = 10.0,
    ):
        self.model = model
        self.decision_interval = decision_interval
        self.vision_interval = vision_interval

        self._history: Deque[GameSnapshot] = deque(maxlen=30)
        self._last_decision_time = 0.0
        self._last_vision_time = 0.0
        self._last_frame: Optional[np.ndarray] = None
        self._last_decision: Optional[dict] = None
        self._decision_count = 0

        try:
            import ollama
            self._ollama = ollama
        except ImportError:
            self._ollama = None
            log.warning("ollama not available — LLM brain disabled")

    def record_state(self, snap: GameSnapshot):
        """Called every tick to record history."""
        self._history.append(snap)

    def record_frame(self, frame: np.ndarray):
        """Store latest frame for vision queries."""
        self._last_frame = frame

    def should_decide(self) -> bool:
        return time.time() - self._last_decision_time >= self.decision_interval

    @property
    def last_decision(self) -> Optional[dict]:
        return self._last_decision

    def decide(self) -> Optional[dict]:
        """
        Synchronous LLM decision. Call from executor if in async context.
        Returns decision dict or None on failure.
        """
        if not self._ollama or not self._history:
            return None

        now = time.time()
        self._last_decision_time = now

        state_text = self._build_state_text()

        # Vision: include frame periodically
        images = []
        vision_note = ""
        if (now - self._last_vision_time >= self.vision_interval
                and self._last_frame is not None):
            img_bytes = self._encode_frame(self._last_frame)
            images.append(img_bytes)
            self._last_vision_time = now
            vision_note = "A screenshot of what the bot currently sees is attached."
        else:
            vision_note = "No screenshot available this cycle."

        prompt = BRAIN_PROMPT.format(state_text=state_text, vision_note=vision_note)

        try:
            msg = {"role": "user", "content": prompt}
            if images:
                msg["images"] = images

            response = self._ollama.chat(
                model=self.model,
                messages=[msg],
            )
            text = response["message"]["content"].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            decision = json.loads(text)
            self._last_decision = decision
            self._decision_count += 1

            log.info("LLM Brain #%d: %s → %s (%s)",
                     self._decision_count,
                     decision.get("action"),
                     decision.get("target_item"),
                     decision.get("reasoning", ""))

            return decision
        except Exception as e:
            log.warning("LLM Brain failed: %s", e)
            return None

    def _build_state_text(self) -> str:
        if not self._history:
            return "No data"

        current = self._history[-1]
        recent = list(self._history)[-10:]

        # Damage trend
        healths = [s.health for s in recent if s.health is not None]
        taking_damage = False
        if len(healths) >= 2:
            taking_damage = healths[-1] < healths[0]

        enemies_seen = sum(1 for s in recent if s.enemy_count > 0)
        avg_enemies = sum(s.enemy_count for s in recent) / len(recent)

        lines = [
            f"Health: {current.health or '?'}  Armor: {current.armor or '?'}",
            f"Weapon: {current.weapon or 'machinegun'}  Ammo: {current.ammo or '?'}",
            f"Position: ({current.pos_x:.0f}, {current.pos_y:.0f}, {current.pos_z:.0f})",
            f"Enemies visible now: {current.enemy_count}",
            f"Enemies seen in last 10 ticks: {enemies_seen}/10 (avg {avg_enemies:.1f})",
            f"Taking damage: {taking_damage}",
            f"Alive: {current.is_alive}",
            f"Score: {current.frags} kills / {current.deaths} deaths",
        ]
        return "\n".join(lines)

    def _encode_frame(self, frame: np.ndarray) -> bytes:
        h, w = frame.shape[:2]
        scale = min(1.0, 512 / max(h, w))
        if scale < 1.0:
            small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        else:
            small = frame
        _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
        return buf.tobytes()

    @property
    def decision_count(self) -> int:
        return self._decision_count
