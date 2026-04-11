# Phase 13: Room Perception and Wall Reconstruction — Research

**Researched:** 2026-04-11
**Domain:** 2D point-cloud line fitting, computational geometry, room inference
**Confidence:** HIGH (stack already in-tree — OpenCV 4.13.0 + numpy 2.4.4 verified on this machine)

## Summary

Phase 13 replaces the 500-stub `_record_wall` hack in `learned_map.py` with a proper perception-to-geometry pipeline: raycast capture → line fitting → corner detection → room polygon inference → per-room knowledge log → CAD-style minimap rendering. The good news is every library we need is already a project dependency (`opencv-python-headless` for `HoughLinesP`/`fitLine`/`pointPolygonTest`, `numpy` for the point cloud math). **No new runtime dependencies required.**

The hard calls for the planner are (1) **RANSAC vs Hough** — I recommend **custom RANSAC on the raw point cloud**, not Hough on a rasterized bitmap, because RANSAC handles the non-uniform density of wall hits better and gives us per-wall support counts for free; (2) **hand-rolled simple cycle enumeration** on the corner graph instead of adding `networkx`, because cycles are short (≤8 walls) and we want zero new deps; and (3) **versioned JSON schema bump to v3** on `learned_map.json` with explicit top-level fields (`raycasts_per_floor`, `fitted_walls`, `corners`, `rooms`, `doorways`) — Phase 12's v2 loader already tolerates unknown keys so forward-compat is cheap.

**Primary recommendation:** Custom seeded RANSAC (numpy-only, deterministic via `np.random.default_rng(seed)`) for line fitting, hand-rolled DFS cycle detection for room inference, `cv2.pointPolygonTest` for point-in-polygon, schema v3 with graceful v2 fallback, line-fitting runs at 2–5 Hz cadence OR on explicit `fit_now()` — never per tick.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Data capture (replaces current `_record_wall`)**
- Replace `_record_wall()` perpendicular stubbing. Current 64-unit cross-strokes are unusable as architectural geometry.
- New approach = store **raycasts** — each observation is `(origin_x, origin_y, origin_z, dir_angle_deg, hit_x, hit_y, hit_z, confidence, timestamp)`. Call them "wall hits" or "raycast samples".
- Sources of raycast observations — at minimum the existing `wall_ahead` + `wall_score` from the vision forward-scan. Also consider perimeter scan from stuck-recovery, optional deliberate side-scan during idle ticks. Must be reusing existing perception outputs, not adding new vision work.
- Point cloud is per-floor (reuse Phase 12.1 floor threshold) and stored in `learned_map.json` alongside existing grids/edge memory. Cap total points per floor (≤ 5000 per floor expected) with a decimation strategy when cap reached.
- Backward compatibility — on load, if an older `learned_map.json` has `wall_segments` but no raycast point cloud, IGNORE the old segments. New saves only write the new schema. Keep `wall_segments: []` empty in new saves so older loaders don't crash.

**Line fitting**
- Periodically (not per tick) run a line-fitting pass over the point cloud. Cadence is Claude's discretion — expect every N seconds OR on room-boundary crossing OR explicit `fit_now()` API.
- Algorithm = RANSAC or Hough. Claude picks based on research. Publish choice in PLAN.md with reasoning.
- Output of fitting = list of `Wall` objects: `(x1, y1, x2, y2, confidence, support_count, first_seen, last_seen)`.
- Walls must merge across fitting passes (collinearity + proximity + overlap of x/y ranges).
- Walls below a confidence threshold are "candidate" and not rendered / not used for room inference.

**Corner detection**
- A corner exists where two fitted walls meet at an angle NOT close to 0°/180° AND their endpoints are within a proximity threshold (e.g. 32 units).
- Each corner is `(x, y, wall_a_id, wall_b_id, angle_deg, confidence)`.
- Corners are first-class entities, not just computed at render time.

**Room polygon inference**
- A `Room` is a closed loop of walls connected by corners. Detection: walk the corner graph looking for cycles.
- Minimum room size (~64×64 or larger) — Claude picks.
- Rooms are inferred lazily — after a line-fitting pass that added/modified walls OR on explicit API call.
- Open doorways — where two walls ALMOST meet but leave a gap (<~96 units) — create a `Doorway` entity connecting two rooms OR one room to "outside".
- Rooms that cannot be closed remain as `PartialRoom` and do not participate in polygon rendering.

**Room knowledge log**
- Per `Room`: `id, polygon_vertices, bounds, area, walls[], corners[], doorways[], items_seen[], visit_count, first_seen_ts, last_seen_ts, last_visited_ts, notes`.
- `items_seen` = what items (weapons/health/armor/powerup) the bot has spotted WHILE INSIDE the room's polygon. Reuses existing item-on-map data from ReactiveAgent.
- Per-room data persists in `learned_map.json` alongside walls/corners/doorways/raycasts. Versioned schema — Phase 12 loaders that don't know about rooms gracefully skip new fields.
- A new `current_room_id` field is exported via the HUD payload. Adding this to `hud_schema.build_hud_payload` as an optional kwarg — do NOT break the dedup contract.

**Minimap rendering**
- Fitted walls rendered as clean bright-green-ish lines (NOT `(255,60,60)` red stubs), drawn ON TOP of the learned grid cells but UNDER the trail and waypoints.
- Corners rendered as small filled circles at vertex positions.
- Room polygons rendered as faint outline + 20% alpha fill. Current room gets brighter outline/fill.
- Backward compat — if no fitted walls exist yet, fall back silently to Phase 12.1 display.
- Dedup contract from Phase 12 still holds — `current_room_id` shows ONCE in stats, not in minimap text.
- Red stub rendering (current `wall_segments` draw at lines 192-203 of `minimap.py`) is REMOVED entirely.

**HUD stats panel impact**
- Stats panel gets 2 new rows: `room` (current room id or "—") and `room_items`. Sit below existing verbose rows. Do NOT exceed panel height.
- 9-verbose-row contract from Phase 12 still intact; these are ADDITIONS at rows 10 and 11.

