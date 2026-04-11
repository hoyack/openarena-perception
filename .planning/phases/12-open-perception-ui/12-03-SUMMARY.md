---
phase: 12-open-perception-ui
plan: 03
subsystem: open-perception-app
tags: [hud, pygame, unified-view, legacy-cleanup, app-entry-point]
requires:
  - Phase 12-01 HUD schema verbose fields
  - Phase 12-02 panels subpackage (MinimapPanel, WireframePanel, StatsPanel)
  - Phase 11 WireframeRoomRenderer + AASDepthBackend
  - Phase 10 HUD state format
provides:
  - open_perception.py app entry point (1400x700 unified HUD)
  - open_perception.HUDState class with Phase 10 + Phase 12-01 fields
  - --aas CLI flag with auto-detect + oa_dm1.aas fallback
  - WAITING FOR BOT placeholder when state file missing
affects:
  - open_perception.py (created)
  - tests/test_open_perception.py (created)
  - tests/test_hud_schema.py (contract test rewritten)
  - strategic_hud.py (deleted)
  - openarena_perception/visualization/demo_wireframe_room.py (deleted)
  - openarena_perception/hud_schema.py (docstring reference update)
  - item_tour.py (docstring/comment reference updates)
  - .planning/REQUIREMENTS.md (OP-04..OP-12 added)
tech-stack:
  added: []
  patterns:
    - "screen.subsurface(Rect) composition with panels drawing (0,0)-relative"
    - "Parent-surface absolute coords for vertical separators (Pitfall 1)"
    - "HUD_WIDTH imported from panels/__init__ (never hardcoded — Pitfall 4)"
    - "Tolerant HUDState.load with bare except — matches Phase 10 precedent"
    - "AAS resolution: CLI -> maps/{state_map}.aas -> maps/oa_dm1.aas fallback"
    - "_peek_state_map_name reads only 'map' field at startup before main loop"
key-files:
  created:
    - open_perception.py
    - tests/test_open_perception.py
    - .planning/phases/12-open-perception-ui/deferred-items.md
  modified:
    - tests/test_hud_schema.py
    - openarena_perception/hud_schema.py
    - item_tour.py
    - .planning/REQUIREMENTS.md
  deleted:
    - strategic_hud.py
    - openarena_perception/visualization/demo_wireframe_room.py
decisions:
  - HUDState is a plain class (not @dataclass) mirroring Phase 10 precedent; load() tolerates missing/malformed files and returns self for chaining
  - AAS auto-detect peeks only the 'map' field via _peek_state_map_name to avoid triggering a full HUDState.load before the app window exists
  - _resolve_aas_path raises FileNotFoundError only when ALL candidates (CLI / autodetect / fallback) fail — lets the app abort with a clear message
  - Status bar drawn on the parent surface (absolute coords) at the bottom 20px strip, consistent with separator placement (Pitfall 1)
  - Session-scoped real AAS fixture (parse_aas maps/oa_dm1.aas) for app tests; MagicMock could not satisfy AASDepthBackend's graph.vertexes.size probe
  - map_explorer.py: this file is untracked in git; our on-disk edits fix the reference but do not land in the commit (documented in deferred-items.md)
metrics:
  duration: ~25min
  tasks: 3
  new_tests: 12
  total_tests_passing: 732
  files_created: 3
  files_modified: 4
  files_deleted: 2
requirements:
  - OP-08
  - OP-09
  - OP-10
  - OP-11
  - OP-12
completed: 2026-04-11
---

# Phase 12 Plan 03: Open-Perception Unified HUD App Summary

Shipped `open_perception.py` — the standalone 1400×700 pygame app that
composes the Phase 12-02 panels into a single unified window — and
deleted the legacy `strategic_hud.py` (Phase 10) and
`openarena_perception/visualization/demo_wireframe_room.py` (Phase 11).
Rewrote the one breaking contract test. Full regression stayed green
across the deletion (732 passing both before and after).

## Task Breakdown

