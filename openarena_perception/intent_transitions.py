"""Pure intent transition detection (Phase 10).

Extracted from ItemTour._on_state so transition logic can be tested without
constructing the full tour object. The rules are edge-triggered (Pitfall 3):
only return a new Intent when the macro or sub actually changes.
"""
from __future__ import annotations

from dataclasses import dataclass

from openarena_perception.models import Intent, IntentStatus, MacroIntent


@dataclass
class TransitionSignals:
    """Snapshot of all tick-level signals the transition detector needs.

    Plain dataclass, not frozen -- callers build and mutate it freely each
    tick before calling detect_intent_transition().
    """
    # Nav state
    nav_is_stuck: bool = False
    nav_is_climbing_stairs: bool = False
    nav_current_area: int = 0
    # Route state
    route_idx: int = 0
    route_target_name: str = ""
    route_target_pos: tuple[float, float, float] | None = None
    # Health / respawn
    health: int | None = None
    was_alive_prev_tick: bool = True
    # Halt / wall / pin signals (already computed by item_tour)
    halt_reason: str | None = None
    advisor_hazard: bool = False
    advisor_warning: str = ""
    pinned: bool = False
    pin_escalated: bool = False
    # Time
    now: float = 0.0
    # Previous intent macro+sub for edge-trigger check
    prev_macro: MacroIntent = MacroIntent.IDLE
    prev_sub: str = ""


def detect_intent_transition(
    signals: TransitionSignals,
) -> Intent | None:
    """Return a new Intent if a transition should fire, else None.

    Priority order (highest first):
        1. Death (health <= 0)           -> RESPAWNING
        2. Respawn (was_dead -> alive)   -> TOURING ("recovering from respawn")
        3. Navigator stuck               -> RECOVERING_STUCK
        4. Pin escalation                -> RECOVERING_STUCK
        5. Proactive halt (wall/visual)  -> AVOIDING_WALL
        6. Advisor hazard ahead          -> REASSESSING_POSITION
        7. Stair-climb active            -> CLIMBING_STAIRS
        8. Stair-climb ended             -> TOURING (revert)
        9. Route advance (sub change)    -> TOURING (new sub only)

    Returns None if none of the above apply OR the detected (macro, sub)
    matches prev_macro/prev_sub exactly (edge-trigger).
    """
    s = signals

    def _maybe(new_macro: MacroIntent, new_sub: str, description: str,
               target=None, status=IntentStatus.EXECUTING) -> Intent | None:
        if new_macro == s.prev_macro and new_sub == s.prev_sub:
            return None
        return Intent(
            macro=new_macro,
            sub=new_sub,
            description=description,
            started_at=s.now,
            target=target,
            status=status,
        )

    # 1. Death
    if s.health is not None and s.health <= 0:
        return _maybe(MacroIntent.RESPAWNING, "waiting for respawn",
                      "Waiting for respawn")

    # 2. Respawn edge (was dead last tick, now alive)
    if (not s.was_alive_prev_tick) and s.health is not None and s.health > 0:
        return _maybe(MacroIntent.TOURING, "recovering from respawn",
                      "Recovering from respawn")

    # 3. Navigator stuck
    if s.nav_is_stuck:
        return _maybe(MacroIntent.RECOVERING_STUCK, "navigator stuck",
                      "Navigator reports stuck -- attempting recovery")

    # 4. Pin escalation (pinned or visual_pin halt reason)
    if s.pin_escalated or (s.halt_reason == "visual_pin" and s.pinned):
        return _maybe(MacroIntent.RECOVERING_STUCK, "pin escalation, replanning",
                      "Pin detected -- replanning path")

    # 5. Proactive wall halt
    if s.halt_reason is not None and s.halt_reason != "visual_pin":
        return _maybe(MacroIntent.AVOIDING_WALL, s.halt_reason,
                      f"Avoiding wall: {s.halt_reason}")

    # 6. Advisor hazard
    if s.advisor_hazard:
        return _maybe(MacroIntent.REASSESSING_POSITION,
                      s.advisor_warning or "advisor halt",
                      "Reassessing after advisor warning")

    # 7. Stair-climb active
    if s.nav_is_climbing_stairs:
        return _maybe(MacroIntent.CLIMBING_STAIRS, "climbing",
                      "Climbing stairs")

    # 8. Stair-climb ended (falls through to step 9 TOURING)
    # 9. Route advance (sub-only change inside TOURING)
    new_sub = f"heading to {s.route_target_name}" if s.route_target_name else "touring"
    description = (
        f"Heading to {s.route_target_name}" if s.route_target_name else "Touring"
    )
    return _maybe(MacroIntent.TOURING, new_sub, description,
                  target=s.route_target_pos)
