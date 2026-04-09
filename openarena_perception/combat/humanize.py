"""Human-likeness overlays for aim, reaction, and personality.

Provides Perlin-noise-based aim drift, skill-level parameter mapping,
and personality presets that make bot behavior less robotic.

Created in Phase 8 (Human-Likeness).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

# ── Skill Parameter Table ───────────────────────────────────────────
# Source: 08-RESEARCH.md Code Examples, derived from FPS Bot Spec 5.1

SKILL_PARAMS: dict[int, dict[str, float]] = {
    1: {  # Novice
        "aim_noise_base": 25.0,
        "aim_noise_velocity_scale": 0.15,
        "aim_noise_distance_scale": 0.10,
        "aim_noise_turn_scale": 0.08,
        "max_accuracy": 0.25,
        "reaction_time_min": 0.35,
        "reaction_time_max": 0.55,
        "reaction_surprise_bonus": 0.15,
        "hesitation_min": 0.25,
        "hesitation_max": 0.50,
        "corner_overshoot_px": 40.0,
        "path_deviation_chance": 0.30,
        "strafe_timing_noise": 0.3,
        "decision_noise": 0.40,
    },
    2: {  # Beginner
        "aim_noise_base": 18.0,
        "aim_noise_velocity_scale": 0.12,
        "aim_noise_distance_scale": 0.08,
        "aim_noise_turn_scale": 0.06,
        "max_accuracy": 0.35,
        "reaction_time_min": 0.28,
        "reaction_time_max": 0.45,
        "reaction_surprise_bonus": 0.12,
        "hesitation_min": 0.20,
        "hesitation_max": 0.40,
        "corner_overshoot_px": 30.0,
        "path_deviation_chance": 0.20,
        "strafe_timing_noise": 0.25,
        "decision_noise": 0.30,
    },
    3: {  # Intermediate (default)
        "aim_noise_base": 12.0,
        "aim_noise_velocity_scale": 0.08,
        "aim_noise_distance_scale": 0.06,
        "aim_noise_turn_scale": 0.04,
        "max_accuracy": 0.50,
        "reaction_time_min": 0.20,
        "reaction_time_max": 0.35,
        "reaction_surprise_bonus": 0.10,
        "hesitation_min": 0.12,
        "hesitation_max": 0.30,
        "corner_overshoot_px": 20.0,
        "path_deviation_chance": 0.12,
        "strafe_timing_noise": 0.18,
        "decision_noise": 0.20,
    },
    4: {  # Advanced
        "aim_noise_base": 7.0,
        "aim_noise_velocity_scale": 0.05,
        "aim_noise_distance_scale": 0.04,
        "aim_noise_turn_scale": 0.03,
        "max_accuracy": 0.60,
        "reaction_time_min": 0.15,
        "reaction_time_max": 0.28,
        "reaction_surprise_bonus": 0.06,
        "hesitation_min": 0.08,
        "hesitation_max": 0.20,
        "corner_overshoot_px": 12.0,
        "path_deviation_chance": 0.06,
        "strafe_timing_noise": 0.10,
        "decision_noise": 0.10,
    },
    5: {  # Expert
        "aim_noise_base": 4.0,
        "aim_noise_velocity_scale": 0.03,
        "aim_noise_distance_scale": 0.02,
        "aim_noise_turn_scale": 0.02,
        "max_accuracy": 0.70,  # HARD CAP per HUMN-01
        "reaction_time_min": 0.12,
        "reaction_time_max": 0.22,
        "reaction_surprise_bonus": 0.04,
        "hesitation_min": 0.05,
        "hesitation_max": 0.12,
        "corner_overshoot_px": 6.0,
        "path_deviation_chance": 0.03,
        "strafe_timing_noise": 0.06,
        "decision_noise": 0.05,
    },
}


# ── HumanizationConfig ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class HumanizationConfig:
    """All humanization parameters derived from skill level.

    Use ``from_skill_level(1-5)`` to construct with validated defaults.
    """

    # Aim (HUMN-01)
    aim_noise_base: float
    aim_noise_velocity_scale: float
    aim_noise_distance_scale: float
    aim_noise_turn_scale: float
    max_accuracy: float

    # Reaction time (HUMN-02)
    reaction_time_min: float
    reaction_time_max: float
    reaction_surprise_bonus: float

    # Movement (HUMN-03)
    corner_overshoot_px: float
    path_deviation_chance: float
    strafe_timing_noise: float

    # Hesitation (HUMN-06)
    hesitation_min: float
    hesitation_max: float

    # Decision quality (HUMN-07)
    decision_noise: float

    @classmethod
    def from_skill_level(cls, level: int) -> HumanizationConfig:
        """Map skill level 1-5 to concrete parameters.

        Raises ``ValueError`` for out-of-range levels.
        """
        if level < 1 or level > 5:
            raise ValueError(
                f"skill_level must be 1-5, got {level}"
            )
        params = SKILL_PARAMS[level]
        return cls(**params)


# ── PersonalityProfile ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PersonalityProfile:
    """Bot personality affecting combat and decision preferences."""

    name: str
    aggression: float       # 0.0-1.0
    caution: float          # 0.0-1.0
    weapon_preference: str  # preferred weapon type
    grudge_factor: float    # 0.0-1.0


PERSONALITIES: dict[str, PersonalityProfile] = {
    "aggressive": PersonalityProfile(
        name="aggressive",
        aggression=0.9,
        caution=0.2,
        weapon_preference="rocket",
        grudge_factor=0.6,
    ),
    "cautious": PersonalityProfile(
        name="cautious",
        aggression=0.3,
        caution=0.8,
        weapon_preference="railgun",
        grudge_factor=0.2,
    ),
    "balanced": PersonalityProfile(
        name="balanced",
        aggression=0.5,
        caution=0.5,
        weapon_preference="lightning",
        grudge_factor=0.4,
    ),
    "grudge": PersonalityProfile(
        name="grudge",
        aggression=0.7,
        caution=0.3,
        weapon_preference="rocket",
        grudge_factor=0.9,
    ),
}


# ── PerlinNoise1D ───────────────────────────────────────────────────


class PerlinNoise1D:
    """Lightweight 1D Perlin noise for aim drift.

    Produces temporally smooth values in [-1, 1] using quintic fade
    interpolation and a seeded 256-entry gradient table.
    """

    def __init__(self, seed: int = 42) -> None:
        rng = np.random.default_rng(seed)
        self._perm = rng.permutation(256).astype(np.int32)

    def __call__(self, t: float) -> float:
        """Return noise value in [-1, 1] at time *t*."""
        t0 = int(np.floor(t)) & 255
        t1 = (t0 + 1) & 255
        frac = t - np.floor(t)
        # Quintic fade: t^3*(t*(t*6-15)+10)
        fade = frac * frac * frac * (frac * (frac * 6 - 15) + 10)
        g0 = self._grad(self._perm[t0], frac)
        g1 = self._grad(self._perm[t1], frac - 1.0)
        return float(g0 + fade * (g1 - g0))

    @staticmethod
    def _grad(hash_val: int, x: float) -> float:
        """Pseudo-random gradient: +x or -x based on hash parity."""
        return x if (hash_val & 1) == 0 else -x


# ── AimHumanizer ────────────────────────────────────────────────────


class AimHumanizer:
    """Generates Perlin-noise-based aim offsets scaled by context.

    The returned (noise_x, noise_y) should be added to the aim target
    *before* PID processing to avoid integral windup.
    """

    def __init__(self, config: HumanizationConfig, seed: int = 42) -> None:
        self._cfg = config
        self._perlin_x = PerlinNoise1D(seed=seed)
        self._perlin_y = PerlinNoise1D(seed=seed + 1)
        self._rng = np.random.default_rng(seed + 2)

    def sample(
        self,
        t: float,
        target_velocity: float = 0.0,
        target_distance: float = 100.0,
        turn_rate: float = 0.0,
    ) -> Tuple[float, float]:
        """Return (noise_x, noise_y) aim offset at time *t*.

        Parameters
        ----------
        t : float
            Current time (seconds). Drives Perlin noise phase.
        target_velocity : float
            Target speed in px/s (increases noise).
        target_distance : float
            Distance to target in pixels (scales noise).
        turn_rate : float
            Bot turn rate in deg/s (increases noise).
        """
        cfg = self._cfg

        # Base Perlin drift (smooth, temporally coherent)
        base_x = self._perlin_x(t * 0.8) * cfg.aim_noise_base
        base_y = self._perlin_y(t * 0.8) * cfg.aim_noise_base

        # Context-dependent noise scales
        velocity_noise = target_velocity * cfg.aim_noise_velocity_scale
        distance_noise = (target_distance / 100.0) * cfg.aim_noise_distance_scale * cfg.aim_noise_base
        turn_noise = turn_rate * cfg.aim_noise_turn_scale

        # Gaussian perturbation on top of Perlin base
        gauss_scale = velocity_noise + turn_noise + 1.0
        gauss_x = self._rng.normal(0.0, gauss_scale)
        gauss_y = self._rng.normal(0.0, gauss_scale)

        # Distance factor as additional offset
        dist_factor_x = self._rng.normal(0.0, distance_noise + 0.1)
        dist_factor_y = self._rng.normal(0.0, distance_noise + 0.1)

        total_x = base_x + gauss_x + dist_factor_x
        total_y = base_y + gauss_y + dist_factor_y

        return (float(total_x), float(total_y))
