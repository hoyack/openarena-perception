# Phase 12: Open-Perception UI — Plan Check

**Checked:** 2026-04-10
**Checker:** gsd-plan-checker
**Plans reviewed:** 12-01, 12-02, 12-03
**Method:** Goal-backward verification against CONTEXT.md decisions, RESEARCH.md pitfalls/assumptions, requirement coverage, dependency chain, scope sanity, dedup contract, legacy deletion completeness, Nyquist compliance.

## VERDICT: PASS

If executed exactly as written, the three plans WILL achieve Phase 12's goal: a single standalone 1400×700 `open_perception.py` three-panel app replacing both `strategic_hud.py` and `demo_wireframe_room.py`, with deduplicated metrics and verbose telemetry, human-verified via a live tour.

---

## Coverage Matrix

### Requirement coverage (OP-01 … OP-12)
| Req | Covering plan/task | Status |
|---|---|---|
| OP-01 verbose telemetry in HUD schema | 12-01 Task 1 | covered |
| OP-02 Navigator replan + swim-edge hooks | 12-01 Task 2 | covered |
| OP-03 item_tour fills verbose fields | 12-01 Task 3 | covered |
| OP-04 MinimapPanel extracted + isolated tests | 12-02 Task 2 | covered |
| OP-05 WireframePanel with decoration-only chrome | 12-02 Tasks 1+2 | covered |
| OP-06 StatsPanel with 9 verbose rows | 12-02 Task 3 | covered |
| OP-07 `hud.py` `decoration_only` mode | 12-02 Task 1 | covered |
| OP-08 `open_perception.py` entry point | 12-03 Task 1 | covered |
| OP-09 1400×700 three-panel layout | 12-03 Task 1 | covered |
| OP-10 Legacy file deletion | 12-03 Task 2 | covered |
| OP-11 Contract test rewritten against `open_perception.HUDState` | 12-03 Task 2 | covered |
| OP-12 Human visual verify | 12-03 Task 3 | covered |

### User decision compliance (CONTEXT.md locked 5)
| Decision | Honored in | Status |
|---|---|---|
| D1 — Delete legacy (option C) | 12-03 Task 2 | honored |
| D2 — 3-panel 1400×700 (option D) | 12-03 Task 1 | honored |
| D3 — Deduplication proposal | 12-02 Task 1 (`decoration_only`), Task 2 (no text in minimap), Task 3 (stats owns all) | honored |
| D4 — Full verbose list (all 9) | 12-02 Task 3 renders all 9; 12-01 Task 3 wires all 9 | honored |
| D5 — Read-only observability (option A) | No plan includes any input handlers beyond QUIT | honored |

### Pitfall coverage (10 from RESEARCH.md)
| # | Pitfall | Addressed in |
|---|---|---|
| P1 | Sub-surface vs parent coord mixing | 12-02 Task 2 (panels use sub-relative); 12-03 Task 1 (separators on parent) |
| P2 | BGR/RGB silent color bug | 12-02 Task 2 RGB_ constants + explicit BGR→RGB swap test |
| P3 | Pygame font cache after window close | 12-02 Task 2 & 3 fonts created in `__init__` |
| P4 | `subsurface()` ValueError on resize | 12-02 Task 2 HUD_WIDTH derived from panel constants |
| P5 | `extra_hud=None` doesn't suppress FRAME text | 12-02 Task 1 adds `decoration_only` kwarg + regression test |
| P6 | Missing test import update on legacy delete | 12-03 Task 2 order-of-operations: rewrite test BEFORE deletion |
| P7 | Log-based replan tracking swallows events | 12-01 Task 2 uses callback (`on_replan=`), NOT logging.Handler |
| P8 | Swim edge traversal fires every tick | 12-01 Task 2 `_last_swim_edge_area` set on transition only + 2s decay |
| P9 | State file stale before bot start | 12-03 Task 1 "WAITING FOR BOT" status bar |
| P10 | Map bounds flicker | 12-02 Task 2 latch bounds on first load |

### Assumption handling (A3, A4, A8 — MEDIUM flagged)
| # | Assumption | Plan response |
|---|---|---|
| A3 | `_stair_target_area` does NOT exist | 12-01 Task 3 derives via `navigator.current_step_area` (new property = `_path[0]`); plan `<interfaces>` block calls this out explicitly |
| A4 | `advisor.current_narrative()` present | 12-01 Task 3 step 7 "Verify `advisor.current_narrative()` exists before calling — grep to confirm; if absent, executor must flag and stop (not fabricate)" |
| A8 | Single replan site | 12-01 Task 2 step 1 "Audit assumption A8: grep `self._path = ` in navigator.py to confirm only ONE replan site. If additional sites exist, fire the hook at each" |

### Deduplication contract (every metric appears exactly once)
| Metric | Owner | Excluded from |
|---|---|---|
| HP / Armor / Ammo / Weapon | StatsPanel | MinimapPanel (explicit NO), WireframePanel (`decoration_only=True`) |
| POS XYZ / Yaw | StatsPanel | MinimapPanel (explicit NO — only player marker + arrow, no text), WireframePanel |
| FRAME / ROOM / FOV / MODE / OBJECTS | NEITHER (suppressed entirely) | Guaranteed by `hud.py decoration_only` kwarg in 12-02 Task 1 |
| Route waypoints + yaw arrow | MinimapPanel (visual only) | Nowhere else |
| Decoration chrome (brackets/crosshair/SRC/status) | WireframePanel only | — |
| 9 verbose telemetry rows | StatsPanel | — |

