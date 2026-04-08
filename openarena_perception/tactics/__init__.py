"""OpenArena Perception -- tactics subsystem.

FSM state management, goal selection, and fight-or-flight decisions.
Extracted from strategic_brain.py in Phase 5.
"""
from .commander import Commander, ItemMemory
from .fight_or_flight import FightOrFlight
from .fsm import TacticalFSM

__all__ = ["Commander", "ItemMemory", "FightOrFlight", "TacticalFSM"]
