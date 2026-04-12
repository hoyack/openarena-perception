# Phase 13 Verification Report — Partial

**Date:** 2026-04-11
**Verifier:** human (live) + orchestrator (static analysis)
**Baseline commit:** 881e508 (post-quick-task-260411-gaa)
**Status:** BLOCKED on 1 integration gap — requires gap-closure plan

## Automated Status

- `uv run pytest -q` → **775 passed**, no regressions vs Phase 12.1 baseline (743)
- All 6 Phase 13 plan commits present (1d1bcc7..d49899b)
- All 12 room-perception requirements (RP-01..RP-12) marked complete in REQUIREMENTS.md by plan executors

## Live Verification Status

Ran `uv run python item_tour.py --no-vision` on `oa_dm1` with ioquake3 running. User observed the minimap for ~60 s.

**User report:** "clean minimap with no red stubs, but no green walls either"

This single observation exposes a cascading integration defect. The user saw:
- ✅ Red `wall_segments` stub block removed (RP-11 partial)
- ❌ No bright-green fitted wall lines
- ❌ No amber corner dots
- ❌ No blue room polygon fills / outlines
- ❌ Stats panel rows 10/11 (`room:` / `room_items:`) stayed at placeholder `----`

## Gap Analysis

### GAP-1: `LearnedMap.fit_rooms()` has zero callers in the live tour loop

**Evidence:**
```
grep -rn "fit_rooms\|note_item" item_tour.py openarena_perception/
→ only the method definitions in learned_map.py; no call sites
```

**Impact:** Plan 13-05 implemented `fit_rooms()` correctly and Plan 13-05's unit tests exercise it directly via `lm.fit_rooms()` calls in the test file. But **no production code path calls it**. In the live tour:
- Raycast point cloud accumulates correctly (`_record_raycast()` at learned_map.py:212)
- `fit_rooms()` is never invoked → `_fitted_walls_per_floor`, `_corners_per_floor`, `_rooms_per_floor`, `_partial_rooms_per_floor`, `_doorways_per_floor` all stay empty lists
- `export_for_hud()` emits empty `fitted_walls / corners / rooms / doorways` keys
- `current_room_id()` always returns None (no rooms to test against)
- `MinimapPanel` falls through to the Phase 12.1 backward-compat render path
- `StatsPanel` rows 10/11 render placeholder because `current_room_id` is None

**Requirements downgraded:**
- **RP-09** (LearnedMap.fit_rooms integration into the tick loop) — claimed complete by plan 13-05 summary but actually not wired. Marked back to **in-progress**.
- **RP-11** (live minimap visual verification on oa_dm1) — cannot pass until fit_rooms() is being called. Marked back to **in-progress**.
- **RP-12** partial — HUD schema kwargs work in unit tests but in live runs `current_room_id` is always None, so stats panel rows 10/11 never populate. Marked **at-risk**.

### GAP-2: `LearnedMap.note_item(name, x, y)` has zero callers

**Evidence:** Same grep. Defined in learned_map.py:729, never called.

**Impact:** Per-room `items_seen` list is always empty. `export_for_hud()` emits `current_room_items=[]`. Stats panel row 11 can never display real item summaries.

**Requirements affected:**
- **RP-09** (item ingestion into rooms via pointPolygonTest) — tested directly in unit tests but not wired into the item observation pathway. Marked back to **in-progress**.

### GAP-3: `RoomInferrer` over-emits duplicate + noise rooms on real data

**Evidence (measured 2026-04-11 from live `oa_dm1.json` after Plan 13-07 wired fit_rooms):**
```
fitted_walls[floor 0] = 23     (clean: min length 633u, median 810u, median support 127, median conf 0.61)
fitted_walls[floor 1] = 11
corners     [floor 0] = 30
corners     [floor 1] = 0      ← floor 1 walls never intersect under the 64u endpoint-proximity threshold
rooms       [floor 0] = 65     ← ~13× too many
rooms       [floor 1] = 0
```

