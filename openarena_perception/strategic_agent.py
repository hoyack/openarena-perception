"""DEPRECATED: strategic_agent.py has broken Strategy enum references.
Use openarena_perception.strategy.LLMStrategyBrain instead.

strategic_agent.py — LLM-powered strategic decision layer via Ollama.

Runs every few seconds (not every tick). Analyzes game state trends
and sends frame snapshots to gemma4 for vision analysis.

Decisions:
  - Strategy mode (HUNT / DEFEND / RETREAT / EXPLORE)
  - Weapon preference
  - Tactical observations (e.g., "enemies clustering left side")

The strategic layer communicates with the reactive layer via
ReactiveAgent.set_strategy().
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional, Deque

import cv2
import numpy as np

from .game_state import GameState
from .reactive_agent import ReactiveAgent

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a real-time strategic advisor for an AI agent playing OpenArena \
(a Quake 3 Arena clone). You receive periodic game state summaries and \
occasionally a screenshot from the game.

Your job is to decide the HIGH-LEVEL STRATEGY. The reactive layer handles \
aiming, shooting, and moment-to-moment dodging automatically.

You must respond with a JSON object (no markdown fences) containing:
{
  "strategy": "HUNT" | "DEFEND" | "RETREAT" | "EXPLORE",
  "weapon": "railgun" | "rocket" | "lightning" | "shotgun" | "plasma" | "machinegun" | null,
  "reasoning": "brief explanation (1-2 sentences)"
}

Strategy meanings:
- HUNT: Aggressively pursue and engage enemies. Use when healthy and armed.
- DEFEND: Hold a strong position, engage targets of opportunity. Use at power \
  item locations or choke points.
- RETREAT: Seek health and armor pickups, avoid direct fights. Use when \
  health < 40 or ammo is very low.
- EXPLORE: Roam the map to find weapons, items, and enemies. Use when no \
  enemies are visible and well-equipped.

Decision factors:
- Health/armor levels (retreat if critically low)
- Ammo count and weapon quality
- Number and distance of visible enemies
- Kill/death ratio trends
- Whether we're taking damage without seeing enemies

Keep reasoning brief. Respond ONLY with the JSON object.\
"""


@dataclass
class StateSnapshot:
    """A summary of game state at a point in time."""
    timestamp: float
    health: Optional[int]
    armor: Optional[int]
    ammo: Optional[int]
    weapon: Optional[str]
    frags: Optional[int]
    deaths: Optional[int]
    enemy_count: int
    nearest_distance: Optional[str]
    crosshair_on_enemy: bool
    is_alive: bool
    low_health: bool
    low_ammo: bool


