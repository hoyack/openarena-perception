# Phase 10: Intent System and HUD Companion — Context

**Gathered:** 2026-04-10
**Status:** Ready for planning
**Source:** Session conversation (post-milestone feature work, captured inline rather than via discuss-phase)

<domain>
## Phase Boundary

This phase delivers **bot self-awareness and developer observability**. Three user-visible outcomes:

1. **The bot knows what it is trying to do** — not just "walk forward" but "heading to mega health", "climbing stairs to reach it", "exiting room through the door", "avoiding wall", "reassessing position after pin". Intent is explicit, named, timestamped, and transitions are logged.

2. **The developer can see what the bot thinks** — a companion HUD window renders current intent, sub-intent, intent history (last N transitions), problem history (stuck/pin/halt events), path progress, area history, advisor stats, and other brain context in real time.

3. **The runtime is observable and organized** — instead of polluting `/tmp`, the bot writes to `./tmp/` and `./logs/` in the project directory, with `.gitignore` excluding them. Session tour logs and HUD state files go to these dirs.

A fourth outcome is **teed up but not delivered this phase**: the HUD becomes a bidirectional control surface (HUD → bot commands). Plumbing is scoped so a later phase can add control without architectural rework.

## What's in scope

- A new `BotContext` / `Intent` data model (dataclass or pydantic) that lives in `tactics/` or `brainstem/` and is updated per tick by the tour/strategic-brain loop
- Intent transition hooks in `item_tour.py` and optionally `strategic_brain.py` (if feasible without destabilizing v1.0 work)
- **Pause-to-assess**: a short stop (200-500ms, tunable) before starting a new macro intent, skippable when a `threat_flag` is set (no-op for now, wired for future integration with enemy detection)
- HUD JSON export schema extended with intent + context fields; `strategic_hud.py` reads and renders them
- New HUD panel layout: left side = existing minimap; right side = intent/context panel
- Directory reorganization: create `./tmp/`, `./logs/`, move HUD state file, tour log file, add `.gitignore`
- Unit tests for intent state machine and transitions (pure Python, no game loop required)

## What's out of scope

- **Bidirectional HUD control** (HUD → bot commands) — plumbing should be considered in the design but no command channel is delivered this phase
- **Threat detection wiring** — the `threat_flag` hook is just a stub that always returns False; real threat integration waits for multi-player testing
- **Voice/TTS intent announcements** — the user mentioned wanting to *see* intent, not hear it; no audio output
- **Any changes to the AAS parser, navigator pathfinding, or vision pipeline** beyond what's needed to expose state to the HUD
- **Retroactive intent labeling for past events** — intent only tracks the *current* action and forward history; no backfilling
- **Multi-bot observability** — single bot only
- **Web/remote HUD** — pygame desktop window only, same machine as game

</domain>

<decisions>
## Implementation Decisions

### Intent Model

- **Intent is a dataclass** with fields: `macro` (enum or str), `sub` (str, optional), `description` (human-readable), `started_at` (timestamp), `target` (optional (x,y,z) or area_id), `status` ("planning" | "executing" | "completed" | "failed")
- **BotContext** is a separate dataclass holding: `current_intent: Intent`, `intent_history: deque[Intent]` (last 5), `problem_history: deque[Problem]` (last 5), `path_progress: (current_step, total_steps)`, `current_area_history: deque[int]` (last 10), and `tick_count`
- **Macro intents** for this phase: `TOURING` (default when walking to a route waypoint), `CLIMBING_STAIRS`, `AVOIDING_WALL`, `RECOVERING_STUCK`, `REASSESSING_POSITION`, `RESPAWNING`, `PAUSING_TO_ASSESS`, `IDLE`
- **Sub-intents** are free-form short strings (e.g., `"exiting through door"`, `"crossing swim edge"`, `"strafing right off corner"`) — no enum, so we can add new observations without a refactor
- Intent changes are **edge-triggered**: when the tick loop recognizes a transition (new macro or new sub), it creates a new Intent, pushes the old one to history, and sets `current_intent = new`

### Pause-to-Assess

