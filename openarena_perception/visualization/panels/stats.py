"""StatsPanel — vital stats + intent + history + problems + verbose.

Phase 12-02 Task 3 implementation. Renders six sub-blocks stacked
vertically inside a 400x700 sub-surface:

    y=  0, h=120  Vital stats (HP, armor, ammo, weapon, pos, yaw)
    y=120, h=110  Intent block (macro, sub, duration, pause-flash border)
    y=230, h=100  Intent history (5 dim rows)
    y=330, h=100  Problem history (5 color-coded rows)
    y=430, h= 40  Path progress (Step N/M + filled yellow bar)
    y=470, h=230  Verbose telemetry (9 rows with dimmed placeholders)

All drawing is sub-surface (0,0)-relative. Fonts constructed in
__init__ (Pitfall 3). Colors from panels/__init__.py RGB_ constants only
(Pitfall 2). Verbose rows render "----" placeholders when None so layout
is stable frame-over-frame.
"""

from __future__ import annotations

import time
from typing import Any, List, Optional, Tuple

import pygame

from openarena_perception.visualization.panels import (
    RGB_ALERT,
    RGB_BG,
    RGB_GRID,
    RGB_INTENT_CURRENT,
    RGB_INTENT_HISTORY,
    RGB_INTENT_LABEL,
    RGB_INTENT_SUB,
    RGB_OK,
    RGB_PAUSE_BORDER,
    RGB_PROBLEM_ADVISOR,
    RGB_PROBLEM_PIN,
    RGB_PROBLEM_RESPAWN,
    RGB_PROBLEM_STUCK,
    RGB_PROBLEM_WALL,
    RGB_TEXT,
    RGB_TEXT_DIM,
)

_FRAME_LAG_WARN_MS = 100.0
_PLACEHOLDER = "----"


