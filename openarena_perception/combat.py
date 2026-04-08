"""DEPRECATED: Use openarena_perception.combat package instead."""
from openarena_perception.combat.weapons import WEAPONS, WeaponInfo
from openarena_perception.combat.weapon_select import select_weapon, aim_lead
from openarena_perception.combat.threat_assess import evaluate_threat
from openarena_perception.combat.combat_movement import CombatMover

__all__ = ["WEAPONS", "WeaponInfo", "select_weapon", "aim_lead",
           "evaluate_threat", "CombatMover"]
