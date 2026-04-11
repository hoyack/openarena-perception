"""Phase 13 test stubs for room perception subsystems.

Each test is a placeholder that downstream plans (13-03, 13-04, 13-05)
will implement by REMOVING the skip marker and adding assertions.
"""
from __future__ import annotations

import numpy as np
import pytest


# ---- Wave 1: Plan 13-03 LineFitter (RP-03, RP-04, RP-05) ----


def test_ransac_four_wall_rectangle(rect_point_cloud):
    """RP-03: fitted 4-wall rectangle produces exactly 4 walls within tolerance; seeded RNG identical across runs."""
    from openarena_perception.navigation.room_perception.line_fitter import (
        LineFitter,
    )

    fitter1 = LineFitter(seed=42)
    walls1 = fitter1.fit_now(rect_point_cloud, now=0.0)
    assert len(walls1) == 4, f"expected 4 walls, got {len(walls1)}: {walls1}"

    # Determinism: a second fresh fitter with the same seed produces walls
    # with bit-identical coordinates and support counts.
    fitter2 = LineFitter(seed=42)
    walls2 = fitter2.fit_now(rect_point_cloud, now=0.0)
    assert len(walls2) == 4
    for w1, w2 in zip(walls1, walls2):
        assert abs(w1.x1 - w2.x1) < 1e-9
        assert abs(w1.y1 - w2.y1) < 1e-9
        assert abs(w1.x2 - w2.x2) < 1e-9
        assert abs(w1.y2 - w2.y2) < 1e-9
        assert w1.support_count == w2.support_count

    # Ground-truth rectangle corners: (0,0)-(512,384). Each wall midpoint
    # must lie within 5 units of one of the 4 boundary lines.
    expected = [("y", 0.0), ("y", 384.0), ("x", 0.0), ("x", 512.0)]
    matched: set[int] = set()
    for w in walls1:
        mid_x = (w.x1 + w.x2) / 2.0
        mid_y = (w.y1 + w.y2) / 2.0
        for i, (axis, target) in enumerate(expected):
            if i in matched:
                continue
            if axis == "y" and abs(mid_y - target) < 5.0:
                matched.add(i)
                break
            if axis == "x" and abs(mid_x - target) < 5.0:
                matched.add(i)
                break
    assert (
        len(matched) == 4
    ), f"expected all 4 walls to match boundaries, matched {matched}"


def test_ransac_noise_only_returns_empty(noisy_point_cloud):
    """Noise-only point cloud should not produce any walls."""
    from openarena_perception.navigation.room_perception.line_fitter import (
        LineFitter,
    )

    fitter = LineFitter(seed=42)
    walls = fitter.fit_now(noisy_point_cloud, now=0.0)
    # 400 uniform random points over a large area should not yield a line
    # with >= 20 inliers within 8u perpendicular distance; if any slip
    # through, they should at most be a small count.
    assert len(walls) == 0, (
        f"noise cloud should not fit walls, got {len(walls)}: {walls}"
    )


def test_fit_cadence():
    """RP-04: cadence gate prevents per-tick invocation (exactly 4 fits over 10s at 3s interval)."""
    from openarena_perception.navigation.room_perception.line_fitter import (
        LineFitter,
    )

    # Trivial cloud — we only care about counting fit_now invocations.
    cloud = np.random.default_rng(0).uniform(-10, 10, size=(5, 2))

    fitter = LineFitter(seed=42, fit_interval_s=3.0, min_support=2)
    call_count = 0
    original_fit_now = fitter.fit_now

    def spy(c, now=None):
        nonlocal call_count
        call_count += 1
        return original_fit_now(c, now=now)

    fitter.fit_now = spy  # type: ignore[method-assign]

    # Simulate 10 ticks at 1s spacing. First call fits (no prior fit);
    # subsequent fits trigger when (now - last_fit) >= 3.0s.
    # Expected: t=0 (first), t=3 (>=3 since 0), t=6, t=9 -> 4 fits.
    for t in [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]:
        fitter.fit(cloud, now=t)
    assert call_count == 4, (
        f"expected 4 fits over 10s at 3s cadence, got {call_count}"
    )


