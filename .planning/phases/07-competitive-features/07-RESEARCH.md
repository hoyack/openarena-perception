# Phase 7: Competitive Features - Research

**Researched:** 2026-04-08
**Domain:** Item timing, spawn prediction, sound awareness, multi-timescale decision architecture
**Confidence:** HIGH

## Summary

Phase 7 transforms the bot from a functional player into a competitive deathmatch contender. The four requirements (COMP-01, COMP-02, COMP-03, PERC-08) address the biggest competitive gaps: item control through timing and prediction, 360-degree awareness via sound parsing, and formalizing the already-existing fast/slow decision split into explicit, documented rate boundaries.

The codebase is well-prepared for these additions. Commander already has respawn time constants and item scoring logic. EpisodicMemory and SemanticMemory provide the persistence layer for pickup timestamps. The PerceptionPipeline already implements attention-based rate limiting. The game bridge supports both named pipe commands and RCON queries. The primary technical challenge is parsing Q3 server-side game log (`games.log`) or client console output (`qconsole.log`) for kill, pickup, and sound-related events -- this is the only genuinely new I/O channel being added.

The respawn times in Q3/OpenArena are well-documented in the open-source engine code: Health=35s, Armor=25s, MegaHealth=35s, Powerups=120s, Ammo=40s, Weapons=5s. The Commander class already has these constants (with RESPAWN_MEGA incorrectly set to 120s -- MegaHealth is actually 35s in the source, though OpenArena may differ). The plan should verify against the running game.

**Primary recommendation:** Build an ItemTimingService that wraps Commander's existing item memory with precise pickup timestamps from game log parsing, add a ConsoleLogParser for PERC-08 events, and formalize the multi-timescale boundaries as explicit rate-limiter decorators on existing subsystem tick methods.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| COMP-01 | Item timing -- track pickup timestamps, predict next spawn for MH (35s), RA (25s), Quad (120s) | Commander already has respawn constants and item scoring. Q3 source confirms respawn times. Add ItemTimingService wrapping Commander with precise timestamps from game log. |
| COMP-02 | Spawn prediction -- navigate preemptively to high-value item spawns | Commander._find_best_item already penalizes recently-visited items. Enhance with countdown-based urgency scoring that navigates to item N seconds before predicted respawn. |
| COMP-03 | Multi-timescale decision architecture formalized | PerceptionPipeline already rate-limits sub-modules. TacticalFSM runs at tick rate (~15 Hz). LLMStrategyBrain runs at ~0.25 Hz. Formalize with explicit TimescaleBudget config and rate-limiter wrappers. |
| PERC-08 | Sound awareness -- parse Q3 console output for footsteps, weapon fire, item pickup events | Q3 server logs events in `games.log` with "Kill:", "Item:" prefixes. Client console logs to `qconsole.log` with `logfile 3`. Parse these for 360-degree awareness. |
</phase_requirements>

## Standard Stack

### Core (existing -- no new dependencies needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (re, time, asyncio) | 3.11+ | Log parsing, timing, async coordination | Zero overhead, already in use | [VERIFIED: pyproject.toml]
| SQLAlchemy Core | >=2.0 | Item timing persistence via existing schema | Already in use for memory subsystem | [VERIFIED: pyproject.toml]
| structlog | >=24.0 | Logging for new subsystems | Already in use project-wide | [VERIFIED: pyproject.toml]
| pydantic | >=2.6 | Data models for sound events, item timers | Already in use for all data contracts | [VERIFIED: pyproject.toml]

### No New Dependencies Required

This phase builds entirely on existing infrastructure. No new pip packages needed.

**Installation:** No changes to pyproject.toml required.

## Architecture Patterns

### Recommended Project Structure

```
openarena_perception/
  perception/
    sound_parser.py          # NEW: ConsoleLogParser for PERC-08
  tactics/
    commander.py             # MODIFY: Add item timing integration
    item_timing.py           # NEW: ItemTimingService with spawn prediction
    timescale.py             # NEW: TimescaleBudget config + rate-limiter decorator
  brainstem/
    game_bridge.py           # MODIFY: Add log file reading capability
```

