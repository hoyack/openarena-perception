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


@pytest.mark.skip(reason="Wave 2 — Plan 13-04 RP-07")
def test_room_from_square():
    """RP-07: synthetic 4-corner square graph -> exactly 1 Room; triangle below min-area -> 0 Rooms."""
    raise NotImplementedError


@pytest.mark.skip(reason="Wave 2 — Plan 13-04 RP-08")
def test_partial_room_and_doorway(u_shape_point_cloud):
    """RP-08: 3-wall U -> 1 PartialRoom, 0 rooms rendered; adjacent rooms with <96u gap -> 1 Doorway."""
    raise NotImplementedError


# ---- Wave 3: Plan 13-05 Room log + HUD (RP-09) ----

@pytest.mark.skip(reason="Wave 3 — Plan 13-05 RP-09")
def test_item_ingestion_pip():
    """RP-09: observing a weapon inside room R's polygon appends to R.items_seen via cv2.pointPolygonTest; visit_count increments once per entry, not per tick."""
    raise NotImplementedError
