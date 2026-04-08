# Phase 3: Memory and Persistence - Research

**Researched:** 2026-04-08
**Domain:** SQLite persistence, async database access, memory subsystem architecture
**Confidence:** HIGH

## Summary

Phase 3 replaces all JSON/pickle file persistence with SQLite, and organizes the memory subsystem into three cognitive layers: working memory (current match state), episodic memory (match history, engagement outcomes), and semantic memory (map knowledge, room surveys, item locations). The existing codebase has two concrete persistence sources to migrate: 64 room survey JSON files in `room_surveys/` and 1 learned map JSON file in `~/.openarena/learned_maps/`. The spatial_map.py (topological map) and object_tracker.py currently have no persistence -- they are in-memory only.

The stack is well-established: SQLite 3.51.1 (already on the Pi), aiosqlite for async access, SQLAlchemy Core (not ORM) for query building, and Alembic for schema migrations. The key architectural decision is using SQLAlchemy Core mode (Table + select/insert expressions) rather than full ORM to keep it lightweight on Pi -- raw SQL only for proven hot paths. The sync/async boundary is handled by providing both sync and async database access since the game loop is synchronous but the future FastAPI layer (Phase 6) needs async.

**Primary recommendation:** Build a thin `memory/` module with `storage.py` (DB engine + connection management), `working.py` (in-process dict/dataclass -- NOT in DB), `episodic.py` (match events table), `semantic.py` (room surveys + learned maps + item locations tables). Include a one-time migration script to import existing JSON files. Use Alembic with file-based config for schema evolution.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEM-01 | SQLite database replaces all JSON/pickle file persistence | storage.py with engine factory, WAL mode, 64 room surveys + 1 learned map migrated |
| MEM-02 | Working memory -- current match state, recent events, short-term buffer | working.py as in-process data structure (not DB-backed), ring buffer for recent events |
| MEM-03 | Episodic memory -- match history, death locations, engagement outcomes | episodic.py with match_events table, death_locations table, engagement_outcomes table |
| MEM-04 | Semantic memory -- map knowledge, room surveys, item locations persisted in DB | semantic.py with room_surveys, learned_maps (grid blobs), item_locations tables |
| MEM-05 | Alembic migrations for schema evolution | alembic/ directory at project root, env.py configured for SQLite, initial migration creates all tables |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlite3 | stdlib (3.51.1 on Pi) | Database engine | Zero-config, single-file, already available. WAL mode for concurrent access. [VERIFIED: `python3 -c "import sqlite3; print(sqlite3.sqlite_version)"` returns 3.51.1] |
| aiosqlite | >=0.22 | Async SQLite wrapper | Non-blocking DB from future async handlers. Wraps stdlib sqlite3. [VERIFIED: PyPI shows v0.22.1, Dec 2025] |
| SQLAlchemy | >=2.0,<3.0 | Query builder (Core mode) | Type-safe query building without ORM overhead. SA 2.0 supports async via aiosqlite. [VERIFIED: from STACK.md research] |
| alembic | >=1.14 | Schema migrations | Industry standard for SQLAlchemy migrations. Essential for evolving DB schema. [VERIFIED: from STACK.md research] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-asyncio | >=0.24 | Async test support | Testing async DB operations | [VERIFIED: from STACK.md research] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQLAlchemy Core | Raw sqlite3 | Less type safety, manual SQL strings, harder to maintain. Core adds minimal overhead. |
| SQLAlchemy Core | SQLAlchemy ORM | ORM adds object mapping overhead unnecessary for this use case. Core is ~2x faster for inserts. |
| aiosqlite | synchronous sqlite3 only | Would block the event loop in Phase 6 (FastAPI). Plan for async now. |

**Installation:**
```bash
uv add aiosqlite "sqlalchemy>=2.0,<3.0" alembic
uv add --dev pytest-asyncio
```

## Architecture Patterns