class StrategicAgent:
    """
    Periodically queries Ollama (gemma4) for strategic decisions based on
    accumulated game state history and optional vision frames.
    """

    def __init__(
        self,
        reactive: ReactiveAgent,
        model: str = "gemma4:31b-cloud",
        decision_interval: float = 4.0,
        vision_interval: float = 15.0,
        history_size: int = 30,
        ollama_host: str = "http://localhost:11434",
    ):
        self.reactive = reactive
        self.model = model
        self.decision_interval = decision_interval
        self.vision_interval = vision_interval
        self.ollama_host = ollama_host

        self._history: Deque[StateSnapshot] = deque(maxlen=history_size)
        self._last_decision_time = 0.0
        self._last_vision_time = 0.0
        self._last_frame: Optional[np.ndarray] = None
        self._running = False
        self._decision_count = 0

        import ollama as _ollama
        self._ollama = _ollama

    def record_state(self, gs: GameState):
        """Called every tick to record state history. Cheap — no LLM call."""
        snap = StateSnapshot(
            timestamp=gs.timestamp,
            health=gs.health,
            armor=gs.armor,
            ammo=gs.ammo,
            weapon=gs.weapon,
            frags=gs.frags,
            deaths=gs.deaths,
            enemy_count=len(gs.enemies),
            nearest_distance=gs.nearest_enemy.distance_estimate if gs.nearest_enemy else None,
            crosshair_on_enemy=gs.crosshair_on_enemy,
            is_alive=gs.is_alive,
            low_health=gs.low_health,
            low_ammo=gs.low_ammo,
        )
        self._history.append(snap)

        if gs.frame is not None:
            self._last_frame = gs.frame

    def should_decide(self) -> bool:
        """Check if it's time for a strategic decision."""
        return time.time() - self._last_decision_time >= self.decision_interval

    async def make_decision(self):
        """Query Ollama for a strategic decision."""
        if not self._history:
            return

        now = time.time()
        self._last_decision_time = now

        user_msg = self._build_state_message()

        # Include a frame for vision periodically
        include_vision = (now - self._last_vision_time >= self.vision_interval
                          and self._last_frame is not None)

        images = []
        if include_vision:
            img_bytes = self._encode_frame(self._last_frame)
            images.append(img_bytes)
            self._last_vision_time = now

        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, self._call_ollama, user_msg, images,
            )
            self._apply_decision(response)
            self._decision_count += 1
        except Exception as e:
            log.warning("Strategic decision failed: %s", e)

    def _call_ollama(self, user_msg: str, images: list) -> dict:
        """Synchronous Ollama call (run in executor)."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        user_payload = {"role": "user", "content": user_msg}
        if images:
            user_payload["images"] = images
        messages.append(user_payload)

        response = self._ollama.chat(
            model=self.model,
            messages=messages,
        )

        text = response["message"]["content"].strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0].strip()
        return json.loads(text)

    def _apply_decision(self, decision: dict):
        """Apply the LLM's strategic decision to the reactive layer."""
        strategy_name = decision.get("strategy", "HUNT").upper()
        weapon = decision.get("weapon")
        reasoning = decision.get("reasoning", "")

        strategy_map = {
            "HUNT": Strategy.HUNT,
            "DEFEND": Strategy.DEFEND,
            "RETREAT": Strategy.RETREAT,
            "EXPLORE": Strategy.EXPLORE,
        }
        strategy = strategy_map.get(strategy_name, Strategy.HUNT)
        self.reactive.set_strategy(strategy, preferred_weapon=weapon)

        log.info("LLM Decision #%d: %s (weapon=%s) — %s",
                 self._decision_count + 1, strategy.name, weapon, reasoning)

        if weapon:
            self.reactive.bridge.select_weapon_by_name(weapon)

    def _build_state_message(self) -> str:
        """Build a concise text summary of recent game state for the LLM."""
        recent = list(self._history)[-10:]
        current = recent[-1]

        healths = [s.health for s in recent if s.health is not None]
        enemy_counts = [s.enemy_count for s in recent]
        damage_events = sum(1 for i in range(1, len(healths))
                           if healths[i] < healths[i-1])

        frags_start = next((s.frags for s in recent if s.frags is not None), 0)
        frags_end = current.frags or 0
        deaths_start = next((s.deaths for s in recent if s.deaths is not None), 0)
        deaths_end = current.deaths or 0

        lines = [
            f"=== Game State (decision #{self._decision_count + 1}) ===",
            f"Health: {current.health}  Armor: {current.armor}",
            f"Ammo: {current.ammo}  Weapon: {current.weapon}",
            f"Frags: {current.frags}  Deaths: {current.deaths}",
            f"Recent K/D delta: +{frags_end - (frags_start or 0)} kills, "
            f"+{deaths_end - (deaths_start or 0)} deaths",
            f"Enemies visible: {current.enemy_count}",
            f"Nearest enemy: {current.nearest_distance or 'none'}",
            f"Crosshair on enemy: {current.crosshair_on_enemy}",
            f"Taking damage: {damage_events} hits in last {len(recent)} ticks",
            f"Low health: {current.low_health}  Low ammo: {current.low_ammo}",
            f"Alive: {current.is_alive}",
            f"Avg enemies visible (recent): {sum(enemy_counts)/len(enemy_counts):.1f}",
        ]

        if current.is_alive and self._last_frame is not None:
            lines.append("A screenshot is attached — use it to assess the tactical situation.")

        return "\n".join(lines)

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

    @property
    def decision_count(self) -> int:
        return self._decision_count
