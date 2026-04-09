"""Perception pipeline configuration."""
from dataclasses import dataclass


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
