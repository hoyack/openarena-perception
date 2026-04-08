"""Database engine factory with WAL mode configuration.

Provides sync SQLite engine creation with WAL journal mode for safe
concurrent access from the game loop and future API layer.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text

from openarena_perception.memory.schema import metadata

# Module-level engine cache keyed by resolved path
_engine_cache: dict[str, Engine] = {}


def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    """Set SQLite PRAGMAs on every new connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-8000")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def create_database(db_path: str) -> Engine:
    """Create a new SQLite database with WAL mode and all tables.

    Expands ``~`` in *db_path*, creates parent directories, initialises all
    tables defined in :pydata:`schema.metadata`, and sets performance PRAGMAs.

    Args:
        db_path: Filesystem path to the SQLite database file.

    Returns:
        A configured :class:`sqlalchemy.engine.Engine`.
    """
    path = Path(db_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{path}", echo=False)

    # Attach PRAGMA listener before any connections are made
    event.listen(engine, "connect", _set_sqlite_pragmas)

    # Create all tables
    metadata.create_all(engine)

    return engine


def get_engine(db_path: str) -> Engine:
    """Return a cached engine for *db_path*, creating one if needed.

    Engines are cached by their resolved absolute path so that multiple
    callers sharing the same database file share a single engine instance.
    """
    key = str(Path(db_path).expanduser().resolve())
    if key not in _engine_cache:
        _engine_cache[key] = create_database(db_path)
    return _engine_cache[key]
