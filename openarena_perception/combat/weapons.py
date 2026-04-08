"""Weapon database -- data definitions for all Q3/OA weapons.

Extracted from root-level combat.py in Phase 4.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WeaponInfo:
    name: str
    slot: int
    damage: float          # damage per hit
    fire_rate: float       # seconds between shots
    speed: float           # projectile speed (0 = hitscan)
    splash_radius: float   # splash damage radius (0 = none)
    optimal_range: float   # best engagement distance
    max_range: float       # effective range


WEAPONS = {
    "gauntlet":    WeaponInfo("Gauntlet",    1, 50,  0.4,   0,   0,   50,   50),
    "machinegun":  WeaponInfo("Machinegun",  2, 7,   0.1,   0,   0,  400,  800),
    "shotgun":     WeaponInfo("Shotgun",     3, 110, 1.0,   0,   0,  200,  400),
    "grenade":     WeaponInfo("Grenade",     4, 100, 0.8, 700, 150,  300,  500),
    "rocket":      WeaponInfo("Rocket",      5, 100, 0.8, 900, 120,  400,  800),
    "lightning":   WeaponInfo("Lightning",   6, 8,   0.05,  0,   0,  400,  768),
    "railgun":     WeaponInfo("Railgun",     7, 80,  1.5,   0,   0,  800, 2000),
    "plasma":      WeaponInfo("Plasma",      8, 20,  0.1, 2000,  0,  500, 1000),
    "bfg":         WeaponInfo("BFG",         9, 100, 0.2, 2000, 100, 500, 1000),
}