### Pattern 1: Game Log Parsing (PERC-08)

**What:** Parse Q3 server game log for structured events (kills, pickups, sound cues)
**When to use:** Every perception tick (or rate-limited to every N ticks)

The Q3 engine writes a server-side game log when `g_log` is set. The log format is well-documented from the open-source code:

```
# Server-side game log (games.log) format:
# Timestamp Event: client_id data
20:40 Kill: 1022 2 22: <world> killed Isgalamido by MOD_TRIGGER_HURT
20:40 Item: 2 weapon_rocketlauncher
20:42 Item: 2 item_armor_body
21:15 Item: 3 item_health_mega
```

[VERIFIED: Q3 source code on GitHub and multiple Q3 log parser projects]

Additionally, the client-side console can be logged via `logfile 3` cvar which writes `qconsole.log`. Client console shows obituary messages ("PlayerName was railed by OtherPlayer") and can show debug events with `cg_debugEvents 1`.

[VERIFIED: ioquake3 source code cg_event.c on GitHub]

**Recommended approach:** Use the server-side `games.log` (more structured, machine-parseable) rather than client-side `qconsole.log` (human-readable kill messages, less structured). The bot runs its own local server, so the game log is always available.

```python
# Source: Q3 source code g_log format + cg_event.c analysis
import re
import time
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class GameEvent:
    """Parsed event from Q3 game log."""
    timestamp_game: str        # "20:40" game-clock
    timestamp_real: float      # time.time() when parsed
    event_type: str            # "Kill", "Item", "ClientConnect", etc.
    client_id: int
    data: str                  # raw remainder after client_id

# Regex patterns for game log lines
_RE_KILL = re.compile(
    r"(\d+:\d+)\s+Kill:\s+(\d+)\s+(\d+)\s+(\d+):\s+(.*)\skilled\s+(.*)\sby\s+(MOD_\w+)"
)
_RE_ITEM = re.compile(
    r"(\d+:\d+)\s+Item:\s+(\d+)\s+(\S+)"
)

class ConsoleLogParser:
    """Tail-reads Q3 games.log and yields structured events."""
    
    def __init__(self, log_path: str):
        self._path = log_path
        self._offset = 0  # file position for incremental reads
    
    def poll(self) -> list[GameEvent]:
        """Read new lines since last poll. Non-blocking."""
        # Open, seek to offset, read new lines, update offset
        ...
```

### Pattern 2: Item Timing Service (COMP-01, COMP-02)

**What:** Track exact pickup timestamps per item location and predict next spawn
**When to use:** Integrated with Commander decision-making

```python
# Source: Q3 source code g_items.c respawn constants
from dataclasses import dataclass, field
import time

# Verified respawn times from Q3 source (g_items.c)
RESPAWN_TIMES = {
    "weapon": 5.0,      # RESPAWN_WEAPON [VERIFIED: Q3 source]
    "ammo": 40.0,        # RESPAWN_AMMO [VERIFIED: Q3 source]
    "health": 35.0,      # RESPAWN_HEALTH [VERIFIED: Q3 source]
    "armor": 25.0,       # RESPAWN_ARMOR [VERIFIED: Q3 source]
    "mega": 35.0,        # RESPAWN_MEGAHEALTH [VERIFIED: Q3 source]
    "powerup": 120.0,    # RESPAWN_POWERUP (Quad, etc.) [VERIFIED: Q3 source]
    "holdable": 60.0,    # RESPAWN_HOLDABLE [VERIFIED: Q3 source]
}

@dataclass
class ItemTimer:
    """Tracks a single item's respawn cycle."""
    item_name: str           # e.g., "item_health_mega"
    item_category: str       # e.g., "mega"
    position: tuple[float, float, float]
    respawn_seconds: float   # from RESPAWN_TIMES
    last_pickup_time: float = 0.0
    pickup_count: int = 0
    
    @property
    def predicted_spawn_time(self) -> float:
        """When this item will next be available."""
        if self.last_pickup_time == 0.0:
            return 0.0  # never seen picked up, assume available
        return self.last_pickup_time + self.respawn_seconds
    
    @property
    def seconds_until_spawn(self) -> float:
        return max(0.0, self.predicted_spawn_time - time.time())
    
    @property
    def is_available(self) -> bool:
        return self.seconds_until_spawn <= 0.0
```

