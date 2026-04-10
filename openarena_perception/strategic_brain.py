"""
strategic_brain.py -- Layered strategic decision architecture.

Thin orchestrator that delegates all behavior to subsystem modules:
  - reflexes/ (SubsumptionArbiter, DeathHandler, StuckEscape)
  - combat/ (CombatEngager)
  - navigation/ (NavBehavior, SurveyBehavior)

Single tick entry point that orchestrates ALL perception and action modules
through a finite state machine with unified situational awareness.

States:
  DEAD -> COMBAT -> STUCK -> PICKING_UP_ITEM -> TRAVERSING_DOOR ->
  SURVEYING -> NAVIGATING -> EXPLORING

Each state has specific behaviors and transition conditions.
All movement goes through VirtualController (pipe-only, no mouse).
LLM is used strategically (not every tick).
"""

from __future__ import annotations

import logging
import os
import time

from .combat import CombatEngager, CombatMover
from .commander import Commander
from .damage_tracker import DamageTracker
from .game_bridge import GameBridge
from .game_state import GameState
from .hud_schema import (
    STATE_FILE as _HUD_STATE_FILE,
)
from .hud_schema import (
    build_hud_payload,
    ensure_runtime_dirs,
    write_hud_state,
)
from .learned_map import LearnedMap
from .models import BrainState, SituationalAwareness, SpatialKnowledge
from .motion_anomaly import MotionAnomalyTracker
from .navigation import NavBehavior, SurveyBehavior
from .navigator import Navigator
from .object_tracker import ObjectTracker
from .perception import Perception
from .reflexes import DeathHandler, StuckEscape, SubsumptionArbiter
from .room_surveyor import RoomSurveyor
from .tactics import TacticalFSM
from .virtual_controller import VirtualController

log = logging.getLogger(__name__)


# -- Build Situational Awareness ---------------------------------------------

def build_situational_awareness(tick, gs, nav, damage, perception, obj_tracker,
                                 anomaly_tracker, surveyor, spatial, nav_target=None):
    """Build a SituationalAwareness snapshot from current game state."""
    hp = gs.health
    is_alive = hp is None or hp > 0

    # Disposition
    if not is_alive:
        disposition = "dead"
    elif hp is not None and hp < 30:
        disposition = "critical"
    elif hp is not None and hp < 60:
        disposition = "wounded"
    else:
        disposition = "healthy"

    # Armament
    ammo = gs.ammo
    if ammo is not None and ammo > 20:
        armament = "armed"
    elif ammo is not None and ammo > 5:
        armament = "light"
    else:
        armament = "unarmed"

    # Orientation
    if nav.has_path:
        orientation = "oriented"
    elif nav.current_area > 0:
        orientation = "exploring"
    else:
        orientation = "lost"

    # Threats
    under_attack = damage.update(gs.health, gs.frame) if gs.frame is not None else False
    enemies = len(gs.enemies) if gs.enemies else 0

    # Environment
    wall_ahead = False
    wall_score = 0.0
    open_dir = 0
    if gs.frame is not None:
        wall_ahead, wall_score, open_dir = perception.detect_wall_ahead(gs.frame)

    # Room survey
    room_surveyed = spatial.is_surveyed(nav.current_area)
    survey = spatial.get_survey(nav.current_area)

    # Anomalies
    lockable = anomaly_tracker.get_lockable_anomaly() if anomaly_tracker else None

    return SituationalAwareness(
        tick=tick, timestamp=time.time(),
        pos=nav.pos, yaw=nav.yaw, current_area=nav.current_area,
        health=hp, armor=gs.armor, ammo=ammo, weapon=gs.weapon,
        is_alive=is_alive,
        disposition=disposition, armament=armament, orientation=orientation,
        under_attack=under_attack,
        attacker_direction=damage.attacker_direction,
        seconds_since_damage=damage.seconds_since_damage,
        enemies_visible=enemies,
        nearest_enemy_distance=gs.nearest_enemy.distance_estimate if gs.nearest_enemy else None,
        wall_ahead=wall_ahead, wall_score=wall_score,
        open_direction=open_dir,
        in_water=False,  # checked separately
        tracked_objects=obj_tracker.active_count if obj_tracker else 0,
        locked_target=obj_tracker.locked_id is not None if obj_tracker else False,
        anomaly_count=anomaly_tracker.active_tracks if anomaly_tracker else 0,
        lockable_anomaly=lockable is not None,
        room_surveyed=room_surveyed,
        room_type=survey.room_type if survey else "",
        room_exits=len(survey.exits) if survey else 0,
        has_path=nav.has_path, path_length=len(nav._path),
        is_stuck=nav.is_stuck, is_recovering=nav.is_recovering,
        nav_target=nav_target,
        has_frame=gs.frame is not None,
    )


