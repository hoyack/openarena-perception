---
phase: 13-room-perception-and-wall-reconstruction
plan: 07
subsystem: navigation
tags: [navigation, integration, gap-closure, checkpoint]
gap_closure: true
requirements: [RP-09, RP-11, RP-12]
status: AWAITING LIVE HUMAN VERIFICATION
dependency-graph:
  requires: [13-05, 13-06]
  provides: [live fit_rooms caller, live note_item caller]
  affects: [item_tour.py tick loop]
tech-stack:
  added: []
  patterns: [defensive try/except around optional learned_map calls]
key-files:
  created: []
  modified:
    - item_tour.py
decisions:
  - "Hook fit_rooms() per-tick inside the existing `if self.agent.nav.pos and gs.frame is not None:` gate immediately after learned_map.update() — matches the single tick on which a newly-appended raycast could affect the fit; LineFitter cadence gate makes this microsecond-cheap on no-op ticks."
  - "Hook note_item() per-tick driven by self._route (not a ReactiveAgent callback) — self._route is a stable AAS-derived (name,x,y,z) list already in scope; per-tick dedup is handled inside note_item; avoids fabricating an on_item_seen callback that doesn't exist."
  - "Single try/except wraps BOTH calls mirroring _check_proactive_wall pattern — learned_map is optional, must never crash tick."
metrics:
  duration: ~5 min
  tasks_completed: 1
  tasks_total: 2  # Task 2 is a live human-verification checkpoint
  files_touched: 1
  tests_before: 775
  tests_after: 775
  completed_date: 2026-04-11
---

# Phase 13 Plan 07: Wire fit_rooms + note_item into item_tour tick loop — Summary

Gap-closure plan that adds the missing production callers for `LearnedMap.fit_rooms()` and `LearnedMap.note_item()`. Both methods were correct and unit-tested in plan 13-05 but had zero call sites in `item_tour.py`, so the live tour never fitted walls, never inferred rooms, and never populated stats rows 10/11. GAP-1 and GAP-2 from `13-VERIFICATION.md`.

## Status: AWAITING LIVE HUMAN VERIFICATION

Task 1 (code change) is committed. Task 2 (live eyeball on `oa_dm1`) is a blocking checkpoint. **Until the user replies "approved", RP-09, RP-11, RP-12 remain in-progress and Phase 13 is not yet ready for `/gsd-verify-work`.**

## Call Sites Added

Both inside the existing `if self.agent.nav.pos and gs.frame is not None:` block in `TourRunner._tick()`, immediately after the existing `self.learned_map.update(...)` call (item_tour.py lines 637-639):

```python
try:
    self.learned_map.fit_rooms()
    for _route_entry in self._route:
        _name = _route_entry[0]
        _ix = float(_route_entry[1])
        _iy = float(_route_entry[2])
        self.learned_map.note_item(_name, _ix, _iy)
except Exception:
    pass  # room perception optional; never crash the tick
```

Post-edit grep:

```
642:            # using the freshly-updated raycast cloud. fit_rooms() is
650:                self.learned_map.fit_rooms()
652:                # note_item() has internal name-dedup and early-returns
660:                    self.learned_map.note_item(_name, _ix, _iy)
```

## Hook-Site Rationale

**Why per-tick (not gated by a timer or a new fit_now API):**
- `LineFitter.fit()` is already internally cadence-gated (3s elapsed OR 500 new points OR explicit force). On a "not yet" tick `fit_rooms()` is effectively a no-op that costs microseconds — cheaper than adding our own cadence gate at the call site.
- `fit_rooms()` also early-returns if the raycast cloud has fewer than 20 samples, so the first seconds of a tour are silent.

**Why route-driven note_item (not a ReactiveAgent on_item_seen callback):**
- `self._route` is a stable `(name, x, y, z)` list built once at tour start (item_tour.py:484) from the AAS item entity list. We already have every tour item's position in scope.
- Rooms don't exist when `self._route` is first built (raycast cloud is empty), so a startup-only `note_item()` pass would route zero items. Per-tick invocation is self-correcting: as `fit_rooms()` produces rooms 10-15 s in, the next per-tick `note_item()` loop fills `items_seen` for each room.
- `note_item()` has internal name-dedup AND early-returns when `rooms` is empty — per-tick cost on a ~20-item route is essentially zero until rooms exist, then trivially small (cv2.pointPolygonTest ≈ microseconds per test).
- The alternative (ReactiveAgent item-observed callback) was rejected because `ReactiveAgent.items` is populated at init from the AAS file, not from per-tick vision — there is no `on_item_seen` event to subscribe to. The tour route IS the observation stream.

**Defensive wrapping:** Single `try/except Exception: pass` mirrors the canonical learned_map pattern at item_tour.py lines ~1240-1248 (`_check_proactive_wall`). The tick loop MUST NEVER crash because of an optional subsystem.

## Verification

| Check | Result |
|---|---|
| `grep -n "fit_rooms\|note_item" item_tour.py` | 4 matches (2 code sites + 2 comments) — PASS |
| `uv run python -c "import ast; ast.parse(open('item_tour.py').read())"` | OK — PASS |
| `uv run pytest -q` | 775 passed in 66.01s (baseline 775) — PASS, zero regressions |
| Live eyeball on `oa_dm1` | **PENDING** — awaiting user |

## Deviations from Plan

None. Executed exactly as planned in `13-07-PLAN.md`. Both call sites landed at the locked hook site; single try/except wraps both; no modifications to `learned_map.py`; no new unit tests.

## Commits

| Task | Commit | Message |
|---|---|---|
| 1 | `e34c1ef` | feat(13-07): wire fit_rooms + note_item into item_tour tick loop |

No final metadata commit was made (and none will be) until live verification signs off. STATE.md, ROADMAP.md, and REQUIREMENTS.md are intentionally untouched.

## Requirements Status

**RP-09, RP-11, RP-12 remain in-progress.** They close ONLY after the user replies "approved" to the Task 2 checkpoint. The orchestrator will then:

1. Flip RP-09, RP-11, RP-12 to complete in `.planning/REQUIREMENTS.md`.
2. Advance STATE.md / ROADMAP.md to mark Phase 13 ready for `/gsd-verify-work`.
3. Rerun `/gsd-verify-work` on Phase 13 to finalize the phase and close milestone v1.0.

This plan executor deliberately does NOT perform any of the above. See orchestrator prompt contract.

## Self-Check: PASSED

- `item_tour.py` modified at lines 637-664 — FOUND (grep shows 4 fit_rooms/note_item matches)
- Commit `e34c1ef` — FOUND in `git log`
- `13-07-SUMMARY.md` — being written (this file)
- REQUIREMENTS.md — untouched (intentional)
- STATE.md — untouched (intentional)
- ROADMAP.md — untouched (intentional)

## Known Stubs

None. The two newly-added call sites are real, route-driven, and gate-guarded.

## Threat Flags

None. No new network surface, auth path, file access, or schema change. This plan only adds two in-process method calls behind an existing positional/frame guard and a defensive try/except.
