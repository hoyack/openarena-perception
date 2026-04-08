"""Perception subsystem -- produces SituationalAwareness snapshots.

All perception modules live here. Re-export stubs at the old package-root
locations maintain backward compatibility for consumers like strategic_brain.py.
"""
from openarena_perception.perception.capture import ScreenCapture, make_capture
from openarena_perception.perception.hud_parser import HUDParser
from openarena_perception.perception.world_parser import WorldParser
from openarena_perception.perception.wall_detector import Perception
from openarena_perception.perception.motion_detector import MotionDetector
from openarena_perception.perception.player_detector import PlayerDetector
from openarena_perception.perception.object_tracker import ObjectTracker, TrackedObject
from openarena_perception.perception.damage_tracker import DamageTracker
from openarena_perception.perception.motion_anomaly import (
    MotionAnomalyTracker, TrackedAnomaly, AnomalyReport,
)
from openarena_perception.perception.pipeline import (
    PerceptionPipeline, build_situational_awareness,
)
from openarena_perception.perception.config import PerceptionPipelineConfig

__all__ = [
    "PerceptionPipeline", "build_situational_awareness", "PerceptionPipelineConfig",
    "ScreenCapture", "make_capture",
    "HUDParser", "WorldParser", "Perception",
    "MotionDetector", "PlayerDetector",
    "ObjectTracker", "TrackedObject",
    "DamageTracker",
    "MotionAnomalyTracker", "TrackedAnomaly", "AnomalyReport",
]