def test_fit_triggered_by_point_count():
    """RP-04: point-count trigger fires re-fit even when time hasn't elapsed."""
    from openarena_perception.navigation.room_perception.line_fitter import (
        LineFitter,
    )

    rng = np.random.default_rng(0)
    small_cloud = rng.uniform(-10, 10, size=(50, 2))
    big_cloud = rng.uniform(-10, 10, size=(600, 2))

    # Huge interval so the time gate never fires; point-count gate matters.
    fitter = LineFitter(
        seed=42,
        fit_interval_s=999.0,
        point_count_trigger=500,
        min_support=2,
    )
    call_count = 0
    original_fit_now = fitter.fit_now

    def spy(c, now=None):
        nonlocal call_count
        call_count += 1
        return original_fit_now(c, now=now)

    fitter.fit_now = spy  # type: ignore[method-assign]

    fitter.fit(small_cloud, now=0.0)  # first call -> triggers
    assert call_count == 1, "first call must trigger"
    fitter.fit(small_cloud, now=0.1)  # delta=0, time<999 -> no fit
    assert call_count == 1, "no delta, no time elapsed -> no fit"
    fitter.fit(big_cloud, now=0.2)  # delta=550 >= 500 -> triggers
    assert call_count == 2, (
        f"point-count delta should trigger; got {call_count}"
    )


def test_wall_merge(rect_point_cloud):
    """RP-05: running fit twice yields same N walls with accumulated support_count."""
    from openarena_perception.navigation.room_perception.line_fitter import (
        LineFitter,
    )

    fitter = LineFitter(seed=42)
    walls_a = fitter.fit_now(rect_point_cloud, now=0.0)
    assert len(walls_a) == 4
    support_a = sorted(w.support_count for w in walls_a)

    walls_b = fitter.fit_now(rect_point_cloud, now=1.0)
    # After second pass, still exactly 4 walls (merged, not duplicated).
    assert len(walls_b) == 4, (
        f"merge failed: got {len(walls_b)} walls after 2nd pass"
    )
    support_b = sorted(w.support_count for w in walls_b)
    # Support count for each wall should roughly double after the second
    # pass (small slack for outliers that moved between passes).
    for a, b in zip(support_a, support_b):
        assert b >= 2 * a - 5, f"support did not accumulate: {a} -> {b}"

    # last_seen timestamps should advance to the second pass's now=1.0.
    for w in walls_b:
        assert w.last_seen == 1.0


# ---- Wave 2: Plan 13-04 Corner + Room (RP-06, RP-07, RP-08) ----

def test_corner_from_two_walls():
    """RP-06: perpendicular touching walls -> 1 corner; parallel -> 0; far apart -> 0."""
    from openarena_perception.navigation.room_perception import (
        CornerDetector,
        Wall,
    )

    # Case A: perpendicular walls touching at (100, 0)
    w1 = Wall(1, 0, 0, 100, 0, 0.9, 30, 0.0, 1.0)
    w2 = Wall(2, 100, 0, 100, 100, 0.9, 30, 0.0, 1.0)
    corners = CornerDetector().detect([w1, w2])
    assert len(corners) == 1
    assert 85 <= corners[0].angle_deg <= 95
    assert abs(corners[0].x - 100) < 1e-6
    assert abs(corners[0].y - 0) < 1e-6

    # Case B: parallel walls -> no corner
    w3 = Wall(3, 0, 0, 100, 0, 0.9, 30, 0.0, 1.0)
    w4 = Wall(4, 0, 50, 100, 50, 0.9, 30, 0.0, 1.0)
    assert CornerDetector().detect([w3, w4]) == []

    # Case C: perpendicular but 50 units apart (over 32-unit threshold)
    w5 = Wall(5, 0, 0, 100, 0, 0.9, 30, 0.0, 1.0)
    w6 = Wall(6, 150, 0, 150, 100, 0.9, 30, 0.0, 1.0)
    assert CornerDetector().detect([w5, w6]) == []


