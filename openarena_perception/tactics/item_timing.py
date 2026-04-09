"""Item timing service with spawn prediction (COMP-01).

Tracks exact pickup timestamps per item and predicts next spawn time
using verified Q3/OpenArena respawn constants from g_items.c source.

The service consumes GameEvent objects from ConsoleLogParser and
maintains per-item timers with countdown predictions.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from openarena_perception.perception.sound_parser import GameEvent

# ---------------------------------------------------------------------------
# Respawn constants (verified from Q3 source g_items.c)
# ---------------------------------------------------------------------------

RESPAWN_TIMES: dict[str, float] = {
    "weapon": 5.0,  # RESPAWN_WEAPON
    "ammo": 40.0,  # RESPAWN_AMMO
    "health": 35.0,  # RESPAWN_HEALTH
    "armor": 25.0,  # RESPAWN_ARMOR
    "mega": 35.0,  # RESPAWN_MEGAHEALTH (NOT 120 -- that's powerups)
    "powerup": 120.0,  # RESPAWN_POWERUP (Quad, Haste, etc.)
    "holdable": 60.0,  # RESPAWN_HOLDABLE (Medkit, Teleporter)
}

# Powerup item names for fast lookup
_POWERUP_ITEMS = frozenset(
    {"item_quad", "item_haste", "item_enviro", "item_flight", "item_invis", "item_regen"}
)


# ---------------------------------------------------------------------------
# Item classification
# ---------------------------------------------------------------------------


def classify_item(item_name: str) -> str:
    """Map a Q3 item classname to a respawn category.

    Returns one of: "mega", "powerup", "weapon", "armor", "health", "ammo".
    Falls back to "health" (35s) for unknown items.
    """
    if item_name == "item_health_mega":
        return "mega"
    if item_name in _POWERUP_ITEMS:
        return "powerup"
    if "weapon" in item_name:
        return "weapon"
    if "armor" in item_name:
        return "armor"
    if "health" in item_name:
        return "health"
    if "ammo" in item_name:
        return "ammo"
    return "health"  # safe fallback: 35s


# ---------------------------------------------------------------------------
# ItemTimer dataclass
# ---------------------------------------------------------------------------


@dataclass
class ItemTimer:
    """Tracks a single item's respawn cycle."""

    item_name: str  # e.g., "item_health_mega"
    category: str  # from classify_item
    respawn_seconds: float  # from RESPAWN_TIMES[category]
    last_pickup_time: float = 0.0
    pickup_count: int = 0

    @property
    def predicted_spawn_time(self) -> float:
        """When this item will next be available."""
        if self.last_pickup_time == 0.0:
            return 0.0  # never seen picked up -> assume available
        return self.last_pickup_time + self.respawn_seconds

    @property
    def seconds_until_spawn(self) -> float:
        """Seconds until predicted spawn. Clamped to >= 0."""
        return max(0.0, self.predicted_spawn_time - time.time())

    @property
    def is_available(self) -> bool:
        """True when item is predicted to have respawned."""
        return self.seconds_until_spawn <= 0.0


# ---------------------------------------------------------------------------
# ItemTimingService
# ---------------------------------------------------------------------------


class ItemTimingService:
    """Manages timers for all tracked items across a match.

    Consumes GameEvent objects from ConsoleLogParser and maintains
    per-item timers with countdown-based spawn predictions.
    """

    def __init__(self) -> None:
        self._timers: dict[str, ItemTimer] = {}

    def record_pickup(
        self, item_name: str, pickup_time: float | None = None
    ) -> None:
        """Record an item pickup, creating or updating the timer."""
        if pickup_time is None:
            pickup_time = time.time()

        if item_name in self._timers:
            timer = self._timers[item_name]
            timer.last_pickup_time = pickup_time
            timer.pickup_count += 1
        else:
            category = classify_item(item_name)
            respawn = RESPAWN_TIMES.get(category, 35.0)
            self._timers[item_name] = ItemTimer(
                item_name=item_name,
                category=category,
                respawn_seconds=respawn,
                last_pickup_time=pickup_time,
                pickup_count=1,
            )

    def process_events(self, events: list[GameEvent]) -> None:
        """Consume a list of GameEvents, updating timers for Item events.

        Resets all timers on InitGame (map change).
        """
        for evt in events:
            if evt.event_type == "InitGame":
                self.reset_all()
            elif evt.event_type == "Item" and evt.item_name:
                self.record_pickup(evt.item_name, evt.timestamp_real)

    def reset_all(self) -> None:
        """Clear all timers. Called on map change."""
        self._timers.clear()

    def get_timer(self, item_name: str) -> ItemTimer | None:
        """Get the timer for a specific item, or None if not tracked."""
        return self._timers.get(item_name)

    def get_upcoming(self, limit: int = 5) -> list[ItemTimer]:
        """Return timers sorted by seconds_until_spawn, excluding available items."""
        pending = [t for t in self._timers.values() if not t.is_available]
        pending.sort(key=lambda t: t.seconds_until_spawn)
        return pending[:limit]
