"""TacticalFSM -- State machine orchestrator for the bot cognitive architecture.

Extracted from strategic_brain.py in Phase 5. Manages all FSM state transitions,
enter/exit hooks, and tick dispatch to subsystem handlers.

The FSM evaluates transitions via SubsumptionArbiter (reflexes layer),
then dispatches behavior execution to the appropriate subsystem module.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import numpy as np

from openarena_perception.models import BrainState

if TYPE_CHECKING:
    from openarena_perception.combat import CombatEngager
    from openarena_perception.combat.humanize import HumanizationConfig
    from openarena_perception.models import SituationalAwareness
    from openarena_perception.motion_anomaly import MotionAnomalyTracker
    from openarena_perception.navigation import NavBehavior, SurveyBehavior
    from openarena_perception.object_tracker import ObjectTracker
    from openarena_perception.reflexes import DeathHandler, StuckEscape, SubsumptionArbiter
    from openarena_perception.virtual_controller import VirtualController

log = logging.getLogger(__name__)


class TacticalFSM:
    """State machine orchestrator. Evaluates transitions and dispatches behavior.

    Owns the FSM state (_state, _state_enter_time, _prev_state) and delegates
    transition evaluation to SubsumptionArbiter. Enter/exit hooks trigger
    side-effects on subsystem modules. Dispatch routes each tick to the
    appropriate handler.
    """

    def __init__(
        self,
        arbiter: SubsumptionArbiter,
        death_handler: DeathHandler,
        stuck_escape: StuckEscape,
        engager: CombatEngager,
        nav_behavior: NavBehavior,
        survey_behavior: SurveyBehavior | None = None,
        ctrl: VirtualController | None = None,
        anomaly_tracker: MotionAnomalyTracker | None = None,
        obj_tracker: ObjectTracker | None = None,
        humanize_config: HumanizationConfig | None = None,
    ) -> None:
        self._arbiter = arbiter
        self._death_handler = death_handler
        self._stuck_escape = stuck_escape
        self._engager = engager
        self._nav_behavior = nav_behavior
        self._survey_behavior = survey_behavior
        self._ctrl = ctrl
        self._anomaly_tracker = anomaly_tracker
        self._obj_tracker = obj_tracker
        self._humanize_config = humanize_config

        # FSM state
        self._state: BrainState = BrainState.EXPLORING
        self._state_enter_time: float = time.time()
        self._prev_state: BrainState = BrainState.EXPLORING

        # Reaction delay buffer (HUMN-02/06)
        self._pending_transition: tuple[BrainState, float] | None = None

    # -- Properties ----------------------------------------------------------

    @property
    def state(self) -> BrainState:
        """Current FSM state."""
        return self._state

    @property
    def state_enter_time(self) -> float:
        """Timestamp when the current state was entered."""
        return self._state_enter_time

    # -- FSM Methods ---------------------------------------------------------

    def evaluate_transitions(
        self, sa: SituationalAwareness, **context: Any
    ) -> BrainState:
        """Priority-ordered transition evaluation via SubsumptionArbiter."""
        state_time = time.time() - self._state_enter_time
        return self._arbiter.evaluate(
            sa, self._state, state_time, **context
        )

    # -- Humanization helpers --------------------------------------------------

    def _sample_reaction_delay(
        self, new_state: BrainState, old_state: BrainState
    ) -> float:
        """Sample reaction + hesitation delay for a state transition.

        Returns 0.0 for DEAD transitions (safety invariant) and when
        no humanization config is set.
        """
        cfg = self._humanize_config
        if cfg is None or new_state == BrainState.DEAD:
            return 0.0  # NEVER delay death handling

        rng = np.random.default_rng()

        # Reaction time from truncated normal
        mean = (cfg.reaction_time_min + cfg.reaction_time_max) / 2
        std = (cfg.reaction_time_max - cfg.reaction_time_min) / 4
        base = float(
            np.clip(rng.normal(mean, std), cfg.reaction_time_min, cfg.reaction_time_max)
        )

        # Surprise bonus: entering COMBAT from non-combat state
        if new_state == BrainState.COMBAT and old_state not in (
            BrainState.COMBAT,
            BrainState.DEAD,
        ):
            base += cfg.reaction_surprise_bonus

        # Hesitation on top (HUMN-06)
        h_mean = (cfg.hesitation_min + cfg.hesitation_max) / 2
        h_std = (cfg.hesitation_max - cfg.hesitation_min) / 4
        hesitation = float(
            np.clip(rng.normal(h_mean, h_std), cfg.hesitation_min, cfg.hesitation_max)
        )

        return base + hesitation

    def _execute_transition(
        self, new_state: BrainState, sa: SituationalAwareness
    ) -> None:
        """Execute a state transition (enter/exit hooks + logging)."""
        self.on_exit_state(self._state, sa)
        old = self._state
        self._prev_state = old
        self._state = new_state
        self._state_enter_time = time.time()
        self.on_enter_state(new_state, sa)
        log.info(
            "BRAIN: %s -> %s [%s hp=%s area=%d]",
            old.value,
            new_state.value,
            sa.disposition,
            sa.health,
            sa.current_area,
        )

    # -- State hooks -----------------------------------------------------------

    def on_enter_state(
        self, state: BrainState, sa: SituationalAwareness
    ) -> None:
        """Delegate state entry side-effects to subsystem modules."""
        if state == BrainState.DEAD:
            self._death_handler.on_enter(sa, self._anomaly_tracker, self._obj_tracker)

        elif state == BrainState.COMBAT:
            self._engager.on_enter(sa)

        elif state == BrainState.STUCK:
            nav_target = self._nav_behavior.nav_target
            new_target = self._stuck_escape.on_enter(sa, nav_target)
            if new_target is None and nav_target is not None:
                self._nav_behavior.nav_target = None  # target was blacklisted

        elif state == BrainState.EXPLORING:
            self._nav_behavior.on_enter_exploring()
            self._stuck_escape.reset_stuck_count()

        elif state == BrainState.NAVIGATING:
            self._nav_behavior.on_enter_navigating()
            self._stuck_escape.reset_stuck_count()

    def on_exit_state(
        self, state: BrainState, sa: SituationalAwareness
    ) -> None:
        """Delegate state exit side-effects to subsystem modules."""
        # Always release look actions to prevent stuck lookdown
        self._death_handler.on_exit(sa)

        if state == BrainState.COMBAT:
            self._engager.on_exit(sa)

        elif state == BrainState.SURVEYING:
            if self._ctrl is not None:
                self._ctrl.center_view()

    async def dispatch(
        self,
        state: BrainState,
        sa: SituationalAwareness,
        gs: Any,
        tick_count: int = 0,
    ) -> float | None:
        """Dispatch tick to the appropriate subsystem handler.

        Args:
            state: Current FSM state.
            sa: Situational awareness snapshot.
            gs: Game state object.
            tick_count: Current tick counter (for nav behavior).

        Returns:
            Survey cooldown value if in SURVEYING state, else None.
        """
        if state == BrainState.DEAD:
            await self._death_handler.tick(sa, gs)
        elif state == BrainState.COMBAT:
            await self._engager.tick(sa, gs)
        elif state == BrainState.STUCK:
            await self._stuck_escape.tick(sa, gs)
        elif state == BrainState.SURVEYING:
            if self._survey_behavior:
                state_time = time.time() - self._state_enter_time
                cooldown = await self._survey_behavior.tick(sa, gs, state_time)
                if cooldown is not None:
                    return cooldown
        elif state == BrainState.NAVIGATING:
            await self._nav_behavior.tick_navigating(sa, gs, tick_count)
        elif state == BrainState.EXPLORING:
            await self._nav_behavior.tick_exploring(sa, gs, tick_count)
        elif state == BrainState.TRAVERSING_DOOR:
            await self._nav_behavior.tick_door(sa, gs)
        elif state == BrainState.PICKING_UP_ITEM:
            await self._nav_behavior.tick_pickup(sa, gs, self._anomaly_tracker)
        return None

    async def tick(
        self,
        sa: SituationalAwareness,
        gs: Any,
        tick_count: int = 0,
        **context: Any,
    ) -> float | None:
        """High-level FSM tick: evaluate transitions, handle state change, dispatch.

        When *humanize_config* is set, transitions are buffered by a sampled
        reaction + hesitation delay (timestamp comparison, NOT a sleep).
        DEAD transitions are always immediate regardless of config.

        Args:
            sa: Situational awareness snapshot.
            gs: Game state object.
            tick_count: Current tick counter (for nav behavior).
            **context: Additional context for transition evaluation.

        Returns:
            Survey cooldown value if applicable, else None.
        """
        new_state = self.evaluate_transitions(sa, **context)
        now = time.time()

        if new_state != self._state:
            if self._humanize_config is None:
                # No humanization -- immediate transition (backward compat)
                self._execute_transition(new_state, sa)
            else:
                if self._pending_transition is None:
                    delay = self._sample_reaction_delay(new_state, self._state)
                    if delay <= 0.0:
                        # Zero delay (e.g. DEAD) -- execute immediately
                        self._execute_transition(new_state, sa)
                    else:
                        self._pending_transition = (new_state, now + delay)
                else:
                    # Already pending -- check if situation changed
                    if new_state != self._pending_transition[0]:
                        self._pending_transition = None  # Cancel: situation changed
                    elif now >= self._pending_transition[1]:
                        # Delay expired, execute
                        actual = self._pending_transition[0]
                        self._pending_transition = None
                        self._execute_transition(actual, sa)
        else:
            # Staying in same state -- cancel pending if target differs
            if self._pending_transition is not None:
                if self._pending_transition[0] != new_state:
                    self._pending_transition = None

        return await self.dispatch(self._state, sa, gs, tick_count=tick_count)
