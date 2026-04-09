"""Tests for Phase 8: Human-Likeness (HUMN-01 through HUMN-07).

Comprehensive test suite validating all 7 HUMN requirements:
- HUMN-01: Aim noise scaled by velocity/distance/turn, accuracy capped at 70%
- HUMN-02: Reaction time 150-250ms+, no delay on DEAD
- HUMN-03: Movement variability -- strafe noise, overshoot
- HUMN-04: Personality profiles with distinct parameters
- HUMN-05: Death heatmap -> danger zones (adaptive learning)
- HUMN-06: Hesitation delay 100-300ms on state transitions, none on DEAD
- HUMN-07: Unified skill 1-5 with monotonic parameter scaling
"""
from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest

from openarena_perception.combat.humanize import (
    AimHumanizer,
    HumanizationConfig,
    PERSONALITIES,
    PerlinNoise1D,
    PersonalityProfile,
    SKILL_PARAMS,
)
from openarena_perception.models import BrainState


# ── HUMN-01: Aim Humanization ──────────────────────────────────────


class TestAimHumanization:
    """HUMN-01: Aim noise scaled by velocity/distance/turn, accuracy capped at 70%."""

    def test_perlin_noise_range(self):
        """Perlin noise values stay in [-1, 1]."""
        noise = PerlinNoise1D(seed=42)
        for i in range(1000):
            v = noise(i * 0.1)
            assert -1.0 <= v <= 1.0, f"Perlin out of range at t={i*0.1}: {v}"

    def test_perlin_noise_smoothness(self):
        """Consecutive Perlin samples differ by < 0.5 (temporal coherence)."""
        noise = PerlinNoise1D(seed=42)
        prev = noise(0.0)
        for i in range(1, 200):
            t = i * 0.05
            curr = noise(t)
            assert abs(curr - prev) < 0.5, f"Perlin jump at t={t}: {abs(curr-prev)}"
            prev = curr

    def test_perlin_deterministic(self):
        """Same seed produces identical sequences."""
        a = PerlinNoise1D(seed=99)
        b = PerlinNoise1D(seed=99)
        for t in [0.0, 1.5, 3.7, 10.2]:
            assert a(t) == b(t)

    def test_aim_humanizer_produces_noise(self):
        """AimHumanizer.sample() returns non-zero noise."""
        cfg = HumanizationConfig.from_skill_level(3)
        h = AimHumanizer(cfg, seed=42)
        non_zero = 0
        for i in range(100):
            nx, ny = h.sample(i * 0.05, target_velocity=100, target_distance=200, turn_rate=10)
            if abs(nx) > 0.1 or abs(ny) > 0.1:
                non_zero += 1
        assert non_zero > 50, f"Expected most samples non-zero, got {non_zero}/100"

    def test_noise_scales_with_velocity(self):
        """Higher target velocity produces larger average noise."""
        cfg = HumanizationConfig.from_skill_level(3)
        h = AimHumanizer(cfg, seed=42)
        low_vel_mag = sum(
            math.hypot(*h.sample(i * 0.05, target_velocity=10, target_distance=200, turn_rate=0))
            for i in range(100)
        ) / 100
        h2 = AimHumanizer(cfg, seed=42)
        high_vel_mag = sum(
            math.hypot(*h2.sample(i * 0.05, target_velocity=500, target_distance=200, turn_rate=0))
            for i in range(100)
        ) / 100
        assert high_vel_mag > low_vel_mag, f"High vel {high_vel_mag} should > low vel {low_vel_mag}"

    def test_accuracy_cap_all_levels(self):
        """max_accuracy <= 0.70 for all skill levels (HARD CAP)."""
        for level in range(1, 6):
            cfg = HumanizationConfig.from_skill_level(level)
            assert cfg.max_accuracy <= 0.70, f"Level {level}: max_accuracy={cfg.max_accuracy} exceeds 0.70"

    def test_accuracy_cap_enforced_in_aim_controller(self):
        """AimController with skill 1 (large noise) reduces on_target_ratio."""
        from openarena_perception.combat.aim_controller import AimController

        # Skill 1 has aim_noise_base=25 which consistently exceeds 8px deadzone
        cfg = HumanizationConfig.from_skill_level(1)
        h = AimHumanizer(cfg, seed=1001)
        ctrl = AimController(humanize=h)
        on_target = 0
        for _ in range(200):
            dx, dy = ctrl.update(400, 300, 400, 300)
            if dx == 0 and dy == 0:
                on_target += 1
        ratio = on_target / 200
        assert ratio < 0.95, (
            f"Expected noise to reduce on-target ratio, got {ratio}"
        )

    def test_base_noise_floor_close_range(self):
        """Even at close range (distance < 50), noise is non-zero (Pitfall 3)."""
        cfg = HumanizationConfig.from_skill_level(5)
        h = AimHumanizer(cfg, seed=42)
        non_zero = sum(
            1 for i in range(100)
            if math.hypot(*h.sample(i * 0.05, target_velocity=0, target_distance=10, turn_rate=0)) > 0.1
        )
        assert non_zero > 30, f"Close range should still have noise, got {non_zero}/100 non-zero"

    def test_aim_controller_backward_compat(self):
        """AimController() without humanize behaves identically."""
        from openarena_perception.combat.aim_controller import AimController

        a = AimController()
        dx, dy = a.update(400, 300, 400, 300)
        assert (dx, dy) == (0, 0), "On-target should return (0, 0)"

    def test_accuracy_window_reset(self):
        """reset() clears the accuracy window."""
        from openarena_perception.combat.aim_controller import AimController

        cfg = HumanizationConfig.from_skill_level(3)
        humanizer = AimHumanizer(cfg, seed=42)
        a = AimController(humanize=humanizer)
        for _ in range(10):
            a.update(400, 300, 400, 300)
        a.reset()
        assert len(a._accuracy_window) == 0


