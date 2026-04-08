"""DeathHandler -- death detection, state reset, and respawn recovery.

Extracted from StrategicBrain._tick_dead(), _on_enter_state(DEAD),
and _on_exit_state() in Phase 4.

Handles the highest-priority reflex: when the bot dies, release all controls,
reset trackers, and tap +attack to respawn.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from openarena_perception.models import SituationalAwareness

if TYPE_CHECKING:
    from openarena_perception.game_bridge import GameBridge
    from openarena_perception.game_state import GameState
    from openarena_perception.motion_anomaly import MotionAnomalyTracker
    from openarena_perception.object_tracker import ObjectTracker
    from openarena_perception.virtual_controller import VirtualController

log = logging.getLogger(__name__)


class DeathHandler:
    """Handles death detection, state reset, and respawn tap.

    On death entry:
      - Increment death counter
      - Release all controls
      - Reset anomaly and object trackers

    On death exit:
      - Release look actions, center view

    Each tick while dead:
      - Detect alive->dead transition
      - Release all movement
      - Tap +attack/-attack for respawn
    """

    def __init__(self, bridge: GameBridge, ctrl: VirtualController) -> None:
        self._bridge = bridge
        self._ctrl = ctrl
        self._deaths: int = 0
        self._was_alive: bool = True

    @property
    def deaths(self) -> int:
        """Total death count this session."""
        return self._deaths

    @property
    def was_alive(self) -> bool:
        """Whether the bot was alive last tick."""
        return self._was_alive

    @was_alive.setter
    def was_alive(self, value: bool) -> None:
        self._was_alive = value

    def on_enter(
        self,
        sa: SituationalAwareness,
        anomaly_tracker: MotionAnomalyTracker,
        obj_tracker: ObjectTracker,
    ) -> None:
        """Called when entering DEAD state.

        Increments death counter, releases all controls, resets trackers.
        """
        self._deaths += 1
        self._ctrl.release_all()
        anomaly_tracker.reset()
        obj_tracker.reset()

    def on_exit(self, sa: SituationalAwareness) -> None:
        """Called when leaving DEAD state.

        Releases look actions and centers view to prevent stuck look angles.
        """
        self._bridge.cmd("-lookup")
        self._bridge.cmd("-lookdown")
        self._bridge.cmd("centerview")

    async def tick(self, sa: SituationalAwareness, gs: GameState) -> None:
        """Execute death behavior for one tick.

        Detects alive->dead transition, releases all movement, and taps
        +attack/-attack to trigger respawn.
        """
        if self._was_alive:
            self._was_alive = False
            log.info("DIED (#%d)", self._deaths)
        self._bridge.release_all()
        self._bridge.cmd("+attack")
        self._bridge.cmd("-attack")
