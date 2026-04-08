"""SubsumptionArbiter -- priority-based state transition evaluator.

Extracted from StrategicBrain._evaluate_transitions() in Phase 4.
Preserves the exact subsumption priority order and all edge conditions.

The arbiter does NOT execute behaviors -- it only evaluates which state
should be active. The orchestrator calls this instead of inline transition logic.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from openarena_perception.models import BrainState, SituationalAwareness

if TYPE_CHECKING:
    from openarena_perception.models import SpatialKnowledge


class SubsumptionArbiter:
    """Priority-based state transition evaluator.

    Implements the subsumption architecture where higher-priority behaviors
    suppress lower-priority ones. Priority order (highest first):

        P1: DEAD        -- bot is dead, must handle respawn
        P2: COMBAT      -- under attack with visible enemies
        P3: STUCK       -- movement blocked (not from DEAD/COMBAT/SURVEYING)
        P4: PICKING_UP_ITEM -- motion anomaly while navigating/exploring
        P5: TRAVERSING_DOOR -- wall obstruction while navigating (>2s)
        P6: SURVEYING   -- new unsurveyed room while navigating/exploring

    Then return transitions for each active state back to base behaviors.
    """

    def evaluate(
        self,
        sa: SituationalAwareness,
        current_state: BrainState,
        state_time: float,
        **context,
    ) -> BrainState:
        """Return the state that should be active given current awareness.

        Args:
            sa: Current situational awareness snapshot (immutable).
            current_state: The FSM state currently active.
            state_time: Seconds elapsed since entering current_state.
            **context: Additional context for transition decisions:
                - survey_cooldown (float): timestamp after which surveys allowed
                - spatial (SpatialKnowledge): for should_survey check
                - surveyor: existence check for survey capability
                - commander: for should_decide() check
                - nav_target (Optional[str]): current navigation target

        Returns:
            The BrainState that should be active next tick.
        """
        # Extract context kwargs
        survey_cooldown: float = context.get("survey_cooldown", 0.0)
        spatial: SpatialKnowledge | None = context.get("spatial")
        surveyor = context.get("surveyor")
        commander = context.get("commander")

        # ── Priority interrupts (highest to lowest) ──────────────

        # P1: Dead -- highest priority
        if not sa.is_alive:
            return BrainState.DEAD

        # P2: Combat (under attack with visible enemies)
        if (sa.under_attack and sa.enemies_visible > 0
                and current_state != BrainState.DEAD):
            return BrainState.COMBAT

        # P3: Stuck (not from DEAD, COMBAT, SURVEYING)
        if (sa.is_stuck and not sa.is_recovering
                and current_state not in (BrainState.DEAD, BrainState.COMBAT,
                                          BrainState.SURVEYING)):
            return BrainState.STUCK

        # P4: Item pickup (motion anomaly detected while navigating)
        if (sa.lockable_anomaly
                and current_state in (BrainState.NAVIGATING, BrainState.EXPLORING)):
            return BrainState.PICKING_UP_ITEM

        # P5: Door/wall obstruction while navigating
        if (sa.wall_ahead and sa.wall_score > 0.7
                and sa.has_path
                and current_state == BrainState.NAVIGATING
                and state_time > 2.0):
            return BrainState.TRAVERSING_DOOR

        # P6: Survey new room
        if (not sa.room_surveyed
                and sa.current_area > 0
                and surveyor
                and time.time() > survey_cooldown
                and spatial is not None
                and spatial.should_survey(sa.current_area, sa.pos)
                and current_state in (BrainState.NAVIGATING, BrainState.EXPLORING)):
            return BrainState.SURVEYING

        # ── Return transitions (state-specific exits) ────────────

        # DEAD -> EXPLORING (respawned)
        if current_state == BrainState.DEAD and sa.is_alive:
            return BrainState.EXPLORING

        # COMBAT -> NAVIGATING (threat cleared)
        if (current_state == BrainState.COMBAT
                and not sa.under_attack and sa.seconds_since_damage > 3.0):
            return BrainState.NAVIGATING

        # STUCK -> NAVIGATING (unstuck)
        if (current_state == BrainState.STUCK
                and not sa.is_stuck and not sa.is_recovering):
            return BrainState.NAVIGATING

        # SURVEYING -> NAVIGATING (timeout)
        if current_state == BrainState.SURVEYING and state_time > 15.0:
            return BrainState.NAVIGATING

        # TRAVERSING_DOOR -> NAVIGATING (wall cleared or timeout)
        if current_state == BrainState.TRAVERSING_DOOR:
            if sa.wall_score < 0.3 or state_time > 5.0:
                return BrainState.NAVIGATING

        # PICKING_UP_ITEM -> NAVIGATING (anomaly gone or timeout)
        if (current_state == BrainState.PICKING_UP_ITEM
                and (not sa.lockable_anomaly or state_time > 5.0)):
            return BrainState.NAVIGATING

        # EXPLORING -> NAVIGATING (commander has a target)
        if (current_state == BrainState.EXPLORING
                and commander is not None and commander.should_decide()):
            return BrainState.NAVIGATING

        # NAVIGATING -> EXPLORING (no path and commander has nothing)
        if (current_state == BrainState.NAVIGATING
                and not sa.has_path
                and commander is not None and not commander.should_decide()):
            return BrainState.EXPLORING

        # No transition -- stay in current state
        return current_state
