#!/usr/bin/env python3
"""
strategic_hud.py — Pygame strategic overview HUD.

Shows a real-time 2D minimap with:
  - Player position + heading arrow
  - Route waypoints + progress
  - Visited/surveyed rooms
  - Current objective + disposition
  - Error state (stuck/lost/disoriented)
  - Tracked objects
  - Room survey summaries

Reads game state from a shared file (./tmp/oa_hud_state.json under the
project root) that item_tour or play.py writes every tick.

Usage:
    python strategic_hud.py              # launch the HUD window
    python strategic_hud.py --port 5555  # or listen on a UDP port
"""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import pygame
from typing import Tuple

# ── Config ──────────────────────────────────────────────────────────

HUD_WIDTH = 600
HUD_HEIGHT = 700
MINIMAP_SIZE = 400
FPS = 10
# Phase 10-01: project-root-relative runtime dir. strategic_hud.py lives at
# the repo root, so Path(__file__).parent IS the project root. This file
# stays standalone -- it MUST NOT import from openarena_perception
# (Pitfall 1: HUD machine may not have opencv/mss/numpy installed).
STATE_FILE = str(Path(__file__).resolve().parent / "tmp" / "oa_hud_state.json")
SURVEY_DIR = os.path.join(os.path.dirname(__file__), "room_surveys")

# Colors
BG = (20, 20, 30)
GRID = (40, 40, 55)
PLAYER = (0, 255, 100)
PLAYER_TRAIL = (0, 120, 50)
WAYPOINT_DONE = (80, 80, 80)
WAYPOINT_NEXT = (255, 200, 0)
WAYPOINT_FUTURE = (100, 100, 150)
ITEM_WEAPON = (255, 100, 50)
ITEM_HEALTH = (50, 255, 50)
ITEM_ARMOR = (255, 255, 50)
ITEM_POWERUP = (100, 100, 255)
ROOM_SURVEYED = (40, 60, 40)
ENEMY = (255, 0, 0)
LOCKED = (255, 0, 255)
TEXT_COLOR = (200, 200, 200)
TEXT_DIM = (120, 120, 140)
ALERT_COLOR = (255, 80, 80)
OK_COLOR = (80, 255, 80)


# ── HUD State ───────────────────────────────────────────────────────

class HUDState:
    """Parsed state from the game."""
    def __init__(self):
        self.map_name = "unknown"
        self.player_x = 0.0
        self.player_y = 0.0
        self.player_z = 0.0
        self.player_yaw = 0.0
        self.health = 100
        self.armor = 0
        self.ammo = 0
        self.weapon = "machinegun"
        self.is_alive = True
        self.is_stuck = False
        self.is_recovering = False

        # Route
        self.route = []           # [(name, x, y, z), ...]
        self.route_idx = 0
        self.tours_done = 0

        # Items on map
        self.items = []           # [(name, x, y, z), ...]

        # Tracked objects
        self.tracked_objects = [] # [(id, cx, cy, label, locked), ...]

        # Surveys
        self.surveys = {}         # area_id -> {room_type, exits, summary}

        # Status
        self.status = ""
        self.vision_count = 0
        self.anomaly_count = 0
        self.stuck_attempts = 0
        self.deaths = 0
        self.elapsed = 0.0

        # Trail
        self.trail = []           # [(x, y), ...] recent positions

        # Learned map data
        self.learned_map = {}     # from strategic brain export
        self.brain_state = ""
        self.disposition = ""

        # Map bounds (for minimap scaling)
        self.map_min_x = -800
        self.map_max_x = 1200
        self.map_min_y = 600
        self.map_max_y = 1800

    def load(self):
        """Load state from shared file."""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE) as f:
                    d = json.load(f)
                self.map_name = d.get("map", self.map_name)
                self.player_x = d.get("x", self.player_x)
                self.player_y = d.get("y", self.player_y)
                self.player_z = d.get("z", self.player_z)
                self.player_yaw = d.get("yaw", self.player_yaw)
                self.health = d.get("health", self.health)
                self.armor = d.get("armor", self.armor)
                self.ammo = d.get("ammo", self.ammo)
                self.weapon = d.get("weapon", self.weapon)
                self.is_alive = d.get("alive", self.is_alive)
                self.is_stuck = d.get("stuck", self.is_stuck)
                self.is_recovering = d.get("recovering", False)
                self.route = d.get("route", self.route)
                self.route_idx = d.get("route_idx", self.route_idx)
                self.tours_done = d.get("tours_done", self.tours_done)
                self.items = d.get("items", self.items)
                self.tracked_objects = d.get("tracked", self.tracked_objects)
                self.status = d.get("status", self.status)
                self.vision_count = d.get("vision_count", 0)
                self.anomaly_count = d.get("anomaly_count", 0)
                self.stuck_attempts = d.get("stuck_attempts", 0)
                self.deaths = d.get("deaths", 0)
                self.elapsed = d.get("elapsed", 0.0)
                self.learned_map = d.get("learned_map", {})
                self.brain_state = d.get("brain_state", "")
                self.disposition = d.get("disposition", "")

                # Update trail
                self.trail.append((self.player_x, self.player_y))
                if len(self.trail) > 500:
                    self.trail = self.trail[-500:]

                # Auto-detect map bounds from items
                all_pts = [(self.player_x, self.player_y)]
                for item in self.items:
                    if len(item) >= 3:
                        all_pts.append((item[1], item[2]))
                for wp in self.route:
                    if len(wp) >= 3:
                        all_pts.append((wp[1], wp[2]))
                if all_pts:
                    xs = [p[0] for p in all_pts]
                    ys = [p[1] for p in all_pts]
                    pad = 200
                    self.map_min_x = min(xs) - pad
                    self.map_max_x = max(xs) + pad
                    self.map_min_y = min(ys) - pad
                    self.map_max_y = max(ys) + pad

        except Exception:
            pass

    def load_surveys(self):
        """Load room survey data."""
        import glob
        self.surveys = {}
        for path in glob.glob(os.path.join(SURVEY_DIR, "area_*.json")):
            try:
                with open(path) as f:
                    d = json.load(f)
                aid = d["area_id"]
                self.surveys[aid] = {
                    "pos": d.get("position", [0,0,0]),
                    "room_type": d.get("room_type", ""),
                    "exits": len(d.get("exits", [])),
                    "summary": d.get("summary", "")[:60],
                }
            except Exception:
                pass


