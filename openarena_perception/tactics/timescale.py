"""Multi-timescale decision architecture configuration (COMP-03).

Formalizes the rate boundaries between cognitive layers into an explicit,
frozen configuration. The codebase already implements multi-timescale
naturally -- this module makes those rates documentable, tunable, and
enforceable.

Exports:
    TimescaleConfig -- frozen dataclass with Hz rates per layer
    rate_limited -- decorator enforcing max call frequency
    DEFAULT_TIMESCALE -- module-level default instance
"""

from __future__ import annotations

import functools
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class TimescaleConfig:
    """Explicit tick rate boundaries per cognitive layer.

    Documents the multi-timescale decision architecture:
    - Fast layer (10-22 Hz): perception, reflexes, combat, tactics
    - Medium layer (~1-2 Hz): sound polling, item timing
    - Slow layer (~0.2-0.33 Hz): commander goal selection, LLM strategy

    These rates are architectural requirements, not incidental.
    Perception hardware (Pi 5) sets the fast-layer ceiling.
    LLM latency (~4-5s) sets the slow-layer floor.
    """

    perception_hz: float = 15.0
    reflex_hz: float = 15.0
    combat_hz: float = 15.0
    tactics_hz: float = 15.0
    commander_hz: float = 0.33       # DECISION_INTERVAL = 3s
    strategy_hz: float = 0.2         # LLM every ~5s
    sound_poll_hz: float = 2.0       # log file check 2x/sec
    item_timing_hz: float = 1.0      # recalculate predictions 1x/sec

    def interval_seconds(self, layer: str) -> float:
        """Return minimum seconds between calls for a layer."""
        hz = getattr(self, f"{layer}_hz", None)
        if hz is None or hz <= 0:
            raise ValueError(f"Unknown layer: {layer}")
        return 1.0 / hz

    def ticks_per_call(self, layer: str, base_hz: float = 15.0) -> int:
        """Return tick interval for rate-limiting at base_hz tick rate."""
        hz = getattr(self, f"{layer}_hz", None)
        if hz is None or hz <= 0:
            raise ValueError(f"Unknown layer: {layer}")
        return max(1, round(base_hz / hz))


def rate_limited(min_interval_seconds: float):
    """Decorator that enforces minimum time between calls.

    Returns None if called too soon. Uses time.time() for wall-clock
    comparison (same pattern as Commander.should_decide()).
    """

    def decorator(fn):
        last_call_time = [0.0]  # mutable container for closure

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            now = time.time()
            if now - last_call_time[0] < min_interval_seconds:
                return None
            last_call_time[0] = now
            return fn(*args, **kwargs)

        wrapper._last_call_time = last_call_time  # expose for testing
        return wrapper

    return decorator


DEFAULT_TIMESCALE = TimescaleConfig()
