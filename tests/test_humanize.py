"""Tests for combat humanization — aim noise, skill configs, personalities.

Covers HUMN-01, HUMN-04, HUMN-07 requirements.
"""
from __future__ import annotations

import math

import pytest


# ── HumanizationConfig ──────────────────────────────────────────────


class TestHumanizationConfig:
    """HUMN-07: Skill level 1-5 produces valid configs."""

    def test_skill_level_1(self):
        from openarena_perception.combat.humanize import HumanizationConfig

        cfg = HumanizationConfig.from_skill_level(1)
        assert cfg.aim_noise_base == 25.0
        assert cfg.max_accuracy == 0.25
        assert cfg.reaction_time_min == 0.35

    def test_skill_level_5(self):
        from openarena_perception.combat.humanize import HumanizationConfig

        cfg = HumanizationConfig.from_skill_level(5)
        assert cfg.aim_noise_base == 4.0
        assert cfg.max_accuracy == 0.70
        assert cfg.reaction_time_min == 0.12

    def test_skill_level_3(self):
        from openarena_perception.combat.humanize import HumanizationConfig

        cfg = HumanizationConfig.from_skill_level(3)
        assert cfg.aim_noise_base == 12.0
        assert cfg.max_accuracy == 0.50

    def test_hard_cap_all_levels(self):
        from openarena_perception.combat.humanize import HumanizationConfig

        for level in range(1, 6):
            cfg = HumanizationConfig.from_skill_level(level)
            assert cfg.max_accuracy <= 0.70, f"Level {level} exceeds 0.70 cap"

    def test_invalid_level_0(self):
        from openarena_perception.combat.humanize import HumanizationConfig

        with pytest.raises(ValueError):
            HumanizationConfig.from_skill_level(0)

    def test_invalid_level_6(self):
        from openarena_perception.combat.humanize import HumanizationConfig

        with pytest.raises(ValueError):
            HumanizationConfig.from_skill_level(6)

    def test_frozen(self):
        from openarena_perception.combat.humanize import HumanizationConfig

        cfg = HumanizationConfig.from_skill_level(3)
        with pytest.raises(AttributeError):
            cfg.max_accuracy = 0.99  # type: ignore[misc]


# ── PersonalityProfile ──────────────────────────────────────────────


class TestPersonality:
    """HUMN-04: Four distinct named personality presets."""

    def test_four_presets(self):
        from openarena_perception.combat.humanize import PERSONALITIES

        assert len(PERSONALITIES) == 4
        assert set(PERSONALITIES.keys()) == {"aggressive", "cautious", "balanced", "grudge"}

    def test_aggressive(self):
        from openarena_perception.combat.humanize import PERSONALITIES

        p = PERSONALITIES["aggressive"]
        assert p.aggression == 0.9
        assert p.caution == 0.2

    def test_cautious(self):
        from openarena_perception.combat.humanize import PERSONALITIES

        p = PERSONALITIES["cautious"]
        assert p.aggression == 0.3
        assert p.caution == 0.8

    def test_balanced(self):
        from openarena_perception.combat.humanize import PERSONALITIES

        p = PERSONALITIES["balanced"]
        assert p.aggression == 0.5
        assert p.caution == 0.5

    def test_grudge(self):
        from openarena_perception.combat.humanize import PERSONALITIES

        p = PERSONALITIES["grudge"]
        assert p.grudge_factor == 0.9


# ── PerlinNoise1D ───────────────────────────────────────────────────


class TestPerlinNoise1D:
    """Perlin noise produces smooth values in [-1, 1]."""

    def test_range(self):
        from openarena_perception.combat.humanize import PerlinNoise1D

        noise = PerlinNoise1D(seed=42)
        for t in [i * 0.1 for i in range(200)]:
            v = noise(t)
            assert -1.0 <= v <= 1.0, f"Out of range at t={t}: {v}"

    def test_temporal_smoothness(self):
        from openarena_perception.combat.humanize import PerlinNoise1D

        noise = PerlinNoise1D(seed=42)
        prev = noise(0.0)
        for i in range(1, 100):
            t = i * 0.05
            curr = noise(t)
            assert abs(curr - prev) < 0.5, f"Jump too large at t={t}: {abs(curr - prev)}"
            prev = curr

    def test_deterministic(self):
        from openarena_perception.combat.humanize import PerlinNoise1D

        a = PerlinNoise1D(seed=99)
        b = PerlinNoise1D(seed=99)
        for t in [0.0, 1.5, 3.7, 10.2]:
            assert a(t) == b(t)


# ── AimHumanizer ────────────────────────────────────────────────────


class TestAimHumanizer:
    """HUMN-01: Aim noise scaled by velocity, distance, turn rate."""

    def test_returns_tuple(self):
        from openarena_perception.combat.humanize import AimHumanizer, HumanizationConfig

        cfg = HumanizationConfig.from_skill_level(3)
        h = AimHumanizer(cfg, seed=42)
        result = h.sample(t=1.0, target_velocity=0.0, target_distance=100.0, turn_rate=0.0)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_base_noise_floor(self):
        from openarena_perception.combat.humanize import AimHumanizer, HumanizationConfig

        cfg = HumanizationConfig.from_skill_level(3)
        h = AimHumanizer(cfg, seed=42)
        # Sample many times — magnitude should generally be above noise floor
        magnitudes = []
        for i in range(100):
            nx, ny = h.sample(t=i * 0.1, target_velocity=0.0, target_distance=100.0, turn_rate=0.0)
            magnitudes.append(math.hypot(nx, ny))
        avg_mag = sum(magnitudes) / len(magnitudes)
        # Average magnitude should be meaningful (at least 30% of base noise)
        assert avg_mag >= cfg.aim_noise_base * 0.3, f"Average magnitude {avg_mag} too low"

    def test_high_velocity_more_noise(self):
        from openarena_perception.combat.humanize import AimHumanizer, HumanizationConfig

        cfg = HumanizationConfig.from_skill_level(3)
        h_low = AimHumanizer(cfg, seed=42)
        h_high = AimHumanizer(cfg, seed=42)

        mags_low = []
        mags_high = []
        for i in range(200):
            t = i * 0.05
            nx, ny = h_low.sample(t=t, target_velocity=0.0, target_distance=100.0, turn_rate=0.0)
            mags_low.append(math.hypot(nx, ny))
            nx, ny = h_high.sample(t=t, target_velocity=500.0, target_distance=100.0, turn_rate=0.0)
            mags_high.append(math.hypot(nx, ny))

        avg_low = sum(mags_low) / len(mags_low)
        avg_high = sum(mags_high) / len(mags_high)
        assert avg_high > avg_low, f"High velocity ({avg_high}) should produce more noise than zero ({avg_low})"
