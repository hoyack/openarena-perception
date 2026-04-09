"""Tests for the FastAPI REST API layer.

Covers: /health, /perception/*, /navigation/*, /combat/*, /skills/*, /strategy/*, /docs.
Uses httpx.AsyncClient with ASGITransport (project convention: asyncio.run wrapper).
"""
from __future__ import annotations

import asyncio
from typing import Any

from httpx import ASGITransport, AsyncClient

from openarena_perception.api.app import create_app
from openarena_perception.api.deps import BotState
from openarena_perception.models import SituationalAwareness
from openarena_perception.skills.base import SkillLayer, SkillRegistry, SkillResult

# ── Helpers ───────────────────────────────────────────────────────────


def _fake_sa(**overrides: Any) -> SituationalAwareness:
    """Build a SituationalAwareness with sensible defaults."""
    defaults = dict(
        tick=42,
        timestamp=1000.0,
        pos=(100.0, 200.0, 300.0),
        yaw=90.0,
        current_area=5,
        health=75,
        armor=50,
        ammo=20,
        weapon="rocket",
        is_alive=True,
        disposition="healthy",
        armament="armed",
        orientation="oriented",
        under_attack=False,
        attacker_direction=0,
        seconds_since_damage=10.0,
        enemies_visible=2,
        nearest_enemy_distance="medium",
        wall_ahead=False,
        wall_score=0.1,
        open_direction=90,
        in_water=False,
        tracked_objects=1,
        locked_target=False,
        anomaly_count=0,
        lockable_anomaly=False,
        room_surveyed=True,
        room_type="arena",
        room_exits=3,
        has_path=True,
        path_length=5,
        is_stuck=False,
        is_recovering=False,
        nav_target="area_10",
        has_frame=True,
    )
    defaults.update(overrides)
    return SituationalAwareness(**defaults)


def _make_registry() -> SkillRegistry:
    """Build a SkillRegistry with a mock 'move' skill."""
    registry = SkillRegistry()

    class FakeSkill:
        name = "move"
        layer = SkillLayer.ACTION
        description = "Move forward or backward"

        async def execute(self, **params: Any) -> SkillResult:
            return SkillResult(success=True, message="moved", data=params)

        def cancel(self) -> None:
            pass

    registry.register(FakeSkill())
    return registry


def _bot_with_sa() -> BotState:
    """BotState with a fake SA and registry."""
    bot = BotState()
    bot.last_sa = _fake_sa()
    bot.registry = _make_registry()
    return bot


def _bot_without_sa() -> BotState:
    """BotState with no SA (simulates startup before first tick)."""
    bot = BotState()
    bot.registry = _make_registry()
    return bot


async def _client(bot: BotState | None = None) -> AsyncClient:
    """Build an httpx AsyncClient for the test app."""
    from openarena_perception.api.deps import set_bot

    b = bot or _bot_with_sa()
    app = create_app(bot=b)
    # Manually set the singleton so Depends(get_bot) works without lifespan
    set_bot(b)
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── Tests ─────────────────────────────────────────────────────────────


def test_app_health():
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"

    asyncio.run(_run())


def test_perception_state():
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/perception/state")
        assert r.status_code == 200
        body = r.json()
        assert body["tick"] == 42
        assert body["health"] == 75
        assert body["weapon"] == "rocket"
        assert body["is_alive"] is True

    asyncio.run(_run())


def test_perception_503():
    async def _run():
        client = await _client(bot=_bot_without_sa())
        async with client:
            r = await client.get("/perception/state")
        assert r.status_code == 503

    asyncio.run(_run())


def test_perception_enemies():
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/perception/enemies")
        assert r.status_code == 200
        body = r.json()
        assert body["enemies_visible"] == 2
        assert body["nearest_enemy_distance"] == "medium"
        assert body["under_attack"] is False

    asyncio.run(_run())


def test_perception_hud():
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/perception/hud")
        assert r.status_code == 200
        body = r.json()
        assert body["health"] == 75
        assert body["armor"] == 50
        assert body["ammo"] == 20
        assert body["weapon"] == "rocket"

    asyncio.run(_run())


def test_navigation_goto():
    async def _run():
        client = await _client()
        async with client:
            r = await client.post("/navigation/goto", json={"area_id": 5})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "navigating"
        assert body["target"] == 5

    asyncio.run(_run())