| Task | Commit | Tests Added | Files |
|------|--------|-------------|-------|
| 1. open_perception.py + HUDState + smoke tests | 2e62f05 | 12 | open_perception.py, tests/test_open_perception.py |
| 2. Rewrite contract test + delete legacy files + docstring sweep | 61d12db | 0 (rewrite) | tests/test_hud_schema.py, hud_schema.py, item_tour.py, strategic_hud.py (deleted), demo_wireframe_room.py (deleted) |
| 3. Human-verify checkpoint | n/a | 0 | (auto-approved per workflow.auto_advance) |

## Final File Sizes

| File | LOC |
|------|-----|
| `open_perception.py` | 451 |
| `tests/test_open_perception.py` | 225 |

open_perception.py overshot the 150-200 target; the overage comes from
docstrings, HUDState's full Phase 10 field list, the argparse/resolver
helpers, and the CLI/waiting placeholder branches. Pure loop/draw logic
is ~120 lines — target met on the executable portion.

## Grep Sweep Results

Pre-deletion, live references to `strategic_hud` / `demo_wireframe_room`
existed in:

| File | Action |
|------|--------|
| `openarena_perception/hud_schema.py:3` | Docstring comment updated to "open_perception.py reader" |
| `item_tour.py:613` | Comment updated to "open_perception.py companion app" |
| `item_tour.py:1284` | Docstring updated to "open_perception.py" |
| `map_explorer.py:21` | Docstring updated (file is UNTRACKED — see deferred-items.md) |
| `map_explorer.py:548` | subprocess.Popen target updated (UNTRACKED — see deferred-items.md) |
| `tests/test_hud_schema.py:373-438` | Contract test rewritten end-to-end |

Remaining matches after Task 2 (all intentional):
- `open_perception.py:12-13` — docstring historical note ("replaces legacy X")
- `tests/test_hud_schema.py:414` — comment inside rewritten test ("pattern as the legacy strategic_hud.HUDState")
- `tests/test_open_perception_panels.py:138-140, 404-409` — negative assertions proving panels do NOT import strategic_hud
- `.hypothesis/constants/bccdd3a092bafd95` — hypothesis cache file (build artifact, not source)

No live import of either deleted file remains anywhere in the tracked
codebase.

## Key Decisions Walked

### HUDState is a plain class, not @dataclass

Follows the Phase 10 deviation documented in 10-03-SUMMARY. @dataclass
would force us to enumerate every field in __init__ signatures which
makes the 7 new Phase 12-01 fields annoying to plumb through; a plain
class with instance-attribute defaults mirrors strategic_hud's original
shape and keeps `HUDState().load(path)` working as a fluent call.

### Real AAS graph fixture instead of MagicMock

The first draft of `test_open_perception.py` used a `MagicMock` for the
AAS graph. AASDepthBackend.__init__ calls `_has_face_mesh(graph)` which
evaluates `graph.vertexes.size > 0` — MagicMock returns a MagicMock for
attribute access and then `> 0` raises TypeError. Switching to a
session-scoped `parse_aas(maps/oa_dm1.aas)` fixture fixed it in one line
and gave the smoke tests a realistic render path.

### Auto-approved checkpoint

Workflow config has `auto_advance: true`. Per the executor checkpoint
protocol, human-verify checkpoints auto-approve under auto mode. Live
bot verification by the user is queued for the next interactive session;
the SUMMARY is gated on the automated verification (732 tests green +
self-check file existence + zero live legacy imports).

### map_explorer.py out-of-scope fix

`map_explorer.py` is UNTRACKED in git but contained two live references
to `strategic_hud.py` (launch shortcut + docstring). Task 2 fixed them
on disk (Rule 1 — broken reference) but did not stage the file since
committing a whole untracked root script is outside the plan scope. The
fix keeps map_explorer runnable locally; documented in
`.planning/phases/12-open-perception-ui/deferred-items.md`.

## Deviations from Plan

### Rule 1 - Bug fix

**1. map_explorer.py launched a now-deleted file**
- **Found during:** Task 2 grep sweep
- **Issue:** `subprocess.Popen([sys.executable, "strategic_hud.py"], ...)`
  would have failed post-deletion.
- **Fix:** Replaced with `open_perception.py` in the launch call and in
  the module docstring. File is untracked so the fix lives on disk only;
  documented in deferred-items.md.

### Rule 2 - Missing critical functionality

