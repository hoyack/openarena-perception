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
    PANEL_MINIMAP_W,
    PANEL_STATS_W,
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
    assert HUD_WIDTH == PANEL_MINIMAP_W + PANEL_WIREFRAME_W + PANEL_STATS_W
    assert HUD_WIDTH == 1400
    assert PANEL_HEIGHT == 700


# -----------------------------------------------------------------------
# MinimapPanel tests
# -----------------------------------------------------------------------


def test_minimap_panel_draws_player_marker() -> None:
    panel = MinimapPanel(PANEL_MINIMAP_W, PANEL_HEIGHT)
    surface = _surface(PANEL_MINIMAP_W, PANEL_HEIGHT)
    # Player at world origin so marker lands near minimap center.
    state = _make_state(player_x=0.0, player_y=0.0, player_yaw=0.0)
    panel.draw(state, surface)
    # Expect non-bg pixels somewhere in the surface (player + grid)
    assert _any_nonbg(surface) > 0


def test_minimap_panel_no_hud_text() -> None:
    """Minimap owns NO HP/POS/YAW/AMMO text (dedup contract)."""
    panel = MinimapPanel(PANEL_MINIMAP_W, PANEL_HEIGHT)
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
    surface = _surface(PANEL_MINIMAP_W, PANEL_HEIGHT)
    panel.draw(_make_state(), surface)


def test_minimap_panel_draws_route_waypoints() -> None:
    panel = MinimapPanel(PANEL_MINIMAP_W, PANEL_HEIGHT)
    surface = _surface(PANEL_MINIMAP_W, PANEL_HEIGHT)
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
    panel = MinimapPanel(PANEL_MINIMAP_W, PANEL_HEIGHT)
    surface = _surface(PANEL_MINIMAP_W, PANEL_HEIGHT)
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
    panel = WireframePanel(aas_graph, width=PANEL_WIREFRAME_W, height=PANEL_HEIGHT)
    surface = _surface(PANEL_WIREFRAME_W, PANEL_HEIGHT)
    x, y, z, yaw = _pose_inside_graph(aas_graph)
    state = _make_state(player_x=x, player_y=y, player_z=z, player_yaw=yaw)
    panel.draw(state, surface)
    # Scene should produce many non-bg pixels (decoration brackets alone
    # already contribute ~80 pixels of non-bg).
    assert _any_nonbg(surface) > 100


def test_wireframe_panel_no_numeric_overlay(aas_graph) -> None:
    """Top-left FRAME text region stays bg (Pitfall 5 regression)."""
    panel = WireframePanel(aas_graph, width=PANEL_WIREFRAME_W, height=PANEL_HEIGHT)
    surface = _surface(PANEL_WIREFRAME_W, PANEL_HEIGHT)
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
    panel = WireframePanel(aas_graph, width=PANEL_WIREFRAME_W, height=PANEL_HEIGHT)
    surface = _surface(PANEL_WIREFRAME_W, PANEL_HEIGHT)
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
