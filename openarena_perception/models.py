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
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Set, Tuple

log = logging.getLogger(__name__)


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