**Testing strategy**
- Unit tests for every new subsystem: raycast capture, line fitting, corner detection, room polygon inference, doorway detection.
- Integration test: feed a recorded tour's raycasts (or synthetic oa_dm1 ground truth) and verify fitted walls match known oa_dm1 architecture within a tolerance.
- Panel isolation tests: MinimapPanel must still render cleanly with EITHER new-schema data OR legacy empty-walls data.
- Live visual verification: run `item_tour.py --no-vision` and eyeball fitted walls on `oa_dm1`.

**Non-functional constraints**
- Pi 4/5 perception loop 10+ FPS maintained — line fitting at slower cadence, not per tick. Per-tick raycast capture <1ms.
- Persistence format forward-compatible with Phase 12.1 grids/edge-failure data (same JSON file).
- Must not regress 743 passing tests from Phase 12.1.

### Claude's Discretion
- Exact raycast sources beyond `wall_ahead + wall_score` (also available: `wall_detector.score_direction_openness` left/center/right, stuck-recovery probes)
- Point cloud cap and decimation strategy
- Line fitting cadence (time-based vs event-based vs explicit)
- Choice of RANSAC vs Hough (this research recommends RANSAC — see below)
- Wall confidence threshold
- Corner proximity threshold
- Minimum room size
- Doorway gap threshold

### Deferred Ideas (OUT OF SCOPE)
- Active wall-mapping skill (deliberate side-sweeps)
- Room-aware pathing / A* preference for known rooms
- Room-aware combat (cover, enemy-route prediction)
- Multi-story room graph (3D rooms with vertical doorways)
- Replacing AAS entirely
- Wall material classification
- Enemy-room belief
- Player-driven persistent room naming via LLM
</user_constraints>

## Project Constraints (from CLAUDE.md)

The planner must honor these directives from `./CLAUDE.md` and project rules:

