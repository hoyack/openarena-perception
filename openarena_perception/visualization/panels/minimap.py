"""MinimapPanel — top-down minimap for Open-Perception (Phase 12-02).

Extracted from the legacy Phase 10 HUD minimap rendering code
(world_to_minimap + draw minimap block). Adapted to render into a
sub-surface with (0,0) relative coordinates so the parent app composes
it onto the main window.

Deduplication contract (Phase 12): NO HP/POS/YAW/AMMO text — those live in
StatsPanel. The minimap shows spatial state only: learned map cells, wall
segments, surveyed rooms, items, route, player trail, player marker with
yaw arrow, and current area label.

Pitfall 1: all drawing uses sub-surface (0,0)-relative coordinates. The
panel never touches pixels outside the handed-in surface.
Pitfall 3: pygame fonts created in __init__, never at module load time.
Pitfall 10: map bounds are latched on first successful bounds read so the
minimap does not flicker as new waypoints/items stream in.
"""

from __future__ import annotations

import math
from typing import Any, Optional, Tuple

import pygame

from openarena_perception.navigation.aas_parser import areas_on_floor
from openarena_perception.visualization.panels import (
    RGB_BG,
    RGB_CORNER,
    RGB_FITTED_WALL,
    RGB_GRID,
    RGB_ITEM_ARMOR,
    RGB_ITEM_HEALTH,
    RGB_ITEM_POWERUP,
    RGB_ITEM_WEAPON,
    RGB_PLAYER,
    RGB_PLAYER_TRAIL,
    RGB_ROOM_OUTLINE,
    RGB_ROOM_OUTLINE_CUR,
    RGB_ROOM_SURVEYED,
    RGB_TEXT_DIM,
    RGB_WAYPOINT_DONE,
    RGB_WAYPOINT_FUTURE,
    RGB_WAYPOINT_NEXT,
)