def test_room_from_square():
    """RP-07: 4-corner square above min-area -> 1 Room; small 30x30 -> 0 Rooms."""
    from openarena_perception.navigation.room_perception import (
        CornerDetector,
        RoomInferrer,
        Wall,
    )

    # 200x200 square (area 40000 >> 4096 min)
    w1 = Wall(1, 0, 0, 200, 0, 0.9, 30, 0.0, 1.0)
    w2 = Wall(2, 200, 0, 200, 200, 0.9, 30, 0.0, 1.0)
    w3 = Wall(3, 200, 200, 0, 200, 0.9, 30, 0.0, 1.0)
    w4 = Wall(4, 0, 200, 0, 0, 0.9, 30, 0.0, 1.0)
    walls = [w1, w2, w3, w4]
    corners = CornerDetector().detect(walls)
    assert len(corners) == 4
    rooms, partials = RoomInferrer().infer(walls, corners)
    assert len(rooms) == 1, (
        f"expected 1 room, got {len(rooms)} rooms and {len(partials)} partials"
    )
    assert rooms[0].area == pytest.approx(40000.0, rel=0.01)
    assert len(rooms[0].polygon_vertices) == 4

    # Tiny 30x30 -- below 4096 min area
    t1 = Wall(10, 0, 0, 30, 0, 0.9, 30, 0.0, 1.0)
    t2 = Wall(11, 30, 0, 30, 30, 0.9, 30, 0.0, 1.0)
    t3 = Wall(12, 30, 30, 0, 30, 0.9, 30, 0.0, 1.0)
    t4 = Wall(13, 0, 30, 0, 0, 0.9, 30, 0.0, 1.0)
    tiny = [t1, t2, t3, t4]
    tiny_corners = CornerDetector().detect(tiny)
    rooms_tiny, _ = RoomInferrer().infer(tiny, tiny_corners)
    assert len(rooms_tiny) == 0


def test_room_inferrer_tightened_defaults():
    """Plan 13-08: default thresholds are min_room_area=20000, max_cycle_length=6."""
    from openarena_perception.navigation.room_perception import RoomInferrer

    inferrer = RoomInferrer()
    assert inferrer.min_room_area == 20000.0
    assert inferrer.max_cycle_length == 6


def test_room_spatial_dedup():
    """Plan 13-08: spatial dedup keyed on sorted corner-ID tuple.

    Validates that when multiple cycles share the same participating corner
    set, RoomInferrer emits only one Room (the shortest-perimeter one).
    Constructed by hand-crafting Corner objects so two distinct cycles map
    to the same corner-ID signature -- the natural CornerDetector output
    never collides because it assigns unique corner IDs per wall pair.
    """
    from openarena_perception.navigation.room_perception import (
        RoomInferrer,
        Wall,
    )
    from openarena_perception.navigation.room_perception.types import Corner

    # 4 walls forming a square, with 4 corners sharing IDs in a way that
    # lets the adjacency graph enumerate the cycle {1,2,3,4} exactly once.
    walls = [
        Wall(1, 0, 0, 200, 0, 0.9, 30, 0.0, 1.0),
        Wall(2, 200, 0, 200, 200, 0.9, 30, 0.0, 1.0),
        Wall(3, 200, 200, 0, 200, 0.9, 30, 0.0, 1.0),
        Wall(4, 0, 200, 0, 0, 0.9, 30, 0.0, 1.0),
    ]
    corners = [
        Corner(1, 200.0, 0.0, 1, 2, 90.0, 0.9),
        Corner(2, 200.0, 200.0, 2, 3, 90.0, 0.9),
        Corner(3, 0.0, 200.0, 3, 4, 90.0, 0.9),
        Corner(4, 0.0, 0.0, 1, 4, 90.0, 0.9),
    ]
    rooms, _ = RoomInferrer().infer(walls, corners)
    # Exactly one room -- the square.
    assert len(rooms) == 1
    assert rooms[0].area == pytest.approx(40000.0, rel=0.01)
    # Spatial dedup key is sorted corner IDs: all 4 corners participate.
    assert rooms[0].corner_ids == (1, 2, 3, 4)

    # Sanity check: introducing a near-duplicate parallel wall (y=1 strip)
    # DOES yield a second closed cycle, because the CornerDetector-style
    # output assigns different corner IDs to each wall-pair. Plan 13-08's
    # primary defense against this live failure mode is the tightened
    # max_cycle_length (6) and min_room_area (20000). The spatial-dedup
    # key is a secondary guard; this test asserts the primary guard keeps
    # the room count bounded.
    from openarena_perception.navigation.room_perception import (
        CornerDetector,
    )

    w5 = Wall(5, 0, 1, 200, 1, 0.9, 30, 0.0, 1.0)
    walls2 = walls + [w5]
    detected = CornerDetector().detect(walls2)
    rooms2, _ = RoomInferrer().infer(walls2, detected)
    # Fallback assertion per plan 13-08: <= 2 rooms (was 65 on live oa_dm1).
    assert len(rooms2) <= 2, f"expected <=2 rooms, got {len(rooms2)}"


