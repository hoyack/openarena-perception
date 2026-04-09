"""FastAPI application factory.

``create_app()`` builds the app with lifespan, CORS, routers,
WebSocket state streaming, and Prometheus metrics.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .deps import BotState, set_bot
from .models import BotFullStateResponse, HealthResponse, PerceptionStateResponse


def create_app(bot: BotState | None = None) -> FastAPI:
    """Build and return the FastAPI application.

    Args:
        bot: Optional BotState to inject.  If *None* a fresh empty
             BotState is created (useful for smoke-testing startup).
    """
    if bot is None:
        bot = BotState()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.bot = bot
        set_bot(bot)
        yield

    app = FastAPI(
        title="OpenArena Bot API",
        version="0.1.0",
        description="LLM agent control interface for OpenArena bot",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Pi-local, no auth needed
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Routers ---
    from .routers import combat, navigation, perception, skills, strategy
    from .ws import ws_router

    app.include_router(perception.router, prefix="/perception", tags=["perception"])
    app.include_router(navigation.router, prefix="/navigation", tags=["navigation"])
    app.include_router(combat.router, prefix="/combat", tags=["combat"])
    app.include_router(skills.router, prefix="/skills", tags=["skills"])
    app.include_router(strategy.router, prefix="/strategy", tags=["strategy"])
    app.include_router(ws_router)

    # --- Prometheus metrics ---
    from .metrics import metrics_app

    app.mount("/metrics", metrics_app)

    # --- Top-level endpoints ---

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/state/full", response_model=BotFullStateResponse, tags=["system"])
    async def full_state() -> BotFullStateResponse:
        from .deps import get_bot

        b = get_bot()
        brain = "unknown"
        if b.fsm is not None:
            brain = getattr(b.fsm, "state", getattr(b.fsm, "_state", "unknown"))
            if hasattr(brain, "value"):
                brain = brain.value
        perception = None
        if b.last_sa is not None:
            perception = PerceptionStateResponse.from_sa(b.last_sa)
        return BotFullStateResponse(
            brain_state=str(brain),
            perception=perception,
        )

    return app