### Recommended Module Structure
```
openarena_perception/
  memory/
    __init__.py          # Public API: get_db(), MemoryManager
    storage.py           # Engine factory, connection mgmt, WAL config
    schema.py            # SQLAlchemy Core Table definitions (all tables)
    working.py           # WorkingMemory class (in-process, NOT DB)
    episodic.py          # EpisodicMemory class (DB-backed)
    semantic.py          # SemanticMemory class (DB-backed)
    migrate.py           # One-time JSON-to-SQLite migration script

alembic/                 # At project root (standard location)
  env.py
  versions/
    001_initial_schema.py
alembic.ini
```

### Pattern 1: Sync + Async Dual Access
**What:** Provide both synchronous and asynchronous database access. The game tick loop is synchronous and needs fast sync reads. The future API layer (Phase 6) needs async.
**When:** All DB operations.
**Why:** The perception loop runs synchronously at 15+ FPS. Wrapping every DB call in `asyncio.run()` or `loop.run_until_complete()` adds unnecessary overhead. Instead, maintain a sync sqlite3 connection for the hot path and an async aiosqlite connection for API/background tasks.

```python
# Source: SQLAlchemy 2.0 docs + aiosqlite patterns [ASSUMED]
import sqlite3
from pathlib import Path
from sqlalchemy import create_engine, MetaData

class DatabaseManager:
    """Manages sync and async database connections."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Sync engine for game loop (fast reads/writes)
        self._sync_engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            pool_pre_ping=True,
        )

        # Configure WAL mode on first connection
        with self._sync_engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))
            conn.execute(text("PRAGMA cache_size=-8000"))  # 8MB cache
            conn.commit()

    @property
    def sync_engine(self):
        return self._sync_engine

    async def async_engine(self):
        """Lazy-create async engine for API layer (Phase 6)."""
        from sqlalchemy.ext.asyncio import create_async_engine
        if not hasattr(self, '_async_engine'):
            self._async_engine = create_async_engine(
                f"sqlite+aiosqlite:///{self.db_path}",
                echo=False,
            )
        return self._async_engine
```

### Pattern 2: Schema as SQLAlchemy Core Tables
**What:** Define all tables as SQLAlchemy `Table` objects in a single `schema.py`. No ORM models -- just table definitions with MetaData.
**When:** All table definitions.

```python
# Source: SQLAlchemy Core pattern [CITED: docs.sqlalchemy.org/en/20/core/]
from sqlalchemy import (
    MetaData, Table, Column, Integer, Float, Text, Boolean, LargeBinary,
    JSON, UniqueConstraint, Index
)

metadata = MetaData()

room_surveys = Table(
    "room_surveys", metadata,
    Column("id", Integer, primary_key=True),
    Column("area_id", Integer, nullable=False, unique=True),
    Column("map_name", Text, nullable=False, default=""),
    Column("position_x", Float),
    Column("position_y", Float),
    Column("position_z", Float),
    Column("yaw_at_survey", Float),
    Column("timestamp", Float),
    Column("room_type", Text, default="unknown"),
    Column("exits", JSON),           # list of exit dicts
    Column("items", JSON),           # list of item dicts
    Column("vantage_points", JSON),  # list of vantage dicts
    Column("hazards", JSON),         # list of hazard dicts
    Column("recommended_exit", Text, default=""),
    Column("summary", Text, default=""),
    Column("image_paths", JSON),     # dict of direction -> path
    Index("ix_room_surveys_map_area", "map_name", "area_id"),
)

learned_maps = Table(
    "learned_maps", metadata,
    Column("id", Integer, primary_key=True),
    Column("map_name", Text, nullable=False, unique=True),
    Column("version", Integer, default=2),
    Column("grid_resolution", Integer),
    Column("grid_size", Integer),
    Column("num_floors", Integer),
    Column("floor_z_threshold", Float),
    Column("grid_origin_x", Float),
    Column("grid_origin_y", Float),
    Column("grids", LargeBinary),    # concatenated numpy arrays as bytes
    Column("wall_segments", JSON),   # list of [x1,y1,x2,y2,confidence,last_seen]
    Column("edge_failures", JSON),   # dict of edge_key -> count
    Column("edge_successes", JSON),  # dict of edge_key -> count
    Column("updated_at", Float),
)

match_events = Table(
    "match_events", metadata,
    Column("id", Integer, primary_key=True),
    Column("match_id", Text),
    Column("timestamp", Float),
    Column("event_type", Text),       # death, kill, damage, item_pickup
    Column("map_name", Text),
    Column("position_x", Float),
    Column("position_y", Float),
    Column("position_z", Float),
    Column("details", JSON),          # event-specific data
    Index("ix_match_events_type", "event_type", "map_name"),
    Index("ix_match_events_match", "match_id"),
)

item_locations = Table(
    "item_locations", metadata,
    Column("id", Integer, primary_key=True),
    Column("map_name", Text, nullable=False),
    Column("item_type", Text),        # weapon/health/armor/powerup
    Column("item_name", Text),        # specific: "rocket_launcher", "mega_health"
    Column("area_id", Integer),
    Column("position_x", Float),
    Column("position_y", Float),
    Column("position_z", Float),
    Column("last_seen", Float),
    Column("pickup_count", Integer, default=0),
    UniqueConstraint("map_name", "item_type", "area_id", name="uq_item_loc"),
)
```