- **Runtime:** Python 3.11+, asyncio, uv for deps. Do NOT use `pip` directly.
- **Package manager:** `uv add` / `uv sync` — never `pip install`.
- **Linting/formatting:** `ruff` is the single source of truth. Run `uv run ruff check .` and `uv run ruff format .` on every edit.
- **Types:** `mypy` strict on new code. Hint everything.
- **Tests:** `pytest` with `pytest-asyncio` (`mode=auto`), use `pytest-cov`, hypothesis for property-based tests where math is involved.
- **Logging:** `structlog` with context binding — `log.bind(subsystem="learned_map")` etc. No plain `logging.getLogger` for NEW modules (existing code uses stdlib `logging` — don't introduce a mixed-world regression, but use structlog for Phase 13 new modules if feasible, otherwise match the existing `learned_map.py` pattern of `logging.getLogger(__name__)`).
- **Pi 4/5 performance:** 10+ FPS perception loop is sacred. Per-tick work <1ms. Measure on Pi, not desktop.
- **Dependencies:** keep lightweight. The existing stack already has `opencv-python-headless`, `numpy`, `pydantic`, `aiosqlite`, `structlog`. **Adding `networkx`, `scikit-learn`, or `shapely` is strongly discouraged** — this research recommends hand-rolled / OpenCV-based alternatives everywhere.
- **GSD workflow enforcement:** all file changes must go through `/gsd-execute-phase`. No ad-hoc edits.
- **Dedup contract:** every HUD metric appears exactly ONCE across panels. Phase 12's 9-verbose-row contract + new `room`/`room_items` rows = 11 total, StatsPanel only.
- **Backward compatibility:** 743 Phase 12.1 tests must stay green. `learned_map.json` v2 files must still load.
- **No breaking changes to `build_hud_payload`:** new kwargs are optional only, match the Phase 12-01 pattern of `if x is not None: payload[key] = x`.

<phase_requirements>
## Phase Requirements

These are the 12 proposed `RP-XX` requirement rows that REQUIREMENTS.md should receive before planning. Each is anchored in the locked decisions from CONTEXT.md and has an acceptance criterion the verifier can mechanically check.

| ID | Description | Acceptance Criterion | Research Support |
|----|-------------|----------------------|------------------|
| **RP-01** | `learned_map.py` captures per-tick raycast hits from perception forward-scan (`wall_ahead` + `wall_score`) and stores them in a per-floor point cloud structure `_raycasts_per_floor` | Running one tick with `wall_ahead=True, wall_score=0.8` appends exactly one `RaycastHit` NamedTuple to the current floor's cloud; per-tick capture benchmarked < 1ms on Pi 4 | `learned_map.py:120-130` is the wire-in site; CONTEXT raycast format spec |
| **RP-02** | Point cloud is capped per-floor with a decimation strategy that keeps the most recent / highest-confidence hits when the cap is reached | Cap of 5000/floor enforced; when exceeded, oldest-low-confidence hits evicted; unit test synthesizes 6000 hits and asserts final size == 5000 | Cap section below; decimation strategies |
| **RP-03** | A `LineFitter` module runs RANSAC line fitting over the raycast cloud with a deterministic seeded RNG and emits `Wall` entities `(x1, y1, x2, y2, confidence, support_count, first_seen, last_seen)` | Feeding a synthetic 4-wall rectangular point cloud (with 10% outliers) produces exactly 4 walls within 2-unit endpoint tolerance; seeding RNG produces identical output across runs | RANSAC algorithm section below |
| **RP-04** | Line fitting runs at slower-than-tick cadence — every N seconds (default 3s) OR on explicit `fit_now()` API call — never per tick | Per-tick update path does NOT invoke fitter; a 10-second fake-clock test shows exactly 3 fit calls at default cadence | Cadence section below |
| **RP-05** | New walls merge with existing walls across fit passes using collinearity + endpoint-overlap criteria; `support_count` accumulates | Running fit twice on the same point cloud produces the same N walls with doubled `support_count`, not 2N walls | Wall merging section below |
| **RP-06** | A `CornerDetector` module emits `Corner` entities where two fitted walls meet at 20°<θ<160° AND nearest endpoints are within 32 units | Two perpendicular walls with touching endpoints produce exactly one corner; two parallel walls produce zero | Corner detection section below |
| **RP-07** | A `RoomInferrer` module walks the corner graph with hand-rolled simple cycle detection (max cycle length 8) and emits `Room` polygons for cycles whose enclosed area ≥ 64×64 square units | Synthetic 4-corner square graph produces exactly 1 Room; triangle of corners with area < threshold produces 0 Rooms | Room inference section below |
| **RP-08** | Incomplete room loops (2 or 3 walls) are stored as `PartialRoom` entities and excluded from polygon rendering; doorways are inferred where two walls almost-meet with gap < 96 units | 3-wall U-shape produces 1 PartialRoom with 0 rooms rendered; two adjacent rooms sharing a gapped wall pair produce 1 Doorway | Doorway section below |
| **RP-09** | Each `Room` maintains a knowledge log: `{id, polygon_vertices, bounds, area, walls[], corners[], doorways[], items_seen[], visit_count, first_seen_ts, last_seen_ts, last_visited_ts, notes}`; items observed via `ReactiveAgent` are associated with a room via `cv2.pointPolygonTest` | Observing a weapon at a point inside room R appends it to `R.items_seen`; `visit_count` increments once per entry (not per tick) | Room log schema + PIP section |
| **RP-10** | `learned_map.json` bumps to schema version 3 with new top-level keys (`raycasts_per_floor`, `fitted_walls`, `corners`, `rooms`, `doorways`); v2 files load gracefully with empty new collections; `wall_segments` key is written as `[]` for legacy loader compatibility | Loading a canned v2 fixture populates grids and leaves `rooms=[]`; saving v3 and reloading preserves all data byte-stable; pre-Phase-13 loaders (Phase 12.1) don't crash reading v3 files | Persistence section below |
| **RP-11** | `MinimapPanel` removes the red-stub render block (lines 192-203) and draws: (a) fitted walls as bright-green lines (2px) UNDER the trail, (b) corners as 3px filled circles, (c) room polygons as 20% alpha fill + outline, with current-room brighter. Falls back silently to Phase 12.1 display when `fitted_walls` is empty | Panel isolation test renders cleanly with new-schema HUD state AND with legacy empty-walls state; visual checkpoint on `oa_dm1` shows no red stubs | Minimap render section below |
| **RP-12** | `hud_schema.build_hud_payload` accepts optional `current_room_id` and `current_room_items` kwargs (backward-compatible, None → key omitted); `StatsPanel` adds rows 10 (`room`) and 11 (`room_items`) below the existing 9 verbose rows without exceeding panel height | Calling `build_hud_payload()` without new kwargs produces a payload byte-identical to Phase 12.1 output; with kwargs, keys appear exactly once in stats panel; 743 existing tests stay green | hud_schema.py:164-181 pattern |

**Notes for REQUIREMENTS.md append step:**
- These rows go under a new `### Room Perception (Phase 13)` subsection of v1 Requirements (or v2 if v1 is frozen — planner decides)
- Traceability table gets 12 new entries: `| RP-01..RP-12 | Phase 13 | Not started |`
- Coverage count bumps from 88 → 100
</phase_requirements>

## Standard Stack

### Core (all already in-tree — verified via `python3 -c "import cv2, numpy"`)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | 2.4.4 (verified) | Point cloud storage, vectorized RANSAC inlier test, line math | Project foundation; no alternative |
| opencv-python-headless | 4.13.0 (verified) | `cv2.pointPolygonTest`, optional `cv2.HoughLinesP` / `cv2.fitLine` for auxiliary use, `cv2.Canny` (not needed here) | Already a hard dep; provides all geometry primitives we need without adding shapely |
| stdlib `json`, `base64` | — | Schema v3 persistence | Matches existing `learned_map.save()` pattern |
| stdlib `math`, `itertools.combinations` | — | Angle math, wall pair enumeration | — |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest + hypothesis | existing | Unit + property-based tests for line fitting math | Hypothesis excels at finding corner-case point clouds (degenerate collinear points, noise-only clouds, near-parallel walls) |
| structlog | existing | Structured logging of fit passes | `log.bind(phase="fit", walls_in=N, walls_out=M).info("ransac_pass")` |

### Alternatives Considered and Rejected

| Instead of | Could Use | Why Not |
|------------|-----------|---------|
| Custom RANSAC | `skimage.measure.ransac` | scikit-image is ~40MB, not a current dep, adds install burden on Pi. Hand-roll is 30 lines. |
| Custom cycle detection | `networkx.simple_cycles` | networkx is ~2MB + depends on scipy paths we don't need. Hand-rolled DFS on a small graph (<30 corners) is <50 LOC. |
| `cv2.pointPolygonTest` | `shapely.geometry.Polygon.contains` | Shapely is ~20MB + GEOS C library, not a current dep. OpenCV already provides PIP natively. |
| Custom RANSAC | OpenCV `cv2.fitLine` with LMEDS | `cv2.fitLine` fits a single line to ALL points — doesn't segment a multi-wall scene. Wrong tool. |
| Custom RANSAC | `cv2.HoughLinesP` on rasterized cloud | Works, but rasterization loses density information and the inlier/support count that RANSAC gives for free. Also coarser on continuous data. Keep as a **fallback option** the planner may pick if RANSAC's non-determinism becomes a test nightmare. |

**No new packages required.** This phase is pure numpy + OpenCV + stdlib.

### Version verification

Verified on this machine (Raspberry Pi 5 / Linux 6.12):

```
python3 -c "import cv2, numpy; print(cv2.__version__, numpy.__version__)"
# cv2 4.13.0 numpy 2.4.4
```

Both satisfy the `>=4.8` and `>=1.26` floors in CLAUDE.md.

## Architecture Patterns

### Recommended Module Layout

```
openarena_perception/navigation/
├── learned_map.py              # Existing — extend with raycast capture + HUD export
├── room_perception/            # NEW subpackage
│   ├── __init__.py             # Re-exports Wall, Corner, Room, Doorway, PartialRoom
│   ├── types.py                # NamedTuples / frozen dataclasses for all entities
│   ├── line_fitter.py          # RANSAC line fitting + wall merging
│   ├── corner_detector.py      # Pairwise wall intersection + endpoint gating
│   ├── room_inferrer.py        # Corner graph + simple cycle enumeration
│   └── doorway_detector.py     # Gap detection between almost-touching walls
```

Keeping room-perception as a subpackage under `navigation/` preserves the Phase 4 extraction boundary (no cross-imports into `perception/` or `combat/`) and keeps the `learned_map.py` file from ballooning.

### Pattern 1: Immutable entity types via NamedTuple

```python
# Source: project convention (Phase 01 SituationalAwareness, Phase 08 HumanizationConfig)
from typing import NamedTuple, Tuple, List

class RaycastHit(NamedTuple):
    origin_x: float
    origin_y: float
    origin_z: float
    dir_angle_deg: float
    hit_x: float
    hit_y: float
    confidence: float
    timestamp: float

class Wall(NamedTuple):
    id: int
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    support_count: int
    first_seen: float
    last_seen: float

class Corner(NamedTuple):
    id: int
    x: float
    y: float
    wall_a_id: int
    wall_b_id: int
    angle_deg: float
    confidence: float
```

Use `NamedTuple` not `@dataclass(frozen=True)` because JSON round-trip is `list(tuple)` which is idiomatic. (Matches the existing `_wall_segments: List[List[float]]` JSON shape.)

### Pattern 2: RANSAC line fitting (custom, deterministic, numpy-vectorized)

```python
# Reference: standard 2D line RANSAC — https://en.wikipedia.org/wiki/Random_sample_consensus
# Project needs: deterministic (seeded), outputs support_count, peels multiple lines
import numpy as np

def ransac_lines(
    points: np.ndarray,              # shape (N, 2)
    *,
    inlier_dist: float = 8.0,        # perpendicular distance in world units
    min_inliers: int = 20,           # minimum support to emit a wall
    max_lines: int = 32,             # safety cap
    iterations: int = 200,           # per-line attempt count
    seed: int = 42,                  # DETERMINISTIC — tests rely on this
) -> list[tuple[float, float, float, float, int]]:
    """Returns [(x1, y1, x2, y2, support_count), ...] with points peeled."""
    rng = np.random.default_rng(seed)
    remaining = points.copy()
    walls = []
    for _ in range(max_lines):
        if len(remaining) < min_inliers:
            break
        best_inliers_mask = None
        best_count = 0
        for _ in range(iterations):
            idx = rng.choice(len(remaining), 2, replace=False)
            p1, p2 = remaining[idx[0]], remaining[idx[1]]
            d = p2 - p1
            norm = np.hypot(d[0], d[1])
            if norm < 1e-6:
                continue
            # Perpendicular distance from every remaining point to line p1-p2
            # Cross product magnitude / |d|
            diffs = remaining - p1
            dist = np.abs(diffs[:, 0] * d[1] - diffs[:, 1] * d[0]) / norm
            mask = dist < inlier_dist
            count = int(mask.sum())
            if count > best_count:
                best_count = count
                best_inliers_mask = mask
        if best_count < min_inliers or best_inliers_mask is None:
            break
        inliers = remaining[best_inliers_mask]
        # Refit with least squares to all inliers for a clean line
        # Project inliers onto dominant axis for endpoint estimation
        mean = inliers.mean(axis=0)
        centered = inliers - mean
        # Principal direction via SVD on 2D is just eigenvector of covariance
        cov = centered.T @ centered
        eigvals, eigvecs = np.linalg.eigh(cov)
        direction = eigvecs[:, np.argmax(eigvals)]
        projections = centered @ direction
        t_min, t_max = projections.min(), projections.max()
        p_start = mean + t_min * direction
        p_end = mean + t_max * direction
        walls.append((float(p_start[0]), float(p_start[1]),
                      float(p_end[0]), float(p_end[1]),
                      best_count))
        remaining = remaining[~best_inliers_mask]
    return walls
```

**Perf note:** `N=5000, iterations=200, max_lines=32` — each iteration is O(N) vectorized → ~32M numpy ops per fit pass. On Pi 5 ARM64 this should run in 50-200ms; well under a 3-second cadence budget. **Planner should benchmark on Pi before locking cadence.**

### Pattern 3: Hand-rolled simple cycle enumeration

```python
# Reference: standard DFS-based simple cycle finder
# Small graphs (≤ 30 corners) mean we don't need Johnson's algorithm
def find_simple_cycles(adjacency: dict[int, list[int]], max_len: int = 8) -> list[list[int]]:
    cycles = []
    seen_cycles: set[frozenset[int]] = set()
    def dfs(start: int, current: int, path: list[int]):
        if len(path) > max_len:
            return
        for nxt in adjacency.get(current, []):
            if nxt == start and len(path) >= 3:
                key = frozenset(path)
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    cycles.append(list(path))
            elif nxt not in path and nxt > start:  # canonical: start is min
                dfs(start, nxt, path + [nxt])
    for node in adjacency:
        dfs(node, node, [node])
    return cycles
```

The `nxt > start` trick ensures each cycle is only discovered once (starting from its minimum-id node), eliminating the need for deduplication on rotated equivalents.

### Anti-Patterns to Avoid

- **Per-tick line fitting:** NEVER call `fit_now()` from `LearnedMap.update()`. Fitting is 50-200ms; that kills the 10 FPS budget.
- **Mutating walls in place during fit:** always produce a new list, merge, then atomic-swap. Otherwise HUD readers race on partial state.
- **Writing to `_wall_segments` from new code:** leave it as `[]`. New code writes to `_fitted_walls`. Mixing them is how dedup contract breaks.
- **Unseeded RNG in RANSAC:** flaky tests. Always take `seed` as a parameter; default 42.
- **Calling `cv2.pointPolygonTest` with non-contiguous arrays:** it requires `np.int32` contour arrays. Cast on the way in.
- **Storing raycasts as Python list-of-dicts:** 5000 dicts is ~5MB in memory. Use `np.ndarray` of shape `(N, 8)` and only materialize NamedTuples on API export.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Point-in-polygon | Custom ray-casting PIP | `cv2.pointPolygonTest(contour, pt, measureDist=False)` | OpenCV is already a dep; handles edge cases (on-boundary, degenerate) that hand-rolled PIP gets wrong |
| Line-line intersection | Manual determinant math | Short helper using numpy — **this one IS hand-rolled**, ~8 lines, no library exists that's both lightweight and handles segment (not infinite line) intersection cleanly. Write + test it. | — |
| Principal direction of a point set | Custom angle averaging | `np.linalg.eigh(covariance)` (2×2 matrix) | Numerically stable, one numpy call |
| JSON schema versioning | Custom migration code | Follow the existing `learned_map.py:213-252` pattern — check `version` field, upcast with defaults | Already proven on v1→v2 |
| RNG seeding | `random.seed()` module state | `np.random.default_rng(seed)` instance | Instance-scoped, no global state pollution, test-friendly |

**Key insight:** The project already has every geometric primitive it needs via OpenCV + numpy. Avoid the temptation to add `shapely` or `networkx` "because it's cleaner" — both are multi-megabyte adds on Pi for functionality we can replicate in ~100 LOC.

## Runtime State Inventory

**Not applicable** — Phase 13 is a new-feature phase, not a rename/refactor/migration. No existing runtime state is being moved.

However, there IS one "migration" concern: existing `~/.openarena/learned_maps/*.json` files are v2 schema. The locked decision is to IGNORE old `wall_segments` on load (no round-trip). Verified by reading CONTEXT.md — no action needed beyond the v2→v3 load path.

## Common Pitfalls

### Pitfall 1: RANSAC non-determinism breaks tests
**What goes wrong:** Running the same fit twice produces different walls because the random sample order changes, and snapshot tests fail intermittently.
**Why it happens:** Default `np.random` is process-global.
**How to avoid:** Always pass `seed` to the fitter. In tests, use `seed=42`. In production, use a time-derived seed logged to structlog so failures are reproducible.
**Warning sign:** CI flakes on `test_line_fitter.py` but passes locally.

### Pitfall 2: Wall merging across fit passes creates Frankenstein walls
**What goes wrong:** Two fit passes see slightly different inlier sets; the merge extends a wall beyond its true endpoints, fusing adjacent walls into one diagonal mega-wall.
**Why it happens:** `merge` currently just takes `min/max` on x and y coordinates (see existing `_record_wall` lines 381-384 for the anti-pattern). This fails for non-axis-aligned walls.
**How to avoid:** Merge by projecting both walls' endpoints onto the merged wall's **principal direction**, taking min/max of the projection parameter (t), then reconstructing endpoints. Never min/max the raw coordinates. And only merge if the angle between the two walls is < 5° AND endpoints lie within 2 × `inlier_dist`.
**Warning sign:** Walls visibly extending through other walls on the minimap after multiple fit passes.

### Pitfall 3: Point-cloud cap decimation throws away the wrong points
**What goes wrong:** Naive FIFO eviction drops the oldest points, which are often the most "structural" (bot's first view of a wall). Newer points are from the bot facing random directions during combat.
**Why it happens:** FIFO is the obvious implementation.
**How to avoid:** Evict the LOWEST-confidence points first, breaking ties by age. Or reservoir sample. Tests should verify a 4-wall synthetic cloud still produces 4 walls after cap-triggered decimation.
**Warning sign:** Line fitting quality degrades over a long tour even though more data was collected.

### Pitfall 4: Corner graph builds using list identity instead of IDs
**What goes wrong:** After a fit pass produces new `Wall` NamedTuples (immutable), the old `Corner` objects still reference the stale walls by list index. Indexes shift. Corners point at wrong walls.
**Why it happens:** Walls are positional in a list.
**How to avoid:** Assign monotonic integer IDs to walls on creation (a `_next_wall_id` counter on `LineFitter`). Store walls in a dict keyed by ID. Corners reference wall IDs, not list positions. Same rule for `Corner.id` → `Room.corners[]`.
**Warning sign:** After a merge pass, `current_room_id` points at a room whose corners reference deleted walls.

### Pitfall 5: `hud_schema.build_hud_payload` dedup contract violation
**What goes wrong:** Someone adds `current_room_id` as a `payload["minimap"]["current_room_id"]` AND a `payload["current_room_id"]`, duplicating the metric.
**Why it happens:** Convenience during the learn-map export path.
**How to avoid:** Add `current_room_id` and `current_room_items` as **top-level optional kwargs only**, matching the existing Phase 12-01 pattern (`hud_schema.py:164-181`). NEVER inside `learned_map` sub-dict. The StatsPanel reads `getattr(state, "current_room_id", None)` — single path.
**Warning sign:** `test_no_duplicates.py` fails.

### Pitfall 6: Schema v3 breaks Phase 12.1 loaders
**What goes wrong:** Phase 12.1 `LearnedMap.load()` at line 221 checks `version not in (1, 2)` and refuses v3. A user with a newer save file can't load on an older bot build.
**Why it happens:** Explicit version whitelist.
**How to avoid:** Update the check to `version not in (1, 2, 3)`. The v2 → v3 upgrade path writes `raycasts_per_floor=[]` and `fitted_walls=[]` etc. so old code reading v3 still works IF it tolerates unknown keys (which `.get(..., default)` always does). The failure mode is the whitelist, not the keys. **Verify by loading a v3 file with a Phase 12.1 loader in an integration test.**
**Warning sign:** Bisecting a user's learned map across git versions breaks.

### Pitfall 7: Line fitting cadence coupled to wall-clock drift
**What goes wrong:** Using `time.time()` differences for cadence causes drift and non-reproducible tests.
**Why it happens:** Python convention.
**How to avoid:** Use `time.monotonic()` for cadence. In tests, inject a clock (`time_fn: Callable[[], float] = time.monotonic`) so tests drive cadence deterministically.
**Warning sign:** Flaky cadence tests, wall-time-based assertions.

### Pitfall 8: Point-in-polygon with non-contiguous numpy arrays
**What goes wrong:** `cv2.pointPolygonTest` raises cryptic "expected np.int32 contour" errors.
**Why it happens:** OpenCV expects contours as `np.int32`, shape `(N, 1, 2)`, C-contiguous.
**How to avoid:** `contour = np.ascontiguousarray(polygon_vertices, dtype=np.int32).reshape(-1, 1, 2)`. Cache this on the Room object — don't rebuild per tick.
**Warning sign:** Integration test blows up on the first item-observed-inside-room call.

### Pitfall 9: RANSAC on rooms with curved or diagonal walls
**What goes wrong:** RANSAC finds a spurious "line" through points that actually lie on a curved wall or three short offset walls, producing a ghost wall.
**Why it happens:** RANSAC finds ANY line with enough support.
**How to avoid:** Set `min_inliers` high enough (e.g. 30+) that noise can't form a line. Add a post-filter: reject walls whose inlier distribution along the line is too sparse (e.g. gaps > 128 units between consecutive inliers). `oa_dm1` ground-truth walls are 256+ units long — pick thresholds that exclude 64-unit accidents.
**Warning sign:** Ghost walls appearing in wide-open areas on the minimap.

### Pitfall 10: Two fit passes produce DUPLICATE rooms due to ID instability
**What goes wrong:** Each pass creates new `Room` objects with fresh IDs, and the room log grows unboundedly.
**Why it happens:** Room inference is stateless — it rebuilds from walls + corners each pass.
**How to avoid:** Rooms are matched across passes by **polygon centroid + area similarity** (centroid within 64 units AND area within 20%). If match found, update the existing Room's `last_seen_ts` and `walls`/`corners` references. Else assign new ID. Items_seen is carried over from the matched previous room.
**Warning sign:** Room count strictly increasing every fit pass during a single tour.

## Code Examples

### Raycast capture wired into `LearnedMap.update()`

```python
# Source: extends existing learned_map.py:120-130 (current _record_wall call site)
# Replaces the _record_wall call with raycast append
if wall_ahead and wall_score > 0.5:
    wall_dist = 30.0 + (1.0 - wall_score) * 40.0
    hit_x = wx + wall_dist * math.cos(math.radians(yaw))
    hit_y = wy + wall_dist * math.sin(math.radians(yaw))
    hit_z = wz  # 2D fitting per CONTEXT lock — but preserve z for future 3D
    hit = RaycastHit(
        origin_x=wx, origin_y=wy, origin_z=wz,
        dir_angle_deg=yaw,
        hit_x=hit_x, hit_y=hit_y, hit_z=hit_z,
        confidence=wall_score,
        timestamp=time.monotonic(),
    )
    self._raycasts_per_floor[self._current_floor].append(hit)
    self._maybe_decimate_raycasts(self._current_floor)
```

### Point-in-polygon for current-room detection

```python
# Source: https://docs.opencv.org/4.x/dc/d48/tutorial_point_polygon_test.html
import cv2
import numpy as np

def point_in_room(room_polygon: list[tuple[float, float]], px: float, py: float) -> bool:
    contour = np.ascontiguousarray(room_polygon, dtype=np.int32).reshape(-1, 1, 2)
    # measureDist=False → returns +1 inside, 0 on edge, -1 outside
    return cv2.pointPolygonTest(contour, (float(px), float(py)), False) >= 0
```

### OpenCV auxiliary APIs (not the primary fitter, but useful)

```python
# cv2.HoughLinesP — fallback if RANSAC determinism becomes painful
# Source: https://docs.opencv.org/4.x/d9/db0/tutorial_hough_lines.html
# Input: 8-bit binary bitmap. Rasterize cloud first.
bitmap = np.zeros((H, W), dtype=np.uint8)
for px, py in world_points_mapped_to_bitmap:
    bitmap[py, px] = 255
lines = cv2.HoughLinesP(bitmap, rho=1, theta=np.pi/180,
                        threshold=50, minLineLength=30, maxLineGap=10)
# lines shape: (N, 1, 4) — [x1, y1, x2, y2] per line

# cv2.fitLine — single-line fit to ALL points (wrong for multi-wall scenes, but good for
# refining a single wall's endpoints after RANSAC picks the inlier set)
# Source: https://docs.opencv.org/4.x/dd/d49/tutorial_py_contour_features.html
vx, vy, x0, y0 = cv2.fitLine(inlier_points, cv2.DIST_L2, 0, 0.01, 0.01)
```

## State of the Art

| Old Approach (Phase 12.1) | Current Approach (Phase 13) | Impact |
|--------------------------|-----------------------------|--------|
| 64-unit perpendicular stubs recorded per wall sighting | Raycast point cloud + RANSAC line fitting | CAD-quality continuous walls; support counts; mergeable |
| `wall_segments: List[List[float]]` in JSON | `raycasts_per_floor` + `fitted_walls` + `corners` + `rooms` + `doorways` top-level keys | Versioned schema v3; legacy `wall_segments: []` preserved for crash-safety |
| Red stub render on minimap | Bright-green clean CAD lines + corner dots + room polygon fills | Dedicated under-trail-over-grid layer |
| No per-room knowledge | Full `Room` log with items_seen, visit counts, timestamps | Enables eventual AAS-free play |
| No current-room concept | `current_room_id` exported in HUD + shown in stats panel | New dedup-safe row |

**Deprecated/removed:**
- `learned_map._record_wall()` method (lines 347-389): removed, replaced by raycast capture
- `MinimapPanel` lines 192-203 red stub draw: removed entirely
- `export_for_hud()` `wall_segments` field: kept as `[]` for backward compat, but no longer populated by new code

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| python | runtime | ✓ | 3.11+ (CLAUDE.md says 3.11 baseline) | — |
| numpy | RANSAC, point cloud | ✓ | 2.4.4 (verified `python3 -c "import numpy"`) | — |
| opencv-python-headless | PIP, HoughLinesP fallback | ✓ | 4.13.0 (verified `python3 -c "import cv2"`) | — |
| pytest + hypothesis | tests | ✓ | existing per pyproject | — |
| structlog | logging | ✓ | existing | stdlib logging (matches learned_map.py current pattern) |

**No missing dependencies.** No fallbacks required. This phase is entirely in-tree.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (mode=auto) + hypothesis |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_learned_map.py tests/test_room_perception.py -x` |
| Full suite command | `uv run pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RP-01 | Per-tick raycast append | unit | `pytest tests/test_learned_map.py::test_raycast_capture_appends -x` | ❌ Wave 0 — add to existing-or-new `tests/test_learned_map.py` |
| RP-02 | Point-cloud cap + decimation | unit (hypothesis) | `pytest tests/test_learned_map.py::test_raycast_decimation -x` | ❌ Wave 0 |
| RP-03 | RANSAC emits walls on synthetic data | unit | `pytest tests/test_room_perception.py::test_ransac_four_wall_rectangle -x` | ❌ Wave 0 — new file `tests/test_room_perception.py` |
| RP-04 | Cadence gating | unit (fake clock) | `pytest tests/test_room_perception.py::test_fit_cadence -x` | ❌ Wave 0 |
| RP-05 | Wall merge preserves support | unit | `pytest tests/test_room_perception.py::test_wall_merge -x` | ❌ Wave 0 |
| RP-06 | Corner detection pair gating | unit | `pytest tests/test_room_perception.py::test_corner_from_two_walls -x` | ❌ Wave 0 |
| RP-07 | Room polygon from closed cycle | unit | `pytest tests/test_room_perception.py::test_room_from_square -x` | ❌ Wave 0 |
| RP-08 | PartialRoom + doorway | unit | `pytest tests/test_room_perception.py::test_partial_room_and_doorway -x` | ❌ Wave 0 |
| RP-09 | items_seen ingestion via PIP | unit | `pytest tests/test_room_perception.py::test_item_ingestion_pip -x` | ❌ Wave 0 |
| RP-10 | Schema v2→v3 round trip | unit | `pytest tests/test_learned_map.py::test_schema_v3_roundtrip -x` | ❌ Wave 0 |
| RP-11 | MinimapPanel renders new-schema + falls back | isolation (SDL dummy) | `SDL_VIDEODRIVER=dummy pytest tests/test_open_perception_panels.py -x` | ✓ exists, ADD cases |
| RP-12 | HUD schema kwargs backward-compat | unit | `pytest tests/test_hud_schema.py -x` | ✓ exists, ADD cases |
| *integration* | oa_dm1 ground-truth fit | integration | `pytest tests/test_room_perception_integration.py -x` | ❌ Wave 0 — new file |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_learned_map.py tests/test_room_perception.py -x` (≤10s target)
- **Per wave merge:** `uv run pytest -q` (full suite — must keep 743 Phase 12.1 tests green)
- **Phase gate:** Full suite green + live visual verification on `oa_dm1` via `python -m item_tour --no-vision`

### Wave 0 Gaps

- [ ] `tests/test_room_perception.py` — create, covers RP-03..RP-09
- [ ] `tests/test_room_perception_integration.py` — create, covers oa_dm1 ground-truth fit
- [ ] `tests/test_learned_map.py` — create (does not currently exist per `ls tests/`), covers RP-01, RP-02, RP-10
- [ ] `tests/fixtures/room_perception/oa_dm1_raycasts.json` — synthetic or recorded raycast cloud ground-truth fixture. Authoring strategy: run `item_tour.py --no-vision` on `oa_dm1` with the new capture code, hand-verify the resulting cloud looks right, save as fixture. ALTERNATIVELY: compute synthetic raycasts by sampling points along known AAS area boundaries (faster, fully deterministic).
- [ ] `tests/conftest.py` — add a `fixed_rng_seed` fixture (shared across room perception tests)
- [ ] Hypothesis strategies: `rectangle_point_cloud(width, height, noise)`, `triangle_cycle_of_corners()` — reusable generators for property-based tests

*No framework install needed — pytest + hypothesis + pytest-asyncio already in `pyproject.toml` dev deps.*

## Security Domain

ASVS categories are largely N/A for this phase — there is no network I/O, no authentication, no user input, no crypto. The relevant controls are:

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | **yes (mild)** | `learned_map.json` load path must reject malformed/oversized files gracefully. The existing `try/except` at `learned_map.py:250` is sufficient pattern — extend it for v3 fields. |
| V6 Cryptography | no | — |

### Known Threat Patterns for this phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed `learned_map.json` with huge `raycasts_per_floor` array → memory DoS on load | Denial of service | Cap on load: truncate `raycasts_per_floor` to `5000/floor` at deserialize time, log a warning |
| Crafted polygon with 10^6 vertices → `cv2.pointPolygonTest` pathological case | Denial of service | Enforce `max_len=8` in cycle detection; polygons with >16 vertices are rejected with a warning |
| JSON with `"version": 99999` | Tampering | Whitelist: `version not in (1, 2, 3)` → refuse load, keep in-memory defaults |

The learned-map file lives under `~/.openarena/learned_maps/` — local, user-owned, not internet-exposed. Threat model is "don't crash on malformed self-written files", not adversarial. Matches existing pattern.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | RANSAC on 5000 points × 200 iterations × 32 max_lines runs in 50-200ms on Pi 5 | RANSAC perf note | If slower, cadence must be stretched to 5-10s OR max_lines dropped. **Planner MUST benchmark on Pi before locking cadence.** [ASSUMED] |
| A2 | oa_dm1 walls are ≥256 units long | Pitfall 9 | If some walls are shorter, `min_inliers=30` is too aggressive and misses real walls. Tunable. [ASSUMED] |
| A3 | Phase 12.1 has 743 passing tests | Non-functional constraint | Verifier gate may need adjustment if count drifted. Spot-check with `uv run pytest -q --collect-only | tail -5` at plan time. [ASSUMED per CONTEXT.md] |
| A4 | `wall_detector.score_direction_openness` returns reliable left/center/right signals suitable for auxiliary raycast capture | Raycast sources | If output is too noisy, Phase 13 sticks to just `wall_ahead + wall_score` from forward scan. [ASSUMED from grep of wall_detector.py:220] |
| A5 | Adding 2 rows (rows 10, 11) to StatsPanel fits within current 700px height | HUD stats panel | The verbose block starts at y=470 and has 9 rows × 14px = 126px, ending at y=596. Two more rows = y=624. Panel height is 700. **Comfortable fit.** [VERIFIED: stats.py:62-68] |
| A6 | `cv2.pointPolygonTest` has acceptable perf for ~20 rooms × 1 check per item observation | RP-09 | Each call is O(polygon_vertices), with max 8 vertices per room → negligible. [ASSUMED based on OpenCV docs] |
| A7 | Room count stays small (<30 per map) throughout a tour | Room inference | If it explodes, cycle enumeration becomes O(exponential). Mitigated by `max_len=8` + min-area filter. [ASSUMED from oa_dm1 scale] |
| A8 | Phase 12.1 loader tolerates unknown JSON keys | Backward compat (Pitfall 6) | Loader uses `.get(key, default)` pattern at lines 241-243 → YES tolerates unknown. But the **version whitelist** at line 221 refuses v3 outright. **The planner MUST update this whitelist in a Phase-12.1-code edit OR version-bump learned_map schema only AFTER ensuring the loader accepts v3.** [VERIFIED: learned_map.py:220-221] |

**If this table is non-empty:** the assumptions above should be confirmed at `/gsd-discuss-phase` time OR mitigated by the planner picking conservative defaults (e.g., start cadence at 5 seconds not 3, benchmark during Wave 0).

## Open Questions

1. **Should the raycast point cloud store Z coordinates even though fitting is 2D?**
   - What we know: CONTEXT.md locks "within a floor, rooms are 2D" and the floor filter is already in Phase 12.1
   - What's unclear: whether preserving Z is worth the storage cost for future 3D extension
   - Recommendation: **YES, preserve Z in the NamedTuple** (`origin_z`, `hit_z`) at negligible cost — future 3D work will thank us. Fitter ignores Z.

2. **Does wall merging run incrementally (every fit pass) or batch (only on `fit_now()`)?**
   - What we know: "Walls must merge across fitting passes" is locked
   - What's unclear: whether a single fit pass produces walls and a separate merge phase combines them with prior walls, or if fit takes prior walls as input
   - Recommendation: **Two-phase**. Phase 1: `ransac_lines(points) → new_walls`. Phase 2: `merge_walls(prior_walls, new_walls) → merged_walls`. Separates testing concerns.

3. **Where does `current_room_id` actually get computed?**
   - What we know: It's exported via HUD; item_tour and strategic_brain are the payload builders
   - What's unclear: whether `LearnedMap` computes it on each HUD export OR whether the caller computes it
   - Recommendation: `LearnedMap.export_for_hud()` computes it once using cached polygon contours, returns in the dict, caller passes to `build_hud_payload(current_room_id=...)`. Keeps the PIP cost in one place and off the hot path.

4. **Do we need to preserve `wall_segments` field at all in schema v3?**
   - What we know: CONTEXT.md says "keep `wall_segments: []` empty in new saves so older loaders don't crash"
   - What's unclear: whether ANY active code reads this field. Grep confirms `minimap.py:192-203` does (which is being removed), and `export_for_hud` populates it.
   - Recommendation: **Yes, keep as `[]`** for a few phases, then schedule removal in Phase 14+ once all live installations have migrated.

5. **Cadence: time-based or event-based?**
   - What we know: CONTEXT allows either or an explicit API
   - Recommendation: **Both, OR'd.** Fit runs if `monotonic() - last_fit > 3.0` OR `points_added_since_last_fit > 500` OR `fit_now()` called. Event-based avoids stalled-bot syndrome; time-based avoids thrashing.

## Sources

### Primary (HIGH confidence — verified in-tree)
- `openarena_perception/navigation/learned_map.py` (lines 120-136, 185-255, 256-303, 347-389) — current implementation, full read
- `openarena_perception/navigation/aas_parser.py:316-346` — `areas_on_floor` helper (coexists)
- `openarena_perception/visualization/panels/minimap.py:1-220` — current render path, red stub block to remove
- `openarena_perception/visualization/panels/stats.py:294-360` — verbose row pattern (additions go here)
- `openarena_perception/hud_schema.py:37-186` — optional-kwarg pattern for `build_hud_payload`
- `openarena_perception/perception/wall_detector.py:44-336` — `wall_score`, `wall_ahead`, `score_direction_openness` — the perception signals already available
- `.planning/phases/13-room-perception-and-wall-reconstruction/13-CONTEXT.md` — authoritative locked decisions
- `.planning/phases/12.1-open-perception-ui-polish-square-wireframe-minimap-reflowed-/12.1-CONTEXT.md` — coexistence requirements
- `./CLAUDE.md` — recommended stack, version floors, Pi constraints
- Python verification: `python3 -c "import cv2, numpy; print(cv2.__version__, numpy.__version__)"` → `4.13.0 2.4.4` [VERIFIED]

### Secondary (MEDIUM confidence)
- OpenCV 4.x documentation (training knowledge): `cv2.HoughLinesP`, `cv2.fitLine`, `cv2.pointPolygonTest` API shapes — signatures stable across 4.x [CITED: docs.opencv.org]
- numpy `default_rng` deterministic seeding pattern [CITED: numpy.org/doc random]
- Standard RANSAC algorithm [CITED: Fischler & Bolles 1981, Wikipedia RANSAC]

### Tertiary (LOW confidence — not independently re-verified this session)
- None. All claims above either pulled from the source tree (HIGH) or pulled from stable algorithmic tradition (MEDIUM).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libs verified in-tree, versions checked on this machine
- Architecture patterns: HIGH — matches existing project conventions (NamedTuples, JSON persistence, sub-surface rendering)
- RANSAC algorithm choice: HIGH — well-established, numpy-only, 30 LOC
- Room inference algorithm: MEDIUM — hand-rolled DFS cycle detection works for small graphs but hasn't been stress-tested on pathological `oa_dm1` layouts
- Pitfalls: HIGH — most are direct reads of existing code; the Pitfall 6 version-whitelist gotcha is a **real live bug** the planner MUST address
- Performance budget: MEDIUM-LOW — Pi-benchmark assumption A1 needs empirical confirmation during Wave 0

**Research date:** 2026-04-11
**Valid until:** 2026-05-11 (30 days — stack is stable)