# ── Drawing ──────────────────────────────────────────────────────────

class StrategicHUD:

    def __init__(self, state: HUDState):
        self.state = state
        pygame.init()
        self.screen = pygame.display.set_mode((HUD_WIDTH, HUD_HEIGHT))
        pygame.display.set_caption(f"OpenArena Strategic HUD — {state.map_name}")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("monospace", 13)
        self.font_lg = pygame.font.SysFont("monospace", 16, bold=True)
        self.font_sm = pygame.font.SysFont("monospace", 10)

    def world_to_minimap(self, wx: float, wy: float) -> Tuple[int, int]:
        """Convert world coords to minimap pixel coords.
        Q3 world: +X=east, +Y=north. Pygame: +X=right, +Y=down.
        So we map world X→screen X, world Y→screen Y (inverted)."""
        s = self.state
        rx = (wx - s.map_min_x) / max(s.map_max_x - s.map_min_x, 1)
        ry = (wy - s.map_min_y) / max(s.map_max_y - s.map_min_y, 1)
        margin = (HUD_WIDTH - MINIMAP_SIZE) // 2
        mx = margin + int(rx * MINIMAP_SIZE)
        my = 50 + MINIMAP_SIZE - int(ry * MINIMAP_SIZE)  # invert Y
        return (mx, my)

    def draw(self):
        s = self.state
        self.screen.fill(BG)

        # ── Header ──
        title = f"MAP: {s.map_name}  |  Tour #{s.tours_done + 1}"
        self._text(title, HUD_WIDTH // 2, 10, self.font_lg, TEXT_COLOR, center=True)

        # ── Minimap background ──
        margin = (HUD_WIDTH - MINIMAP_SIZE) // 2
        map_rect = pygame.Rect(margin, 50, MINIMAP_SIZE, MINIMAP_SIZE)
        pygame.draw.rect(self.screen, (30, 30, 40), map_rect)
        pygame.draw.rect(self.screen, GRID, map_rect, 1)

        # Grid lines
        for i in range(1, 4):
            gx = margin + i * MINIMAP_SIZE // 4
            gy = 50 + i * MINIMAP_SIZE // 4
            pygame.draw.line(self.screen, GRID, (gx, 50), (gx, 50 + MINIMAP_SIZE))
            pygame.draw.line(self.screen, GRID, (margin, gy), (margin + MINIMAP_SIZE, gy))

        # ── Learned map: occupancy grid ──
        lm = s.learned_map
        if lm and lm.get("grid_cells"):
            origin = lm.get("grid_origin", [0, 0])
            res = lm.get("grid_resolution", 64)
            CELL_COLORS = {
                1: (30, 80, 30),    # OPEN: dark green
                2: (180, 40, 40),   # WALL: red
                3: (40, 70, 40),    # VISITED: brighter green
                4: (40, 40, 180),   # LIQUID: blue
            }
            for gx_c, gy_c, state in lm["grid_cells"]:
                color = CELL_COLORS.get(state)
                if not color:
                    continue
                wx = origin[0] + (gx_c + 0.5) * res
                wy = origin[1] + (gy_c + 0.5) * res
                sx, sy = self.world_to_minimap(wx, wy)
                # Semi-transparent cell
                cell_surf = pygame.Surface((4, 4), pygame.SRCALPHA)
                cell_surf.fill((*color, 80))
                self.screen.blit(cell_surf, (sx - 2, sy - 2))

        # ── Learned map: wall segments ──
        if lm and lm.get("wall_segments"):
            for seg in lm["wall_segments"]:
                if len(seg) >= 5:
                    sx1, sy1 = self.world_to_minimap(seg[0], seg[1])
                    sx2, sy2 = self.world_to_minimap(seg[2], seg[3])
                    conf = seg[4]
                    thickness = min(3, 1 + conf // 3)
                    pygame.draw.line(self.screen, (255, 60, 60),
                                     (sx1, sy1), (sx2, sy2), thickness)

        # ── Surveyed rooms ──
        for aid, info in s.surveys.items():
            pos = info["pos"]
            sx, sy = self.world_to_minimap(pos[0], pos[1])
            pygame.draw.circle(self.screen, ROOM_SURVEYED, (sx, sy), 8)

        # ── Items on map ──
        for item in s.items:
            if len(item) < 3:
                continue
            name, ix, iy = item[0], item[1], item[2]
            mx, my = self.world_to_minimap(ix, iy)
            if "weapon" in name:
                color = ITEM_WEAPON
            elif "health" in name:
                color = ITEM_HEALTH
            elif "armor" in name:
                color = ITEM_ARMOR
            elif "quad" in name or "invis" in name:
                color = ITEM_POWERUP
            else:
                color = TEXT_DIM
            pygame.draw.circle(self.screen, color, (mx, my), 3)

        # ── Route waypoints ──
        for i, wp in enumerate(s.route):
            if len(wp) < 3:
                continue
            wx, wy = self.world_to_minimap(wp[1], wp[2])
            if i < s.route_idx:
                color = WAYPOINT_DONE
                r = 4
            elif i == s.route_idx:
                color = WAYPOINT_NEXT
                r = 7
            else:
                color = WAYPOINT_FUTURE
                r = 5
            pygame.draw.circle(self.screen, color, (wx, wy), r, 1 if i < s.route_idx else 0)
            self._text(str(i+1), wx+8, wy-6, self.font_sm, color)

        # Draw route line
        if len(s.route) > 1:
            pts = []
            for wp in s.route:
                if len(wp) >= 3:
                    pts.append(self.world_to_minimap(wp[1], wp[2]))
            if len(pts) > 1:
                pygame.draw.lines(self.screen, (60, 60, 80), False, pts, 1)

        # ── Player trail ──
        if len(s.trail) > 2:
            trail_pts = [self.world_to_minimap(x, y) for x, y in s.trail[-100:]]
            if len(trail_pts) > 2:
                pygame.draw.lines(self.screen, PLAYER_TRAIL, False, trail_pts, 1)

        # ── Player position + heading ──
        px, py = self.world_to_minimap(s.player_x, s.player_y)
        pygame.draw.circle(self.screen, PLAYER, (px, py), 6)
        # Heading arrow — atan2(dy,dx) convention, screen Y inverted
        rad = math.radians(s.player_yaw)
        ax = px + int(math.cos(rad) * 15)
        ay = py - int(math.sin(rad) * 15)
        pygame.draw.line(self.screen, PLAYER, (px, py), (ax, ay), 2)

        # ── Info panel below minimap ──
        panel_y = 50 + MINIMAP_SIZE + 15

        # Disposition bar
        self._text("DISPOSITION", 20, panel_y, self.font_lg, TEXT_COLOR)
        panel_y += 20

        # Health bar
        hp = max(0, min(200, s.health or 0))
        hp_color = OK_COLOR if hp > 50 else ALERT_COLOR
        pygame.draw.rect(self.screen, (40, 40, 40), (20, panel_y, 200, 14))
        pygame.draw.rect(self.screen, hp_color, (20, panel_y, hp, 14))
        self._text(f"HP: {hp}", 230, panel_y, self.font, hp_color)
        panel_y += 18

        # Armor bar
        ar = max(0, min(200, s.armor or 0))
        ar_color = (100, 200, 255)
        pygame.draw.rect(self.screen, (40, 40, 40), (20, panel_y, 200, 14))
        pygame.draw.rect(self.screen, ar_color, (20, panel_y, ar, 14))
        self._text(f"AR: {ar}", 230, panel_y, self.font, ar_color)
        panel_y += 22

        # Weapon + ammo
        self._text(f"Weapon: {s.weapon or '?'}  Ammo: {s.ammo or '?'}",
                   20, panel_y, self.font, TEXT_COLOR)
        panel_y += 18

        # Position
        self._text(f"Pos: ({s.player_x:.0f}, {s.player_y:.0f}, {s.player_z:.0f}) "
                   f"Yaw: {s.player_yaw:.0f}",
                   20, panel_y, self.font, TEXT_DIM)
        panel_y += 22

        # ── Objective ──
        self._text("OBJECTIVE", 20, panel_y, self.font_lg, WAYPOINT_NEXT)
        panel_y += 20
        if s.route_idx < len(s.route):
            wp = s.route[s.route_idx]
            name = wp[0] if len(wp) > 0 else "?"
            self._text(f"[{s.route_idx+1}/{len(s.route)}] → {name}",
                       20, panel_y, self.font, WAYPOINT_NEXT)
        else:
            self._text("Tour complete!", 20, panel_y, self.font, OK_COLOR)
        panel_y += 20

        # ── Status ──
        self._text("STATUS", 20, panel_y, self.font_lg, TEXT_COLOR)
        panel_y += 20

        # Error state
        if not s.is_alive:
            self._text("DEAD — respawning...", 20, panel_y, self.font, ALERT_COLOR)
        elif s.is_stuck:
            self._text(f"STUCK (attempt #{s.stuck_attempts})", 20, panel_y, self.font, ALERT_COLOR)
        elif s.is_recovering:
            self._text("Recovering from stuck...", 20, panel_y, self.font, (255, 200, 0))
        else:
            self._text("Navigating", 20, panel_y, self.font, OK_COLOR)
        panel_y += 18

        # Stats
        self._text(f"Time: {s.elapsed:.0f}s  Deaths: {s.deaths}  "
                   f"Vision: {s.vision_count}  Anomalies: {s.anomaly_count}",
                   20, panel_y, self.font, TEXT_DIM)
        panel_y += 18

        if s.status:
            self._text(s.status[:70], 20, panel_y, self.font_sm, TEXT_DIM)
        panel_y += 22

        # ── Brain state ──
        if s.brain_state:
            state_color = OK_COLOR if s.brain_state in ("navigating", "exploring") else ALERT_COLOR
            if s.brain_state == "combat":
                state_color = (255, 0, 0)
            self._text(f"BRAIN: {s.brain_state.upper()}  |  {s.disposition}",
                       20, panel_y, self.font_lg, state_color)
            panel_y += 20

        # ── Mapping stats ──
        lm_stats = s.learned_map.get("stats", {}) if s.learned_map else {}
        if lm_stats:
            visited = lm_stats.get("visited_cells", 0)
            walls = lm_stats.get("wall_cells", 0)
            segs = lm_stats.get("wall_segments", 0)
            failed = lm_stats.get("failed_edges", 0)
            self._text(f"MAP: {visited} visited  {walls} walls  {segs} segs  {failed} bad edges",
                       20, panel_y, self.font, (100, 180, 100))
            panel_y += 18

        # ── Tracked objects ──
        if s.tracked_objects:
            self._text("TRACKED OBJECTS", 20, panel_y, self.font_lg, LOCKED)
            panel_y += 18
            for obj in s.tracked_objects[:3]:
                oid = obj[0] if len(obj) > 0 else 0
                label = obj[3] if len(obj) > 3 else "?"
                locked = obj[4] if len(obj) > 4 else False
                prefix = ">>>" if locked else "   "
                color = LOCKED if locked else TEXT_DIM
                self._text(f"{prefix} #{oid}: {label}", 20, panel_y, self.font, color)
                panel_y += 14

        pygame.display.flip()

    def _text(self, text: str, x: int, y: int, font, color, center=False):
        surf = font.render(text, True, color)
        if center:
            x -= surf.get_width() // 2
        self.screen.blit(surf, (x, y))

    def run(self):
        running = True
        self.state.load_surveys()

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q or event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r:
                        self.state.load_surveys()

            self.state.load()
            self.draw()
            self.clock.tick(FPS)

        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description="Strategic HUD")
    parser.parse_args()

    state = HUDState()
    state.load_surveys()
    hud = StrategicHUD(state)
    hud.run()


if __name__ == "__main__":
    main()
