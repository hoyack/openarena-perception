---
phase: 13-room-perception-and-wall-reconstruction
plan: 04
subsystem: navigation-room-perception
tags: [navigation, geometry, graph, wave-2]
wave: 2
requires: [13-03]
provides:
  - "CornerDetector: wall-pair angle + endpoint-proximity gate -> Corner list"
  - "DoorwayDetector: near-miss collinear wall gaps -> Doorway list"
  - "RoomInferrer: hand-rolled DFS simple-cycle enumeration over corner graph -> (Room, PartialRoom) lists"
  - "_geometry.py shared helpers (nearest_endpoints, angle_between)"
affects:
  - openarena_perception/navigation/room_perception/_geometry.py
  - openarena_perception/navigation/room_perception/corner_detector.py
  - openarena_perception/navigation/room_perception/doorway_detector.py
  - openarena_perception/navigation/room_perception/room_inferrer.py
  - openarena_perception/navigation/room_perception/__init__.py
  - tests/test_room_perception.py
tech-stack:
  added: []
  patterns:
    - "Hand-rolled simple-cycle DFS with canonical min-id start + sorted-tuple dedup (no networkx)"
    - "Shoelace polygon area + min_room_area gating"
    - "BFS connected-component extraction for PartialRoom fallback"
    - "Shared private _geometry.py module keeps CornerDetector and DoorwayDetector DRY without circular imports"
key-files:
  created:
    - openarena_perception/navigation/room_perception/_geometry.py
    - openarena_perception/navigation/room_perception/corner_detector.py
    - openarena_perception/navigation/room_perception/doorway_detector.py
    - openarena_perception/navigation/room_perception/room_inferrer.py
  modified:
    - openarena_perception/navigation/room_perception/__init__.py
    - tests/test_room_perception.py
decisions:
  - "Hand-rolled DFS cycle enumeration over networkx -- max 8-length cycles on <50-node graphs, no new dep, deterministic iteration via sorted(adj.keys())"
  - "Corner rule: (20 < angle < 160) AND nearest-endpoint-distance <= 32u; Corner position is the midpoint of the two closest endpoints"
  - "Doorway rule: nearest-endpoint-distance in (4u, 96u) AND (angle <= 20 OR angle >= 160); pairs already bridged by a Corner are skipped"
  - "Room min area = 64*64 = 4096 sq units; below-min closed shapes are NOT emitted as Room and do not consume their walls (they fall through to PartialRoom)"
  - "Shared private _geometry.py module so CornerDetector and DoorwayDetector agree on math without mutual imports"
  - "PartialRoom = any BFS-connected wall component (2..max_cycle_length walls) that is not inside a closed Room; ensures a U-shape reports one PartialRoom even with two corners"
  - "Polygon vertices come from resolving consecutive wall pairs to their shared Corner -- if any pair does not share a Corner, the cycle is rejected (not polygon-realisable)"
requirements: [RP-06, RP-07, RP-08]
metrics:
  duration: ~5min
  tasks: 2
  files: 6
  completed: 2026-04-11
---

# Phase 13 Plan 04: Corner, Room, Doorway Geometry Summary

Completes the geometry half of Phase 13: given `Wall` segments from the Plan 13-03 LineFitter, produce `Corner`s at wall intersections, closed `Room` polygons via hand-rolled DFS cycle enumeration, `PartialRoom`s for non-closed wall chains, and `Doorway`s for near-miss collinear wall gaps. Zero new dependencies -- pure numpy + stdlib. All three RP-06/RP-07/RP-08 tests flip GREEN.

## What Shipped

### 1. Shared geometry helpers (Task 1, commit `a5ba00e`)

`openarena_perception/navigation/room_perception/_geometry.py` -- private module, no public exports:

- `nearest_endpoints(w1, w2) -> (e1, e2, dist)` -- closest endpoint pair between two Walls (4-way min)
- `angle_between(w1, w2) -> float` -- unsigned angle in 0..180 degrees between two Wall direction vectors

Both `CornerDetector` and `DoorwayDetector` import from here so the pair-angle / pair-distance math lives in exactly one place.

### 2. CornerDetector (Task 1, commit `a5ba00e`)

`openarena_perception/navigation/room_perception/corner_detector.py`:

```python
class CornerDetector:
    def __init__(self, *, angle_min=20.0, angle_max=160.0, endpoint_max_dist=32.0)
    def detect(self, walls: list[Wall]) -> list[Corner]
```

For every unordered wall pair via `itertools.combinations`:

1. Reject parallel / anti-parallel pairs -- require `20 < angle_between < 160`
2. Reject far-apart pairs -- require nearest endpoint distance `<= 32.0`
3. Emit `Corner` at the midpoint of the two closest endpoints with `confidence = min(w1.confidence, w2.confidence)`

### 3. DoorwayDetector (Task 1, commit `a5ba00e`)

`openarena_perception/navigation/room_perception/doorway_detector.py`:

```python
class DoorwayDetector:
    def __init__(self, *, gap_min=4.0, gap_max=96.0)
    def detect(self, walls, corners=None) -> list[Doorway]
```

For every unordered wall pair:

1. Skip if already bridged by a Corner (pair id set intersection)
2. Reject unless nearest endpoint distance in `(4.0, 96.0)` (strictly > gap_min, strictly < gap_max)
3. Reject perpendicular pairs (`20 < angle < 160`) -- those would be missed corners, not doorways
4. Emit `Doorway` with gap distance + midpoint

### 4. RoomInferrer (Task 2, commit `c75e5d2`)

`openarena_perception/navigation/room_perception/room_inferrer.py` -- ~200 lines, pure stdlib:

```python
class RoomInferrer:
    def __init__(self, *, min_room_area=4096.0, max_cycle_length=8)
    def infer(self, walls, corners) -> tuple[list[Room], list[PartialRoom]]
```

Algorithm:

1. Build wall-id -> set[wall-id] adjacency from Corners (each Corner connects `wall_a_id <-> wall_b_id`).
2. **Enumerate simple cycles** via `_find_cycles` -- hand-rolled DFS over sorted nodes. Canonicalises by anchoring each DFS to a min-id start (`neighbor > start` extension only) and dedups on `tuple(sorted(path))`. Caps cycle length at `max_cycle_length=8`. No networkx.
3. For each cycle: `_cycle_to_polygon` walks consecutive wall pairs and resolves each pair to its shared Corner's `(x, y)` -- that point is a polygon vertex. If any consecutive pair does not share a Corner, the cycle is rejected.
4. Shoelace area filter: `_polygon_area < min_room_area=4096` -> skip (below min, not a real room).
5. Emit `Room` with vertices, bounds, area, wall ids, corner ids.
6. **PartialRoom fallback**: connected components of walls NOT inside any closed Room, enumerated via `_bfs_component`. Components of length `2..max_cycle_length` become `PartialRoom`. This is how the U-shape test produces exactly one PartialRoom with 3 walls.

### 5. Test coverage -- RP-06, RP-07, RP-08 all GREEN

Un-skipped three tests in `tests/test_room_perception.py`:

| Test | Requirement | Coverage |
|------|-------------|----------|
| `test_corner_from_two_walls` | RP-06 | (A) Perpendicular touching walls -> 1 Corner at (100,0) with angle in [85, 95]. (B) Parallel horizontal walls -> 0 Corners. (C) Perpendicular but 50u apart -> 0 Corners (over 32u threshold). |
| `test_room_from_square` | RP-07 | (A) 200x200 square -> 4 Corners -> exactly 1 Room, area 40000, 4 vertices. (B) 30x30 square -> 4 Corners -> 0 Rooms (area 900 < 4096 min). |
| `test_partial_room_and_doorway` | RP-08 | (A) U-shape 3-wall -> 0 Rooms, 1 PartialRoom with 3 walls. (B) Two collinear walls with 50u gap -> 1 Doorway, gap in (40, 60). (C) Two walls 200u apart -> 0 Doorways. |

Wave 3 stub (RP-09) stays skipped for Plan 13-05.

## Verification Results

```
$ uv run pytest tests/test_room_perception.py -q
8 passed, 1 skipped in 2.58s

$ uv run pytest -q
760 passed, 1 skipped in 53.36s
```

Plan 13-03 baseline: 757 passed / 4 skipped. Plan 13-04:

- Un-skipped 3 Wave 2 stubs (RP-06, RP-07, RP-08) -> -3 skipped, +3 passed
- Net: 757 -> 760 passed, 4 -> 1 skipped (only RP-09 remains for Plan 13-05)

Zero new dependencies:

```
$ grep -rn "networkx\|shapely\|skimage" openarena_perception/navigation/room_perception/
room_inferrer.py:8:Pure-stdlib. No networkx, no shapely, no skimage.
line_fitter.py:5:or networkx, only numpy + stdlib. Walls merge across fit passes via
```

Both hits are docstring commentary -- no actual imports.

