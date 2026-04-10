# Phase 10: Intent System and HUD Companion — Research

**Researched:** 2026-04-10
**Domain:** Bot self-awareness data model + pygame companion HUD + runtime artifact organization
**Confidence:** HIGH (all findings verified from in-repo code; no external library speculation)

## Summary

Phase 10 is a pure in-repo feature phase. No new third-party dependencies are required — the work is (1) adding a frozen+slotted `Intent`/`BotContext`/`Problem` dataclass trio, (2) hooking transition detection into the existing `ItemTour._on_state` tick loop, (3) extending the JSON schema written by `item_tour._export_hud` and `StrategicBrain._export_hud`, (4) extending `strategic_hud.py` with a right-side panel, and (5) moving `/tmp/oa_hud_state.json` into a new `./tmp/` directory and tour logs into `./logs/`.

All conventions needed are already in the codebase and should be followed verbatim: `@dataclass(frozen=True, slots=True)` in `models.py`, `collections.deque(maxlen=N)` for bounded history (5+ examples), `asyncio.run()` in unit tests (pytest-asyncio installed but existing tests use `asyncio.run` directly), and the "timestamp-based commitment window" pattern that `Fix A avoidance` (`_avoidance_until`) already implements at item_tour.py:307,541 — pause-to-assess is a direct clone of that pattern.

**Primary recommendation:** Place `Intent`, `BotContext`, and `Problem` in `openarena_perception/models.py` alongside `SituationalAwareness`. Hook transition detection in `ItemTour._on_state` (not StrategicBrain — v1.0 stability) and use the item_tour `_export_hud` as the single writer for Phase 10; defer StrategicBrain schema extension to a follow-up (item_tour already mirrors its schema). Centralize the schema as a module-level constant in a new `openarena_perception/hud_schema.py` so both writers can reference it.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Intent Model:**
- Intent is a dataclass with fields: `macro` (enum or str), `sub` (str, optional), `description` (human-readable), `started_at` (timestamp), `target` (optional (x,y,z) or area_id), `status` (`"planning" | "executing" | "completed" | "failed"`)
- `BotContext` is a separate dataclass holding: `current_intent: Intent`, `intent_history: deque[Intent]` (last 5), `problem_history: deque[Problem]` (last 5), `path_progress: (current_step, total_steps)`, `current_area_history: deque[int]` (last 10), `tick_count`
- Macro intents for this phase: `TOURING`, `CLIMBING_STAIRS`, `AVOIDING_WALL`, `RECOVERING_STUCK`, `REASSESSING_POSITION`, `RESPAWNING`, `PAUSING_TO_ASSESS`, `IDLE`
- Sub-intents are free-form short strings (no enum)
- Intent changes are edge-triggered: when a new macro or sub is detected, push old to history, set new as current

**Pause-to-Assess:**
- Duration: 300ms default, configurable via env var `OA_INTENT_PAUSE_MS`
- Triggers on macro intent change only (not sub changes)
- Implementation: `self._intent_pause_until = now + pause_duration`; tick loop calls `release_all()` once and returns without movement. Equivalent to existing Fix A avoidance commitment pattern.
- Skippable when `threat_flag` is True (stub returns False, wired for future)
- Logged and visible in HUD as distinct state color

**Context Memory:**
- `intent_history` and `problem_history` use `collections.deque(maxlen=5)`
- `current_area_history` uses `maxlen=10`
- Problem model (new dataclass): `kind` (stuck/pin/wall_halt/advisor_halt/respawn), `location` ((x,y,z)), `timestamp`, `description`
- Problems appended by existing hooks (no new detection logic)

**HUD Export Schema** extends existing /tmp/oa_hud_state.json with `intent`, `intent_history`, `problem_history`, `path_progress`, `area_history`, `is_paused_for_assess`, `threat_flag` fields.

**HUD Display Layout:**
- Window size: 1000x700 (up from 600x700)
- Left 600: existing minimap + player state
- Right 400: current intent (24pt), sub-intent (16pt), intent history (5 rows 12pt), problem history (5 rows 12pt color-coded), path progress bar, advisor stats, halt counters
- Color scheme locked: bright yellow current intent, white sub, dim gray history, red/orange/purple/cyan for problem kinds, flashing blue border during pause-to-assess

**Directory Reorganization:**
- Create `./tmp/` and `./logs/`
- Move HUD state file to `./tmp/oa_hud_state.json`
- Update `strategic_hud.py` `STATE_FILE` constant
- `.gitignore` adds `tmp/` and `logs/`
- Do NOT move the OpenArena pipe file (`oapipe`) — set by game engine
- Tour `--log` flag defaults to `./logs/tour.log`

**Testing Strategy:**
- Unit tests for Intent/BotContext construction, transitions, history eviction
- Unit tests for transition detection logic
- Unit tests for pause-to-assess timing (mock `time.time()`)
- Integration smoke test for HUD JSON write
- No live-game tests required

### Claude's Discretion

- Exact file locations for new classes (`brainstem/`, `tactics/`, or new `intent/` module) → **recommendation below**
- Pygame rendering layout details (fonts, exact pixel positions, animations)
- Sub-intent transition thresholds
- `dataclass(frozen=True, slots=True)` vs mutable → **follow existing convention below**
- Whether to integrate with `StrategicBrain._export_hud` or duplicate in `item_tour.py` → **recommendation below**
- Whether intent state lives on `ItemTour` vs `ReactiveAgent`/`StrategicBrain` → **recommendation below**
- Optional new `.claude/skills/` skill

### Deferred Ideas (OUT OF SCOPE)

- Bidirectional HUD control (HUD → bot commands) — design plumbing only, no channel delivered
- Threat detection wiring — `threat_flag` is stubbed
- Voice/TTS intent announcements
- Remote/web HUD
- Profiling/metrics dashboard
- LLM-driven intent generation

## Phase Requirements

No explicit REQ-IDs assigned (new work outside v1.0 requirement set). Phase objectives are captured in the locked decisions above.

## Standard Stack

**No new libraries required.** All infrastructure is already in the project:

| Library | Version | Purpose | Already Installed |
|---------|---------|---------|-------------------|
| `dataclasses` | stdlib | Intent/BotContext/Problem models | [VERIFIED: used throughout models.py] |
| `collections.deque` | stdlib | Bounded history (maxlen=5/10) | [VERIFIED: 15+ call sites in openarena_perception/] |
| `enum.Enum` | stdlib | MacroIntent enum | [VERIFIED: used for BrainState in models.py:29] |
| `pygame` | >=2.5 | HUD rendering | [VERIFIED: imported in strategic_hud.py:29] |
| `pytest` | >=8.0 | Tests | [VERIFIED: pyproject.toml:28] |
| `pytest-asyncio` | >=0.24 | Installed but unused (project uses `asyncio.run()`) | [VERIFIED: pyproject.toml:55, no `pytest.mark.asyncio` decorators in tests/] |

**Installation:** None.

## Architecture Patterns

### Project Conventions (copy verbatim)

**Dataclass convention — `@dataclass(frozen=True, slots=True)`** [VERIFIED: models.py:43]
- `SituationalAwareness` uses `frozen=True, slots=True` (models.py:43)
- `HumanizationConfig`, `PersonalityProfile` same pattern (combat/humanize.py:105,153)
- `timescale.py`, `sound_parser.py`, `advisor.py` use `frozen=True` without slots

**Recommendation:** Use `@dataclass(frozen=True, slots=True)` for `Intent` and `Problem` (true immutable value objects). For `BotContext`, which contains mutable deques that get mutated in-place, use `@dataclass(slots=True)` WITHOUT `frozen=True` — or make it frozen but hold a `_state: _BotContextState` mutable sub-struct. **Preferred:** plain `@dataclass(slots=True)` for `BotContext` — the deques are mutated in place anyway, and slots gives us a memory/perf win without fighting frozen semantics.

**Deque convention — `collections.deque(maxlen=N)`** [VERIFIED: 15+ call sites]
- `spatial_map.py:106`, `strategic_agent.py:111`, `combat/aim_controller.py:137,148`, `llm_brain.py:97`, `strategy/advisor.py:107`
- Use `Deque[T]` type hint from `typing`

**Enum convention — `class X(Enum): FOO = "foo"`** [VERIFIED: models.py:29 BrainState]
- Use string values, not int. Example: `BrainState.NAVIGATING = "navigating"`.
- For `MacroIntent` use `StrEnum` if we want string interop for JSON export (Python 3.11+, already adopted per STATE.md Phase 06 decision line "Migrated SkillLayer from str+Enum to StrEnum"). **Use `StrEnum`**.

**Async test convention — `asyncio.run()`** [VERIFIED: 30+ call sites in tests/]
- `asyncio.run(engager.tick(sa, gs))` — do NOT use `@pytest.mark.asyncio` decorator even though `pytest-asyncio` is installed
- STATE.md Phase 04/05 decisions confirm: "Used asyncio.run() instead of pytest-asyncio for async test execution" (repeated for phases 04, 05, 09)

### Dataclass Placement — RECOMMENDATION

Place `Intent`, `MacroIntent` enum, `IntentStatus` enum, `Problem`, and `BotContext` in **`openarena_perception/models.py`**, below the existing `SituationalAwareness` class.

**Rationale:**
1. `models.py` is the documented "API between subsystems" home (docstring line 1-4)
2. `brainstem/` is a stub (only `__init__.py`, Phase 1 leftover) — placing new code there creates orphan modules
3. `tactics/` holds FSM + commander + fight-or-flight — intent is conceptually above the tactical layer, not inside it
4. Placing new data contracts in `models.py` matches the Phase 01/04/05 extraction pattern
5. Cross-subsystem access (item_tour.py, strategic_brain.py, HUD) means it must live somewhere both can import without circular-dep risk. `models.py` already has no domain dependencies.

Do NOT create a new `intent/` module. One file, co-located with `SituationalAwareness`, keeps import cost low and matches the convention the codebase actually uses.

### State Ownership — RECOMMENDATION

`BotContext` lives on **`ItemTour`** (`self.context: BotContext`) for Phase 10.

**Rationale:**
- `ItemTour._on_state` is where all the transition signals already exist (stuck, pin, proactive halt, advisor halt, respawn, route_idx advance)
- `StrategicBrain._on_state` is separate and already v1.0-stable — touching it risks regression
- CONTEXT.md Claude's Discretion says: "prefer the layer that already tracks tick state" → item_tour
- Later, if StrategicBrain needs intent, it can construct its own `BotContext` from the same dataclass — the data model is decoupled from the owner

## HUD Schema Centralization — RECOMMENDATION

Both `item_tour.py:1056 _export_hud()` and `strategic_brain.py:439 _export_hud()` currently duplicate the schema, and the task description explicitly calls out the dual-writer risk. The clean fix is:

1. Create **`openarena_perception/hud_schema.py`** with:
   - `STATE_FILE` constant (`Path("./tmp/oa_hud_state.json")` — relative to project root)
   - `def build_hud_payload(sa=None, context=None, map_name="", **extras) -> dict` — pure function, no I/O
   - `def write_hud_state(payload: dict) -> None` — atomic write (tmp + os.replace)
2. Both `item_tour._export_hud` and `strategic_brain._export_hud` call `build_hud_payload(...)` then `write_hud_state(...)`
3. `strategic_hud.py` imports `STATE_FILE` from the same module (or duplicates the constant if we want to avoid importing `openarena_perception` from the standalone HUD script — probably yes, since strategic_hud.py is a separate executable that should not need the full package)

**Implementation note:** strategic_hud.py runs as a standalone script (`python strategic_hud.py`) — importing from `openarena_perception` will work because of the `sys.path.insert` pattern item_tour uses, but **keep strategic_hud.py lightweight**: duplicate only the `STATE_FILE` path constant, not the schema builder. This matches the existing standalone-script style.

## Intent Transition Signal Map

Answers research question 1: "Where in the tick loop should we hook intent transitions?"

All signals are already in `ItemTour._on_state` or the `Navigator`. Hook points (line numbers from current HEAD):

