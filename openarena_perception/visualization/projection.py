"""Pure pinhole projection + tessellation + depth-color math.

Zero cv2 imports. Pure numpy/math. Enables unit testing on any host without
OpenCV baggage. Consumed by WireframeRoomRenderer (Plan 11-02) and
AASDepthBackend (Plan 11-03).

Camera convention:
    +X right, +Y down, +Z forward

World convention (Quake 3 / OpenArena):
    +X east, +Y north, +Z up. Yaw is degrees CCW from +X (east=0°, north=90°).
    Canonical formula: navigator.py:292 `math.degrees(math.atan2(dy, dx))`.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np

from openarena_perception.visualization.config import RoomConfig

Point3 = Tuple[float, float, float]
Segment3 = Tuple[Point3, Point3]
Pixel = Tuple[int, int]
Segment2 = Tuple[Pixel, Pixel]

NEAR_Z: float = 0.1  # near-plane clip distance (Pitfall 3)


def focal_length(width: int, fov_deg: float) -> float:
    return width / (2.0 * math.tan(math.radians(fov_deg) / 2.0))


def project_point(
    x: float, y: float, z: float, cfg: RoomConfig
) -> Optional[Pixel]:
    """Pinhole project a 3D camera-space point to pixel coords.

    Returns None if z <= NEAR_Z (behind / on near plane). Uses np.round
    (not int-cast) to avoid sub-pixel shimmer during orbit (Pitfall 6).
    """
    if z <= NEAR_Z:
        return None
    fx = focal_length(cfg.width, cfg.fov_deg)
    sx = cfg.width / 2.0 + x * fx / z
    sy = cfg.height / 2.0 + y * fx / z   # fy == fx, square pixels
    return (int(np.round(sx)), int(np.round(sy)))


def project_line(
    p1: Point3, p2: Point3, cfg: RoomConfig
) -> Optional[Segment2]:
    """Project a 3D line segment with near-plane clipping.

    Both endpoints behind → None. One behind → parametric trim to NEAR_Z.
    """
    x1, y1, z1 = p1
    x2, y2, z2 = p2

    if z1 <= NEAR_Z and z2 <= NEAR_Z:
        return None
    if z1 <= NEAR_Z:
        # Clip p1 onto NEAR_Z along segment
        t = (NEAR_Z - z1) / (z2 - z1)
        x1 = x1 + t * (x2 - x1)
        y1 = y1 + t * (y2 - y1)
        z1 = NEAR_Z
    elif z2 <= NEAR_Z:
        t = (NEAR_Z - z2) / (z1 - z2)
        x2 = x2 + t * (x1 - x2)
        y2 = y2 + t * (y1 - y2)
        z2 = NEAR_Z

    sp1 = project_point(x1, y1, z1, cfg)
    sp2 = project_point(x2, y2, z2, cfg)
    if sp1 is None or sp2 is None:
        return None
    return (sp1, sp2)


def room_surface_grid(
    origin: Point3,
    axis_u: Point3,
    axis_v: Point3,
    divs_u: int,
    divs_v: int,
) -> List[Segment3]:
    """Tessellate a parametric quad into iso-line segments.

    Returns (divs_u + 1) + (divs_v + 1) segments: iso-u lines sweep v, iso-v
    lines sweep u. Evenly spaced per PRD §4.2.
    """
    ox, oy, oz = origin
    ux, uy, uz = axis_u
    vx, vy, vz = axis_v
    segs: List[Segment3] = []

    # iso-u lines: for each step in u, a line along v
    for i in range(divs_u + 1):
        t = i / divs_u if divs_u > 0 else 0.0
        sx = ox + t * ux
        sy = oy + t * uy
        sz = oz + t * uz
        ex = sx + vx
        ey = sy + vy
        ez = sz + vz
        segs.append(((sx, sy, sz), (ex, ey, ez)))

    # iso-v lines: for each step in v, a line along u
    for j in range(divs_v + 1):
        t = j / divs_v if divs_v > 0 else 0.0
        sx = ox + t * vx
        sy = oy + t * vy
        sz = oz + t * vz
        ex = sx + ux
        ey = sy + uy
        ez = sz + uz
        segs.append(((sx, sy, sz), (ex, ey, ez)))

    return segs


def project_depth_color(z: float, cfg: RoomConfig) -> Tuple[int, int, int]:
    """Near-warning / interpolated / far-faded color per PRD §4.4."""
    if z < cfg.proximity_threshold:
        return cfg.warning_color
    max_z = cfg.max_depth if cfg.max_depth > 0 else 1.0
    t = (max(z, 0.0) / max_z) ** cfg.fade_power
    t = min(max(t, 0.0), 1.0)
    nr, ng, nb = cfg.near_color
    fr, fg, fb = cfg.far_color
    r = int(round(nr + (fr - nr) * t))
    g = int(round(ng + (fg - ng) * t))
    b = int(round(nb + (fb - nb) * t))
    return (r, g, b)


def cube_edges(
    x: float, y: float, z: float, w: float, h: float, d: float
) -> Tuple[Segment3, ...]:
    """12 edges of an AABB centered at (x,y,z) with full extents (w,h,d)."""
    hw, hh, hd = w / 2.0, h / 2.0, d / 2.0
    x0, x1 = x - hw, x + hw
    y0, y1 = y - hh, y + hh
    z0, z1 = z - hd, z + hd
    v = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),   # z0 ring
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),   # z1 ring
    ]
    idx = [(0, 1), (1, 2), (2, 3), (3, 0),
           (4, 5), (5, 6), (6, 7), (7, 4),
           (0, 4), (1, 5), (2, 6), (3, 7)]
    return tuple((v[a], v[b]) for a, b in idx)


def screen_to_room(
    bbox_2d: Tuple[int, int, int, int],
    cfg: RoomConfig,
    depth_hint: float,
) -> Tuple[float, float, float, float, float, float]:
    """Unproject a screen-space bbox to a camera-space AABB at depth_hint.

    Version B escape hatch: used when a 2D detection needs to be placed into
    the wireframe room without a known world position. depth_hint is the
    assumed camera-space Z (metric) for the detection.
    """
    x1, y1, x2, y2 = bbox_2d
    z = max(depth_hint, NEAR_Z + 1e-3)
    fx = focal_length(cfg.width, cfg.fov_deg)
    cx = cfg.width / 2.0
    cy = cfg.height / 2.0
    # Unproject the two corners at the same z
    world_x1 = (x1 - cx) * z / fx
    world_y1 = (y1 - cy) * z / fx
    world_x2 = (x2 - cx) * z / fx
    world_y2 = (y2 - cy) * z / fx
    wx = (world_x1 + world_x2) / 2.0
    wy = (world_y1 + world_y2) / 2.0
    w = abs(world_x2 - world_x1)
    h = abs(world_y2 - world_y1)
    d = w * 0.5  # PRD §5.1 depth heuristic
    return (wx, wy, z, w, h, d)


def world_to_camera(
    world_xyz,
    bot_pos: Point3,
    bot_yaw_deg: float,
    camera_height: Optional[float] = None,
):
    """Q3 world coordinates → renderer camera coordinates.

    Accepts either a 3-tuple (returns 3-tuple) or an ndarray of shape (N, 3)
    (returns ndarray of the same shape). Batched numpy path is used for the
    AAS backend; the scalar path is used for per-point tests.

    Pitfalls 1 and 2 addressed:
      - Q3 yaw is CCW from +X: east=0°, north=90° (navigator.py:292).
      - Q3 +Z is up; screen +Y is down → negate.
      - After rotating world by -yaw, the bot's forward direction lands on
        world +Y, which becomes camera +Z (forward).
    """
    cam_h = camera_height if camera_height is not None else 0.0

    is_tuple = not isinstance(world_xyz, np.ndarray)
    if is_tuple:
        arr = np.array(world_xyz, dtype=np.float64).reshape(1, 3)
    else:
        arr = np.asarray(world_xyz, dtype=np.float64)
        if arr.ndim == 1:
            arr = arr.reshape(1, 3)

    bx, by, bz = bot_pos
    dx = arr[:, 0] - bx
    dy = arr[:, 1] - by
    dz = arr[:, 2] - bz

    yaw_rad = math.radians(bot_yaw_deg)
    cos_y = math.cos(yaw_rad)
    sin_y = math.sin(yaw_rad)

    fwd = cos_y * dx + sin_y * dy          # → +Z camera
    right = -sin_y * dx + cos_y * dy       # → +X camera

    cam = np.empty_like(arr)
    cam[:, 0] = right
    cam[:, 1] = -dz + cam_h
    cam[:, 2] = fwd

    if is_tuple:
        return (float(cam[0, 0]), float(cam[0, 1]), float(cam[0, 2]))
    return cam