### Pattern 3: Working Memory as In-Process Data (Not DB)
**What:** Working memory is a fast, in-process data structure -- NOT stored in SQLite. It holds the current match state, recent event ring buffer, and short-term context. It resets on death and between matches.
**When:** Every tick reads/writes working memory.
**Why:** DB round-trips are too slow for per-tick data (even 0.1ms x 15 FPS = 1.5ms/s wasted). Working memory is volatile by design.

```python
from collections import deque
from dataclasses import dataclass, field
from typing import Any

@dataclass
class WorkingMemory:
    """Fast in-process state for current match. Resets on match end."""

    # Current match context
    match_id: str = ""
    map_name: str = ""
    match_start: float = 0.0
    deaths: int = 0
    kills: int = 0

    # Recent events ring buffer (last N events)
    recent_events: deque = field(default_factory=lambda: deque(maxlen=100))

    # Short-term spatial memory
    last_death_position: tuple | None = None
    last_kill_position: tuple | None = None
    recently_visited_areas: deque = field(default_factory=lambda: deque(maxlen=20))

    # Danger zones (area_id -> timestamp, decays)
    danger_zones: dict[int, float] = field(default_factory=dict)

    def add_event(self, event_type: str, data: dict[str, Any]) -> None:
        import time
        self.recent_events.append({
            "type": event_type,
            "time": time.time(),
            **data,
        })

    def reset(self) -> None:
        """Reset for new match."""
        self.deaths = 0
        self.kills = 0
        self.recent_events.clear()
        self.danger_zones.clear()
        self.recently_visited_areas.clear()
```

### Pattern 4: Alembic for Non-Web Python Project
**What:** Standard Alembic configuration that reads the DB path from BotSettings and uses SQLAlchemy Core metadata.
**When:** Schema evolution after initial release.

```python
# alembic/env.py (simplified for non-web project)
from alembic import context
from openarena_perception.memory.schema import metadata
from openarena_perception.settings import get_settings

settings = get_settings()
db_url = f"sqlite:///{settings.db_path}"

def run_migrations_online():
    from sqlalchemy import create_engine
    engine = create_engine(db_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
```

### Anti-Patterns to Avoid
- **Storing per-tick data in SQLite:** Working memory must be in-process. DB writes are for durable data only (surveys, maps, match summaries).
- **Using SQLAlchemy ORM sessions:** Core is the right abstraction. No Session, no mapped classes, no identity map overhead.
- **Blocking async event loop with sync DB calls:** Keep sync engine for game loop, async engine for API. Never mix.
- **Storing image files in SQLite:** Keep survey images on filesystem. Store file paths in DB. BLOBs are for compact binary data (occupancy grids).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Schema migrations | Custom SQL scripts | Alembic | Alembic handles version tracking, rollback, dependency ordering |
| Connection pooling | Custom pool | SQLAlchemy engine (built-in pool) | Handles connection lifecycle, pool_pre_ping for stale connections |
| JSON column handling | Manual json.dumps/loads | SQLAlchemy JSON type | Automatic serialization, works with both sync and async |
| Binary blob storage | Custom base64 encoding | SQLAlchemy LargeBinary | Direct bytes storage, no encode/decode overhead vs JSON+base64 |
| Query building | f-string SQL | SQLAlchemy Core expressions | SQL injection prevention, type checking, database-agnostic |