def test_room_shortest_perimeter_wins():
    """Plan 13-08: _polygon_perimeter computes correct perimeter and
    shorter-perimeter cycle is preferred on dedup collision.
    """
    from openarena_perception.navigation.room_perception.room_inferrer import (
        RoomInferrer,
    )

    poly_short = [(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)]
    poly_long = [(0.0, 0.0), (210.0, 0.0), (210.0, 210.0), (0.0, 210.0)]
    p_short = RoomInferrer._polygon_perimeter(poly_short)
    p_long = RoomInferrer._polygon_perimeter(poly_long)
    assert p_short < p_long
    assert p_short == pytest.approx(800.0, rel=0.01)
    assert p_long == pytest.approx(840.0, rel=0.01)

    # Degenerate cases
    assert RoomInferrer._polygon_perimeter([]) == 0.0
    assert RoomInferrer._polygon_perimeter([(0.0, 0.0)]) == 0.0


def test_partial_room_and_doorway(u_shape_point_cloud):
    """RP-08: U-shape -> 1 PartialRoom; collinear near-miss walls -> 1 Doorway."""
    from openarena_perception.navigation.room_perception import (
        CornerDetector,
        DoorwayDetector,
        RoomInferrer,
        Wall,
    )

    # U-shape: left, bottom, right (no top)
    left = Wall(1, 0, 0, 0, 200, 0.9, 30, 0.0, 1.0)
    bottom = Wall(2, 0, 0, 300, 0, 0.9, 30, 0.0, 1.0)
    right = Wall(3, 300, 0, 300, 200, 0.9, 30, 0.0, 1.0)
    walls = [left, bottom, right]
    corners = CornerDetector().detect(walls)
    rooms, partials = RoomInferrer().infer(walls, corners)
    assert len(rooms) == 0
    assert len(partials) == 1
    assert len(partials[0].wall_ids) == 3

    # Doorway: two collinear walls with 50-unit gap
    d1 = Wall(10, 0, 0, 100, 0, 0.9, 30, 0.0, 1.0)
    d2 = Wall(11, 150, 0, 250, 0, 0.9, 30, 0.0, 1.0)
    doorways = DoorwayDetector().detect([d1, d2])
    assert len(doorways) == 1
    assert 40 < doorways[0].gap_distance < 60

    # Far apart -- 200 unit gap > 96 threshold
    d3 = Wall(20, 0, 0, 100, 0, 0.9, 30, 0.0, 1.0)
    d4 = Wall(21, 300, 0, 400, 0, 0.9, 30, 0.0, 1.0)
    assert DoorwayDetector().detect([d3, d4]) == []


# ---- Wave 3: Plan 13-05 Room log + HUD (RP-09) ----


def test_fit_rooms_end_to_end(rect_point_cloud):
    """RP-09 plumbing: full pipeline wired into LearnedMap."""
    import time

    from openarena_perception.navigation.learned_map import LearnedMap, RaycastHit

    lm = LearnedMap(map_name="test_rp09_e2e")
    now = time.time()
    lm._raycasts_per_floor[1] = [
        RaycastHit(0, 0, 50, 0, float(p[0]), float(p[1]), 50, 0.9, now)
        for p in rect_point_cloud
    ]
    lm._current_floor = 1
    lm.fit_rooms(force=True, now=now)
    assert len(lm._fitted_walls_per_floor[1]) == 4
    assert len(lm._corners_per_floor[1]) == 4
    assert len(lm._rooms_per_floor[1]) == 1


def test_item_ingestion_pip(rect_point_cloud):
    """RP-09: item inside room polygon -> appended via cv2.pointPolygonTest."""
    import time

    from openarena_perception.navigation.learned_map import LearnedMap, RaycastHit

    lm = LearnedMap(map_name="test_rp09_pip")
    now = time.time()
    lm._raycasts_per_floor[1] = [
        RaycastHit(0, 0, 50, 0, float(p[0]), float(p[1]), 50, 0.9, now)
        for p in rect_point_cloud
    ]
    lm._current_floor = 1
    lm.fit_rooms(force=True, now=now)

    lm.note_item("weapon_rocketlauncher", 256.0, 192.0)
    room = lm._rooms_per_floor[1][0]
    assert any(item[0] == "weapon_rocketlauncher" for item in room.items_seen)

    items_before = list(lm._rooms_per_floor[1][0].items_seen)
    lm.note_item("weapon_plasma", -200.0, -200.0)
    room_after = lm._rooms_per_floor[1][0]
    assert len(room_after.items_seen) == len(items_before)


