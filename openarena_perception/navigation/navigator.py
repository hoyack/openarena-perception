"""
navigator.py — AAS-based pathfinding with viewpos tracking.

Uses the same nav mesh as the built-in Q3 bots:
  - AAS areas define walkable regions
  - Reachability edges define how to travel between areas
  - Travel types: walk, jump, swim, ladder, jumppad, etc.
  - viewpos gives real-time player position + yaw

Navigation loop:
  1. viewpos -> find current AAS area
  2. A* to target area on AAS graph
  3. Follow path: turn toward next area center, move forward
  4. Handle travel types (jump when needed, etc.)
"""

from __future__ import annotations

import heapq
import logging
import math
import random
import re
import time
from typing import Callable, Dict, List, Optional, Tuple

from .aas_parser import AASGraph, parse_aas, TRAVEL_JUMP, TRAVEL_JUMPPAD, \
    TRAVEL_LADDER, TRAVEL_WALKOFFLEDGE, TRAVEL_BARRIERJUMP
from openarena_perception.game_bridge import GameBridge

log = logging.getLogger(__name__)


class Navigator:
    """AAS-powered navigator with viewpos tracking."""

    STUCK_THRESHOLD = 5.0
    STUCK_COUNT = 3  # ~0.6 seconds of no movement (faster detection)
    AREA_REACH_DIST = 200.0  # 2D distance to consider "at" an area
    POS_INTERVAL = 0.2
    YAW_SPEED = 180

    def __init__(
        self,
        bridge: GameBridge,
        aas_path: str = "",
        bsp_path: str = "",
        on_replan: Optional[Callable[[int], None]] = None,
    ):
        self.bridge = bridge
        self.graph: Optional[AASGraph] = None
        self.pos: Optional[Tuple[float, float, float]] = None
        self.yaw: float = 0.0
        self._prev_pos: Optional[Tuple[float, float, float]] = None
        self._stuck_count = 0
        self._last_query = 0.0
        self._area_stuck_counts: Dict[int, int] = {}  # area_id -> total stuck events
        self._current_area = 0
        self._path: List[int] = []

        # Learned map hooks (set by StrategicBrain)
        self._edge_cost_fn = None      # callable(from_area, to_area) -> float
        self._on_area_transition = None # callable(from_area, to_area, success)
        self._prev_area_for_learning = 0

        # Phase 12-01: verbose telemetry hooks
        self._on_replan: Optional[Callable[[int], None]] = on_replan
        self._in_replan_callback: bool = False
        self._last_swim_edge_area: Optional[int] = None
        self._last_swim_edge_time: float = 0.0

        if aas_path:
            self.graph = parse_aas(aas_path)

    def update_position(self):
        """Query viewpos via RCON."""
        now = time.time()
        if now - self._last_query < self.POS_INTERVAL:
            return
        self._last_query = now
        self._prev_pos = self.pos

        raw = self.bridge.rcon("viewpos")
        m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)\s*:\s*(-?\d+)", raw)
        if m:
            self.pos = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
            self.yaw = float(m.group(4))
            self._check_stuck()
            if self.graph:
                new_area = self.graph.nearest_area(*self.pos)
                if new_area != self._current_area:
                    # Moved to a new area -- reset stuck counter
                    if hasattr(self, '_consecutive_stuck'):
                        self._consecutive_stuck = 0
                    # Report successful edge traversal
                    if (self._on_area_transition and
                            self._prev_area_for_learning > 0):
                        self._on_area_transition(
                            self._prev_area_for_learning, new_area, True)
                    self._prev_area_for_learning = new_area
                self._current_area = new_area

    @property
    def is_stuck(self) -> bool:
        return self._stuck_count >= self.STUCK_COUNT

    @property
    def is_climbing_stairs(self) -> bool:
        """True while follow_path is inside a stair-climb commitment window.

        Set by follow_path when a vertical step is detected, cleared when the
        climb completes. Exposed for Phase 10 intent tracking (ItemTour reads
        this to fire CLIMBING_STAIRS intent transitions).
        """
        return getattr(self, "_stair_climb_active", False)

    @property
    def has_path(self) -> bool:
        return len(self._path) > 0

    @property
    def current_area(self) -> int:
        return self._current_area

    # -- Phase 12-01: verbose telemetry helpers -----------------------------

    @property
    def current_step_area(self) -> Optional[int]:
        """First area on the current path, or None if path empty."""
        return self._path[0] if self._path else None

    def note_swim_edge(self, target_area: int) -> None:
        """Record a transition into a swim-edge traversal.

        Only advances `_last_swim_edge_time` on actual area transitions so
        the timestamp-based decay is meaningful (Pitfall 8 — firing every
        tick inside the same swim branch would keep the window open forever).
        """
        if target_area != self._last_swim_edge_area:
            self._last_swim_edge_area = target_area
            self._last_swim_edge_time = time.monotonic()

    def swim_edge_state_str(self, now: Optional[float] = None) -> Optional[str]:
        """Return a human-readable swim-edge state if within the 2s window."""
        if self._last_swim_edge_area is None:
            return None
        t = now if now is not None else time.monotonic()
        if t - self._last_swim_edge_time < 2.0:
            return f"traversing to area {self._last_swim_edge_area}"
        return None

    # -- Pathfinding --------------------------------------------------------

    def path_to_area(self, target: int) -> bool:
        """A* from current area to target area."""
        if not self.graph or self._current_area == 0:
            return False
        path = self._astar(self._current_area, target)
        if path and len(path) > 1:
            self._path = path[1:]  # skip current area
            log.info("Path: %d steps from area %d to %d",
                     len(self._path), self._current_area, target)
            return True
        return False

    def path_to_random(self) -> bool:
        """Path to a random connected area for exploration."""
        if not self.graph:
            return False
        # Pick a random area that has connections
        candidates = [a.idx for a in self.graph.areas
                      if a.neighbors and a.idx != self._current_area]
        if not candidates:
            return False
        target = random.choice(candidates)
        return self.path_to_area(target)

    def follow_path(self) -> Optional[int]:
        """
        Two-phase path following (same algorithm as Q3 built-in bots):
          Phase 1: Steer toward reachability START point
          Phase 2: When close to start, steer toward reachability END point
          Advance: When close to end, pop path and move to next edge

        Uses the exact start/end vectors from the AAS reachability data,
        which define walkable paths that don't go through walls.

        Returns the travel type, or None if no path / arrived.
        """
        if not self._path or not self.pos or not self.graph:
            return None

        # Force-advance if stuck on same path step too long (15s)
        now = time.time()
        if not hasattr(self, '_path_step_start'):
            self._path_step_start = now
            self._path_step_area = self._path[0] if self._path else -1
        if self._path and self._path[0] != self._path_step_area:
            self._path_step_start = now
            self._path_step_area = self._path[0]
        elif now - self._path_step_start > 15.0 and self._path:
            log.warning("Force-advancing path (stuck on step to area %d for %.0fs)",
                        self._path[0], now - self._path_step_start)
            self._path.pop(0)
            self._path_step_start = now
            self._path_step_area = self._path[0] if self._path else -1
            if not self._path:
                return None

        target_area = self._path[0]
        current = self._current_area

        # If we drifted into an area not on the path, re-plan from here (once)
        if current not in self._path and current != 0:
            if not hasattr(self, '_last_replan_area') or self._last_replan_area != current:
                self._last_replan_area = current
                final_goal = self._path[-1]
                new_path = self._astar(current, final_goal)
                if new_path and len(new_path) > 1:
                    old_len = len(self._path)
                    self._path = new_path[1:]  # skip current area
                    log.info("Re-planned path from area %d: %d -> %d steps",
                             current, old_len, len(self._path))
                    target_area = self._path[0]
                    # Phase 12-01: fire replan hook, guarded against re-entry.
                    if self._on_replan is not None and not self._in_replan_callback:
                        self._in_replan_callback = True
                        try:
                            self._on_replan(len(self._path))
                        finally:
                            self._in_replan_callback = False

        # Find reachability edge from current area to target
        reach = None
        area = self.graph.areas[current]
        for r in area.reaches:
            if r.dest_area == target_area:
                reach = r
                break

        if reach:
            # Swim edges: allow if it's the only way
            if reach.travel_type in self.SWIM_TRAVEL:
                # Phase 12-01: record transition into swim edge (once per
                # target) so the HUD can show "traversing to area N" with a
                # 2s decay instead of filling the log every tick.
                self.note_swim_edge(target_area)
                log.warning("Traversing swim edge to area %d (may take damage!)", target_area)
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")

            # Never walk off a ledge into a liquid area (lava/water)
            if (reach.travel_type == TRAVEL_WALKOFFLEDGE and
                    target_area < len(self.graph.areas) and
                    self.graph.areas[target_area].is_liquid):
                self._path.pop(0)
                log.warning("Skipping walkoffledge into liquid area %d!", target_area)
                return None

            # Navigate using reachability START point (floor-level, not area center
            # which can be mid-air in tall areas). Fall back to END point once close.
            sx, sy, sz = reach.start
            ex, ey, ez = reach.end
            dist_start = math.hypot(sx - self.pos[0], sy - self.pos[1])
            dist_end = math.hypot(ex - self.pos[0], ey - self.pos[1])

            # Stair-climbing: spaced single jumps for ascending transitions.
            # Rapid jumping launches the bot OVER stairs. Spaced jumps (1/sec)
            # let the bot step up each stair lip then walk to the next.
            height_delta = ez - self.pos[2]
            is_ascending = height_delta > 16

            if is_ascending:
                if not hasattr(self, '_stair_climb_active') or not self._stair_climb_active:
                    self._stair_climb_active = True
                    self._stair_last_jump = 0.0
                    self.bridge.cmd("centerview")
                    log.info("Stair-climb started (height delta: %.0f)", height_delta)
                # One jump per second — not every tick
                now = time.time()
                if now - self._stair_last_jump > 1.0:
                    self.bridge.cmd("+moveup")
                    self.bridge.cmd("-moveup")
                    self._stair_last_jump = now
            else:
                if hasattr(self, '_stair_climb_active') and self._stair_climb_active:
                    self._stair_climb_active = False

            # Jump for special travel types (jumppads, barriers, ladders)
            if reach.travel_type in (TRAVEL_JUMP, TRAVEL_JUMPPAD, TRAVEL_BARRIERJUMP,
                                     TRAVEL_WALKOFFLEDGE, TRAVEL_LADDER):
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")

            # Advance if: entered target area OR close to end point
            if self._current_area == target_area or dist_end < 80:
                self._path.pop(0)
                if not self._path:
                    log.info("Reached destination (area %d)", target_area)
                    return None
                return reach.travel_type

            # Steer toward start point, then end point when close
            if dist_start > 80:
                self._steer_toward(sx, sy)
            else:
                self._steer_toward(ex, ey)
            return reach.travel_type
        else:
            # No reachability edge — use area center as fallback
            tx, ty, tz = self.graph.area_center(target_area)
            dist = math.hypot(tx - self.pos[0], ty - self.pos[1])
            if dist < self.AREA_REACH_DIST or self._current_area == target_area:
                self._path.pop(0)
                if not self._path:
                    log.info("Reached destination (area %d)", target_area)
                    return None
            else:
                self._steer_toward(tx, ty)
                if tz > self.pos[2] + 16:
                    self.bridge.cmd("+moveup")
                    self.bridge.cmd("-moveup")
            return 1

    def _steer_toward(self, tx: float, ty: float):
        """
        Closed-loop steering toward a world position.
        Turns, reads viewpos, corrects until within tolerance.
        Much more accurate than blind timed turns.
        """
        if not self.pos:
            return

        # Up to 3 correction iterations
        for iteration in range(3):
            # Re-read position for accurate yaw
            raw = self.bridge.rcon("viewpos")
            m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)\s*:\s*(-?\d+)", raw)
            if m:
                self.yaw = float(m.group(4))

            desired = math.degrees(math.atan2(ty - self.pos[1], tx - self.pos[0]))
            delta = self._yaw_diff(self.yaw, desired)

            if abs(delta) < 5:
                self.bridge.action_stop("left")
                self.bridge.action_stop("right")
                return

            # Proportional speed: small error = slow fine turn, big = fast
            speed = min(300, max(60, abs(delta) * 4))
            duration = max(0.015, abs(delta) / speed)

            self.bridge.cmd(f"cl_yawspeed {int(speed)}")
            direction = "left" if delta > 0 else "right"
            opposite = "right" if delta > 0 else "left"
            self.bridge.action_stop(opposite)
            self.bridge.action_start(direction)
            time.sleep(duration)
            self.bridge.action_stop(direction)
            time.sleep(0.03)  # settle for viewpos update

    # -- Stuck recovery -----------------------------------------------------

    def handle_stuck(self, capture_fn=None):
        """
        Smart stuck recovery with hazard detection, stair assessment, and vision-informed dodging:
          0. Check for lava/slime — if detected, back away immediately
          0.5. Check if stuck on stairs — try stair probe-and-climb
          1st attempt: vision-informed dodge (look before moving)
          2nd attempt: scan-and-probe exit finder (~4s)
          3rd+: skip waypoint and blacklist area
        """
        if not hasattr(self, '_consecutive_stuck'):
            self._consecutive_stuck = 0
        self._consecutive_stuck += 1

        # Track per-area stuck counts for A* penalty
        area = self._current_area
        self._area_stuck_counts[area] = self._area_stuck_counts.get(area, 0) + 1

        log.info("STUCK #%d at area %d (total stucks in area: %d)",
                 self._consecutive_stuck, area, self._area_stuck_counts[area])

        # Report edge failure to learned map
        if self._path and self._on_area_transition:
            self._on_area_transition(self._current_area, self._path[0], False)

        # -- Hazard check: lava/slime detection via pixels --
        if capture_fn:
            frame = capture_fn()
            if frame is not None:
                hazard = self._check_hazard(frame)
                if hazard:
                    self._stuck_count = 0
                    return

        # -- Stair detection: if target is above us, try probe-and-climb --
        if self._path and self.pos and self.graph and capture_fn:
            target_area = self._path[0]
            tc = self.graph.area_center(target_area)
            height_delta = tc[2] - self.pos[2]
            if height_delta > 20:
                try:
                    frame = capture_fn()
                    if frame is not None:
                        from .stair_navigator import StairNavigator
                        stair_nav = StairNavigator(self.bridge)
                        if stair_nav.detect_stairs_ahead(frame, self.pos[2], tc[2]):
                            log.info("Attempting stair probe-and-climb (target %.0f above)", height_delta)
                            # Find the reach start point for the ascending edge
                            reach = None
                            for r in self.graph.areas[self._current_area].reaches:
                                if r.dest_area == target_area:
                                    reach = r
                                    break
                            target_point = reach.start if reach else (tc[0], tc[1], tc[2])
                            best_yaw = stair_nav.assess_approach(
                                self.bridge, self.pos, target_point)
                            if stair_nav.climb(self.bridge, best_yaw, timeout=6.0):
                                log.info("Stair climb succeeded!")
                                self._stuck_count = 0
                                self._consecutive_stuck = 0
                                self.update_position()
                                return
                            log.info("Stair climb did not gain enough height — falling through to normal recovery")
                except Exception as e:
                    log.debug("Stair navigation failed: %s", e)

        if self._consecutive_stuck >= 4:
            # Give up on this waypoint and blacklist the area
            log.warning("Stuck %d times at area %d -- skipping waypoint (area blacklisted)",
                        self._consecutive_stuck, area)
            self._consecutive_stuck = 0
            if self._path:
                self._path.pop(0)
            self._stuck_count = 0
            return

        if self._consecutive_stuck == 1:
            # First try: vision-informed dodge (pick best direction from frame)
            if capture_fn:
                frame = capture_fn()
                if frame is not None and self._vision_dodge(frame):
                    self._stuck_count = 0
                    return
            # Fallback to blind wall dodge
            log.info("Trying wall dodge...")
            if self.wall_dodge():
                self._stuck_count = 0
                return
            self._random_unstick()
        elif self._consecutive_stuck == 2 and capture_fn:
            # Second try: scan-and-probe exit finder
            log.info("Using exit finder...")
            from .exit_finder import find_exit
            result = find_exit(self.bridge, capture_fn)
            if result:
                exit_yaw, dist = result
                log.info("Exit found at yaw=%.0f (%.0f units clear)", exit_yaw, dist)
                self._steer_toward(
                    self.pos[0] + 500 * math.cos(math.radians(exit_yaw)),
                    self.pos[1] + 500 * math.sin(math.radians(exit_yaw)),
                )
                self.bridge.move_forward(True)
                self._stuck_cleanup = ("none", "none", time.time() + 1.5)
            else:
                self._random_unstick()
        else:
            self._random_unstick()

        self._stuck_count = 0
        if self._path:
            self._path.pop(0)

    def _check_hazard(self, frame) -> bool:
        """Check for lava/slime ahead. If found, back away and reroute."""
        try:
            from openarena_perception.perception.wall_detector import Perception
            detector = Perception()
            hazard, htype, coverage = detector.detect_hazard_ahead(frame)
            if hazard:
                log.warning("HAZARD DETECTED: %s ahead (%.0f%% coverage) -- backing away!",
                            htype, coverage * 100)
                # Stop moving forward and back up briefly
                self.bridge.move_forward(False)
                self.bridge.action_start("back")
                time.sleep(0.5)
                self.bridge.action_stop("back")
                # Gentle turn (90 degrees, not 180 — less disorienting)
                self.bridge.cmd("cl_yawspeed 300")
                self.bridge.action_start("left")
                time.sleep(90 / 300)
                self.bridge.action_stop("left")
                self.bridge.move_forward(True)
                # Penalize the hazard path step (soft, not blocking)
                if self._path:
                    bad_area = self._path[0]
                    self._area_stuck_counts[bad_area] = self._area_stuck_counts.get(bad_area, 0) + 3
                    log.info("Penalized hazard area %d (stuck count now %d)",
                             bad_area, self._area_stuck_counts[bad_area])
                    self._path.pop(0)
                return True
        except Exception as e:
            log.debug("Hazard check failed: %s", e)
        return False

    def _vision_dodge(self, frame) -> bool:
        """Use frame analysis to pick the most open direction for dodging."""
        try:
            from openarena_perception.perception.wall_detector import Perception
            detector = Perception()
            left_score, center_score, right_score = detector.score_direction_openness(frame)

            # Pick the most open direction
            if center_score > left_score and center_score > right_score:
                # Center is open — maybe jump forward
                log.info("Vision dodge: center is most open (%.1f) -- jumping forward",
                         center_score)
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")
                self.bridge.move_forward(True)
                time.sleep(0.5)
                self.update_position()
                if self.pos and self._prev_pos:
                    dist = math.hypot(self.pos[0] - self._prev_pos[0],
                                      self.pos[1] - self._prev_pos[1])
                    if dist > 20:
                        log.info("Vision dodge: jump forward worked (moved %.0f)", dist)
                        return True
                return False

            # Pick the more open side
            if left_score > right_score:
                dodge_dir = "left"
                score = left_score
            else:
                dodge_dir = "right"
                score = right_score

            log.info("Vision dodge: %s is more open (%.1f vs L=%.1f C=%.1f R=%.1f)",
                     dodge_dir, score, left_score, center_score, right_score)

            # Turn toward the open direction and walk
            self.bridge.cmd("cl_yawspeed 250")
            self.bridge.action_start(dodge_dir)
            time.sleep(90 / 250)
            self.bridge.action_stop(dodge_dir)
            time.sleep(0.05)

            px0, py0 = self.pos[0], self.pos[1]
            self.bridge.cmd("+forward")
            time.sleep(0.5)
            self.bridge.cmd("-forward")
            time.sleep(0.1)

            self.update_position()
            if self.pos:
                dist = math.hypot(self.pos[0] - px0, self.pos[1] - py0)
                if dist > 20:
                    log.info("Vision dodge: %s worked (moved %.0f)", dodge_dir, dist)
                    return True

            # Turn back
            opposite = "right" if dodge_dir == "left" else "left"
            self.bridge.cmd("cl_yawspeed 250")
            self.bridge.action_start(opposite)
            time.sleep(90 / 250)
            self.bridge.action_stop(opposite)
            time.sleep(0.05)

        except Exception as e:
            log.debug("Vision dodge failed: %s", e)
        return False

    def area_stuck_penalty(self, area: int) -> float:
        """A* cost penalty for areas where the bot repeatedly gets stuck.
        Soft penalties only — never fully block (may be the only route)."""
        count = self._area_stuck_counts.get(area, 0)
        if count == 0:
            return 0.0
        # Soft cap at 2000 — expensive but not blocking
        return min(count * 300.0, 2000.0)

    def reset_stuck_penalties(self):
        """Clear stuck penalties when retrying with fresh routes."""
        if self._area_stuck_counts:
            log.info("Resetting %d area stuck penalties for fresh pathfinding",
                     len(self._area_stuck_counts))
            self._area_stuck_counts.clear()

    def path_to_area_fresh(self, target: int) -> bool:
        """Try pathfinding with cleared penalties — last resort when normal path fails."""
        self.reset_stuck_penalties()
        return self.path_to_area(target)

    def explore_toward(self, target_x: float, target_y: float) -> bool:
        """Navigate toward a world position by picking the nearest reachable area
        in that general direction. Used when direct A* fails."""
        if not self.graph or not self.pos:
            return False

        best_area = -1
        best_score = float('inf')
        tx, ty = target_x, target_y
        cx, cy = self.pos[0], self.pos[1]

        for area in self.graph.areas:
            if not area.neighbors or area.idx == self._current_area:
                continue
            ax, ay, az = area.cx, area.cy, area.cz
            # Score = distance from area to target (prefer closer to target)
            # with bonus for being reachable from current position
            dist_to_target = math.hypot(ax - tx, ay - ty)
            dist_from_us = math.hypot(ax - cx, ay - cy)
            # Only consider areas that are closer to target than we are
            our_dist = math.hypot(cx - tx, cy - ty)
            if dist_to_target < our_dist:
                score = dist_to_target + dist_from_us * 0.3
                if score < best_score:
                    # Quick check: can we path there?
                    test_path = self._astar(self._current_area, area.idx)
                    if test_path:
                        best_score = score
                        best_area = area.idx

        if best_area >= 0:
            log.info("Exploring toward (%.0f,%.0f) via area %d (score=%.0f)",
                     tx, ty, best_area, best_score)
            return self.path_to_area(best_area)
        return False

    def wall_dodge(self):
        """
        Quick wall avoidance: try 90 deg left, if blocked try 90 deg right.
        Returns True if we found an open direction.
        """
        if not self.pos:
            return False

        for try_dir in ["left", "right"]:
            # Turn 90 degrees
            self.bridge.cmd("cl_yawspeed 250")
            self.bridge.action_start(try_dir)
            time.sleep(90 / 250)
            self.bridge.action_stop(try_dir)
            time.sleep(0.05)

            # Walk forward briefly
            px0, py0 = self.pos[0], self.pos[1]
            self.bridge.cmd("+forward")
            time.sleep(0.4)
            self.bridge.cmd("-forward")
            time.sleep(0.1)

            # Check if we moved
            self.update_position()
            if self.pos:
                dist = math.hypot(self.pos[0] - px0, self.pos[1] - py0)
                if dist > 20:
                    log.info("Wall dodge: %s worked (moved %.0f)", try_dir, dist)
                    return True

            # Didn't move -- turn back and try other direction
            opposite = "right" if try_dir == "left" else "left"
            self.bridge.cmd("cl_yawspeed 250")
            self.bridge.action_start(opposite)
            time.sleep(90 / 250)
            self.bridge.action_stop(opposite)
            time.sleep(0.05)

        return False

    def _random_unstick(self):
        """Quick random jump + strafe + turn recovery."""
        near_stairs = False
        if self._path and self.pos and self.graph:
            target = self._path[0]
            tc = self.graph.area_center(target)
            near_stairs = abs(tc[2] - self.pos[2]) > 16

        if near_stairs:
            self.bridge.move_forward(True)
            strafe_dir = random.choice(["moveleft", "moveright"])
            self.bridge.action_start(strafe_dir)
            for _ in range(3):
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")
                time.sleep(0.15)
            self._stuck_cleanup = ("none", strafe_dir, time.time() + 0.8)
        else:
            self.bridge.move_forward(False)
            self.bridge.action_start("back")
            strafe_dir = random.choice(["moveleft", "moveright"])
            self.bridge.action_start(strafe_dir)
            turn_dir = random.choice(["left", "right"])
            self.bridge.cmd("cl_yawspeed 350")
            self.bridge.action_start(turn_dir)
            self.bridge.cmd("+moveup")
            self.bridge.cmd("-moveup")
            self._stuck_cleanup = (turn_dir, strafe_dir, time.time() + 1.2)

    def check_stuck_cleanup(self):
        """Call each tick to clean up stuck recovery actions."""
        if hasattr(self, '_stuck_cleanup') and self._stuck_cleanup:
            turn_dir, strafe_dir, end_time = self._stuck_cleanup
            if time.time() >= end_time:
                if turn_dir != "none":
                    self.bridge.action_stop(turn_dir)
                self.bridge.action_stop(strafe_dir)
                self.bridge.action_stop("back")
                self.bridge.move_forward(True)
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")
                self._stuck_cleanup = None

    @property
    def is_recovering(self) -> bool:
        return hasattr(self, '_stuck_cleanup') and self._stuck_cleanup is not None

    # -- Status -------------------------------------------------------------

    def get_status(self) -> str:
        pos_str = f"({self.pos[0]:.0f},{self.pos[1]:.0f})" if self.pos else "?"
        area_str = f"a={self._current_area}" if self.graph else ""
        path_str = f" path={len(self._path)}" if self._path else ""
        stuck = " STUCK" if self.is_stuck else ""
        n_areas = self.graph.num_areas if self.graph else 0
        return f"pos={pos_str} y={self.yaw:.0f} {area_str}/{n_areas}{path_str}{stuck}"

    # -- Internal -----------------------------------------------------------

    def _astar_allow_swim(self, start: int, goal: int) -> List[int]:
        """A* that ALLOWS swim edges (for deliberate swim missions)."""
        if start == goal:
            return [goal]
        if not self.graph:
            return []

        open_set = [(0.0, start)]
        came_from: Dict[int, int] = {}
        g_score: Dict[int, float] = {start: 0.0}
        gx, gy, gz = self.graph.area_center(goal)

        while open_set:
            _, cur = heapq.heappop(open_set)
            if cur == goal:
                path = [cur]
                while cur in came_from:
                    cur = came_from[cur]
                    path.append(cur)
                path.reverse()
                return path

            area = self.graph.areas[cur]
            for i, nb in enumerate(area.neighbors):
                nx, ny, nz = self.graph.area_center(nb)
                cx, cy, cz = self.graph.area_center(cur)
                d = math.hypot(nx-cx, ny-cy) + abs(nz-cz) * 0.3
                tentative = g_score[cur] + d
                if tentative < g_score.get(nb, float('inf')):
                    came_from[nb] = cur
                    g_score[nb] = tentative
                    h = math.hypot(nx-gx, ny-gy) + abs(nz-gz) * 0.3
                    heapq.heappush(open_set, (tentative + h, nb))

        return []

    @staticmethod
    def _yaw_diff(current: float, target: float) -> float:
        """Signed yaw difference. Positive = turn left."""
        return (target - current + 180) % 360 - 180

    def _check_stuck(self):
        if self._prev_pos and self.pos:
            d = math.hypot(self.pos[0]-self._prev_pos[0], self.pos[1]-self._prev_pos[1])
            if d < self.STUCK_THRESHOLD:
                self._stuck_count += 1
            else:
                self._stuck_count = 0

    # Travel types that require ground movement (preferred)
    GROUND_TRAVEL = {1, 2, 3, 4, 5, 6, 17}  # walk, crouch, barrierjump, jump, ladder, walkoffledge, jumppad
    SWIM_TRAVEL = {7, 8}  # swim, waterjump
    SWIM_PENALTY = 5000.0  # expensive but not blocked — swim edges may be the only route out

    def _astar(self, start: int, goal: int) -> List[int]:
        if start == goal:
            return [goal]
        if not self.graph:
            return []

        open_set = [(0.0, start)]
        came_from: Dict[int, int] = {}
        g_score: Dict[int, float] = {start: 0.0}
        gx, gy, gz = self.graph.area_center(goal)

        while open_set:
            _, cur = heapq.heappop(open_set)
            if cur == goal:
                path = [cur]
                while cur in came_from:
                    cur = came_from[cur]
                    path.append(cur)
                path.reverse()
                return path

            area = self.graph.areas[cur]
            for i, nb in enumerate(area.neighbors):
                nx, ny, nz = self.graph.area_center(nb)
                cx, cy, cz = self.graph.area_center(cur)
                d = math.hypot(nx-cx, ny-cy) + abs(nz-cz) * 0.3

                # Penalize swim paths heavily (lava/slime) but don't block —
                # they may be the only route out of dead-end areas
                ttype = area.travel_types[i] if i < len(area.travel_types) else 1
                if ttype in self.SWIM_TRAVEL:
                    d += self.SWIM_PENALTY

                # Add learned edge penalty (avoid repeatedly failed edges)
                if self._edge_cost_fn:
                    d += self._edge_cost_fn(cur, nb)

                # Add area stuck penalty (avoid areas where bot repeatedly gets stuck)
                d += self.area_stuck_penalty(nb)

                tentative = g_score[cur] + d
                if tentative < g_score.get(nb, float('inf')):
                    came_from[nb] = cur
                    g_score[nb] = tentative
                    h = math.hypot(nx-gx, ny-gy) + abs(nz-gz) * 0.3
                    heapq.heappush(open_set, (tentative + h, nb))

        return []
