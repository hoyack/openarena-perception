# Plan 10-03 Summary: HUD Overhaul

**Completed:** 2026-04-10
**Status:** Complete — human-verified in live tour run
**Commits:** `6e4cfd1`, `30021ba`

## What was delivered

- `strategic_hud.py` widened from 600×700 to 1000×700
- `MINIMAP_MARGIN=100` constant replaces all `(HUD_WIDTH - MINIMAP_SIZE) // 2` centering math so the minimap stays LEFT-anchored
- New `_draw_intent_panel(x_offset=600)` method renders the full right-side panel with 6 sections:
  - **Current Intent box** — macro name (22pt yellow), sub-intent (14pt white), duration counter (gray)
  - **2Hz flashing blue border** (`PAUSE_BORDER=(80,150,255)`, 3px) during pause-to-assess windows
  - **Intent history** — 5 rows, dim gray, 12pt
  - **Problem history** — 5 color-coded rows (red wall_halt, orange stuck, purple pin, cyan respawn, red advisor_halt)
  - **Path progress** — `N/M` text + filled yellow progress bar
  - **Stats** — advisor sent/complete/failed + proactive halt counters + tick counter
  - **Threat badge** — green "no threat" (default) / red "THREAT" (when threat_flag=True)
- `HUDState.__init__` extended with safe defaults for all new intent/context fields
- `HUDState.load(path=None)` now accepts an optional path and returns `self` for chaining
- New contract test in `tests/test_hud_schema.py` round-trips `build_hud_payload(context=_ctx())` → JSON → `HUDState.load()` → field assertions, using `SDL_VIDEODRIVER=dummy` for headless pygame init

## Deviations from plan

**[Rule 3 blocking]** `HUDState` is NOT a `@dataclass` in reality — it's a regular class with an instance-method `load(self)`. Plan spec assumed a dataclass with classmethod `load`. Executor adapted:
- Extended `__init__` with safe defaults instead of `field(default_factory=...)`
- Made `load()` accept optional path + return `self` for chaining
- Contract test uses `HUDState().load(path)` instead of the plan's `HUDState.load(path)` classmethod form

Documented in the executor's checkpoint report; not a regression since all existing call sites remain unchanged.

## Pitfalls addressed

- **Pitfall 1** (standalone HUD executable): `strategic_hud.py` imports zero from `openarena_perception` package — verified via `rg "from openarena_perception" strategic_hud.py` → 0 matches
- **Pitfall 7** (deque JSON serialization): already handled in 10-02's `build_hud_payload` extension; 10-03 consumes the lists

## Verification results

### Automated
- `uv run python -c "import strategic_hud; assert strategic_hud.HUD_WIDTH == 1000"` → OK
- `HUDState().load('/nonexistent')` returns empty defaults → OK (edge case)
- New contract test `test_contract_build_payload_to_strategic_hud_load` → PASS
- HUD + intent scoped suite (`test_hud_schema` + `test_intent*`) → 57/57 PASS
- Wider scope (`-k "hud or intent or strategic_brain or item_tour"`) → 119/119 PASS
- `rg "HUD_WIDTH - MINIMAP_SIZE" strategic_hud.py` (active code) → 0 matches (only comments)

### Live game run (human-verified)
- Ran `OA_INTENT_PAUSE_MS=500 uv run python item_tour.py --no-vision` for 767 seconds
- **Tours completed: 1/1** (first successful end-to-end tour of the session)
- **Deaths: 0** (previous runs consistently died to lava / swim edges)
- **Tick rate: 20 FPS** (2x improvement over pre-Phase-10 runs at 8-11 FPS)
- **Intent transitions fired: 401** total events (PROACTIVE WALL HALT + intent transitions + pin escalations)
- **Advisor stats**: sent=86, complete=24, stale=56, failed=5 — cloud model actually delivered actionable advice once warm (e.g. `"The bot is in a narrow corridor with a stone wall immediately to the right..." -> walk_forward`)
- **HUD rendered successfully** — 1000×700 window, left-anchored minimap, right-side intent panel with all 6 sections visible, zero pygame errors in `./logs/hud.log`
- **All intent macros observed in logs**: `TOURING`, `AVOIDING_WALL`, `RECOVERING_STUCK`, and `(pause 500ms)` markers on every transition
- User visually confirmed the layout and reported the flashing blue border firing during transitions

## Files changed

- `strategic_hud.py` — 1000×700 widening + `_draw_intent_panel` + extended `HUDState`
- `tests/test_hud_schema.py` — new contract test

## Ruff status

New code is ruff-clean. 6 pre-existing violations in `strategic_hud.py` (unused `sys`, deprecated `typing.Tuple`, uppercase `CELL_COLORS` local, unused loop var `aid`) are unchanged from the pre-plan baseline and remain out of scope per the scope boundary rule.

## What's next

Plan 10-03 closes Phase 10. Intent System and HUD Companion is complete.

The session's live-run evidence shows Phase 10 delivers meaningful behavioral improvement:
- First full tour completion of the session
- 2x FPS improvement
- Zero deaths on a map that killed the bot consistently before
- Clean HUD observability with intent visible in real time

Ready for Phase 11 (Wireframe Perception Grid).