Sampled rooms on floor 0 show near-identical bounds (duplicate detection):
```
id=1  verts=8  area=5055   bounds=[-251..535, 1342..1678]
id=2  verts=8  area=5053   bounds=[-254..535, 1342..1678]   ← duplicate of #1
id=3  verts=7  area=5210   bounds=[-254..535, 1342..1678]
id=4  verts=5  area=9379   bounds=[-250..447, 1637..1678]   ← subset of above
id=5  verts=7  area=11010  bounds=[-247..447, 1637..1678]
```

**Root causes:**

1. **Dedup is by wall-ID tuple, not spatial equivalence.** `room_inferrer.py:55` / `154` dedup via `tuple(sorted(cycle))` where `cycle` is a list of wall IDs. Different wall subsets of the same physical room produce different tuples, so the same space is emitted multiple times.
2. **`MIN_ROOM_AREA = 4096`** (= 64×64) is way too loose for oa_dm1 architecture. Real rooms are ~200×200+ = 40000+ sq units. 4096 lets noise cycles through.
3. **`max_cycle_length = 8`** is too generous. 7–8 vertex "rooms" with area ~5000 mean ~35u average side length — that is NOT a room, that's a zig-zag 8-cycle hopping adjacent corners.
4. **No preference for shortest / simplest cycle** when multiple cycles yield the same vertex set. Current enumeration emits every valid simple cycle.
5. **Floor 1 is dark:** 11 walls, 0 corners, 0 rooms. `CornerDetector.endpoint_max_dist = 64u` (the value set inside `LearnedMap.fit_rooms()`) is still under-shooting floor 1 wall intersections.

**Impact on requirements:**
- **RP-07** (room inference) — passes unit tests on synthetic 4-corner rectangles but fails on real `oa_dm1` data. Marked **in-progress** pending fix.
- **RP-11** (live visual) — minimap shows ~65 overlapping translucent polygons and corner dots, user reported "strange vector shade / plex with connected dots". Pipeline is wired and rendering, but output is noisy enough to read as broken.

**Scope for gap-closure plan:**

Surgical fix in `openarena_perception/navigation/room_perception/room_inferrer.py`:

1. **Spatial dedup** — after building `polygon_vertices`, dedup by a spatial signature: sorted tuple of corner vertex positions rounded to ~4u, OR sorted tuple of corner IDs participating in the cycle. Two cycles producing the same vertex set (or centroid + area within ε) are duplicates regardless of wall-id sequence.
2. **Raise `MIN_ROOM_AREA` 4096 → 20000** (parameterize; default 20000). ~141×141 is the minimum credible room size.
3. **Reduce `max_cycle_length` 8 → 6.**
4. **Prefer the shortest / lowest-perimeter cycle** per vertex set when multiple orderings yield the same corner set.

Additional tuning in `LearnedMap.fit_rooms()`:

5. **Bump `CornerDetector(endpoint_max_dist=...)` from 64u → 96u** only at the live call site (Plan 13-05 already overrides the 32u default to 64u; this just widens further for floor-1-style sparse walls). Do NOT change the `CornerDetector` unit-test default of 32u.

**Acceptance criteria for this gap:**
- After the fix, live tour on `oa_dm1` produces ≤ ~10 rooms on floor 0 (down from 65), with no two rooms sharing centroid within 32u.
- Floor 1 produces > 0 corners and > 0 rooms.
- Minimap visually shows distinct room polygons that map to recognizable architecture, not a "plex of overlapping fills".
- No regression on existing `room_inferrer` unit tests. If the raised `MIN_ROOM_AREA` default breaks synthetic test fixtures, either (a) pass the old value explicitly in tests, or (b) update fixtures to match realistic areas.

### GAP-3 Attempt 1: Plan 13-08 (REVERTED in commit cd65788)

Plan 13-08 applied the 5-part fix above (spatial corner-ID dedup, MIN_ROOM_AREA 20000, max_cycle_length 6, shortest-perimeter preference, endpoint_max_dist 96u). **The regression got worse, not better.** Measured 2026-04-11 13:32 after a full tour on clean state:

```
fitted_walls[floor 0] = 15     (clean: 279u min, 746u median, 1246u max)
corners    [floor 0] = 45      (up from 30 pre-13-08, due to endpoint_max_dist 64→96)
rooms      [floor 0] = 487     ← 7.5× WORSE than pre-13-08 (was 65)
centroid-pairs within 32u = 8411
rooms      [floor 1] = 0       ← unchanged (only 137 raycasts accumulated)
```

Sample rooms have near-identical bounds but different corner ID tuples:
```
id=1  verts=6  area=274086  bounds=[-288.39..531.57, 682.62..1627.51]
id=3  verts=6  area=272301  bounds=[-288.39..531.57, 680.49..1627.51]  ← y differs by 2u
id=5  verts=5  area=287865  bounds=[-287.99..531.57, 682.62..1628.79]  ← x differs by 0.4u
```
Areas 263k–561k sq units = cycles spanning 500×1000+ units, i.e. the entire map, not individual rooms.

**Root cause of the 13-08 regression — diagnosis revised:**

1. **CornerDetector emits near-duplicate corners.** Two walls nearly intersecting produce multiple corner candidates at slightly different midpoints (because the "nearest endpoint pair" can vary by a few units between wall pairs). With 15 walls on floor 0 and the relaxed `endpoint_max_dist=96`, 45 corners fall into roughly 10–15 spatial clusters of 2–4 corners each. Every such near-duplicate is assigned a different corner ID.
2. **Spatial dedup keyed on sorted CORNER IDs was therefore useless.** Two cycles using structurally "the same" corner at position (x, y) but landing on different corner IDs (because the IDs are distinct near-duplicates) produce different ID tuples → both emitted. The dedup passes but doesn't actually dedup.
3. **`endpoint_max_dist 64 → 96` made the over-generation worse**, not better. 96u is too loose for floor 0's dense wall geometry; it caused C(15,2) = 105 wall pairs to emit corners where previously only ~30 did.
4. **No upper bound on room area.** Cycles of length 6 in an over-connected graph happily hop across the entire map and produce 500k sq unit "rooms" that are not architectural rooms at all.
5. **Unit tests did not catch this** because they use small (≤ 10 corner) synthetic graphs with well-separated corners — the corner-duplication regime is not exercised in the test suite.

**Revised fix hypothesis for GAP-3 Attempt 2 (Plan 13-09):**

The dedup must be **spatial at the corner level, not at the cycle level**, OR the room dedup must use a **centroid-cell signature**, not corner IDs. Probably both.

1. **Spatial corner merge at source.** In `CornerDetector.detect()`, after initial pair enumeration, merge any two corners within a radius (~16u) into a single corner — midpoint of their positions, union of wall refs, average angle and confidence. Kills the near-duplicate fleet before RoomInferrer ever sees it.
2. **Revert `endpoint_max_dist 96 → 64`** in `LearnedMap.fit_rooms()`. The 96u value was the 13-08 mistake; 64u is the Plan-13-05 tuned value that produced 30 clean corners. Floor-1 sparseness (11 walls, 0 corners) is a **data scarcity** problem, not a proximity-threshold problem — it'll resolve when the raycast cloud gets bigger.
3. **Centroid-cell dedup in RoomInferrer.** After building `polygon_vertices` + `area`, compute centroid. Bucket by `(round(cx/16), round(cy/16))`. Keep **smallest-area** room per bucket (tightest cycle = most architectural). Orthogonal to any ID-based dedup; robust against upstream corner noise.
4. **Add `MAX_ROOM_AREA` cap** (~200000 sq units ≈ 450×450). Hard-reject anything larger — those are map-spanning cycles, not rooms.
5. **Keep** Plan 13-08's `MIN_ROOM_AREA = 20000`, `max_cycle_length = 6`, and shortest-perimeter-per-set logic. They are independently sensible and were not the cause of the regression.
6. **New regression test.** Construct a synthetic scenario that reproduces the 13-08 blowup in principle: many walls within an over-connected graph with intentional near-duplicate corners. Assert that `CornerDetector` merges them and `RoomInferrer` emits ≤ K rooms for a synthetic room count K. This fixture should have CAUGHT the 13-08 regression before live verification.

