---
phase: 10-intent-system-and-hud-companion
plan: 02
subsystem: intent
tags: [feature, intent, pause-to-assess, hud, dataclasses, tdd]
requires:
  - 10-01 (hud_schema centralization)
provides:
  - openarena_perception.models.MacroIntent (StrEnum, 8 members)
  - openarena_perception.models.IntentStatus (StrEnum)
  - openarena_perception.models.Intent (frozen+slots dataclass)
  - openarena_perception.models.Problem (frozen+slots dataclass)
  - openarena_perception.models.BotContext (slots, mutable -- holds deques)
  - openarena_perception.intent_transitions.TransitionSignals
  - openarena_perception.intent_transitions.detect_intent_transition (pure fn)
  - openarena_perception.navigation.navigator.Navigator.is_climbing_stairs property
  - openarena_perception.settings.BotSettings.intent_pause_ms field
  - hud_schema.build_hud_payload extended with context/is_paused_for_assess/threat_flag
  - ItemTour.context, threat_flag, _apply_intent_transition helper
affects:
  - openarena_perception/models.py
  - openarena_perception/settings.py
  - openarena_perception/navigation/navigator.py
  - openarena_perception/hud_schema.py
  - item_tour.py
tech-stack:
  added: []
  patterns:
    - "Edge-triggered intent transition detection (Research Pitfall 3)"
    - "Pure-function transition detection (testable without ItemTour)"
    - "Pause-to-assess as a 'release_all once + skip ticks until window expires' gate"
    - "Emergency break-out condition: threat OR stuck OR death overrides pause"
    - "Helper-method dispatch from every tick exit point (advisor/wall/death/stuck/normal)"
    - "BotContext.push_intent / record_problem / record_area encapsulate deque mutations"
    - "Deque -> list conversion in HUD payload builder (Pitfall 7)"
key-files:
  created:
    - openarena_perception/intent_transitions.py
    - tests/test_intent.py
    - tests/test_intent_transitions.py
    - tests/test_intent_pause.py
  modified:
    - openarena_perception/models.py
    - openarena_perception/settings.py
    - openarena_perception/navigation/navigator.py
    - openarena_perception/hud_schema.py
    - item_tour.py
    - tests/test_hud_schema.py
decisions:
  - "BotContext is NOT @dataclass(frozen=True) -- it owns mutable deques (Pitfall 2)"
  - "Intent and Problem are frozen+slots; modifications use dataclasses.replace()"
  - "Pause-to-assess gate sits at TOP of _on_state and uses tick-skip semantics, NOT a sleep"
  - "Transition detection wrapped in _apply_intent_transition helper called from every exit"
  - "Edge-trigger via prev_macro+prev_sub equality check inside _maybe()"
  - "Sub-only TOURING route advances do NOT open the pause window"
  - "ItemTour reads OA_INTENT_PAUSE_MS directly via os.environ AND BotSettings exposes it"
  - "_apply_intent_transition takes optional was_alive_prev_tick to handle the respawn edge"
metrics:
  duration: ~40min
  tasks: 2
  files_created: 4
  files_modified: 6
  tests_added: 47
  completed: 2026-04-10
---

# Phase 10 Plan 02: Intent + BotContext + Pause-to-Assess Summary

Delivered the bot self-awareness layer: an explicit Intent data model, a pure-function transition detector, BotContext ownership on ItemTour with deque-bounded history, a pause-to-assess gate that fires before each new macro intent (skippable on emergency or threat), Navigator.is_climbing_stairs property, OA_INTENT_PAUSE_MS env binding, and a HUD payload extension that emits all the new fields. Plan 10-03's HUD overhaul can now consume context.* fields directly from the HUD JSON.

## Outcome

- 8 MacroIntent members (IDLE, TOURING, CLIMBING_STAIRS, AVOIDING_WALL, RECOVERING_STUCK, REASSESSING_POSITION, RESPAWNING, PAUSING_TO_ASSESS) and 4 IntentStatus members all live in `models.py` and serialize as plain strings via StrEnum.
- `intent_transitions.detect_intent_transition()` is a pure function with edge-trigger semantics (Pitfall 3) -- the same signal twice in a row returns None on the second call.
- `Navigator.is_climbing_stairs` reads `_stair_climb_active` via getattr default for safety.
- `BotSettings.intent_pause_ms` clamps to [0, 5000] ms, falls back to 300 on bad input, and is bound to `OA_INTENT_PAUSE_MS`.
- ItemTour owns `self.context: BotContext` and a `threat_flag` stub property.
- The pause-to-assess gate sits at the TOP of `_on_state`, calls `release_all()` exactly ONCE on entry (Pitfall 4), and breaks out on emergency (`threat_flag OR nav.is_stuck OR health<=0`).
- All 6 transition signal sites are wired through `_apply_intent_transition()`, plus 5 Problem record sites (wall_halt, pin, advisor_halt, respawn, stuck).
- HUD payload now emits `intent`, `intent_history`, `problem_history`, `area_history`, `path_progress`, `tick_count`, `is_paused_for_assess`, `threat_flag` keys with all deques converted to lists (Pitfall 7) -- `json.dumps(payload)` no longer raises.

