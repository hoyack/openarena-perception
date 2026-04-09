"""Game log parser for event awareness (PERC-08).

Parses Q3/OpenArena server-side game log (games.log) for structured events:
kills, item pickups, map changes. Provides 360-degree event awareness
beyond what visual perception can offer.

The server writes events in a fixed format:
    ``20:40 Kill: 1 2 6: Player1 killed Player2 by MOD_ROCKET``
    ``20:40 Item: 2 weapon_rocketlauncher``
    ``0:00 InitGame: \\g_gametype\\0\\mapname\\q3dm17\\...``

Uses seek-based incremental reading to avoid re-reading old content.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_READ_BYTES = 65536  # T-07-02: cap per-poll read to 64KB

# Compiled regex patterns for Q3 game log line formats
_RE_KILL = re.compile(
    r"(\d+:\d+)\s+Kill:\s+(\d+)\s+(\d+)\s+(\d+):\s+(.+)\skilled\s+(.+)\sby\s+(MOD_\w+)"
)
_RE_ITEM = re.compile(r"(\d+:\d+)\s+Item:\s+(\d+)\s+(\S+)")
_RE_INITGAME = re.compile(r"(\d+:\d+)\s+InitGame:")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GameEvent:
    """Parsed event from Q3 game log.

    Frozen dataclass -- immutable after creation.
    """

    timestamp_game: str  # e.g., "20:40"
    timestamp_real: float  # time.time() when parsed
    event_type: str  # "Kill", "Item", "InitGame"
    client_id: int  # -1 for InitGame
    data: str  # raw remainder after event prefix

    # Kill-specific fields
    killer_id: int = -1
    victim_id: int = -1
    means_of_death: str = ""

    # Item-specific fields
    item_name: str = ""


# ---------------------------------------------------------------------------
# Incremental log reader
# ---------------------------------------------------------------------------


class IncrementalLogReader:
    """Read new lines from a growing log file without re-reading old content.

    Uses ``os.stat()`` to detect file rotation (inode change or smaller size)
    and resets the offset automatically.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._offset = 0
        self._inode = 0

    def read_new_lines(self) -> list[str]:
        """Return new lines since last call. Non-blocking, O(new_bytes)."""
        try:
            stat = os.stat(self._path)
        except FileNotFoundError:
            return []

        # Detect file rotation (new file with different inode or smaller size)
        if stat.st_ino != self._inode or stat.st_size < self._offset:
            self._offset = 0
            self._inode = stat.st_ino

        if stat.st_size == self._offset:
            return []  # no new data

        with open(self._path, "r", errors="replace") as f:
            f.seek(self._offset)
            data = f.read(_MAX_READ_BYTES)
            self._offset = f.tell()

        return [line for line in data.splitlines() if line.strip()]

    def reset(self) -> None:
        """Reset offset to re-read from the beginning."""
        self._offset = 0
        self._inode = 0


# ---------------------------------------------------------------------------
# Console log parser
# ---------------------------------------------------------------------------


class ConsoleLogParser:
    """Tail-reads Q3 games.log and yields structured GameEvents.

    Create one instance per log file. Call ``poll()`` periodically
    (e.g., 2 Hz) to get new events since the last poll.
    """

    def __init__(self, log_path: str) -> None:
        self._reader = IncrementalLogReader(log_path)

    def poll(self) -> list[GameEvent]:
        """Read new lines, parse each with regex, return structured events."""
        lines = self._reader.read_new_lines()
        events: list[GameEvent] = []
        now = time.time()

        for line in lines:
            evt = self._parse_line(line, now)
            if evt is not None:
                events.append(evt)

        return events

    def reset(self) -> None:
        """Reset reader offset. Useful on map change."""
        self._reader.reset()

    # -- internal ----------------------------------------------------------

    @staticmethod
    def _parse_line(line: str, now: float) -> GameEvent | None:
        """Parse a single log line into a GameEvent, or None if unrecognised."""
        # Kill event
        m = _RE_KILL.match(line)
        if m:
            return GameEvent(
                timestamp_game=m.group(1),
                timestamp_real=now,
                event_type="Kill",
                client_id=int(m.group(2)),
                data=line,
                killer_id=int(m.group(2)),
                victim_id=int(m.group(3)),
                means_of_death=m.group(7),
            )

        # Item event
        m = _RE_ITEM.match(line)
        if m:
            return GameEvent(
                timestamp_game=m.group(1),
                timestamp_real=now,
                event_type="Item",
                client_id=int(m.group(2)),
                data=line,
                item_name=m.group(3),
            )

        # InitGame event
        m = _RE_INITGAME.match(line)
        if m:
            return GameEvent(
                timestamp_game=m.group(1),
                timestamp_real=now,
                event_type="InitGame",
                client_id=-1,
                data=line,
            )

        # Unrecognised line -- silently skip
        return None
