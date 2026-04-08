"""Threat assessment for fight-or-flight decisions (CMBT-05, CMBT-07).

evaluate_threat() moved from root-level combat.py in Phase 4.
ThreatAssessor wraps it with stateful disengage logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .weapons import WEAPONS

if TYPE_CHECKING:
    from openarena_perception.models import SituationalAwareness


def evaluate_threat(
    my_health: int,
    my_armor: int,
    my_weapon: Optional[str],
    enemy_count: int,
    enemy_distance: float,
) -> str:
    """
    Evaluate whether to fight, retreat, or be cautious.
    Returns: "FIGHT", "RETREAT", or "CAUTIOUS"
    """
    effective_hp = my_health + my_armor * 0.66  # armor absorbs ~66%

    # Immediate danger -- retreat
    if effective_hp < 30:
        return "RETREAT"

    # Low health with no good weapon -- retreat
    has_power_weapon = my_weapon in ("rocket", "lightning", "railgun", "plasma")
    if effective_hp < 50 and not has_power_weapon:
        return "RETREAT"

    # Outnumbered -- be cautious
    if enemy_count > 1 and effective_hp < 80:
        return "RETREAT"

    # Strong position -- fight
    if effective_hp > 80 and has_power_weapon:
        return "FIGHT"

    # Default -- cautious approach
    if effective_hp > 50:
        return "FIGHT"

    return "CAUTIOUS"


class ThreatAssessor:
    """Stateful threat assessment with disengage logic (CMBT-05, CMBT-07).

    Wraps evaluate_threat() and adds should_disengage() for combat exit decisions.
    """

    def evaluate(
        self,
        own_health: int,
        own_armor: int,
        own_weapon: Optional[str],
        enemy_count: int,
        enemy_distance: float,
    ) -> dict:
        """Evaluate the current threat level.

        Returns a dict with:
          - verdict: "FIGHT", "RETREAT", or "CAUTIOUS"
          - effective_hp: combined health + armor value
          - has_power_weapon: whether current weapon is strong
        """
        effective_hp = own_health + own_armor * 0.66
        has_power_weapon = own_weapon in ("rocket", "lightning", "railgun", "plasma")
        verdict = evaluate_threat(own_health, own_armor, own_weapon,
                                  enemy_count, enemy_distance)
        return {
            "verdict": verdict,
            "effective_hp": effective_hp,
            "has_power_weapon": has_power_weapon,
        }

    def should_disengage(self, sa: SituationalAwareness) -> bool:
        """Determine if the bot should disengage from combat (CMBT-05).

        Returns True if:
          - health < 25 (critical, must flee)
          - health < 50 AND weapon is gauntlet/machinegun AND enemy close (< 200 units)
            (weak weapon at close range with low health = death trap)
        """
        health = sa.health if sa.health is not None else 100

        # Critical health -- always disengage
        if health < 25:
            return True

        # Low health with weak weapon at close range
        if health < 50:
            weapon = (sa.weapon or "").lower()
            if weapon in ("gauntlet", "machinegun"):
                # Parse nearest_enemy_distance (stored as string category or None)
                enemy_dist = _parse_enemy_distance(sa.nearest_enemy_distance)
                if enemy_dist is not None and enemy_dist < 200:
                    return True

        return False


def _parse_enemy_distance(dist_str: Optional[str]) -> Optional[float]:
    """Parse the nearest_enemy_distance field from SituationalAwareness.

    The field may be a string like "close", "medium", "far" or a numeric string.
    Returns estimated distance in game units, or None if unparseable.
    """
    if dist_str is None:
        return None

    # Try numeric first
    try:
        return float(dist_str)
    except (ValueError, TypeError):
        pass

    # Map category strings to approximate distances
    dist_map = {
        "close": 150.0,
        "medium": 400.0,
        "far": 800.0,
        "very_far": 1200.0,
    }
    return dist_map.get(dist_str.lower())