### Pattern 3: Multi-Timescale Formalization (COMP-03)

**What:** Explicit rate boundaries between subsystem tick rates
**When to use:** Architecture documentation + runtime enforcement

The codebase already implements multi-timescale naturally:
- Perception: 10-22 Hz (PerceptionPipeline.tick) [VERIFIED: pipeline.py]
- Reflexes/Combat: tick rate (~15 Hz via SubsumptionArbiter) [VERIFIED: arbiter.py]
- Tactics/FSM: tick rate (~15 Hz via TacticalFSM) [VERIFIED: fsm.py]
- Strategy/LLM: 0.2-0.25 Hz (~4-5s intervals) [VERIFIED: llm_brain.py, decision_interval=5.0]
- Commander: ~0.33 Hz (DECISION_INTERVAL=3.0s) [VERIFIED: commander.py]

Formalization means:
1. Document these rates as explicit TimescaleConfig
2. Add rate-limiter wrappers that enforce max frequency per subsystem
3. Add metrics (prometheus counters) for actual tick rates per layer

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class TimescaleConfig:
    """Explicit tick rate boundaries per cognitive layer."""
    perception_hz: float = 15.0        # 10-22 Hz, hardware-dependent
    reflex_hz: float = 15.0            # matches perception tick rate
    combat_hz: float = 15.0            # matches perception tick rate
    tactics_hz: float = 15.0           # FSM evaluates every tick
    commander_hz: float = 0.33         # DECISION_INTERVAL = 3s
    strategy_hz: float = 0.2           # LLM every ~5s
    sound_poll_hz: float = 2.0         # log file check 2x/sec (plenty fast)
    item_timing_hz: float = 1.0        # recalculate predictions 1x/sec