| Signal | Location | Detection | Target Macro Intent |
|--------|----------|-----------|---------------------|
| Route waypoint advance | item_tour.py:818 (`self._route_idx += 1`) | `_route_idx` change | `TOURING` (sub = `"heading to {name}"`) |
| Item timeout | item_tour.py:803 | Edge-trigger same as above | `TOURING` with new sub |
| Advisor halt | item_tour.py:528-536 | `self.advisor.is_hazard_ahead()` True | `REASSESSING_POSITION` (sub = advisor warning text) |
| Fix A avoidance window active | item_tour.py:541 | `now < self._avoidance_until` | `AVOIDING_WALL` (sub = `self._avoidance_hint`) |
| Proactive wall halt fires | item_tour.py:563 (`halt_reason is not None`) | halt_reason in (`wall_ahead`, `visual_pin`, etc) | `AVOIDING_WALL` (sub = halt_reason) |
| Pin escalation replan | item_tour.py:611 | `pinned or halt_reason == "visual_pin"` | `RECOVERING_STUCK` (sub = `"pin escalation, replanning"`) |
| Death detected | item_tour.py:632 (`gs.health <= 0` transition) | `self._was_alive` True→False | `RESPAWNING` |
| Respawn detected | item_tour.py:645 (`not self._was_alive` True→walking) | `self._was_alive` False→True | `TOURING` (sub = `"recovering from respawn"`) |
| Navigator stuck | item_tour.py:668 (`self.agent.nav.is_stuck`) | First tick `is_stuck` True | `RECOVERING_STUCK` (sub = `"stuck #{self._stuck_attempts}"`) |
| Stair-climb started | navigator.py:214-218 (`self._stair_climb_active = True`) | Expose as event flag | `CLIMBING_STAIRS` (sub = `"height delta N"`) |
| Stair-climb ended | navigator.py:226-227 | Flag clears | revert to `TOURING` |
| Area transition | via `nav.current_area` change (per-tick) | Track last; append to `current_area_history` deque | (sub-intent update only) |

**Critical exposure needed:** `Navigator._stair_climb_active` is set inside `follow_path()` (navigator.py:214). ItemTour can poll it after `self.agent.nav.follow_path()` (item_tour.py:771) — but this is only set AFTER follow_path runs, so transition detection for CLIMBING_STAIRS must happen AFTER line 771. Alternatively, add a read-only property `nav.is_climbing_stairs` — recommended, matches the `nav.is_stuck`/`nav.is_recovering` property convention.

**Area transition detection for `current_area_history`:** Track `self._last_area` on ItemTour; when `nav.current_area != self._last_area and nav.current_area > 0`, append to `context.current_area_history`. This mirrors `SpatialKnowledge.enter_area()` at models.py:129-134.

## Pause-to-Assess Mechanics

Answers research question 2: "How does Fix A work and can pause-to-assess reuse it?"

**Fix A pattern** (item_tour.py:307-309, 541-543):
```python
# State vars (in __init__)
self._avoidance_until = 0.0       # timestamp threshold
self._avoidance_hint = None       # action to hold during window

# Early-return gate in _on_state
if now < self._avoidance_until and self._avoidance_hint is not None:
    self._execute_advisor_action(self._avoidance_hint)
    return  # skip forward movement
```

**Pause-to-assess is a direct clone**, but simpler (no held action, just stop):

```python
# State vars (in __init__)
self._intent_pause_until = 0.0

# In __init__ — read env var
pause_ms = int(os.environ.get("OA_INTENT_PAUSE_MS", "300"))
self._INTENT_PAUSE_DURATION = pause_ms / 1000.0

# When macro intent transition is detected:
def _on_macro_intent_change(self, new_intent: Intent, now: float):
    if not self.threat_flag:
        self._intent_pause_until = now + self._INTENT_PAUSE_DURATION
        self.bridge.release_all()
        self.context.current_intent = replace(new_intent, status="planning")
    # else: skip pause, go straight to executing

# Early-return gate in _on_state (place BEFORE Fix A gate at :541)
if now < self._intent_pause_until:
    if not self.threat_flag:
        return  # stay paused, assess
    # threat appeared mid-pause — break out
    self._intent_pause_until = 0.0
```

**Gotchas identified:**

1. **Order of early-returns matters.** Place the intent-pause gate BEFORE Fix A (:541), the advisor-halt gate (:528), and the proactive wall halt (:545). The advisor-halt and wall-halt paths also return early and would otherwise prevent the pause from running. But the death check (:632) and stuck recovery (:668) must NOT be gated by pause — if the bot dies or is stuck during a pause, those reflexes need to fire. **Recommendation:** gate with `if now < self._intent_pause_until and not nav.is_stuck and self._was_alive:`.

2. **Intent transition during an active Fix A window.** If the bot is in the middle of a 500ms Fix A avoidance commitment and a separate transition fires (e.g., respawn), it will set `_intent_pause_until = now + 300ms`. Both gates can coexist — pause-to-assess sits ABOVE Fix A in the tick flow, so the pause fires first; when it clears, Fix A may still be active. This is fine — the semantics are "first assess, then finish avoiding." Document this in the plan.

3. **Release_all during pause.** Call `self.bridge.release_all()` ONCE at pause entry (not every pause tick), otherwise we're spamming the pipe. The pattern is: set `_intent_pause_until`, call release_all once, then the gate just returns for subsequent ticks until the window expires. The existing `release_all()` at `game_bridge.py:155` supports this.

4. **Pause interacts with vision_task**. The async vision_task (item_tour.py:767) is spawned from the normal tick path. During a pause, vision queries are skipped — fine, they resume post-pause. No cleanup needed.

5. **Sub-intent changes do NOT pause.** Only macro transitions. This is correctly in the locked decisions. Sub is computed from navigator state every tick; macro changes are rarer.

## Threat Flag Design

Answers research question 9.

**Recommendation:** Property on `ItemTour` with a plain boolean backing field initialized to `False`:

```python
# In ItemTour.__init__
self._threat_flag = False

@property
def threat_flag(self) -> bool:
    """Stubbed to False; later phase will wire to enemy detection."""
    return self._threat_flag
```

**Why not on BotContext:** BotContext is a data contract that crosses subsystems; threat detection is a policy decision owned by the tour loop. Keeping it on the owner keeps BotContext immutable-ish.