# -- Strategic Brain ----------------------------------------------------------

class StrategicBrain:
    """
    Top-level orchestrator. Single tick() entry point.
    Owns the state machine, delegates all behavior to subsystem modules.
    """

    # Back-compat alias for any code that referenced StrategicBrain.STATE_FILE
    # as a class attribute. New code should import hud_schema.STATE_FILE
    # directly. (Pitfall 6 from 10-RESEARCH.md.)
    STATE_FILE = _HUD_STATE_FILE

    def __init__(
        self,
        bridge: GameBridge,
        nav: Navigator,
        commander: Commander,
        perception: Perception,
        damage_tracker: DamageTracker,
        ctrl: VirtualController,
        obj_tracker: ObjectTracker | None = None,
        anomaly_tracker: MotionAnomalyTracker | None = None,
        surveyor: RoomSurveyor | None = None,
        spatial: SpatialKnowledge | None = None,
        items: list | None = None,
        map_name: str = "unknown",
    ):
        self.bridge = bridge
        self.nav = nav
        self.commander = commander
        self.perception = perception
        self.damage = damage_tracker
        self.ctrl = ctrl
        self.obj_tracker = obj_tracker or ObjectTracker()
        self.anomaly = anomaly_tracker or MotionAnomalyTracker()
        self.surveyor = surveyor
        self.spatial = spatial or SpatialKnowledge()
        self.items = items or []
        self.map_name = map_name
        self.combat_mover = CombatMover()

        # Learned map -- self-mapping navigation layer
        self.learned_map = LearnedMap(map_name=map_name, aas_graph=nav.graph)
        self.learned_map.load()
        # Wire edge cost callback into A*
        nav._edge_cost_fn = self.learned_map.edge_penalty
        # Wire area transition reporting
        self._prev_area_for_learning = 0
        nav._on_area_transition = self._on_area_transition

        # Awareness
        self._awareness: SituationalAwareness | None = None

        # Tick counter
        self._tick = 0
        self._start_time = time.time()

        # Timing
        self._last_refocus = 0.0
        self._survey_cooldown = 0.0
        self._last_strategic_query = 0.0
        self._last_status_log = 0.0

        # Window focus
        self._window_id = ""

        # -- Subsystem modules (Phase 4 extraction) --
        self._arbiter = SubsumptionArbiter()
        self._death_handler = DeathHandler(bridge, ctrl)
        self._stuck_escape = StuckEscape(nav)
        self._engager = CombatEngager(ctrl, bridge, self.combat_mover)
        self._nav_behavior = NavBehavior(ctrl, nav, commander, nav.graph if nav else None)
        self._survey_behavior = SurveyBehavior(surveyor, self.spatial) if surveyor else None

        # -- Tactical FSM (Phase 5 extraction) --
        self._fsm = TacticalFSM(
            arbiter=self._arbiter,
            death_handler=self._death_handler,
            stuck_escape=self._stuck_escape,
            engager=self._engager,
            nav_behavior=self._nav_behavior,
            survey_behavior=self._survey_behavior,
            ctrl=self.ctrl,
            anomaly_tracker=self.anomaly,
            obj_tracker=self.obj_tracker,
        )

    # -- Property bridges for backward compat with tests/external access ------

    @property
    def _deaths(self) -> int:
        return self._death_handler.deaths

    @_deaths.setter
    def _deaths(self, value: int) -> None:
        self._death_handler._deaths = value

    @property
    def _was_alive(self) -> bool:
        return self._death_handler.was_alive

    @_was_alive.setter
    def _was_alive(self, value: bool) -> None:
        self._death_handler.was_alive = value

    @property
    def _stuck_attempts(self) -> int:
        return self._stuck_escape.stuck_attempts

    @_stuck_attempts.setter
    def _stuck_attempts(self, value: int) -> None:
        self._stuck_escape._stuck_attempts = value

    @property
    def _stucks_on_current_target(self) -> int:
        return self._stuck_escape._stucks_on_current_target

    @_stucks_on_current_target.setter
    def _stucks_on_current_target(self, value: int) -> None:
        self._stuck_escape._stucks_on_current_target = value

    @property
    def _target_failures(self) -> dict[str, int]:
        return self._stuck_escape.target_failures

    @property
    def _target_blacklist(self) -> dict[str, float]:
        return self._stuck_escape.target_blacklist

    @property
    def _nav_target(self) -> str | None:
        return self._nav_behavior.nav_target

    @_nav_target.setter
    def _nav_target(self, value: str | None) -> None:
        self._nav_behavior.nav_target = value

    @property
    def _items_collected(self) -> int:
        return self._nav_behavior.items_collected

    # -- FSM property bridges (delegate to TacticalFSM) ----------------------

    @property
    def _state(self) -> BrainState:
        return self._fsm._state

    @_state.setter
    def _state(self, value: BrainState) -> None:
        self._fsm._state = value

    @property
    def _state_enter_time(self) -> float:
        return self._fsm._state_enter_time

    @_state_enter_time.setter
    def _state_enter_time(self, value: float) -> None:
        self._fsm._state_enter_time = value

    # -- Public API -----------------------------------------------------------

    async def tick(self, gs: GameState):
        """Single entry point -- called every frame."""
        self._tick += 1
        now = time.time()

        # Refocus game window periodically
        if now - self._last_refocus > 20.0:
            self._refocus()
            self._last_refocus = now

        # Update all sensors
        self.nav.update_position()
        self.nav.check_stuck_cleanup()

        if gs.frame is not None:
            self.obj_tracker.update(gs.frame)
            bot_pos = self.nav.pos[:2] if self.nav.pos else None
            self.anomaly.update(gs.frame, bot_pos=bot_pos)

        # Build unified awareness
        sa = build_situational_awareness(
            self._tick, gs, self.nav, self.damage, self.perception,
            self.obj_tracker, self.anomaly, self.surveyor, self.spatial,
            nav_target=self._nav_target,
        )
        self._awareness = sa

        # Update learned map (occupancy grid + wall segments)
        if sa.pos:
            self.learned_map.update(
                pos=sa.pos, yaw=sa.yaw,
                wall_ahead=sa.wall_ahead, wall_score=sa.wall_score,
                open_direction=sa.open_direction, in_water=sa.in_water,
            )

        # Update spatial knowledge
        if sa.current_area > 0:
            self.spatial.enter_area(sa.current_area, sa.yaw)
            if sa.under_attack:
                self.spatial.record_danger(sa.current_area)

        # Propagate was_alive for death detection (T-04-08 mitigation)
        if sa.is_alive:
            self._death_handler.was_alive = True

        # Evaluate state transitions
        new_state = self._evaluate_transitions(sa)
        if new_state != self._state:
            self._on_exit_state(self._state, sa)
            old = self._state
            self._state = new_state
            self._state_enter_time = now
            self._on_enter_state(new_state, sa)
            log.info("BRAIN: %s -> %s [%s hp=%s area=%d]",
                     old.value, new_state.value, sa.disposition,
                     sa.health, sa.current_area)

        # Execute current state behavior via subsystem dispatch
        await self._dispatch(self._state, sa, gs)

        # Status log every ~4s
        if now - self._last_status_log > 4.0:
            elapsed = now - self._start_time
            log.info("[%3.0fs] %s | %s | %s | %s | obj=%d anom=%d",
                     elapsed, self._state.value.upper(), sa.disposition,
                     sa.nav_target or "no target",
                     self.nav.get_status(),
                     sa.tracked_objects, sa.anomaly_count)
            self._last_status_log = now

        # Export HUD state
        if self._tick % 6 == 0:
            self._export_hud(sa)

    @property
    def state(self) -> BrainState:
        return self._fsm.state

    def get_status(self) -> str:
        sa = self._awareness
        if not sa:
            return "initializing"
        return (f"{self._state.value} | {sa.disposition} | "
                f"target={sa.nav_target or '?'} | "
                f"area={sa.current_area}")

    def _on_area_transition(self, from_area: int, to_area: int, success: bool):
        """Called by Navigator when area changes or stuck on an edge."""
        if success:
            self.learned_map.record_edge_success(from_area, to_area)
        else:
            self.learned_map.record_edge_failure(from_area, to_area)

    def shutdown(self):
        self.ctrl.release_all()
        # Guarantee all look/move actions released
        for a in ['lookup', 'lookdown', 'left', 'right',
                   'forward', 'back', 'moveleft', 'moveright',
                   'moveup', 'movedown', 'attack']:
            self.bridge.cmd(f"-{a}")
        self.bridge.cmd("centerview")
        self.bridge.stop_movement()
        self.bridge.stop_firing()
        self.learned_map.save()

    # -- State Machine (delegated to TacticalFSM) ------------------------------

    def _evaluate_transitions(self, sa: SituationalAwareness) -> BrainState:
        """Priority-ordered transition evaluation via TacticalFSM."""
        return self._fsm.evaluate_transitions(
            sa,
            survey_cooldown=self._survey_cooldown,
            spatial=self.spatial,
            surveyor=self.surveyor,
            commander=self.commander,
            nav_target=self._nav_target,
        )

    def _on_enter_state(self, state: BrainState, sa: SituationalAwareness):
        """Delegate state entry to TacticalFSM."""
        self._fsm.on_enter_state(state, sa)

    def _on_exit_state(self, state: BrainState, sa: SituationalAwareness):
        """Delegate state exit to TacticalFSM."""
        self._fsm.on_exit_state(state, sa)

    async def _dispatch(self, state: BrainState, sa: SituationalAwareness, gs):
        """Delegate tick dispatch to TacticalFSM."""
        cooldown = await self._fsm.dispatch(state, sa, gs, tick_count=self._tick)
        if cooldown is not None:
            self._survey_cooldown = cooldown

    # -- Utility --------------------------------------------------------------

    def _refocus(self):
        import subprocess
        env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", "ioquake3"],
                capture_output=True, text=True, timeout=3, env=env)
            for wid in result.stdout.strip().split("\n"):
                wid = wid.strip()
                if wid:
                    subprocess.run(["xdotool", "windowactivate", wid],
                                   capture_output=True, timeout=2, env=env)
                    self._window_id = wid
                    break
        except Exception:
            pass

    def _export_hud(self, sa):
        """Write the HUD state file via centralized hud_schema (Phase 10-01).

        Every pre-existing key is preserved verbatim via `extras=` so the
        HUD reader sees the same schema as before.
        """
        try:
            ensure_runtime_dirs()
            legacy_fields = {
                "map": self.map_name,
                "x": sa.pos[0] if sa.pos else 0,
                "y": sa.pos[1] if sa.pos else 0,
                "z": sa.pos[2] if sa.pos else 0,
                "yaw": sa.yaw,
                "health": sa.health,
                "armor": sa.armor,
                "ammo": sa.ammo,
                "weapon": sa.weapon,
                "alive": sa.is_alive,
                "stuck": sa.is_stuck,
                "recovering": sa.is_recovering,
                "items": [[n, x, y, z] for n, x, y, z in self.items],
                "deaths": self._deaths,
                "elapsed": time.time() - self._start_time,
                # Brain-specific
                "brain_state": self._state.value,
                "disposition": sa.disposition,
                "armament": sa.armament,
                "orientation": sa.orientation,
                "under_attack": sa.under_attack,
                "anomaly_count": sa.anomaly_count,
                "surveys_total": self.spatial.total_surveys,
                "current_room_type": sa.room_type,
                "current_room_exits": sa.room_exits,
                "nav_target": sa.nav_target or "",
                "state_duration": time.time() - self._state_enter_time,
                "items_collected": self._items_collected,
                "learned_map": self.learned_map.export_for_hud(),
            }
            payload = build_hud_payload(extras=legacy_fields)
            write_hud_state(payload)
        except Exception:
            pass
