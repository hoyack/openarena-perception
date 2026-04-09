"""Combat engagement behavior extracted from strategic_brain._tick_combat.

Handles: target acquisition snap (CMBT-01), forward movement,
combat strafing, fire control, and obstacle avoidance during combat (NAV-05).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openarena_perception.combat.humanize import PersonalityProfile
    from openarena_perception.game_bridge import GameBridge
    from openarena_perception.models import SituationalAwareness
    from openarena_perception.virtual_controller import VirtualController

from .combat_movement import CombatMover

log = logging.getLogger(__name__)

# Absolute minimum HP retreat floor regardless of personality (T-08-07)
_MIN_RETREAT_HP: int = 15


class CombatEngager:
    """Combat engagement behavior extracted from strategic_brain._tick_combat.

    Handles: target acquisition snap (CMBT-01), forward movement,
    combat strafing, fire control, and personality-aware engagement.
    """

    def __init__(
        self,
        ctrl: VirtualController,
        bridge: GameBridge,
        combat_mover: CombatMover,
        personality: "PersonalityProfile | None" = None,
    ):
        self.ctrl = ctrl
        self.bridge = bridge
        self.combat_mover = combat_mover
        self._personality = personality

    @property
    def personality_name(self) -> str:
        """Return personality name if set, else 'default'."""
        if self._personality is not None:
            return self._personality.name
        return "default"

    def on_enter(self, sa: SituationalAwareness) -> None:
        """Start firing on combat entry."""
        self.bridge.fire(True)

    def on_exit(self, sa: SituationalAwareness) -> None:
        """Stop firing and strafing on combat exit."""
        self.bridge.fire(False)
        self.ctrl.strafe_left(False)
        self.ctrl.strafe_right(False)

    async def tick(self, sa: SituationalAwareness, gs) -> None:
        """Execute one combat tick.

        Handles CMBT-01 target acquisition snap, NAV-05 obstacle avoidance,
        and personality-aware engagement modifiers.
        """
        p = self._personality

        # ── Cautious disengage at low health ──────────────────────────
        # Cautious bots stop firing and back off when health is critical.
        # Minimum retreat threshold of 15 HP is absolute (T-08-07).
        if p is not None and p.caution > 0.7:
            if sa.health is not None and sa.health < max(30, _MIN_RETREAT_HP):
                self.bridge.fire(False)
                log.debug(
                    "Cautious disengage: health=%s < 30, personality=%s",
                    sa.health, p.name,
                )
                return

        # ── Grudge logging ────────────────────────────────────────────
        # Actual grudge target tracking deferred to integration plan;
        # for now log the tendency for observability.
        if p is not None and p.grudge_factor > 0.5:
            log.debug("Grudge tendency active: factor=%.1f", p.grudge_factor)

        # Snap aim toward attacker (RFLX-01 damage response, <1ms)
        if sa.attacker_direction != 0 and sa.seconds_since_damage < 0.3:
            self.ctrl.turn_degrees(-sa.attacker_direction * 15)

        # NAV-05: Obstacle avoidance during combat
        # If wall ahead with high confidence, turn toward open space
        # instead of running straight into the wall
        if sa.wall_ahead and sa.wall_score > 0.7:
            self.ctrl.forward(False)
            self.ctrl.turn_degrees(sa.open_direction * 30)
        else:
            # Move aggressively
            self.ctrl.forward(True)

        # ── Personality-scaled skill for movement ─────────────────────
        skill = 0.9
        if p is not None and p.aggression > 0.7:
            skill = min(skill + 0.1, 1.0)

        move = self.combat_mover.get_movement(300, 'machinegun', skill)
        self.ctrl.strafe_left(move['strafe_left'])
        self.ctrl.strafe_right(move['strafe_right'])
        if move['jump']:
            self.ctrl.jump()