### GAP-3 Attempt 2 acceptance criteria

Same live behaviour as Attempt 1's criteria (≤ ~10 rooms on floor 0, no centroid pairs within 32u, distinct recognizable polygons), plus:
- `fitted_walls` output is the **same** as the no-13-08 state (15 walls) — because LineFitter is not being touched.
- Corner count after spatial merge is in the 10–25 range (not 45).
- Existing unit tests unchanged unless the synthetic graphs now collide with corner-merge radius (in which case, adjust fixtures to keep corners ≥ 20u apart).
- New regression test for the over-connected graph passes.

## Non-Gap Observations

### Pre-existing Phase 12.1 motion pathology (surfaced, not caused, by Phase 13)

During live verification the bot exhibited excessive walking / spinning / wall-gazing. Root cause investigated in `.planning/debug/bot-wall-gazing-regression.md`:

1. A biased `oa_dm1.json` with 1,958 `edge_failures` + 118 stale WALL cells (resolved for this verification run by resetting the file; backup at `~/.openarena/learned_maps/oa_dm1.json.pre-debug-20260411-113218.bak`).
2. `item_tour.py` 500ms avoidance commitment holding rotation actions longer than necessary (fixed via quick task `260411-gaa-lm-halt-shorter-avoid`, commit 881e508 — now halt-reason-aware: 150ms for learned-map-only halts, 500ms for vision-confirmed halts).

Both are tracked independently of Phase 13. The underlying root fixes (edge_penalty decay, WALL cell decay, telemetry) from debug-report fix paths B/C/E are deferred to a follow-up phase, **not** this gap-closure plan.

## Gap-Closure Scope

**Single plan required.** Slug suggestion: `13-07-PLAN.md` marked `gap_closure: true` in frontmatter.

**In scope:**
1. Add a `fit_rooms()` call in `item_tour.py` inside the tick loop, right after `self.learned_map.update(...)` at ~item_tour.py:631. The `LineFitter` cadence gate (3s / 500-point / explicit) makes unconditional per-tick calls safe; planner may still choose a coarser guard if profiling suggests it.
2. Add `note_item(name, x, y)` calls at the site(s) where items enter tour state. Likely hooks: ReactiveAgent's item-observed callback, the item-waypoint-targeting code in item_tour.py, or wherever `self.agent`'s perception layer surfaces item positions. Planner must trace this and document the chosen hook site.
3. Live re-verification on `oa_dm1` after the plan lands. Acceptance: bright-green fitted walls + amber corner dots + blue room polygons appear on the minimap within 10–15 s of tour start; stats rows 10/11 show real `room:` and `room_items:` values when the bot enters a fitted room.

**Out of scope (explicitly excluded):**
- Avoidance-duration logic (already fixed).
- edge_penalty decay / WALL cell decay / telemetry (separate follow-up phase).
- Any changes to `learned_map.py` `fit_rooms()` or `note_item()` implementations — both are correct; the gap is purely missing callers.
- New unit tests unless the planner identifies a specific regression risk. Live eyeball IS the verification gate.

## Acceptance Criteria

After the gap-closure plan lands and is executed:
- [ ] `grep -n "fit_rooms\|note_item" item_tour.py` shows at least one call site for each.
- [ ] `uv run pytest -q` stays at or above 775 passing, zero new failures.
- [ ] Live `item_tour.py --no-vision` on `oa_dm1` shows bright-green fitted walls + amber corners + blue room polygons within 10–15 s.
- [ ] Stats rows 10/11 display real values when the bot is inside a fitted room.
- [ ] User visually approves via "approved" reply.
- [ ] RP-09, RP-11, RP-12 re-marked complete in REQUIREMENTS.md only after live approval.

Then and only then: phase verifier runs, STATE.md / ROADMAP.md finalize Phase 13, milestone v1.0 closes.
