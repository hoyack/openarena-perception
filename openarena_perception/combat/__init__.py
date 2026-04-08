"""OpenArena Perception -- combat subsystem.

Weapon selection, aim control, combat movement, engagement, and threat assessment.
Extracted and consolidated from root-level modules in Phase 4.
"""
from .weapons import WEAPONS, WeaponInfo
from .weapon_select import select_weapon, aim_lead, should_preemptive_switch
from .aim_controller import AimController, AimProfile, PROFILES
from .combat_movement import CombatMover
from .engage import CombatEngager
from .threat_assess import ThreatAssessor, evaluate_threat

__all__ = [
    "WEAPONS", "WeaponInfo",
    "select_weapon", "aim_lead", "should_preemptive_switch",
    "AimController", "AimProfile", "PROFILES",
    "CombatMover",
    "CombatEngager",
    "ThreatAssessor", "evaluate_threat",
]
