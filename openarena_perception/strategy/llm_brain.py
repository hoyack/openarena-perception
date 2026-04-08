"""LLM-powered strategic reasoning via Ollama (STRT-01).

Queries the LLM every ~4-5 seconds with structured game state
(STRT-02) and validates responses against constrained action
vocabulary (STRT-03).

Extracted from root llm_brain.py in Phase 5. Key enhancements:
- AsyncClient instead of sync ollama.chat
- SituationalAwareness input instead of custom GameSnapshot
- Pydantic StrategyDecision validation with fallback
- Separated prompt templates in prompts.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

import cv2
import numpy as np

from openarena_perception.models import SituationalAwareness
from openarena_perception.strategy.models import StrategyAction, StrategyDecision
from openarena_perception.strategy.prompts import STRATEGY_PROMPT

log = logging.getLogger(__name__)

# Timeout for LLM calls (T-05-04 mitigation)
_LLM_TIMEOUT_SECONDS = 10.0


class LLMStrategyBrain:
    """LLM-powered strategic reasoning via Ollama (STRT-01).

    Queries the LLM every ~4-5 seconds with structured game state
    (STRT-02) and validates responses against constrained action
    vocabulary (STRT-03).
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

        self._last_decision_time = 0.0
        self._last_vision_time = 0.0
        self._last_frame: Optional[np.ndarray] = None
        self._last_decision: Optional[StrategyDecision] = None
        self._decision_count = 0

        # Lazy-init async client
        self._client = None
        try:
            import ollama

            self._ollama_mod = ollama
        except ImportError:
            self._ollama_mod = None
            log.warning("ollama not available -- LLM strategy brain disabled")

    def _get_client(self):
        """Lazily create AsyncClient on first use."""
        if self._client is None and self._ollama_mod is not None:
            self._client = self._ollama_mod.AsyncClient()
        return self._client

    def should_decide(self) -> bool:
        """Check if enough time has elapsed for a new decision."""
        return time.time() - self._last_decision_time >= self.decision_interval

    def record_frame(self, frame: np.ndarray) -> None:
        """Store latest frame for vision queries."""
        self._last_frame = frame

    @property
    def last_decision(self) -> Optional[StrategyDecision]:
        return self._last_decision

    @property
    def decision_count(self) -> int:
        return self._decision_count

    async def decide(self, sa: SituationalAwareness) -> StrategyDecision:
        """Query Ollama for a strategic decision (STRT-01).

        Builds structured state text from SituationalAwareness (STRT-02),
        validates the response with Pydantic StrategyDecision (STRT-03).
        Falls back to rule-based decision on any failure.

        Args:
            sa: Current situational awareness snapshot.

        Returns:
            Validated StrategyDecision (always returns, never raises).
        """
        client = self._get_client()
        if client is None:
            return self._fallback_decision(sa)

        now = time.time()
        self._last_decision_time = now

        state_text = self._build_state_text(sa)

        # Vision: include frame periodically
        images = []
        vision_note = "No screenshot available this cycle."
        if (
            now - self._last_vision_time >= self.vision_interval
            and self._last_frame is not None
        ):
            img_bytes = self._encode_frame(self._last_frame)
            images.append(img_bytes)
            self._last_vision_time = now
            vision_note = "A screenshot of what the bot currently sees is attached."

        prompt = STRATEGY_PROMPT.format_map(
            {"state_text": state_text, "vision_note": vision_note}
        )

        try:
            msg: dict = {"role": "user", "content": prompt}
            if images:
                msg["images"] = images

            response = await asyncio.wait_for(
                client.chat(model=self.model, messages=[msg]),
                timeout=_LLM_TIMEOUT_SECONDS,
            )
            text = response["message"]["content"].strip()

            # Strip markdown fences if present (T-05-03 mitigation)
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            decision = StrategyDecision.model_validate_json(text)
            self._last_decision = decision
            self._decision_count += 1

            log.info(
                "LLM Strategy #%d: %s (weapon=%s) -- %s",
                self._decision_count,
                decision.action.value,
                decision.weapon,
                decision.reasoning,
            )
            return decision

        except (json.JSONDecodeError, Exception) as e:
            log.warning("LLM strategy failed, using fallback: %s", e)
            fallback = self._fallback_decision(sa)
            self._last_decision = fallback
            return fallback

    def _build_state_text(self, sa: SituationalAwareness) -> str:
        """Build human-readable state summary from SituationalAwareness (STRT-02)."""
        pos_str = "unknown"
        if sa.pos is not None:
            pos_str = f"({sa.pos[0]:.0f}, {sa.pos[1]:.0f}, {sa.pos[2]:.0f})"

        lines = [
            f"Health: {sa.health or '?'}  Armor: {sa.armor or '?'}",
            f"Weapon: {sa.weapon or 'machinegun'}  Ammo: {sa.ammo or '?'}",
            f"Position: {pos_str}",
            f"Disposition: {sa.disposition}",
            f"Enemies visible: {sa.enemies_visible}",
            f"Nearest enemy: {sa.nearest_enemy_distance or 'none'}",
            f"Under attack: {sa.under_attack}",
            f"Alive: {sa.is_alive}",
            f"Navigation: {'has path' if sa.has_path else 'no path'}"
            + (f" -> {sa.nav_target}" if sa.nav_target else ""),
        ]
        return "\n".join(lines)

    def _fallback_decision(self, sa: SituationalAwareness) -> StrategyDecision:
        """Rule-based fallback when LLM fails or is unavailable.

        Priority:
        1. Critical health -> RETREAT
        2. Enemies visible -> HUNT
        3. Otherwise -> EXPLORE
        """
        if sa.health is not None and sa.health < 30:
            return StrategyDecision(
                action=StrategyAction.RETREAT,
                reasoning="Critical health, seeking safety",
            )
        if sa.enemies_visible > 0:
            return StrategyDecision(
                action=StrategyAction.HUNT,
                reasoning="Enemies visible, engaging",
            )
        return StrategyDecision(
            action=StrategyAction.EXPLORE,
            reasoning="No threats, exploring map",
        )

    def _encode_frame(self, frame: np.ndarray) -> bytes:
        """Encode a BGR frame as JPEG bytes for Ollama vision."""
        h, w = frame.shape[:2]
        scale = min(1.0, 512 / max(h, w))
        if scale < 1.0:
            small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        else:
            small = frame
        _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
        return buf.tobytes()
