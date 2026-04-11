"""Phase 13 test stubs for room perception subsystems.

Each test is a placeholder that downstream plans (13-03, 13-04, 13-05)
will implement by REMOVING the skip marker and adding assertions.
"""
from __future__ import annotations

import pytest


# ---- Wave 1: Plan 13-03 LineFitter (RP-03, RP-04, RP-05) ----

@pytest.mark.skip(reason="Wave 1 — Plan 13-03 RP-03")
def test_ransac_four_wall_rectangle(rect_point_cloud):
    """RP-03: fitted 4-wall rectangle produces exactly 4 walls within 2-unit tolerance; seeded RNG identical across runs."""
    raise NotImplementedError


@pytest.mark.skip(reason="Wave 1 — Plan 13-03 RP-04")
def test_fit_cadence():
    """RP-04: 10s fake-clock test shows exactly 3 fit calls at 3s default cadence; per-tick update NEVER invokes fitter."""
    raise NotImplementedError


@pytest.mark.skip(reason="Wave 1 — Plan 13-03 RP-05")
def test_wall_merge(rect_point_cloud):
    """RP-05: running fit twice on same cloud yields same N walls with doubled support_count, not 2N walls."""
    raise NotImplementedError


# ---- Wave 2: Plan 13-04 Corner + Room (RP-06, RP-07, RP-08) ----

@pytest.mark.skip(reason="Wave 2 — Plan 13-04 RP-06")
def test_corner_from_two_walls():
    """RP-06: two perpendicular walls with touching endpoints -> exactly 1 corner; two parallel walls -> 0 corners."""
    raise NotImplementedError


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
