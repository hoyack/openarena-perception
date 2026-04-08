"""DB-backed semantic memory for persistent map knowledge.

Manages room surveys, learned maps, and item locations in SQLite via
SQLAlchemy Core expressions. All methods are synchronous and use
connection-per-call pattern with explicit commit.
"""
from __future__ import annotations

import logging
import time

from sqlalchemy import Engine, insert, select, update
from sqlalchemy.exc import IntegrityError

from .schema import item_locations, learned_maps, room_surveys

log = logging.getLogger(__name__)


class SemanticMemory:
    """Semantic memory layer -- persists map knowledge in SQLite."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ── Room survey methods ──────────────────────────────────────

    def save_survey(
        self,
        area_id: int,
        map_name: str,
        position: tuple[float, float, float],
        yaw: float,
        timestamp: float,
        room_type: str = "unknown",
        exits: list | None = None,
        items: list | None = None,
        vantage_points: list | None = None,
        hazards: list | None = None,
        recommended_exit: str = "",
        summary: str = "",
        image_paths: dict | None = None,
    ) -> None:
        """Upsert a room survey. Insert first, update on conflict."""
        values = {
            "area_id": area_id,
            "map_name": map_name,
            "position_x": position[0],
            "position_y": position[1],
            "position_z": position[2],
            "yaw_at_survey": yaw,
            "timestamp": timestamp,
            "room_type": room_type,
            "exits": exits,
            "items": items,
            "vantage_points": vantage_points,
            "hazards": hazards,
            "recommended_exit": recommended_exit,
            "summary": summary,
            "image_paths": image_paths,
        }
        with self._engine.connect() as conn:
            try:
                conn.execute(insert(room_surveys).values(**values))
            except IntegrityError:
                # area_id already exists -- update instead
                upd = (
                    update(room_surveys)
                    .where(room_surveys.c.area_id == area_id)
                    .values(**{k: v for k, v in values.items() if k != "area_id"})
                )
                conn.execute(upd)
            conn.commit()

    def get_survey(self, area_id: int, map_name: str = "") -> dict | None:
        """Retrieve a single survey by area_id, optionally filtered by map_name."""
        stmt = select(room_surveys).where(room_surveys.c.area_id == area_id)
        if map_name:
            stmt = stmt.where(room_surveys.c.map_name == map_name)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        return dict(row) if row else None

    def get_all_surveys(self, map_name: str = "") -> list[dict]:
        """Return all surveys, optionally filtered by map_name."""
        stmt = select(room_surveys)
        if map_name:
            stmt = stmt.where(room_surveys.c.map_name == map_name)
        stmt = stmt.order_by(room_surveys.c.area_id)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(r) for r in rows]

    # ── Learned map methods ──────────────────────────────────────

    def save_learned_map(
        self,
        map_name: str,
        version: int,
        grid_resolution: int,
        grid_size: int,
        num_floors: int,
        floor_z_threshold: float,
        grid_origin: tuple[float, float],
        grids_bytes: bytes,
        wall_segments: list,
        edge_failures: dict,
        edge_successes: dict,
    ) -> None:
        """Upsert a learned map. Store grids as raw bytes (LargeBinary)."""
        values = {
            "map_name": map_name,
            "version": version,
            "grid_resolution": grid_resolution,
            "grid_size": grid_size,
            "num_floors": num_floors,
            "floor_z_threshold": floor_z_threshold,
            "grid_origin_x": grid_origin[0],
            "grid_origin_y": grid_origin[1],
            "grids": grids_bytes,
            "wall_segments": wall_segments,
            "edge_failures": edge_failures,
            "edge_successes": edge_successes,
            "updated_at": time.time(),
        }
        with self._engine.connect() as conn:
            try:
                conn.execute(insert(learned_maps).values(**values))
            except IntegrityError:
                upd = (
                    update(learned_maps)
                    .where(learned_maps.c.map_name == map_name)
                    .values(**{k: v for k, v in values.items() if k != "map_name"})
                )
                conn.execute(upd)
            conn.commit()

    def get_learned_map(self, map_name: str) -> dict | None:
        """Retrieve a learned map by map_name."""
        stmt = select(learned_maps).where(learned_maps.c.map_name == map_name)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        return dict(row) if row else None

    # ── Item location methods ────────────────────────────────────

    def record_item(
        self,
        map_name: str,
        item_type: str,
        item_name: str,
        area_id: int,
        position: tuple[float, float, float],
    ) -> None:
        """Upsert an item location. Increments pickup_count on update."""
        values = {
            "map_name": map_name,
            "item_type": item_type,
            "item_name": item_name,
            "area_id": area_id,
            "position_x": position[0],
            "position_y": position[1],
            "position_z": position[2],
            "last_seen": time.time(),
            "pickup_count": 1,
        }
        with self._engine.connect() as conn:
            try:
                conn.execute(insert(item_locations).values(**values))
            except IntegrityError:
                upd = (
                    update(item_locations)
                    .where(item_locations.c.map_name == map_name)
                    .where(item_locations.c.item_type == item_type)
                    .where(item_locations.c.area_id == area_id)
                    .values(
                        item_name=item_name,
                        position_x=position[0],
                        position_y=position[1],
                        position_z=position[2],
                        last_seen=time.time(),
                        pickup_count=item_locations.c.pickup_count + 1,
                    )
                )
                conn.execute(upd)
            conn.commit()

    def get_items(
        self, map_name: str, item_type: str | None = None
    ) -> list[dict]:
        """Return items for a map, optionally filtered by type."""
        stmt = select(item_locations).where(item_locations.c.map_name == map_name)
        if item_type is not None:
            stmt = stmt.where(item_locations.c.item_type == item_type)
        stmt = stmt.order_by(item_locations.c.last_seen.desc())
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [dict(r) for r in rows]