```

### Pattern 4: Sound Events to SituationalAwareness

**What:** Add sound awareness fields to the immutable snapshot
**When to use:** Extend SA with new fields for sound-detected threats

```python
# New fields to add to SituationalAwareness dataclass:
# Sound awareness (PERC-08)
sound_events_recent: int = 0            # events parsed this tick
sound_nearby_footsteps: bool = False     # footstep kill/item near us
sound_nearby_combat: bool = False        # weapon fire detected nearby
sound_last_pickup_item: Optional[str] = None  # last item pickup event
sound_last_kill_victim: Optional[str] = None  # last kill victim name
```

### Anti-Patterns to Avoid

- **Over-engineering the log parser:** Do NOT build a full game state reconstruction from logs. Parse only what we need: Item pickups (for timing), kills (for threat awareness), and our own events.
- **Blocking I/O in tick loop:** Log file reads MUST be non-blocking. Use seek-and-read-new pattern, never read entire file. Keep under 1ms per poll.
- **Polling log too frequently:** The game log doesn't update every frame. 2 Hz polling is sufficient -- events don't expire faster than that.
- **Coupling item timing to Commander:** ItemTimingService should be a separate class that Commander consumes, not embedded in Commander's decision logic.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Log file tailing | Custom file watcher with inotify | Simple seek-based polling (read from last offset) | inotify adds unnecessary complexity for a single file read 2x/sec |
| Respawn time database | Custom config file | Hardcoded dict from Q3 source constants | These are engine constants, not user-configurable |
| Rate limiting | Custom frame counter logic | Simple time.time() comparison (already used everywhere) | Pattern already established in Commander.should_decide(), LLMStrategyBrain.should_decide() |
| Event bus for sound events | Pub/sub system | Direct function call from poll -> update SA | Single consumer, single producer -- events don't fan out |

**Key insight:** The competitive features build on well-established patterns already in the codebase. Commander already scores items. The pipeline already rate-limits. The game bridge already communicates via pipe/RCON. The new code is glue, not greenfield.

## Common Pitfalls

### Pitfall 1: MegaHealth Respawn Time Confusion
**What goes wrong:** Commander currently has `RESPAWN_MEGA = 120.0` which treats MegaHealth like a powerup (120s). Q3 source code defines `RESPAWN_MEGAHEALTH = 35` (same as regular health). The 120s is for powerups (Quad Damage, etc.).
**Why it happens:** MegaHealth is often confused with powerups because it's the most valuable health item. Common Q3 wisdom says "Mega respawns in 35 seconds" but some sources cite different values.
**How to avoid:** Verify against the running OpenArena instance. Set `RESPAWN_MEGA = 35.0` per Q3 source, but add a config override in case OpenArena modified it. The Commander's existing constant should be corrected. [VERIFIED: Q3 source g_items.c defines RESPAWN_MEGAHEALTH as 35]
**Warning signs:** Bot arrives at MegaHealth spawn too early or too late consistently.

### Pitfall 2: Game Log Not Enabled
**What goes wrong:** Q3 server doesn't write games.log unless `g_log` cvar is set.
**Why it happens:** Default server config may not enable logging.
**How to avoid:** Set `g_log "games.log"` and `g_logsync 1` (flush every write) in the server config. The game bridge can inject this via RCON at startup: `rcon g_log "games.log"` and `rcon g_logsync 1`. [ASSUMED]
**Warning signs:** ConsoleLogParser.poll() returns empty results every time.

### Pitfall 3: Log File Grows Unbounded
**What goes wrong:** games.log grows indefinitely during long play sessions, eventual disk exhaustion on Pi SD card.
**Why it happens:** No built-in log rotation in Q3 engine.
**How to avoid:** Track file size. When it exceeds a threshold (e.g., 10MB), use `rcon g_log ""` + `rcon g_log "games.log"` to rotate, or truncate the file after reading. Alternatively, use client-side `condump` periodically.
**Warning signs:** Slow log reads, disk space warnings.

### Pitfall 4: Stale Timestamps After Map Change
**What goes wrong:** Item timers become invalid when map changes -- all items reset.
**Why it happens:** Item timing is per-map, but the timer service may not detect map transitions.
**How to avoid:** Reset all ItemTimer entries on map change. Detect map change via RCON `getstatus` (already implemented in GameBridge.get_status()) or via "InitGame:" log line.
**Warning signs:** Bot navigates to item that doesn't exist on the new map.

### Pitfall 5: Client vs Server Event Mismatch
**What goes wrong:** Parsing client console (`qconsole.log`) gives human-readable kill messages like "PlayerName was railed by OtherPlayer" which are locale-dependent and harder to parse than server log "Kill: 3 2 10: ..." format.
**Why it happens:** Client and server use different message formats for the same events.
**How to avoid:** Use server-side `games.log` exclusively. It's machine-parseable with fixed format. The bot runs its own server, so access is guaranteed.
**Warning signs:** Regex fails on unexpected kill message wording.

### Pitfall 6: Sound Event Localization Not Available
**What goes wrong:** Sound events in the log don't include spatial coordinates. We know WHAT happened but not WHERE (beyond the client ID).
**Why it happens:** Q3 server log only records "Item: 2 weapon_rocketlauncher" -- no position data.
**How to avoid:** Cross-reference with known item locations from SemanticMemory. If "Item: 2 item_health_mega" is parsed, look up where mega health spawns on this map. For kills, use last-known enemy position from perception. This gives approximate localization.
**Warning signs:** Sound awareness claims enemy is nearby but position is wrong.

## Code Examples

### Game Log Setup via RCON

```python
# Source: Q3 server cvar documentation [CITED: https://ioquake3.org/help/sys-admin-guide/]
def enable_game_logging(bridge: GameBridge) -> None:
    """Enable server-side game logging for event parsing."""
    bridge.rcon('g_log "games.log"')
    bridge.rcon("g_logsync 1")  # flush every write
