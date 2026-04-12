"""
reactive_agent.py — AAS-navigating bot with item-targeted pathfinding.

Can be told "go get the rocket launcher" and will A* to it on the AAS graph.
"""

from __future__ import annotations

import logging
import re
import struct
import subprocess
import time
from typing import Dict, List, Optional, Tuple

from .aas_parser import TRAVEL_JUMP, TRAVEL_JUMPPAD, TRAVEL_BARRIERJUMP, \
    TRAVEL_WALKOFFLEDGE, TRAVEL_LADDER
from .combat import select_weapon, evaluate_threat, CombatMover, WEAPONS
from .commander import Commander
from .damage_tracker import DamageTracker
from .game_bridge import GameBridge
from .game_state import GameState
from .motion_detector import MotionDetector
from .player_detector import PlayerDetector
from .navigator import Navigator
from .perception import Perception

log = logging.getLogger(__name__)


class ReactiveAgent:

    def __init__(self, bridge: GameBridge, window_id: str = "",
                 aas_path: str = "", bsp_path: str = ""):
        self.bridge = bridge
        self.nav = Navigator(bridge, aas_path=aas_path)
        self.window_id = window_id
        self.combat_enabled = True  # combat is ON
        self.combat_mover = CombatMover()

        from pynput.mouse import Controller as MouseController
        self.mouse = MouseController()

        # Map items + commander
        self.items: List[Tuple[str, float, float, float]] = []
        if bsp_path:
            self._load_items(bsp_path)
        # Filter items to only dry-reachable ones
        dry_items = self._filter_dry_items() if aas_path else self.items
        self.cmd = Commander(dry_items)
        self.perception = Perception()
        self.motion = MotionDetector()
        self.player_det = PlayerDetector()
        self.damage = DamageTracker()

        self._tick = 0
        self._firing = False
        self._last_jump = 0.0
        self._last_steer = 0.0
        self._last_cmd_decision = 0.0
        self._last_refocus = 0.0
        self._target_item: Optional[str] = None
        self._manual_target = False
        self._was_alive = True
        self._swim_mission = False   # True = deliberately underwater, don't panic
        self._swim_exit_area = None  # dry area to return to after swim mission
        self._swim_item_reached = False

    def init_game(self):
        self.bridge.cmd("centerview")
        time.sleep(0.1)
        self.nav.update_position()
        if self.nav.pos:
            log.info("Init: pos=%s area=%d/%d, %d items on map",
                     self.nav.pos, self.nav.current_area,
                     self.nav.graph.num_areas if self.nav.graph else 0,
                     len(self.items))

    # ── Item navigation ────────────────────────────────────────────────

    def goto_item(self, item_keyword: str, manual: bool = False) -> bool:
        """
        Navigate to a specific item by keyword match.
        If manual=True, commander won't override this target.
        """
        keyword = item_keyword.lower()
        self._manual_target = manual
        if not self.nav.graph or not self.nav.pos:
            log.warning("Cannot navigate: no graph or no position")
            return False

        # Find matching items
        matches = [(name, x, y, z) for name, x, y, z in self.items
                    if keyword in name.lower()]
        if not matches:
            log.warning("No item matching '%s' found on map", keyword)
            return False

        # Sort by distance
        px, py, pz = self.nav.pos
        matches.sort(key=lambda m: (m[1]-px)**2 + (m[2]-py)**2)
        name, ix, iy, iz = matches[0]

        # Find nearest AAS area to the item
        target_area = self.nav.graph.nearest_area(ix, iy, iz)
        tc = self.nav.graph.area_center(target_area)

        log.info("Navigating to %s at (%.0f,%.0f,%.0f) → area %d (%.0f,%.0f,%.0f)",
                 name, ix, iy, iz, target_area, tc[0], tc[1], tc[2])

        self._target_item = name
        return self.nav.path_to_area(target_area)

    def goto_item_direct(self, classname: str, x: float, y: float, z: float) -> bool:
        """Navigate to a specific item by its coordinates."""
        if not self.nav.graph or not self.nav.pos:
            return False
        target_area = self.nav.graph.nearest_area(x, y, z)
        self._target_item = classname
        return self.nav.path_to_area(target_area)

    def goto_explore(self) -> bool:
        """Navigate to a random area."""
        self._target_item = None
        return self.nav.path_to_random()

    # ── Tick ───────────────────────────────────────────────────────────

    def tick(self, gs: GameState):
        now = time.perf_counter()
        self._tick += 1

        # Refocus window
        if now - self._last_refocus > 15.0:
            self._focus_game()
            self._last_refocus = now

        # Update position
        self.nav.update_position()

        # Stuck cleanup (non-blocking)
        self.nav.check_stuck_cleanup()

        # Dead?
        if gs.health is not None and gs.health <= 0:
            self._handle_dead()
            return

        # === WATER HANDLING ===
        in_water = self._is_in_water()
        if in_water:
            if self._swim_mission:
                self._handle_swim_mission(gs)
            else:
                self._handle_water_panic(gs)
            return
        else:
            # Exited water — release swim-up, end swim mission
            self.bridge.cmd("-moveup")
            if self._swim_mission:
                log.info("Exited water! Swim mission complete.")
                self._swim_mission = False
                self._swim_item_reached = False

        # Recovering from stuck? Don't interfere
        if self.nav.is_recovering:
            return

        # Keep view level (not during recovery)
        if self._tick % 8 == 0:
            self.bridge.cmd("centerview")

        # Stuck?
        if self.nav.is_stuck:
            self.nav.handle_stuck()
            return

        # We're alive
        self._was_alive = True

        # === COMBAT: only when taking damage (guarantees enemy is near) ===
        under_attack = self.damage.update(gs.health, gs.frame)

        if under_attack and self.combat_enabled:
            # We're being shot — fire back, dodge, charge
            if not self._firing:
                self.bridge.fire(True)
                self._firing = True

            # Snap toward damage direction
            direction = self.damage.attacker_direction
            if direction != 0 and self.damage.seconds_since_damage < 0.3:
                self.mouse.move(direction * 50, 0)

            # Dodge: strafe + jump
            self.bridge.move_forward(True)
            move = self.combat_mover.get_movement(300, 'machinegun', 0.9)
            self.bridge.strafe_left(move['strafe_left'])
            self.bridge.strafe_right(move['strafe_right'])
            if move['jump']:
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")
            return  # combat takes priority over navigation
        else:
            # No enemies — stop firing, navigate
            if self._firing:
                self.bridge.fire(False)
                self._firing = False
            # Stop combat strafing
            self.bridge.strafe_left(False)
            self.bridge.strafe_right(False)

            # Wall detection
            wall_ahead = False
            if gs.frame is not None:
                wall_ahead, _, open_dir = self.perception.detect_wall_ahead(gs.frame)

            if wall_ahead:
                self.bridge.move_forward(False)
                if open_dir < 0:
                    self.bridge.cmd("cl_yawspeed 200")
                    self.bridge.action_start("left")
                    self.bridge.action_stop("right")
                elif open_dir > 0:
                    self.bridge.cmd("cl_yawspeed 200")
                    self.bridge.action_start("right")
                    self.bridge.action_stop("left")
                else:
                    self.bridge.cmd("cl_yawspeed 300")
                    self.bridge.action_start("right")
                    self.bridge.action_stop("left")
            else:
                self.bridge.move_forward(True)
                self.bridge.move_back(False)
                self.bridge.action_stop("left")
                self.bridge.action_stop("right")
                self._do_navigate(gs, now)

    # ── Combat (motion-based) ──────────────────────────────────────────

    def _do_combat_motion(self, targets, now: float, screen_cx: int):
        """Combat: aim at largest moving target, fire, charge forward."""
        target = targets[0]  # largest
        x1, y1, x2, y2, conf = target
        cx = (x1 + x2) // 2
        target_w = x2 - x1
        target_h = y2 - y1

        # AIM at target center with mouse
        dx = cx - screen_cx
        if abs(dx) > 50:
            mouse_dx = int(dx * 0.45)
        elif abs(dx) > 15:
            mouse_dx = int(dx * 0.3)
        else:
            mouse_dx = int(dx * 0.15)
        mouse_dx = max(-80, min(80, mouse_dx))
        if abs(mouse_dx) > 1:
            self.mouse.move(mouse_dx, 0)

        # FIRE — always fire when motion detected (spray and pray)
        if not self._firing:
            self.bridge.fire(True)
            self._firing = True

        # CHARGE FORWARD to close distance + strafe to dodge
        self.bridge.move_forward(True)
        move = self.combat_mover.get_movement(
            enemy_distance=500, weapon='machinegun', skill=0.8)
        self.bridge.strafe_left(move['strafe_left'])
        self.bridge.strafe_right(move['strafe_right'])
        if move['jump']:
            self.bridge.cmd("+moveup")
            self.bridge.cmd("-moveup")

    def _do_navigate(self, gs: GameState, now: float):
        """Strategic navigation via commander + path following."""
        # Commander decides what to go after (unless manual target is set)
        if not self._manual_target and (self.cmd.should_decide() or not self.nav.has_path):
            px = self.nav.pos[0] if self.nav.pos else 0
            py = self.nav.pos[1] if self.nav.pos else 0
            enemies = len(gs.enemies) if gs.enemies else 0
            target = self.cmd.decide(
                health=gs.health, armor=gs.armor, ammo=gs.ammo,
                pos_x=px, pos_y=py, enemies_visible=enemies,
            )
            if target:
                self.goto_item_direct(target.classname, target.x, target.y, target.z)
            else:
                self.goto_explore()
        elif not self.nav.has_path:
            # Manual target reached — clear manual mode
            self._manual_target = False

        # Steer every tick for responsive navigation
        travel_type = self.nav.follow_path()
        if travel_type is not None:
            if travel_type in (TRAVEL_JUMP, TRAVEL_JUMPPAD, TRAVEL_BARRIERJUMP,
                                TRAVEL_WALKOFFLEDGE):
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")
                self._last_jump = now
            elif travel_type == TRAVEL_LADDER:
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")

        # Bunny hop for speed
        if now - self._last_jump > 0.6:
            self.bridge.cmd("+moveup")
            self.bridge.cmd("-moveup")
            self._last_jump = now

    # ── Dead ───────────────────────────────────────────────────────────

    def _handle_dead(self):
        if self._was_alive:
            self.cmd.record_death()
            self._was_alive = False
            self.motion.reset_background()
            self.player_det.reset()
            log.info("DIED! Deaths: %d", self.cmd._deaths)
        self.bridge.release_all()
        self.bridge.cmd("centerview")
        self.bridge.cmd("cl_yawspeed 140")
        self.bridge.cmd("+attack")
        self.bridge.cmd("-attack")

    def _is_scoreboard(self, frame) -> bool:
        import cv2
        h, w = frame.shape[:2]
        center = frame[h//4:3*h//4, w//4:3*w//4]
        gray = cv2.cvtColor(center, cv2.COLOR_BGR2GRAY)
        bright = cv2.countNonZero(cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY)[1])
        return (bright / (center.shape[0] * center.shape[1])) < 0.08

    # ── Util ───────────────────────────────────────────────────────────

    def _focus_game(self):
        if self.window_id:
            try:
                subprocess.run(
                    ["xdotool", "windowactivate", self.window_id],
                    capture_output=True, timeout=1,
                    env={"DISPLAY": ":0", "PATH": "/usr/bin:/bin"})
            except Exception:
                pass

    def _load_items(self, bsp_path: str):
        """Extract item positions from BSP entities."""
        try:
            with open(bsp_path, "rb") as f:
                f.read(4); f.read(4)
                ent_ofs = struct.unpack("<i", f.read(4))[0]
                ent_len = struct.unpack("<i", f.read(4))[0]
                f.seek(ent_ofs)
                raw = f.read(ent_len).decode("ascii", errors="replace")

            for block in raw.split("}"):
                cn = re.search(r'"classname"\s+"([^"]+)"', block)
                origin = re.search(r'"origin"\s+"([^"]+)"', block)
                if cn and origin:
                    name = cn.group(1)
                    parts = origin.group(1).split()
                    if len(parts) == 3 and any(k in name for k in
                            ["weapon", "health", "armor", "ammo", "item_"]):
                        self.items.append((
                            name, float(parts[0]), float(parts[1]), float(parts[2])
                        ))
            log.info("Loaded %d map items from BSP", len(self.items))
        except Exception as e:
            log.warning("Failed to load BSP items: %s", e)

    def _is_in_water(self) -> bool:
        """Check if the player is in water via AAS area flag or frame tint."""
        if self.nav.graph and self.nav.pos:
            area = self.nav.graph.areas[self.nav.current_area]
            if area.is_liquid:
                return True
        return False

    def start_swim_mission(self, item_keyword: str) -> bool:
        """Start a deliberate swim mission to grab an underwater item."""
        keyword = item_keyword.lower()
        matches = [(n,x,y,z) for n,x,y,z in self.items if keyword in n.lower()]
        if not matches:
            log.warning("No item matching '%s' for swim mission", keyword)
            return False

        name, ix, iy, iz = matches[0]

        # Remember where we are now so we can return
        if self.nav.pos:
            self._swim_exit_area = self._find_nearest_dry_area()

        # Use full A* (including swim edges) for this path
        target_area = self.nav.graph.nearest_area(ix, iy, iz)
        path = self.nav._astar_allow_swim(self.nav.current_area, target_area)
        if path:
            self.nav._path = path[1:]
            self._swim_mission = True
            self._swim_item_reached = False
            self._target_item = name
            self._manual_target = True
            log.info("SWIM MISSION: %s at (%.0f,%.0f,%.0f) → %d steps",
                     name, ix, iy, iz, len(path))
            return True
        log.warning("No path to underwater item %s", name)
        return False

    def _handle_swim_mission(self, gs: GameState):
        """Deliberate underwater navigation — follow path, grab item, get out."""
        # Health check — abort if about to die
        if gs.health is not None and gs.health < 20:
            log.warning("SWIM ABORT — health critical (%d)! Surfacing!", gs.health)
            self._swim_mission = False
            self._handle_water_panic(gs)
            return

        # Keep swimming (hold +moveup to stay near surface / navigate)
        self.bridge.move_forward(True)

        if self.nav.has_path:
            # Follow the swim path
            travel_type = self.nav.follow_path()
            # Swim movement: use +moveup to go up, let gravity pull down
            if travel_type == 7:  # SWIM
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")
        else:
            # Path complete — item should be collected
            if not self._swim_item_reached:
                self._swim_item_reached = True
                log.info("SWIM: Reached item area! Heading for exit.")

            # Now navigate back to the exit (dry area)
            if self._swim_exit_area is not None:
                path = self.nav._astar_allow_swim(self.nav.current_area, self._swim_exit_area)
                if path:
                    self.nav._path = path[1:]
                else:
                    # Can't pathfind out — just swim up
                    self.bridge.cmd("+moveup")
            else:
                # No exit recorded — just swim up
                self.bridge.cmd("+moveup")

    def _handle_water_panic(self, gs: GameState):
        """
        EMERGENCY: We're in water. Swim UP hard and move forward.
        Don't try to pathfind — just get out by going up.
        In Q3, water surfaces are always above you when submerged.
        """
        if self._tick % 20 == 0:
            log.warning("IN WATER at area %d! Swimming UP!", self.nav.current_area)

        # SWIM UP — hold +moveup constantly while in water
        self.bridge.cmd("+moveup")

        # Move forward to find the edge of the water
        self.bridge.move_forward(True)

        # Steer toward nearest dry area (by XY only)
        if self.nav.graph and self.nav.pos:
            dry_area = self._find_nearest_dry_area()
            if dry_area is not None:
                tx, ty, _ = self.nav.graph.area_center(dry_area)
                self.nav._steer_toward(tx, ty)

        # DON'T release +moveup here — keep swimming up every tick
        # It will be released when we exit water (_is_in_water returns False)

    def _find_nearest_dry_area(self) -> int:
        """Find the closest non-liquid area by distance."""
        if not self.nav.graph or not self.nav.pos:
            return None
        import math
        best = None
        best_dist = float('inf')
        px, py, pz = self.nav.pos
        for a in self.nav.graph.areas:
            if a.idx == 0 or a.is_liquid:
                continue
            d = math.hypot(a.cx - px, a.cy - py)
            if d < best_dist:
                best_dist = d
                best = a.idx
        return best

    def _filter_dry_items(self) -> list:
        """Filter items to only those reachable without swimming from current position."""
        if not self.nav.graph:
            return self.items
        SWIM = {7, 8}
        # Start BFS from current area (or area 1 if unknown)
        start = self.nav.current_area if self.nav.current_area > 0 else 1
        dry = set()
        queue = [start]
        dry.add(start)
        while queue:
            cur = queue.pop(0)
            a = self.nav.graph.areas[cur]
            for i, nb in enumerate(a.neighbors):
                tt = a.travel_types[i] if i < len(a.travel_types) else 1
                if tt not in SWIM and nb not in dry:
                    dry.add(nb)
                    queue.append(nb)
        result = []
        for name, x, y, z in self.items:
            nearest = self.nav.graph.nearest_area(x, y, z)
            if nearest in dry:
                result.append((name, x, y, z))
        log.info("Dry-reachable items: %d / %d", len(result), len(self.items))
        return result

    def shutdown(self):
        self.bridge.stop_firing()
        self.bridge.stop_movement()
        self.bridge.release_all()

    def get_status(self) -> str:
        target = f" →{self._target_item}" if self._target_item else ""
        wall = f" WALL={self.perception.wall_score:.1f}" if self.perception.wall_score > 0.3 else ""
        fire = " FIRE" if self._firing else ""
        mt = len(self.motion._last_detections) if hasattr(self.motion, '_last_detections') else 0
        motion = f" tgt={mt}" if mt > 0 else ""
        return f"{self.cmd.get_status()} {self.nav.get_status()}{target}{wall}{fire}{motion}"
