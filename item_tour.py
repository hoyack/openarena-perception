#!/usr/bin/env python3
"""
item_tour.py — Vision-assisted navigation through all weapons and powerups.

Combines AAS pathfinding (global routing) with vision LLM (local obstacle
handling). Gemma4 is queried every ~2.5s to identify stairs, doorways,
corridors, and obstacles that pure pathfinding misses.

Usage:
    python item_tour.py                 # tour all weapons + powerups
    python item_tour.py --all           # tour ALL items (including ammo/shards)
    python item_tour.py --loop          # loop forever
    python item_tour.py --no-vision     # AAS-only (no LLM)
    python item_tour.py --category weapon  # only weapons
"""

import argparse
import asyncio
import atexit
import base64
import json
import logging
import math
import os
import signal
import subprocess
import sys
import time
import urllib.request

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from openarena_perception import build_config, PerceptionLoop, GameState
from openarena_perception.game_bridge import GameBridge
from openarena_perception.reactive_agent import ReactiveAgent
from openarena_perception.room_surveyor import RoomSurveyor
from openarena_perception.motion_anomaly import MotionAnomalyTracker
from openarena_perception.aas_parser import (
    TRAVEL_JUMP, TRAVEL_JUMPPAD, TRAVEL_BARRIERJUMP,
    TRAVEL_WALKOFFLEDGE, TRAVEL_LADDER,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("tour")

# Items worth visiting (excluding small ammo/shards unless --all)
PRIORITY_PREFIXES = [
    "weapon_",
    "item_quad",
    "item_invis",
    "item_haste",
    "item_regen",
    "item_health_mega",
    "item_health_large",
    "item_armor_body",
    "item_armor_combat",
]

# Vision navigation prompt
VISION_NAV_PROMPT = """\
You are guiding a bot navigating a Quake 3 arena map. Analyze this first-person screenshot.

Identify:
1. What is directly ahead (open corridor, wall, stairs going up/down, doorway, ledge, ramp)
2. Are there stairs? If so, describe their position (left/center/right) and direction (up/down)
3. Is there a clear path forward or is the bot blocked?

Respond with ONLY a JSON object:
{
  "ahead": "open" | "wall" | "stairs_up" | "stairs_down" | "doorway" | "ledge" | "ramp" | "blocked",
  "stairs_position": "left" | "center" | "right" | "none",
  "blocked": true/false,
  "open_left": true/false,
  "open_right": true/false,
  "action": "forward" | "slight_left" | "slight_right" | "turn_left" | "turn_right" | "turn_around" | "jump_forward" | "walk_up_stairs",
  "reason": "1 sentence"
}

The bottom of the screen shows HUD (health/ammo numbers) — ignore it.\
"""

VISION_STUCK_PROMPT = """\
You are guiding a bot that is STUCK in a Quake 3 arena map.

Look at this screenshot and tell me:
1. WHY is the bot stuck? (wall, bars, railing, edge of stairs, corner, pit)
2. Which direction should it go to get unstuck?

Respond with ONLY a JSON object:
{
  "obstacle": "description of what's blocking",
  "action": "turn_left" | "turn_right" | "turn_around" | "jump_forward" | "back_up" | "strafe_left" | "strafe_right",
  "reason": "1 sentence"
}
\
"""


# ── Helpers ──────────────────────────────────────────────────────────

def nearest_neighbor_route(items, start_pos):
    """Greedy nearest-neighbor TSP approximation."""
    remaining = list(items)
    route = []
    cx, cy = start_pos
    while remaining:
        best_idx = min(range(len(remaining)),
                       key=lambda i: math.hypot(remaining[i][1]-cx, remaining[i][2]-cy))
        item = remaining.pop(best_idx)
        route.append(item)
        cx, cy = item[1], item[2]
    return route


def focus_game_window() -> str:
    """Focus ioquake3 window, return window ID."""
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
                return wid
    except Exception:
        pass
    return ""


# ── Vision Helper ────────────────────────────────────────────────────

class VisionHelper:
    """Throttled vision LLM queries for navigation."""

    QUERY_INTERVAL = 3.0   # seconds between nav queries
    STUCK_INTERVAL = 4.0   # seconds between stuck queries
    OLLAMA_URL = "http://localhost:11434/api/generate"
    MODEL = "gemma4:31b-cloud"

    def __init__(self):
        self._last_query_time = 0.0
        self._pending = False
        self._last_action = None
        self._query_count = 0

    def should_query(self) -> bool:
        return (not self._pending and
                time.time() - self._last_query_time >= self.QUERY_INTERVAL)

    def can_stuck_query(self) -> bool:
        return (not self._pending and
                time.time() - self._last_query_time >= self.STUCK_INTERVAL)

    async def query_navigation(self, frame: np.ndarray) -> dict:
        if self._pending:
            return {"action": "forward", "reason": "busy"}
        self._pending = True
        self._last_query_time = time.time()
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, self._call_ollama, frame, VISION_NAV_PROMPT)
            self._last_action = result.get("action", "forward")
            self._query_count += 1
            return result
        except Exception as e:
            log.warning("Vision nav failed: %s", e)
            return {"action": "forward", "reason": str(e)}
        finally:
            self._pending = False

    async def query_stuck(self, frame: np.ndarray) -> dict:
        if self._pending:
            return {"action": "turn_around", "reason": "busy"}
        self._pending = True
        self._last_query_time = time.time()
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, self._call_ollama, frame, VISION_STUCK_PROMPT)
            self._query_count += 1
            return result
        except Exception as e:
            log.warning("Vision stuck failed: %s", e)
            return {"action": "turn_around", "reason": str(e)}
        finally:
            self._pending = False

    def _call_ollama(self, frame: np.ndarray, prompt: str) -> dict:
        h, w = frame.shape[:2]
        scale = min(1.0, 512 / max(h, w))
        if scale < 1.0:
            small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        else:
            small = frame
        _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 55])
        b64 = base64.b64encode(buf).decode()

        data = json.dumps({
            "model": self.MODEL, "prompt": prompt, "images": [b64],
            "stream": False,
            "options": {"num_predict": 150, "temperature": 0.1},
        }).encode()

        req = urllib.request.Request(
            self.OLLAMA_URL, data=data,
            headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=8)
        result = json.loads(resp.read())
        text = result.get("response", "{}").strip()

        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            log.warning("Vision non-JSON: %s", text[:80])
            return {"action": "forward", "reason": "parse error"}