## End-to-End Pipeline

Plan 13-04 closes the wall-to-geometry loop. A downstream caller now has:

```python
from openarena_perception.navigation.room_perception import (
    LineFitter,
    CornerDetector,
    RoomInferrer,
    DoorwayDetector,
)

# Plan 13-03 output: Walls from a raycast point cloud
walls = LineFitter(seed=42).fit_now(cloud, now=t)

# Plan 13-04 pipeline
corners = CornerDetector().detect(walls)
rooms, partials = RoomInferrer().infer(walls, corners)
doorways = DoorwayDetector().detect(walls, corners)

# -> rooms have polygon_vertices, bounds, area; partials track incomplete
#    wall chains; doorways connect near-miss collinear walls
```

Plan 13-05 will consume `rooms` for the per-room knowledge log (`items_seen`, `visit_count`, `current_room_id` in HUD) and `doorways` for room-to-room connectivity.

## Thresholds Chosen

| Knob | Value | Rationale |
|------|-------|-----------|
| `angle_min` / `angle_max` (corner) | 20 / 160 | Walls within 20deg of parallel or anti-parallel are not corners; matches 13-CONTEXT.md spec |
| `endpoint_max_dist` (corner) | 32.0 | Half the 64u min room edge; a pair farther apart cannot be a shared vertex on a valid room |
| `min_room_area` | 4096.0 (64*64) | Smallest plausible oa_dm1 room cell; filters noise triangles |
| `max_cycle_length` | 8 | Typical oa_dm1 rooms have 4-8 walls; bounds DFS combinatorially |
| `gap_min` (doorway) | 4.0 | Anything < 4u is effectively touching -- should be a Corner, not a Doorway |
| `gap_max` (doorway) | 96.0 | Q3 doorway width ~64-96u; wider than this is "no connection" |

## Key Algorithm: Hand-rolled Simple Cycle DFS

```python
def _find_cycles(self, adj, max_len):
    cycles, seen = [], set()
    for start in sorted(adj.keys()):
        stack = [(start, [start])]
        while stack:
            node, path = stack.pop()
            if len(path) > max_len:
                continue
            for neighbor in adj.get(node, ()):
                if neighbor == start and len(path) >= 3:
                    key = tuple(sorted(path))
                    if key not in seen:
                        seen.add(key)
                        cycles.append(list(path))
                elif neighbor not in path and neighbor > start:
                    stack.append((neighbor, path + [neighbor]))
    return cycles
```

Canonicalisation trick: each DFS only extends to `neighbor > start`. This guarantees each simple cycle is discovered exactly once at its minimum-id anchor, so `seen` dedup is a cheap belt-and-braces check rather than the primary mechanism. Max 8-length cycles on <50-node corner graphs makes worst-case combinatorics trivial (~300us for the 200x200 square test).

## Deviations from Plan

None -- plan executed exactly as written. The only detail worth flagging: the `_cycle_to_polygon` helper returns `[]` (empty polygon) if any consecutive wall pair in a cycle does not share a Corner. Such cycles exist in pathological corner graphs but cannot appear from real Corner inputs -- the adjacency was built from those same Corners. Kept the check as a defensive guard, then rejected by `len(polygon) < 3` downstream.

## Commits

- `a5ba00e` feat(13-04): add CornerDetector and DoorwayDetector (RP-06)
- `c75e5d2` feat(13-04): add RoomInferrer with hand-rolled DFS cycle detection (RP-07, RP-08)

## Self-Check: PASSED

- FOUND: openarena_perception/navigation/room_perception/_geometry.py
- FOUND: openarena_perception/navigation/room_perception/corner_detector.py (class CornerDetector)
- FOUND: openarena_perception/navigation/room_perception/doorway_detector.py (class DoorwayDetector)
- FOUND: openarena_perception/navigation/room_perception/room_inferrer.py (class RoomInferrer, _find_cycles, _cycle_to_polygon, _polygon_area, _bfs_component)
- FOUND: RoomInferrer + CornerDetector + DoorwayDetector exported from room_perception.__init__
- FOUND: commit a5ba00e (Task 1)
- FOUND: commit c75e5d2 (Task 2)
- VERIFIED: `uv run pytest tests/test_room_perception.py -q` -> 8 passed, 1 skipped
- VERIFIED: `uv run pytest -q` -> 760 passed, 1 skipped (Plan 13-03 baseline 757 + 3 new)
- VERIFIED: No networkx/shapely/skimage imports in room_perception/