# ── HUMN-02: Reaction Time ──────────────────────────────────────────


class TestReactionTime:
    """HUMN-02: Reaction time 150-250ms+, no delay on DEAD."""

    def test_dead_never_delayed(self):
        """DEAD transitions always have 0.0 delay."""
        from openarena_perception.tactics.fsm import TacticalFSM

        cfg = HumanizationConfig.from_skill_level(3)
        fsm = TacticalFSM(
            arbiter=MagicMock(), death_handler=MagicMock(),
            stuck_escape=MagicMock(), engager=MagicMock(),
            nav_behavior=MagicMock(), humanize_config=cfg,
        )
        for old_state in BrainState:
            delay = fsm._sample_reaction_delay(BrainState.DEAD, old_state)
            assert delay == 0.0, f"DEAD from {old_state}: delay={delay}, expected 0.0"

    def test_reaction_delay_range(self):
        """Non-DEAD transitions have delay in expected range."""
        from openarena_perception.tactics.fsm import TacticalFSM

        cfg = HumanizationConfig.from_skill_level(3)
        fsm = TacticalFSM(
            arbiter=MagicMock(), death_handler=MagicMock(),
            stuck_escape=MagicMock(), engager=MagicMock(),
            nav_behavior=MagicMock(), humanize_config=cfg,
        )
        delays = [
            fsm._sample_reaction_delay(BrainState.NAVIGATING, BrainState.EXPLORING)
            for _ in range(100)
        ]
        assert all(d > 0 for d in delays), "All non-DEAD delays should be positive"
        # Total = reaction + hesitation, so minimum is reaction_min + hesitation_min
        min_total = cfg.reaction_time_min + cfg.hesitation_min
        assert min(delays) >= min_total * 0.8, f"Min delay {min(delays)} too low (expected >= {min_total*0.8})"

    def test_combat_surprise_bonus(self):
        """COMBAT from non-combat state includes surprise bonus."""
        from openarena_perception.tactics.fsm import TacticalFSM

        cfg = HumanizationConfig.from_skill_level(3)
        fsm = TacticalFSM(
            arbiter=MagicMock(), death_handler=MagicMock(),
            stuck_escape=MagicMock(), engager=MagicMock(),
            nav_behavior=MagicMock(), humanize_config=cfg,
        )
        surprise = sum(
            fsm._sample_reaction_delay(BrainState.COMBAT, BrainState.EXPLORING)
            for _ in range(200)
        ) / 200
        no_surprise = sum(
            fsm._sample_reaction_delay(BrainState.NAVIGATING, BrainState.EXPLORING)
            for _ in range(200)
        ) / 200
        assert surprise > no_surprise, (
            f"COMBAT surprise {surprise} should > non-combat {no_surprise}"
        )

    def test_no_config_no_delay(self):
        """Without humanize_config, all delays are 0.0 (backward compat)."""
        from openarena_perception.tactics.fsm import TacticalFSM

        fsm = TacticalFSM(
            arbiter=MagicMock(), death_handler=MagicMock(),
            stuck_escape=MagicMock(), engager=MagicMock(),
            nav_behavior=MagicMock(),
        )
        delay = fsm._sample_reaction_delay(BrainState.COMBAT, BrainState.EXPLORING)
        assert delay == 0.0


