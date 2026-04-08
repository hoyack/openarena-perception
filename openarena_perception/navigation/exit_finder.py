"""
exit_finder.py — Scan-and-probe exit finding for stuck recovery.

When the bot is stuck, instead of random jumping:
  1. SCAN: Capture 8 directions, score each for visual openness
  2. PROBE: Walk briefly in the top candidates, measure distance moved
  3. COMMIT: Go in the direction that moved the most

This replaces the old blind stuck recovery with intelligent room analysis.
Runs in ~4 seconds total (scan + probe).
"""

from __future__ import annotations

import logging
import math
import re
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from openarena_perception.game_bridge import GameBridge

log = logging.getLogger(__name__)


def score_frame_openness(frame: np.ndarray) -> float:
    """Score how 'open' a view looks. Higher = more depth/corridor/doorway."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    center = gray[int(h * 0.2):int(h * 0.7), int(w * 0.2):int(w * 0.8)]
    edges = cv2.Canny(center, 50, 150)
    edge_score = float(edges.mean())
    brightness = float(center.mean())
    return edge_score * 0.7 + brightness * 0.3


def find_exit(
    bridge: GameBridge,
    capture_fn,
    num_directions: int = 8,
    probe_top: int = 3,
    probe_walk_time: float = 0.8,
) -> Optional[Tuple[float, float]]:
    """
    Scan the room, probe the most open directions, return the best exit.

    Args:
        bridge: GameBridge for pipe commands and RCON
        capture_fn: callable that returns a BGR numpy frame
        num_directions: how many directions to scan (default 8 = every 45 deg)
        probe_top: how many top candidates to physically probe
        probe_walk_time: seconds to walk during each probe

    Returns:
        (yaw, distance_moved) for the best exit, or None if completely stuck.
    """
    angle_step = 360 / num_directions

    # Release movement
    bridge.stop_movement()
    bridge.cmd("centerview")
    time.sleep(0.2)

    # Get starting position
    raw = bridge.rcon("viewpos")
    m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)\s*:\s*(-?\d+)", raw)
    if not m:
        return None
    start_x = float(m.group(1))
    start_y = float(m.group(2))
    start_yaw = float(m.group(4))

    # SCAN phase: capture each direction and score openness
    candidates = []
    for i in range(num_directions):
        if i > 0:
            bridge.cmd("cl_yawspeed 250")
            bridge.cmd("+right")
            time.sleep(angle_step / 250)
            bridge.cmd("-right")
            time.sleep(0.15)

        bridge.cmd("centerview")
        time.sleep(0.08)

        raw = bridge.rcon("viewpos")
        m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)\s*:\s*(-?\d+)", raw)
        if not m:
            continue
        yaw = float(m.group(4))

        frame = capture_fn()
        if frame is None:
            continue

        openness = score_frame_openness(frame)
        candidates.append((openness, yaw, i))

    if not candidates:
        return None

    # Sort by openness (highest first)
    candidates.sort(reverse=True)

    # PROBE phase: walk briefly in top candidates, measure actual movement
    best_result = None
    best_moved = 0

    for openness, probe_yaw, idx in candidates[:probe_top]:
        # Turn to this direction (closed-loop)
        for correction in range(3):
            raw = bridge.rcon("viewpos")
            m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)\s*:\s*(-?\d+)", raw)
            if not m:
                break
            cur_yaw = float(m.group(4))
            delta = ((probe_yaw - cur_yaw + 180) % 360) - 180
            if abs(delta) < 5:
                break
            speed = min(300, max(60, abs(delta) * 4))
            direction = "left" if delta > 0 else "right"
            bridge.cmd(f"cl_yawspeed {int(speed)}")
            bridge.action_start(direction)
            time.sleep(abs(delta) / speed)
            bridge.action_stop(direction)
            time.sleep(0.03)

        # Record position before probe
        raw = bridge.rcon("viewpos")
        m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)\s*:\s*(-?\d+)", raw)
        if not m:
            continue
        px0, py0 = float(m.group(1)), float(m.group(2))

        # Walk forward
        bridge.cmd("+forward")
        time.sleep(probe_walk_time)
        bridge.cmd("-forward")
        time.sleep(0.15)

        # Measure distance moved
        raw = bridge.rcon("viewpos")
        m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)\s*:\s*(-?\d+)", raw)
        if not m:
            continue
        px1, py1 = float(m.group(1)), float(m.group(2))
        dist_moved = math.hypot(px1 - px0, py1 - py0)

        log.info("Exit probe: view %d yaw=%.0f openness=%.1f moved=%.0f",
                 idx, probe_yaw, openness, dist_moved)

        if dist_moved > best_moved:
            best_moved = dist_moved
            best_result = (probe_yaw, dist_moved)

        # Walk back to center
        bridge.cmd("+back")
        time.sleep(probe_walk_time * 0.7)
        bridge.cmd("-back")
        time.sleep(0.15)

    if best_result and best_result[1] > 30:
        log.info("Best exit: yaw=%.0f (moved %.0f units)", best_result[0], best_result[1])
        return best_result

    log.warning("No viable exit found (best moved %.0f)", best_moved)
    return None
