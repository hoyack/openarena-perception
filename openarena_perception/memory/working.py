"""In-process working memory for current match state.

WorkingMemory is a mutable dataclass that holds per-tick state: recent events
in a ring buffer, danger zone tracking with time decay, and area visit history.
This class NEVER touches the database -- it lives entirely in process memory.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkingMemory:
    """Mutable in-process memory for current match state."""

    match_id: str = ""
    map_name: str = ""
    match_start: float = 0.0
    deaths: int = 0
    kills: int = 0

    recent_events: deque = field(default_factory=lambda: deque(maxlen=100))
    last_death_position: tuple[float, float, float] | None = None
    last_kill_position: tuple[float, float, float] | None = None
    recently_visited_areas: deque = field(default_factory=lambda: deque(maxlen=20))
    danger_zones: dict[int, float] = field(default_factory=dict)

    def add_event(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Append an event to the ring buffer with current timestamp."""
        entry: dict[str, Any] = {
            "type": event_type,
            "time": time.time(),
        }
        if data:
            entry.update(data)
        self.recent_events.append(entry)

    def get_recent_events(
        self, event_type: str | None = None, limit: int = 10
    ) -> list[dict]:
        """Return the most recent events, optionally filtered by type."""
        if event_type is None:
            items = list(self.recent_events)
        else:
            items = [e for e in self.recent_events if e.get("type") == event_type]
        return items[-limit:]

    def reset(self) -> None:
        """Zero all counters and clear all buffers."""
        self.kills = 0
        self.deaths = 0
        self.last_death_position = None
        self.last_kill_position = None
        self.recent_events.clear()
        self.recently_visited_areas.clear()
        self.danger_zones.clear()

    def visit_area(self, area_id: int) -> None:
        """Record visiting an area."""
        self.recently_visited_areas.append(area_id)

    def mark_danger(self, area_id: int) -> None:
        """Mark an area as dangerous at the current time."""
        self.danger_zones[area_id] = time.time()

    def is_dangerous(self, area_id: int, decay_seconds: float = 30.0) -> bool:
        """Return True if area was marked dangerous within *decay_seconds*."""
        ts = self.danger_zones.get(area_id)
        if ts is None:
            return False
        return (time.time() - ts) < decay_seconds
