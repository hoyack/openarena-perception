"""OpenArena Perception -- reflexes subsystem.

Reactive interrupt layer: death handling, stuck escape, subsumption arbitration.
Extracted from strategic_brain.py in Phase 4.
"""
from .arbiter import SubsumptionArbiter
from .death_handler import DeathHandler
from .stuck_escape import StuckEscape

__all__ = ["SubsumptionArbiter", "DeathHandler", "StuckEscape"]