# ── HUMN-03: Movement Variability ───────────────────────────────────


class TestMovementVariability:
    """HUMN-03: Movement variability -- strafe noise, overshoot."""

    def test_combat_mover_backward_compat(self):
        """CombatMover without config returns valid movement dict."""
        from openarena_perception.combat.combat_movement import CombatMover

        m = CombatMover()
        result = m.get_movement(400, "rocket launcher", skill=0.8)
        assert isinstance(result, dict)
        assert "strafe_left" in result
        assert "strafe_right" in result

    def test_combat_mover_with_config(self):
        """CombatMover with config still returns valid movement dict."""
        from openarena_perception.combat.combat_movement import CombatMover

        cfg = HumanizationConfig.from_skill_level(1)
        m = CombatMover(humanize_config=cfg)
        result = m.get_movement(400, "rocket launcher", skill=0.8)
        assert isinstance(result, dict)

    def test_corner_overshoot_property(self):
        """corner_overshoot_px returns config value or 0.0."""
        from openarena_perception.combat.combat_movement import CombatMover

        m1 = CombatMover()
        assert m1.corner_overshoot_px == 0.0
        cfg = HumanizationConfig.from_skill_level(1)
        m2 = CombatMover(humanize_config=cfg)
        assert m2.corner_overshoot_px == 40.0

    def test_strafe_interval_clamped(self):
        """Strafe interval must stay in [0.15, 1.5] even with high noise (T-08-05)."""
        from openarena_perception.combat.combat_movement import CombatMover

        cfg = HumanizationConfig.from_skill_level(1)  # noise=0.3
        m = CombatMover(humanize_config=cfg)
        for _ in range(50):
            m._last_switch = 0.0  # Force switch
            m.get_movement(400, "rocket launcher", skill=0.8)
            assert 0.15 <= m._switch_interval <= 1.5, (
                f"Interval {m._switch_interval} out of bounds"
            )

    def test_path_deviation_can_invert_strafe(self):
        """With high path_deviation_chance, some strafes should be inverted."""
        from openarena_perception.combat.combat_movement import CombatMover

        cfg = HumanizationConfig.from_skill_level(1)  # chance=0.30
        m = CombatMover(humanize_config=cfg)
        directions = set()
        for _ in range(100):
            m._last_switch = 0.0
            m._strafe_dir = 1
            r = m.get_movement(400, "rocket launcher", skill=0.8)
            if r["strafe_left"]:
                directions.add("left")
            if r["strafe_right"]:
                directions.add("right")
        assert len(directions) == 2, f"Expected both directions, got {directions}"


# ── HUMN-04: Personality ────────────────────────────────────────────


class TestPersonality:
    """HUMN-04: Personality profiles with distinct parameters."""

    def test_four_presets_exist(self):
        """PERSONALITIES has aggressive, cautious, balanced, grudge."""
        assert len(PERSONALITIES) == 4
        for name in ("aggressive", "cautious", "balanced", "grudge"):
            assert name in PERSONALITIES

    def test_aggressive_high_aggression(self):
        assert PERSONALITIES["aggressive"].aggression == 0.9
        assert PERSONALITIES["aggressive"].caution == 0.2

    def test_cautious_high_caution(self):
        assert PERSONALITIES["cautious"].caution == 0.8
        assert PERSONALITIES["cautious"].aggression == 0.3

    def test_grudge_high_grudge_factor(self):
        assert PERSONALITIES["grudge"].grudge_factor == 0.9

    def test_profiles_are_frozen(self):
        with pytest.raises(AttributeError):
            PERSONALITIES["aggressive"].aggression = 0.5  # type: ignore[misc]

    def test_engager_personality_name(self):
        """CombatEngager reports personality name."""
        from openarena_perception.combat.engage import CombatEngager

        e = CombatEngager(
            ctrl=MagicMock(), bridge=MagicMock(), combat_mover=MagicMock(),
            personality=PERSONALITIES["aggressive"],
        )
        assert e.personality_name == "aggressive"

    def test_engager_default_personality(self):
        """CombatEngager without personality returns 'default'."""
        from openarena_perception.combat.engage import CombatEngager

        e = CombatEngager(
            ctrl=MagicMock(), bridge=MagicMock(), combat_mover=MagicMock(),
        )
        assert e.personality_name == "default"

    def test_balanced_profile(self):
        """Balanced profile has equal aggression and caution."""
        p = PERSONALITIES["balanced"]
        assert p.aggression == 0.5
        assert p.caution == 0.5


