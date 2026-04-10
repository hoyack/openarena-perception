"""Async spatial advisor loop — background LLM reasoning for real-time navigation.

The advisor runs in the same asyncio event loop as the tour. It:
  1. Records a rolling position trail (via record_trail every tick)
  2. Dispatches a thought to Ollama every 2.5s with the latest frame + trail
  3. Validates the response when it arrives (is the bot still in the same place?)
  4. Exposes warnings, narrative, and action hints to the navigator

Key design: the bot keeps moving while a thought is in-flight. When the response
arrives, we check if the bot has moved too far for the advice to still apply.
Stale thoughts are discarded.

Usage:
    advisor = SpatialAdvisor(model="gemma3:4b")
    advisor.set_goal(target_area=239, goal_pos=(232, 1600, -112), goal_name="item_health_mega")

    # In the tick loop:
    advisor.record_trail(pos, yaw, area)
    advisor.maybe_dispatch(frame)  # returns immediately, spawns task if needed
    warnings = advisor.current_warnings()
    if advisor.is_hazard_ahead():
        action = advisor.get_recommended_action()  # e.g. "back_away"
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple

import cv2
import numpy as np

from openarena_perception.strategy.advisor_prompts import (
    SPATIAL_ADVISOR_PROMPT,
    build_trail_summary,
    describe_goal,
)

log = logging.getLogger(__name__)

_DEFAULT_MODEL = os.environ.get("OA_ADVISOR_MODEL", "gemma3:4b")
_DEFAULT_INTERVAL = float(os.environ.get("OA_ADVISOR_INTERVAL", "2.5"))
_DEFAULT_TIMEOUT = float(os.environ.get("OA_ADVISOR_TIMEOUT", "6.0"))

# Staleness thresholds
_MAX_STALE_DISTANCE = 200.0  # units — if bot moved more than this, thought is stale
_MAX_WARNING_AGE = 5.0       # seconds — warnings older than this are ignored
_MAX_THOUGHT_AGE = 10.0      # seconds — thoughts older than this are always stale

# Hazard kinds that should halt forward movement
_HALT_HAZARD_KINDS = {"lava", "ledge", "drop"}


@dataclass(frozen=True)
class TrailPoint:
    t: float
    x: float
    y: float
    z: float
    yaw: float
    area: int


@dataclass
class Warning:
    kind: str           # lava|ledge|drop|wall|bars|dead_end
    direction: str      # ahead|left|right
    severity: str       # low|medium|high
    text: str
    recorded_at: float  # time the warning was recorded
    recorded_pos: Tuple[float, float, float]  # bot pos when recorded


@dataclass
class ThoughtSnapshot:
    """State captured when a thought was dispatched."""
    id: str
    sent_at: float
    sent_pos: Tuple[float, float, float]
    sent_yaw: float
    sent_area: int
    goal_desc: str


class SpatialAdvisor:
    """Background LLM spatial advisor."""

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        dispatch_interval: float = _DEFAULT_INTERVAL,
        timeout: float = _DEFAULT_TIMEOUT,
        trail_maxlen: int = 30,
    ):
        self.model = model
        self.dispatch_interval = dispatch_interval
        self.timeout = timeout

        # State
        self._trail: Deque[TrailPoint] = deque(maxlen=trail_maxlen)
        self._warnings: List[Warning] = []
        self._narrative: str = ""
        self._action_hint: str = ""
        self._confidence: float = 0.0
        self._narrative_pos: Optional[Tuple[float, float, float]] = None
        self._narrative_time: float = 0.0

        # Goal
        self._goal_area: int = 0
        self._goal_pos: Optional[Tuple[float, float, float]] = None
        self._goal_name: str = "explore"

        # Dispatch state
        self._last_dispatch_time: float = 0.0
        self._pending_task: Optional[asyncio.Task] = None
        self._last_problem: str = ""

        # Stats
        self.thoughts_sent: int = 0
        self.thoughts_complete: int = 0
        self.thoughts_stale: int = 0
        self.thoughts_failed: int = 0

        # Lazy ollama client
        self._client = None
        self._ollama_mod = None
        try:
            import ollama
            self._ollama_mod = ollama
        except ImportError:
            log.warning("ollama not available -- spatial advisor disabled")

    def _get_client(self):
        if self._client is None and self._ollama_mod is not None:
            try:
                self._client = self._ollama_mod.AsyncClient()
            except Exception as e:
                log.warning("Failed to create ollama client: %s", e)
        return self._client

    @property
    def enabled(self) -> bool:
        return self._ollama_mod is not None

    # -- Trail and goal ----------------------------------------------------

    def record_trail(
        self,
        pos: Tuple[float, float, float],
        yaw: float,
        area: int,
    ) -> None:
        """Called every tick with current position."""
        if pos is None:
            return
        self._trail.append(TrailPoint(
            t=time.time(),
            x=float(pos[0]),
            y=float(pos[1]),
            z=float(pos[2]),
            yaw=float(yaw),
            area=int(area),
        ))

    def set_goal(
        self,
        goal_area: int,
        goal_pos: Optional[Tuple[float, float, float]] = None,
        goal_name: str = "target",
    ) -> None:
        """Update the current navigation objective."""
        self._goal_area = goal_area
        self._goal_pos = goal_pos
        self._goal_name = goal_name

    def note_problem(self, text: str) -> None:
        """Record a brief note about the most recent problem (for LLM context)."""
        self._last_problem = text[:120]

    # -- Dispatch ----------------------------------------------------------

    def maybe_dispatch(self, frame: np.ndarray) -> bool:
        """Spawn a thought if the interval has elapsed and no thought is pending.

        Returns True if a thought was dispatched, False otherwise.
        """
        if not self.enabled or frame is None:
            return False
        if self._pending_task is not None and not self._pending_task.done():
            return False
        if not self._trail:
            return False
        now = time.time()
        if now - self._last_dispatch_time < self.dispatch_interval:
            return False

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False  # not in an async context

        # Snapshot current state
        latest = self._trail[-1]
        snapshot = ThoughtSnapshot(
            id=f"t{self.thoughts_sent + 1}",
            sent_at=now,
            sent_pos=(latest.x, latest.y, latest.z),
            sent_yaw=latest.yaw,
            sent_area=latest.area,
            goal_desc=describe_goal(
                (latest.x, latest.y, latest.z), self._goal_pos, self._goal_name
            ),
        )

        # Copy trail (deque is shared)
        trail_snapshot = list(self._trail)

        # Copy frame bytes before spawning (frame ref is mutable)
        frame_copy = frame.copy()

        self._last_dispatch_time = now
        self.thoughts_sent += 1
        self._pending_task = asyncio.ensure_future(
            self._run_thought(frame_copy, snapshot, trail_snapshot)
        )
        log.debug("Advisor dispatched thought %s at area %d",
                  snapshot.id, snapshot.sent_area)
        return True

    async def _run_thought(
        self,
        frame: np.ndarray,
        snapshot: ThoughtSnapshot,
        trail: List[TrailPoint],
    ) -> None:
        """Run a single thought end-to-end: build prompt, call Ollama, validate, apply."""
        client = self._get_client()
        if client is None:
            self.thoughts_failed += 1
            return

        try:
            prompt = self._build_prompt(snapshot, trail)
            img_bytes = self._encode_frame(frame)

            msg = {
                "role": "user",
                "content": prompt,
                "images": [img_bytes],
            }

            response = await asyncio.wait_for(
                client.chat(model=self.model, messages=[msg]),
                timeout=self.timeout,
            )
            text = response["message"]["content"].strip()

            # Strip markdown fences (common Ollama pattern)
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text
                text = text.rsplit("```", 1)[0].strip()

            parsed = json.loads(text)
        except asyncio.TimeoutError:
            log.warning("Advisor thought %s timed out after %.1fs",
                        snapshot.id, self.timeout)
            self.thoughts_failed += 1
            return
        except (json.JSONDecodeError, KeyError) as e:
            log.warning("Advisor thought %s parse error: %s", snapshot.id, e)
            self.thoughts_failed += 1
            return
        except Exception as e:
            log.warning("Advisor thought %s failed: %s", snapshot.id, e)
            self.thoughts_failed += 1
            return

        # Validate staleness
        if self._is_stale(snapshot):
            self.thoughts_stale += 1
            log.debug("Advisor thought %s stale on arrival", snapshot.id)
            return

        self._apply_response(parsed, snapshot)
        self.thoughts_complete += 1

    def _is_stale(self, snapshot: ThoughtSnapshot) -> bool:
        """Check if a thought's context is still valid."""
        now = time.time()
        if now - snapshot.sent_at > _MAX_THOUGHT_AGE:
            return True
        if not self._trail:
            return True
        latest = self._trail[-1]
        cur_pos = (latest.x, latest.y, latest.z)
        dist = math.hypot(
            cur_pos[0] - snapshot.sent_pos[0],
            cur_pos[1] - snapshot.sent_pos[1],
        )
        if dist > _MAX_STALE_DISTANCE:
            return True
        # Also check vertical — if we moved up/down a lot, context changed
        if abs(cur_pos[2] - snapshot.sent_pos[2]) > 100:
            return True
        return False

    def _apply_response(self, parsed: dict, snapshot: ThoughtSnapshot) -> None:
        """Apply a validated response to the advisor state."""
        self._narrative = str(parsed.get("narrative", ""))[:200]
        self._action_hint = str(parsed.get("action_hint", ""))[:40]
        self._confidence = float(parsed.get("confidence", 0.5))
        self._narrative_pos = snapshot.sent_pos
        self._narrative_time = time.time()

        new_warnings = []
        for h in parsed.get("hazards", []) or []:
            if not isinstance(h, dict):
                continue
            kind = str(h.get("kind", "")).lower()
            if kind in ("none", "null", ""):
                continue
            direction = str(h.get("direction", "ahead")).lower()
            severity = str(h.get("severity", "low")).lower()
            if severity not in ("low", "medium", "high"):
                severity = "low"
            text = str(h.get("text", kind))[:160]
            new_warnings.append(Warning(
                kind=kind,
                direction=direction,
                severity=severity,
                text=text,
                recorded_at=self._narrative_time,
                recorded_pos=snapshot.sent_pos,
            ))
        self._warnings = new_warnings

        if new_warnings:
            top = new_warnings[0]
            log.info("Advisor #%s: %s [%s/%s] %s -> %s",
                     snapshot.id, self._narrative,
                     top.kind, top.severity, top.text, self._action_hint)
        else:
            log.debug("Advisor #%s: %s -> %s",
                      snapshot.id, self._narrative, self._action_hint)

    def _build_prompt(
        self,
        snapshot: ThoughtSnapshot,
        trail: List[TrailPoint],
    ) -> str:
        trail_summary = build_trail_summary(trail)
        return SPATIAL_ADVISOR_PROMPT.format(
            px=int(snapshot.sent_pos[0]),
            py=int(snapshot.sent_pos[1]),
            pz=int(snapshot.sent_pos[2]),
            yaw=int(snapshot.sent_yaw),
            area=snapshot.sent_area,
            goal_desc=snapshot.goal_desc,
            trail_summary=trail_summary,
            last_problem=self._last_problem or "none",
        )

    def _encode_frame(self, frame: np.ndarray) -> bytes:
        h, w = frame.shape[:2]
        scale = min(1.0, 512 / max(h, w))
        if scale < 1.0:
            small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        else:
            small = frame
        _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
        return buf.tobytes()

    # -- Queries from navigator --------------------------------------------

    def current_warnings(self) -> List[Warning]:
        """Return non-stale warnings. Prunes stale ones in place."""
        now = time.time()
        if not self._trail:
            return []
        cur = self._trail[-1]
        cur_pos = (cur.x, cur.y, cur.z)

        fresh = []
        for w in self._warnings:
            if now - w.recorded_at > _MAX_WARNING_AGE:
                continue
            # Stale if bot moved far from where warning was issued
            dist = math.hypot(
                cur_pos[0] - w.recorded_pos[0],
                cur_pos[1] - w.recorded_pos[1],
            )
            if dist > _MAX_STALE_DISTANCE:
                continue
            fresh.append(w)
        self._warnings = fresh
        return list(fresh)

    def current_narrative(self) -> str:
        return self._narrative

    def is_hazard_ahead(self) -> bool:
        """Quick check — is there a high-severity halt-worthy hazard ahead?"""
        for w in self.current_warnings():
            if w.severity == "high" and w.kind in _HALT_HAZARD_KINDS and w.direction == "ahead":
                return True
        return False

    def get_recommended_action(self) -> Optional[str]:
        """Return the action hint if it's still fresh, else None."""
        if not self._action_hint:
            return None
        if time.time() - self._narrative_time > _MAX_WARNING_AGE:
            return None
        return self._action_hint

    def stats(self) -> dict:
        return {
            "sent": self.thoughts_sent,
            "complete": self.thoughts_complete,
            "stale": self.thoughts_stale,
            "failed": self.thoughts_failed,
            "pending": 1 if (self._pending_task and not self._pending_task.done()) else 0,
        }

    # -- Lifecycle ---------------------------------------------------------

    def shutdown(self) -> None:
        """Cancel any pending thought and log stats."""
        if self._pending_task and not self._pending_task.done():
            self._pending_task.cancel()
        log.info("SpatialAdvisor shutdown: %s", self.stats())
