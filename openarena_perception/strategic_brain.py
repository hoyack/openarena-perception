"""
strategic_brain.py — Layered strategic decision architecture.

Single tick entry point that orchestrates ALL perception and action modules
through a finite state machine with unified situational awareness.

States:
  DEAD → COMBAT → STUCK → PICKING_UP_ITEM → TRAVERSING_DOOR →
  SURVEYING → NAVIGATING → EXPLORING

Each state has specific behaviors and transition conditions.
All movement goes through VirtualController (pipe-only, no mouse).
LLM is used strategically (not every tick).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from typing import Dict, Optional

import cv2
import numpy as np

from .aas_parser import (
    TRAVEL_JUMP, TRAVEL_JUMPPAD, TRAVEL_BARRIERJUMP,
    TRAVEL_WALKOFFLEDGE, TRAVEL_LADDER,
)
from .combat import CombatMover
from .commander import Commander
from .damage_tracker import DamageTracker
from .game_bridge import GameBridge
from .game_state import GameState
from .models import BrainState, SituationalAwareness, SpatialKnowledge
from .motion_anomaly import MotionAnomalyTracker
from .navigator import Navigator
from .object_tracker import ObjectTracker
from .perception import Perception
from .room_surveyor import RoomSurveyor
from .learned_map import LearnedMap
from .virtual_controller import VirtualController

log = logging.getLogger(__name__)


# ── Build Situational Awareness ─────────────────────────────────────

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


# ── Strategic Brain ──────────────────────────────────────────────────

class StrategicBrain:
    """
    Top-level orchestrator. Single tick() entry point.
    Owns the state machine, calls all modules, exports HUD state.
    """

    STATE_FILE = "/tmp/oa_hud_state.json"

    def __init__(
        self,
        bridge: GameBridge,
        nav: Navigator,
        commander: Commander,
        perception: Perception,
        damage_tracker: DamageTracker,
        ctrl: VirtualController,
        obj_tracker: Optional[ObjectTracker] = None,
        anomaly_tracker: Optional[MotionAnomalyTracker] = None,
        surveyor: Optional[RoomSurveyor] = None,
        spatial: Optional[SpatialKnowledge] = None,
        items: Optional[list] = None,
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

        # Learned map — self-mapping navigation layer
        self.learned_map = LearnedMap(map_name=map_name, aas_graph=nav.graph)
        self.learned_map.load()
        # Wire edge cost callback into A*
        nav._edge_cost_fn = self.learned_map.edge_penalty
        # Wire area transition reporting
        self._prev_area_for_learning = 0
        nav._on_area_transition = self._on_area_transition

        # State machine
        self._state = BrainState.EXPLORING
        self._state_enter_time = time.time()
        self._prev_state = BrainState.EXPLORING

        # Awareness
        self._awareness: Optional[SituationalAwareness] = None
        self._nav_target: Optional[str] = None

        # Tick counter
        self._tick = 0
        self._start_time = time.time()
        self._deaths = 0
        self._was_alive = True
        self._stuck_attempts = 0
        self._items_collected = 0

        # Timing
        self._last_refocus = 0.0
        self._survey_cooldown = 0.0
        self._last_strategic_query = 0.0
        self._last_status_log = 0.0

        # Target blacklist — skip unreachable targets temporarily
        self._target_failures: Dict[str, int] = {}   # classname -> failure count
        self._target_blacklist: Dict[str, float] = {} # classname -> blacklist until timestamp
        self._stucks_on_current_target = 0

        # Window focus
        self._window_id = ""

    # ── Public API ────────────────────────────────────────────────

    async def tick(self, gs: GameState):
        """Single entry point — called every frame."""
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

        # Evaluate state transitions
        new_state = self._evaluate_transitions(sa)
        if new_state != self._state:
            self._on_exit_state(self._state, sa)
            old = self._state
            self._state = new_state
            self._state_enter_time = now
            self._on_enter_state(new_state, sa)
            log.info("BRAIN: %s → %s [%s hp=%s area=%d]",
                     old.value, new_state.value, sa.disposition,
                     sa.health, sa.current_area)

        # Execute current state behavior
        handlers = {
            BrainState.DEAD: self._tick_dead,
            BrainState.COMBAT: self._tick_combat,
            BrainState.STUCK: self._tick_stuck,
            BrainState.SURVEYING: self._tick_surveying,
            BrainState.NAVIGATING: self._tick_navigating,
            BrainState.EXPLORING: self._tick_exploring,
            BrainState.TRAVERSING_DOOR: self._tick_traversing_door,
            BrainState.PICKING_UP_ITEM: self._tick_picking_up_item,
        }
        await handlers[self._state](sa, gs)

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
        return self._state

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

    # ── State Transitions ─────────────────────────────────────────

    def _evaluate_transitions(self, sa: SituationalAwareness) -> BrainState:
        """Priority-ordered transition evaluation."""
        state_time = time.time() - self._state_enter_time

        # P1: Dead
        if not sa.is_alive:
            return BrainState.DEAD

        # P2: Combat (under attack with visible enemies)
        if (sa.under_attack and sa.enemies_visible > 0 and
                self._state != BrainState.DEAD):
            return BrainState.COMBAT

        # P3: Stuck
        if (sa.is_stuck and not sa.is_recovering and
                self._state not in (BrainState.DEAD, BrainState.COMBAT,
                                     BrainState.SURVEYING)):
            return BrainState.STUCK

        # P4: Item pickup (motion anomaly detected while navigating)
        if (sa.lockable_anomaly and
                self._state in (BrainState.NAVIGATING, BrainState.EXPLORING)):
            return BrainState.PICKING_UP_ITEM

        # P5: Door/wall obstruction while navigating
        if (sa.wall_ahead and sa.wall_score > 0.7 and
                sa.has_path and
                self._state == BrainState.NAVIGATING and
                state_time > 2.0):  # only if stuck for >2s
            return BrainState.TRAVERSING_DOOR

        # P6: Survey new room
        if (not sa.room_surveyed and
                sa.current_area > 0 and
                self.surveyor and
                time.time() > self._survey_cooldown and
                self.spatial.should_survey(sa.current_area, sa.pos) and
                self._state in (BrainState.NAVIGATING, BrainState.EXPLORING)):
            return BrainState.SURVEYING

        # Returning from states
        if self._state == BrainState.DEAD and sa.is_alive:
            return BrainState.EXPLORING

        if (self._state == BrainState.COMBAT and
                not sa.under_attack and sa.seconds_since_damage > 3.0):
            return BrainState.NAVIGATING

        if (self._state == BrainState.STUCK and
                not sa.is_stuck and not sa.is_recovering):
            return BrainState.NAVIGATING

        if self._state == BrainState.SURVEYING and state_time > 15.0:
            return BrainState.NAVIGATING  # timeout

        if self._state == BrainState.TRAVERSING_DOOR:
            if sa.wall_score < 0.3 or state_time > 5.0:
                return BrainState.NAVIGATING

        if (self._state == BrainState.PICKING_UP_ITEM and
                (not sa.lockable_anomaly or state_time > 5.0)):
            return BrainState.NAVIGATING

        if (self._state == BrainState.EXPLORING and
                self.commander.should_decide()):
            return BrainState.NAVIGATING

        if (self._state == BrainState.NAVIGATING and
                not sa.has_path and not self.commander.should_decide()):
            return BrainState.EXPLORING

        return self._state

    def _on_enter_state(self, state: BrainState, sa: SituationalAwareness):
        if state == BrainState.DEAD:
            self._deaths += 1
            self.ctrl.release_all()
            self.anomaly.reset()
            self.obj_tracker.reset()

        elif state == BrainState.COMBAT:
            self.bridge.fire(True)

        elif state == BrainState.STUCK:
            self._stuck_attempts += 1
            self._stucks_on_current_target += 1
            # Blacklist target after 2 stucks — move on faster
            if self._nav_target and self._stucks_on_current_target >= 2:
                self._target_failures[self._nav_target] = \
                    self._target_failures.get(self._nav_target, 0) + 1
                self._target_blacklist[self._nav_target] = time.time() + 90.0
                log.warning("Blacklisting %s for 90s (stuck %d times)",
                            self._nav_target, self._stucks_on_current_target)
                self._nav_target = None
                self._stucks_on_current_target = 0

        elif state == BrainState.EXPLORING:
            self._stuck_attempts = 0
            self.nav.path_to_random()

        elif state == BrainState.NAVIGATING:
            self._stuck_attempts = 0

    def _on_exit_state(self, state: BrainState, sa: SituationalAwareness):
        # Always release look actions to prevent stuck lookdown
        self.bridge.cmd("-lookup")
        self.bridge.cmd("-lookdown")
        self.bridge.cmd("centerview")

        if state == BrainState.COMBAT:
            self.bridge.fire(False)
            self.ctrl.strafe_left(False)
            self.ctrl.strafe_right(False)

        elif state == BrainState.SURVEYING:
            self.ctrl.center_view()

    # ── State Behaviors ───────────────────────────────────────────

    async def _tick_dead(self, sa, gs):
        if self._was_alive:
            self._was_alive = False
            log.info("DIED (#%d)", self._deaths)
        self.bridge.release_all()
        self.bridge.cmd("+attack")
        self.bridge.cmd("-attack")

    async def _tick_combat(self, sa, gs):
        self._was_alive = True

        # Snap aim toward attacker
        if sa.attacker_direction != 0 and sa.seconds_since_damage < 0.3:
            self.ctrl.turn_degrees(-sa.attacker_direction * 15)

        # Move aggressively
        self.ctrl.forward(True)
        move = self.combat_mover.get_movement(300, 'machinegun', 0.9)
        self.ctrl.strafe_left(move['strafe_left'])
        self.ctrl.strafe_right(move['strafe_right'])
        if move['jump']:
            self.ctrl.jump()

    async def _tick_stuck(self, sa, gs):
        self._was_alive = True

        def capture():
            return gs.frame

        self.nav.handle_stuck(capture_fn=capture if sa.has_frame else None)

    async def _tick_surveying(self, sa, gs):
        self._was_alive = True
        state_time = time.time() - self._state_enter_time

        # Only survey once per entry
        if state_time < 0.5 and self.surveyor and sa.pos:
            def capture():
                return gs.frame
            survey = self.surveyor.perform_survey(
                area_id=sa.current_area, pos=sa.pos,
                start_yaw=sa.yaw, capture_fn=capture,
            )
            if survey:
                self.spatial.store_survey(survey)
                log.info("SURVEY: %s | exits=%d | recommended=%s",
                         survey.room_type, len(survey.exits),
                         survey.recommended_exit)
            self._survey_cooldown = time.time() + 45.0

    async def _tick_navigating(self, sa, gs):
        self._was_alive = True
        now = time.time()

        # Commander decides target every 3s
        if self.commander.should_decide() or not sa.has_path:
            px = sa.pos[0] if sa.pos else 0
            py = sa.pos[1] if sa.pos else 0

            # Try up to 5 targets in case some are blacklisted
            for _ in range(5):
                target = self.commander.decide(
                    health=sa.health, armor=sa.armor, ammo=sa.ammo,
                    pos_x=px, pos_y=py, enemies_visible=sa.enemies_visible,
                )
                if not target:
                    break

                # Check blacklist
                bl_until = self._target_blacklist.get(target.classname, 0)
                if bl_until > now:
                    # Force commander to skip this one next time
                    target.last_visited = now
                    continue

                new_target = target.classname != self._nav_target
                self._nav_target = target.classname
                if new_target:
                    self._stucks_on_current_target = 0

                target_area = self.nav.graph.nearest_area(target.x, target.y, target.z)
                # Skip liquid targets
                if (target_area < len(self.nav.graph.areas) and
                        self.nav.graph.areas[target_area].is_liquid):
                    log.warning("Target %s in liquid — skipping", target.classname)
                    continue

                if self.nav.path_to_area(target_area):
                    break  # path found
                else:
                    log.warning("No path to %s — trying next", target.classname)
                    continue
            else:
                # All targets exhausted — explore randomly
                self._nav_target = None
                self.nav.path_to_random()

        # Move forward
        self.ctrl.forward(True)

        # Follow path
        travel_type = self.nav.follow_path()
        if travel_type is not None:
            if travel_type in (TRAVEL_JUMP, TRAVEL_JUMPPAD, TRAVEL_BARRIERJUMP,
                               TRAVEL_WALKOFFLEDGE, TRAVEL_LADDER):
                self.ctrl.jump()

        # Bunny hop
        if self._tick % 8 == 0:
            self.ctrl.jump()

        # Keep view level
        if self._tick % 12 == 0:
            self.ctrl.center_view()

        # Check arrival
        if not sa.has_path and self._nav_target:
            log.info("ARRIVED at %s", self._nav_target)
            self._items_collected += 1
            self._nav_target = None

    async def _tick_exploring(self, sa, gs):
        self._was_alive = True

        self.ctrl.forward(True)

        # Follow random path
        travel_type = self.nav.follow_path()
        if travel_type is not None:
            if travel_type in (TRAVEL_JUMP, TRAVEL_JUMPPAD, TRAVEL_BARRIERJUMP,
                               TRAVEL_WALKOFFLEDGE, TRAVEL_LADDER):
                self.ctrl.jump()

        if not sa.has_path:
            self.nav.path_to_random()

        if self._tick % 8 == 0:
            self.ctrl.jump()
        if self._tick % 12 == 0:
            self.ctrl.center_view()

    async def _tick_traversing_door(self, sa, gs):
        self._was_alive = True

        # Slow approach: walk forward briefly, check wall
        self.ctrl.forward(True)

        # If wall still ahead, try turning toward open direction
        if sa.wall_ahead:
            if sa.open_direction < 0:
                self.ctrl.turn_degrees(20)  # turn left
            elif sa.open_direction > 0:
                self.ctrl.turn_degrees(-20)  # turn right
            else:
                self.ctrl.turn_degrees(-30)  # default turn right

            self.ctrl.jump()  # try jumping in case it's a step

    async def _tick_picking_up_item(self, sa, gs):
        self._was_alive = True

        lockable = self.anomaly.get_lockable_anomaly()
        if lockable and sa.has_frame:
            # Aim toward the anomaly
            screen_w, screen_h = 800, 600
            dx = lockable.cx - screen_w // 2
            dy = lockable.cy - screen_h // 2
            self.ctrl.track_target(dx, dy, smoothing=0.4)
            self.ctrl.forward(True)

            # Identify if not yet identified
            if not lockable.identified:
                report = self.anomaly.identify_anomaly(lockable, gs.frame)
                if report:
                    log.info("PICKUP: %s (%s) — %s",
                             report.identity, report.category, report.action)
        else:
            self.ctrl.forward(True)

    # ── Utility ───────────────────────────────────────────────────

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
        try:
            state = {
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
            tmp = self.STATE_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(state, f)
            os.replace(tmp, self.STATE_FILE)
        except Exception:
            pass
