"""Initial schema -- create all memory tables.

Revision ID: 001
Revises: None
Create Date: 2026-04-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# Revision identifiers
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all 4 memory tables."""
    # room_surveys
    op.create_table(
        "room_surveys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("area_id", sa.Integer, nullable=False, unique=True),
        sa.Column("map_name", sa.Text, nullable=False, server_default=""),
        sa.Column("position_x", sa.Float),
        sa.Column("position_y", sa.Float),
        sa.Column("position_z", sa.Float),
        sa.Column("yaw_at_survey", sa.Float),
        sa.Column("timestamp", sa.Float),
        sa.Column("room_type", sa.Text, server_default="unknown"),
        sa.Column("exits", sa.JSON),
        sa.Column("items", sa.JSON),
        sa.Column("vantage_points", sa.JSON),
        sa.Column("hazards", sa.JSON),
        sa.Column("recommended_exit", sa.Text, server_default=""),
        sa.Column("summary", sa.Text, server_default=""),
        sa.Column("image_paths", sa.JSON),
    )
    op.create_index(
        "ix_room_surveys_map_area", "room_surveys", ["map_name", "area_id"]
    )

    # learned_maps
    op.create_table(
        "learned_maps",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("map_name", sa.Text, nullable=False, unique=True),
        sa.Column("version", sa.Integer, server_default="2"),
        sa.Column("grid_resolution", sa.Integer),
        sa.Column("grid_size", sa.Integer),
        sa.Column("num_floors", sa.Integer),
        sa.Column("floor_z_threshold", sa.Float),
        sa.Column("grid_origin_x", sa.Float),
        sa.Column("grid_origin_y", sa.Float),
        sa.Column("grids", sa.LargeBinary),
        sa.Column("wall_segments", sa.JSON),
        sa.Column("edge_failures", sa.JSON),
        sa.Column("edge_successes", sa.JSON),
        sa.Column("updated_at", sa.Float),
    )

    # match_events
    op.create_table(
        "match_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("match_id", sa.Text),
        sa.Column("timestamp", sa.Float),
        sa.Column("event_type", sa.Text),
        sa.Column("map_name", sa.Text),
        sa.Column("position_x", sa.Float),
        sa.Column("position_y", sa.Float),
        sa.Column("position_z", sa.Float),
        sa.Column("details", sa.JSON),
    )
    op.create_index(
        "ix_match_events_type_map", "match_events", ["event_type", "map_name"]
    )
    op.create_index(
        "ix_match_events_match_id", "match_events", ["match_id"]
    )

    # item_locations
    op.create_table(
        "item_locations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("map_name", sa.Text, nullable=False),
        sa.Column("item_type", sa.Text),
        sa.Column("item_name", sa.Text),
        sa.Column("area_id", sa.Integer),
        sa.Column("position_x", sa.Float),
        sa.Column("position_y", sa.Float),
        sa.Column("position_z", sa.Float),
        sa.Column("last_seen", sa.Float),
        sa.Column("pickup_count", sa.Integer, server_default="0"),
        sa.UniqueConstraint(
            "map_name", "item_type", "area_id",
            name="uq_item_locations_map_type_area",
        ),
    )


def downgrade() -> None:
    """Drop all 4 memory tables in reverse order."""
    op.drop_table("item_locations")
    op.drop_table("match_events")
    op.drop_table("learned_maps")
    op.drop_table("room_surveys")
