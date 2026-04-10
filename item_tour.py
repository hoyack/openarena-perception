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
from dataclasses import replace as dc_replace

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from openarena_perception import GameState, PerceptionLoop, build_config
from openarena_perception.aas_parser import (
    TRAVEL_BARRIERJUMP,
    TRAVEL_JUMP,
    TRAVEL_JUMPPAD,
    TRAVEL_LADDER,
    TRAVEL_WALKOFFLEDGE,
)
from openarena_perception.game_bridge import GameBridge
from openarena_perception.hud_schema import (
    build_hud_payload,
    ensure_runtime_dirs,
    write_hud_state,
)
from openarena_perception.intent_transitions import (
    TransitionSignals,
    detect_intent_transition,
)
from openarena_perception.models import (
    BotContext,
    Intent,
    IntentStatus,
    MacroIntent,
    Problem,
)
from openarena_perception.motion_anomaly import MotionAnomalyTracker
from openarena_perception.reactive_agent import ReactiveAgent
from openarena_perception.room_surveyor import RoomSurveyor

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
        # Ensure ./tmp/ and ./logs/ exist before any HUD export or log file
        # handler opens (Phase 10-01: project-root runtime dirs).
        ensure_runtime_dirs()
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

        # Proactive wall avoidance (Option C): vision streak + learned_map look-ahead
        self._wall_vision_streak = 0      # consecutive ticks with wall_ahead=True
        self._proactive_halts = 0         # stat: how many times we halted preemptively
        self._last_proactive_halt = 0.0   # timestamp; throttle repeated halts
        # Pin detection: halts clustered in one spot -> bot is wedged, replan
        self._pin_origin = None           # (x, y) of first clustered halt, or None
        self._pin_count = 0               # consecutive halts within PIN_RADIUS
        self._PIN_RADIUS = 64.0           # units; halts within this count as same pin
        self._PIN_ESCALATE = 3            # after N clustered halts, force replan

        # Fix A: avoidance commitment — hold the strafe/turn action for 0.5s
        # instead of releasing it next tick. Stops the "wall-slide then
        # re-engage +forward into the same wall" loop.
        self._avoidance_until = 0.0       # timestamp; while now<this, skip forward
        self._avoidance_hint = None       # action hint to keep held during avoidance
        self._AVOIDANCE_DURATION = 0.5    # seconds

        # Fix B: visual pin detector — detect "walking but screen stays the
        # same" (bot wedged against geometry the wall_detector can't see, like
        # corners). Uses a small center-strip frame hash compared tick-to-tick.
        self._last_frame_hash = None      # downsampled grayscale bytes
        self._frame_still_streak = 0      # consecutive low-diff ticks
        self._last_pos_for_vis = None     # last position when we checked visual
        self._visual_pin_hits = 0         # stat
        self._VISUAL_PIN_FRAME_THRESH = 3.5  # mean abs pixel diff below this = "still"
        self._VISUAL_PIN_POS_THRESH = 6.0    # units; position delta below this = "not moving"
        self._VISUAL_PIN_STREAK = 3       # ticks required to fire

        # Vision state
        self._vision_action = None
        self._vision_task = None  # track the single pending async task

        # Survey state — only survey significant rooms, not every AAS area
        self._surveyed_clusters = set()  # coarse position keys we've surveyed
        self._survey_cooldown = 0.0

        # Death tracking
        self._was_alive = True
        self._deaths = 0

        # Phase 10: intent tracking + pause-to-assess
        pause_raw = os.environ.get("OA_INTENT_PAUSE_MS", "300")
        try:
            pause_ms = int(pause_raw)
        except ValueError:
            pause_ms = 300
        pause_ms = max(0, min(5000, pause_ms))  # clamp [0, 5000]
        self._intent_pause_duration: float = pause_ms / 1000.0
        self._intent_pause_until: float = 0.0
        self._threat_flag: bool = False
        self._last_area: int = 0
        initial_intent = Intent(
            macro=MacroIntent.IDLE,
            sub="",
            description="Initializing",
            started_at=time.time(),
        )
        self.context: BotContext = BotContext(current_intent=initial_intent)

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
        import collections

        from openarena_perception.navigation.aas_parser import parse_aas
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

    @property
    def threat_flag(self) -> bool:
        """Stubbed to False for Phase 10. Later phases will wire enemy detection."""
        return self._threat_flag

    def _apply_intent_transition(self, now: float, gs, *,
                                 halt_reason: str | None = None,
                                 pinned: bool = False,
                                 pin_escalated: bool = False,
                                 advisor_hazard: bool = False,
                                 advisor_warning: str = "",
                                 was_alive_prev_tick: bool | None = None) -> None:
        """Phase 10: detect + apply any intent transition for this tick.

        Called at every tick-exit point in _on_state (early returns AND the
        normal fallthrough). Handles push_intent, pause-gate opening (if
        macro changed and no threat), and release_all() exactly once per
        transition (Pitfall 4).
        """
        nav = self.agent.nav
        route_target_name = ""
        route_target_pos = None
        if 0 <= self._route_idx < len(self._route):
            name, x, y, z = self._route[self._route_idx]
            route_target_name = name
            route_target_pos = (float(x), float(y), float(z))

        signals = TransitionSignals(
            nav_is_stuck=getattr(nav, "is_stuck", False),
            nav_is_climbing_stairs=getattr(nav, "is_climbing_stairs", False),
            nav_current_area=getattr(nav, "current_area", 0),
            route_idx=self._route_idx,
            route_target_name=route_target_name,
            route_target_pos=route_target_pos,
            health=gs.health,
            was_alive_prev_tick=(was_alive_prev_tick
                                 if was_alive_prev_tick is not None
                                 else self._was_alive),
            halt_reason=halt_reason,
            advisor_hazard=advisor_hazard,
            advisor_warning=advisor_warning,
            pinned=pinned,
            pin_escalated=pin_escalated,
            now=now,
            prev_macro=self.context.current_intent.macro,
            prev_sub=self.context.current_intent.sub,
        )
        new_intent = detect_intent_transition(signals)
        if new_intent is not None:
            macro_changed = new_intent.macro != self.context.current_intent.macro
            prev_macro = self.context.current_intent.macro
            self.context.push_intent(new_intent)
            if macro_changed and not self.threat_flag:
                # Open pause-to-assess window (Fix A clone pattern).
                # release_all() is called ONCE here, not every tick during
                # the pause (Pitfall 4).
                self._intent_pause_until = now + self._intent_pause_duration
                self.context.current_intent = dc_replace(
                    new_intent, status=IntentStatus.PLANNING
                )
                self.bridge.release_all()
                log.info("Intent transition: %s → %s (pause %dms)",
                         prev_macro, new_intent.macro,
                         int(self._intent_pause_duration * 1000))
            else:
                log.info("Intent: %s / %s", new_intent.macro, new_intent.sub)

        # Area history tracking
        cur_area = getattr(nav, "current_area", 0)
        if cur_area != self._last_area and cur_area > 0:
            self.context.record_area(cur_area)
            self._last_area = cur_area

        self.context.tick_count += 1
        self.context.path_progress = (
            self._route_idx,
            len(self._route),
        )

    async def _on_state(self, gs: GameState):
        self._tick += 1
        now = time.time()

        # === Phase 10: Pause-to-assess gate ===
        # Must sit ABOVE advisor/wall/Fix A early returns but BELOW death/stuck
        # reflexes (which come later in this tick). Honors Pitfall 4:
        # emergencies override the pause. release_all() is NOT called here --
        # it was called exactly once when the pause window opened.
        if now < self._intent_pause_until:
            nav_is_stuck = getattr(self.agent.nav, "is_stuck", False)
            health_ok = gs.health is None or gs.health > 0
            if not self.threat_flag and not nav_is_stuck and health_ok:
                # Stay paused — assessing
                self.context.tick_count += 1
                return
            # Emergency or threat → break out
            self._intent_pause_until = 0.0
            if self.context.current_intent.status == IntentStatus.PLANNING:
                self.context.current_intent = dc_replace(
                    self.context.current_intent, status=IntentStatus.EXECUTING
                )

        # Phase 10: per-tick locals tracked for intent transition detection
        halt_reason: str | None = None
        pinned: bool = False
        pin_escalated: bool = False

        # Refocus game window every 20s to prevent terminal capture
        if now - self._last_refocus > 20.0:
            self._window_id = focus_game_window()
            self._last_refocus = now

        # Export HUD state for the strategic_hud.py companion app (every 6 ticks)
        if self._tick % 6 == 0:
            self._export_hud(gs)

        # Update position
        self.agent.nav.update_position()
        self.agent.nav.check_stuck_cleanup()

        # Update learned map with wall detection every tick
        wall_ahead = False
        wall_score = 0.0
        open_dir = 0
        if self.agent.nav.pos and gs.frame is not None:
            from openarena_perception.perception.wall_detector import Perception
            if not hasattr(self, '_wall_detector'):
                self._wall_detector = Perception()
            wall_ahead, wall_score, open_dir = self._wall_detector.detect_wall_ahead(gs.frame)
            in_water = self._wall_detector.detect_underwater(gs.frame)
            self.learned_map.update(
                self.agent.nav.pos, self.agent.nav.yaw,
                wall_ahead, wall_score, open_dir, in_water)

        # Vision streak hysteresis (used by proactive wall halt below)
        if wall_ahead:
            self._wall_vision_streak += 1
        else:
            self._wall_vision_streak = 0

        # Fix B: Visual pin detector — "walking but screen stays the same".
        # Catches corners/geometry the wall_detector is blind to. Updates
        # self._frame_still_streak every tick; consumed below.
        visual_pin = False
        if gs.frame is not None and self.agent.nav.pos is not None:
            import cv2 as _cv2
            h, w = gs.frame.shape[:2]
            strip = gs.frame[int(h*0.3):int(h*0.7), int(w*0.25):int(w*0.75)]
            small = _cv2.cvtColor(_cv2.resize(strip, (64, 48)), _cv2.COLOR_BGR2GRAY)
            if self._last_frame_hash is not None:
                frame_diff = float(np.abs(
                    small.astype(np.int16) - self._last_frame_hash.astype(np.int16)
                ).mean())
            else:
                frame_diff = 999.0
            self._last_frame_hash = small

            if self._last_pos_for_vis is not None:
                pos_delta = math.hypot(
                    self.agent.nav.pos[0] - self._last_pos_for_vis[0],
                    self.agent.nav.pos[1] - self._last_pos_for_vis[1])
            else:
                pos_delta = 999.0
            self._last_pos_for_vis = self.agent.nav.pos

            if (frame_diff < self._VISUAL_PIN_FRAME_THRESH
                    and pos_delta < self._VISUAL_PIN_POS_THRESH):
                self._frame_still_streak += 1
            else:
                self._frame_still_streak = 0
            if self._frame_still_streak >= self._VISUAL_PIN_STREAK:
                visual_pin = True

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
            # Phase 10: record advisor_halt Problem
            _pos = tuple(self.agent.nav.pos) if self.agent.nav.pos else (0.0, 0.0, 0.0)
            self.context.record_problem(Problem(
                kind="advisor_halt", location=_pos, timestamp=now,
                description=top.text if top else "advisor halt",
            ))
            self._apply_intent_transition(
                now, gs,
                advisor_hazard=True,
                advisor_warning=top.text if top else "advisor halt",
            )
            return  # skip normal movement this tick

        # Fix A: avoidance commitment — if we're still inside the commitment
        # window, keep the strafe/turn held and skip forward movement so the
        # bot actually gains distance from the wall instead of wall-sliding.
        if now < self._avoidance_until and self._avoidance_hint is not None:
            self._execute_advisor_action(self._avoidance_hint)
            # Phase 10: hold current AVOIDING_WALL intent; report ongoing halt
            self._apply_intent_transition(
                now, gs, halt_reason=self._avoidance_hint,
            )
            return

        # ── PROACTIVE WALL HALT (Option C) ──────────────────────────────────
        # Combine vision (reactive, 60Hz) + learned_map look-ahead (predictive
        # in known areas) + visual pin (Fix B — catches corners). Halt forward
        # movement BEFORE the bot commits 1s of "+forward" into a wall and
        # waits for stuck detection to catch up.
        # Throttled to once per 0.5s to avoid flapping during micro-dodges.
        if (self.agent.nav.pos is not None
                and now - self._last_proactive_halt > 0.5
                and not self.agent.nav.is_recovering):
            halt_reason = self._check_proactive_wall(
                self.agent.nav.pos, self.agent.nav.yaw,
                wall_ahead, wall_score, open_dir)
            # Fix B: visual pin overrides if wall_detector missed it
            if halt_reason is None and visual_pin:
                halt_reason = "visual_pin"
                self._visual_pin_hits += 1
                self._frame_still_streak = 0  # reset so we don't re-fire immediately
            if halt_reason is not None:
                self._last_proactive_halt = now
                self._proactive_halts += 1
                pos_xy = (self.agent.nav.pos[0], self.agent.nav.pos[1])

                # Pin detection: are we halting in the same spot repeatedly?
                if (self._pin_origin is not None
                        and math.hypot(pos_xy[0] - self._pin_origin[0],
                                       pos_xy[1] - self._pin_origin[1]) < self._PIN_RADIUS):
                    self._pin_count += 1
                else:
                    self._pin_origin = pos_xy
                    self._pin_count = 1

                pinned = self._pin_count >= self._PIN_ESCALATE

                # Action picker:
                #   - Turn clears the vision flag (bot looks elsewhere)
                #   - Strafe same direction keeps lateral distance from wall
                #     (splash-damage avoidance + unpredictable pathing)
                #   - If pinned OR visual_pin, escalate to a harder action
                #     (open_dir is unreliable in corners where visual_pin fires)
                if pinned or halt_reason == "visual_pin":
                    # Turn around AND strafe in a picked direction to break
                    # out of corners where both sides look similar.
                    hint = "turn_around"
                elif open_dir < 0:
                    hint = "turn_left_and_strafe"
                elif open_dir > 0:
                    hint = "turn_right_and_strafe"
                else:
                    # Both sides look closed — back away and re-survey
                    hint = "back_away"

                log.warning("PROACTIVE WALL HALT: %s (score=%.2f streak=%d pin=%d vpin=%d) -> %s",
                            halt_reason, wall_score, self._wall_vision_streak,
                            self._pin_count, self._frame_still_streak, hint)
                self._execute_advisor_action(hint)
                # Phase 10: record wall_halt Problem (pin/visual_pin handled below)
                _pos = tuple(self.agent.nav.pos) if self.agent.nav.pos else (0.0, 0.0, 0.0)
                if pinned or halt_reason == "visual_pin":
                    self.context.record_problem(Problem(
                        kind="pin", location=_pos, timestamp=now,
                        description=f"pin escalation, replanning ({halt_reason})",
                    ))
                    pin_escalated = True
                else:
                    self.context.record_problem(Problem(
                        kind="wall_halt", location=_pos, timestamp=now,
                        description=f"halt_reason={halt_reason} score={wall_score:.2f}",
                    ))

                # Fix A: commit to this avoidance action for the next 0.5s so
                # the bot actually gains distance instead of wall-sliding and
                # re-engaging +forward on the next tick.
                self._avoidance_hint = hint
                self._avoidance_until = now + self._AVOIDANCE_DURATION

                # Escalation: bot is wedged — force a replan from current pos.
                # This fixes the "routing into walls while trying to reach a
                # different destination" case: our planned path is wrong for
                # where we actually are, so recompute it.
                if (pinned or halt_reason == "visual_pin") and self._route_idx < len(self._route):
                    log.warning("PIN ESCALATION: replanning from area %d",
                                self.agent.nav.current_area)
                    self._pin_count = 0
                    self._pin_origin = None
                    self._goto_next()
                # Phase 10: fire AVOIDING_WALL or RECOVERING_STUCK (pin escalated)
                self._apply_intent_transition(
                    now, gs,
                    halt_reason=halt_reason,
                    pinned=pinned,
                    pin_escalated=pin_escalated,
                )
                return  # skip normal movement this tick
        else:
            # No halt this tick: if we've walked >PIN_RADIUS from the pin spot,
            # clear the counter (bot broke free on its own).
            if self._pin_origin is not None and self.agent.nav.pos is not None:
                dist = math.hypot(
                    self.agent.nav.pos[0] - self._pin_origin[0],
                    self.agent.nav.pos[1] - self._pin_origin[1])
                if dist > self._PIN_RADIUS * 2:
                    self._pin_origin = None
                    self._pin_count = 0

        current_area = self.agent.nav.current_area

        # ── DEAD? Respawn and replan ──
        if gs.health is not None and gs.health <= 0:
            if self._was_alive:
                self._deaths += 1
                self._was_alive = False
                log.info("DIED (#%d)! Will respawn and replan.", self._deaths)
                if self.anomaly:
                    self.anomaly.reset()
                # Phase 10: record respawn Problem on death edge
                _pos = tuple(self.agent.nav.pos) if self.agent.nav.pos else (0.0, 0.0, 0.0)
                self.context.record_problem(Problem(
                    kind="respawn", location=_pos, timestamp=now,
                    description="died, waiting for respawn",
                ))
            self.bridge.release_all()
            self.bridge.cmd("+attack")
            self.bridge.cmd("-attack")
            # Phase 10: fire RESPAWNING intent transition (edge-triggered)
            self._apply_intent_transition(now, gs)
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
            # Phase 10: fire TOURING "recovering from respawn" transition.
            # Pass was_alive_prev_tick=False so detect_intent_transition
            # sees the was_dead -> alive edge.
            self._apply_intent_transition(now, gs, was_alive_prev_tick=False)
            return

        # ── STUCK recovery ──
        if self.agent.nav.is_recovering:
            self._apply_intent_transition(now, gs)
            return

        if self.agent.nav.is_stuck:
            # Phase 10: record stuck Problem + fire RECOVERING_STUCK transition.
            # First-tick only (edge) -- detect via stuck_attempts==0 before incr.
            if self._stuck_attempts == 0:
                _pos = tuple(self.agent.nav.pos) if self.agent.nav.pos else (0.0, 0.0, 0.0)
                self.context.record_problem(Problem(
                    kind="stuck", location=_pos, timestamp=now,
                    description=f"stuck #{self._stuck_attempts + 1}",
                ))
            self._stuck_attempts += 1

            # Edge-trigger advisor diagnosis on 2nd stuck attempt.
            # Lets the LLM look at the current frame and suggest a targeted
            # unstuck action (e.g. "turn_around", "strafe_left"). Fires once
            # per stuck streak; single-thought-in-flight guard prevents spam.
            if self._stuck_attempts == 2 and gs.frame is not None:
                problem = f"stuck {self._stuck_attempts}x at area {current_area}, navigator cannot advance"
                self.advisor.request_diagnosis(gs.frame, problem)

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
                    self._apply_intent_transition(now, gs)
                    return

            self.agent.nav.handle_stuck()
            self._apply_intent_transition(now, gs)
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
                    self._apply_intent_transition(now, gs)
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
            self._apply_intent_transition(now, gs)
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

        # ── Phase 10: Intent transition detection (normal tick fallthrough) ──
        # Runs after follow_path so nav.is_climbing_stairs / is_stuck reflect
        # this tick's nav state. halt_reason is None on the normal path
        # (the wall-halt early return handles non-None halt_reason cases).
        self._apply_intent_transition(now, gs, halt_reason=halt_reason,
                                      pinned=pinned, pin_escalated=pin_escalated)

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

    def _check_proactive_wall(
        self, pos, yaw: float,
        wall_ahead: bool, wall_score: float, open_dir: int,
    ):
        """Return a short reason string if a proactive wall halt should fire,
        else None. Combines vision (hysteresis) with learned_map look-ahead.

        Vision trigger:
          - single-tick high-confidence (wall_score >= 0.80), OR
          - 2+ consecutive ticks of wall_ahead=True

        Learned map trigger:
          - Project pos forward by 72 units (~1 grid cell) along yaw
          - If that cell is CellState.WALL (known wall from prior mapping), halt
        """
        # Vision signal
        if wall_ahead and (wall_score >= 0.80 or self._wall_vision_streak >= 2):
            return f"vision"

        # Learned map look-ahead
        try:
            from openarena_perception.navigation.learned_map import CellState
            look_dist = 72.0  # ~1.1 grid cells at 64-unit resolution
            lx = pos[0] + look_dist * math.cos(math.radians(yaw))
            ly = pos[1] + look_dist * math.sin(math.radians(yaw))
            if self.learned_map.cell_state(lx, ly) == int(CellState.WALL):
                return "learned_map"
        except Exception:
            pass  # learned_map optional; never let it crash the tick

        return None

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
        elif hint == "turn_left_and_strafe":
            # Combined primitive used by proactive wall halt: rotate the view
            # (clears the wall_ahead flag) and strafe the same way (gain
            # lateral distance, avoid wall-hugging / splash damage).
            self.bridge.cmd("cl_yawspeed 250")
            self.bridge.action_start("left")
            self.bridge.action_start("moveleft")
        elif hint == "turn_right_and_strafe":
            self.bridge.cmd("cl_yawspeed 250")
            self.bridge.action_start("right")
            self.bridge.action_start("moveright")
        elif hint == "stop":
            pass  # already stopped forward motion above
        # Note: these keys stay held briefly. The next tick's handle_stuck
        # or release_all will clear them, so we don't over-turn.

    def _export_hud(self, gs):
        """Write ./tmp/oa_hud_state.json for the companion strategic_hud.py.

        Delegates to openarena_perception.hud_schema (Phase 10-01). Every
        pre-existing key is preserved verbatim via the `extras` dict so the
        HUD reader sees the same schema as before. Called every 6 ticks
        from the tick loop.
        """
        try:
            nav = self.agent.nav
            pos = nav.pos or (0, 0, 0)
            # Build route waypoint list compatible with HUD schema
            items = [[name, x, y, z] for (name, x, y, z) in self._route]
            legacy_fields = {
                "map": getattr(self.agent, "map_name", "oa_dm1"),
                "x": pos[0], "y": pos[1], "z": pos[2],
                "yaw": nav.yaw,
                "health": gs.health if gs.health is not None else 100,
                "armor": gs.armor if getattr(gs, "armor", None) is not None else 0,
                "ammo": getattr(gs, "ammo", 0) or 0,
                "weapon": getattr(gs, "weapon", "machinegun") or "machinegun",
                "alive": self._was_alive,
                "stuck": nav.is_stuck,
                "recovering": nav.is_recovering,
                "items": items,
                "deaths": self._deaths,
                "elapsed": time.time() - (self._item_start_time or time.time()),
                # Tour-specific progress
                "brain_state": "TOURING",
                "disposition": "explore",
                "armament": "none",
                "orientation": "open" if not nav.is_stuck else "blocked",
                "under_attack": False,
                "anomaly_count": 0,
                "surveys_total": 0,
                "current_room_type": f"area_{nav.current_area}",
                "current_room_exits": [],
                "nav_target": (self._route[self._route_idx][0]
                               if self._route_idx < len(self._route) else ""),
                "state_duration": time.time() - (self._item_start_time or time.time()),
                "items_collected": self._route_idx,
                "learned_map": self.learned_map.export_for_hud(),
                # item_tour extras
                "route_idx": self._route_idx,
                "proactive_halts": self._proactive_halts,
                "visual_pin_hits": self._visual_pin_hits,
                "advisor_stats": self.advisor.stats() if hasattr(self, "advisor") else {},
            }
            payload = build_hud_payload(
                context=self.context,
                is_paused_for_assess=(time.time() < self._intent_pause_until),
                threat_flag=self.threat_flag,
                extras=legacy_fields,
            )
            write_hud_state(payload)
        except Exception as e:
            log.debug("HUD export failed: %s", e)

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
