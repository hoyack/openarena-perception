"""Perception pipeline orchestrator.

Wires all perception sub-modules together, manages tick budgets with
rate-limiting and attention-based priority, and produces immutable
SituationalAwareness snapshots every tick.

This is the single class that game loop consumers call instead of
manually orchestrating individual detectors.  It implements attention-based
filtering (FPS Bot Spec Section 2.2) where combat state increases tracker
frequency and decreases anomaly detection frequency.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from openarena_perception.config import PerceptionConfig, build_config
from openarena_perception.models import SituationalAwareness

if TYPE_CHECKING:
    from openarena_perception.perception.sound_parser import ConsoleLogParser
from openarena_perception.perception.capture import ScreenCapture, make_capture
from openarena_perception.perception.config import PerceptionPipelineConfig
from openarena_perception.perception.damage_tracker import DamageTracker
from openarena_perception.perception.hud_parser import HUDParser
from openarena_perception.perception.motion_anomaly import MotionAnomalyTracker
from openarena_perception.perception.motion_detector import MotionDetector
from openarena_perception.perception.object_tracker import ObjectTracker
from openarena_perception.perception.player_detector import PlayerDetector
from openarena_perception.perception.wall_detector import Perception
from openarena_perception.perception.world_parser import WorldParser

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Builder function -- maps detector outputs to SituationalAwareness fields
# ---------------------------------------------------------------------------

def build_situational_awareness(
    *,
    tick: int,
    enemies: list,
    hud: Dict[str, Any],
    wall_ahead: bool,
    wall_score: float,
    open_direction: int,
    under_attack: bool,
    damage_tracker: DamageTracker,
    tracked: list,
    anomalies: list,
    pos: Optional[Tuple[float, float, float]],
    yaw: float,
    area: int,
    nav_state: Any,
    spatial: Any,
    has_frame: bool,
    sound_events: Optional[list] = None,
) -> SituationalAwareness:
    """Assemble a frozen SituationalAwareness snapshot from detector outputs."""
    health = hud.get("health")
    armor = hud.get("armor")
    ammo = hud.get("ammo")
    weapon = hud.get("weapon")

    is_alive = health is None or health > 0

    # Disposition derivation
    if not is_alive:
        disposition = "dead"
    elif health is not None and health < 30:
        disposition = "critical"
    elif health is not None and health < 60:
        disposition = "wounded"
    else:
        disposition = "healthy"

    # Armament derivation
    if weapon is None:
        armament = "unarmed"
    elif ammo is not None and ammo < 5:
        armament = "light"
    else:
        armament = "armed"

    # Orientation
    orientation = "oriented" if pos else "lost"

    # Enemy info
    nearest_enemy_distance: Optional[str] = None
    if enemies:
        nearest_enemy_distance = enemies[0].distance_estimate

    # Tracked objects
    locked_target = any(getattr(t, "locked", False) for t in tracked)

    # Anomalies
    lockable_anomaly = any(
        getattr(a, "frames_seen", 0) >= 3 and not getattr(a, "identified", True)
        for a in anomalies
    )

    # Spatial memory
    room_surveyed = spatial.is_surveyed(area) if spatial else False

    # Navigation state
    has_path = getattr(nav_state, "has_path", False) if nav_state else False
    path_length = getattr(nav_state, "path_length", 0) if nav_state else 0
    is_stuck = getattr(nav_state, "is_stuck", False) if nav_state else False
    is_recovering = getattr(nav_state, "is_recovering", False) if nav_state else False
    nav_target = getattr(nav_state, "nav_target", None) if nav_state else None

    # Sound awareness derivation (PERC-08)
    _sound_events = sound_events or []
    sound_events_recent = len(_sound_events)
    sound_nearby_combat = any(e.event_type == "Kill" for e in _sound_events)
    sound_last_pickup_item: Optional[str] = None
    sound_last_kill_victim: Optional[str] = None
    for e in reversed(_sound_events):
        if sound_last_pickup_item is None and e.event_type == "Item":
            sound_last_pickup_item = getattr(e, "item_name", None) or e.data
        if sound_last_kill_victim is None and e.event_type == "Kill":
            sound_last_kill_victim = getattr(e, "data", "")
        if sound_last_pickup_item is not None and sound_last_kill_victim is not None:
            break

    return SituationalAwareness(
        tick=tick,
        timestamp=time.time(),
        pos=pos,
        yaw=yaw,
        current_area=area,
        health=health,
        armor=armor,
        ammo=ammo,
        weapon=weapon,
        is_alive=is_alive,
        disposition=disposition,
        armament=armament,
        orientation=orientation,
        under_attack=under_attack,
        attacker_direction=damage_tracker.attacker_direction,
        seconds_since_damage=damage_tracker.seconds_since_damage,
        enemies_visible=len(enemies),
        nearest_enemy_distance=nearest_enemy_distance,
        wall_ahead=wall_ahead,
        wall_score=wall_score,
        open_direction=open_direction,
        in_water=False,
        tracked_objects=len(tracked),
        locked_target=locked_target,
        anomaly_count=len(anomalies),
        lockable_anomaly=lockable_anomaly,
        room_surveyed=room_surveyed,
        room_type="unknown",
        room_exits=0,
        has_path=has_path,
        path_length=path_length,
        is_stuck=is_stuck,
        is_recovering=is_recovering,
        nav_target=nav_target,
        has_frame=has_frame,
        sound_events_recent=sound_events_recent,
        sound_nearby_combat=sound_nearby_combat,
        sound_last_pickup_item=sound_last_pickup_item,
        sound_last_kill_victim=sound_last_kill_victim,
    )


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

class PerceptionPipeline:
    """Orchestrates all perception sub-modules into SituationalAwareness.

    Accepts a ``PerceptionPipelineConfig`` (tick-budget/rate-limiting) and a
    ``PerceptionConfig`` (ROIs, HSV ranges, OCR config) at construction time.

    Call ``tick()`` once per game loop iteration to get an immutable snapshot
    of the bot's current perception state.
    """

    def __init__(
        self,
        pipeline_cfg: Optional[PerceptionPipelineConfig] = None,
        perception_cfg: Optional[PerceptionConfig] = None,
        *,
        capture: Optional[ScreenCapture] = None,
        sound_parser: Optional["ConsoleLogParser"] = None,
    ):
        self._pcfg = pipeline_cfg or PerceptionPipelineConfig()
        self._cfg = perception_cfg or build_config()

        # Sound parser (PERC-08)
        self._sound_parser = sound_parser
        self._last_sound_events: list = []

        # Sub-modules
        self._capture = capture or make_capture(
            mode="window",
            window_title=self._cfg.window_title,
        )
        self._hud = HUDParser(self._cfg)
        self._world = WorldParser(self._cfg)
        self._wall = Perception()
        self._motion = MotionDetector()
        self._player = PlayerDetector()
        self._tracker = ObjectTracker()
        self._damage = DamageTracker()
        self._anomaly = MotionAnomalyTracker()

        # Tick counter
        self._tick = 0

        # Cached results between rate-limited runs
        self._last_hud: Dict[str, Any] = {}
        self._last_motion: list = []
        self._last_tracked: list = []
        self._last_anomalies: list = []

        # Previous alive state for death-reset detection
        self._was_alive = True

    # -- lifecycle -----------------------------------------------------------

    def open(self) -> "PerceptionPipeline":
        """Open the underlying screen capture.  Call before ``tick()``."""
        self._capture.open()
        return self

    def close(self) -> None:
        """Release the screen capture resource."""
        self._capture.close()

    def __enter__(self) -> "PerceptionPipeline":
        return self.open()

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- main tick -----------------------------------------------------------

    def tick(
        self,
        pos: Optional[Tuple[float, float, float]] = None,
        yaw: float = 0.0,
        area: int = 0,
        nav_state: Any = None,
        spatial: Any = None,
    ) -> SituationalAwareness:
        """Run one perception cycle.  Returns a frozen snapshot."""
        self._tick += 1

        # (a) Grab frame -------------------------------------------------------
        frame = self._safe_call("capture", self._capture.grab)
        if frame is None:
            # Cannot proceed without a frame -- return a minimal snapshot
            return self._empty_snapshot(pos, yaw, area, nav_state, spatial)

        # (b) ALWAYS: enemy detection (~8 ms) -----------------------------------
        enemies = self._safe_call("world", self._world.parse_enemies, frame) or []

        # (c) ALWAYS: wall detection (~2 ms) ------------------------------------
        wall_result = self._safe_call("wall", self._wall.detect_wall_ahead, frame)
        if wall_result is None:
            wall_ahead, wall_score, open_dir = False, 0.0, 0
        else:
            wall_ahead, wall_score, open_dir = wall_result

        # (d) ALWAYS: damage tracking (~1 ms) -----------------------------------
        health = self._last_hud.get("health")
        under_attack = self._safe_call(
            "damage", self._damage.update, health, frame,
        )
        if under_attack is None:
            under_attack = False

        # Determine combat state for attention priority
        in_combat = under_attack or len(enemies) > 0

        # (e) Rate-limited: HUD OCR (every hud_ocr_interval ticks) -------------
        if self._tick % self._pcfg.hud_ocr_interval == 0:
            hud = self._safe_call("hud", self._hud.parse_all, frame)
            if hud is not None:
                self._last_hud = hud

        # (f) Rate-limited: motion detection ------------------------------------
        motion_interval = self._pcfg.motion_interval
        if self._tick % motion_interval == 0:
            motion = self._safe_call("motion", self._motion.detect, frame)
            if motion is not None:
                self._last_motion = motion

        # (g) Rate-limited: object tracking (attention-aware) -------------------
        tracker_interval = (
            self._pcfg.combat_tracker_interval
            if in_combat
            else self._pcfg.tracker_interval
        )
        if self._tick % tracker_interval == 0:
            tracked = self._safe_call("tracker", self._tracker.update, frame)
            if tracked is not None:
                self._last_tracked = tracked

        # (h) Rate-limited: anomaly detection (attention-aware) -----------------
        run_anomaly = (
            self._pcfg.combat_anomaly_enabled if in_combat else True
        )
        if run_anomaly and self._tick % self._pcfg.anomaly_interval == 0:
            bot_pos_2d = (pos[0], pos[1]) if pos else None
            anomalies = self._safe_call(
                "anomaly", self._anomaly.update, frame, bot_pos_2d, yaw,
            )
            if anomalies is not None:
                self._last_anomalies = anomalies

        # (h2) Rate-limited: sound event polling (PERC-08) ----------------------
        if self._sound_parser and self._tick % self._pcfg.sound_poll_interval == 0:
            events = self._safe_call("sound", self._sound_parser.poll)
            if events is not None:
                self._last_sound_events = events
            else:
                self._last_sound_events = []

        # (i) Death reset -------------------------------------------------------
        is_alive = self._last_hud.get("health") is None or self._last_hud.get("health", 1) > 0
        if self._was_alive and not is_alive and self._pcfg.reset_on_death:
            self._reset_stateful_trackers()
        self._was_alive = is_alive

        # (j) Assemble snapshot -------------------------------------------------
        return build_situational_awareness(
            tick=self._tick,
            enemies=enemies,
            hud=self._last_hud,
            wall_ahead=wall_ahead,
            wall_score=wall_score,
            open_direction=open_dir,
            under_attack=under_attack,
            damage_tracker=self._damage,
            tracked=self._last_tracked,
            anomalies=self._last_anomalies,
            pos=pos,
            yaw=yaw,
            area=area,
            nav_state=nav_state,
            spatial=spatial,
            has_frame=True,
            sound_events=self._last_sound_events,
        )

    # -- helpers -------------------------------------------------------------

    def _safe_call(self, name: str, fn, *args, **kwargs):
        """Call *fn* and return the result; on error log and return None."""
        try:
            return fn(*args, **kwargs)
        except Exception:
            log.exception("Perception sub-module '%s' raised an error", name)
            return None

    def _reset_stateful_trackers(self) -> None:
        """Reset trackers that accumulate state across lives."""
        log.info("Death detected -- resetting stateful trackers")
        try:
            self._tracker.reset()
        except Exception:
            log.exception("Failed to reset ObjectTracker")
        try:
            self._anomaly.reset()
        except Exception:
            log.exception("Failed to reset MotionAnomalyTracker")

    def _empty_snapshot(
        self,
        pos: Optional[Tuple[float, float, float]],
        yaw: float,
        area: int,
        nav_state: Any,
        spatial: Any,
    ) -> SituationalAwareness:
        """Return a minimal snapshot when no frame could be captured."""
        return build_situational_awareness(
            tick=self._tick,
            enemies=[],
            hud=self._last_hud,
            wall_ahead=False,
            wall_score=0.0,
            open_direction=0,
            under_attack=False,
            damage_tracker=self._damage,
            tracked=[],
            anomalies=[],
            pos=pos,
            yaw=yaw,
            area=area,
            nav_state=nav_state,
            spatial=spatial,
            has_frame=False,
            sound_events=[],
        )

    @property
    def tick_count(self) -> int:
        """Current tick counter value."""
        return self._tick