**Key insight:** The existing codebase already has JSON serialization everywhere. SQLAlchemy's JSON column type replaces manual json.dumps/loads transparently, and LargeBinary replaces the base64-encoded numpy arrays currently in learned_map.py.

## Data Migration Analysis

### Existing Persistence Inventory

| Source | Location | Format | Records | Data Size | Migration Strategy |
|--------|----------|--------|---------|-----------|-------------------|
| Room surveys | `room_surveys/area_*.json` | JSON files | 64 surveys | ~64 files + 640 images | Insert JSON data into room_surveys table, keep image files on disk |
| Learned maps | `~/.openarena/learned_maps/*.json` | JSON + base64 grids | 1 map | ~116KB | Insert into learned_maps table, decode base64 to raw bytes for LargeBinary |
| Spatial map | In-memory only | N/A | 0 | 0 | No migration needed -- spatial_map.py has no persistence |
| Object tracker | In-memory only | N/A | 0 | 0 | No migration needed -- ephemeral per-frame data |
| SpatialKnowledge | `room_surveys/area_*.json` (same as above) | JSON | Same as room surveys | Same | Already covered by room survey migration |

### Room Survey JSON Schema (from actual files)
```json
{
  "area_id": 111,
  "position": [659.0, 964.0, 50.0],
  "yaw_at_survey": -108.0,
  "timestamp": 1775613332.49,
  "room_type": "jail_cell",
  "exits": [{"direction": "SE", "type": "corridor", "description": "..."}],
  "items": [{"direction": "N", "type": "weapon", "description": "..."}],
  "vantage_points": [],
  "hazards": [],
  "recommended_exit": "SE",
  "summary": "A small room...",
  "image_paths": {"N": "/path/to/area_111_N.jpg", ...}
}
```
[VERIFIED: direct inspection of room_surveys/area_111.json and area_125.json]

### Learned Map JSON Schema (from actual file)
```json
{
  "map_name": "str",
  "version": 2,
  "grid_resolution": 64,
  "grid_size": 64,
  "num_floors": 2,
  "floor_z_threshold": -20.0,
  "grid_origin": [float, float],
  "grids": ["base64_string", "base64_string"],  // 2 floors, each 64x64 uint8
  "wall_segments": [[x1,y1,x2,y2,confidence,last_seen], ...],  // 500 segments
  "edge_failures": {"key": count, ...},
  "edge_successes": {"key": count, ...}
}
```
[VERIFIED: inspected ~/.openarena/learned_maps/oa_dm1.json structure]

### Grid Binary Storage
Each floor grid is 64x64 uint8 = 4,096 bytes raw. Currently stored as base64 (~5,461 chars per floor). In SQLite, store as a single LargeBinary column containing concatenated raw bytes for all floors (8,192 bytes for 2 floors). This is 33% smaller than base64 and avoids encode/decode on every save. [ASSUMED: numpy tobytes() output is compatible with SQLite BLOB]

