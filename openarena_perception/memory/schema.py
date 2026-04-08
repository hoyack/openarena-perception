"""SQLAlchemy Core table definitions for the memory subsystem.

All persistent memory tables are defined here using SQLAlchemy Core (not ORM)
for lightweight query building on Pi hardware.
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    Index,
    Integer,
    JSON,
    LargeBinary,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

room_surveys = Table(
    "room_surveys",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("area_id", Integer, nullable=False, unique=True),
    Column("map_name", Text, nullable=False, server_default=""),
    Column("position_x", Float),
    Column("position_y", Float),
    Column("position_z", Float),
    Column("yaw_at_survey", Float),
    Column("timestamp", Float),
    Column("room_type", Text, server_default="unknown"),
    Column("exits", JSON),
    Column("items", JSON),
    Column("vantage_points", JSON),
    Column("hazards", JSON),
    Column("recommended_exit", Text, server_default=""),
    Column("summary", Text, server_default=""),
    Column("image_paths", JSON),
    Index("ix_room_surveys_map_area", "map_name", "area_id"),
)

learned_maps = Table(
    "learned_maps",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("map_name", Text, nullable=False, unique=True),
    Column("version", Integer, server_default="2"),
    Column("grid_resolution", Integer),
    Column("grid_size", Integer),
    Column("num_floors", Integer),
    Column("floor_z_threshold", Float),
    Column("grid_origin_x", Float),
    Column("grid_origin_y", Float),
    Column("grids", LargeBinary),
    Column("wall_segments", JSON),
    Column("edge_failures", JSON),
    Column("edge_successes", JSON),
    Column("updated_at", Float),
)

match_events = Table(
    "match_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("match_id", Text),
    Column("timestamp", Float),
    Column("event_type", Text),
    Column("map_name", Text),
    Column("position_x", Float),
    Column("position_y", Float),
    Column("position_z", Float),
    Column("details", JSON),
    Index("ix_match_events_type_map", "event_type", "map_name"),
    Index("ix_match_events_match_id", "match_id"),
)

item_locations = Table(
    "item_locations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("map_name", Text, nullable=False),
    Column("item_type", Text),
    Column("item_name", Text),
    Column("area_id", Integer),
    Column("position_x", Float),
    Column("position_y", Float),
    Column("position_z", Float),
    Column("last_seen", Float),
    Column("pickup_count", Integer, server_default="0"),
    UniqueConstraint("map_name", "item_type", "area_id", name="uq_item_locations_map_type_area"),
)
