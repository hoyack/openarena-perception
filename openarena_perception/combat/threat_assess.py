"""Threat assessment for fight-or-flight decisions.

evaluate_threat() moved from root-level combat.py in Phase 4.
ThreatAssessor class will be added in Task 2.
"""

from __future__ import annotations

from typing import Optional

from .weapons import WEAPONS


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
