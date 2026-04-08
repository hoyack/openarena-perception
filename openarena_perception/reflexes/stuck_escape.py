"""StuckEscape -- stuck recovery with target blacklisting.

Extracted from StrategicBrain._tick_stuck(), _on_enter_state(STUCK),
and target blacklist logic in Phase 4.

When the bot gets stuck, this module:
  - Delegates to Navigator.handle_stuck for scan-and-probe recovery
  - Tracks per-target failure counts
  - Blacklists targets that cause repeated stucks (90s timeout)
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Dict, Optional

from openarena_perception.models import SituationalAwareness

if TYPE_CHECKING:
    from openarena_perception.game_state import GameState
    from openarena_perception.navigator import Navigator

log = logging.getLogger(__name__)


class StuckEscape:
    """Stuck recovery handler with target blacklisting.

    Tracks how many times the bot gets stuck on each navigation target.
    After 2 stucks on the same target, blacklists it for 90 seconds
    so the commander picks a different destination.

    The actual stuck recovery (scan-and-probe exit finding) is delegated
    to Navigator.handle_stuck().
    """

    # Blacklist duration in seconds
    BLACKLIST_TIMEOUT: float = 90.0
    # Stucks on same target before blacklisting
    BLACKLIST_THRESHOLD: int = 2

    def __init__(self, navigator: Navigator) -> None:
        self._navigator = navigator
        self._stuck_attempts: int = 0
        self._stucks_on_current_target: int = 0
        self._target_failures: Dict[str, int] = {}
        self._target_blacklist: Dict[str, float] = {}

    @property
    def stuck_attempts(self) -> int:
        """Total stuck attempts this session."""
        return self._stuck_attempts

    @property
    def target_failures(self) -> Dict[str, int]:
        """Per-target failure counts."""
        return self._target_failures

    @property
    def target_blacklist(self) -> Dict[str, float]:
        """Per-target blacklist expiry timestamps."""
        return self._target_blacklist

    def on_enter(
        self,
        sa: SituationalAwareness,
        nav_target: Optional[str],
    ) -> Optional[str]:
        """Called when entering STUCK state.

        Increments stuck counters. If the same target has caused 2+ stucks,
        blacklists it for 90 seconds and returns None (forcing target change).

        Args:
            sa: Current situational awareness.
            nav_target: Current navigation target classname, or None.

        Returns:
            Updated nav_target (None if blacklisted, unchanged otherwise).
        """
        self._stuck_attempts += 1
        self._stucks_on_current_target += 1

        # Blacklist target after repeated stucks
        if nav_target and self._stucks_on_current_target >= self.BLACKLIST_THRESHOLD:
            self._target_failures[nav_target] = (
                self._target_failures.get(nav_target, 0) + 1
            )
            self._target_blacklist[nav_target] = time.time() + self.BLACKLIST_TIMEOUT
            log.warning(
                "Blacklisting %s for %.0fs (stuck %d times)",
                nav_target,
                self.BLACKLIST_TIMEOUT,
                self._stucks_on_current_target,
            )
            self._stucks_on_current_target = 0
            return None  # target blacklisted, caller should clear nav_target

        return nav_target

    async def tick(self, sa: SituationalAwareness, gs: GameState) -> None:
        """Execute stuck recovery for one tick.

        Delegates to Navigator.handle_stuck() which runs the scan-and-probe
        exit finding algorithm.
        """

        def capture():
            return gs.frame

        self._navigator.handle_stuck(
            capture_fn=capture if sa.has_frame else None,
        )

    def is_blacklisted(self, target: str) -> bool:
        """Check if a target is currently blacklisted.

        Args:
            target: The target classname to check.

        Returns:
            True if target is blacklisted and the blacklist has not expired.
        """
        expiry = self._target_blacklist.get(target, 0)
        return time.time() < expiry

    def reset_stuck_count(self) -> None:
        """Reset stuck attempt counters.

        Called when entering EXPLORING or NAVIGATING states to start
        fresh stuck tracking for the new movement phase.
        """
        self._stuck_attempts = 0
