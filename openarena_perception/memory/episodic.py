"""DB-backed episodic memory for match events.

Records and retrieves match events (kills, deaths, engagements) from SQLite
via SQLAlchemy Core expressions against the match_events table.
"""
from __future__ import annotations

import time

from sqlalchemy import Engine, func, insert, select

from .schema import match_events


class EpisodicMemory:
    """Episodic memory layer -- stores match events in SQLite."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record_event(
        self,
        match_id: str,
        event_type: str,
        map_name: str,
        position: tuple[float, float, float] | None = None,
        details: dict | None = None,
    ) -> None:
        """Insert a match event with the current timestamp."""
        values: dict = {
            "match_id": match_id,
            "event_type": event_type,
            "map_name": map_name,
            "timestamp": time.time(),
            "details": details,
        }
        if position is not None:
            values["position_x"] = position[0]
            values["position_y"] = position[1]
            values["position_z"] = position[2]

        with self._engine.connect() as conn:
            conn.execute(insert(match_events).values(**values))
            conn.commit()

    def get_deaths(self, map_name: str, limit: int = 50) -> list[dict]:
        """Return recent death events for *map_name*."""
        stmt = (
            select(match_events)
            .where(match_events.c.event_type == "death")
            .where(match_events.c.map_name == map_name)
            .order_by(match_events.c.timestamp.desc())
            .limit(limit)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(r) for r in rows]

    def get_match_events(self, match_id: str) -> list[dict]:
        """Return all events for a given match, ordered by timestamp."""
        stmt = (
            select(match_events)
            .where(match_events.c.match_id == match_id)
            .order_by(match_events.c.timestamp)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(r) for r in rows]

    def get_events_by_type(
        self,
        event_type: str,
        map_name: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Query events by type with optional map filter."""
        stmt = (
            select(match_events)
            .where(match_events.c.event_type == event_type)
            .order_by(match_events.c.timestamp.desc())
            .limit(limit)
        )
        if map_name is not None:
            stmt = stmt.where(match_events.c.map_name == map_name)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(r) for r in rows]

    def get_death_heatmap(
        self, map_name: str
    ) -> list[tuple[float, float, float, int]]:
        """Return (x, y, z, count) death clusters rounded to nearest 100 units."""
        # Round positions to nearest 100 for clustering
        rx = func.round(match_events.c.position_x / 100.0) * 100.0
        ry = func.round(match_events.c.position_y / 100.0) * 100.0
        rz = func.round(match_events.c.position_z / 100.0) * 100.0
        cnt = func.count()

        stmt = (
            select(rx.label("x"), ry.label("y"), rz.label("z"), cnt.label("count"))
            .where(match_events.c.event_type == "death")
            .where(match_events.c.map_name == map_name)
            .where(match_events.c.position_x.isnot(None))
            .group_by(rx, ry, rz)
            .order_by(cnt.desc())
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [(float(r[0]), float(r[1]), float(r[2]), int(r[3])) for r in rows]