# ── Item Tour ────────────────────────────────────────────────────────

class ItemTour:

    def __init__(self, args):
        self.args = args
        self.cfg = build_config(resolution="800x600", enemy_color_mode="red")

        self.bridge = GameBridge(rcon_password=args.rcon_password)
        self.bridge.open()

        status = self.bridge.get_status()
        map_name = status.map_name or "oa_dm1"
        log.info("Map: %s, Players: %d", map_name, len(status.players))

        maps_dir = os.path.join(os.path.dirname(__file__), "maps")
        aas_path = os.path.join(maps_dir, f"{map_name}.aas")
        bsp_path = os.path.join(maps_dir, f"{map_name}.bsp")

        self.agent = ReactiveAgent(self.bridge, aas_path=aas_path, bsp_path=bsp_path)
        self.agent.combat_enabled = False
        self.bridge.close()

        # Learned map — tracks walls, edge failures, occupancy grid
        from openarena_perception.navigation.learned_map import LearnedMap
        self.learned_map = LearnedMap(map_name=map_name, aas_graph=self.agent.nav.graph)
        self.learned_map.load()
        # Wire edge cost penalty into navigator's A*
        self.agent.nav._edge_cost_fn = self.learned_map.edge_penalty
        # Wire edge success/failure callbacks
        def on_area_transition(from_area, to_area, success):
            if success:
                self.learned_map.record_edge_success(from_area, to_area)
            else:
                self.learned_map.record_edge_failure(from_area, to_area)
        self.agent.nav._on_area_transition = on_area_transition
        log.info("Learned map loaded: %s", self.learned_map.map_name)

        # Spatial advisor — async LLM loop for hazard detection and guidance
        from openarena_perception.strategy.advisor import SpatialAdvisor
        self.advisor = SpatialAdvisor()
        if self.advisor.enabled:
            log.info("Spatial advisor enabled (model=%s)", self.advisor.model)
        else:
            log.warning("Spatial advisor disabled (ollama unavailable)")

        # Subsystems
        use_vision = not args.no_vision
        self.vision = VisionHelper() if use_vision else None
        self.surveyor = RoomSurveyor(self.bridge) if use_vision else None
        self.anomaly = MotionAnomalyTracker() if use_vision else None

        # Tour state — items selected after init_game when position is known
        self.tour_items = []
        self._route = []
        self._route_idx = 0
        self._tours_done = 0
        self._stuck_attempts = 0
        self._max_stuck_before_skip = 4
        self._item_start_time = 0.0       # when we started navigating to current item
        self._item_timeout = 90.0         # skip item after 90 seconds of trying

        # Vision state
        self._vision_action = None
        self._vision_task = None  # track the single pending async task

        # Survey state — only survey significant rooms, not every AAS area
        self._surveyed_clusters = set()  # coarse position keys we've surveyed
        self._survey_cooldown = 0.0

        # Death tracking
        self._was_alive = True
        self._deaths = 0

        # Window focus
        self._window_id = ""
        self._last_refocus = 0.0

        # Perception loop
        self.loop = PerceptionLoop(
            cfg=self.cfg,
            on_state=self._on_state,
            target_fps=12,
            capture_mode="window",
            keep_frame=True,
        )
        self._tick = 0
        self._start = 0.0

    def _select_items(self, args):
        # Use dry-reachable items only (excludes underwater/disconnected areas)
        items = self.agent._filter_dry_items() if self.agent.nav.graph else self.agent.items
        if args.all:
            selected = items
        elif args.category:
            selected = [(n, x, y, z) for n, x, y, z in items
                        if n.startswith(args.category)]
        else:
            selected = [(n, x, y, z) for n, x, y, z in items
                        if any(n.startswith(p) for p in PRIORITY_PREFIXES)]
        log.info("Tour items: %d / %d total (dry-reachable)", len(selected), len(self.agent.items))
        for name, x, y, z in selected:
            log.info("  %s at (%.0f, %.0f, %.0f)", name, x, y, z)
        return selected

    # ── Run ────────────────────────────────────────────────────────

    async def run(self):
        self._start = time.time()
        self.bridge.open()

        self._window_id = focus_game_window()
        self.agent.window_id = self._window_id
        # Retry init_game until we get a valid position (RCON can be slow after launch)
        for attempt in range(10):
            self.agent.init_game()
            if self.agent.nav.pos and self.agent.nav.current_area > 0:
                break
            log.warning("No position from RCON (attempt %d/10) — retrying in 1s...", attempt + 1)
            time.sleep(1.0)
        if not self.agent.nav.pos or self.agent.nav.current_area == 0:
            log.error("Could not get position after 10 attempts — is the game running?")
            return

        # If we spawned in a poorly-connected area (few reachable items),
        # walk around to find a better-connected area before starting the tour
        from openarena_perception.navigation.aas_parser import parse_aas
        import collections
        max_relocate = 5
        for relocate in range(max_relocate):
            # Quick connectivity check from current area (no swim)
            reachable = set()
            queue = collections.deque([self.agent.nav.current_area])
            while queue:
                node = queue.popleft()
                if node in reachable or node >= len(self.agent.nav.graph.areas):
                    continue
                reachable.add(node)
                area = self.agent.nav.graph.areas[node]
                for i, nb in enumerate(area.neighbors):
                    tt = area.travel_types[i] if i < len(area.travel_types) else 1
                    if tt not in (7, 8) and nb not in reachable:
                        queue.append(nb)

            if len(reachable) > 50:
                break  # well-connected area

            log.warning("Poorly-connected spawn area %d (%d reachable) — walking to find better area (attempt %d/%d)",
                        self.agent.nav.current_area, len(reachable), relocate + 1, max_relocate)
            # Walk forward + jump to get out of dead-ends
            self.bridge.cmd("+forward")
            self.bridge.cmd("+moveup")
            time.sleep(0.3)
            self.bridge.cmd("-moveup")
            time.sleep(2.0)
            self.bridge.cmd("-forward")
            time.sleep(0.5)
            self.agent.nav.update_position()

        time.sleep(0.5)

        # Select items NOW that we know our position
        self.tour_items = self._select_items(self.args)

        # Build route
        start = (self.agent.nav.pos[0], self.agent.nav.pos[1]) if self.agent.nav.pos else (0, 0)
        self._route = nearest_neighbor_route(self.tour_items, start)
        self._route_idx = 0

        log.info("=== ITEM TOUR START === (vision=%s)", "ON" if self.vision else "OFF")
        log.info("Route: %d waypoints", len(self._route))
        for i, (name, x, y, z) in enumerate(self._route):
            log.info("  [%d] %s (%.0f, %.0f, %.0f)", i, name, x, y, z)

        self._goto_next()
        await asyncio.sleep(2)

        try:
            await self.loop.run_async()
        except asyncio.CancelledError:
            pass
        finally:
            # Cancel any pending vision task
            if self._vision_task and not self._vision_task.done():
                self._vision_task.cancel()
            self._shutdown()

    # ── Tick ───────────────────────────────────────────────────────

    async def _on_state(self, gs: GameState):
        self._tick += 1
        now = time.time()

        # Refocus game window every 20s to prevent terminal capture
        if now - self._last_refocus > 20.0:
            self._window_id = focus_game_window()
            self._last_refocus = now

        # Update position
        self.agent.nav.update_position()
        self.agent.nav.check_stuck_cleanup()

        # Update learned map with wall detection every tick
        if self.agent.nav.pos and gs.frame is not None:
            from openarena_perception.perception.wall_detector import Perception
            if not hasattr(self, '_wall_detector'):
                self._wall_detector = Perception()
            wall_ahead, wall_score, open_dir = self._wall_detector.detect_wall_ahead(gs.frame)
            in_water = self._wall_detector.detect_underwater(gs.frame)
            self.learned_map.update(
                self.agent.nav.pos, self.agent.nav.yaw,
                wall_ahead, wall_score, open_dir, in_water)

        # Spatial advisor: record trail + dispatch thoughts
        if self.agent.nav.pos:
            self.advisor.record_trail(
                self.agent.nav.pos, self.agent.nav.yaw,
                self.agent.nav.current_area)
        if gs.frame is not None:
            self.advisor.maybe_dispatch(gs.frame)

        # Check advisor warnings BEFORE committing to forward movement
        if self.advisor.is_hazard_ahead():
            warnings = self.advisor.current_warnings()
            top = warnings[0] if warnings else None
            hint = self.advisor.get_recommended_action() or "back_away"
            if top:
                log.warning("ADVISOR HALT: %s [%s] %s -> %s",
                            top.kind, top.severity, top.text, hint)
            self._execute_advisor_action(hint)
            return  # skip normal movement this tick

        current_area = self.agent.nav.current_area

        # ── DEAD? Respawn and replan ──
        if gs.health is not None and gs.health <= 0:
            if self._was_alive:
                self._deaths += 1
                self._was_alive = False
                log.info("DIED (#%d)! Will respawn and replan.", self._deaths)
                if self.anomaly:
                    self.anomaly.reset()
            self.bridge.release_all()
            self.bridge.cmd("+attack")
            self.bridge.cmd("-attack")
            return

        # Just respawned — replan from new position
        if not self._was_alive:
            self._was_alive = True
            log.info("Respawned! Replanning route from new position.")
            # Wait a moment, walk forward to clear spawn
            self.bridge.cmd("+forward")
            await asyncio.sleep(1.5)
            self.bridge.cmd("-forward")
            self.agent.nav.update_position()
            # Replan from current position
            if self.agent.nav.pos:
                start = (self.agent.nav.pos[0], self.agent.nav.pos[1])
                # Rebuild route from remaining items
                remaining = self._route[self._route_idx:]
                if remaining:
                    self._route = [self._route[i] for i in range(self._route_idx)] + \
                                  nearest_neighbor_route(remaining, start)
                self._goto_next()
            return

        # ── STUCK recovery ──
        if self.agent.nav.is_recovering:
            return

        if self.agent.nav.is_stuck:
            self._stuck_attempts += 1

            # Use navigator's smart stuck recovery (includes exit finder on 2nd attempt)
            def capture():
                try:
                    return self.loop._capture.grab()
                except Exception:
                    return gs.frame

            self.agent.nav.handle_stuck(capture_fn=capture if gs.frame is not None else None)

            # Skip waypoint after too many attempts
            if self._stuck_attempts >= self._max_stuck_before_skip:
                if self._route_idx < len(self._route):
                    name = self._route[self._route_idx][0]
                    log.warning("SKIPPING [%d] %s after %d stuck",
                                self._route_idx + 1, name, self._stuck_attempts)
                    self._route_idx += 1
                    self._stuck_attempts = 0
                    self._item_start_time = time.time()
                    if self._route_idx < len(self._route):
                        self._goto_next()
                    else:
                        self._finish_tour()
                    return

            self.agent.nav.handle_stuck()
            return

        # ── ROOM SURVEY (throttled, clustered) ──
        if (self.surveyor and current_area > 0 and
                gs.frame is not None and
                now > self._survey_cooldown):
            # Cluster areas by coarse position (256-unit grid)
            if self.agent.nav.pos:
                cx = int(self.agent.nav.pos[0]) // 256
                cy = int(self.agent.nav.pos[1]) // 256
                cluster_key = (cx, cy)
                if (cluster_key not in self._surveyed_clusters and
                        self.surveyor.should_survey(current_area)):
                    self._surveyed_clusters.add(cluster_key)
                    self._survey_cooldown = now + 45.0  # 45s between surveys

                    def capture():
                        try:
                            return self.loop._capture.grab()
                        except Exception:
                            return gs.frame

                    survey = self.surveyor.perform_survey(
                        area_id=current_area,
                        pos=self.agent.nav.pos,
                        start_yaw=self.agent.nav.yaw,
                        capture_fn=capture,
                    )
                    if survey:
                        log.info("Survey: %s | exits=%d | exit=%s",
                                 survey.room_type, len(survey.exits),
                                 survey.recommended_exit)
                    # Re-center after survey spin
                    self.bridge.cmd("centerview")
                    return  # skip this tick — we just spun around

        # ── Keep view level ──
        if self._tick % 12 == 0:
            self.bridge.cmd("centerview")

        # ── Move forward ──
        self.bridge.move_forward(True)

        # ── MOTION ANOMALY (every tick, cheap) ──
        if self.anomaly and gs.frame is not None:
            bot_pos = (self.agent.nav.pos[:2]) if self.agent.nav.pos else None
            self.anomaly.update(gs.frame, bot_pos=bot_pos)

            lockable = self.anomaly.get_lockable_anomaly()
            if lockable:
                log.info("ANOMALY #%d at (%d,%d) speed=%.1f — identifying...",
                         lockable.track_id, lockable.cx, lockable.cy,
                         lockable.flow_magnitude)
                report = self.anomaly.identify_anomaly(lockable, gs.frame)
                if report:
                    log.info("  → %s (%s) conf=%.2f action=%s",
                             report.identity, report.category,
                             report.confidence, report.action)

        # ── VISION NAV (async, single task at a time) ──
        if (self.vision and gs.frame is not None and
                self.vision.should_query() and
                (self._vision_task is None or self._vision_task.done())):
            self._vision_task = asyncio.ensure_future(
                self._do_vision_query(gs.frame))

        # ── FOLLOW PATH ──
        travel_type = self.agent.nav.follow_path()
        if travel_type is not None:
            # Jump for vertical traversals
            if travel_type in (TRAVEL_JUMP, TRAVEL_JUMPPAD, TRAVEL_BARRIERJUMP,
                               TRAVEL_WALKOFFLEDGE):
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")
            elif travel_type == TRAVEL_LADDER:
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")

            # Vision detected stairs — extra jumps
            if self._vision_action == "walk_up_stairs" and self._tick % 3 == 0:
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")
            elif self._vision_action == "jump_forward":
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")
                self._vision_action = None
        else:
            # Bunny hop
            if self._tick % 8 == 0:
                self.bridge.cmd("+moveup")
                self.bridge.cmd("-moveup")

        # ── CHECK ITEM TIMEOUT (circular navigation protection) ──
        if (self._item_start_time > 0 and self._route_idx < len(self._route)
                and time.time() - self._item_start_time > self._item_timeout):
            name = self._route[self._route_idx][0]
            elapsed_item = time.time() - self._item_start_time
            log.warning("TIMEOUT [%d] %s after %.0fs — skipping (circular navigation)",
                        self._route_idx + 1, name, elapsed_item)
            self._route_idx += 1
            self._stuck_attempts = 0
            self._item_start_time = time.time()
            if self._route_idx < len(self._route):
                self._goto_next()
            else:
                self._finish_tour()
            return

        # ── CHECK ARRIVAL ──
        if not self.agent.nav.has_path and self._route_idx < len(self._route):
            name = self._route[self._route_idx][0]
            elapsed = time.time() - self._start
            log.info("[%3.0fs] ARRIVED at [%d/%d] %s",
                     elapsed, self._route_idx + 1, len(self._route), name)
            self._route_idx += 1
            self._stuck_attempts = 0
            self._item_start_time = time.time()
            if self._route_idx < len(self._route):
                self._goto_next()
            else:
                self._finish_tour()

        # ── STATUS LOG every ~4s ──
        if self._tick % 48 == 0:
            elapsed = now - self._start
            wp = self._route[self._route_idx][0] if self._route_idx < len(self._route) else "DONE"
            extra = ""
            if self.vision:
                extra += f" vis={self.vision._query_count}"
            if self.anomaly and self.anomaly.active_tracks:
                extra += f" anom={self.anomaly.active_tracks}"
            log.info("[%3.0fs] [%d/%d] → %s | %s |%s",
                     elapsed, self._route_idx + 1, len(self._route),
                     wp, self.agent.nav.get_status(), extra)

    # ── Vision query (single async task) ──

    async def _do_vision_query(self, frame: np.ndarray):
        try:
            decision = await self.vision.query_navigation(frame)
            action = decision.get("action", "forward")
            ahead = decision.get("ahead", "?")
            reason = decision.get("reason", "")

            log.info("Vision #%d: %s → %s — %s",
                     self.vision._query_count, ahead, action, reason)

            self._vision_action = action

            # Only intervene if path is blocked
            if action in ("turn_left", "turn_right", "turn_around") and \
                    ahead in ("wall", "blocked"):
                self._execute_vision_action(action)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.debug("Vision error: %s", e)

    # ── Execute turn/movement actions ──

    def _execute_vision_action(self, action: str):
        YAW = 200
        if action == "turn_left":
            self.bridge.cmd(f"cl_yawspeed {YAW}")
            self.bridge.action_start("left")
            time.sleep(0.45)
            self.bridge.action_stop("left")
        elif action == "turn_right":
            self.bridge.cmd(f"cl_yawspeed {YAW}")
            self.bridge.action_start("right")
            time.sleep(0.45)
            self.bridge.action_stop("right")
        elif action == "turn_around":
            self.bridge.cmd(f"cl_yawspeed {YAW}")
            self.bridge.action_start("right")
            time.sleep(0.9)
            self.bridge.action_stop("right")
        elif action == "slight_left":
            self.bridge.cmd(f"cl_yawspeed {YAW}")
            self.bridge.action_start("left")
            time.sleep(0.2)
            self.bridge.action_stop("left")
        elif action == "slight_right":
            self.bridge.cmd(f"cl_yawspeed {YAW}")
            self.bridge.action_start("right")
            time.sleep(0.2)
            self.bridge.action_stop("right")
        elif action == "jump_forward":
            self.bridge.move_forward(True)
            self.bridge.cmd("+moveup")
            self.bridge.cmd("-moveup")
        elif action == "walk_up_stairs":
            self.bridge.move_forward(True)
            self.bridge.cmd("+moveup")
            self.bridge.cmd("-moveup")
        elif action == "back_up":
            self.bridge.move_forward(False)
            self.bridge.action_start("back")
            time.sleep(0.5)
            self.bridge.action_stop("back")
            self.bridge.move_forward(True)
        elif action in ("strafe_left", "strafe_right"):
            d = "moveleft" if action == "strafe_left" else "moveright"
            self.bridge.action_start(d)
            time.sleep(0.4)
            self.bridge.action_stop(d)

    # ── Tour lifecycle ──

    def _finish_tour(self):
        self._tours_done += 1
        elapsed = time.time() - self._start
        log.info("=== TOUR #%d COMPLETE in %.0fs (deaths=%d) ===",
                 self._tours_done, elapsed, self._deaths)
        if self.args.loop:
            log.info("Starting next loop...")
            self._route_idx = 0
            self._stuck_attempts = 0
            self._start = time.time()
            # Re-select items from current position (may have different reachability)
            self.tour_items = self._select_items(self.args)
            start = (self.agent.nav.pos[:2]) if self.agent.nav.pos else (0, 0)
            self._route = nearest_neighbor_route(self.tour_items, start)
            if not self._route:
                log.warning("No reachable items — exploring")
                self.agent.nav.path_to_random()
                return
            self._goto_next()
        else:
            log.info("Tour done!")
            raise asyncio.CancelledError()

    def _goto_next(self):
        if self._route_idx >= len(self._route):
            return
        name, x, y, z = self._route[self._route_idx]
        target_area = self.agent.nav.graph.nearest_area(x, y, z)

        # Skip liquid areas
        if (self.agent.nav.graph and target_area < len(self.agent.nav.graph.areas)
                and self.agent.nav.graph.areas[target_area].is_liquid):
            log.warning("Target %s in liquid area %d — skipping", name, target_area)
            self._advance_route()
            return

        self._item_start_time = time.time()
        log.info("→ [%d/%d] %s at (%.0f,%.0f,%.0f) area=%d",
                 self._route_idx + 1, len(self._route), name, x, y, z, target_area)
        self.advisor.set_goal(target_area, (x, y, z), name)

        if self.agent.nav.path_to_area(target_area):
            return  # path found

        # Path failed — try with fresh penalties (stuck blacklist may have cut off routes)
        log.warning("No direct path to %s (area %d) — retrying with cleared penalties",
                    name, target_area)
        if self.agent.nav.path_to_area_fresh(target_area):
            return  # path found after clearing penalties

        # Still no path — try exploring toward the target's general direction
        log.warning("Still no path to %s — exploring toward (%.0f,%.0f)",
                    name, x, y)
        if self.agent.nav.explore_toward(x, y):
            return  # exploring toward target

        # Try random exploration as last resort
        log.warning("Explore-toward failed for %s — trying random exploration", name)
        if self.agent.nav.path_to_random():
            return  # explore and retry next decision cycle

        # Truly no path — skip
        log.warning("Skipping %s — unreachable from area %d", name, self.agent.nav.current_area)
        self._advance_route()

    def _advance_route(self):
        """Move to the next waypoint in the route."""
        self._route_idx += 1
        self._stuck_attempts = 0
        if self._route_idx < len(self._route):
            self._goto_next()
        else:
            self._finish_tour()

    def _execute_advisor_action(self, hint: str) -> None:
        """Translate an advisor action_hint into game commands.
        Used when the advisor detects a hazard and we must halt forward movement.
        """
        self.bridge.move_forward(False)
        if hint == "back_away":
            self.bridge.action_start("back")
            # brief backup; release_all will stop it next tick
        elif hint == "turn_around":
            self.bridge.cmd("cl_yawspeed 300")
            self.bridge.action_start("right")
        elif hint == "turn_left_90":
            self.bridge.cmd("cl_yawspeed 250")
            self.bridge.action_start("left")
        elif hint == "turn_right_90":
            self.bridge.cmd("cl_yawspeed 250")
            self.bridge.action_start("right")
        elif hint == "strafe_left":
            self.bridge.action_start("moveleft")
        elif hint == "strafe_right":
            self.bridge.action_start("moveright")
        elif hint == "stop":
            pass  # already stopped forward motion above
        # Note: these keys stay held briefly. The next tick's handle_stuck
        # or release_all will clear them, so we don't over-turn.

    def _shutdown(self):
        log.info("Shutting down...")
        # Advisor shutdown (cancel pending thought, log stats)
        if hasattr(self, 'advisor'):
            self.advisor.shutdown()
        # Save learned map before exit
        self.learned_map.save()
        stats = self.learned_map.export_for_hud()
        log.info("Learned map saved: %d updates, %d edge failures",
                 stats.get("updates", 0), len(self.learned_map._edge_failures))
        self.agent.shutdown()
        self.bridge.close()
        log.info("Tours: %d | Deaths: %d", self._tours_done, self._deaths)
        if self.vision:
            log.info("Vision queries: %d", self.vision._query_count)
        if self.surveyor:
            log.info("Surveys: %d new, %d total",
                     self.surveyor.survey_count, self.surveyor.total_surveys)
        if self.anomaly:
            log.info("Anomalies identified: %d", self.anomaly.identified_count)
            for item in self.anomaly.catalog:
                log.info("  #%d: %s (%s)", item.track_id, item.identity, item.category)


