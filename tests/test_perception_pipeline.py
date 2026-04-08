"""Comprehensive tests for the PerceptionPipeline.

Covers all PERC requirements (PERC-01 through PERC-07), backward
compatibility of re-export stubs, pipeline rate-limiting, attention-based
priority, and death-reset behavior.
"""
from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from openarena_perception.models import SituationalAwareness
from openarena_perception.perception.config import PerceptionPipelineConfig
from openarena_perception.perception.pipeline import (
    PerceptionPipeline,
    build_situational_awareness,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _synthetic_frame() -> np.ndarray:
    """Return a small synthetic BGR frame (avoids OpenCV on real images)."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


def _make_enemy(distance_estimate: str = "near"):
    """Return a mock enemy object with the minimal interface."""
    enemy = SimpleNamespace(
        distance_estimate=distance_estimate,
        bbox=SimpleNamespace(x=100, y=100, w=40, h=80),
        pixel_mass=5000,
        screen_angle=10.0,
        confidence=0.9,
    )
    return enemy


def _make_tracked_object(track_id: int = 1, locked: bool = False):
    """Return a mock TrackedObject with the minimal interface."""
    return SimpleNamespace(track_id=track_id, locked=locked, frames_lost=0)


def _make_pipeline(**cfg_overrides) -> PerceptionPipeline:
    """Build a PerceptionPipeline with every sub-module mocked out.

    Patches constructors so the pipeline's __init__ gets mocks instead
    of real detector objects.
    """
    cfg = PerceptionPipelineConfig(**cfg_overrides)

    # Mock all constructors
    with (
        patch("openarena_perception.perception.pipeline.make_capture") as mk_cap,
        patch("openarena_perception.perception.pipeline.HUDParser") as mk_hud,
        patch("openarena_perception.perception.pipeline.WorldParser") as mk_world,
        patch("openarena_perception.perception.pipeline.Perception") as mk_wall,
        patch("openarena_perception.perception.pipeline.MotionDetector") as mk_motion,
        patch("openarena_perception.perception.pipeline.PlayerDetector") as mk_player,
        patch("openarena_perception.perception.pipeline.ObjectTracker") as mk_tracker,
        patch("openarena_perception.perception.pipeline.DamageTracker") as mk_damage,
        patch("openarena_perception.perception.pipeline.MotionAnomalyTracker") as mk_anomaly,
        patch("openarena_perception.perception.pipeline.build_config"),
    ):
        # Set up capture mock
        capture_inst = MagicMock()
        capture_inst.grab.return_value = _synthetic_frame()
        mk_cap.return_value = capture_inst

        # HUD mock -- returns empty dict by default (rate-limited, may not run)
        hud_inst = MagicMock()
        hud_inst.parse_all.return_value = {
            "health": 100, "armor": 50, "ammo": 30,
            "weapon": "machinegun", "frags": 5, "deaths": 1,
        }
        mk_hud.return_value = hud_inst

        # World mock -- no enemies by default
        world_inst = MagicMock()
        world_inst.parse_enemies.return_value = []
        mk_world.return_value = world_inst

        # Wall mock
        wall_inst = MagicMock()
        wall_inst.detect_wall_ahead.return_value = (False, 0.2, 0)
        mk_wall.return_value = wall_inst

        # Motion mock
        motion_inst = MagicMock()
        motion_inst.detect.return_value = []
        mk_motion.return_value = motion_inst

        # Player mock
        player_inst = MagicMock()
        mk_player.return_value = player_inst

        # Tracker mock
        tracker_inst = MagicMock()
        tracker_inst.update.return_value = []
        mk_tracker.return_value = tracker_inst

        # Damage mock
        damage_inst = MagicMock()
        damage_inst.update.return_value = False
        damage_inst.attacker_direction = 0
        damage_inst.seconds_since_damage = float("inf")
        mk_damage.return_value = damage_inst

        # Anomaly mock
        anomaly_inst = MagicMock()
        anomaly_inst.update.return_value = []
        mk_anomaly.return_value = anomaly_inst

        pipeline = PerceptionPipeline(pipeline_cfg=cfg)

    return pipeline


# ---------------------------------------------------------------------------
# PERC-01: Pipeline produces SituationalAwareness at 15+ FPS
# ---------------------------------------------------------------------------

class TestPERC01_PipelineProducesSA:
    """PERC-01: Pipeline produces SituationalAwareness."""

    def test_pipeline_produces_awareness(self):
        """tick() returns a SituationalAwareness instance."""
        pipe = _make_pipeline()
        sa = pipe.tick()
        assert isinstance(sa, SituationalAwareness)

    def test_awareness_is_frozen(self):
        """The returned SA is immutable (frozen dataclass)."""
        pipe = _make_pipeline()
        sa = pipe.tick()
        with pytest.raises(dataclasses.FrozenInstanceError):
            sa.health = 999  # type: ignore[misc]

    def test_tick_counter_increments(self):
        """Each tick() increments the internal counter."""
        pipe = _make_pipeline()
        pipe.tick()
        pipe.tick()
        pipe.tick()
        assert pipe.tick_count == 3


# ---------------------------------------------------------------------------
# PERC-02: Enemy detection with bounding boxes from HSV thresholding
# ---------------------------------------------------------------------------

class TestPERC02_EnemyDetection:
    """PERC-02: Enemy detection returns bounding boxes from HSV thresholding."""

    def test_enemy_detection(self):
        """When WorldParser.parse_enemies returns enemies, SA reflects them."""
        pipe = _make_pipeline()
        enemy = _make_enemy(distance_estimate="near")
        pipe._world.parse_enemies.return_value = [enemy]

        sa = pipe.tick()
        assert sa.enemies_visible == 1
        assert sa.nearest_enemy_distance == "near"

    def test_no_enemies(self):
        """When no enemies are detected, SA shows zero."""
        pipe = _make_pipeline()
        sa = pipe.tick()
        assert sa.enemies_visible == 0
        assert sa.nearest_enemy_distance is None


# ---------------------------------------------------------------------------
# PERC-03: HUD parsing extracts health, armor, ammo, weapon, frags, deaths
# ---------------------------------------------------------------------------

class TestPERC03_HUDParsing:
    """PERC-03: HUD parser extracts health, armor, ammo, weapon, frags, deaths."""

    def test_hud_parsing(self):
        """On the HUD OCR interval tick, SA fields are populated from HUD."""
        pipe = _make_pipeline(hud_ocr_interval=1)  # OCR every tick for testing
        pipe._hud.parse_all.return_value = {
            "health": 80, "armor": 50, "ammo": 25,
            "weapon": "railgun", "frags": 3, "deaths": 1,
        }

        sa = pipe.tick()
        assert sa.health == 80
        assert sa.armor == 50
        assert sa.ammo == 25
        assert sa.weapon == "railgun"


# ---------------------------------------------------------------------------
# PERC-04: Damage direction from screen flash analysis
# ---------------------------------------------------------------------------

class TestPERC04_DamageDirection:
    """PERC-04: Damage direction is detected from screen flash analysis."""

    def test_damage_direction(self):
        """When DamageTracker reports under_attack, SA reflects it."""
        pipe = _make_pipeline(hud_ocr_interval=1)
        pipe._damage.update.return_value = True
        pipe._damage.attacker_direction = 1
        pipe._damage.seconds_since_damage = 0.5

        sa = pipe.tick()
        assert sa.under_attack is True
        assert sa.attacker_direction == 1
        assert sa.seconds_since_damage == 0.5


# ---------------------------------------------------------------------------
# PERC-05: Distance estimation from bounding box size
# ---------------------------------------------------------------------------

class TestPERC05_DistanceEstimation:
    """PERC-05: Distance estimation works from bounding box size."""

    def test_distance_estimation_far(self):
        """SA.nearest_enemy_distance reflects WorldParser enemy distance."""
        pipe = _make_pipeline()
        enemy = _make_enemy(distance_estimate="far")
        pipe._world.parse_enemies.return_value = [enemy]

        sa = pipe.tick()
        assert sa.nearest_enemy_distance == "far"

    def test_distance_estimation_mid(self):
        pipe = _make_pipeline()
        enemy = _make_enemy(distance_estimate="mid")
        pipe._world.parse_enemies.return_value = [enemy]

        sa = pipe.tick()
        assert sa.nearest_enemy_distance == "mid"


# ---------------------------------------------------------------------------
# PERC-06: Multi-target tracking with persistent IDs
# ---------------------------------------------------------------------------

class TestPERC06_PersistentTracking:
    """PERC-06: Multi-target tracking maintains persistent IDs across frames."""

    def test_persistent_tracking_ids(self):
        """When ObjectTracker returns tracked objects, SA count is correct."""
        pipe = _make_pipeline(tracker_interval=1)
        tracked = [
            _make_tracked_object(track_id=1),
            _make_tracked_object(track_id=2),
            _make_tracked_object(track_id=3),
        ]
        pipe._tracker.update.return_value = tracked

        sa = pipe.tick()
        assert sa.tracked_objects == 3


# ---------------------------------------------------------------------------
# PERC-07: Motion detection via frame differencing
# ---------------------------------------------------------------------------

class TestPERC07_MotionDetection:
    """PERC-07: Motion detection finds moving regions via frame differencing."""

    def test_motion_detection(self):
        """MotionDetector.detect is called on ticks divisible by motion_interval."""
        pipe = _make_pipeline(motion_interval=2)

        # Tick 1: not divisible by 2 -> no motion call
        pipe._motion.detect.reset_mock()
        pipe.tick()
        pipe._motion.detect.assert_not_called()

        # Tick 2: divisible by 2 -> motion called
        pipe._motion.detect.reset_mock()
        pipe.tick()
        pipe._motion.detect.assert_called_once()


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    """HUD OCR and tracker are rate-limited by their interval config."""

    def test_hud_rate_limiting(self):
        """HUDParser.parse_all is called only every 30 ticks."""
        pipe = _make_pipeline(hud_ocr_interval=30)

        for _ in range(60):
            pipe.tick()

        assert pipe._hud.parse_all.call_count == 2

    def test_tracker_rate_limiting(self):
        """ObjectTracker.update is called every 2 ticks normally (no combat)."""
        pipe = _make_pipeline(tracker_interval=2)
        # Ensure no enemies so in_combat is False
        pipe._world.parse_enemies.return_value = []
        pipe._damage.update.return_value = False

        for _ in range(10):
            pipe.tick()

        assert pipe._tracker.update.call_count == 5


# ---------------------------------------------------------------------------
# Attention-based priority
# ---------------------------------------------------------------------------

class TestAttentionPriority:
    """During combat, tracker runs every tick instead of every 2."""

    def test_combat_attention_priority(self):
        """When enemies are visible, ObjectTracker runs every tick."""
        pipe = _make_pipeline(tracker_interval=2, combat_tracker_interval=1)
        enemy = _make_enemy()
        pipe._world.parse_enemies.return_value = [enemy]

        for _ in range(10):
            pipe.tick()

        # In combat: tracker runs every tick (combat_tracker_interval=1)
        assert pipe._tracker.update.call_count == 10


# ---------------------------------------------------------------------------
# Death reset
# ---------------------------------------------------------------------------

class TestDeathReset:
    """When health=0, stateful trackers are reset."""

    def test_death_resets_trackers(self):
        """ObjectTracker.reset() and MotionAnomalyTracker.reset() called on death."""
        pipe = _make_pipeline(hud_ocr_interval=1, reset_on_death=True)

        # First tick: alive with health=100
        pipe._hud.parse_all.return_value = {
            "health": 100, "armor": 50, "ammo": 30,
            "weapon": "machinegun", "frags": 0, "deaths": 0,
        }
        pipe.tick()

        # Second tick: dead with health=0
        pipe._hud.parse_all.return_value = {
            "health": 0, "armor": 0, "ammo": 0,
            "weapon": None, "frags": 0, "deaths": 1,
        }
        pipe.tick()

        pipe._tracker.reset.assert_called()
        pipe._anomaly.reset.assert_called()


# ---------------------------------------------------------------------------
# Backward compatibility imports
# ---------------------------------------------------------------------------

class TestBackwardCompatImports:
    """All old import paths (from openarena_perception.X) still work."""

    def test_backward_compat_imports(self):
        """Import from all 9 old locations and verify the classes match."""
        # capture
        from openarena_perception.capture import ScreenCapture as OldCapture
        from openarena_perception.perception.capture import ScreenCapture as NewCapture
        assert OldCapture is NewCapture

        # hud_parser
        from openarena_perception.hud_parser import HUDParser as OldHUD
        from openarena_perception.perception.hud_parser import HUDParser as NewHUD
        assert OldHUD is NewHUD

        # world_parser
        from openarena_perception.world_parser import WorldParser as OldWorld
        from openarena_perception.perception.world_parser import WorldParser as NewWorld
        assert OldWorld is NewWorld

        # perception (wall_detector) -- old module was perception.py, now
        # openarena_perception.perception is a package that re-exports Perception
        from openarena_perception.perception import Perception as OldPerc
        from openarena_perception.perception.wall_detector import Perception as NewPerc
        assert OldPerc is NewPerc

        # damage_tracker
        from openarena_perception.damage_tracker import DamageTracker as OldDmg
        from openarena_perception.perception.damage_tracker import DamageTracker as NewDmg
        assert OldDmg is NewDmg

        # motion_detector
        from openarena_perception.motion_detector import MotionDetector as OldMotion
        from openarena_perception.perception.motion_detector import MotionDetector as NewMotion
        assert OldMotion is NewMotion

        # player_detector
        from openarena_perception.player_detector import PlayerDetector as OldPlayer
        from openarena_perception.perception.player_detector import PlayerDetector as NewPlayer
        assert OldPlayer is NewPlayer

        # object_tracker
        from openarena_perception.object_tracker import ObjectTracker as OldTracker
        from openarena_perception.perception.object_tracker import ObjectTracker as NewTracker
        assert OldTracker is NewTracker

        # motion_anomaly
        from openarena_perception.motion_anomaly import MotionAnomalyTracker as OldAnom
        from openarena_perception.perception.motion_anomaly import MotionAnomalyTracker as NewAnom
        assert OldAnom is NewAnom
