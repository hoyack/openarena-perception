"""Central data contracts for the bot cognitive architecture.

These types are the API between subsystems. Import from here, not from
strategic_brain.py (which re-exports for backward compatibility).
"""
from __future__ import annotations

import glob
import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Deque, Dict, Optional, Set, Tuple

log = logging.getLogger(__name__)

# Re-exported for cross-subsystem access (Phase 8)
from openarena_perception.combat.humanize import (  # noqa: E402
    HumanizationConfig,
    PERSONALITIES,
    PersonalityProfile,
)


# ── State Machine ────────────────────────────────────────────────────

class BrainState(Enum):
    """FSM states for the strategic brain."""
    DEAD = "dead"
    COMBAT = "combat"
    STUCK = "stuck"
    PICKING_UP_ITEM = "picking_up_item"
    TRAVERSING_DOOR = "traversing_door"
    SURVEYING = "surveying"
    NAVIGATING = "navigating"
    EXPLORING = "exploring"


# ── Situational Awareness ────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class SituationalAwareness:
    """Unified perception snapshot -- rebuilt every tick. Immutable."""
    tick: int
    timestamp: float

    # Position
    pos: Optional[Tuple[float, float, float]]
    yaw: float
    current_area: int

    # Vitals
    health: Optional[int]
    armor: Optional[int]
    ammo: Optional[int]
    weapon: Optional[str]
    is_alive: bool

    # Disposition (derived)
    disposition: str   # healthy/wounded/critical/dead
    armament: str      # armed/light/unarmed
    orientation: str   # oriented/exploring/lost

    # Threats
    under_attack: bool
    attacker_direction: int
    seconds_since_damage: float
    enemies_visible: int
    nearest_enemy_distance: Optional[str]

    # Environment
    wall_ahead: bool
    wall_score: float
    open_direction: int
    in_water: bool

    # Object tracking
    tracked_objects: int
    locked_target: bool

    # Motion anomalies
    anomaly_count: int
    lockable_anomaly: bool

    # Spatial memory
    room_surveyed: bool
    room_type: str
    room_exits: int

    # Navigation
    has_path: bool
    path_length: int
    is_stuck: bool
    is_recovering: bool
    nav_target: Optional[str]

    # Frame available
    has_frame: bool

    # Sound awareness (PERC-08)
    sound_events_recent: int = 0
    sound_nearby_combat: bool = False
    sound_last_pickup_item: Optional[str] = None
    sound_last_kill_victim: Optional[str] = None


# ── Spatial Knowledge ────────────────────────────────────────────────

class SpatialKnowledge:
    """Persistent spatial memory across the session."""

    def __init__(self, survey_dir: str = ""):
        if not survey_dir:
            survey_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                       "room_surveys")
        self._surveys: Dict[int, object] = {}  # area_id -> RoomSurvey
        self._visited: Set[int] = set()
        self._visited_clusters: Set[Tuple[int, int]] = set()
        self._entry_yaw: Dict[int, float] = {}
        self._entry_time: Dict[int, float] = {}
        self._danger: Dict[int, float] = {}
        self._prev_area: int = 0

        # Load existing surveys
        self._load_surveys(survey_dir)

    def enter_area(self, area_id: int, yaw: float):
        if area_id != self._prev_area and area_id > 0:
            self._visited.add(area_id)
            self._entry_yaw[area_id] = yaw
            self._entry_time[area_id] = time.time()
            self._prev_area = area_id

    def record_danger(self, area_id: int):
        self._danger[area_id] = time.time()

    def is_surveyed(self, area_id: int) -> bool:
        return area_id in self._surveys

    def should_survey(self, area_id: int, pos=None) -> bool:
        if area_id in self._surveys:
            return False
        if pos:
            cx = int(pos[0]) // 256
            cy = int(pos[1]) // 256
            key = (cx, cy)
            if key in self._visited_clusters:
                return False
            self._visited_clusters.add(key)
        return True

    def get_survey(self, area_id: int):
        return self._surveys.get(area_id)

    def store_survey(self, survey):
        self._surveys[survey.area_id] = survey

    def is_dangerous(self, area_id: int, window: float = 30.0) -> bool:
        t = self._danger.get(area_id, 0)
        return time.time() - t < window

    def entry_yaw(self, area_id: int) -> Optional[float]:
        return self._entry_yaw.get(area_id)

    @property
    def total_surveys(self) -> int:
        return len(self._surveys)

    def _load_surveys(self, survey_dir):
        for path in glob.glob(os.path.join(survey_dir, "area_*.json")):
            try:
                with open(path) as f:
                    d = json.load(f)
                # Store as a simple namespace
                from types import SimpleNamespace
                s = SimpleNamespace(**d)
                s.exits = d.get("exits", [])
                self._surveys[d["area_id"]] = s
            except Exception:
                pass
        if self._surveys:
            log.info("Loaded %d room surveys", len(self._surveys))


# ── Intent / Problem / BotContext (Phase 10) ─────────────────────────


class MacroIntent(StrEnum):
    """High-level bot intent categories for Phase 10 intent tracking."""
    IDLE = "IDLE"
    TOURING = "TOURING"
    CLIMBING_STAIRS = "CLIMBING_STAIRS"
    AVOIDING_WALL = "AVOIDING_WALL"
    RECOVERING_STUCK = "RECOVERING_STUCK"
    REASSESSING_POSITION = "REASSESSING_POSITION"
    RESPAWNING = "RESPAWNING"
    PAUSING_TO_ASSESS = "PAUSING_TO_ASSESS"


class IntentStatus(StrEnum):
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Intent:
    """Immutable snapshot of a single bot intent.

    Use dataclasses.replace() to create modified copies (intent is frozen).
    """
    macro: MacroIntent
    sub: str
    description: str
    started_at: float
    target: Optional[Tuple[float, float, float]] = None
    target_area: Optional[int] = None
    status: IntentStatus = IntentStatus.EXECUTING

    def duration(self, now: float) -> float:
        return now - self.started_at


@dataclass(frozen=True, slots=True)
class Problem:
    """Immutable record of a bot problem event (stuck, pin, halt, respawn)."""
    kind: str   # "stuck" | "pin" | "wall_halt" | "advisor_halt" | "respawn"
    location: Tuple[float, float, float]
    timestamp: float
    description: str


@dataclass(slots=True)   # NOT frozen -- holds mutable deques (Research Pitfall 2)
class BotContext:
    """Mutable container for bot self-awareness state.

    Owned by ItemTour for Phase 10. Designed to be subsystem-neutral so
    StrategicBrain or other loops can adopt it in later phases without
    refactoring the data model.
    """
    current_intent: Intent
    tick_count: int = 0
    path_progress: Tuple[int, int] = (0, 0)
    intent_history: Deque[Intent] = field(default_factory=lambda: deque(maxlen=5))
    problem_history: Deque[Problem] = field(default_factory=lambda: deque(maxlen=5))
    current_area_history: Deque[int] = field(default_factory=lambda: deque(maxlen=10))

    def push_intent(self, new_intent: Intent) -> None:
        """Push current intent to history and replace with new."""
        self.intent_history.append(self.current_intent)
        self.current_intent = new_intent

    def record_problem(self, problem: Problem) -> None:
        self.problem_history.append(problem)

    def record_area(self, area_id: int) -> None:
        if area_id <= 0:
            return
        if self.current_area_history and self.current_area_history[-1] == area_id:
            return  # same area, do not duplicate
        self.current_area_history.append(area_id)