def test_navigation_path():
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/navigation/path")
        assert r.status_code == 200
        body = r.json()
        assert body["has_path"] is True
        assert body["path_length"] == 5
        assert body["is_stuck"] is False
        assert body["nav_target"] == "area_10"

    asyncio.run(_run())


def test_combat_engage():
    async def _run():
        client = await _client()
        async with client:
            r = await client.post("/combat/engage")
        assert r.status_code == 200
        assert r.json()["status"] == "engaging"

    asyncio.run(_run())


def test_combat_disengage():
    async def _run():
        client = await _client()
        async with client:
            r = await client.post("/combat/disengage")
        assert r.status_code == 200
        assert r.json()["status"] == "disengaged"

    asyncio.run(_run())


def test_skills_execute():
    async def _run():
        client = await _client()
        async with client:
            r = await client.post(
                "/skills/execute",
                json={"name": "move", "params": {"direction": "forward"}},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["message"] == "moved"
        assert body["data"]["direction"] == "forward"

    asyncio.run(_run())


def test_skills_catalog():
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/skills/catalog")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        assert body[0]["name"] == "move"
        assert body[0]["layer"] == "action"

    asyncio.run(_run())


def test_skills_detail():
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/skills/move")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "move"

    asyncio.run(_run())


def test_skills_not_found():
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/skills/nonexistent")
        assert r.status_code == 404

    asyncio.run(_run())


def test_strategy_current():
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/strategy/current")
        assert r.status_code == 200
        body = r.json()
        assert "brain_state" in body
        assert "current_action" in body

    asyncio.run(_run())


def test_strategy_override():
    async def _run():
        client = await _client()
        async with client:
            r = await client.post("/strategy/override", json={"action": "HUNT"})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "override_set"
        assert body["action"] == "HUNT"

    asyncio.run(_run())


def test_models():
    """Validate Pydantic models accept and reject correct data."""
    from openarena_perception.api.models import (
        HealthResponse,
        NavigationRequest,
        PerceptionStateResponse,
        SkillExecuteRequest,
    )

    # HealthResponse defaults
    h = HealthResponse()
    assert h.status == "ok"
    assert h.version == "0.1.0"

    # NavigationRequest validates
    n = NavigationRequest(area_id=5)
    assert n.area_id == 5

    # SkillExecuteRequest validates
    s = SkillExecuteRequest(name="move", params={"direction": "forward"})
    assert s.name == "move"

    # PerceptionStateResponse from_sa
    sa = _fake_sa()
    p = PerceptionStateResponse.from_sa(sa)
    assert p.tick == 42
    assert p.health == 75


def test_openapi_docs():
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/docs")
        assert r.status_code == 200

    asyncio.run(_run())


def test_full_state():
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/state/full")
        assert r.status_code == 200
        body = r.json()
        assert "brain_state" in body
        assert body["perception"] is not None
        assert body["perception"]["tick"] == 42

    asyncio.run(_run())


# ── WebSocket Tests ──────────────────────────────────────────────────


def test_websocket():
    """Connect to /ws/state, receive at least 1 message with SA fields."""
    from starlette.testclient import TestClient

    bot = _bot_with_sa()
    app = create_app(bot=bot)
    from openarena_perception.api.deps import set_bot

    set_bot(bot)
    client = TestClient(app)
    with client.websocket_connect("/ws/state") as ws:
        data = ws.receive_json()
        # Should have SA fields since last_sa is set
        assert "tick" in data
        assert data["tick"] == 42
        assert data["health"] == 75
        assert data["weapon"] == "rocket"


def test_websocket_no_sa():
    """With last_sa=None, verify receives heartbeat {"type": "waiting"}."""
    from starlette.testclient import TestClient

    bot = _bot_without_sa()
    app = create_app(bot=bot)
    from openarena_perception.api.deps import set_bot

    set_bot(bot)
    client = TestClient(app)
    with client.websocket_connect("/ws/state") as ws:
        data = ws.receive_json()
        assert data == {"type": "waiting"}


def test_metrics():
    """GET /metrics returns 200, body contains metric names."""
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/metrics/")
        assert r.status_code == 200
        body = r.text
        assert "bot_perception_fps" in body
        assert "bot_kills_total" in body
        assert "bot_deaths_total" in body
        assert "bot_llm_latency_seconds" in body
        assert "bot_stuck_total" in body
        assert "bot_tick_duration_seconds" in body

    asyncio.run(_run())


def test_metrics_content_type():
    """Response content-type is text/plain or Prometheus format."""
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/metrics/")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/plain" in ct or "text/openmetrics" in ct

    asyncio.run(_run())


# ── Integration Tests ───────────────────────────────────────────────


def test_api_skill_execute_integration():
    """POST /skills/execute with a real SkillRegistry (mocked subsystems).

    Verifies full request -> registry.execute -> SkillResult -> response cycle.
    """
    from unittest.mock import MagicMock

    from openarena_perception.skills.catalog import build_registry

    async def _run():
        ctrl = MagicMock()
        ctrl.forward = MagicMock()
        ctrl.back = MagicMock()
        bridge = MagicMock()

        registry = build_registry(ctrl, bridge)
        bot = BotState()
        bot.last_sa = _fake_sa()
        bot.registry = registry

        client = await _client(bot=bot)
        async with client:
            r = await client.post(
                "/skills/execute",
                json={"name": "move", "params": {"direction": "forward", "duration": 0.01}},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        ctrl.forward.assert_any_call(True)
        ctrl.forward.assert_any_call(False)

    asyncio.run(_run())


def test_api_skill_catalog_populated():
    """GET /skills/catalog with build_registry returns all 10 skills."""
    from unittest.mock import AsyncMock, MagicMock

    from openarena_perception.skills.catalog import build_registry

    async def _run():
        ctrl = MagicMock()
        ctrl.forward = MagicMock()
        ctrl.back = MagicMock()
        ctrl.turn_degrees = MagicMock()
        bridge = MagicMock()
        bridge.fire = MagicMock()
        bridge.select_weapon_by_name = MagicMock(return_value=True)
        engager = MagicMock()
        engager.tick = AsyncMock()
        survey = MagicMock()

        registry = build_registry(ctrl, bridge, engager=engager, survey=survey)
        bot = BotState()
        bot.last_sa = _fake_sa()
        bot.registry = registry

        client = await _client(bot=bot)
        async with client:
            r = await client.get("/skills/catalog")
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 10
        names = {e["name"] for e in body}
        assert "move" in names
        assert "turn" in names
        assert "fire" in names
        assert "weapon_select" in names
        assert "patrol" in names
        assert "room_survey" in names
        assert "combat_engage" in names
        assert "explore_map" in names
        assert "deathmatch" in names
        assert "defend_area" in names
        layers = {e["layer"] for e in body}
        assert layers == {"action", "behavior", "mission"}

    asyncio.run(_run())


def test_api_perception_all_fields():
    """Verify PerceptionStateResponse includes all key SA fields."""
    async def _run():
        client = await _client()
        async with client:
            r = await client.get("/perception/state")
        assert r.status_code == 200
        body = r.json()
        # Core SA fields must be present
        expected_fields = [
            "tick", "timestamp", "pos", "yaw", "current_area",
            "health", "armor", "ammo", "weapon", "is_alive",
            "disposition", "enemies_visible", "under_attack",
            "wall_ahead", "has_path", "is_stuck", "nav_target",
            "has_frame",
        ]
        for field in expected_fields:
            assert field in body, f"Missing field: {field}"
        # Verify specific values match our fake SA
        assert body["tick"] == 42
        assert body["pos"] == [100.0, 200.0, 300.0]
        assert body["yaw"] == 90.0
        assert body["enemies_visible"] == 2
        assert body["is_stuck"] is False

    asyncio.run(_run())


def test_websocket_stream_rate():
    """Connect WebSocket, receive 2+ messages, verify interval ~333ms (3 Hz)."""
    import time

    from starlette.testclient import TestClient

    bot = _bot_with_sa()
    app = create_app(bot=bot)
    from openarena_perception.api.deps import set_bot

    set_bot(bot)
    client = TestClient(app)
    with client.websocket_connect("/ws/state") as ws:
        t0 = time.monotonic()
        msg1 = ws.receive_json()
        msg2 = ws.receive_json()
        t1 = time.monotonic()

    elapsed = t1 - t0
    assert msg1["tick"] == 42
    assert msg2["tick"] == 42
    # At 3 Hz, two messages should take ~333ms interval.
    # Allow generous tolerance (100ms - 1500ms) for CI variability.
    assert 0.1 < elapsed < 1.5, f"Elapsed {elapsed:.3f}s outside expected range"
