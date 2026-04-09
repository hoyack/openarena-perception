"""Prometheus metric definitions and ASGI sub-app.

Metrics are module-level singletons -- import them from subsystems to
instrument FPS, kills, deaths, LLM latency, stuck events, and tick duration.

Mount ``metrics_app`` at ``/metrics`` in the FastAPI application.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

# ── Metric singletons ───────────────────────────────────────────────

PERCEPTION_FPS = Gauge("bot_perception_fps", "Perception pipeline FPS")

KILL_COUNTER = Counter("bot_kills_total", "Total kills")

DEATH_COUNTER = Counter("bot_deaths_total", "Total deaths")

LLM_LATENCY = Histogram(
    "bot_llm_latency_seconds",
    "LLM strategy call latency",
    buckets=[0.5, 1.0, 2.0, 4.0, 8.0, 15.0],
)

STUCK_COUNTER = Counter("bot_stuck_total", "Times bot got stuck")

TICK_DURATION = Histogram(
    "bot_tick_duration_seconds",
    "Game tick duration",
    buckets=[0.01, 0.02, 0.03, 0.05, 0.08, 0.1],
)

# ── ASGI sub-app ────────────────────────────────────────────────────

metrics_app = make_asgi_app()
