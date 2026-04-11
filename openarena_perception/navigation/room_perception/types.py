"""Immutable entity types for the Phase 13 room perception subsystem.

Wall is locked by 13-CONTEXT.md and consumed by LineFitter (Plan 13-03).
Corner/Room/PartialRoom/Doorway are forward-declared placeholders so Plan
13-04 can populate them without churning the room_perception package API.
"""
from __future__ import annotations

from typing import NamedTuple


class Wall(NamedTuple):
    """Architectural wall segment fitted from a raycast point cloud.

    Produced by LineFitter.fit() / fit_now(). Immutable — merges across fit
    passes emit a replacement tuple with the same id and accumulated support.
    """

    id: int
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    support_count: int
    first_seen: float
    last_seen: float


class Corner(NamedTuple):
    """Vertex where two walls meet at a non-parallel angle (Plan 13-04)."""

    id: int
    x: float
    y: float
    wall_a_id: int
    wall_b_id: int
    angle_deg: float
    confidence: float


class Room(NamedTuple):
    """Closed wall/corner polygon with per-room observation log (Plan 13-04)."""

    id: int
    polygon_vertices: tuple  # tuple[tuple[float, float], ...]
    bounds: tuple            # (min_x, min_y, max_x, max_y)
    area: float
    wall_ids: tuple
    corner_ids: tuple
    doorway_ids: tuple
    items_seen: tuple
    visit_count: int
    first_seen_ts: float
    last_seen_ts: float
    last_visited_ts: float
    notes: str


class PartialRoom(NamedTuple):
    """Incomplete room — walls and corners gathered but no closed cycle yet."""

    id: int
    wall_ids: tuple
    corner_ids: tuple


class Doorway(NamedTuple):
    """Gap between two walls connecting rooms or a room to outside (Plan 13-04)."""

    id: int
    wall_a_id: int
    wall_b_id: int
    gap_distance: float
    midpoint_x: float
    midpoint_y: float
