"""Tactical fight-or-flight evaluator (TACT-03).

Wraps combat.ThreatAssessor to provide FSM-level fight/retreat/cautious
decisions. Does NOT duplicate logic -- delegates to the existing implementation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from openarena_perception.combat.threat_assess import ThreatAssessor

if TYPE_CHECKING:
    from openarena_perception.models import SituationalAwareness


class FightOrFlight:
    """Tactical fight-or-flight decision point for the FSM layer.

    Wraps combat.ThreatAssessor and translates its output into
    FSM-consumable decisions.
    """

    def __init__(self) -> None:
        self._assessor = ThreatAssessor()

    def evaluate(self, sa: SituationalAwareness) -> str:
        """Evaluate whether to fight, retreat, or be cautious.

        Returns: "FIGHT", "RETREAT", or "CAUTIOUS"
        """
        health = sa.health if sa.health is not None else 100
        armor = sa.armor if sa.armor is not None else 0
        weapon = sa.weapon
        enemy_count = sa.enemies_visible
        enemy_distance = self._parse_distance(sa.nearest_enemy_distance)

        result = self._assessor.evaluate(
            own_health=health,
            own_armor=armor,
            own_weapon=weapon,
            enemy_count=enemy_count,
            enemy_distance=enemy_distance,
        )
        return result["verdict"]

    def should_disengage(self, sa: SituationalAwareness) -> bool:
        """Determine if the bot should disengage from current combat."""
        return self._assessor.should_disengage(sa)

    @staticmethod
    def _parse_distance(dist) -> float:
        """Parse nearest_enemy_distance to a float for ThreatAssessor."""
        if dist is None:
            return 999.0
        try:
            return float(dist)
        except (ValueError, TypeError):
            pass
        dist_map = {"close": 150.0, "medium": 400.0, "far": 800.0, "very_far": 1200.0}
        return dist_map.get(str(dist).lower(), 999.0)