class StatsPanel:
    """Right-column stats/intent/verbose renderer."""

    def __init__(self, width: int = 400, height: int = 700) -> None:
        self.width = width
        self.height = height
        # Pitfall 3: fonts in __init__ only.
        self.font_big = pygame.font.SysFont("couriernew", 22, bold=True)
        self.font_med = pygame.font.SysFont("couriernew", 14)
        self.font_small = pygame.font.SysFont("couriernew", 12)
        self.font_label = pygame.font.SysFont("couriernew", 11, bold=True)
        self.font_lg = pygame.font.SysFont("couriernew", 16, bold=True)

        # Sub-block origins (y offsets)
        self.y_vital = 0
        self.y_intent = 120
        self.y_history = 230
        self.y_problems = 330
        self.y_path = 430
        self.y_verbose = 470
        self.pad_x = 10

    # ------------------------------------------------------------------
    def _text(
        self,
        surface: pygame.Surface,
        text: str,
        x: int,
        y: int,
        font: pygame.font.Font,
        color: Tuple[int, int, int],
    ) -> None:
        surf = font.render(text, True, color)
        surface.blit(surf, (x, y))

    # ------------------------------------------------------------------
    def draw(self, state: Any, surface: pygame.Surface) -> None:
        surface.fill(RGB_BG)
        self._draw_vital(state, surface)
        self._draw_intent(state, surface)
        self._draw_intent_history(state, surface)
        self._draw_problems(state, surface)
        self._draw_path_progress(state, surface)
        self._draw_verbose(state, surface)

    # ------------------------------------------------------------------
    def _draw_vital(self, state: Any, surface: pygame.Surface) -> None:
        y = self.y_vital + 4
        self._text(surface, "VITAL", self.pad_x, y, self.font_label, RGB_INTENT_LABEL)
        y += 16

        hp = int(getattr(state, "health", 0) or 0)
        hp_clamped = max(0, min(200, hp))
        hp_color = RGB_OK if hp_clamped > 50 else RGB_ALERT
        pygame.draw.rect(
            surface, (40, 40, 40), (self.pad_x, y, 200, 14)
        )
        pygame.draw.rect(
            surface, hp_color, (self.pad_x, y, hp_clamped, 14)
        )
        self._text(surface, f"HP: {hp}", self.pad_x + 210, y, self.font_small, hp_color)
        y += 18

        ar = int(getattr(state, "armor", 0) or 0)
        ar_clamped = max(0, min(200, ar))
        ar_color = (100, 200, 255)
        pygame.draw.rect(surface, (40, 40, 40), (self.pad_x, y, 200, 14))
        pygame.draw.rect(surface, ar_color, (self.pad_x, y, ar_clamped, 14))
        self._text(
            surface, f"AR: {ar}", self.pad_x + 210, y, self.font_small, ar_color
        )
        y += 20

        weapon = getattr(state, "weapon", None) or "?"
        ammo = getattr(state, "ammo", None)
        ammo_s = "?" if ammo is None else str(ammo)
        self._text(
            surface,
            f"Weapon: {weapon}  Ammo: {ammo_s}",
            self.pad_x,
            y,
            self.font_small,
            RGB_TEXT,
        )
        y += 16

        px = float(getattr(state, "player_x", 0.0))
        py = float(getattr(state, "player_y", 0.0))
        pz = float(getattr(state, "player_z", 0.0))
        yaw = float(getattr(state, "player_yaw", 0.0))
        self._text(
            surface,
            f"Pos: ({px:.0f}, {py:.0f}, {pz:.0f})",
            self.pad_x,
            y,
            self.font_small,
            RGB_TEXT_DIM,
        )
        y += 14
        self._text(
            surface,
            f"Yaw: {yaw:.0f}",
            self.pad_x,
            y,
            self.font_small,
            RGB_TEXT_DIM,
        )

    # ------------------------------------------------------------------
    def _draw_intent(self, state: Any, surface: pygame.Surface) -> None:
        y = self.y_intent
        box_x = self.pad_x
        box_y = y
        box_w = self.width - 2 * self.pad_x
        box_h = 100
        pygame.draw.rect(
            surface, (40, 40, 50), (box_x, box_y, box_w, box_h), border_radius=4
        )

        if bool(getattr(state, "is_paused_for_assess", False)):
            flash_on = int(time.time() * 2) % 2 == 0
            if flash_on:
                pygame.draw.rect(
                    surface,
                    RGB_PAUSE_BORDER,
                    (box_x, box_y, box_w, box_h),
                    width=3,
                    border_radius=4,
                )

        intent = getattr(state, "intent", {}) or {}
        macro = str(intent.get("macro", "IDLE"))
        sub = str(intent.get("sub", "") or "")
        desc = str(intent.get("description", "") or "")
        duration_s = float(intent.get("duration_s", 0.0) or 0.0)

        self._text(
            surface, macro, box_x + 10, box_y + 6, self.font_big, RGB_INTENT_CURRENT
        )
        detail = sub or desc
        if detail:
            self._text(
                surface,
                detail[:26],
                box_x + 10,
                box_y + 36,
                self.font_med,
                RGB_INTENT_SUB,
            )
        self._text(
            surface,
            f"{duration_s:.1f}s",
            box_x + 10,
            box_y + 56,
            self.font_med,
            RGB_INTENT_LABEL,
        )

        # Threat badge in corner
        threat = bool(getattr(state, "threat_flag", False))
        threat_color = RGB_PROBLEM_WALL if threat else (100, 200, 100)
        threat_text = "THREAT" if threat else "no threat"
        t_surf = self.font_small.render(threat_text, True, threat_color)
        surface.blit(
            t_surf, (box_x + box_w - t_surf.get_width() - 8, box_y + 8)
        )

    # ------------------------------------------------------------------
    def _draw_intent_history(self, state: Any, surface: pygame.Surface) -> None:
        y = self.y_history
        self._text(
            surface, "HISTORY", self.pad_x, y, self.font_label, RGB_INTENT_LABEL
        )
        y += 16
        hist = list(getattr(state, "intent_history", []) or [])[-5:]
        for item in hist:
            if not isinstance(item, dict):
                continue
            m = str(item.get("macro", "?"))
            sb = str(item.get("sub", "") or "")
            dur = float(item.get("duration_s", 0.0) or 0.0)
            line = f"{m[:14]:<14s} {sb[:14]:<14s} {dur:>4.1f}s"
            self._text(
                surface, line, self.pad_x, y, self.font_small, RGB_INTENT_HISTORY
            )
            y += 14

    # ------------------------------------------------------------------
    def _draw_problems(self, state: Any, surface: pygame.Surface) -> None:
        y = self.y_problems
        self._text(
            surface, "PROBLEMS", self.pad_x, y, self.font_label, RGB_INTENT_LABEL
        )
        y += 16
        problem_colors = {
            "wall_halt": RGB_PROBLEM_WALL,
            "stuck": RGB_PROBLEM_STUCK,
            "pin": RGB_PROBLEM_PIN,
            "respawn": RGB_PROBLEM_RESPAWN,
            "advisor_halt": RGB_PROBLEM_ADVISOR,
        }
        probs = list(getattr(state, "problem_history", []) or [])[-5:]
        for prob in probs:
            if not isinstance(prob, dict):
                continue
            kind = str(prob.get("kind", "?"))
            pdesc = str(prob.get("description", "") or "")
            color = problem_colors.get(kind, (200, 200, 200))
            line = f"{kind[:12]:<12s} {pdesc[:24]}"
            self._text(surface, line, self.pad_x, y, self.font_small, color)
            y += 14

    # ------------------------------------------------------------------
    def _draw_path_progress(self, state: Any, surface: pygame.Surface) -> None:
        y = self.y_path
        self._text(surface, "PATH", self.pad_x, y, self.font_label, RGB_INTENT_LABEL)
        y += 14
        pp = getattr(state, "path_progress", {}) or {}
        cur_step = int(pp.get("current_step", 0) or 0)
        total_steps = int(pp.get("total_steps", 0) or 0)
        self._text(
            surface,
            f"{cur_step}/{total_steps}",
            self.pad_x,
            y,
            self.font_small,
            RGB_INTENT_SUB,
        )
        bar_y = y + 14
        bar_w = self.width - 2 * self.pad_x
        bar_h = 6
        pygame.draw.rect(
            surface, (60, 60, 70), (self.pad_x, bar_y, bar_w, bar_h), border_radius=2
        )
        if total_steps > 0:
            fill_w = int(bar_w * min(1.0, cur_step / total_steps))
            if fill_w > 0:
                pygame.draw.rect(
                    surface,
                    RGB_INTENT_CURRENT,
                    (self.pad_x, bar_y, fill_w, bar_h),
                    border_radius=2,
                )

    # ------------------------------------------------------------------
    def _draw_verbose(self, state: Any, surface: pygame.Surface) -> None:
        y = self.y_verbose
        self._text(
            surface, "VERBOSE", self.pad_x, y, self.font_label, RGB_INTENT_LABEL
        )
        y += 16

        tick_rate = getattr(state, "tick_rate_fps", None)
        tick_str: Optional[str] = (
            f"{tick_rate:.1f} FPS" if tick_rate is not None else None
        )
        frame_lag = getattr(state, "frame_lag_ms", None)
        lag_str: Optional[str] = (
            f"{frame_lag:.0f}ms" if frame_lag is not None else None
        )
        nav_step_area = getattr(state, "nav_current_step_area", None)
        nav_str: Optional[str] = (
            f"area {nav_step_area}" if nav_step_area is not None else None
        )

        rows: List[Tuple[str, Optional[object]]] = [
            ("stair_climb", getattr(state, "stair_climb_state", None)),
            ("swim_edge", getattr(state, "swim_edge_state", None)),
            ("advisor", getattr(state, "advisor_last_thought", None)),
            ("last_replans", getattr(state, "last_replan_steps", None)),
            ("tick_rate", tick_str),
            ("frame_lag", lag_str),
            ("halts", getattr(state, "proactive_halts", None)),
            ("vpin", getattr(state, "visual_pin_hits", None)),
            ("nav_step", nav_str),
        ]

        label_w = 110
        for name, value in rows:
            self._text(
                surface,
                f"{name}:",
                self.pad_x,
                y,
                self.font_small,
                RGB_TEXT_DIM,
            )
            if value is None:
                self._text(
                    surface,
                    _PLACEHOLDER,
                    self.pad_x + label_w,
                    y,
                    self.font_small,
                    RGB_TEXT_DIM,
                )
            else:
                color = RGB_TEXT
                if name == "frame_lag" and frame_lag is not None:
                    if float(frame_lag) > _FRAME_LAG_WARN_MS:
                        color = RGB_ALERT
                text = str(value)
                self._text(
                    surface,
                    text[:24],
                    self.pad_x + label_w,
                    y,
                    self.font_small,
                    color,
                )
            y += 14
