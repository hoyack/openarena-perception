#!/usr/bin/env python3
"""open_perception.py — Open-Perception unified HUD app (Phase 12-03).

Single standalone pygame app that composes three sub-surface panels into a
760x720 window (Phase 12.1 layout):

    TOP-LEFT    (  0..360,   0..360) — WireframePanel (first-person, square, chrome only)
    BOTTOM-LEFT (  0..360, 360..720) — MinimapPanel   (top-down learned map + route, square)
    RIGHT       (360..760,   0..720) — StatsPanel     (vital stats + intent + verbose rows)

Reads `./tmp/oa_hud_state.json` every tick at 10 FPS. Replaces the deleted
legacy `strategic_hud.py` (Phase 10) and
`openarena_perception/visualization/demo_wireframe_room.py` (Phase 11).

Usage:
    uv run python open_perception.py
    uv run python open_perception.py --aas maps/oa_dm1.aas

Deduplication contract (Phase 12 decision): every metric appears exactly once.
Numeric HUD state lives only in the right panel; the wireframe center panel is
chrome-only (corner brackets, crosshair, `// PERCEPTION ACTIVE`, `SRC NxN`);
the minimap left panel shows spatial state + current area label only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, List, Optional

import pygame

from openarena_perception.hud_schema import STATE_FILE
from openarena_perception.navigation.aas_parser import parse_aas
from openarena_perception.visualization.panels import (
    HUD_WIDTH,
    PANEL_HEIGHT,
    PANEL_LEFT_W,
    PANEL_MINIMAP_SIZE,
    PANEL_STATS_W,
    PANEL_WIREFRAME_SIZE,
    RGB_ALERT,
    RGB_BG,
    RGB_GRID,
    RGB_OK,
    RGB_TEXT,
    RGB_TEXT_DIM,
    MinimapPanel,
    StatsPanel,
    WireframePanel,
)

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_AAS_FALLBACK = PROJECT_ROOT / "maps" / "oa_dm1.aas"


# ── HUD State ────────────────────────────────────────────────────────────────


class HUDState:
    """Parsed state from the game state file.

    Plain class with __init__ defaults (Phase 10 deviation — NOT a @dataclass).
    Carries all Phase 10 fields plus the 7 Phase 12-01 verbose telemetry fields.
    ``load(path)`` tolerates missing/malformed files and returns ``self`` for
    chaining. Attribute access never raises KeyError — defaults apply.
    """

    def __init__(self) -> None:
        # Core player / match state
        self.map_name: str = "unknown"
        self.player_x: float = 0.0
        self.player_y: float = 0.0
        self.player_z: float = 0.0
        self.player_yaw: float = 0.0
        self.health: int = 100
        self.armor: int = 0
        self.ammo: int = 0
        self.weapon: str = "machinegun"
        self.is_alive: bool = True
        self.is_stuck: bool = False
        self.is_recovering: bool = False

        # Route / items / tracked objects
        self.route: list = []
        self.route_idx: int = 0
        self.tours_done: int = 0
        self.items: list = []
        self.tracked_objects: list = []

        # Status + counters
        self.status: str = ""
        self.vision_count: int = 0
        self.anomaly_count: int = 0
        self.stuck_attempts: int = 0
        self.deaths: int = 0
        self.elapsed: float = 0.0

        # Trail + learned map + brain
        self.trail: list = []
        self.learned_map: dict = {}
        self.brain_state: str = ""
        self.disposition: str = ""

        # Minimap bounds (auto-derived in load())
        self.map_min_x: float = -800.0
        self.map_max_x: float = 1200.0
        self.map_min_y: float = 600.0
        self.map_max_y: float = 1800.0

        # Phase 10-03 intent / context fields
        self.intent: dict = {}
        self.intent_history: list = []
        self.problem_history: list = []
        self.area_history: list = []
        self.path_progress: dict = {}
        self.is_paused_for_assess: bool = False
        self.threat_flag: bool = False
        self.advisor_sent: int = 0
        self.advisor_complete: int = 0
        self.advisor_failed: int = 0
        self.proactive_halts: int = 0
        self.visual_pin_hits: int = 0
        self.tick_count: int = 0
        self.current_area: Optional[int] = None

        # Phase 12-01 verbose telemetry
        self.stair_climb_state: Optional[str] = None
        self.swim_edge_state: Optional[str] = None
        self.advisor_last_thought: Optional[str] = None
        self.last_replan_steps: Optional[List[int]] = None
        self.tick_rate_fps: Optional[float] = None
        self.frame_lag_ms: Optional[float] = None
        self.nav_current_step_area: Optional[int] = None

    def load(self, path: Optional[Any] = None) -> "HUDState":
        """Load state from the shared HUD JSON file.

        Tolerant: missing file, malformed JSON, missing keys — all silently
        fall back to existing attribute values. Returns self.
        """
        state_path = Path(path) if path is not None else Path(STATE_FILE)
        try:
            if not state_path.exists():
                return self
            with open(state_path) as f:
                d = json.load(f)
            if not isinstance(d, dict):
                return self

            self.map_name = d.get("map", d.get("map_name", self.map_name))
            self.player_x = float(d.get("x", self.player_x) or 0.0)
            self.player_y = float(d.get("y", self.player_y) or 0.0)
            self.player_z = float(d.get("z", self.player_z) or 0.0)
            self.player_yaw = float(d.get("yaw", self.player_yaw) or 0.0)
            self.health = int(d.get("health", self.health) or 0)
            self.armor = int(d.get("armor", self.armor) or 0)
            self.ammo = int(d.get("ammo", self.ammo) or 0)
            self.weapon = d.get("weapon", self.weapon) or self.weapon
            self.is_alive = bool(d.get("alive", self.is_alive))
            self.is_stuck = bool(d.get("stuck", self.is_stuck))
            self.is_recovering = bool(d.get("recovering", False))

            self.route = d.get("route", self.route) or []
            self.route_idx = int(d.get("route_idx", self.route_idx) or 0)
            self.tours_done = int(d.get("tours_done", self.tours_done) or 0)
            self.items = d.get("items", self.items) or []
            self.tracked_objects = d.get("tracked", self.tracked_objects) or []

            self.status = d.get("status", self.status) or ""
            self.vision_count = int(d.get("vision_count", 0) or 0)
            self.anomaly_count = int(d.get("anomaly_count", 0) or 0)
            self.stuck_attempts = int(d.get("stuck_attempts", 0) or 0)
            self.deaths = int(d.get("deaths", 0) or 0)
            self.elapsed = float(d.get("elapsed", 0.0) or 0.0)

            self.learned_map = d.get("learned_map") or {}
            self.brain_state = d.get("brain_state", "") or ""
            self.disposition = d.get("disposition", "") or ""

            # Phase 10-03 intent / context fields
            self.intent = d.get("intent") or {}
            self.intent_history = d.get("intent_history") or []
            self.problem_history = d.get("problem_history") or []
            self.area_history = d.get("area_history") or []
            self.path_progress = d.get("path_progress") or {}
            self.is_paused_for_assess = bool(d.get("is_paused_for_assess", False))
            self.threat_flag = bool(d.get("threat_flag", False))
            self.advisor_sent = int(d.get("advisor_sent", 0) or 0)
            self.advisor_complete = int(d.get("advisor_complete", 0) or 0)
            self.advisor_failed = int(d.get("advisor_failed", 0) or 0)
            self.proactive_halts = int(d.get("proactive_halts", 0) or 0)
            self.visual_pin_hits = int(d.get("visual_pin_hits", 0) or 0)
            self.tick_count = int(d.get("tick_count", 0) or 0)
            self.current_area = d.get("current_area")

            # Phase 12-01 verbose telemetry (None when absent)
            self.stair_climb_state = d.get("stair_climb_state")
            self.swim_edge_state = d.get("swim_edge_state")
            self.advisor_last_thought = d.get("advisor_last_thought")
            self.last_replan_steps = d.get("last_replan_steps")
            tick_rate = d.get("tick_rate_fps")
            self.tick_rate_fps = float(tick_rate) if tick_rate is not None else None
            frame_lag = d.get("frame_lag_ms")
            self.frame_lag_ms = float(frame_lag) if frame_lag is not None else None
            self.nav_current_step_area = d.get("nav_current_step_area")

            # Trail append + auto bounds
            self.trail.append((self.player_x, self.player_y))
            if len(self.trail) > 500:
                self.trail = self.trail[-500:]

            all_pts = [(self.player_x, self.player_y)]
            for item in self.items:
                if isinstance(item, (list, tuple)) and len(item) >= 3:
                    all_pts.append((item[1], item[2]))
            for wp in self.route:
                if isinstance(wp, (list, tuple)) and len(wp) >= 3:
                    all_pts.append((wp[1], wp[2]))
            if all_pts:
                xs = [p[0] for p in all_pts]
                ys = [p[1] for p in all_pts]
                pad = 200.0
                self.map_min_x = min(xs) - pad
                self.map_max_x = max(xs) + pad
                self.map_min_y = min(ys) - pad
                self.map_max_y = max(ys) + pad
        except Exception:
            pass
        return self


# ── CLI + AAS resolution ─────────────────────────────────────────────────────


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open-Perception — unified 760x720 bot observability HUD",
    )
    parser.add_argument(
        "--aas",
        type=str,
        default=None,
        help="Path to an AAS file. Defaults to auto-detect from HUD state map, "
        "falling back to maps/oa_dm1.aas.",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default=None,
        help="Override the HUD state JSON path (default: ./tmp/oa_hud_state.json).",
    )
    return parser.parse_args(argv)


def _resolve_aas_path(
    cli_aas: Optional[str],
    state_map_name: Optional[str],
) -> Path:
    """Resolve which AAS file to load.

    Priority: --aas CLI -> maps/{state_map_name}.aas -> maps/oa_dm1.aas.
    Raises FileNotFoundError with a clear message if none exist.
    """
    if cli_aas:
        p = Path(cli_aas)
        if p.exists():
            return p
        raise FileNotFoundError(f"--aas path does not exist: {cli_aas}")

    if state_map_name and state_map_name != "unknown":
        candidate = PROJECT_ROOT / "maps" / f"{state_map_name}.aas"
        if candidate.exists():
            return candidate

    if DEFAULT_AAS_FALLBACK.exists():
        return DEFAULT_AAS_FALLBACK

    raise FileNotFoundError(
        f"No AAS file available. Tried --aas, maps/{state_map_name}.aas, "
        f"and fallback {DEFAULT_AAS_FALLBACK}. Pass --aas PATH."
    )


# ── App ──────────────────────────────────────────────────────────────────────


class OpenPerceptionApp:
    """Composes the three panels into the unified 760x720 window (Phase 12.1)."""

    def __init__(
        self,
        aas_graph: Any,
        state_file: Optional[Any] = None,
    ) -> None:
        pygame.init()
        pygame.display.set_caption("Open-Perception")
        self.screen = pygame.display.set_mode((HUD_WIDTH, PANEL_HEIGHT))
        self.clock = pygame.time.Clock()

        # New layout (Phase 12.1): wireframe (top-left square) + minimap
        # (below it, square) on the left; stats on the right full-height.
        self.wireframe_surf = self.screen.subsurface(
            pygame.Rect(0, 0, PANEL_WIREFRAME_SIZE, PANEL_WIREFRAME_SIZE)
        )
        self.minimap_surf = self.screen.subsurface(
            pygame.Rect(0, PANEL_WIREFRAME_SIZE, PANEL_MINIMAP_SIZE, PANEL_MINIMAP_SIZE)
        )
        self.stats_surf = self.screen.subsurface(
            pygame.Rect(PANEL_LEFT_W, 0, PANEL_STATS_W, PANEL_HEIGHT)
        )

        self.minimap = MinimapPanel(width=PANEL_MINIMAP_SIZE, height=PANEL_MINIMAP_SIZE)
        self.wireframe = WireframePanel(
            aas_graph, width=PANEL_WIREFRAME_SIZE, height=PANEL_WIREFRAME_SIZE
        )
        self.stats = StatsPanel(width=PANEL_STATS_W, height=PANEL_HEIGHT)

        # Status bar font (Pitfall 3: constructed once).
        self.status_font = pygame.font.SysFont("couriernew", 12, bold=True)

        self.state = HUDState()
        self.state_file = (
            Path(state_file) if state_file is not None else Path(STATE_FILE)
        )

        self.running = True
        self.start_time = time.time()

    # ------------------------------------------------------------------
    def _draw_separators(self) -> None:
        # Absolute parent coordinates — Pitfall 1.
        # Vertical: between left column and stats panel.
        x_split = PANEL_LEFT_W
        pygame.draw.line(
            self.screen, RGB_GRID, (x_split, 0), (x_split, PANEL_HEIGHT), 2
        )
        # Horizontal: between wireframe and minimap (inside left column only).
        y_split = PANEL_WIREFRAME_SIZE
        pygame.draw.line(
            self.screen, RGB_GRID, (0, y_split), (PANEL_LEFT_W, y_split), 2
        )

    def _draw_status_bar(self, waiting: bool) -> None:
        # Parent-surface absolute coords at the bottom 20px strip.
        bar_h = 20
        bar_y = PANEL_HEIGHT - bar_h
        pygame.draw.rect(
            self.screen, RGB_BG, pygame.Rect(0, bar_y, HUD_WIDTH, bar_h)
        )
        pygame.draw.line(
            self.screen, RGB_GRID, (0, bar_y), (HUD_WIDTH, bar_y), 1
        )
        if waiting:
            text = "WAITING FOR BOT — no ./tmp/oa_hud_state.json yet"
            color = RGB_ALERT
        else:
            alive = "ALIVE" if self.state.is_alive else "DEAD"
            threat = "THREAT" if self.state.threat_flag else "clear"
            elapsed = self.state.elapsed or (time.time() - self.start_time)
            text = (
                f"map={self.state.map_name}  "
                f"elapsed={elapsed:6.1f}s  "
                f"{alive}  threat={threat}"
            )
            color = RGB_OK if self.state.is_alive else RGB_ALERT
        surf = self.status_font.render(text, True, color)
        self.screen.blit(surf, (8, bar_y + 4))

    def _draw_waiting_placeholder(self) -> None:
        """Minimal placeholder when no state file exists yet (Pitfall 9)."""
        self.screen.fill(RGB_BG)
        font = self.status_font
        msg = font.render(
            "Open-Perception — waiting for bot (start item_tour.py)",
            True,
            RGB_TEXT_DIM,
        )
        rect = msg.get_rect(center=(HUD_WIDTH // 2, PANEL_HEIGHT // 2))
        self.screen.blit(msg, rect)

    # ------------------------------------------------------------------
    def draw_tick(self) -> None:
        """Draw one frame based on the currently loaded state."""
        waiting = not self.state_file.exists()
        if waiting:
            self._draw_waiting_placeholder()
        else:
            self.screen.fill(RGB_BG)
            self.minimap.draw(self.state, self.minimap_surf)
            self.wireframe.draw(self.state, self.wireframe_surf)
            self.stats.draw(self.state, self.stats_surf)
        self._draw_separators()
        self._draw_status_bar(waiting)
        pygame.display.flip()

    def run(self) -> int:
        """Main loop. Exits cleanly on pygame.QUIT."""
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    break
            if not self.running:
                break
            self.state.load(self.state_file)
            self.draw_tick()
            self.clock.tick(10)
        pygame.quit()
        return 0


def _peek_state_map_name(state_file: Path) -> Optional[str]:
    """Read only the ``map`` field from the state file without a full load.

    Used at startup to pick an AAS before the main loop begins. Returns
    None if the file does not exist or cannot be parsed.
    """
    try:
        if not state_file.exists():
            return None
        with open(state_file) as f:
            d = json.load(f)
        if not isinstance(d, dict):
            return None
        return d.get("map") or d.get("map_name")
    except Exception:
        return None


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    state_file = Path(args.state_file) if args.state_file else Path(STATE_FILE)
    state_map_name = _peek_state_map_name(state_file)

    aas_path = _resolve_aas_path(args.aas, state_map_name)
    graph = parse_aas(str(aas_path))
    if graph is None:
        print(
            f"[open_perception] Failed to parse AAS file: {aas_path}",
            file=sys.stderr,
        )
        return 2

    app = OpenPerceptionApp(graph, state_file=state_file)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