# ── Entry point ──────────────────────────────────────────────────────

def release_all():
    pipe_path = os.path.expanduser("~/.openarena/baseoa/oapipe")
    try:
        fd = os.open(pipe_path, os.O_WRONLY | os.O_NONBLOCK)
        for action in ["forward", "back", "moveleft", "moveright",
                       "left", "right", "attack", "moveup", "movedown",
                       "lookup", "lookdown"]:
            os.write(fd, f"-{action}\n".encode())
        os.close(fd)
    except OSError:
        pass


def main():
    atexit.register(release_all)
    # Release keys on any fatal signal — prevents the bot from walking forever
    # if the process is killed mid-movement.
    def _cleanup_and_exit(*args):
        release_all()
        sys.exit(0)
    signal.signal(signal.SIGTERM, _cleanup_and_exit)
    signal.signal(signal.SIGHUP, _cleanup_and_exit)
    # SIGINT handled by asyncio loop below
    # Also release on startup to clear any stale state from a crashed predecessor
    release_all()

    parser = argparse.ArgumentParser(description="Item Tour")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--category", type=str)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--rcon-password", default="botctl")
    args = parser.parse_args()

    tour = ItemTour(args)
    loop = asyncio.new_event_loop()
    loop.add_signal_handler(signal.SIGINT,
                            lambda: [t.cancel() for t in asyncio.all_tasks(loop)])
    try:
        loop.run_until_complete(tour.run())
    finally:
        release_all()
        loop.close()


if __name__ == "__main__":
    main()