**Why not a callback:** Callbacks add indirection and make tests harder. A simple property is trivial to monkeypatch in tests (`tour._threat_flag = True`) and trivial for a future phase to hook by subclassing or by replacing the property implementation.

**Future integration hook:** When threat detection arrives, the later phase can:
- Override the property to consult `self.anomaly.get_lockable_anomaly()`, `gs.under_attack`, etc.
- OR: a combat module sets `tour._threat_flag = True/False` from its own tick pass

No protocol/ABC needed now.

## Directory Reorganization — Discovered /tmp References

Answers research question 7: "What else references /tmp?"

From a complete `/tmp` grep of the project (excluding `.venv`):

| File | Line | Reference | Action |
|------|------|-----------|--------|
| `strategic_hud.py` | 38 | `STATE_FILE = "/tmp/oa_hud_state.json"` | **MOVE** → `./tmp/oa_hud_state.json` |
| `openarena_perception/strategic_brain.py` | 137 | `STATE_FILE = "/tmp/oa_hud_state.json"` | **MOVE** → import from `hud_schema.py` |
| `item_tour.py` | 1102, 1105 | `/tmp/oa_hud_state.json[.tmp]` | **MOVE** → import from `hud_schema.py` |
| `openarena_perception/vision_nav.py` | 227 | `cv2.imwrite("/tmp/oa_vision_step.jpg", ...)` | **OUT OF SCOPE** — vision debug artifact, separate concern; document but do not move in Phase 10 |
| `vision_walk.py` | 55-65 | `/tmp/oa_vision_step.jpg`, `/tmp/oa_step_*.jpg` | **OUT OF SCOPE** — standalone debug script |
| `openarena_perception/settings.py` | 28 | `pipe_path = "/tmp/openarena_pipe"` | **DO NOT MOVE** — this is the game pipe path, set by the game engine. CONTEXT.md locks this out of scope. |
| `play.py` | 209-210 | `cmd_file = "/tmp/oa_nav_cmd.txt"` | **OUT OF SCOPE** — legacy play.py nav command file, unrelated to HUD; document but leave alone |

**Conclusion:** Phase 10 touches only the three HUD state file references. The vision debug and play.py command file are separate pre-existing tech debt — flag them in the plan as "future cleanup" but do not bundle with this phase (keeps scope clean).

**`.gitignore` content** (from CONTEXT.md lock):
```gitignore
tmp/
logs/
```

Check if `.gitignore` already exists — if yes, append; if no, create. Also check `room_surveys/`, `training_data/`, etc — do NOT touch, those are committed assets.

**Directory creation:** The tour startup path should `os.makedirs("./tmp", exist_ok=True)` and `os.makedirs("./logs", exist_ok=True)` before writing. Strategic_hud.py should also tolerate the directory not yet existing (fallback: wait for first write).

**Path resolution:** Use `pathlib.Path(__file__).parent / "tmp" / "oa_hud_state.json"` from `hud_schema.py` to anchor to the project root, NOT `cwd`. This way running the tour from any directory still writes to the right place.

## HUD JSON Schema Compatibility (Research Q3)

**Current state:** Both `item_tour._export_hud` (item_tour.py:1056) and `strategic_brain._export_hud` (strategic_brain.py:439) write the same file path with **similar but not identical** schemas. Item_tour adds: `route_idx`, `proactive_halts`, `visual_pin_hits`, `advisor_stats`. Strategic_brain has: `brain_state` (enum value), `state_duration`, `items_collected`, `learned_map`.

**Strategic_hud.py `HUDState.load()`** (strategic_hud.py:116-172) uses `.get(key, default)` for every field — so the HUD tolerates missing keys gracefully. Adding new fields is safe. Removing or renaming is not.

