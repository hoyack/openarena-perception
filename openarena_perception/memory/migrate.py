"""JSON-to-SQLite migration for room surveys and learned maps.

Imports existing JSON persistence files into the SQLite memory database.
Designed as a one-time migration but safe to re-run (upserts on conflict).
"""
from __future__ import annotations

import base64
import glob
import json
import logging
import os

from sqlalchemy import Engine

from .semantic import SemanticMemory

log = logging.getLogger(__name__)


def migrate_room_surveys(
    engine: Engine, survey_dir: str, map_name: str = ""
) -> int:
    """Import ``area_*.json`` files from *survey_dir* into SQLite.

    Args:
        engine: SQLAlchemy engine connected to the target database.
        survey_dir: Directory containing ``area_*.json`` files.
        map_name: Map name to assign to all imported surveys.

    Returns:
        Number of surveys successfully imported.
    """
    sm = SemanticMemory(engine)
    pattern = os.path.join(survey_dir, "area_*.json")
    files = sorted(glob.glob(pattern))
    count = 0

    for path in files:
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Skipping malformed survey file %s: %s", path, exc)
            continue

        # Validate required fields
        if "area_id" not in data or "position" not in data:
            log.warning("Skipping survey file %s: missing area_id or position", path)
            continue

        pos = data["position"]
        if not isinstance(pos, list) or len(pos) < 3:
            log.warning("Skipping survey file %s: invalid position field", path)
            continue

        sm.save_survey(
            area_id=data["area_id"],
            map_name=map_name or data.get("map_name", ""),
            position=(float(pos[0]), float(pos[1]), float(pos[2])),
            yaw=data.get("yaw_at_survey", 0.0),
            timestamp=data.get("timestamp", 0.0),
            room_type=data.get("room_type", "unknown"),
            exits=data.get("exits"),
            items=data.get("items"),
            vantage_points=data.get("vantage_points"),
            hazards=data.get("hazards"),
            recommended_exit=data.get("recommended_exit", ""),
            summary=data.get("summary", ""),
            image_paths=data.get("image_paths"),
        )
        count += 1

    log.info("Migrated %d room surveys from %s", count, survey_dir)
    return count


def migrate_learned_maps(engine: Engine, maps_dir: str) -> int:
    """Import learned map JSON files from *maps_dir* into SQLite.

    Each JSON file contains base64-encoded grid data that is decoded to raw
    bytes before storage.

    Args:
        engine: SQLAlchemy engine connected to the target database.
        maps_dir: Directory containing ``*.json`` learned map files.

    Returns:
        Number of maps successfully imported.
    """
    sm = SemanticMemory(engine)
    expanded = os.path.expanduser(maps_dir)
    pattern = os.path.join(expanded, "*.json")
    files = sorted(glob.glob(pattern))
    count = 0

    for path in files:
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Skipping malformed map file %s: %s", path, exc)
            continue

        # Validate required fields
        if "map_name" not in data or "grids" not in data:
            log.warning("Skipping map file %s: missing map_name or grids", path)
            continue

        # Decode base64 grids to raw bytes
        try:
            grids_bytes = b"".join(
                base64.b64decode(g) for g in data["grids"]
            )
        except Exception as exc:
            log.warning("Skipping map file %s: failed to decode grids: %s", path, exc)
            continue

        origin = data.get("grid_origin", [0.0, 0.0])

        sm.save_learned_map(
            map_name=data["map_name"],
            version=data.get("version", 2),
            grid_resolution=data.get("grid_resolution", 64),
            grid_size=data.get("grid_size", 64),
            num_floors=data.get("num_floors", 2),
            floor_z_threshold=data.get("floor_z_threshold", -20.0),
            grid_origin=(float(origin[0]), float(origin[1])),
            grids_bytes=grids_bytes,
            wall_segments=data.get("wall_segments", []),
            edge_failures=data.get("edge_failures", {}),
            edge_successes=data.get("edge_successes", {}),
        )
        count += 1

    log.info("Migrated %d learned maps from %s", count, expanded)
    return count


def migrate_all(
    engine: Engine,
    survey_dir: str = "room_surveys",
    maps_dir: str = "~/.openarena/learned_maps",
    map_name: str = "",
) -> dict:
    """Run all migrations and return counts.

    Args:
        engine: SQLAlchemy engine.
        survey_dir: Path to room survey JSON directory.
        maps_dir: Path to learned map JSON directory.
        map_name: Map name to assign to imported surveys.

    Returns:
        Dict with ``surveys`` and ``maps`` counts.
    """
    surveys = migrate_room_surveys(engine, survey_dir, map_name)
    maps = migrate_learned_maps(engine, maps_dir)
    return {"surveys": surveys, "maps": maps}


if __name__ == "__main__":
    import sys

    from .storage import create_database

    # Default DB path from settings or argument
    db_path = sys.argv[1] if len(sys.argv) > 1 else "~/.openarena/memory.db"
    engine = create_database(db_path)
    result = migrate_all(engine)
    print(f"Migration complete: {result['surveys']} surveys, {result['maps']} maps")