### Migration Script Approach
```python
# memory/migrate.py
def migrate_room_surveys(db_engine, survey_dir: str, map_name: str = ""):
    """Import existing room_surveys/*.json into SQLite."""
    import glob, json
    from sqlalchemy import insert
    from .schema import room_surveys

    with db_engine.connect() as conn:
        for path in glob.glob(os.path.join(survey_dir, "area_*.json")):
            with open(path) as f:
                data = json.load(f)
            conn.execute(insert(room_surveys).values(
                area_id=data["area_id"],
                map_name=map_name,
                position_x=data["position"][0],
                position_y=data["position"][1],
                position_z=data["position"][2],
                yaw_at_survey=data["yaw_at_survey"],
                timestamp=data["timestamp"],
                room_type=data.get("room_type", "unknown"),
                exits=data.get("exits", []),
                items=data.get("items", []),
                vantage_points=data.get("vantage_points", []),
                hazards=data.get("hazards", []),
                recommended_exit=data.get("recommended_exit", ""),
                summary=data.get("summary", ""),
                image_paths=data.get("image_paths", {}),
            ))
        conn.commit()

def migrate_learned_maps(db_engine, maps_dir: str):
    """Import existing learned_maps/*.json into SQLite."""
    import base64, glob, json
    from sqlalchemy import insert
    from .schema import learned_maps

    with db_engine.connect() as conn:
        for path in glob.glob(os.path.join(maps_dir, "*.json")):
            with open(path) as f:
                data = json.load(f)
            # Decode base64 grids to raw bytes
            raw_grids = b"".join(base64.b64decode(g) for g in data.get("grids", []))
            conn.execute(insert(learned_maps).values(
                map_name=data["map_name"],
                version=data.get("version", 1),
                grid_resolution=data.get("grid_resolution", 64),
                grid_size=data.get("grid_size", 64),
                num_floors=data.get("num_floors", 2),
                floor_z_threshold=data.get("floor_z_threshold", -20.0),
                grid_origin_x=data["grid_origin"][0],
                grid_origin_y=data["grid_origin"][1],
                grids=raw_grids,
                wall_segments=data.get("wall_segments", []),
                edge_failures=data.get("edge_failures", {}),
                edge_successes=data.get("edge_successes", {}),
            ))
        conn.commit()
```

## Settings Integration

Add `db_path` to `BotSettings` in `settings.py`:

```python
# In BotSettings class
db_path: str = Field(
    default="~/.openarena/bot.db",
    description="Path to SQLite database file"
)
```
[VERIFIED: settings.py currently uses pydantic-settings with env prefix OA_]

This allows override via `OA_DB_PATH` env var or `bot.toml` config.

## Sync/Async Boundary Decision

The game loop in this project is synchronous (Phase 2 perception loop runs at 15+ FPS without asyncio). The key question is how to provide DB access.

**Decision: Sync-first with async adapter for Phase 6.**

1. **Phase 3 (now):** All memory module methods are synchronous. Use `sqlalchemy.create_engine()` (sync). The game loop calls `semantic.save_survey()`, `episodic.record_death()`, etc. directly.
2. **Phase 6 (future):** When FastAPI needs async DB access, add `create_async_engine()` with aiosqlite. The memory module gains async wrappers that reuse the same schema and connection.

This avoids premature async complexity. aiosqlite is still installed now (required by Alembic async support and to validate the stack works), but the primary interface is sync. [ASSUMED: this is the right boundary given the sync game loop]

## WAL Mode Configuration

SQLite WAL (Write-Ahead Logging) mode is essential for future Phase 6 when the API reads the DB concurrently with the game loop writing to it.

```python
# Set on database creation, persists across connections
PRAGMA journal_mode=WAL;       # Enable WAL
PRAGMA synchronous=NORMAL;     # Good enough durability for game data
PRAGMA cache_size=-8000;       # 8MB page cache (default is 2MB)
PRAGMA busy_timeout=5000;      # Wait 5s on lock contention
```

WAL mode allows concurrent readers with one writer. SQLite 3.51.1 supports this fully. [VERIFIED: SQLite 3.51.1 on Pi via python3 check]

## Bot Spec Memory Architecture Mapping

The FPS Bot Spec (Section 2.3) describes LSTM/GRU for short-term memory and transformer attention for episodic memory. These are neural architectures for end-to-end learned bots. Our project uses a modular cognitive architecture instead, which maps as follows:

| Bot Spec Concept | Our Implementation | Rationale |
|-----------------|-------------------|-----------|
| Short-Term Memory (LSTM) | WorkingMemory (in-process dataclass + deque) | We don't train neural networks; explicit data structures are more interpretable and debuggable on Pi |
| Long-Term Memory (Episodic, Transformer) | EpisodicMemory (SQLite match_events table) | SQL queries replace attention mechanism for retrieving relevant past events |
| Semantic knowledge (implied) | SemanticMemory (room_surveys + learned_maps + item_locations) | Structured storage is more practical than neural embeddings for map knowledge |

