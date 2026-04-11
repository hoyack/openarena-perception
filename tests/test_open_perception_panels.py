"""Panel isolation tests for Open-Perception UI (Phase 12-02)."""

from __future__ import annotations

import os

# Must set before pygame import (Pitfall 3 / headless contract)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pygame
import pytest

pygame.init()  # noqa: E402 — explicit init so font subsystem is ready

from openarena_perception.visualization.panels import (  # noqa: E402
    HUD_WIDTH,
    PANEL_HEIGHT,
    PANEL_LEFT_W,
    PANEL_MINIMAP_SIZE,
    PANEL_MINIMAP_W,
    PANEL_STATS_W,
    PANEL_WIREFRAME_SIZE,
    PANEL_WIREFRAME_W,
    MinimapPanel,
    StatsPanel,
    WireframePanel,
)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _make_state(**overrides: Any) -> SimpleNamespace:
    """Fake HUDState-like object with every field the panels read."""
    base = dict(
        map_name="oa_dm1",
        player_x=100.0,
        player_y=200.0,
        player_z=0.0,
        player_yaw=90.0,
        health=100,
        armor=50,
        ammo=40,
        weapon="machinegun",
        map_min_x=-500.0,
        map_max_x=500.0,
        map_min_y=-500.0,
        map_max_y=500.0,
        learned_map={},
        surveys={},
        items=[],
        route=[],
        route_idx=0,
        trail=[],
        intent={},
        intent_history=[],
        problem_history=[],
        path_progress={},
        is_paused_for_assess=False,
        threat_flag=False,
        # Phase 12 verbose
        stair_climb_state=None,
        swim_edge_state=None,
        advisor_last_thought=None,
        last_replan_steps=None,
        tick_rate_fps=None,
        frame_lag_ms=None,
        proactive_halts=None,
        visual_pin_hits=None,
        nav_current_step_area=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _surface(w: int, h: int) -> pygame.Surface:
    return pygame.Surface((w, h))


def _any_nonbg(surface: pygame.Surface, bg=(20, 20, 30)) -> int:
    arr = pygame.surfarray.array3d(surface)
    bg_arr = np.array(bg, dtype=np.uint8)
    diff = np.any(arr != bg_arr, axis=-1)
    return int(diff.sum())


def _region_nonbg(
    surface: pygame.Surface, x: int, y: int, w: int, h: int, bg=(20, 20, 30)
) -> int:
    # pygame array3d is (width, height, 3)
    arr = pygame.surfarray.array3d(surface)
    region = arr[x : x + w, y : y + h]
    bg_arr = np.array(bg, dtype=np.uint8)
    diff = np.any(region != bg_arr, axis=-1)
    return int(diff.sum())


# -----------------------------------------------------------------------
# Layout constant sanity
# -----------------------------------------------------------------------


def test_hud_width_is_derived() -> None:
    assert HUD_WIDTH == PANEL_LEFT_W + PANEL_STATS_W
    assert HUD_WIDTH == 760
    assert PANEL_HEIGHT == 720
    assert PANEL_WIREFRAME_SIZE == 360
    assert PANEL_MINIMAP_SIZE == 360
    assert PANEL_LEFT_W == 360
    # Backward-compat aliases still equal the new square edge.
    assert PANEL_MINIMAP_W == PANEL_WIREFRAME_W == 360


# -----------------------------------------------------------------------
# MinimapPanel tests
# -----------------------------------------------------------------------


def test_minimap_panel_draws_player_marker() -> None:
    panel = MinimapPanel(aas_graph=None, width=PANEL_MINIMAP_SIZE, height=PANEL_MINIMAP_SIZE)
    surface = _surface(PANEL_MINIMAP_SIZE, PANEL_MINIMAP_SIZE)
    # Player at world origin so marker lands near minimap center.
    state = _make_state(player_x=0.0, player_y=0.0, player_yaw=0.0)
    panel.draw(state, surface)
    # Expect non-bg pixels somewhere in the surface (player + grid)
    assert _any_nonbg(surface) > 0


def test_minimap_panel_no_hud_text() -> None:
    """Minimap owns NO HP/POS/YAW/AMMO text (dedup contract)."""
    panel = MinimapPanel(aas_graph=None, width=PANEL_MINIMAP_SIZE, height=PANEL_MINIMAP_SIZE)
    src = Path(
        "openarena_perception/visualization/panels/minimap.py"
    ).read_text()
    for forbidden in ("HP:", "AR:", "Ammo:", "Pos:", "Yaw:"):
        assert forbidden not in src, (
            f"minimap.py must not draw '{forbidden}' — dedup contract"
        )
    # Also: no imports from strategic_hud
    assert "import strategic_hud" not in src
    assert "from strategic_hud" not in src
    # Sanity: panel still runs
    surface = _surface(PANEL_MINIMAP_SIZE, PANEL_MINIMAP_SIZE)
    panel.draw(_make_state(), surface)


def test_minimap_panel_draws_route_waypoints() -> None:
    panel = MinimapPanel(aas_graph=None, width=PANEL_MINIMAP_SIZE, height=PANEL_MINIMAP_SIZE)
    surface = _surface(PANEL_MINIMAP_SIZE, PANEL_MINIMAP_SIZE)
    state = _make_state(
        player_x=0.0,
        player_y=0.0,
        route=[
            ("wp1", -100.0, -100.0, 0.0),
            ("wp2", 100.0, 100.0, 0.0),
            ("wp3", 200.0, -200.0, 0.0),
        ],
        route_idx=1,
    )
    panel.draw(state, surface)
    # Count non-bg pixels — with 3 waypoints rendered as filled/outlined
    # circles plus the route line, the count must be meaningfully nonzero.
    assert _any_nonbg(surface) > 50


def test_minimap_panel_latches_bounds(monkeypatch) -> None:
    """Map bounds should latch on first draw (Pitfall 10)."""
    panel = MinimapPanel(aas_graph=None, width=PANEL_MINIMAP_SIZE, height=PANEL_MINIMAP_SIZE)
    surface = _surface(PANEL_MINIMAP_SIZE, PANEL_MINIMAP_SIZE)
    s1 = _make_state(
        map_min_x=-500, map_max_x=500, map_min_y=-500, map_max_y=500
    )
    panel.draw(s1, surface)
    bounds_after_first = panel._bounds
    # Second frame with wildly different bounds — must not widen.
    s2 = _make_state(
        map_min_x=-5000, map_max_x=5000, map_min_y=-5000, map_max_y=5000
    )
    panel.draw(s2, surface)
    assert panel._bounds == bounds_after_first


def test_minimap_panel_square_layout_dimensions() -> None:
    panel = MinimapPanel(
        aas_graph=None, width=PANEL_MINIMAP_SIZE, height=PANEL_MINIMAP_SIZE
    )
    assert panel.width == 360
    assert panel.height == 360
    assert panel._map_margin == 8
    assert panel._map_top == 24
    assert panel._map_size == min(360 - 16, 360 - 24 - 8)
    assert panel._map_size == 328


def _count_aas_fill_pixels(surface: pygame.Surface) -> int:
    """Count pixels painted with the AAS overhead fill color (35, 45, 60)."""
    arr = pygame.surfarray.array3d(surface)
    fill = np.array((35, 45, 60), dtype=np.uint8)
    return int(np.all(arr == fill, axis=-1).sum())


def test_minimap_panel_aas_overhead_draws_polygons(aas_graph) -> None:
    from openarena_perception.navigation.aas_parser import areas_on_floor

    a1 = aas_graph.areas[1]
    mid_z = (a1.mins[2] + a1.maxs[2]) / 2
    floor_ids = areas_on_floor(aas_graph, mid_z, z_tolerance=24.0)
    assert len(floor_ids) > 0, "fixture must have at least one floor area"

    panel_with = MinimapPanel(
        aas_graph=aas_graph, width=PANEL_MINIMAP_SIZE, height=PANEL_MINIMAP_SIZE
    )
    panel_without = MinimapPanel(
        aas_graph=None, width=PANEL_MINIMAP_SIZE, height=PANEL_MINIMAP_SIZE
    )
    state = _make_state(
        player_x=float(a1.cx),
        player_y=float(a1.cy),
        player_z=mid_z,
        map_min_x=float(a1.mins[0]) - 500.0,
        map_max_x=float(a1.maxs[0]) + 500.0,
        map_min_y=float(a1.mins[1]) - 500.0,
        map_max_y=float(a1.maxs[1]) + 500.0,
    )
    surf_with = _surface(PANEL_MINIMAP_SIZE, PANEL_MINIMAP_SIZE)
    surf_without = _surface(PANEL_MINIMAP_SIZE, PANEL_MINIMAP_SIZE)
    panel_with.draw(state, surf_with)
    panel_without.draw(state, surf_without)
    # Count AAS-fill-colored pixels specifically: panel_with must have >0,
    # panel_without must have exactly 0.
    with_fill = _count_aas_fill_pixels(surf_with)
    without_fill = _count_aas_fill_pixels(surf_without)
    assert with_fill > 0, (
        f"AAS overhead must paint AAS-fill pixels: with_fill={with_fill}"
    )
    assert without_fill == 0, (
        f"panel without aas_graph must not paint AAS fill: "
        f"without_fill={without_fill}"
    )


def test_minimap_panel_aas_overhead_filtered_to_floor(aas_graph) -> None:
    """Moving player_z far above any area shrinks AAS contribution."""
    a1 = aas_graph.areas[1]
    mid_z = (a1.mins[2] + a1.maxs[2]) / 2
    max_z = max(a.maxs[2] for a in aas_graph.areas[1:])
    above_all = max_z + 500.0  # far above every area

    base_state = dict(
        player_x=float(a1.cx),
        player_y=float(a1.cy),
        map_min_x=-4000.0,
        map_max_x=4000.0,
        map_min_y=-4000.0,
        map_max_y=4000.0,
    )
    panel = MinimapPanel(
        aas_graph=aas_graph, width=PANEL_MINIMAP_SIZE, height=PANEL_MINIMAP_SIZE
    )
    surf_on = _surface(PANEL_MINIMAP_SIZE, PANEL_MINIMAP_SIZE)
    panel.draw(_make_state(**base_state, player_z=mid_z), surf_on)
    # Fresh panel so bounds re-latch from the new state.
    panel2 = MinimapPanel(
        aas_graph=aas_graph, width=PANEL_MINIMAP_SIZE, height=PANEL_MINIMAP_SIZE
    )
    surf_above = _surface(PANEL_MINIMAP_SIZE, PANEL_MINIMAP_SIZE)
    panel2.draw(_make_state(**base_state, player_z=above_all), surf_above)
    # Count AAS-fill-colored pixels specifically (generic nonbg also picks
    # up the grid interior which is invariant).
    on_fill = _count_aas_fill_pixels(surf_on)
    above_fill = _count_aas_fill_pixels(surf_above)
    assert on_fill > 0, f"on-floor must have AAS fill: {on_fill}"
    assert above_fill == 0, (
        f"floor filter must drop areas above the bot: "
        f"on_floor_fill={on_fill}, far_above_fill={above_fill}"
    )


def test_minimap_panel_visited_cells_brighter_than_open() -> None:
    panel = MinimapPanel(
        aas_graph=None, width=PANEL_MINIMAP_SIZE, height=PANEL_MINIMAP_SIZE
    )
    state = _make_state(
        player_x=0.0,
        player_y=0.0,
        map_min_x=-500.0,
        map_max_x=500.0,
        map_min_y=-500.0,
        map_max_y=500.0,
        learned_map={
            "grid_origin": [0, 0],
            "grid_resolution": 64,
            "grid_cells": [
                [2, 0, 3],  # VISITED at (2,0)
                [-2, 0, 1],  # OPEN at (-2,0)
            ],
        },
    )
    surf = _surface(PANEL_MINIMAP_SIZE, PANEL_MINIMAP_SIZE)
    panel.draw(state, surf)
    arr = pygame.surfarray.array3d(surf)
    # Mask out the player marker center (~RGB_PLAYER = 0,255,100 is green-
    # dominant too) so we count only the VISITED tile.
    px = panel._map_margin + int(
        (0.0 - state.map_min_x)
        / (state.map_max_x - state.map_min_x)
        * panel._map_size
    )
    py = panel._map_top + panel._map_size - int(
        (0.0 - state.map_min_y)
        / (state.map_max_y - state.map_min_y)
        * panel._map_size
    )
    mask = np.ones_like(arr[:, :, 0], dtype=bool)
    mask[max(0, px - 10) : px + 10, max(0, py - 10) : py + 10] = False
    green_dominant = int(
        np.sum(
            ((arr[:, :, 1].astype(int) - arr[:, :, 0].astype(int)) > 60)
            & ((arr[:, :, 1].astype(int) - arr[:, :, 2].astype(int)) > 60)
            & (arr[:, :, 1] > 140)
            & mask
        )
    )
    assert green_dominant > 0, (
        "VISITED cells must render as bright green (>0 pixels after "
        "masking out the player marker)"
    )


# -----------------------------------------------------------------------
# WireframePanel tests (use real oa_dm1.aas — small & already present)
# -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def aas_graph():
    from openarena_perception.navigation.aas_parser import parse_aas

    path = Path("maps/oa_dm1.aas")
    if not path.exists():
        pytest.skip("maps/oa_dm1.aas not available for wireframe tests")
    graph = parse_aas(str(path))
    if graph is None:
        pytest.skip("failed to parse maps/oa_dm1.aas")
    return graph


def _pose_inside_graph(graph) -> tuple[float, float, float, float]:
    """Return (x, y, z, yaw) at the center of area 1 (first walkable)."""
    # Pick any area and use its center + yaw=0
    for area in graph.areas[1:] if hasattr(graph, "areas") else []:
        center = getattr(area, "center", None)
        if center is not None and len(center) >= 3:
            return (float(center[0]), float(center[1]), float(center[2]), 0.0)
    # Fallback to origin
    return (0.0, 0.0, 0.0, 0.0)


def test_wireframe_panel_renders_non_empty_scene(aas_graph) -> None:
    panel = WireframePanel(
        aas_graph, width=PANEL_WIREFRAME_SIZE, height=PANEL_WIREFRAME_SIZE
    )
    surface = _surface(PANEL_WIREFRAME_SIZE, PANEL_WIREFRAME_SIZE)
    x, y, z, yaw = _pose_inside_graph(aas_graph)
    state = _make_state(player_x=x, player_y=y, player_z=z, player_yaw=yaw)
    panel.draw(state, surface)
    # Scene should produce many non-bg pixels (decoration brackets alone
    # already contribute ~80 pixels of non-bg).
    assert _any_nonbg(surface) > 100


def test_wireframe_panel_no_numeric_overlay(aas_graph) -> None:
    """Top-left FRAME text region stays bg (Pitfall 5 regression)."""
    panel = WireframePanel(
        aas_graph, width=PANEL_WIREFRAME_SIZE, height=PANEL_WIREFRAME_SIZE
    )
    surface = _surface(PANEL_WIREFRAME_SIZE, PANEL_WIREFRAME_SIZE)
    x, y, z, yaw = _pose_inside_graph(aas_graph)
    state = _make_state(player_x=x, player_y=y, player_z=z, player_yaw=yaw)
    panel.draw(state, surface)
    # The FRAME text region would sit at roughly (8..200, 10..35) in pixel
    # coordinates. The panel fills with cfg.bg_color which is the same
    # BGR->RGB (20, 20, 30) as our RGB_BG.
    # We can't cleanly assert absence of scene pixels there (a wall could
    # project into that region), so we assert the text is not drawn by
    # ensuring the WireframePanel forwards decoration_only=True — verified
    # via source inspection.
    src = Path(
        "openarena_perception/visualization/panels/wireframe.py"
    ).read_text()
    assert "decoration_only=True" in src
    assert "draw_room_frame=False" in src
    assert "extra_hud=None" in src


def test_wireframe_panel_decoration_chrome_present(aas_graph) -> None:
    panel = WireframePanel(
        aas_graph, width=PANEL_WIREFRAME_SIZE, height=PANEL_WIREFRAME_SIZE
    )
    surface = _surface(PANEL_WIREFRAME_SIZE, PANEL_WIREFRAME_SIZE)
    x, y, z, yaw = _pose_inside_graph(aas_graph)
    state = _make_state(player_x=x, player_y=y, player_z=z, player_yaw=yaw)
    panel.draw(state, surface)
    # Top-left corner bracket region
    nonbg = _region_nonbg(surface, 0, 0, 30, 30)
    assert nonbg > 0, "corner bracket missing in wireframe panel"


def test_wireframe_panel_bgr_rgb_swap_correct(aas_graph, monkeypatch) -> None:
    """Monkeypatch renderer.render to return a known BGR frame; verify the
    pygame surface shows the correct RGB channel (Pitfall 2)."""
    panel = WireframePanel(aas_graph, width=100, height=100)
    # Stub the renderer to return a pure-blue BGR frame: BGR=(255,0,0) is
    # pure blue. After BGR->RGB swap, the pygame surface should show
    # RGB=(0,0,255) at every pixel.
    def fake_render(*args, **kwargs):
        arr = np.zeros((100, 100, 3), dtype=np.uint8)
        arr[:, :, 0] = 255  # BGR channel 0 = blue
        return arr

    monkeypatch.setattr(panel._renderer, "render", fake_render)

    surface = _surface(100, 100)
    state = _make_state()
    panel.draw(state, surface)

    # Read pygame pixel — should be blue RGB=(0,0,255)
    pixel = surface.get_at((50, 50))
    assert pixel.r == 0
    assert pixel.g == 0
    assert pixel.b == 255, (
        f"BGR->RGB channel swap broken: got RGB=({pixel.r},{pixel.g},{pixel.b})"
    )


# -----------------------------------------------------------------------
# StatsPanel tests
# -----------------------------------------------------------------------


def test_stats_panel_renders_vital_stats() -> None:
    panel = StatsPanel(PANEL_STATS_W, PANEL_HEIGHT)
    surface = _surface(PANEL_STATS_W, PANEL_HEIGHT)
    state = _make_state(health=100, armor=50)
    panel.draw(state, surface)
    # Vital region occupies y in [0, 120]
    assert _region_nonbg(surface, 0, 0, PANEL_STATS_W, 120) > 0


def test_stats_panel_renders_intent_block() -> None:
    panel = StatsPanel(PANEL_STATS_W, PANEL_HEIGHT)
    surface = _surface(PANEL_STATS_W, PANEL_HEIGHT)
    state = _make_state(
        intent={"macro": "TOURING", "sub": "heading north", "duration_s": 2.5}
    )
    panel.draw(state, surface)
    # Intent region y in [120, 230]
    assert _region_nonbg(surface, 0, 120, PANEL_STATS_W, 110) > 0


def test_stats_panel_pause_border_flashes(monkeypatch) -> None:
    panel = StatsPanel(PANEL_STATS_W, PANEL_HEIGHT)
    surf1 = _surface(PANEL_STATS_W, PANEL_HEIGHT)
    surf2 = _surface(PANEL_STATS_W, PANEL_HEIGHT)
    state = _make_state(is_paused_for_assess=True)

    # Frame A — flash ON (even half-second phase)
    import openarena_perception.visualization.panels.stats as stats_mod

    monkeypatch.setattr(stats_mod.time, "time", lambda: 0.0)
    panel.draw(state, surf1)

    # Frame B — flash OFF (odd half-second phase)
    # int(0.5 * 2) % 2 == 1 => flash off
    monkeypatch.setattr(stats_mod.time, "time", lambda: 0.5)
    panel.draw(state, surf2)

    # Sample the top border of the intent box (y ~= 121, x in [10, 390])
    arr1 = pygame.surfarray.array3d(surf1)
    arr2 = pygame.surfarray.array3d(surf2)
    border_row_1 = arr1[10:390, 121:124]
    border_row_2 = arr2[10:390, 121:124]
    assert not np.array_equal(border_row_1, border_row_2), (
        "pause border must visibly flash between t=0.0 and t=0.3"
    )


def test_stats_panel_verbose_rows_populated() -> None:
    panel = StatsPanel(PANEL_STATS_W, PANEL_HEIGHT)
    surface = _surface(PANEL_STATS_W, PANEL_HEIGHT)
    state = _make_state(
        stair_climb_state="climbing target_area=42",
        swim_edge_state="clear",
        advisor_last_thought="heading to mega health",
        last_replan_steps=[3, 4, 6],
        tick_rate_fps=12.3,
        frame_lag_ms=45.0,
        proactive_halts=2,
        visual_pin_hits=1,
        nav_current_step_area=17,
    )
    panel.draw(state, surface)
    # Verbose region y in [470, 700]
    nonbg = _region_nonbg(surface, 0, 470, PANEL_STATS_W, 230)
    assert nonbg > 100, f"verbose region too empty: {nonbg} non-bg pixels"


def test_stats_panel_verbose_rows_none_placeholder() -> None:
    """Verbose rows with None values still render dim placeholders."""
    panel = StatsPanel(PANEL_STATS_W, PANEL_HEIGHT)
    surface = _surface(PANEL_STATS_W, PANEL_HEIGHT)
    state = _make_state()  # all verbose fields default to None
    panel.draw(state, surface)
    # Region still has text because each row renders label + placeholder
    nonbg = _region_nonbg(surface, 0, 470, PANEL_STATS_W, 230)
    assert nonbg > 50, (
        f"verbose rows should still render placeholders when None; "
        f"got {nonbg} non-bg pixels"
    )


def test_stats_panel_frame_lag_warning_color() -> None:
    panel = StatsPanel(PANEL_STATS_W, PANEL_HEIGHT)
    surface = _surface(PANEL_STATS_W, PANEL_HEIGHT)
    state = _make_state(frame_lag_ms=250.0)
    panel.draw(state, surface)
    # Scan the verbose region for red-dominant pixels — RGB_ALERT=(255,80,80).
    # Font antialiasing means only a handful of pixels will hit the exact
    # color, so use a loose dominance check.
    arr = pygame.surfarray.array3d(surface)
    region = arr[:, 470:700]
    red_dominant = np.sum(
        (region[:, :, 0].astype(int) - region[:, :, 1].astype(int) > 40)
        & (region[:, :, 0].astype(int) - region[:, :, 2].astype(int) > 40)
    )
    assert red_dominant > 0, (
        f"frame_lag>100ms should render in RGB_ALERT red; "
        f"found {red_dominant} red-dominant pixels"
    )

    # And: compare against a control panel where lag is low — it must not
    # produce any red-dominant pixels in the verbose region.
    panel_ok = StatsPanel(PANEL_STATS_W, PANEL_HEIGHT)
    surf_ok = _surface(PANEL_STATS_W, PANEL_HEIGHT)
    panel_ok.draw(_make_state(frame_lag_ms=20.0), surf_ok)
    arr_ok = pygame.surfarray.array3d(surf_ok)
    region_ok = arr_ok[:, 470:700]
    red_ok = np.sum(
        (region_ok[:, :, 0].astype(int) - region_ok[:, :, 1].astype(int) > 40)
        & (region_ok[:, :, 0].astype(int) - region_ok[:, :, 2].astype(int) > 40)
    )
    assert red_dominant > red_ok, (
        f"high-lag frame should produce more red pixels than low-lag: "
        f"{red_dominant} vs {red_ok}"
    )


def test_stats_panel_no_strategic_hud_import() -> None:
    src = Path(
        "openarena_perception/visualization/panels/stats.py"
    ).read_text()
    assert "import strategic_hud" not in src
    assert "from strategic_hud" not in src