```

### Incremental Log Reader

```python
# Source: Standard Python file-tailing pattern
import os

class IncrementalLogReader:
    """Read new lines from a growing log file without re-reading old content."""
    
    def __init__(self, path: str):
        self._path = path
        self._offset = 0
        self._inode = 0  # detect file rotation
    
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
            data = f.read()
            self._offset = f.tell()
        
        return [line for line in data.splitlines() if line.strip()]
```

### Item Timer Integration with Commander

```python
# Source: Analysis of existing commander.py scoring logic
def enhanced_item_score(item: ItemMemory, timer: ItemTimer, 
                         pos: tuple[float, float], now: float) -> float:
    """Score an item considering precise respawn timing."""
    import math
    dist = math.hypot(item.x - pos[0], item.y - pos[1])
    base_score = item.priority * 1000.0 / max(dist, 50.0)
    
    seconds_until = timer.seconds_until_spawn
    
    if seconds_until > 5.0:
        # Item not available yet and won't be soon -- heavy penalty
        base_score *= 0.05
    elif seconds_until > 0.0:
        # Item spawning soon -- boost score based on arrival timing
        # Ideal: arrive just as it spawns
        travel_time = dist / 320.0  # rough Q3 run speed in units/sec
        timing_match = 1.0 - abs(seconds_until - travel_time) / max(seconds_until, 1.0)
        base_score *= max(0.3, timing_match)
    else:
        # Item is available NOW -- full score (already handled by existing logic)
        pass
    
    return base_score
```

## Q3/OpenArena Respawn Times (Verified)

| Item Category | Respawn (seconds) | Source | Q3 Constant | Key Items |
|---------------|-------------------|--------|-------------|-----------|
| Weapon | 5 | Q3 source g_items.c | RESPAWN_WEAPON | Rocket Launcher, Railgun, Lightning Gun |
| Armor | 25 | Q3 source g_items.c | RESPAWN_ARMOR | Red Armor (body), Yellow Armor (combat) |
| Health | 35 | Q3 source g_items.c | RESPAWN_HEALTH | Health (+25), Large Health (+50) |
| MegaHealth | 35 | Q3 source g_items.c | RESPAWN_MEGAHEALTH | Mega Health (+100, overheals) |
| Ammo | 40 | Q3 source g_items.c | RESPAWN_AMMO | Rockets, Shells, Cells, Slugs |
| Holdable | 60 | Q3 source g_items.c | RESPAWN_HOLDABLE | Medkit, Personal Teleporter |
| Powerup | 120 | Q3 source g_items.c | RESPAWN_POWERUP | Quad Damage, Battle Suit, Haste |

[VERIFIED: https://github.com/id-Software/Quake-III-Arena/blob/master/code/game/g_items.c]

**Important note:** The Commander class currently has `RESPAWN_MEGA = 120.0` which is WRONG per Q3 source. MegaHealth uses RESPAWN_MEGAHEALTH (35s), not RESPAWN_POWERUP (120s). This should be corrected in this phase. The requirements doc says MH=35s which matches the Q3 source.

**OpenArena caveat:** OpenArena may have modified some respawn timers from vanilla Q3. The plan should include a verification step against a running OpenArena instance. [ASSUMED]

## Q3 Game Log Format (for PERC-08)

The Q3 server writes structured events to `games.log` when `g_log` is set:

```
# Format: "timestamp EventType: data"
# [VERIFIED: Multiple Q3 log parser projects on GitHub]