[VERIFIED: Bot Spec Section 2.3 describes LSTM/GRU + transformer approach]

The spec's neural approach is aspirational (v2/ADV scope). For v1, explicit storage with SQL queries achieves the same functional goals -- the bot can remember death locations, recall room layouts, and track item spawns.

## Common Pitfalls

### Pitfall 1: Over-Engineering the Async Layer
**What goes wrong:** Building full async-first memory module when the game loop is sync, leading to `asyncio.run()` calls everywhere.
**Why it happens:** Anticipating Phase 6 too eagerly.
**How to avoid:** Build sync-first. Add async wrappers in Phase 6. The schema and tables are the same either way.
**Warning signs:** `asyncio.run()` or `loop.run_until_complete()` appearing in game loop code.

### Pitfall 2: Putting Working Memory in SQLite
**What goes wrong:** Per-tick DB writes for ephemeral data (current health, recent events) adds latency and wears the SD card.
**Why it happens:** "Everything should be in the database" mindset.
**How to avoid:** WorkingMemory is explicitly an in-process data structure. Only episodic and semantic memories go to DB.
**Warning signs:** `INSERT` statements in the tick hot path, SD card writes every frame.

### Pitfall 3: Breaking Existing Code During Migration
**What goes wrong:** RoomSurveyor.save/load and LearnedMap.save/load stop working when JSON files are removed.
**Why it happens:** Removing old persistence before new persistence is wired up.
**How to avoid:** Phase 3 adds the DB layer alongside JSON. Migration script imports existing data. Then update RoomSurveyor and LearnedMap to use DB. Keep JSON load as fallback until Phase 4.
**Warning signs:** `FileNotFoundError` in room_surveyor.py or learned_map.py during testing.

### Pitfall 4: SQLite JSON Column Performance
**What goes wrong:** Querying inside JSON columns (e.g., "find all surveys with an exit type of 'stairs'") is slow.
**Why it happens:** SQLite JSON support exists but requires json_extract() which doesn't use indexes.
**How to avoid:** For frequently queried fields, extract to regular columns. JSON columns are for bulk storage where the whole blob is loaded. Room survey exits/items are loaded as a whole object, not queried individually.
**Warning signs:** Queries with `json_extract()` in WHERE clauses.

### Pitfall 5: Alembic autogenerate with JSON/BLOB Columns
**What goes wrong:** Alembic's `--autogenerate` produces spurious diffs for JSON and LargeBinary columns because it can't meaningfully diff their contents.
**Why it happens:** SQLAlchemy type comparison is imprecise for these types.
**How to avoid:** Write migrations manually for JSON/BLOB columns. Use autogenerate only as a starting point.
**Warning signs:** Every `alembic revision --autogenerate` shows changes even when nothing changed.

## Code Examples

### Database Initialization and Table Creation
```python
# memory/storage.py
from pathlib import Path
from sqlalchemy import create_engine, text
from .schema import metadata

def create_database(db_path: str) -> 'Engine':
    """Create SQLite database with WAL mode and all tables."""
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{path}", echo=False)

    # Create all tables
    metadata.create_all(engine)

    # Configure pragmas
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA synchronous=NORMAL"))
        conn.execute(text("PRAGMA cache_size=-8000"))
        conn.execute(text("PRAGMA busy_timeout=5000"))
        conn.commit()

    return engine
```

### Semantic Memory: Save/Load Room Survey
```python
# memory/semantic.py
from sqlalchemy import select, insert, update
from .schema import room_surveys

class SemanticMemory:
    def __init__(self, engine):
        self._engine = engine

    def save_survey(self, survey_data: dict) -> None:
        with self._engine.connect() as conn:
            # Upsert: try insert, on conflict update
            stmt = insert(room_surveys).values(**survey_data)
            try:
                conn.execute(stmt)
            except IntegrityError:
                conn.execute(
                    update(room_surveys)
                    .where(room_surveys.c.area_id == survey_data["area_id"])
                    .values(**survey_data)
                )
            conn.commit()

    def get_survey(self, area_id: int, map_name: str = "") -> dict | None:
        with self._engine.connect() as conn:
            stmt = select(room_surveys).where(
                room_surveys.c.area_id == area_id
            )
            if map_name:
                stmt = stmt.where(room_surveys.c.map_name == map_name)
            row = conn.execute(stmt).first()
            return dict(row._mapping) if row else None

    def has_survey(self, area_id: int) -> bool:
        with self._engine.connect() as conn:
            stmt = select(room_surveys.c.id).where(
                room_surveys.c.area_id == area_id
            )
            return conn.execute(stmt).first() is not None
```

