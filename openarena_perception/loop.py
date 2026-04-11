"""
loop.py — OpenArena perception loop.

Orchestrates screen capture → HUD parsing → world parsing → GameState output.

Two usage patterns:

  1. SYNC BLOCKING (simple scripts, direct agent polling):

        loop = PerceptionLoop(cfg)
        loop.start()
        while True:
            state = loop.tick()
            print(state.summary())
            time.sleep(0.05)
        loop.stop()

  2. ASYNC CALLBACK (event-driven agents, OpenClaw integration):

        async def on_state(state: GameState):
            await agent.observe(state.to_dict())

        loop = PerceptionLoop(cfg, on_state=on_state, target_fps=20)
        await loop.run_async()        # runs until cancelled
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Coroutine, List, Optional, Any

import numpy as np

from .capture import ScreenCapture, make_capture
from .config import PerceptionConfig
from .game_state import GameState
from .hud_parser import HUDParser
from .world_parser import WorldParser

log = logging.getLogger(__name__)

StateCallback = Callable[[GameState], Coroutine[Any, Any, None]]


class PerceptionLoop:
    """
    Full perception loop. Combines capture + HUD + world parsing
    into a single GameState per tick.
    """

    def __init__(
        self,
        cfg: PerceptionConfig,
        capture: Optional[ScreenCapture] = None,
        on_state: Optional[StateCallback] = None,
        target_fps: float = 20.0,
        keep_frame: bool = False,   # attach raw frame to GameState (memory cost)
        capture_mode: str = "window",
    ):
        self.cfg         = cfg
        self.on_state    = on_state
        self.target_fps  = target_fps
        self.keep_frame  = keep_frame

        # Build sub-parsers
        self._hud    = HUDParser(cfg)
        self._world  = WorldParser(cfg)

        # Build or accept capture backend
        self._capture = capture or make_capture(
            mode=capture_mode,
            window_title=cfg.window_title,
        )

        # State
        self._running    = False
        self._frame_id   = 0
        self._last_state: Optional[GameState] = None

        # Perf counters
        self._tick_times: List[float] = []

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self):
        """Open the capture context. Call before tick()."""
        self._capture.open()
        self._running = True
        log.info("PerceptionLoop started — target %.0f FPS", self.target_fps)

    def stop(self):
        """Close the capture context."""
        self._running = False
        self._capture.close()
        if self._tick_times:
            avg_ms = (sum(self._tick_times) / len(self._tick_times)) * 1000
            log.info("PerceptionLoop stopped — avg tick %.1f ms (%.0f FPS)",
                     avg_ms, 1000 / avg_ms if avg_ms > 0 else 0)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()

    # ── Sync tick ────────────────────────────────────────────────────────────

    def tick(self) -> GameState:
        """
        Capture one frame and produce a GameState.
        Call in your own loop at whatever rate you want.
        """
        t0 = time.perf_counter()

        frame = self._capture.grab()
        state = self._parse_frame(frame)

        self._last_state = state
        self._frame_id  += 1
        self._tick_times.append(time.perf_counter() - t0)
        if len(self._tick_times) > 200:
            self._tick_times.pop(0)

        return state

    def run_sync(self, max_frames: int = 0):
        """
        Blocking loop. Runs until max_frames reached (0 = forever).
        Calls on_state synchronously if provided (must be a regular function).
        """
        with self:
            interval = 1.0 / self.target_fps
            frame_count = 0
            while self._running:
                t0 = time.perf_counter()
                state = self.tick()

                if self.on_state:
                    self.on_state(state)   # type: ignore[arg-type]

                frame_count += 1
                if max_frames and frame_count >= max_frames:
                    break

                elapsed = time.perf_counter() - t0
                sleep_for = interval - elapsed
                if sleep_for > 0:
                    time.sleep(sleep_for)

    # ── Async loop ───────────────────────────────────────────────────────────

    async def run_async(self, max_frames: int = 0):
        """
        Async loop. Yields control to the event loop between ticks.
        on_state must be an async callable.

        Usage:
            loop = PerceptionLoop(cfg, on_state=my_async_handler, target_fps=20)
            await loop.run_async()
        """
        self.start()
        interval = 1.0 / self.target_fps
        frame_count = 0

        try:
            while self._running:
                t0 = time.perf_counter()

                # Run capture+parse synchronously — mss is not thread-safe
                # (uses thread-local X11 display handles)
                state = self.tick()

                if self.on_state:
                    await self.on_state(state)

                frame_count += 1
                if max_frames and frame_count >= max_frames:
                    break

                elapsed = time.perf_counter() - t0
                sleep_for = interval - elapsed
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
        except asyncio.CancelledError:
            log.info("PerceptionLoop cancelled.")
        finally:
            self.stop()

    # ── Internals ────────────────────────────────────────────────────────────

    def _parse_frame(self, frame: np.ndarray) -> GameState:
        """
        Fast parsing: enemy detection every tick, HUD OCR only every N ticks.
        Enemy detection: ~8ms. HUD OCR: ~1800ms (Tesseract on Pi).
        """
        enemies = self._world.parse_enemies(frame)

        # HUD OCR runs every ~30 ticks (~2-3 seconds) to avoid bottleneck
        hud = {"health": None, "armor": None, "ammo": None,
               "weapon": None, "frags": None, "deaths": None}

        if self._frame_id % 30 == 0:
            # Only parse health and ammo (skip frags/deaths/weapon — use RCON)
            hud["health"] = self._hud.parse_health(frame)
            hud["ammo"] = self._hud.parse_ammo(frame)
        elif hasattr(self, '_last_hud'):
            hud = self._last_hud
        self._last_hud = hud

        return GameState(
            frame_id=self._frame_id,
            health=hud["health"],
            armor=hud["armor"],
            ammo=hud["ammo"],
            weapon=hud["weapon"],
            frags=hud["frags"],
            deaths=hud["deaths"],
            enemies=enemies,
            frame=frame if self.keep_frame else None,
        )

    # ── Diagnostics ──────────────────────────────────────────────────────────

    @property
    def avg_fps(self) -> float:
        if not self._tick_times:
            return 0.0
        avg = sum(self._tick_times) / len(self._tick_times)
        return 1.0 / avg if avg > 0 else 0.0

    @property
    def last_tick_ms(self) -> float:
        """Most recent tick duration in milliseconds, or 0.0 if none yet.

        Exposed for the Open-Perception HUD (Phase 12) to display frame lag
        without needing to poke at the private `_tick_times` list.
        """
        return (self._tick_times[-1] * 1000.0) if self._tick_times else 0.0

    @property
    def last_state(self) -> Optional[GameState]:
        return self._last_state
