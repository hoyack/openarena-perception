---
phase: 12-open-perception-ui
reviewed: 2026-04-11T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - item_tour.py
  - open_perception.py
  - openarena_perception/hud_schema.py
  - openarena_perception/loop.py
  - openarena_perception/navigation/navigator.py
  - openarena_perception/strategy/advisor.py
  - openarena_perception/visualization/hud.py
  - openarena_perception/visualization/panels/__init__.py
  - openarena_perception/visualization/panels/minimap.py
  - openarena_perception/visualization/panels/stats.py
  - openarena_perception/visualization/panels/wireframe.py
  - openarena_perception/visualization/wireframe_room.py
  - tests/test_hud_schema.py
  - tests/test_navigation.py
  - tests/test_open_perception.py
  - tests/test_open_perception_panels.py
  - tests/test_wireframe_hud.py
findings:
  critical: 0
  warning: 5
  info: 8
  total: 13
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-04-11
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Phase 12 ("Open-Perception UI") introduces a unified 1400x700 pygame HUD that composes three panels over the existing HUD JSON contract. The panel code (`minimap.py`, `stats.py`, `wireframe.py`) is well-structured, obeys its documented deduplication and sub-surface contracts, and is backed by thorough panel-isolation tests. The schema extension in `hud_schema.py` is backward-compatible and the end-to-end contract test in `test_hud_schema.py::test_contract_build_payload_to_open_perception_load` is excellent coverage.

No critical bugs or security issues were found. The warnings below are correctness concerns around silent error handling, a misleading schema field, blocking-sleep calls inside code that is also invoked from async contexts, and `hasattr`-based lazy attribute initialization in `Navigator` that makes the object's state hard to reason about. Info items are code-quality notes (micro-style, minor dead paths, cross-session trail growth).

## Warnings

### WR-01: `HUDState.load` swallows all exceptions silently

**File:** `open_perception.py:231-232`
**Issue:** The entire `load()` body is wrapped in `try: ... except Exception: pass`. Any failure — schema mismatch, type coercion errors, OSError mid-read — is completely silenced, leaving `HUDState` in an inconsistent partially-updated state (e.g. `self.health` already overwritten before the exception fires on the items loop below). That makes incidents during Phase 12 integration nearly impossible to debug from the Open-Perception app itself.
**Fix:**
```python
import logging
log = logging.getLogger("open_perception.hud_state")
...
        except (OSError, ValueError, TypeError, KeyError) as exc:
            log.debug("HUDState.load: ignoring malformed state (%s)", exc)
        except Exception:
            log.exception("HUDState.load: unexpected failure")
        return self
```
At minimum, capture the exception into a debug log so operators can grep for schema regressions when a new field lands.

### WR-02: `intent_history[*].ended_at` is set to `started_at`, not the actual end time

**File:** `openarena_perception/hud_schema.py:140`
**Issue:**
```python
payload["intent_history"] = [
    {
        ...
        "ended_at": h.started_at,  # HUD only needs relative ordering
    }
    for h in context.intent_history
]
```
The field name promises end-time but the value is the start-time. Anyone downstream who computes `ended_at - started_at` will always get zero; anyone displaying "when did this intent finish?" will show the start time. The rationalisation ("HUD only needs relative ordering") does not excuse the misnaming — tests in `test_hud_schema.py` never assert on `ended_at`, so the regression is silent.
**Fix:** either drop the field (HUD already has `started_at` + `duration_s` for ordering) or source the real end time:
```python
ended_at = getattr(h, "ended_at", None) or (h.started_at + getattr(h, "duration_s", 0.0))
...
"ended_at": ended_at,
```

### WR-03: `Navigator._steer_toward` uses blocking `time.sleep` on the async event loop

**File:** `openarena_perception/navigation/navigator.py:359, 361`
**Issue:** `_steer_toward` is called from `follow_path`, which is invoked from `item_tour`'s per-tick loop. The tour runs in an asyncio event loop alongside `SpatialAdvisor`, whose HTTP calls to Ollama need the loop to keep cycling. Each `_steer_toward` iteration can block the loop for `max(0.015, abs(delta)/speed) + 0.03` seconds, with up to 3 iterations — that is ~0.1-0.3s of frozen event loop per call, compounding with Phase 12's 10 Hz HUD writer. Advisor thought timeouts and stale-thought rates will creep up under navigation-heavy load.
**Fix:** sleeps in this function existed pre-Phase 12, but Phase 12 now pushes more work onto the same loop (HUD export every 6 ticks, verbose telemetry queries). Consider running the navigator's blocking helpers in `asyncio.to_thread(...)`, or splitting `_steer_toward` into an iterative tick-driven yaw controller that returns after a single correction and is driven by the tick loop. If a refactor is out of scope, document the constraint in `navigator.py` so callers understand the blocking cost.