## Tasks Completed

| # | Task | Commit |
|---|------|--------|
| 1 | Intent data model + pure transition detector + Navigator.is_climbing_stairs + settings.intent_pause_ms + tests | `bac21b1` |
| 2 | Wire BotContext into ItemTour + 6 transition hooks + pause gate + extend HUD payload + tests | `907b862` |

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest tests/test_intent.py tests/test_intent_transitions.py tests/test_intent_pause.py tests/test_hud_schema.py -x -q` | 56 passed |
| `uv run pytest -q` (full suite) | 606 passed, 1 pre-existing flake (humanize) |
| HUD-scoped suite (`-k "hud or strategic_brain or item_tour or intent"`) | 118 passed |
| `import item_tour` | OK |
| `grep _intent_pause_until item_tour.py` | 5 sites (init, gate-check, gate-clear, transition-open, hud-export) -- expected |
| `grep release_all item_tour.py` | unchanged (12 occurrences); pause-gate calls release_all ONCE per transition, not every tick |
| `uv run ruff check` on new files (intent_transitions.py, test_intent.py, test_intent_transitions.py, test_intent_pause.py) | clean |

## Transition Hook Locations (post-edit line numbers in item_tour.py)

| Hook | Site | Line | Notes |
|------|------|------|-------|
| Pause gate | top of `_on_state` | ~580 | sits above advisor/Fix A/wall halt early returns |
| Advisor halt | inside hazard branch | ~688 | also records advisor_halt Problem |
| Fix A avoidance | inside avoidance window branch | ~701 | re-asserts AVOIDING_WALL |
| Wall halt + pin | end of proactive wall block | ~792 | records wall_halt OR pin Problem |
| Death | end of `gs.health<=0` branch | ~830 | records respawn Problem on edge |
| Respawn | end of `not self._was_alive` branch | ~854 | passes `was_alive_prev_tick=False` |
| Stuck recovering | `is_recovering` early return | ~859 | |
| Stuck first-tick | inside `is_stuck` branch | ~907 | records stuck Problem on first-tick edge |
| Survey spin | end of survey branch | ~942 | |
| Item timeout | end of timeout branch | ~1015 | |
| Normal fallthrough | very end of `_on_state` | ~1049 | passes halt_reason/pinned/pin_escalated locals |
| HUD export | `_export_hud` | ~1320 | reads `_intent_pause_until` to compute is_paused_for_assess |

The pure function `detect_intent_transition` is the single source of truth for which Intent fires; the helper `_apply_intent_transition` only handles state mutation (push_intent, pause window opening, area history, tick_count). 

## HUD Payload Schema Delta

New top-level keys when `context=ctx` is passed to `build_hud_payload`:

```json
{
  "intent": {
    "macro": "TOURING",
    "sub": "heading to item_health_mega",
    "description": "Heading to item_health_mega",
    "started_at": 1234567890.0,
    "duration_s": 2.3,
    "target": [232.0, 1600.0, -112.0],
    "target_area": null,
    "status": "executing"
  },
  "intent_history": [
    {"macro": "AVOIDING_WALL", "sub": "wall_ahead", "description": "...",
     "started_at": 1234567889.0, "duration_s": 0.8, "ended_at": 1234567889.0}
  ],
  "problem_history": [
    {"kind": "wall_halt", "location": [481.0, 1336.0, -93.0],
     "timestamp": 1234567889.0, "description": "halt_reason=wall_ahead score=0.89"}
  ],
  "area_history": [299, 259, 285, 304, 325],
  "path_progress": {"current_step": 5, "total_steps": 13},
  "tick_count": 42
}
```

Plus two unconditional new keys (default false when no context):

```json
{
  "is_paused_for_assess": false,
  "threat_flag": false
}
```

All deques are converted to lists before serialization. `json.dumps(payload)` is verified non-raising via `test_build_payload_is_json_serializable_with_context`.

## Test Counts

| File | Tests |
|------|-------|
| tests/test_intent.py | 12 |
| tests/test_intent_transitions.py | 20 (10 transitions + 3 navigator + 5 settings + 2 misc) |
| tests/test_intent_pause.py | 7 |
| tests/test_hud_schema.py (additions) | 8 |
| **Total new** | **47** |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Critical functionality] Multi-site `_apply_intent_transition` dispatch**

- **Found during:** Task 2 wiring
- **Issue:** The plan's Step 4 specified placing transition detection in a single location after `follow_path()` and before movement dispatch. But `_on_state` has 7 early-return paths (advisor halt, Fix A, wall halt, death, respawn, stuck-recovering, stuck-firsttick, survey, item timeout) -- a single location at the end would miss transitions on every blocking path.
- **Fix:** Extracted a `_apply_intent_transition()` helper method and called it from every tick-exit point. Each call passes the locally-known signals (halt_reason, pinned, advisor_warning, was_alive_prev_tick). This preserves the plan's edge-trigger semantics and lets the pure function `detect_intent_transition` remain the single source of truth.
- **Files modified:** item_tour.py
- **Verification:** `grep _apply_intent_transition item_tour.py` shows 11 call sites (1 helper def + 10 invocations).

**2. [Rule 1 - Bug] Respawn edge needs pre-flip prev tick value**

- **Found during:** Task 2 wiring (writing the respawn branch)
- **Issue:** The respawn branch sets `self._was_alive = True` immediately, so calling `_apply_intent_transition` afterward would see `was_alive_prev_tick=True` and miss the dead-to-alive edge that the transition rule depends on.
- **Fix:** Added optional kwarg `was_alive_prev_tick: bool | None = None` to `_apply_intent_transition` (defaults to `self._was_alive`); the respawn branch passes `was_alive_prev_tick=False` explicitly so `detect_intent_transition` correctly fires the TOURING "recovering from respawn" Intent.
- **Files modified:** item_tour.py
- **Verification:** Tested via `test_respawn_triggers_touring` in test_intent_transitions.py.

**3. [Rule 3 - Blocking] Tick-local halt_reason / pinned / pin_escalated needed at top of `_on_state`**

- **Found during:** Task 2 wiring (referencing halt_reason in the normal fallthrough)
- **Issue:** `halt_reason` was an inner-block local of the proactive wall halt branch. The normal fallthrough path needs to pass it to `_apply_intent_transition`, but Python local scoping meant the variable would not be visible at the bottom of the function unless declared at the top.
- **Fix:** Initialized `halt_reason: str | None = None`, `pinned: bool = False`, `pin_escalated: bool = False` at the top of `_on_state` (right after `now = time.time()`) so the existing `halt_reason = self._check_proactive_wall(...)` assignment correctly mutates the outer local.
- **Files modified:** item_tour.py
- **Verification:** Test suite green; no UnboundLocalError.

**4. [Rule 1 - Bug] Settings field validator needed `mode="before"` for env coercion**

- **Found during:** Task 1 (writing settings tests)
- **Issue:** Pydantic v2 `field_validator` defaults to `mode="after"`, meaning the value is already typed as `int`. When `OA_INTENT_PAUSE_MS=abc` is set, pydantic raises ValidationError BEFORE the validator runs, so the "fallback to 300" requirement could not be met.
- **Fix:** Used `@field_validator("intent_pause_ms", mode="before")` so the validator receives the raw env string, attempts `int(v)` in a try/except, and returns 300 on failure. The clamping logic also moved into the same validator for atomicity.
- **Files modified:** openarena_perception/settings.py
- **Verification:** `test_intent_pause_ms_invalid_fallback` passes.

### Out of scope (logged, not fixed)

- Pre-existing ruff errors in `item_tour.py` (parse_aas unused import line 430, `YAW` variable name line 1078, f-string without placeholders line 1217) -- not introduced by this plan.
- Pre-existing ruff errors in `settings.py` (unused `pathlib.Path`, `typing.ClassVar`) -- present on the 10-01 baseline; confirmed via `git stash`.
- `tests/test_humanize.py::test_accuracy_cap_enforced_in_aim_controller` randomized boundary failure -- pre-existing flake documented in 10-01-SUMMARY.md.

## Threat Surface

No new network surface, auth path, file access patterns, or trust boundary changes. The HUD JSON file is still written atomically to `<project>/tmp/oa_hud_state.json` with the same permissions as 10-01. The new `intent_pause_ms` env var is read once at construction and clamped to a safe range. The `threat_flag` stub returns False; future phases that wire enemy detection should re-evaluate.

## Notes for Plan 10-03

Plan 10-03's `strategic_hud.py` overhaul can render directly from these HUD JSON keys:

- `intent.macro`, `intent.sub`, `intent.description`, `intent.duration_s` -- big-text current intent panel
- `intent_history[]` -- last 5 intents (deque maxlen=5 enforced upstream)
- `problem_history[]` -- last 5 problems (color-coded by `kind`)
- `area_history[]` -- recent area transitions (last 10)
- `path_progress.current_step` / `path_progress.total_steps` -- progress bar
- `is_paused_for_assess` -- flashing blue border indicator
- `threat_flag` -- red border indicator (always false until enemy detection is wired)
- `tick_count` -- liveness indicator

No further model or transition changes are needed for 10-03; all rendering data is already exported.

## Self-Check: PASSED

- openarena_perception/intent_transitions.py: FOUND
- tests/test_intent.py: FOUND
- tests/test_intent_transitions.py: FOUND
- tests/test_intent_pause.py: FOUND
- Commit `bac21b1`: FOUND
- Commit `907b862`: FOUND
- 56/56 phase-10-02-scoped tests passing
- 118/118 HUD+intent-scoped tests passing
- 606/607 full suite (1 pre-existing flake, unrelated to this plan)