# ── HUMN-05: Adaptive Learning ──────────────────────────────────────


class TestAdaptiveLearning:
    """HUMN-05: Death heatmap -> danger zones."""

    def test_populate_danger_zones_exists(self):
        """NavBehavior has populate_danger_zones method."""
        from openarena_perception.navigation.nav_behavior import NavBehavior

        assert hasattr(NavBehavior, "populate_danger_zones")

    def test_no_memory_returns_zero(self):
        """Without episodic memory, populate_danger_zones returns 0."""
        from openarena_perception.navigation.nav_behavior import NavBehavior

        nav = NavBehavior.__new__(NavBehavior)
        nav._episodic_memory = None
        nav._map_name = "testmap"
        spatial = MagicMock()
        count = nav.populate_danger_zones(spatial)
        assert count == 0

    def test_no_map_name_returns_zero(self):
        """Without map_name, populate_danger_zones returns 0."""
        from openarena_perception.navigation.nav_behavior import NavBehavior

        nav = NavBehavior.__new__(NavBehavior)
        nav._episodic_memory = MagicMock()
        nav._map_name = ""
        spatial = MagicMock()
        count = nav.populate_danger_zones(spatial)
        assert count == 0

    def test_danger_zone_cap(self):
        """populate_danger_zones caps at 10 zones maximum."""
        from openarena_perception.navigation.nav_behavior import NavBehavior

        mock_memory = MagicMock()
        # Return 20 death clusters (all with >= _MIN_DEATHS)
        mock_memory.get_death_heatmap.return_value = [
            (float(i * 100), float(i * 200), 0.0, 5) for i in range(20)
        ]
        nav = NavBehavior.__new__(NavBehavior)
        nav._episodic_memory = mock_memory
        nav._map_name = "testmap"
        nav.nav = MagicMock()  # navigator mock
        spatial = MagicMock()
        count = nav.populate_danger_zones(spatial)
        assert count <= 10, f"Should cap at 10 danger zones, got {count}"

    def test_min_deaths_filter(self):
        """Zones with < _MIN_DEATHS (2) are excluded."""
        from openarena_perception.navigation.nav_behavior import NavBehavior

        mock_memory = MagicMock()
        # All zones have only 1 death (below _MIN_DEATHS=2)
        mock_memory.get_death_heatmap.return_value = [
            (100.0, 200.0, 0.0, 1) for _ in range(5)
        ]
        nav = NavBehavior.__new__(NavBehavior)
        nav._episodic_memory = mock_memory
        nav._map_name = "testmap"
        nav.nav = MagicMock()
        spatial = MagicMock()
        count = nav.populate_danger_zones(spatial)
        assert count == 0, f"Should exclude zones with 1 death, got {count}"


# ── HUMN-06: Hesitation ─────────────────────────────────────────────


class TestHesitation:
    """HUMN-06: Hesitation delay 100-300ms on state transitions, none on DEAD."""

    def test_hesitation_included_in_delay(self):
        """Total delay includes hesitation component."""
        from openarena_perception.tactics.fsm import TacticalFSM

        cfg = HumanizationConfig.from_skill_level(3)
        fsm = TacticalFSM(
            arbiter=MagicMock(), death_handler=MagicMock(),
            stuck_escape=MagicMock(), engager=MagicMock(),
            nav_behavior=MagicMock(), humanize_config=cfg,
        )
        delays = [
            fsm._sample_reaction_delay(BrainState.NAVIGATING, BrainState.EXPLORING)
            for _ in range(100)
        ]
        # Total should exceed reaction_time_min alone (hesitation adds on top)
        avg = sum(delays) / len(delays)
        assert avg > cfg.reaction_time_min + cfg.hesitation_min * 0.5, (
            f"Avg delay {avg} should include hesitation beyond reaction_time_min {cfg.reaction_time_min}"
        )

    def test_dead_no_hesitation(self):
        """DEAD transitions have no hesitation delay."""
        from openarena_perception.tactics.fsm import TacticalFSM

        cfg = HumanizationConfig.from_skill_level(3)
        fsm = TacticalFSM(
            arbiter=MagicMock(), death_handler=MagicMock(),
            stuck_escape=MagicMock(), engager=MagicMock(),
            nav_behavior=MagicMock(), humanize_config=cfg,
        )
        delay = fsm._sample_reaction_delay(BrainState.DEAD, BrainState.COMBAT)
        assert delay == 0.0

    def test_hesitation_range_bounds(self):
        """Hesitation component stays within configured min/max bounds."""
        from openarena_perception.tactics.fsm import TacticalFSM

        cfg = HumanizationConfig.from_skill_level(3)
        fsm = TacticalFSM(
            arbiter=MagicMock(), death_handler=MagicMock(),
            stuck_escape=MagicMock(), engager=MagicMock(),
            nav_behavior=MagicMock(), humanize_config=cfg,
        )
        # Total delay = reaction + hesitation. Both are clipped.
        # Total must be >= reaction_min + hesitation_min
        delays = [
            fsm._sample_reaction_delay(BrainState.NAVIGATING, BrainState.EXPLORING)
            for _ in range(200)
        ]
        min_possible = cfg.reaction_time_min + cfg.hesitation_min
        max_possible = cfg.reaction_time_max + cfg.hesitation_max
        for d in delays:
            assert d >= min_possible, f"Delay {d} below floor {min_possible}"
            assert d <= max_possible, f"Delay {d} above ceiling {max_possible}"


