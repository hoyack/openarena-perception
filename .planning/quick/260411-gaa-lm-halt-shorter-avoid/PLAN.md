---
phase: quick
plan: 260411-gaa
type: execute
autonomous: true
files_modified: [item_tour.py]
tags: [tuning, navigation, quick]
---

<objective>
Make `_AVOIDANCE_DURATION` halt-reason-aware in `item_tour.py`. Vision-confirmed halts
keep the existing 500ms hold (distance-gain matters). Learned-map-only halts drop to
150ms so a single false-positive look-ahead trip nudges the bot off the wall instead
of rotating it 30-60° into a partial circle.

Fix path D from `.planning/debug/bot-wall-gazing-regression.md`. Tuning knob only —
no refactor, no tests, no rename.
</objective>

<context>
@item_tour.py
@.planning/debug/bot-wall-gazing-regression.md

Current state verified:
- `item_tour.py:339-341` declares `_avoidance_until`, `_avoidance_hint`, `_AVOIDANCE_DURATION = 0.5`
- `item_tour.py:707-713` holds the hint on subsequent ticks while `now < _avoidance_until`
- `item_tour.py:784-788` commits: `_avoidance_hint = hint; _avoidance_until = now + _AVOIDANCE_DURATION`
- `halt_reason` in scope at commit site; values from `_check_proactive_wall`:
  - `"vision"` — vision wall-score trigger
  - `"learned_map"` — on-disk WALL cell look-ahead trigger
  - `"visual_pin"` — set at line 729 when frame-still streak fires
- Vision-confirmed = `"vision"` or `"visual_pin"` (frame-hash evidence)
- Learned-map-only = `"learned_map"`
- Unknown/future reasons → default to VISION duration (safer, preserves current behavior)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Split _AVOIDANCE_DURATION into VISION (0.5s) and LM (0.15s) constants</name>
  <files>item_tour.py</files>
  <action>
In `item_tour.py` around line 341, replace the single line:

    self._AVOIDANCE_DURATION = 0.5    # seconds

with two constants (keep the surrounding Fix A comment block intact):

    # Fix D (.planning/debug/bot-wall-gazing-regression.md):
    # Halt-reason-aware avoidance hold. Vision-confirmed halts keep the full
    # 500ms (distance-gain from the wall matters). Learned-map-only halts drop
    # to 150ms so a noisy forward-look-ahead trip nudges the bot instead of
    # rotating 30-60 degrees per fire.
    self._AVOIDANCE_DURATION_VISION = 0.5   # seconds — vision/visual_pin halts
    self._AVOIDANCE_DURATION_LM = 0.15      # seconds — learned_map-only halts

Then at the commit site (around line 788), replace:

    self._avoidance_hint = hint
    self._avoidance_until = now + self._AVOIDANCE_DURATION

with halt-reason-aware selection:

    self._avoidance_hint = hint
    # Fix D: learned-map-only halts use a shorter hold (nudge, not spin).
    # Vision-confirmed reasons ("vision", "visual_pin") keep the full duration.
    if halt_reason == "learned_map":
        self._avoidance_until = now + self._AVOIDANCE_DURATION_LM
    else:
        self._avoidance_until = now + self._AVOIDANCE_DURATION_VISION

Do NOT touch the `if now < self._avoidance_until` gate at line 707-713 —
the hold mechanism is unchanged, only the duration value differs.

Do NOT rename, refactor, or add new helpers. Do NOT add tests. Do NOT touch
any other file.
  </action>
  <verify>
    <automated>cd /home/hoyack/openarena-perception &amp;&amp; grep -n "_AVOIDANCE_DURATION" item_tour.py</automated>
  </verify>
  <done>
Exactly three matches in `item_tour.py`:
- `_AVOIDANCE_DURATION_VISION = 0.5` definition
- `_AVOIDANCE_DURATION_LM = 0.15` definition
- Commit site using `_AVOIDANCE_DURATION_LM` in the `learned_map` branch and `_AVOIDANCE_DURATION_VISION` in the else branch.

No leftover bare `_AVOIDANCE_DURATION` reference (without suffix). Python file parses (`python -c "import ast; ast.parse(open('item_tour.py').read())"` exits 0).
  </done>
</task>

<task type="auto">
  <name>Task 2: Confirm pytest baseline still green</name>
  <files></files>
  <action>
Run the full pytest suite. Expected: 774 passing (unchanged baseline). Any new
failure, error, or collection issue is a blocker — the edit must be reverted or
fixed. This is a pure tuning change; the existing test suite does not cover
avoidance-duration values, so nothing should move.
  </action>
  <verify>
    <automated>cd /home/hoyack/openarena-perception &amp;&amp; uv run pytest -q 2>&amp;1 | tail -20</automated>
  </verify>
  <done>
pytest reports the same passing count as the pre-edit baseline (774 passed,
or whatever the current baseline is at the time of execution). No new
failures, no new errors, no new warnings attributable to this change.
  </done>
</task>

</tasks>

<success_criteria>
- Two constants `_AVOIDANCE_DURATION_VISION = 0.5` and `_AVOIDANCE_DURATION_LM = 0.15` defined in `__init__`.
- Commit site at ~line 788 selects duration by `halt_reason` (learned_map → LM, else → VISION).
- Hold mechanism at line 707-713 untouched.
- Inline comment references `.planning/debug/bot-wall-gazing-regression.md` fix path D.
- `uv run pytest -q` baseline unchanged.
- Commit message: `tune(item_tour): shorter avoidance hold for learned-map-only halts`
</success_criteria>
