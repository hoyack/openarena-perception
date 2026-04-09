"""Perception pipeline configuration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openarena_perception.tactics.timescale import TimescaleConfig


@dataclass(frozen=True)
class PerceptionPipelineConfig:
    """Tick budget and rate-limiting configuration for the perception pipeline."""

    # Rate limits (run every N ticks)
    hud_ocr_interval: int = 30        # ~2s at 15 FPS -- Tesseract is ~1800ms
    motion_interval: int = 2           # every other tick
    tracker_interval: int = 2          # every other tick
    anomaly_interval: int = 3          # every 3rd tick

    # Attention overrides during combat
    combat_tracker_interval: int = 1   # every tick during combat
    combat_anomaly_enabled: bool = False  # skip anomaly during combat

    # Sound polling (PERC-08)
    sound_poll_interval: int = 8  # poll game log every N ticks (~2 Hz at 15 FPS)

    # Death reset
    reset_on_death: bool = True

    @classmethod
    def from_timescale(
        cls, ts: TimescaleConfig, base_hz: float = 15.0
    ) -> PerceptionPipelineConfig:
        """Derive tick intervals from explicit timescale config.

        Alternative constructor that computes rate-limiting intervals from
        a TimescaleConfig. The default constructor remains unchanged --
        this is an opt-in bridge between the two config systems.
        """
        return cls(
            hud_ocr_interval=max(1, round(base_hz / 5.0)),       # HUD at ~5 Hz
            motion_interval=max(1, round(base_hz / 7.5)),         # Motion at ~7.5 Hz
            tracker_interval=max(1, round(base_hz / 7.5)),        # Tracker at ~7.5 Hz
            combat_tracker_interval=1,                             # Every tick in combat
            anomaly_interval=max(1, round(base_hz / 3.75)),       # Anomaly at ~3.75 Hz
            sound_poll_interval=ts.ticks_per_call("sound_poll", base_hz),
        )