### Episodic Memory: Record Match Event
```python
# memory/episodic.py
import time
import uuid
from sqlalchemy import insert, select, func
from .schema import match_events

class EpisodicMemory:
    def __init__(self, engine):
        self._engine = engine
        self._current_match_id = str(uuid.uuid4())

    def record_event(self, event_type: str, position: tuple | None = None,
                     details: dict | None = None, map_name: str = "") -> None:
        with self._engine.connect() as conn:
            conn.execute(insert(match_events).values(
                match_id=self._current_match_id,
                timestamp=time.time(),
                event_type=event_type,
                map_name=map_name,
                position_x=position[0] if position else None,
                position_y=position[1] if position else None,
                position_z=position[2] if position else None,
                details=details or {},
            ))
            conn.commit()

    def get_death_locations(self, map_name: str, limit: int = 50) -> list[dict]:
        with self._engine.connect() as conn:
            stmt = (
                select(match_events)
                .where(match_events.c.event_type == "death")
                .where(match_events.c.map_name == map_name)
                .order_by(match_events.c.timestamp.desc())
                .limit(limit)
            )
            return [dict(row._mapping) for row in conn.execute(stmt)]

    def new_match(self) -> str:
        self._current_match_id = str(uuid.uuid4())
        return self._current_match_id
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| JSON files per room survey | SQLite with JSON columns | This phase | Single file, atomic writes, queryable |
| base64-encoded numpy in JSON | LargeBinary BLOB in SQLite | This phase | 33% smaller, no encode/decode |
| No match history | Episodic memory table | This phase | Bot can learn from death locations |
| Scattered persistence paths | Unified db_path setting | This phase | Single config point |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Sync-first with async adapter in Phase 6 is the right boundary | Sync/Async Boundary | If Phase 6 needs full async from day 1, would need refactor -- LOW risk since interface is the same |
| A2 | numpy tobytes() output is directly compatible with SQLite BLOB via LargeBinary | Grid Binary Storage | If incompatible, would need to keep base64 encoding -- LOW risk, bytes are bytes |
| A3 | SQLite JSON type handles Python dicts/lists transparently via SQLAlchemy | Schema Pattern | If not, would need manual json.dumps -- LOW risk, well-documented SQLAlchemy feature |
| A4 | 64 room surveys + 1 learned map is the complete set of persisted data | Migration Analysis | If there are other JSON/pickle files not discovered, migration would be incomplete -- MEDIUM risk |

## Open Questions

1. **Map name for room surveys**
   - What we know: Room surveys are stored by area_id only, with no map_name field in current JSON files.
   - What's unclear: Should the DB schema require a map_name? The current bot only plays one map (dm4ish).
   - Recommendation: Add map_name column with default "" for current data. Multi-map support is free and prevents future migration.

2. **Image file management**
   - What we know: 640 JPEG images in room_surveys/images/ (10 per survey x 64 surveys).
   - What's unclear: Should image paths be updated to a new location, or stay in place?
   - Recommendation: Keep images where they are. Store paths in DB. When DB is the source of truth, image cleanup can happen later.

3. **Existing code modification scope**
   - What we know: room_surveyor.py and learned_map.py have their own save/load methods.
   - What's unclear: Should Phase 3 modify these files to use DB, or just build the DB layer alongside?
   - Recommendation: Phase 3 builds the memory module and migration script. Update room_surveyor.py and learned_map.py to use SemanticMemory for save/load. Keep JSON as fallback during transition.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | Runtime | Yes | 3.11+ (Pi OS Bookworm) | -- |
| sqlite3 | Database | Yes | 3.51.1 | -- |
| aiosqlite | Async DB (Phase 6 prep) | No (not installed) | -- | Install via uv add |
| SQLAlchemy | Query building | No (not installed) | -- | Install via uv add |
| Alembic | Migrations | No (not installed) | -- | Install via uv add |
| pytest-asyncio | Async tests | No (not installed) | -- | Install via uv add --dev |

**Missing dependencies with no fallback:** None -- all can be installed via uv.

**Missing dependencies with fallback:** None needed -- straightforward package installation.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_memory.py -x` |
| Full suite command | `uv run pytest tests/ -v --tb=short` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEM-01 | DB creation, table existence, WAL mode | unit | `uv run pytest tests/test_memory.py::test_db_creation -x` | No -- Wave 0 |
| MEM-01 | JSON migration imports all 64 surveys | unit | `uv run pytest tests/test_memory.py::test_migration -x` | No -- Wave 0 |
| MEM-02 | WorkingMemory add_event, reset, ring buffer | unit | `uv run pytest tests/test_memory.py::test_working_memory -x` | No -- Wave 0 |
| MEM-03 | EpisodicMemory record_event, get_death_locations | unit | `uv run pytest tests/test_memory.py::test_episodic_memory -x` | No -- Wave 0 |
| MEM-04 | SemanticMemory save/load survey, save/load learned map | unit | `uv run pytest tests/test_memory.py::test_semantic_memory -x` | No -- Wave 0 |
| MEM-05 | Alembic migration creates tables from empty DB | unit | `uv run pytest tests/test_memory.py::test_alembic_migration -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_memory.py -x`
- **Per wave merge:** `uv run pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_memory.py` -- covers MEM-01 through MEM-05
- [ ] `tests/conftest.py` -- add fixture for temp SQLite database (`:memory:` or tmpdir)
- [ ] Package install: `uv add aiosqlite "sqlalchemy>=2.0,<3.0" alembic && uv add --dev pytest-asyncio`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A -- local bot, no users |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A -- single-user local system |
| V5 Input Validation | Yes | Pydantic models for data contracts, SQLAlchemy parameterized queries |
| V6 Cryptography | No | N/A -- no secrets in DB |

