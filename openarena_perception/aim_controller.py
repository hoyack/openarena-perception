"""DEPRECATED: Use openarena_perception.combat.aim_controller instead."""
from openarena_perception.combat.aim_controller import (
    AimController,
    AimProfile,
    PROFILES,
    PIDState,
    TargetTrack,
    WEAPON_PROFILE_MAP,
)

__all__ = ["AimController", "AimProfile", "PROFILES",
           "PIDState", "TargetTrack", "WEAPON_PROFILE_MAP"]
