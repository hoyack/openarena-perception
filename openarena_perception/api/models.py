"""Pydantic v2 request/response models for the bot REST API."""
from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict

from openarena_perception.skills.base import SkillResult

# ── Perception ────────────────────────────────────────────────────────


class PerceptionStateResponse(BaseModel):
    """Full SituationalAwareness snapshot as a Pydantic model."""

    model_config = ConfigDict(from_attributes=True)

    tick: int
    timestamp: float
    pos: tuple[float, float, float] | None
    yaw: float
    current_area: int
    health: int | None
    armor: int | None
    ammo: int | None
    weapon: str | None
    is_alive: bool
    disposition: str
    armament: str
    orientation: str
    under_attack: bool
    attacker_direction: int
    seconds_since_damage: float
    enemies_visible: int
    nearest_enemy_distance: str | None
    wall_ahead: bool
    wall_score: float
    open_direction: int
    in_water: bool
    tracked_objects: int
    locked_target: bool
    anomaly_count: int
    lockable_anomaly: bool
    room_surveyed: bool
    room_type: str
    room_exits: int
    has_path: bool
    path_length: int
    is_stuck: bool
    is_recovering: bool
    nav_target: str | None
    has_frame: bool

    @classmethod
    def from_sa(cls, sa: Any) -> Self:
        """Build from a SituationalAwareness dataclass (avoids slow asdict)."""
        return cls(
            tick=sa.tick,
            timestamp=sa.timestamp,
            pos=sa.pos,
            yaw=sa.yaw,
            current_area=sa.current_area,
            health=sa.health,
            armor=sa.armor,
            ammo=sa.ammo,
            weapon=sa.weapon,
            is_alive=sa.is_alive,
            disposition=sa.disposition,
            armament=sa.armament,
            orientation=sa.orientation,
            under_attack=sa.under_attack,
            attacker_direction=sa.attacker_direction,
            seconds_since_damage=sa.seconds_since_damage,
            enemies_visible=sa.enemies_visible,
            nearest_enemy_distance=sa.nearest_enemy_distance,
            wall_ahead=sa.wall_ahead,
            wall_score=sa.wall_score,
            open_direction=sa.open_direction,
            in_water=sa.in_water,
            tracked_objects=sa.tracked_objects,
            locked_target=sa.locked_target,
            anomaly_count=sa.anomaly_count,
            lockable_anomaly=sa.lockable_anomaly,
            room_surveyed=sa.room_surveyed,
            room_type=sa.room_type,
            room_exits=sa.room_exits,
            has_path=sa.has_path,
            path_length=sa.path_length,
            is_stuck=sa.is_stuck,
            is_recovering=sa.is_recovering,
            nav_target=sa.nav_target,
            has_frame=sa.has_frame,
        )


class HudResponse(BaseModel):
    """HUD vitals subset."""

    health: int | None = None
    armor: int | None = None
    ammo: int | None = None
    weapon: str | None = None


class EnemyInfo(BaseModel):
    """Enemy threat summary."""

    enemies_visible: int
    nearest_enemy_distance: str | None = None
    under_attack: bool


# ── Navigation ────────────────────────────────────────────────────────


class NavigationRequest(BaseModel):
    """Request to navigate to an area or named target."""

    area_id: int | None = None
    target: str | None = None


class NavigationStateResponse(BaseModel):
    """Current navigation state."""

    has_path: bool
    path_length: int
    is_stuck: bool
    nav_target: str | None = None


# ── Combat ────────────────────────────────────────────────────────────


class CombatStateResponse(BaseModel):
    """Current combat state."""

    in_combat: bool
    weapon: str | None = None
    ammo: int | None = None


# ── Skills ────────────────────────────────────────────────────────────


class SkillExecuteRequest(BaseModel):
    """Request to execute a skill by name."""

    name: str
    params: dict[str, Any] = {}


class SkillExecuteResponse(SkillResult):
    """Response from skill execution (inherits success, message, data)."""

    pass


class SkillCatalogEntry(BaseModel):
    """Single skill in the catalog."""

    name: str
    layer: str
    description: str


# ── Strategy ──────────────────────────────────────────────────────────


class StrategyStateResponse(BaseModel):
    """Current strategy/FSM state."""

    current_action: str
    brain_state: str


class StrategyOverrideRequest(BaseModel):
    """Override the current strategy action."""

    action: str


# ── System ────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    """API health check response."""

    status: str = "ok"
    version: str = "0.1.0"


class BotFullStateResponse(BaseModel):
    """Full bot state combining FSM + perception."""

    brain_state: str
    perception: PerceptionStateResponse | None = None
    score: dict | None = None