**1. OP-01..OP-12 requirements missing from REQUIREMENTS.md**
- **Found during:** Task 0 prep (flagged by Wave 2 executor)
- **Issue:** The Phase 12 requirement IDs referenced in plan frontmatter
  (OP-01 through OP-12) had no corresponding entries in
  `.planning/REQUIREMENTS.md`, so `requirements mark-complete` would be
  a no-op.
- **Fix:** Added "Open-Perception UI (Phase 12)" section with all 12
  requirement bullets and 12 traceability rows. Plans 12-01 through
  12-02 are now markable (OP-01..OP-07 = complete) and this plan marks
  OP-08..OP-12.

### Rule 3 - Blocking issue

**1. MagicMock AAS graph failed AASDepthBackend probe**
- **Found during:** Task 1 first test run
- **Issue:** `graph.vertexes.size > 0` in `_has_face_mesh` raised
  TypeError against MagicMock.
- **Fix:** Switched fixture to real `parse_aas(maps/oa_dm1.aas)` at
  module scope.

### Auto-fixed bugs

None beyond the above.

### Auth gates

None.

## Test Count Delta

- `tests/test_open_perception.py`: 0 -> 12 (new file)
- `tests/test_hud_schema.py`: 1 test rewritten in place (same count)
- **Total new tests:** 12
- **Full regression:** 732 passed in 33.48s (`SDL_VIDEODRIVER=dummy uv
  run pytest -q`). Matches the pre-deletion count — the rewritten
  contract test replaced its strategic_hud predecessor 1:1.

## Pitfalls Addressed

- **P1 (sub-surface vs parent coord mixing):** Separators and status
  bar drawn on `self.screen` with absolute coords; panels draw into
  their sub-surfaces with (0,0)-relative coords.
- **P4 (subsurface ValueError on resize):** `HUD_WIDTH`, `PANEL_HEIGHT`,
  `PANEL_MINIMAP_W`, `PANEL_WIREFRAME_W`, `PANEL_STATS_W` all imported
  from `openarena_perception.visualization.panels` — no hardcoding.
- **P6 (missing test import update):** Contract test rewritten BEFORE
  `rm strategic_hud.py`. Order-of-operations enforced: test rewrite ->
  `pytest tests/test_hud_schema.py` green -> delete files -> full
  regression still green.
- **P9 (state file stale before bot start):** `draw_tick()` checks
  `state_file.exists()` and renders a "WAITING FOR BOT" placeholder
  plus a status bar message when missing. Verified by
  `test_open_perception_draws_waiting_when_state_missing`.

## Backward Compatibility

- HUD payload consumers: `build_hud_payload` is unchanged — this plan
  only consumed it. All Phase 12-01 kwargs remain optional.
- `item_tour._export_hud` writes the same JSON schema; only comments
  changed.
- Anyone still referencing `strategic_hud.py` from outside the tracked
  codebase will break. The grep sweep confirms no tracked file does.

## Self-Check: PASSED

Verified after SUMMARY write:

- `open_perception.py` — FOUND, contains `class HUDState`, all 7
  verbose fields, `class OpenPerceptionApp`, `_resolve_aas_path`,
  `_peek_state_map_name`, `main`
- `tests/test_open_perception.py` — FOUND, 12 tests all green
- `tests/test_hud_schema.py` — FOUND, rewritten contract test
  `test_contract_build_payload_to_open_perception_load` green
- `strategic_hud.py` — MISSING (deleted per plan)
- `openarena_perception/visualization/demo_wireframe_room.py` — MISSING
  (deleted per plan)
- Commits `2e62f05` and `61d12db` — both FOUND via `git log --oneline`
- Full regression: 732/732 passing (same count pre/post deletion)
- Grep sweep: zero live imports of deleted files in tracked code

## Known Stubs

None. The app renders real data from live `HUDState` instances loaded
from the state file written by `item_tour._export_hud`. The
"WAITING FOR BOT" placeholder is an intentional UX state, not a stub —
it activates only when the state file does not yet exist on disk and
auto-resolves as soon as the bot starts writing.

## Threat Flags

None. This plan is a pure local observability app. The HUD state file
is a local trusted file written by item_tour.py running as the same
user. No network, no subprocess, no user-submitted input beyond the
`--aas` CLI path (filesystem-only, handed verbatim to `parse_aas` which
is the same parser Phase 11 validated).
