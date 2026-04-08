"""Weapon selection and aim lead prediction.

Fuzzy weapon selection (van Waveren thesis Section 9) and projectile
aim lead calculation. Extracted from root-level combat.py in Phase 4.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from .weapons import WEAPONS, WeaponInfo


# ── Fuzzy weapon selection (thesis Section 9) ──────────────────────────

def select_weapon(distance: float, inventory: dict) -> Optional[str]:
    """
    Fuzzy weapon selection based on distance and ammo.
    Returns weapon name or None.

    inventory: {"rocket": ammo_count, "lightning": ammo_count, ...}
    """
    best_name = None
    best_weight = 0.0

    for name, info in WEAPONS.items():
        ammo = inventory.get(name, 0)
        if ammo <= 0 and name != "gauntlet":
            continue

        # Range match: peaks at optimal_range, falls off outside
        if distance <= info.max_range:
            range_match = max(0, 1.0 - abs(distance - info.optimal_range) / info.max_range)
        else:
            range_match = 0.0

        # Ammo comfort: more ammo = more willing to use
        if name == "gauntlet":
            ammo_weight = 0.3  # always available but weak
        else:
            ammo_weight = min(1.0, ammo / 50.0) * 0.8 + 0.2

        # Weapon power factor
        power = info.damage / max(info.fire_rate, 0.05)  # DPS
        power_norm = min(1.0, power / 200.0)

        weight = range_match * ammo_weight * power_norm * 80.0

        if weight > best_weight:
            best_weight = weight
            best_name = name

    return best_name


# ── Aim prediction (thesis Section 13.2) ───────────────────────────────

def aim_lead(
    enemy_x: float, enemy_y: float,
    enemy_vx: float, enemy_vy: float,
    player_x: float, player_y: float,
    weapon: str,
) -> Tuple[float, float]:
    """
    Predict where to aim for projectile weapons.
    For hitscan weapons, returns enemy position directly.

    Returns (aim_x, aim_y) in world coordinates.
    """
    info = WEAPONS.get(weapon)
    if not info or info.speed == 0:
        # Hitscan -- aim directly at enemy
        return enemy_x, enemy_y

    # Projectile -- lead the target
    dist = math.hypot(enemy_x - player_x, enemy_y - player_y)
    if dist < 1:
        return enemy_x, enemy_y

    travel_time = dist / info.speed
    aim_x = enemy_x + enemy_vx * travel_time
    aim_y = enemy_y + enemy_vy * travel_time
    return aim_x, aim_y


# ── Preemptive weapon switch (CMBT-06) ─────────────────────────────────

def should_preemptive_switch(
    current_weapon: str,
    current_ammo: int,
    enemy_dist: float,
    inventory: Optional[dict] = None,
) -> Optional[str]:
    """Recommend a weapon switch before running out of ammo.

    Returns the weapon name to switch to, or None if current weapon is fine.

    Logic: if current ammo is critically low (<= 2 rounds), find a better
    weapon that has ammo and is effective at the current engagement distance.
    Uses the WEAPONS dict for range comparison.
    """
    if current_ammo > 2:
        return None  # plenty of ammo, no switch needed

    if current_weapon == "gauntlet":
        # Gauntlet has no ammo -- always look for something better
        pass
    elif current_ammo <= 0:
        # Completely out -- must switch
        pass
    else:
        # 1-2 rounds left -- consider switching
        pass

    # Build candidate list from inventory or assume all weapons available
    candidates = []
    for name, info in WEAPONS.items():
        if name == current_weapon:
            continue
        if name == "gauntlet":
            continue  # gauntlet is last resort

        # Check ammo availability if inventory provided
        if inventory is not None:
            avail = inventory.get(name, 0)
            if avail <= 0:
                continue
        else:
            # No inventory info -- can't verify ammo, skip recommendation
            return None

        # Check if weapon is effective at current distance
        if enemy_dist <= info.max_range:
            range_match = max(0, 1.0 - abs(enemy_dist - info.optimal_range) / info.max_range)
            power = info.damage / max(info.fire_rate, 0.05)
            score = range_match * power
            candidates.append((name, score))

    if not candidates:
        return None

    # Return best scoring candidate
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]