class MinimapPanel:
    """Top-down minimap renderer for the Open-Perception left column."""

    def __init__(
        self,
        aas_graph: Any = None,
        width: int = 360,
        height: int = 360,
    ) -> None:
        self.width = width
        self.height = height
        self._aas_graph = aas_graph
        # Pitfall 3: font constructed here, not at module import.
        self.font = pygame.font.SysFont("couriernew", 12)
        self.font_sm = pygame.font.SysFont("couriernew", 10)
        # Latched bounds (Pitfall 10). None until first successful populate.
        self._bounds: Optional[Tuple[float, float, float, float]] = None
        # Square layout (Phase 12.1): tight margins, one-line area label at top.
        self._map_margin = 8
        self._map_top = 24  # 12px label + 12px gap
        self._map_size = min(
            width - 2 * self._map_margin,
            height - self._map_top - self._map_margin,
        )

    # ------------------------------------------------------------------
    def _draw_aas_overhead(self, state: Any, surface: pygame.Surface) -> None:
        """Dim fill of AAS areas whose z-range contains bot_z (Plan 12.1-01)."""
        if self._aas_graph is None:
            return
        bot_z = float(getattr(state, "player_z", 0.0) or 0.0)
        try:
            floor_ids = areas_on_floor(self._aas_graph, bot_z, z_tolerance=24.0)
        except Exception:
            return
        fill_color = (35, 45, 60)
        outline_color = RGB_GRID
        areas = self._aas_graph.areas
        for aid in floor_ids:
            if aid <= 0 or aid >= len(areas):
                continue
            a = areas[aid]
            x0, y0 = self._world_to_minimap(a.mins[0], a.mins[1])
            x1, y1 = self._world_to_minimap(a.maxs[0], a.maxs[1])
            rx = min(x0, x1)
            ry = min(y0, y1)
            rw = max(1, abs(x1 - x0))
            rh = max(1, abs(y1 - y0))
            rect = pygame.Rect(rx, ry, rw, rh)
            pygame.draw.rect(surface, fill_color, rect)
            pygame.draw.rect(surface, outline_color, rect, 1)

    # ------------------------------------------------------------------
    def _latch_bounds(self, state: Any) -> None:
        """Populate self._bounds on first valid state. Never widens later."""
        if self._bounds is not None:
            return
        min_x = getattr(state, "map_min_x", None)
        max_x = getattr(state, "map_max_x", None)
        min_y = getattr(state, "map_min_y", None)
        max_y = getattr(state, "map_max_y", None)
        if None in (min_x, max_x, min_y, max_y):
            return
        if max_x <= min_x or max_y <= min_y:
            return
        self._bounds = (float(min_x), float(max_x), float(min_y), float(max_y))

    def _world_to_minimap(self, wx: float, wy: float) -> Tuple[int, int]:
        """Convert Q3 world (X east, Y north) to sub-surface pixel coords.

        Returns (0,0)-relative pixel coordinates inside the minimap square.
        Pygame Y is inverted (down = positive).
        """
        assert self._bounds is not None
        min_x, max_x, min_y, max_y = self._bounds
        rx = (wx - min_x) / max(max_x - min_x, 1.0)
        ry = (wy - min_y) / max(max_y - min_y, 1.0)
        mx = self._map_margin + int(rx * self._map_size)
        my = self._map_top + self._map_size - int(ry * self._map_size)
        return (mx, my)

    # ------------------------------------------------------------------
    def draw(self, state: Any, surface: pygame.Surface) -> None:
        """Render minimap into the given sub-surface at sub-surface origin."""
        surface.fill(RGB_BG)
        self._latch_bounds(state)

        # If bounds not yet available, draw placeholder and return.
        if self._bounds is None:
            placeholder = self.font.render(
                "waiting for state...", True, RGB_TEXT_DIM
            )
            surface.blit(placeholder, (10, 10))
            return

        # --- Minimap background square + grid ---
        map_rect = pygame.Rect(
            self._map_margin, self._map_top, self._map_size, self._map_size
        )
        pygame.draw.rect(surface, (30, 30, 40), map_rect)
        pygame.draw.rect(surface, RGB_GRID, map_rect, 1)
        for i in range(1, 4):
            gx = self._map_margin + i * self._map_size // 4
            gy = self._map_top + i * self._map_size // 4
            pygame.draw.line(
                surface,
                RGB_GRID,
                (gx, self._map_top),
                (gx, self._map_top + self._map_size),
            )
            pygame.draw.line(
                surface,
                RGB_GRID,
                (self._map_margin, gy),
                (self._map_margin + self._map_size, gy),
            )

        # --- AAS overhead (dim current-floor polygons, under learned cells) ---
        self._draw_aas_overhead(state, surface)

        # --- Learned map: occupancy grid (learned-path emphasis) ---
        lm = getattr(state, "learned_map", None) or {}
        if lm.get("grid_cells"):
            origin = lm.get("grid_origin", [0, 0])
            res = lm.get("grid_resolution", 64)
            # (color, brush_size, alpha) — VISITED is brighter+larger than OPEN.
            cell_colors = {
                1: ((30, 80, 30), 4, 80),    # OPEN    — dim small
                2: ((180, 40, 40), 4, 120),  # WALL
                3: ((60, 180, 60), 6, 220),  # VISITED — brighter + larger
                4: ((40, 40, 180), 4, 100),  # LIQUID
            }
            for cell in lm["grid_cells"]:
                if len(cell) < 3:
                    continue
                gx_c, gy_c, cell_state = cell[0], cell[1], cell[2]
                entry = cell_colors.get(cell_state)
                if not entry:
                    continue
                color, size, alpha = entry
                wx = origin[0] + (gx_c + 0.5) * res
                wy = origin[1] + (gy_c + 0.5) * res
                sx, sy = self._world_to_minimap(wx, wy)
                cell_surf = pygame.Surface((size, size), pygame.SRCALPHA)
                cell_surf.fill((*color, alpha))
                surface.blit(cell_surf, (sx - size // 2, sy - size // 2))

        # --- Phase 13: room polygons (alpha fill + outline) ---
        rooms = lm.get("rooms", []) if lm else []
        current_room_id = lm.get("current_room_id") if lm else None
        for room in rooms:
            verts = room.get("polygon_vertices", [])
            if len(verts) < 3:
                continue
            screen_verts = [
                self._world_to_minimap(float(v[0]), float(v[1]))
                for v in verts
            ]
            is_current = room.get("id") == current_room_id
            outline_color = RGB_ROOM_OUTLINE_CUR if is_current else RGB_ROOM_OUTLINE
            fill_alpha = 80 if is_current else 50
            # Alpha fill via SRCALPHA temp surface, blitted at the polygon AABB.
            min_x = min(p[0] for p in screen_verts)
            min_y = min(p[1] for p in screen_verts)
            max_x = max(p[0] for p in screen_verts)
            max_y = max(p[1] for p in screen_verts)
            w = max(1, max_x - min_x + 2)
            h = max(1, max_y - min_y + 2)
            poly_surf = pygame.Surface((w, h), pygame.SRCALPHA)
            local_verts = [
                (p[0] - min_x + 1, p[1] - min_y + 1) for p in screen_verts
            ]
            pygame.draw.polygon(
                poly_surf, (*outline_color, fill_alpha), local_verts
            )
            surface.blit(poly_surf, (min_x - 1, min_y - 1))
            # Outline on main surface — current room gets a 2px stroke.
            pygame.draw.polygon(
                surface,
                outline_color,
                screen_verts,
                width=2 if is_current else 1,
            )

        # --- Phase 13: fitted walls (bright green, 2px) ---
        # Schema: [id, x1, y1, x2, y2, confidence, support_count, first_seen, last_seen]
        fitted_walls = lm.get("fitted_walls", []) if lm else []
        for fw in fitted_walls:
            if len(fw) < 5:
                continue
            x1, y1, x2, y2 = float(fw[1]), float(fw[2]), float(fw[3]), float(fw[4])
            sx1, sy1 = self._world_to_minimap(x1, y1)
            sx2, sy2 = self._world_to_minimap(x2, y2)
            pygame.draw.line(
                surface, RGB_FITTED_WALL, (sx1, sy1), (sx2, sy2), 2
            )

        # --- Phase 13: corners (amber filled circles) ---
        # Schema: [id, x, y, wall_a_id, wall_b_id, angle_deg, confidence]
        corners = lm.get("corners", []) if lm else []
        for c in corners:
            if len(c) < 3:
                continue
            cx, cy = float(c[1]), float(c[2])
            scx, scy = self._world_to_minimap(cx, cy)
            pygame.draw.circle(surface, RGB_CORNER, (scx, scy), 3)

        # --- Surveyed rooms ---
        surveys = getattr(state, "surveys", {}) or {}
        for _aid, info in surveys.items():
            pos = info.get("pos") if isinstance(info, dict) else None
            if not pos or len(pos) < 2:
                continue
            sx, sy = self._world_to_minimap(pos[0], pos[1])
            pygame.draw.circle(surface, RGB_ROOM_SURVEYED, (sx, sy), 8)

        # --- Items on map ---
        for item in getattr(state, "items", []) or []:
            if len(item) < 3:
                continue
            name, ix, iy = item[0], item[1], item[2]
            if "weapon" in name:
                color = RGB_ITEM_WEAPON
            elif "health" in name:
                color = RGB_ITEM_HEALTH
            elif "armor" in name:
                color = RGB_ITEM_ARMOR
            elif "quad" in name or "invis" in name:
                color = RGB_ITEM_POWERUP
            else:
                color = RGB_TEXT_DIM
            mx, my = self._world_to_minimap(ix, iy)
            pygame.draw.circle(surface, color, (mx, my), 3)

        # --- Route waypoints + line ---
        route = getattr(state, "route", []) or []
        route_idx = int(getattr(state, "route_idx", 0) or 0)
        for i, wp in enumerate(route):
            if len(wp) < 3:
                continue
            wx, wy = self._world_to_minimap(wp[1], wp[2])
            if i < route_idx:
                color, r = RGB_WAYPOINT_DONE, 4
                width = 1
            elif i == route_idx:
                color, r = RGB_WAYPOINT_NEXT, 7
                width = 0
            else:
                color, r = RGB_WAYPOINT_FUTURE, 5
                width = 0
            pygame.draw.circle(surface, color, (wx, wy), r, width)
            label = self.font_sm.render(str(i + 1), True, color)
            surface.blit(label, (wx + 8, wy - 6))
        if len(route) > 1:
            pts = [
                self._world_to_minimap(wp[1], wp[2])
                for wp in route
                if len(wp) >= 3
            ]
            if len(pts) > 1:
                pygame.draw.lines(surface, (60, 60, 80), False, pts, 1)

        # --- Player trail ---
        trail = getattr(state, "trail", []) or []
        if len(trail) > 2:
            trail_pts = [self._world_to_minimap(x, y) for x, y in trail[-100:]]
            if len(trail_pts) > 2:
                pygame.draw.lines(
                    surface, RGB_PLAYER_TRAIL, False, trail_pts, 2
                )

        # --- Player + yaw arrow ---
        px, py = self._world_to_minimap(
            float(getattr(state, "player_x", 0.0)),
            float(getattr(state, "player_y", 0.0)),
        )
        pygame.draw.circle(surface, RGB_PLAYER, (px, py), 6)
        yaw = float(getattr(state, "player_yaw", 0.0))
        rad = math.radians(yaw)
        ax = px + int(math.cos(rad) * 15)
        ay = py - int(math.sin(rad) * 15)
        pygame.draw.line(surface, RGB_PLAYER, (px, py), (ax, ay), 2)

        # --- Current area label (top) ---
        area_id = getattr(state, "nav_current_step_area", None)
        if area_id is None:
            area_id = getattr(state, "current_area", None)
        label_txt = f"area {area_id}" if area_id is not None else "area ---"
        label_surf = self.font.render(label_txt, True, RGB_PLAYER)
        surface.blit(label_surf, (self._map_margin, 6))
