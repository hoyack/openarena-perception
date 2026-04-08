"""
nav_behavior.py — Navigation state behavior handlers.

Extracted from strategic_brain.py: tick_navigating, tick_exploring,
tick_door, tick_pickup, and state entry hooks for EXPLORING/NAVIGATING.

These methods preserve the exact logic from the original FSM but are
decoupled from StrategicBrain, accepting explicit parameters instead
of reading instance state.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Dict, Optional

from .aas_parser import (
    TRAVEL_BARRIERJUMP,
    TRAVEL_JUMP,
    TRAVEL_JUMPPAD,
    TRAVEL_LADDER,
    TRAVEL_WALKOFFLEDGE,
)
from .commander import Commander
from .navigator import Navigator

if TYPE_CHECKING:
    from openarena_perception.virtual_controller import VirtualController

log = logging.getLogger(__name__)


class NavBehavior:
    """Navigation behavior handlers extracted from strategic_brain.py.

    Manages navigation state ticks (navigating, exploring, door traversal,
    item pickup) with explicit dependencies passed at construction.

    The DEAD -> EXPLORING transition (respawn recovery, NAV-06) is handled
    by on_enter_exploring which calls navigator.path_to_random(), giving
    the bot an immediate exploration target after respawn.
    """

    def __init__(
        self,
        ctrl: "VirtualController",
        navigator: Navigator,
        commander: Commander,
        aas_graph,
    ):
        self.ctrl = ctrl
        self.nav = navigator
        self.commander = commander
        self.aas_graph = aas_graph

        # Navigation target tracking
        self._nav_target: Optional[str] = None
        self._items_collected: int = 0
        self._stucks_on_current_target: int = 0
        self._target_blacklist: Dict[str, float] = {}
        self._target_failures: Dict[str, int] = {}

    # -- State entry hooks -------------------------------------------------

    def on_enter_exploring(self) -> None:
        """Called when entering EXPLORING state.

        Resets stuck attempts and picks a random exploration path.
        This is the respawn recovery path (NAV-06): after DEAD -> EXPLORING,
        the bot immediately gets a random navigation target.
        """
        self._stucks_on_current_target = 0
        self.nav.path_to_random()

    def on_enter_navigating(self) -> None:
        """Called when entering NAVIGATING state."""
        self._stucks_on_current_target = 0

    # -- State tick handlers -----------------------------------------------

    async def tick_navigating(self, sa, gs, tick_count: int) -> None:
        """Navigate toward commander-selected target.

        Extracted from strategic_brain.py lines 494-563.
        Commander decides target every 3s, blacklist checking, path following
        with jump on TRAVEL_JUMP/JUMPPAD/etc, bunny hop every 8 ticks,
        center view every 12 ticks, arrival detection.

        Args:
            sa: SituationalAwareness snapshot
            gs: GameState with current frame
            tick_count: current tick number (for modulo-based actions)
        """
        now = time.time()

        # Commander decides target every 3s
        if self.commander.should_decide() or not sa.has_path:
            px = sa.pos[0] if sa.pos else 0
            py = sa.pos[1] if sa.pos else 0

            # Try up to 5 targets in case some are blacklisted
            for _ in range(5):
                target = self.commander.decide(
                    health=sa.health, armor=sa.armor, ammo=sa.ammo,
                    pos_x=px, pos_y=py, enemies_visible=sa.enemies_visible,
                )
                if not target:
                    break

                # Check blacklist
                bl_until = self._target_blacklist.get(target.classname, 0)
                if bl_until > now:
                    # Force commander to skip this one next time
                    target.last_visited = now
                    continue

                new_target = target.classname != self._nav_target
                self._nav_target = target.classname
                if new_target:
                    self._stucks_on_current_target = 0

                target_area = self.nav.graph.nearest_area(
                    target.x, target.y, target.z
                )
                # Skip liquid targets
                if (target_area < len(self.nav.graph.areas) and
                        self.nav.graph.areas[target_area].is_liquid):
                    log.warning("Target %s in liquid -- skipping", target.classname)
                    continue

                if self.nav.path_to_area(target_area):
                    break  # path found
                else:
                    log.warning("No path to %s -- trying next", target.classname)
                    continue
            else:
                # All targets exhausted -- explore randomly
                self._nav_target = None
                self.nav.path_to_random()

        # Move forward
        self.ctrl.forward(True)

        # Follow path
        travel_type = self.nav.follow_path()
        if travel_type is not None:
            if travel_type in (TRAVEL_JUMP, TRAVEL_JUMPPAD, TRAVEL_BARRIERJUMP,
                               TRAVEL_WALKOFFLEDGE, TRAVEL_LADDER):
                self.ctrl.jump()

        # Bunny hop
        if tick_count % 8 == 0:
            self.ctrl.jump()

        # Keep view level
        if tick_count % 12 == 0:
            self.ctrl.center_view()

        # Check arrival
        if not sa.has_path and self._nav_target:
            log.info("ARRIVED at %s", self._nav_target)
            self._items_collected += 1
            self._nav_target = None

    async def tick_exploring(self, sa, gs, tick_count: int) -> None:
        """Follow random exploration path.

        Extracted from strategic_brain.py lines 565-583.
        Random path following, jump on travel types, bunny hop, center view.

        Args:
            sa: SituationalAwareness snapshot
            gs: GameState with current frame
            tick_count: current tick number (for modulo-based actions)
        """
        self.ctrl.forward(True)

        # Follow random path
        travel_type = self.nav.follow_path()
        if travel_type is not None:
            if travel_type in (TRAVEL_JUMP, TRAVEL_JUMPPAD, TRAVEL_BARRIERJUMP,
                               TRAVEL_WALKOFFLEDGE, TRAVEL_LADDER):
                self.ctrl.jump()

        if not sa.has_path:
            self.nav.path_to_random()

        if tick_count % 8 == 0:
            self.ctrl.jump()
        if tick_count % 12 == 0:
            self.ctrl.center_view()

    async def tick_door(self, sa, gs) -> None:
        """Handle door/obstacle traversal.

        Extracted from strategic_brain.py lines 585-600.
        Forward + wall turn logic with jump attempts.

        Args:
            sa: SituationalAwareness snapshot
            gs: GameState with current frame
        """
        # Slow approach: walk forward briefly, check wall
        self.ctrl.forward(True)

        # If wall still ahead, try turning toward open direction
        if sa.wall_ahead:
            if sa.open_direction < 0:
                self.ctrl.turn_degrees(20)  # turn left
            elif sa.open_direction > 0:
                self.ctrl.turn_degrees(-20)  # turn right
            else:
                self.ctrl.turn_degrees(-30)  # default turn right

            self.ctrl.jump()  # try jumping in case it's a step

    async def tick_pickup(self, sa, gs, anomaly_tracker) -> None:
        """Handle item pickup behavior.

        Extracted from strategic_brain.py lines 602-621.
        Lockable anomaly tracking, aim toward anomaly, identify.

        Args:
            sa: SituationalAwareness snapshot
            gs: GameState with current frame
            anomaly_tracker: MotionAnomalyTracker instance
        """
        lockable = anomaly_tracker.get_lockable_anomaly()
        if lockable and sa.has_frame:
            # Aim toward the anomaly
            screen_w, screen_h = 800, 600
            dx = lockable.cx - screen_w // 2
            dy = lockable.cy - screen_h // 2
            self.ctrl.track_target(dx, dy, smoothing=0.4)
            self.ctrl.forward(True)

            # Identify if not yet identified
            if not lockable.identified:
                report = anomaly_tracker.identify_anomaly(lockable, gs.frame)
                if report:
                    log.info("PICKUP: %s (%s) -- %s",
                             report.identity, report.category, report.action)
        else:
            self.ctrl.forward(True)

    # -- Properties --------------------------------------------------------

    @property
    def nav_target(self) -> Optional[str]:
        """Current navigation target classname."""
        return self._nav_target

    @nav_target.setter
    def nav_target(self, value: Optional[str]) -> None:
        self._nav_target = value

    @property
    def items_collected(self) -> int:
        return self._items_collected

    @property
    def stucks_on_current_target(self) -> int:
        return self._stucks_on_current_target

    @stucks_on_current_target.setter
    def stucks_on_current_target(self, value: int) -> None:
        self._stucks_on_current_target = value

    @property
    def target_blacklist(self) -> Dict[str, float]:
        return self._target_blacklist

    @property
    def target_failures(self) -> Dict[str, int]:
        return self._target_failures