### Known Threat Patterns for SQLite

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via f-string queries | Tampering | SQLAlchemy Core parameterized queries -- never use f-strings for SQL |
| DB file corruption from unclean shutdown | Denial of Service | WAL mode + PRAGMA synchronous=NORMAL provides crash recovery |
| Sensitive data in plaintext DB | Information Disclosure | Not applicable -- game bot data has no PII |

## Sources

### Primary (HIGH confidence)
- SQLite documentation on WAL mode and PRAGMAs [CITED: sqlite.org/wal.html]
- Existing codebase analysis: room_surveyor.py, learned_map.py, spatial_map.py, models.py, settings.py [VERIFIED: direct file inspection]
- Existing data files: 64 room surveys in room_surveys/, 1 learned map in ~/.openarena/learned_maps/ [VERIFIED: file counts and structure]
- SQLite version on Pi: 3.51.1 [VERIFIED: python3 -c "import sqlite3; print(sqlite3.sqlite_version)"]
- Project STACK.md research [VERIFIED: aiosqlite >=0.22, SQLAlchemy >=2.0, Alembic >=1.14]

### Secondary (MEDIUM confidence)
- SQLAlchemy 2.0 Core tutorial [CITED: docs.sqlalchemy.org/en/20/core/]
- Alembic tutorial for non-web projects [CITED: alembic.sqlalchemy.org/en/latest/tutorial.html]
- FPS Bot Spec Section 2.3 Memory System [VERIFIED: direct file inspection]

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries verified in prior research, versions confirmed
- Architecture: HIGH -- based on direct inspection of existing persistence code and data files
- Pitfalls: HIGH -- derived from practical SQLite + Python patterns and project-specific sync/async constraints
- Migration: HIGH -- actual data files inspected, schemas documented from real files

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (stable domain, unlikely to change)