- **Duration: 300ms default** (configurable via env var `OA_INTENT_PAUSE_MS`)
- **Triggers on macro intent change only**, not sub-intent changes (too frequent otherwise)
- **Implementation**: set `self._intent_pause_until = now + pause_duration`; while inside the window, the tick loop calls `release_all()` once and returns without issuing movement commands. This is equivalent to the existing Fix A avoidance commitment pattern.
- **Skippable when `threat_flag` is True** — `threat_flag` is a property on the tour/agent that returns False for now but is wired so a future phase can hook it to enemy detection
- **Logged** so we can see pause events in the log stream, and **visible in HUD** as a distinct state color

### Context Memory

- `intent_history` and `problem_history` use `collections.deque(maxlen=5)` for O(1) append and automatic eviction
- `current_area_history` uses `maxlen=10` to show recent area transitions (helps debug when the bot thinks it's in area 309 but is actually in 619)
- **Problem model** (new dataclass): `kind` (stuck/pin/wall_halt/advisor_halt/respawn), `location` ((x,y,z)), `timestamp`, `description`
- Problems are appended by existing hooks (stuck recovery, proactive wall halt, pin escalation, advisor halt) — we don't create new detection logic

### HUD Export Schema (extends existing)

New fields added to `/tmp/oa_hud_state.json` → `./tmp/oa_hud_state.json`:

```json
{
  // existing fields preserved...
  "intent": {
    "macro": "TOURING",
    "sub": "heading to item_health_mega",
    "description": "Heading to item_health_mega",
    "started_at": 1234567890.0,
    "duration_s": 2.3,
    "target": [232, 1600, -112],
    "status": "executing"
  },
  "intent_history": [
    {"macro": "AVOIDING_WALL", "sub": "strafing right", "duration_s": 0.8, "ended_at": 1234567889.5},
    // ...
  ],
  "problem_history": [
    {"kind": "wall_halt", "location": [481, 1336, -93], "description": "vision score=0.89", "timestamp": 1234567889.0},
    // ...
  ],
  "path_progress": {"current_step": 5, "total_steps": 13},
  "area_history": [299, 259, 285, 304, 325],
  "is_paused_for_assess": false,
  "threat_flag": false
}
```

### HUD Display Layout

- **Window size: 1000x700** (up from 600x700) to fit new right-side panel
- **Left panel (existing)**: 600-wide minimap + player state rows (health, armor, pos, etc.)
- **Right panel (new, 400-wide)**: 
  - Top: **Current Intent** — big text (24pt), macro + description, duration timer
  - Middle: **Sub-intent** (16pt), time on sub
  - Below middle: **Intent History** (5 rows, 12pt, scrolling)
  - Bottom: **Problem History** (5 rows, 12pt, color-coded by kind)
  - Footer: Path progress bar (step N/M), advisor stats (sent/complete/failed), halt counters
- **Color scheme**: 
  - Current intent: bright yellow
  - Sub-intent: white
  - History: dimmed gray
  - Problems: red (wall_halt), orange (stuck), purple (pin), cyan (respawn)
  - Pause-to-assess indicator: flashing blue border on current intent box

### Directory Reorganization

- Create `./tmp/` — runtime state files (HUD state, any future control channel, temp captures)
- Create `./logs/` — tour logs, advisor logs if separated, HUD crash logs
- Move HUD state file: `/tmp/oa_hud_state.json` → `./tmp/oa_hud_state.json`
- Update `strategic_hud.py` `STATE_FILE` constant
- Add `.gitignore` with:
  ```
  tmp/
  logs/
  ```
- **Do NOT move the OpenArena pipe file** (`oapipe`) — that's set by the game engine, outside our control
- Tour script CLI flag `--log <path>` defaults to `./logs/tour.log`

### Testing Strategy

- Unit tests for `Intent` and `BotContext` dataclasses (construction, transitions, history eviction)
- Unit tests for intent transition detection logic (given tick state, does the right new intent fire?)
- Unit tests for pause-to-assess timing (mock `time.time()`, verify the pause window is respected and cleared correctly)
- Integration smoke test: run a mock tick loop, verify HUD JSON is written with the expected schema
- No live-game tests required for this phase — everything can be tested headless

### Claude's Discretion

- Exact file locations for new classes (`brainstem/`, `tactics/`, or a new `intent/` module)
- Pygame rendering layout details (fonts, exact pixel positions, animations)
- Threshold tuning for when sub-intents transition (vs. staying on the same sub)
- Whether to use `dataclass(frozen=True, slots=True)` or mutable dataclasses — follow existing project convention found in code
- Whether to integrate with `StrategicBrain`'s existing `_export_hud` or duplicate the export in `item_tour.py` — prefer DRY if feasible
- Whether intent state lives on `item_tour.py`'s `ItemTour` class or on `ReactiveAgent`/`StrategicBrain` — prefer the layer that already tracks tick state
- Whether to add a new `./.claude/skills/` skill for this phase's test pattern — optional

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Instructions
- `CLAUDE.md` — project-level instructions, tech stack (asyncio, pydantic, structlog, pytest), hardware constraints (Pi 5, 10+ FPS target), GSD workflow enforcement

### Existing HUD and Brain Infrastructure
- `strategic_hud.py` — existing pygame HUD, `STATE_FILE = "/tmp/oa_hud_state.json"`, reads and renders minimap + player state from JSON every 100ms (FPS=10)
- `openarena_perception/strategic_brain.py` — `_export_hud()` method (line 439) writes the HUD JSON schema every 6 ticks; `STATE_FILE = "/tmp/oa_hud_state.json"` at line 137
- `item_tour.py` — post-milestone tour script with `_export_hud()` added this session (mirrors StrategicBrain schema); this is where new intent tracking code will likely live

### Navigation State (intent transition sources)
- `openarena_perception/navigation/navigator.py` — stuck detection, stair-climb start events, path re-plans; these are intent transition signals
- `openarena_perception/navigation/learned_map.py` — occupancy grid, area transitions

### Existing Dataclass Conventions
- `openarena_perception/models.py` — `SituationalAwareness` frozen slotted dataclass pattern; new Intent/BotContext should follow this convention

### Session Baseline
- Commit `6a0fa26` — proactive wall halt, pin detection, visual pin, HUD export in item_tour.py (this is the baseline Phase 10 builds on)
- Commit `9f8f46e` — advisor request_diagnosis force dispatch

### GSD Tech Stack Reference
- `CLAUDE.md` Technology Stack section — pydantic v2 dataclasses, structlog for structured logging, pytest for tests, ruff/mypy for quality

</canonical_refs>

<specifics>
## Specific Ideas

### User's explicit requests (from session conversation)

1. "I would like to see [the bot's] intent in the companion window"
2. "If it is in a room and intends to exit the room or stay in the room, I would like to see that intent"
3. "'Exiting room through the door' or 'going up the stairs' so that i know if it is achieving it's intent"
4. "or if it's walking into a wall while it thinks it's running up stairs"
5. "I want the bot to stop and assess it's next action and pause for intent if it's not under threat"
6. "We will be adding threats in later when other players join the game"
7. "I also want tmp assets to be posted to a tmp folder here and logs to be posted to a logs folder here in this dir"
8. "I want a .gitignore to ignore the files in those directories"
9. "I want to be able to see what's going on better"
10. "I also want better context memory for the brain, because it's got multiple things it's tracking and I want to see all those things in the companion app represented"
11. "I want the companion app to be a HUD for the bot that ultimately can be used to control it"

### Proposed 4-step execution order (agreed in session)

1. **Step 1** — Directory cleanup (tmp/, logs/, .gitignore, update STATE_FILE paths)
2. **Step 2** — Intent + context model (dataclasses, transition hooks, pause-to-assess, JSON export extension)
3. **Step 3** — HUD display overhaul (new right-side panel, color coding, history lists)
4. **Step 4** — Bidirectional control (DEFERRED to a later phase; this phase just ensures the plumbing doesn't preclude it)

Planner should produce 3 PLAN.md files for Steps 1-3 (Step 4 is out of scope).

</specifics>

<deferred>
## Deferred Ideas

- **Bidirectional HUD control** — HUD → bot commands (pause/resume, skip waypoint, manual nav) — plumbing considered in design but no command channel delivered
- **Threat integration** — `threat_flag` hook stubbed to False; real integration waits for multi-player testing
- **Voice/TTS announcements** — user explicitly wants visual, not audio
- **Remote/web HUD** — pygame desktop only
- **Profiling/metrics dashboard** — separate from the intent HUD; could be a later phase
- **LLM-driven intent generation** — the advisor could eventually supply its own intent strings, but this phase uses rule-based transition detection

</deferred>

---

*Phase: 10-intent-system-and-hud-companion*
*Context gathered: 2026-04-10 via session conversation (slight deviation from standard discuss-phase flow — user explicitly approved this path)*