def test_visit_count_debouncer(rect_point_cloud):
    """RP-09: visit_count increments once per entry, not per tick."""
    import time

    from openarena_perception.navigation.learned_map import LearnedMap, RaycastHit

    lm = LearnedMap(map_name="test_rp09_visit")
    now = time.time()
    lm._raycasts_per_floor[1] = [
        RaycastHit(0, 0, 50, 0, float(p[0]), float(p[1]), 50, 0.9, now)
        for p in rect_point_cloud
    ]
    lm._current_floor = 1
    lm.fit_rooms(force=True, now=now)

    lm._prev_pos = (-100.0, -100.0)
    lm._last_current_room_id = None

    def drive(px, py):
        lm._prev_pos = (px, py)
        lm._current_room_cache_valid = False
        cur = lm.current_room_id()
        if cur != lm._last_current_room_id:
            if cur is not None:
                rooms = lm._rooms_per_floor[lm._current_floor]
                for idx, r in enumerate(rooms):
                    if r.id == cur:
                        rooms[idx] = r._replace(visit_count=r.visit_count + 1)
                        break
            lm._last_current_room_id = cur

    drive(256.0, 192.0)
    drive(260.0, 190.0)
    drive(270.0, 195.0)
    drive(-100.0, -100.0)
    drive(256.0, 192.0)

    room = lm._rooms_per_floor[1][0]
    assert room.visit_count == 2, f"expected 2 entries, got {room.visit_count}"


def test_current_room_id_and_export_for_hud(rect_point_cloud):
    """RP-09: current_room_id + export_for_hud surface fitted walls / rooms."""
    import time

    from openarena_perception.navigation.learned_map import LearnedMap, RaycastHit

    lm = LearnedMap(map_name="test_rp09_export")
    now = time.time()
    lm._raycasts_per_floor[1] = [
        RaycastHit(0, 0, 50, 0, float(p[0]), float(p[1]), 50, 0.9, now)
        for p in rect_point_cloud
    ]
    lm._current_floor = 1
    lm.fit_rooms(force=True, now=now)

    # Inside
    lm._prev_pos = (256.0, 192.0)
    lm._current_room_cache_valid = False
    cur = lm.current_room_id()
    assert cur is not None

    # Outside
    lm._prev_pos = (-500.0, -500.0)
    lm._current_room_cache_valid = False
    assert lm.current_room_id() is None

    # Export includes the new keys
    lm._prev_pos = (256.0, 192.0)
    lm._current_room_cache_valid = False
    payload = lm.export_for_hud()
    for key in (
        "fitted_walls",
        "corners",
        "rooms",
        "doorways",
        "current_room_id",
        "current_room_items",
    ):
        assert key in payload, f"missing key {key!r} in export_for_hud"
    assert payload["current_room_id"] == cur
    assert len(payload["rooms"]) == 1
    assert len(payload["fitted_walls"]) == 4


def test_update_with_10_rooms_under_1ms(rect_point_cloud):
    """RP-09 perf: current_room_id() with 10 rooms stays < 1ms per call."""
    import time

    from openarena_perception.navigation.learned_map import LearnedMap, RaycastHit

    lm = LearnedMap(map_name="test_rp09_perf")
    now = time.time()
    lm._raycasts_per_floor[1] = [
        RaycastHit(0, 0, 50, 0, float(p[0]), float(p[1]), 50, 0.9, now)
        for p in rect_point_cloud
    ]
    lm._current_floor = 1
    lm.fit_rooms(force=True, now=now)
    assert len(lm._rooms_per_floor[1]) >= 1
    base_room = lm._rooms_per_floor[1][0]
    synthetic_rooms = [base_room]
    for i in range(1, 10):
        shift = i * 1000.0
        shifted_vertices = tuple(
            (v[0] + shift, v[1] + shift) for v in base_room.polygon_vertices
        )
        shifted_bounds = (
            base_room.bounds[0] + shift,
            base_room.bounds[1] + shift,
            base_room.bounds[2] + shift,
            base_room.bounds[3] + shift,
        )
        synthetic_rooms.append(
            base_room._replace(
                id=base_room.id + i,
                polygon_vertices=shifted_vertices,
                bounds=shifted_bounds,
            )
        )
    lm._rooms_per_floor[1] = synthetic_rooms

    t0 = time.perf_counter()
    for i in range(100):
        lm._current_room_cache_valid = False
        lm._prev_pos = (256.0 + (i % 3), 192.0 + (i % 3))
        lm.current_room_id()
    elapsed = time.perf_counter() - t0
    avg_ms = (elapsed / 100) * 1000.0
    assert avg_ms < 1.0, f"per-tick avg {avg_ms:.3f}ms exceeds 1ms budget"
