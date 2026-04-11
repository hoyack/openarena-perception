"""Tests for open_perception.py (Phase 12-03).

Headless — SDL_VIDEODRIVER=dummy MUST be set before importing pygame. We
set it at module top to catch any transitive pygame import.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import sys  # noqa: E402
from pathlib import Path  # noqa: E402
import pygame  # noqa: E402
import pytest  # noqa: E402

# Ensure project root is importable so `import open_perception` works under pytest
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import open_perception  # noqa: E402
from openarena_perception.hud_schema import build_hud_payload  # noqa: E402


@pytest.fixture(scope="module")
def fake_graph():
    """Real AAS graph parsed from maps/oa_dm1.aas.

    AASDepthBackend does attribute probes (graph.vertexes.size, etc.) that
    a MagicMock cannot satisfy cleanly, so the cheapest path is to parse
    the real file once per module.
    """
    from openarena_perception.navigation.aas_parser import parse_aas

    path = _REPO_ROOT / "maps" / "oa_dm1.aas"
    if not path.exists():
        pytest.skip(f"Missing fixture AAS file: {path}")
    graph = parse_aas(str(path))
    if graph is None:
        pytest.skip("parse_aas returned None")
    return graph


def _write_payload(tmp_path: Path) -> Path:
    """Write a realistic HUD payload with all 7 verbose fields populated."""
    payload = build_hud_payload(
        map_name="oa_dm1",
        stair_climb_state="climbing target_area=42",
        swim_edge_state="traversing to area 9",
        advisor_last_thought="watch the lava pit ahead",
        last_replan_steps=[3, 4, 6],
        tick_rate_fps=12.5,
        frame_lag_ms=42.0,
        nav_current_step_area=42,
    )
    # Merge the legacy fields item_tour writes via extras
    payload.update(
        {
            "map": "oa_dm1",
            "x": 100.0,
            "y": 200.0,
            "z": -50.0,
            "yaw": 90.0,
            "health": 85,
            "armor": 50,
            "ammo": 32,
            "weapon": "rocketlauncher",
            "alive": True,
            "proactive_halts": 3,
            "visual_pin_hits": 5,
        }
    )
    state_file = tmp_path / "oa_hud_state.json"
    state_file.write_text(json.dumps(payload))
    return state_file


def test_open_perception_hud_state_tolerates_missing_file(tmp_path):
    """Missing file -> no exception, defaults retained."""
    s = open_perception.HUDState()
    result = s.load(tmp_path / "does_not_exist.json")
    assert result is s
    assert s.map_name == "unknown"
    assert s.health == 100


def test_open_perception_hud_state_tolerates_malformed_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json")
    s = open_perception.HUDState().load(p)
    assert s.map_name == "unknown"


def test_open_perception_hud_state_loads_all_verbose_fields(tmp_path):
    """Round-trip: build_hud_payload -> json -> HUDState.load."""
    state_file = _write_payload(tmp_path)
    s = open_perception.HUDState().load(state_file)
    assert s.map_name == "oa_dm1"
    assert s.health == 85
    assert s.armor == 50
    assert s.ammo == 32
    assert s.weapon == "rocketlauncher"
    assert s.player_x == 100.0
    assert s.player_y == 200.0
    assert s.player_yaw == 90.0
    # All 7 verbose fields present
    assert s.stair_climb_state == "climbing target_area=42"
    assert s.swim_edge_state == "traversing to area 9"
    assert s.advisor_last_thought == "watch the lava pit ahead"
    assert s.last_replan_steps == [3, 4, 6]
    assert s.tick_rate_fps == 12.5
    assert s.frame_lag_ms == 42.0
    assert s.nav_current_step_area == 42
    # item_tour verbose counters
    assert s.proactive_halts == 3
    assert s.visual_pin_hits == 5


def test_open_perception_app_init_window_dimensions(fake_graph, tmp_path):
    """App instantiates with a mock AAS graph; screen is 1400x700."""
    state_file = _write_payload(tmp_path)
    app = open_perception.OpenPerceptionApp(fake_graph, state_file=state_file)
    try:
        w, h = app.screen.get_size()
        assert (w, h) == (1400, 700)
        # Sub-surfaces match the panel widths.
        assert app.minimap_surf.get_size() == (400, 700)
        assert app.wireframe_surf.get_size() == (600, 700)
        assert app.stats_surf.get_size() == (400, 700)
    finally:
        pygame.display.quit()


def test_open_perception_one_tick_smoke(fake_graph, tmp_path, monkeypatch):
    """Run main() for exactly one tick via a mocked event queue."""
    state_file = _write_payload(tmp_path)

    app = open_perception.OpenPerceptionApp(fake_graph, state_file=state_file)
    try:
        # Fake QUIT event fires on first poll -> main loop exits after one draw.
        quit_evt = pygame.event.Event(pygame.QUIT)
        call_count = {"n": 0}

        def fake_get_events():
            call_count["n"] += 1
            if call_count["n"] == 1:
                return []  # first poll: no quit, tick proceeds
            return [quit_evt]

        monkeypatch.setattr(pygame.event, "get", fake_get_events)
        rc = app.run()
        assert rc == 0
        # At least one draw happened — call_count increments per iteration.
        assert call_count["n"] >= 1
    finally:
        pygame.display.quit()


def test_open_perception_aas_autodetect_from_state(tmp_path, monkeypatch):
    """state.map_name=oa_dm1 -> resolves to maps/oa_dm1.aas."""
    # Point fallback at a file we know exists for the test.
    fake_aas = tmp_path / "oa_dm1.aas"
    fake_aas.write_bytes(b"stub")

    monkeypatch.setattr(
        open_perception,
        "PROJECT_ROOT",
        tmp_path.parent,  # so tmp_path == PROJECT_ROOT/maps won't work
    )
    # Build a maps/ dir under PROJECT_ROOT override
    maps_dir = tmp_path.parent / "maps"
    maps_dir.mkdir(exist_ok=True)
    target = maps_dir / "oa_dm1.aas"
    target.write_bytes(b"stub")
    try:
        resolved = open_perception._resolve_aas_path(None, "oa_dm1")
        assert resolved == target
    finally:
        target.unlink(missing_ok=True)


def test_open_perception_aas_explicit_cli(tmp_path):
    """--aas PATH with existing file returns that path."""
    f = tmp_path / "custom.aas"
    f.write_bytes(b"stub")
    assert open_perception._resolve_aas_path(str(f), None) == f


def test_open_perception_aas_cli_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        open_perception._resolve_aas_path(
            str(tmp_path / "nope.aas"), None
        )


def test_open_perception_aas_fallback_to_oa_dm1(monkeypatch, tmp_path):
    """Unknown state map -> falls back to maps/oa_dm1.aas under PROJECT_ROOT."""
    # Use real project root — maps/oa_dm1.aas actually exists in the repo.
    resolved = open_perception._resolve_aas_path(None, "nonexistent_map")
    assert resolved.name == "oa_dm1.aas"
    assert resolved.exists()


def test_open_perception_peek_state_map_name(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"map": "oa_dm2"}))
    assert open_perception._peek_state_map_name(p) == "oa_dm2"


def test_open_perception_peek_missing_file(tmp_path):
    assert open_perception._peek_state_map_name(tmp_path / "nope.json") is None


def test_open_perception_draws_waiting_when_state_missing(fake_graph, tmp_path):
    """When state file does not exist, draw_tick uses WAITING placeholder
    without raising."""
    state_file = tmp_path / "no.json"
    app = open_perception.OpenPerceptionApp(fake_graph, state_file=state_file)
    try:
        app.draw_tick()  # must not raise
    finally:
        pygame.display.quit()
