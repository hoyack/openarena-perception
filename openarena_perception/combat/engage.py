"""Combat engagement behavior extracted from strategic_brain._tick_combat.

Handles: target acquisition snap (CMBT-01), forward movement,
combat strafing, fire control, and obstacle avoidance during combat (NAV-05).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openarena_perception.game_bridge import GameBridge
    from openarena_perception.models import SituationalAwareness
    from openarena_perception.virtual_controller import VirtualController

from .combat_movement import CombatMover


class CombatEngager:
    """Combat engagement behavior extracted from strategic_brain._tick_combat.

    Handles: target acquisition snap (CMBT-01), forward movement,
    combat strafing, and fire control.
    """

    def __init__(
        self,
        ctrl: VirtualController,
        bridge: GameBridge,
        combat_mover: CombatMover,
    ):
        self.ctrl = ctrl
        self.bridge = bridge
        self.combat_mover = combat_mover

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

        Handles CMBT-01 target acquisition snap and NAV-05 obstacle avoidance.
        """
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

        move = self.combat_mover.get_movement(300, 'machinegun', 0.9)
        self.ctrl.strafe_left(move['strafe_left'])
        self.ctrl.strafe_right(move['strafe_right'])
        if move['jump']:
            self.ctrl.jump()