# Game lifecycle
0:00 InitGame: \g_gametype\0\mapname\q3dm17\...
0:00 ClientConnect: 0
0:00 ClientUserinfoChanged: 0 n\UnnamedPlayer\t\0\...

# Kill events
20:54 Kill: 1022 2 22: <world> killed Isgalamido by MOD_TRIGGER_HURT
21:07 Kill: 1 2 6: Player1 killed Player2 by MOD_ROCKET

# Item pickup events
20:40 Item: 2 weapon_rocketlauncher
20:42 Item: 2 item_armor_body
21:15 Item: 3 item_health_mega
16:56 Item: 4 weapon_railgun

# Player events
20:34 ClientDisconnect: 2
```

**Events useful for competitive bot:**
- `Item:` -- track who picked up what (item timing for COMP-01)
- `Kill:` -- track deaths for threat awareness, detect our own deaths
- `InitGame:` -- detect map change, reset all timers

**Events NOT available in game log (sound-specific):**
- Footstep sounds -- not logged server-side
- Weapon fire sounds -- only kills are logged, not shots
- Jump pad sounds -- not logged

**Implication for PERC-08:** "Sound awareness" from the game log is limited to kill events and item pickups. True footstep/weapon-fire detection would require either:
1. Client-side `cg_debugEvents 1` which prints event names like "EV_FOOTSTEP" to console [VERIFIED: Q3 source cg_event.c]
2. Audio analysis of game audio output (explicitly rejected as anti-feature in FEATURES.md)

**Recommended approach for PERC-08:** Parse server-side `games.log` for kills and pickups (structured, reliable). Optionally enable `cg_debugEvents 1` on the client and parse `qconsole.log` for EV_FOOTSTEP events (requires `logfile 3`). The footstep approach is lower priority and should be a stretch goal. [ASSUMED]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Commander uses `last_visited` timestamp from bot's own visits | ItemTimingService uses game log pickup timestamps for any player | This phase | Can track enemy pickups, not just own -- much better timing |
| No sound awareness (visual only) | Parse game log for kills/pickups as proxy for sound | This phase | 360-degree awareness of major events beyond screen |
| Implicit multi-timescale (different sleep/interval values) | Explicit TimescaleConfig with documented rates | This phase | Cleaner architecture, easier to tune per hardware |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | OpenArena uses same respawn times as Q3 source | Respawn Times | Item timing predictions would be systematically wrong. Mitigation: verify against running game. |
| A2 | `g_log` and `g_logsync` cvars work in OpenArena | Pitfall 2 | Log parsing approach fails entirely. Fallback: use client-side `qconsole.log` with `logfile 3`. |
| A3 | `cg_debugEvents 1` outputs footstep events to client console | Q3 Game Log Format | PERC-08 footstep detection not possible via log parsing. Fallback: item/kill events only (still valuable). |
| A4 | Game log path is predictable (~/.openarena/baseoa/games.log) | Architecture | Parser can't find the file. Mitigation: make path configurable. |
| A5 | PERC-08 "sound awareness" is satisfied by game log event parsing rather than actual audio processing | Requirements | User may expect actual audio processing. Research confirms FEATURES.md says "Parse game engine text events, not raw audio". |

## Open Questions

1. **Does OpenArena modify Q3 respawn times?**
   - What we know: Q3 source defines exact times. OpenArena is a fork.
   - What's unclear: Whether OpenArena changed any defaults.
   - Recommendation: Add a one-time verification test that measures actual respawn time in-game for MegaHealth and Quad Damage.

2. **What is the exact game log file path in OpenArena?**
   - What we know: Q3 uses `baseq3/games.log`. OpenArena uses `baseoa/`.
   - What's unclear: Whether default path follows `~/.openarena/baseoa/games.log`.
   - Recommendation: Make configurable, default to `~/.openarena/baseoa/games.log`.

3. **Can we identify OUR bot's client ID in the game log?**
   - What we know: GameBridge already tracks `our_name` and `our_client_id` via getstatus.
   - What's unclear: Whether client ID in game log matches the one from getstatus.
   - Recommendation: Cross-reference at startup. Parse `ClientUserinfoChanged` lines to map client IDs to names.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 8.0 + pytest-asyncio >= 0.24 |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `python -m pytest tests/test_item_timing.py tests/test_sound_parser.py tests/test_timescale.py -x` |
| Full suite command | `python -m pytest tests/ -x --tb=short` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COMP-01 | ItemTimer correctly predicts spawn from pickup timestamp | unit | `python -m pytest tests/test_item_timing.py::test_spawn_prediction -x` | Wave 0 |
| COMP-01 | Respawn constants match Q3 source | unit | `python -m pytest tests/test_item_timing.py::test_respawn_constants -x` | Wave 0 |
| COMP-02 | Commander scores items higher when close to respawn | unit | `python -m pytest tests/test_item_timing.py::test_urgency_scoring -x` | Wave 0 |
| COMP-03 | TimescaleConfig enforces documented rate boundaries | unit | `python -m pytest tests/test_timescale.py -x` | Wave 0 |
| PERC-08 | ConsoleLogParser correctly parses Kill and Item lines | unit | `python -m pytest tests/test_sound_parser.py::test_parse_kill -x` | Wave 0 |
| PERC-08 | ConsoleLogParser handles malformed log lines gracefully | unit | `python -m pytest tests/test_sound_parser.py::test_malformed_lines -x` | Wave 0 |
| PERC-08 | IncrementalLogReader only reads new content | unit | `python -m pytest tests/test_sound_parser.py::test_incremental_read -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_item_timing.py tests/test_sound_parser.py tests/test_timescale.py -x`
- **Per wave merge:** `python -m pytest tests/ -x --tb=short`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_item_timing.py` -- covers COMP-01, COMP-02
- [ ] `tests/test_sound_parser.py` -- covers PERC-08
- [ ] `tests/test_timescale.py` -- covers COMP-03