### Legacy deletion completeness (12-03 Task 2)
- [x] `strategic_hud.py` delete instruction present
- [x] `openarena_perception/visualization/demo_wireframe_room.py` delete instruction present
- [x] Rewrite `test_contract_build_payload_to_strategic_hud_load` → `test_contract_build_payload_to_open_perception_load`
- [x] Grep sweep covering `strategic_hud` + `demo_wireframe_room` across repo
- [x] Explicit audit of `map_explorer.py` (RESEARCH-flagged)
- [x] Explicit audit of `openarena_perception/visualization/__init__.py`
- [x] README.md / CLAUDE.md updated if references exist
- [x] Order of operations enforced (rewrite → verify green → delete → verify green again)

### Verbose telemetry 9-field coverage
All 9 fields wired in 12-01 Task 3 and rendered in 12-02 Task 3:
stair_climb_state, swim_edge_state, advisor_last_thought, last_replan_steps, tick_rate_fps, frame_lag_ms, proactive_halts, visual_pin_hits, nav_current_step_area — with correct sources per CONTEXT.md Decision 4 table.

### Dependency chain
12-01 (wave 1, `depends_on: []`) → 12-02 (wave 2, `depends_on: [12-01]`) → 12-03 (wave 3, `depends_on: [12-01, 12-02]`). Acyclic, forward-only. Correct.

### Scope sanity
| Plan | Tasks | Files | Assessment |
|---|---|---|---|
| 12-01 | 3 auto | 7 | within budget |
| 12-02 | 3 auto | 8 | within budget |
| 12-03 | 2 auto + 1 checkpoint | 7 | within budget |

### Autonomous flags
- 12-01: `autonomous: true` ✓
- 12-02: `autonomous: true` ✓
- 12-03: `autonomous: false` with blocking `checkpoint:human-verify` task ✓

### Test convention compliance
- All `<verify>` commands use `uv run pytest` ✓
- All pygame tests set `SDL_VIDEODRIVER=dummy` (module-level before `import pygame` per 12-02 Task 2 step 4 and 12-03 Task 1 step 8) ✓

### Human-verify checkpoint quality (12-03 Task 3)
- [x] Visual checklist with ~20 pass/fail items
- [x] "Every metric appears exactly once" verification row
- [x] Deletion verification via `ls ... 2>&1` commands for both legacy files
- [x] `SDL_VIDEODRIVER=dummy uv run pytest -q` green gate
- [x] Concrete "how to reproduce" instructions (two terminals, exact commands)
- [x] Per-panel breakdown (left/center/right) with specific visual elements called out
- [x] Clear resume signal ("approved" or describe failure)

### Scope creep check
No plan includes: interactive controls, new detection models, path viz in wireframe, Hailo wiring, configurable layout, fullscreen, AAS outlines (explicitly deferred per Open Question 4), or any deferred item from CONTEXT.md. Clean.

---

## Non-blocking improvements

1. **RESEARCH.md `## Open Questions` heading** — the four open questions (--aas flag, contract test rewrite vs delete, None-row rendering, AAS area outlines) are ALL answered in the plans (12-03 Task 1 auto-detect+fallback, 12-03 Task 2 rewrite, 12-02 Task 3 placeholder, 12-02 Task 2 defer to learned map). Consider appending `(RESOLVED)` to the heading and inline `RESOLVED:` markers per the GSD Dimension 11 convention. Non-blocking because every question is substantively answered — only the hygiene marker is missing.

2. **12-02 Task 1 default-mode test** — `test_render_hud_default_draws_numeric_text` will only pass non-bg pixels if the fixture passes a `state={"frame": N, ...}` dict so `render_hud` has a frame counter to draw. The executor should notice this when writing the test; non-blocking because it is an obvious test-writing detail.

3. **12-01 Task 2 `on_replan` callback signature** — plan chose `Callable[[int], None]` (new step count only) vs RESEARCH suggestion `Callable[[int, int, int], None]` (from_area, old_steps, new_steps). Plan's choice is consistent internally and sufficient for the `deque(maxlen=3)` of step counts. If a future phase wants to surface re-plan origin areas or deltas, the callback signature will need to grow — consider passing the three args now for forward-compat. Non-blocking.

4. **12-02 Task 3 pause-flash test** — `test_stats_panel_pause_border_flashes` monkeypatches `time.time`. The executor should verify whether the extracted `_draw_intent_panel` code uses `time.time()` or `time.monotonic()` and patch the right symbol. Non-blocking — obvious during implementation.

5. **WireframePanel constructor deviation from RESEARCH sketch** — plan takes a pre-parsed `aas_graph` (not a path). This is a deliberate, well-justified deviation ("makes testing easier") and is consistent between 12-02 Task 2 and 12-03 Task 1 which calls `parse_aas` in the app and hands the graph to the panel. Called out here for transparency, not as a concern.

---

## Summary

Plans are thorough, goal-backward consistent, dedup-contract-enforcing, and correctly sequenced. All five user decisions are honored, all ten pitfalls are concretely addressed in task steps (not just "watch out" notes), both MEDIUM assumptions have explicit audit steps, and the legacy deletion path is ordered safely (rewrite → verify → delete → verify). The human-verify checkpoint in 12-03 Task 3 is strong enough to catch any silent dedup violation at runtime. Proceed to execution.

## CHECK COMPLETE