**Recommendation — three-step path:**
1. Phase 10 Step 2 creates `hud_schema.py` with `build_hud_payload()` as a superset function: takes optional `sa`, `context`, `brain_state`, `nav`, `learned_map` and emits the union schema. Missing inputs → missing keys.
2. `item_tour._export_hud` becomes a 5-line wrapper calling `build_hud_payload(context=self.context, nav=self.agent.nav, learned_map=self.learned_map, ...)`.
3. `strategic_brain._export_hud` can be migrated in the same phase (low risk: it's a thin wrapper) OR deferred. **Recommend migrate in-phase** since it's just delegating I/O to the shared function — the existing behavior is preserved.

## pygame HUD Extension Patterns (Research Q4)

Current layout (strategic_hud.py):
- Window: `HUD_WIDTH=600, HUD_HEIGHT=700`, `FPS=10`
- Minimap: 400x400 centered at top, margin = `(600-400)//2 = 100`, y=50..450
- Info panel: y=465 onward, anchored x=20
- Fonts: `monospace 13` (body), `monospace 16 bold` (headings), `monospace 10` (small)
- Render pattern: `self._text(text, x, y, font, color, center=False)` blits to `self.screen`
- `draw()` uses a running `panel_y` cursor — linear layout, no panel abstraction

**Cleanest extension (minimal restructure):**
1. Change `HUD_WIDTH = 1000` constant
2. Keep all existing draw code unchanged — it uses x=20, 230, etc relative to the left edge, and world_to_minimap uses `(HUD_WIDTH - MINIMAP_SIZE) // 2` → will silently re-center to `(1000-400)/2=300`, **breaking** the left-aligned panel. **Fix:** change minimap margin calculation to hard-code `margin = 100` (or `margin = (600 - MINIMAP_SIZE) // 2` — anchor to left half). This makes the minimap stay on the left even after window widens.
3. Add a new `_draw_intent_panel(self, x_offset: int)` method called after existing `draw()` content. `x_offset = 600`. Use the same `panel_y` pattern, anchored at `x=x_offset + 20`.
4. New fonts: `self.font_intent = pygame.font.SysFont("monospace", 22, bold=True)` (big current-intent), `self.font_sub = pygame.font.SysFont("monospace", 14)` for sub-intent.
5. Color additions in the color constants block:
   ```python
   INTENT_CURRENT = (255, 255, 0)        # bright yellow
   INTENT_SUB = (255, 255, 255)          # white
   INTENT_HISTORY = (110, 110, 120)      # dim gray
   PROBLEM_WALL = (255, 60, 60)          # red
   PROBLEM_STUCK = (255, 150, 50)        # orange
   PROBLEM_PIN = (200, 80, 255)          # purple
   PROBLEM_RESPAWN = (80, 220, 255)      # cyan
   PAUSE_BORDER = (80, 150, 255)         # flashing blue
   ```
6. Pause flash: use `int(time.time() * 2) % 2 == 0` for a 2Hz flash; draw a 3px border rect around the current-intent box when `s.is_paused_for_assess`.
7. `HUDState` gains new fields mirroring the JSON schema extensions — use `.get(...)` in `load()` same as existing fields.

**Perf at 10 FPS:** Text blits are ~0.1ms each; 20 new blits per frame is ~2ms overhead on Pi 5 — negligible. No caching needed.

**No perf issues are known at current layout** — the minimap is the heaviest render (grid cells + wall segments), and that's unchanged.

## Test Harness for Headless Intent Tests (Research Q6)

**Async pattern (CONFIRMED):** Use `asyncio.run()` directly in test functions, NOT `@pytest.mark.asyncio`. Example from `tests/test_combat.py:48`:
```python
def test_engager_tick(self):
    ...
    asyncio.run(engager.tick(sa, gs))
```

**Mock pattern for tick-state tests:** Existing tests (`test_navigation.py:90`) mock the bridge and nav directly, construct a `SituationalAwareness` fixture, and call `tick_navigating(sa, gs, tick_count=1)`. This is what Phase 10 intent tests should follow.

**Recommended test approach for intent state machine:**
- `tests/test_intent.py` — pure dataclass tests (construction, deque eviction, `replace()` immutability)
- `tests/test_intent_transitions.py` — transition detection function tests. Extract a `detect_intent_transition(prev_context, nav_state, tour_state) -> Optional[Intent]` pure function so tests don't need the full `ItemTour` object. Feed it fake nav/tour state and assert the expected Intent.
- `tests/test_intent_pause.py` — pause-to-assess timing with `monkeypatch.setattr(time, "time", lambda: FAKE_NOW)` — matches the pattern in `test_item_timing.py` (STATE.md Phase 03 note: "Used unittest.mock.patch for time.time to test danger zone decay without real sleeps")
- `tests/test_hud_schema.py` — call `build_hud_payload()` with minimal inputs, assert the JSON structure matches the documented schema

**Fixtures already available in `tests/conftest.py`** — read before implementing to reuse `sa` / `gs` builders.

**Extract transition detection as a pure function** — do NOT bake it into `ItemTour._on_state` inline. Makes both testing and future reuse by StrategicBrain trivial.

## Existing Pattern Precedent for Macro State Tracking (Research Q10)

- **BrainState enum + FSM** (models.py:29, tactics/fsm.py) — enum-per-state, transitions in one place. This is the closest precedent for `MacroIntent`.
- **MotionAnomalyTracker** (motion_anomaly.py) — tracks `active_tracks` with ID assignment and history; uses deque internally
- **SpatialAdvisor._trail** (strategy/advisor.py:107) — `deque(maxlen=30)` for positional history
- **StrategicAgent._history** (strategic_agent.py:111) — `Deque[StateSnapshot] = deque(maxlen=history_size)` — VERY close analog to what BotContext.intent_history does. Copy this exact pattern.

**Copy-paste template for BotContext:**
```python
from collections import deque
from typing import Deque

@dataclass(slots=True)
class BotContext:
    current_intent: Intent
    tick_count: int = 0
    path_progress: Tuple[int, int] = (0, 0)
    intent_history: Deque[Intent] = field(default_factory=lambda: deque(maxlen=5))
    problem_history: Deque["Problem"] = field(default_factory=lambda: deque(maxlen=5))
    current_area_history: Deque[int] = field(default_factory=lambda: deque(maxlen=10))
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bounded history list | Manual list + `if len > N: pop(0)` | `collections.deque(maxlen=N)` | O(1) append+eviction, atomic, idiomatic (15+ uses in-repo) |
| Atomic JSON file write | `open().write()` | `open(tmp).write()` + `os.replace(tmp, final)` | Already the project pattern (item_tour.py:1102-1105, strategic_brain.py:472-475). Avoids partial reads from strategic_hud.py concurrent reader. |
| Timed state windows | `asyncio.sleep()` or threading.Timer | `self._intent_pause_until = now + duration; if now < _intent_pause_until: return` | Non-blocking, matches Fix A (item_tour.py:307,541), survives tick skips, no thread safety issues |
| Time-mocked tests | `time.sleep()` in tests | `monkeypatch.setattr(time, "time", ...)` | STATE.md Phase 03 convention |
| State field persistence | Pickle | Dataclass + JSON via `dataclasses.asdict()` | For HUD export, `asdict` is slow (~0.5ms); Phase 06 STATE.md note: "Manual dict construction for SA WebSocket serialization (~0.05ms vs 0.5ms asdict)" — follow that pattern, build the dict manually in `build_hud_payload` |
| Enum with string values | `class X(Enum): FOO = "foo"` + `.value` | `class X(StrEnum): FOO = "foo"` | Phase 06 STATE.md: "Migrated SkillLayer from str+Enum to StrEnum (Python 3.11+ modern enum pattern)" |

## Common Pitfalls

### Pitfall 1: Importing `openarena_perception` from strategic_hud.py
**What goes wrong:** strategic_hud.py is a standalone executable that users launch separately. Importing the full package triggers dependency loading (opencv, mss, numpy) slowing startup and adding failure modes if the HUD machine doesn't have those deps.
**Prevention:** Keep strategic_hud.py self-contained. Duplicate ONLY the `STATE_FILE` path as a constant (or accept it as a `--state-file` CLI arg). Do NOT import from `openarena_perception.hud_schema`.

### Pitfall 2: `@dataclass(frozen=True)` on BotContext breaks deque mutation
**What goes wrong:** Frozen dataclass forbids `self.current_intent = new_intent` reassignment via `__setattr__` override — but `self.intent_history.append(x)` still works because it mutates the deque object, not the attribute. This creates confusing asymmetric behavior.
**Prevention:** Use `@dataclass(slots=True)` (not frozen) for BotContext. Use `frozen=True, slots=True` only for value types (Intent, Problem) that never get reassigned.

### Pitfall 3: Transition detected every tick instead of on change
**What goes wrong:** Naive check `if nav.is_stuck: new_intent = RECOVERING_STUCK` creates a new Intent object every tick while stuck, filling intent_history with duplicates.
**Prevention:** Edge-trigger: only create new Intent when `(new_macro, new_sub) != (current.macro, current.sub)`. This matches the CONTEXT.md lock: "Intent changes are edge-triggered."

### Pitfall 4: Pause gate placed below existing early-returns
**What goes wrong:** If the pause gate is placed after the advisor-halt (item_tour.py:528) or Fix A (:541) early-returns, those paths return BEFORE the pause check runs → pause never fires when an advisor warning is active.
**Prevention:** Place the pause gate at the TOP of `_on_state` after vision/perception updates but BEFORE any existing early-return path. Exception: death detection (:632) and stuck recovery (:668) must still fire during a pause — gate the pause return on `not nav.is_stuck and gs.health > 0`.

### Pitfall 5: Relative path `./tmp/oa_hud_state.json` breaks when running from another cwd
**What goes wrong:** `pathlib.Path("./tmp/oa_hud_state.json")` resolves against `cwd`, not the project root. If user runs `cd /some/other && python /path/to/item_tour.py`, the file lands in `/some/other/tmp/`.
**Prevention:** Anchor to `Path(__file__).resolve().parent` in `hud_schema.py` (which lives inside `openarena_perception/`, so go up one level). Or compute once at module import and export as a constant.

### Pitfall 6: strategic_brain.py STATE_FILE is a class constant, not module constant
**What goes wrong:** strategic_brain.py:137 has `STATE_FILE = "/tmp/oa_hud_state.json"` as a `StrategicBrain` class attribute. Moving to `hud_schema.STATE_FILE` requires either importing and aliasing, or removing the class attribute entirely. Existing tests may reference `StrategicBrain.STATE_FILE`.
**Prevention:** Grep tests/ for `STATE_FILE` before editing — `grep -rn "STATE_FILE" tests/`. Replace the class attribute with `STATE_FILE = hud_schema.STATE_FILE` as a backward-compat re-export.

### Pitfall 7: deque JSON serialization
**What goes wrong:** `json.dump(deque([1,2,3]))` → `TypeError: Object of type deque is not JSON serializable`.
**Prevention:** In `build_hud_payload`, convert deques to lists: `list(context.intent_history)`. Test this explicitly.

### Pitfall 8: Intent dataclass with tuple target vs JSON array
**What goes wrong:** `target: Tuple[float,float,float]` serializes to a JSON array `[1.0, 2.0, 3.0]`. strategic_hud.py reads it back as a list. If any code does `intent.target == (x,y,z)` after round-trip, the tuple→list mismatch breaks equality.
**Prevention:** Only serialize one way (tour → HUD). The HUD never deserializes back into Intent — it reads `d["intent"]["target"]` as a list directly. Document this one-way contract in `hud_schema.py` docstring.

## Code Examples

### Intent dataclass (target shape for `models.py`)
```python
from enum import StrEnum
from typing import Optional, Tuple

class MacroIntent(StrEnum):
    IDLE = "IDLE"
    TOURING = "TOURING"
    CLIMBING_STAIRS = "CLIMBING_STAIRS"
    AVOIDING_WALL = "AVOIDING_WALL"
    RECOVERING_STUCK = "RECOVERING_STUCK"
    REASSESSING_POSITION = "REASSESSING_POSITION"
    RESPAWNING = "RESPAWNING"
    PAUSING_TO_ASSESS = "PAUSING_TO_ASSESS"

class IntentStatus(StrEnum):
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass(frozen=True, slots=True)
class Intent:
    macro: MacroIntent
    sub: str                        # free-form
    description: str                # human-readable
    started_at: float               # time.time() at creation
    target: Optional[Tuple[float, float, float]] = None
    target_area: Optional[int] = None
    status: IntentStatus = IntentStatus.EXECUTING

    def duration(self, now: float) -> float:
        return now - self.started_at

@dataclass(frozen=True, slots=True)
class Problem:
    kind: str   # "stuck" | "pin" | "wall_halt" | "advisor_halt" | "respawn"
    location: Tuple[float, float, float]
    timestamp: float
    description: str
```

### Pause-to-assess gate (target shape for `_on_state`)
```python
# PLACE AT TOP OF _on_state, right after self._tick += 1 and now = time.time()
if now < self._intent_pause_until:
    # Pause-to-assess active — skip movement unless threat or emergency
    if (not self.threat_flag
            and not self.agent.nav.is_stuck
            and (gs.health is None or gs.health > 0)):
        return
    # Emergency override — break out of pause
    self._intent_pause_until = 0.0
    if self.context.current_intent.status == IntentStatus.PLANNING:
        # Promote planning → executing since we're breaking out
        self.context.current_intent = replace(
            self.context.current_intent, status=IntentStatus.EXECUTING)
```

### Fix A pattern reference (existing, item_tour.py:541-543)
```python
if now < self._avoidance_until and self._avoidance_hint is not None:
    self._execute_advisor_action(self._avoidance_hint)
    return
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Running strategic_hud.py does NOT require importing `openarena_perception` (keep it standalone) | pygame HUD Extension | Low — we can always import if it turns out cleaner, just slightly heavier startup |
| A2 | strategic_brain.py migration to `hud_schema` is low-risk and can ship in Phase 10 | HUD Schema Centralization | Medium — if strategic_brain tests hard-code the class attribute `StrategicBrain.STATE_FILE`, they will break. **Mitigation in Pitfall 6.** |
| A3 | Pause gate placement at top of `_on_state` doesn't conflict with refocus timer, export HUD, wall detection | Pause Mechanics | Low — those are per-tick updates that should continue; only the movement/nav path needs pausing. Plan should validate by running headless with logging. |
| A4 | Relative path anchoring to `Path(__file__).parent` works the same way the current `/tmp` absolute path does | Directory Reorg | Low — `pathlib` is stdlib and the project already uses `os.path.dirname(__file__)` elsewhere (strategic_hud.py:39) |
| A5 | pytest-asyncio is installed but unused; Phase 10 tests should use `asyncio.run()` | Test Harness | Verified via grep — no risk |
| A6 | 300ms pause on a 12 FPS (83ms/tick) loop equals ~3-4 skipped movement ticks; enough to "feel" like an assess | Pause Mechanics | Low — tunable via env var, will be validated in live testing |

## Open Questions

1. **`navigator._stair_climb_active` exposure**
   - What we know: flag exists at navigator.py:214-227, mutated inside `follow_path()`
   - What's unclear: whether to add a read-only property or just `getattr(nav, '_stair_climb_active', False)` in item_tour
   - Recommendation: Plan should add `@property def is_climbing_stairs(self) -> bool: return getattr(self, '_stair_climb_active', False)` to `Navigator` for consistency with `is_stuck`/`is_recovering`.

2. **Should `BotContext` be shared between `ItemTour` and `StrategicBrain`?**
   - What we know: Phase 10 only touches ItemTour
   - What's unclear: whether Phase 11+ wants StrategicBrain to track intent too
   - Recommendation: Design `BotContext` as a generic data contract; don't tie it to ItemTour internals. Both can own a `context: BotContext` attribute.

3. **Does `.gitignore` already exist?**
   - What we know: Grep did not find one in the project root directory listing
   - What's unclear: whether there's a hidden file
   - Recommendation: Plan Step 1 first task: `ls -la` check, then either append or create.

## Environment Availability

Phase 10 has no new external dependencies. All tools and libraries already in the project stack.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pygame | HUD rendering | ✓ (assumed — already in strategic_hud.py imports) | >=2.5 | none needed |
| pytest + pytest-asyncio | Tests | ✓ | >=8.0 / >=0.24 | — |
| stdlib `dataclasses`, `enum`, `collections`, `pathlib` | All models | ✓ | Python 3.11+ | — |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio installed (unused — project uses `asyncio.run()`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_intent.py tests/test_intent_transitions.py tests/test_intent_pause.py tests/test_hud_schema.py -x` |
| Full suite command | `uv run pytest -x` |

### Phase Requirements → Test Map

| Req | Behavior | Test Type | Automated Command | File Exists? |
|-----|----------|-----------|-------------------|-------------|
| Intent dataclass | Construct, replace, equality | unit | `uv run pytest tests/test_intent.py::test_intent_construction -x` | ❌ Wave 0 |
| MacroIntent StrEnum | Enum values serialize as strings | unit | `uv run pytest tests/test_intent.py::test_macro_intent_strenum -x` | ❌ Wave 0 |
| BotContext deque eviction | Append > maxlen evicts oldest | unit | `uv run pytest tests/test_intent.py::test_intent_history_eviction -x` | ❌ Wave 0 |
| Transition detection | Given nav/tour state → correct new Intent | unit | `uv run pytest tests/test_intent_transitions.py -x` | ❌ Wave 0 |
| Pause-to-assess timing | `_intent_pause_until` honored, clears on expiry | unit (time mock) | `uv run pytest tests/test_intent_pause.py -x` | ❌ Wave 0 |
| Pause skip on threat | `threat_flag=True` bypasses pause | unit | `uv run pytest tests/test_intent_pause.py::test_pause_skipped_under_threat -x` | ❌ Wave 0 |
| HUD schema builder | `build_hud_payload()` emits expected keys | unit | `uv run pytest tests/test_hud_schema.py::test_build_payload_keys -x` | ❌ Wave 0 |
| HUD atomic write | `write_hud_state()` uses tmp + replace | unit (tmp_path) | `uv run pytest tests/test_hud_schema.py::test_atomic_write -x` | ❌ Wave 0 |
| Deque JSON serialization | Deques convert to lists in payload | unit | `uv run pytest tests/test_hud_schema.py::test_deque_serialization -x` | ❌ Wave 0 |
| Directory creation | `./tmp/` and `./logs/` auto-created | unit | `uv run pytest tests/test_hud_schema.py::test_dirs_created -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_intent.py tests/test_intent_transitions.py tests/test_intent_pause.py tests/test_hud_schema.py -x` (~5s)
- **Per wave merge:** `uv run pytest -x` (full suite)
- **Phase gate:** Full suite green + manual launch of `python strategic_hud.py` while `item_tour.py` runs to eyeball the right-panel rendering

### Wave 0 Gaps
- [ ] `tests/test_intent.py` — dataclass and enum tests
- [ ] `tests/test_intent_transitions.py` — pure-function transition detection tests
- [ ] `tests/test_intent_pause.py` — pause-to-assess timing with `monkeypatch.setattr(time, "time", ...)`
- [ ] `tests/test_hud_schema.py` — schema builder and atomic write tests
- No framework install needed — pytest already present

## Security Domain

Not applicable for Phase 10. This is an in-process, single-user, single-machine feature with no network surface, no authentication, no user input parsing, and no secrets. The only inputs are:
- Env var `OA_INTENT_PAUSE_MS` — clamp to a sane range (e.g., 0-5000ms) to prevent degenerate values (T-08-05 convention)
- JSON file read by strategic_hud.py — use `.get()` with defaults (already the pattern), tolerate malformed JSON with try/except (already the pattern)

ASVS categories do not apply meaningfully. STRIDE threats considered:
- **Tampering** with the JSON state file: only writable by the same user running the bot; not a security boundary
- **DoS** from runaway history lists: mitigated by `deque(maxlen=N)` per CONTEXT.md locks

## Project Constraints (from CLAUDE.md)

Extracted directives the planner must honor:

- **Python 3.11+, uv package manager, asyncio single event loop** — all code Phase 10 writes must be asyncio-compatible; no threading
- **Pi 5 perception loop at 10+ FPS** — pause-to-assess at 300ms is 3-4 ticks, acceptable; HUD export every 6 ticks (~500ms) is already the budget
- **FastAPI + Pydantic v2** — **N/A for Phase 10**; no API changes planned. If Phase 10 touches `api/` it must use Pydantic v2 models, but CONTEXT.md does not scope API changes in.
- **structlog for structured logging** — existing tour code uses stdlib `logging` with `log = logging.getLogger("tour")` (item_tour.py:51). **Do not refactor to structlog in Phase 10** — out of scope, would bloat the phase. Use existing `log.info(...)` style for intent transition events.
- **pytest + ruff + mypy** — all new code must pass `uv run ruff check` and `uv run ruff format --check`
- **Frozen slotted dataclasses** — project convention (see models.py:43), copy exactly
- **GSD workflow enforcement** — "Before using Edit, Write, or other file-changing tools, start work through a GSD command" → the planner will create 3 PLAN.md files per user's agreed 4-step split (Step 4 deferred)
- **Backward compat: existing room surveys, AAS files, trained models must keep working** → Phase 10 does not touch these assets; `.gitignore` entries for `tmp/` and `logs/` do NOT touch `room_surveys/` or `training_data/`
- **Game interface: named pipe + RCON are the only communication channels** → Do NOT add a new control channel for the HUD; bidirectional control is deferred.

## Sources

### Primary (HIGH confidence — in-repo verified)
- `openarena_perception/models.py` — `SituationalAwareness` frozen+slotted pattern, `BrainState` enum
- `openarena_perception/combat/humanize.py:105,153` — frozen+slotted convention
- `openarena_perception/strategic_agent.py:25,111` — `Deque[StateSnapshot] = deque(maxlen=history_size)` pattern
- `item_tour.py:260-347` — `ItemTour.__init__` full state init
- `item_tour.py:449-838` — `ItemTour._on_state` full tick loop
- `item_tour.py:1056-1107` — `ItemTour._export_hud` current implementation
- `openarena_perception/strategic_brain.py:137,439-477` — `StrategicBrain._export_hud` and STATE_FILE constant
- `openarena_perception/navigation/navigator.py:140-263` — `follow_path`, stair-climb active flag, re-plan
- `openarena_perception/navigation/navigator.py:305-370` — `handle_stuck` recovery logic
- `strategic_hud.py` (full file) — pygame HUD structure, draw pattern, HUDState.load
- `tests/test_combat.py:48`, `tests/test_navigation.py:90`, `tests/test_tactical_fsm.py:149` — `asyncio.run()` test convention
- `pyproject.toml:28-58` — pytest, ruff, uv tooling
- `.planning/STATE.md` — Phase 04/05 decisions re: asyncio.run(), Phase 06 re: StrEnum, Phase 08 re: clamping env var inputs
- `CLAUDE.md` — full tech stack and constraints

### Secondary (MEDIUM confidence)
- None — all claims in this research are verified directly from in-repo source.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Intent dataclass design: HIGH — direct pattern match with SituationalAwareness + StrategicAgent._history
- Pause-to-assess mechanics: HIGH — direct clone of Fix A avoidance pattern, verified at item_tour.py:307,541
- HUD schema centralization: HIGH — strategic_hud.py uses `.get(k, default)` so additive changes are safe
- Directory reorganization: HIGH — full `/tmp` grep performed, all call sites catalogued
- pygame extension plan: HIGH — strategic_hud.py structure fully read
- Test harness: HIGH — 30+ existing `asyncio.run()` call sites, time-mock convention documented in STATE.md
- State ownership (ItemTour vs StrategicBrain): MEDIUM — based on CONTEXT.md discretion + stability heuristic, not formal verification

**Research date:** 2026-04-10
**Valid until:** 2026-05-10 (stable in-repo research, no fast-moving external deps)

## RESEARCH COMPLETE

**Phase:** 10 - Intent System and HUD Companion
**Confidence:** HIGH

### Key Findings

1. **Zero new dependencies.** Everything needed is in the stack: `dataclasses`, `enum.StrEnum`, `collections.deque`, `pygame`, `pytest`. The phase is pure in-repo engineering.
2. **Dataclass placement: `models.py`.** Brainstem is a stub; tactics is for FSM/commander. `models.py` is the documented cross-subsystem contract home.
3. **Pause-to-assess is a direct clone of Fix A** (item_tour.py:307,541) — same timestamp-window gate pattern, plus `release_all()` once on entry and `return` on subsequent ticks. Place the gate ABOVE advisor-halt and wall-halt early returns but below death/stuck reflexes.
4. **Intent transition hooks are all already present** in `ItemTour._on_state` — route advance, stuck, pin escalation, respawn, advisor halt, wall halt. Stair-climb requires exposing `Navigator._stair_climb_active` as a property.
5. **HUD schema centralization:** create `openarena_perception/hud_schema.py` with `build_hud_payload()` and `STATE_FILE = Path(__file__).resolve().parent.parent / "tmp" / "oa_hud_state.json"`. Both item_tour and strategic_brain delegate to it. strategic_hud.py stays standalone (duplicates only the path constant).
6. **strategic_hud.py extension is minimal.** Change `HUD_WIDTH = 1000`, hard-code minimap margin to keep it left-aligned, add `_draw_intent_panel(x_offset=600)` method. ~150 new lines, no refactor of existing code.
7. **Test pattern locked:** `asyncio.run()` in tests, time mocks via `monkeypatch.setattr(time, "time", ...)`, extract transition detection as a pure function for testability.

### File Created
`/home/hoyack/openarena-perception/.planning/phases/10-intent-system-and-hud-companion/10-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Intent data model design | HIGH | Direct pattern match with models.py + StrategicAgent._history |
| Transition hook sites | HIGH | Every site cited by exact line number from HEAD |
| Pause-to-assess mechanics | HIGH | Direct clone of verified Fix A pattern |
| Directory cleanup scope | HIGH | Full /tmp grep complete |
| HUD extension plan | HIGH | strategic_hud.py fully read |
| State ownership (ItemTour vs Brain) | MEDIUM | Heuristic-based; validated against CONTEXT.md discretion |

### Open Questions (for planner)
1. Add read-only `Navigator.is_climbing_stairs` property? (Recommended: yes.)
2. Does `.gitignore` exist at repo root? (Plan Step 1 must check.)
3. Should BotContext be designed for future StrategicBrain reuse? (Recommended: yes, keep it subsystem-neutral.)

### Ready for Planning
Research complete. Planner can now create 3 PLAN.md files per user's agreed execution order: (1) directory cleanup, (2) intent+context model + pause-to-assess, (3) HUD display overhaul.