### WR-04: `Navigator` relies on `hasattr`-based lazy attribute initialization

**File:** `openarena_perception/navigation/navigator.py:92-94, 195-196, 215-216, 273-276, 286-287, 374-375, 705`
**Issue:** The class uses `hasattr(self, '_consecutive_stuck')`, `_path_step_start`, `_last_replan_area`, `_stair_climb_active`, `_stuck_cleanup`, etc. as a lazy-init pattern. This has two real consequences:
  1. A reader cannot enumerate the full state of a `Navigator` from `__init__`; the test file `test_navigation.py::TestNavigatorReplanHook` has to poke private attrs (`nav._path`, `nav._current_area`) to exercise paths that only work after prior side-effects have set them.
  2. `is_climbing_stairs` (line 115) and `is_recovering` (line 718) already protect reads with `getattr`/`hasattr`, but new call sites that access these attributes directly (as `follow_path` does internally at 274, 286) will `AttributeError` on a fresh Navigator until the right branch has executed at least once. The re-plan guard `_in_replan_callback` is correctly initialized in `__init__`; extend the same discipline to the rest.
**Fix:** initialize every mutable attribute in `__init__`:
```python
def __init__(self, ...):
    ...
    self._consecutive_stuck: int = 0
    self._path_step_start: float = 0.0
    self._path_step_area: int = -1
    self._last_replan_area: int = -1
    self._stair_climb_active: bool = False
    self._stair_last_jump: float = 0.0
    self._stuck_cleanup: Optional[Tuple[str, str, float]] = None
```
Then replace `hasattr(self, 'X')` checks with explicit state tests (`if self._stair_climb_active:` etc.).

### WR-05: `advisor.py` markdown fence stripping can produce an empty string

**File:** `openarena_perception/strategy/advisor.py:281-285`
**Issue:**
```python
if text.startswith("```"):
    text = text.split("\n", 1)[1] if "\n" in text else text
    text = text.rsplit("```", 1)[0].strip()
```
When the model returns a single-line fenced response like `` ```{"narrative":"x"}``` `` (no newline), the first conditional leaves `text` unchanged with both fences intact, then `rsplit("```", 1)[0]` strips only the trailing fence, leaving ```` ``` `` or a leading fence that still fails `json.loads`. When the model returns a bare `` ``` ``, both operations can produce an empty string. The surrounding `try` catches `json.JSONDecodeError`, so this is a soft failure — but it counts as a "failed" thought in `thoughts_failed`, inflating error metrics for what is really a formatter quirk.
**Fix:** use a regex strip:
```python
import re
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
...
if text.startswith("```"):
    text = _FENCE_RE.sub("", text).strip()
if not text:
    raise json.JSONDecodeError("empty response after fence strip", text, 0)
```

## Info

### IN-01: `HUDState.trail` is never reset across map changes

**File:** `open_perception.py:212-214`
**Issue:** The trail is appended on every load and truncated at 500 points, but when the bot changes maps (or respawns into a completely different area range) the stale positions stay in the buffer and drag the `_world_to_minimap` bounds wider than the latched minimap view. `MinimapPanel` latches bounds on first draw (Pitfall 10) so the visual impact is bounded, but the trail line drawn in `panels/minimap.py:223-229` will sprawl across the new map until those 500 ticks roll off.
**Fix:** detect map transitions in `HUDState.load()` and clear the trail:
```python
new_map = d.get("map", d.get("map_name", self.map_name))
if new_map != self.map_name:
    self.trail.clear()