## Security Domain

Not applicable for this phase. All code runs locally on the Pi, parsing local log files. No network input, no user-facing API changes, no authentication changes.

## Sources

### Primary (HIGH confidence)
- [Q3 Source: g_items.c](https://github.com/id-Software/Quake-III-Arena/blob/master/code/game/g_items.c) - Respawn time constants verified
- [Q3 Source: cg_event.c](https://github.com/id-Software/Quake-III-Arena/blob/master/code/cgame/cg_event.c) - Client console event format, CG_Obituary, cg_debugEvents
- [ioquake3 Sys Admin Guide](https://ioquake3.org/help/sys-admin-guide/) - Server cvar documentation
- Existing codebase: commander.py, pipeline.py, fsm.py, llm_brain.py, arbiter.py, game_bridge.py, episodic.py, semantic.py -- all verified via direct file reads

### Secondary (MEDIUM confidence)
- [Multiple Q3 log parser projects](https://github.com/jlgm/QuakeParser) - Confirmed game log format with "Kill:", "Item:" prefixes
- [Q3 Console Commands Wiki](https://quake.fandom.com/wiki/Console_Commands_(Q3)) - logfile, condump, developer cvars
- [OpenArena Wiki](https://openarena.fandom.com/wiki/Special_game_options) - Game options and cvars

### Tertiary (LOW confidence)
- OpenArena-specific respawn times -- not verified against OA source, assumed same as Q3

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies, builds on verified existing code
- Architecture: HIGH - Patterns directly extend existing Commander, Pipeline, FSM patterns
- Respawn times: HIGH for Q3 source values, MEDIUM for OpenArena (may differ)
- Game log parsing: HIGH for format, MEDIUM for footstep events via cg_debugEvents
- Pitfalls: HIGH - derived from Q3 engine analysis and codebase review

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (stable domain -- Q3 engine constants don't change)
