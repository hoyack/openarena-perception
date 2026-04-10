---
phase: 10-intent-system-and-hud-companion
plan: 01
subsystem: hud
tags: [refactor, scaffolding, hud, runtime-dirs]
requires: []
provides:
  - openarena_perception.hud_schema (centralized STATE_FILE, build_hud_payload, write_hud_state, ensure_runtime_dirs)
  - ./tmp/ runtime directory (gitignored, .gitkeep tracked)
  - ./logs/ runtime directory (gitignored, .gitkeep tracked)
affects:
  - item_tour.py
  - openarena_perception/strategic_brain.py
  - strategic_hud.py
tech-stack:
  added: []
  patterns:
    - "Project-root anchoring via Path(__file__).resolve().parents[1]"
    - "Atomic write via tmp + os.replace, factored into hud_schema.write_hud_state"
    - "Back-compat class-attribute alias (StrategicBrain.STATE_FILE) for legacy callers"
key-files:
  created:
    - openarena_perception/hud_schema.py
    - tests/test_hud_schema.py
    - tmp/.gitkeep
    - logs/.gitkeep
  modified:
    - .gitignore
    - item_tour.py
    - openarena_perception/strategic_brain.py
    - strategic_hud.py
decisions:
  - "STATE_FILE anchors to PROJECT_ROOT (parents[1] of hud_schema.py), avoiding the cwd trap"
  - "strategic_hud.py stays standalone -- duplicates path constant via pathlib instead of importing openarena_perception"
  - "build_hud_payload always emits timestamp and map_name; legacy keys flow through extras dict"
metrics:
  duration: ~25min
  tasks: 2
  files_created: 4
  files_modified: 4
  tests_added: 9
  completed: 2026-04-10
---

# Phase 10 Plan 01: Directory cleanup + hud_schema.py centralization Summary

Centralized the HUD JSON writer into `openarena_perception/hud_schema.py`, moved the runtime state file from `/tmp/` to `<project>/tmp/`, and migrated both writers (`item_tour.py`, `strategic_brain.py`) plus the standalone reader (`strategic_hud.py`) to the new path -- without changing the legacy schema seen by the HUD reader.

## Outcome

- `hud_schema.STATE_FILE` resolves to `/home/hoyack/openarena-perception/tmp/oa_hud_state.json` regardless of the caller's cwd (Pitfall 5 closed).
- `StrategicBrain.STATE_FILE` is a class-level alias of `hud_schema.STATE_FILE` so any future code that touches the class attribute keeps working (Pitfall 6 closed).
- `strategic_hud.py` remains a self-contained executable: it duplicates only the path constant via `pathlib`, no `openarena_perception` import (Pitfall 1 honored).
- `tmp/` and `logs/` directories now exist at the repo root with `.gitkeep` stubs; `.gitignore` uses `tmp/*` + `logs/*` patterns so the negation `!tmp/.gitkeep` is honored by git.
- `ItemTour.__init__` calls `ensure_runtime_dirs()` so the runtime directories exist before the first HUD export tick.
- 9 unit tests in `tests/test_hud_schema.py` cover anchoring, build, atomic write, and the deque-not-allowed contract (Pitfall 7 documented).

## Tasks Completed

| # | Task                                                            | Commit  |
| - | --------------------------------------------------------------- | ------- |
| 1 | Create hud_schema.py, runtime directories, .gitignore, tests    | af67dea |
| 2 | Migrate item_tour, strategic_brain, strategic_hud to new path   | 21b97b5 |

## Verification

| Check                                                              | Result        |
| ------------------------------------------------------------------ | ------------- |
| `uv run pytest tests/test_hud_schema.py -x -q`                     | 9 passed      |
| HUD-scoped suite (`-k "hud or strategic_brain or item_tour"`)      | 71 passed     |
| `uv run ruff check openarena_perception/hud_schema.py`             | All checks passed |
| `import item_tour, strategic_brain, strategic_hud`                 | OK            |
| `StrategicBrain.STATE_FILE == hud_schema.STATE_FILE`               | OK            |
| Grep for `/tmp/oa_hud_state` in touched files                      | Zero literal references (only `./tmp/` docstrings) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `.gitignore` pattern needed `tmp/*` not `tmp/`**
- **Found during:** Task 1, first commit attempt
- **Issue:** `git add tmp/.gitkeep logs/.gitkeep` failed because the `tmp/` and `logs/` directory-style ignores cause git to refuse to recurse into them — the `!tmp/.gitkeep` negation never gets evaluated.
- **Fix:** Changed `.gitignore` patterns from `tmp/` / `logs/` to `tmp/*` / `logs/*`. Git now ignores directory contents but evaluates the negation, letting the stub files be tracked.
- **Files modified:** .gitignore
- **Verification:** `git check-ignore -v tmp/.gitkeep` reports the `!` rule winning.

**2. [Rule 1 - Bug] Cleanup unused `json` import in strategic_brain.py**
- **Found during:** Task 2, ruff check
- **Issue:** After delegating `_export_hud` to `hud_schema.write_hud_state`, the `json.dump`/`os.replace` block was removed but `import json` stayed. ruff F401.
- **Fix:** Removed the unused `import json`. (`os` is still used at line 433 for `os.environ` lookups.)
- **Files modified:** openarena_perception/strategic_brain.py
- **Commit:** 21b97b5

### Schema additive deviation

The plan's success criteria says the HUD JSON output should be "byte-identical to pre-plan." Strict reading of `build_hud_payload` per spec — `payload = {"timestamp": time.time(), "map_name": map_name}` — means the output now contains two keys (`timestamp`, `map_name`) that the old `_export_hud` writers did not emit. Both writers also pass their full legacy field set via `extras=`, so every legacy key (including the legacy `"map"` key, which is distinct from `"map_name"`) is preserved verbatim.

This is additive, not breaking: `strategic_hud.py` reads via `dict.get(...)` with defaults, so it ignores the new keys. No legacy reader behavior changes. The deviation was unavoidable given the plan's explicit `build_hud_payload` signature.

### Pre-existing test flake (out of scope)

`tests/test_humanize.py::test_accuracy_cap_enforced_in_aim_controller` is randomized and produced a boundary failure (`0.95 < 0.95`) on one of the suite runs. Re-running and stash-baseline runs confirm it's unrelated to this plan and is a pre-existing flake. Logged in `deferred-items.md` if/when one exists; otherwise noted here for the verifier.

## Threat Surface

No new network surface, auth path, file access patterns, or schema changes at trust boundaries. Threat model unchanged.

## Notes for Plan 10-02

`build_hud_payload` is intentionally a thin pure function. Plan 10-02 will:
1. Add a `context: BotContext | None = None` keyword-only parameter
2. When `context` is provided, emit `intent`, `intent_history`, `problem_history`, `path_progress`, `area_history`, `is_paused_for_assess`, `threat_flag` keys
3. Convert `context.intent_history` and `context.problem_history` deques to lists (Pitfall 7) inside `build_hud_payload` so callers don't have to

The migration in this plan keeps both writers passing legacy fields via `extras=` — Plan 10-02 can add a single `context=self._bot_context` argument to each call site without disturbing the legacy fields.

## Self-Check: PASSED

- openarena_perception/hud_schema.py: FOUND
- tests/test_hud_schema.py: FOUND
- tmp/.gitkeep: FOUND
- logs/.gitkeep: FOUND
- Commit af67dea: FOUND
- Commit 21b97b5: FOUND
- 9/9 hud_schema tests passing
- 71/71 HUD-scoped tests passing