self.map_name = new_map
```

### IN-02: `HUDState.load` coerces numeric fields with `int(... or 0)`, silently zeroing valid-but-falsy values

**File:** `open_perception.py:155-161`
**Issue:** `float(d.get("x", self.player_x) or 0.0)` replaces a stored-and-valid `x = 0.0` with `0.0` (harmless) but also wipes any prior `self.player_x` when the new payload has `"x": None`. Combined with WR-01's silent exception handling, an upstream writer that emits `"x": null` will reset the bot to origin on the minimap without any warning.
**Fix:** use explicit None checks:
```python
x = d.get("x")
if x is not None:
    self.player_x = float(x)
```

### IN-03: `build_hud_payload` imports `time` inside the function

**File:** `openarena_perception/hud_schema.py:86`
**Issue:** `import time` inside a function is re-executed every call (cache hit, but still attribute lookup). This function runs at ~10 Hz via `_export_hud`. Cost is negligible but the pattern is inconsistent with the module-level imports above.
**Fix:** move `import time` to the top-level imports.

### IN-04: `MinimapPanel._latch_bounds` accepts strings silently

**File:** `openarena_perception/visualization/panels/minimap.py:69-77`
**Issue:** The `None in (min_x, ...)` check rejects None but not strings or non-finite floats. A `"500.0"` string would skip the None guard and then crash inside `float(...)`. Given WR-01's swallow, the panel would silently stop rendering bounds.
**Fix:** validate types explicitly:
```python
try:
    bounds = (float(min_x), float(max_x), float(min_y), float(max_y))
except (TypeError, ValueError):
    return
if not (math.isfinite(bounds[0]) and math.isfinite(bounds[1])
        and math.isfinite(bounds[2]) and math.isfinite(bounds[3])):
    return
if bounds[1] <= bounds[0] or bounds[3] <= bounds[2]:
    return
self._bounds = bounds
```

### IN-05: `_peek_state_map_name` silently swallows exceptions

**File:** `open_perception.py:420-429`
**Issue:** Same bare-except pattern as WR-01. Any JSON parse or OSError is ignored and the function returns `None`, which then falls through to the hardcoded `maps/oa_dm1.aas` fallback. This is the intended behaviour on a missing file, but log visibility would help when debugging the startup AAS selection.
**Fix:** narrow the exception set to `(OSError, json.JSONDecodeError)` and log a debug message.

### IN-06: `item_tour.py::_export_hud` swallows HUD export failures at DEBUG level

**File:** `item_tour.py:1363-1364`
**Issue:** `except Exception as e: log.debug("HUD export failed: %s", e)`. HUD export is non-critical, but debug-level logging hides ongoing failures during development. Phase 12 adds new kwargs to `build_hud_payload` — if one of them mis-serialises, this log line will not show up in the default INFO logger.
**Fix:** upgrade the first three failures to WARNING, or wrap a rate-limited logger that escalates after N consecutive errors.

### IN-07: `loop.py::_parse_frame` reuses stale HUD dict when `_last_hud` has None values

**File:** `openarena_perception/loop.py:202-211`
**Issue:** `_last_hud` is cached between OCR runs. On the very first call the cached dict is `{"health": None, ...}`, so for the next 29 ticks the consumer sees Nones even if the screen has real HUD content. This is deliberate design (OCR is expensive) and documented, but the Phase 12 verbose HUD exposes these Nones in the stats panel, where they render as literal "None" strings until the first OCR cycle completes.
**Fix:** guard the consumer side (Phase 12 `StatsPanel._draw_vital` already does for `weapon`/`ammo`, extend to `health`/`armor`), or delay the first HUD snapshot until OCR has produced at least one non-None read.

### IN-08: `test_open_perception.py::test_open_perception_aas_autodetect_from_state` uses a confusing monkeypatch

**File:** `tests/test_open_perception.py:162-183`
**Issue:** The test monkeypatches `open_perception.PROJECT_ROOT` to `tmp_path.parent`, then builds `tmp_path.parent / "maps" / "oa_dm1.aas"`. `tmp_path.parent` is shared across all tests in the same worker, so the `target.unlink(missing_ok=True)` in `finally` is the only thing preventing cross-test pollution. If a future refactor moves this test below another one that uses the same parent, the fixture leak will cause a flaky order-dependent failure.
**Fix:** put the fake AAS inside `tmp_path` (not `tmp_path.parent`) and monkeypatch `PROJECT_ROOT` to `tmp_path` so the `maps/` subdir lives in the per-test directory that pytest cleans up automatically.

---

_Reviewed: 2026-04-11_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
