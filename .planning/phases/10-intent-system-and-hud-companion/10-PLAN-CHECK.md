# Phase 10 Plan Check

**Checked:** 2026-04-10
**Plans verified:** 10-01, 10-02, 10-03
**Method:** Goal-backward analysis against CONTEXT.md scope, RESEARCH.md pitfalls/assumptions, and CLAUDE.md project conventions.

## VERDICT: PASS

If executed in order (10-01 → 10-02 → 10-03), the three plans will deliver the Phase 10 goal: bot self-awareness via Intent/BotContext model, pause-to-assess behavior, runtime artifact reorganization under `./tmp/` and `./logs/`, and a 1000x700 companion HUD with right-side intent panel.

## Verification Matrix

| Check | Status | Notes |
|---|---|---|
| Pitfall 1 (no `openarena_perception` import in strategic_hud) | PASS | 10-01 STEP 3 sets `STATE_FILE = Path(__file__).resolve().parent / "tmp" / ...`. 10-03 STEP 7 explicitly greps `from openarena_perception` to confirm zero matches. |
| Pitfall 2 (BotContext not frozen) | PASS | 10-02 STEP 1 uses `@dataclass(slots=True)` (not frozen). `test_bot_context_is_not_frozen` covers it. |
| Pitfall 3 (edge-triggered transitions) | PASS | `detect_intent_transition._maybe()` returns None when `(new_macro, new_sub) == (prev_macro, prev_sub)`. `test_stuck_edge_trigger_no_repeat` covers it. |
| Pitfall 4 (pause gate placement order) | PASS | 10-02 STEP 3: gate placed right after `self._tick += 1 / now = time.time()`, BEFORE advisor-halt (~528), Fix A (~541), wall halt (~545). Emergency break-out: `not threat_flag and not nav_is_stuck and health_ok`. |
| Pitfall 5 (cwd path trap) | PASS | 10-01 STEP 1: `PROJECT_ROOT = Path(__file__).resolve().parents[1]`. `test_state_file_is_anchored_to_project_root` covers it. |
| Pitfall 6 (StrategicBrain class attribute) | PASS | 10-01 STEP 2: `STATE_FILE = _HUD_STATE_FILE` retained as class attribute for back-compat. STEP 2 also instructs greppin tests/ for `STATE_FILE`. |
| Pitfall 7 (deque JSON serialization) | PASS | `build_hud_payload` extension in 10-02 uses `list(...)` and list comprehensions for every deque. `test_build_payload_is_json_serializable_with_context` covers it. `test_build_payload_deque_must_be_converted_by_caller` documents the contract. |
| Pitfall 8 (tuple↔list one-way contract) | PASS | Documented in `hud_schema.py` module docstring (10-01 STEP 1). Payload uses `list(ci.target)` always. HUD reads as list via `.get()`. |
| Schema consistency across plans | PASS | 10-01 defines `build_hud_payload(*, sa, gs, map_name, brain_state, nav, learned_map, extras)`. 10-02 additively extends with `context`, `is_paused_for_assess`, `threat_flag`. 10-03 consumes via `HUDState.load()` with `.get()` defaults — no field drift. |
| Dependency order | PASS | 10-01 wave 1 (`depends_on: []`), 10-02 wave 2 (`depends_on: [10-01]`), 10-03 wave 3 (`depends_on: [10-02]`). No reverse deps. |
| File overlap on `hud_schema.py` | PASS | 10-01 creates the module; 10-02 extends the existing function additively. No edits to existing code paths, only new kwargs and a new conditional block. |
| File overlap on `test_hud_schema.py` | PASS | 10-01 creates 9 tests; 10-02 appends `_ctx()` helper + 7 context tests; 10-03 appends 1 contract test. All append-only, sequential. |
| Test pattern compliance (`uv run pytest`) | PASS | All `<verify>` blocks use `uv run pytest`. No `@pytest.mark.asyncio` (tests are sync). |
| Pause-to-assess gate placement specificity | PASS | 10-02 STEP 3 names the surrounding line numbers (528, 541, 545, 632, 668) and gives the exact gate condition. |
| Transition detection purity | PASS | 10-02 STEP 2 creates `openarena_perception/intent_transitions.py` with pure `detect_intent_transition(signals)` and `TransitionSignals` dataclass. Tested in isolation in `test_intent_transitions.py`. |
| Macro intent enum completeness | PASS | All 8 from CONTEXT.md present in 10-02 STEP 1: IDLE, TOURING, CLIMBING_STAIRS, AVOIDING_WALL, RECOVERING_STUCK, REASSESSING_POSITION, RESPAWNING, PAUSING_TO_ASSESS. |
| Rollback instructions | PASS | All 3 plans have explicit `<rollback>` sections with `git checkout` and `rm -f` commands. |
| Success criteria machine-checkable | PASS | Every `<done>` and `<success_criteria>` item is a test pass, file existence, grep result, or import check. The one human checkpoint is 10-03 Task 3, appropriate for visual HUD verification. |
| Scope creep (no bidirectional control / TTS / real threat) | PASS | `threat_flag` is a stub property returning False (10-02). No HUD→bot command channel. No audio. No remote/web HUD. |
| In-scope completeness (CONTEXT §What's in scope) | PASS | BotContext/Intent ✓ (10-02), transition hooks ✓ (10-02), pause-to-assess ✓ (10-02), HUD schema extended ✓ (10-02), HUD panel ✓ (10-03), directory reorg ✓ (10-01), unit tests ✓ (10-02). StrategicBrain optional intent hook is correctly deferred per RESEARCH stability heuristic. |
| CLAUDE.md compliance (uv, ruff, pytest, structlog left alone) | PASS | All commands use `uv run`. Existing `logging` is preserved (RESEARCH explicitly says "Do not refactor to structlog"). Frozen+slots dataclass convention copied from `models.py:43`. |

## Optional Improvement Suggestions (non-blocking)

1. **`PAUSING_TO_ASSESS` macro is dead code.** The enum value is defined in `MacroIntent` (10-02 STEP 1) but `detect_intent_transition` never returns it — pause is represented via `IntentStatus.PLANNING` + `is_paused_for_assess` JSON flag. Either remove the enum value or have the transition detector return it when opening the pause window. Cosmetic; the HUD displays the previous macro during pause anyway.

2. **`intent_history[].ended_at` mislabeled.** In `hud_schema.py` 10-02 STEP 1 build code: `"ended_at": h.started_at` with comment "HUD only needs relative ordering". This field name is wrong (it's actually `started_at` again). 10-03 never reads `ended_at`, so no functional impact. Suggest either remove the key or compute the real end time as the next intent's `started_at`.

3. **`_current_target_name()` / `_current_target_pos()` helper assumption.** 10-02 STEP 4 references these helpers with a "compute inline if they don't exist" fallback. This is a soft instruction that depends on what the executor finds in `item_tour.py`. Suggest the executor read item_tour.py first and pin the exact extraction expression in the SUMMARY so 10-03 doesn't have to re-discover it.

4. **`pin_escalated` signal duplication.** 10-02 STEP 4 inlines `pin_escalated = (halt_reason == "visual_pin" and getattr(self, "_pinned", False))` rather than reading an existing item_tour state. If item_tour already tracks pin escalation in a dedicated variable, the signal should read that to avoid drift.

5. **10-03 Task 2 contract test imports `_ctx()` from 10-02 additions.** This cross-task dependency is fine (both tasks land in the same file before 10-03 runs), but the test would fail if 10-02 STEP 8 was skipped or `_ctx()` was renamed. Defensive: 10-03 Task 2 could re-define `_ctx()` locally or import it explicitly. Minor.

6. **Navigator.is_climbing_stairs returns False if attribute is missing.** Defensive `getattr(..., False)` is good, but it means a typo in `_stair_climb_active` would silently never fire CLIMBING_STAIRS intents. Consider asserting the attribute exists in a unit test that imports Navigator and checks `hasattr(Navigator, '_stair_climb_active')` or similar.

None of the above block execution. Plans are ready to run.

## CHECK COMPLETE