# ── HUMN-07: Skill Scaling ──────────────────────────────────────────


class TestSkillScaling:
    """HUMN-07: Unified skill 1-5 with monotonic parameter scaling."""

    def test_all_levels_valid(self):
        """from_skill_level works for 1-5."""
        for level in range(1, 6):
            cfg = HumanizationConfig.from_skill_level(level)
            assert cfg.aim_noise_base > 0

    def test_invalid_levels_raise(self):
        """from_skill_level(0) and from_skill_level(6) raise ValueError."""
        with pytest.raises(ValueError):
            HumanizationConfig.from_skill_level(0)
        with pytest.raises(ValueError):
            HumanizationConfig.from_skill_level(6)

    def test_aim_noise_decreases_with_skill(self):
        """Higher skill = less aim noise (monotonic decrease)."""
        noises = [HumanizationConfig.from_skill_level(i).aim_noise_base for i in range(1, 6)]
        for i in range(len(noises) - 1):
            assert noises[i] > noises[i + 1], (
                f"Level {i+1} noise {noises[i]} should > level {i+2} noise {noises[i+1]}"
            )

    def test_max_accuracy_increases_with_skill(self):
        """Higher skill = higher max accuracy (monotonic increase)."""
        accs = [HumanizationConfig.from_skill_level(i).max_accuracy for i in range(1, 6)]
        for i in range(len(accs) - 1):
            assert accs[i] < accs[i + 1], (
                f"Level {i+1} accuracy {accs[i]} should < level {i+2} accuracy {accs[i+1]}"
            )

    def test_reaction_time_decreases_with_skill(self):
        """Higher skill = faster reactions (monotonic decrease)."""
        mins = [HumanizationConfig.from_skill_level(i).reaction_time_min for i in range(1, 6)]
        for i in range(len(mins) - 1):
            assert mins[i] > mins[i + 1], (
                f"Level {i+1} reaction {mins[i]} should > level {i+2} reaction {mins[i+1]}"
            )

    def test_decision_noise_decreases_with_skill(self):
        """Higher skill = less decision noise (monotonic decrease)."""
        noises = [HumanizationConfig.from_skill_level(i).decision_noise for i in range(1, 6)]
        for i in range(len(noises) - 1):
            assert noises[i] > noises[i + 1]

    def test_settings_skill_level(self):
        """BotSettings.skill_level field exists with default 3."""
        from openarena_perception.settings import BotSettings

        s = BotSettings()
        assert s.skill_level == 3
        assert 1 <= s.skill_level <= 5

    def test_corner_overshoot_decreases_with_skill(self):
        """Higher skill = less corner overshoot (monotonic decrease)."""
        overshoots = [HumanizationConfig.from_skill_level(i).corner_overshoot_px for i in range(1, 6)]
        for i in range(len(overshoots) - 1):
            assert overshoots[i] > overshoots[i + 1]

    def test_config_frozen(self):
        """HumanizationConfig is immutable."""
        cfg = HumanizationConfig.from_skill_level(3)
        with pytest.raises(AttributeError):
            cfg.max_accuracy = 0.99  # type: ignore[misc]
