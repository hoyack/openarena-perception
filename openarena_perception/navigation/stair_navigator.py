"""
stair_navigator.py — Specialized navigation for complex staircase geometry.

Q3 maps have L-shaped, switchback, and narrow stairs that require:
  1. Detecting we're facing stairs (visual + AAS height delta)
  2. Assessing the approach angle (which side to enter from)
  3. Executing a probe-and-climb strategy (try angles until one gains height)

The key insight: staircases are narrow corridors with a specific entry point.
Walking straight at them from any angle doesn't work — you have to align
with the corridor first, THEN walk forward with jump-walking.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Optional, Tuple

log = logging.getLogger(__name__)


class StairNavigator:
    """Handles complex stair approach and climbing."""

    # Probe directions: angles relative to current yaw
    PROBE_ANGLES = [0, -30, 30, -60, 60, -90, 90, 180]
    PROBE_WALK_TIME = 0.6   # seconds to walk in each probe direction
    CLIMB_JUMP_INTERVAL = 0.15  # seconds between jumps while climbing
    MAX_CLIMB_TIME = 8.0    # max seconds to attempt a climb

    def __init__(self, bridge, capture_fn=None):
        self.bridge = bridge
        self.capture_fn = capture_fn
        self._climbing = False
        self._climb_start = 0.0

    def detect_stairs_ahead(self, frame, pos_z: float, target_z: float) -> bool:
        """
        Detect if there are stairs ahead that require special handling.

        Criteria:
          - Target is significantly above us (height delta > 20)
          - Frame shows ascending geometry (dark horizontal lines = step edges)
        """
        import cv2
        import numpy as np

        height_delta = target_z - pos_z
        if height_delta < 20:
            return False

        # Analyze center of frame for stair-like horizontal edges
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Look at center-lower region where stairs would appear
        roi = gray[int(h * 0.3):int(h * 0.75), int(w * 0.2):int(w * 0.8)]

        # Horizontal edges = stair step edges
        edges_h = cv2.Sobel(roi, cv2.CV_64F, 0, 1, ksize=3)
        edges_h = abs(edges_h)

        # Strong horizontal lines indicate step edges
        row_sums = edges_h.mean(axis=1)
        strong_rows = sum(1 for r in row_sums if r > row_sums.mean() * 2)

        # Multiple strong horizontal edges = stairs
        stair_score = strong_rows / len(row_sums) if len(row_sums) > 0 else 0

        if stair_score > 0.1 and height_delta > 20:
            log.info("Stairs detected: height_delta=%.0f, stair_score=%.2f",
                     height_delta, stair_score)
            return True
        return False

    def assess_approach(self, bridge, current_pos: Tuple[float, float, float],
                        target_start: Tuple[float, float, float]) -> float:
        """
        Probe multiple approach angles to find which one gains the most height.

        Strategy: try walking at different angles for a short burst, measure
        height gained. The angle that gains the most height is the correct
        stair approach.

        Returns: best yaw angle to approach stairs from, or current yaw if probing fails.
        """
        import re

        best_angle = 0
        best_height_gain = 0
        start_x, start_y, start_z = current_pos

        # Calculate base yaw toward target
        base_yaw = math.degrees(math.atan2(
            target_start[1] - start_y,
            target_start[0] - start_x
        ))

        log.info("Assessing stair approach from (%.0f,%.0f,%.0f) toward (%.0f,%.0f,%.0f)",
                 start_x, start_y, start_z, *target_start)

        for angle_offset in self.PROBE_ANGLES:
            probe_yaw = (base_yaw + angle_offset) % 360

            # Turn to probe angle
            bridge.cmd(f"cl_yawspeed 400")
            # Set yaw directly via setviewpos if available, or use turn commands
            self._turn_to_yaw(bridge, probe_yaw)

            # Walk forward + jump for a short burst
            bridge.cmd("+forward")
            for _ in range(4):
                bridge.cmd("+moveup")
                bridge.cmd("-moveup")
                time.sleep(self.CLIMB_JUMP_INTERVAL)
            bridge.cmd("-forward")
            time.sleep(0.1)

            # Check height gained
            raw = bridge.rcon("viewpos")
            m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)", raw)
            if m:
                new_z = float(m.group(3))
                height_gain = new_z - start_z
                dist_moved = math.hypot(float(m.group(1)) - start_x,
                                        float(m.group(2)) - start_y)

                log.info("  Probe yaw=%.0f (offset=%d): height=%.0f, dist=%.0f",
                         probe_yaw, angle_offset, height_gain, dist_moved)

                if height_gain > best_height_gain:
                    best_height_gain = height_gain
                    best_angle = probe_yaw

                # If we gained significant height, that's the way up
                if height_gain > 15:
                    log.info("  Found stair entry at yaw=%.0f (gained %.0f height)",
                             probe_yaw, height_gain)
                    return probe_yaw

            # Walk back to starting position
            bridge.cmd("+back")
            time.sleep(self.PROBE_WALK_TIME)
            bridge.cmd("-back")
            time.sleep(0.1)

        if best_height_gain > 5:
            log.info("Best approach: yaw=%.0f (gained %.0f)", best_angle, best_height_gain)
            return best_angle

        log.warning("No good stair approach found (best gain: %.0f)", best_height_gain)
        return base_yaw

    def climb(self, bridge, target_yaw: float, timeout: float = None) -> bool:
        """
        Execute stair climbing at a specific yaw angle.

        Uses rapid jump-walk: centerview, face the right direction,
        then forward + continuous jumping until height gain stops or timeout.

        Returns True if we gained height.
        """
        import re

        if timeout is None:
            timeout = self.MAX_CLIMB_TIME

        # Get starting height
        raw = bridge.rcon("viewpos")
        m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)", raw)
        if not m:
            return False
        start_z = float(m.group(3))

        log.info("Climbing stairs at yaw=%.0f from z=%.0f", target_yaw, start_z)

        # Level view and face the stairs
        bridge.cmd("centerview")
        self._turn_to_yaw(bridge, target_yaw)

        # Rapid jump-walk
        bridge.cmd("+forward")
        climb_start = time.time()
        last_z = start_z
        stall_count = 0

        while time.time() - climb_start < timeout:
            bridge.cmd("+moveup")
            bridge.cmd("-moveup")
            time.sleep(self.CLIMB_JUMP_INTERVAL)

            # Check height periodically
            if int((time.time() - climb_start) * 5) % 5 == 0:
                raw = bridge.rcon("viewpos")
                m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)", raw)
                if m:
                    current_z = float(m.group(3))
                    if current_z > last_z + 3:
                        stall_count = 0
                        last_z = current_z
                    else:
                        stall_count += 1

                    # If we've stalled for 2 seconds, we're at the top or stuck
                    if stall_count > 10:
                        break

        bridge.cmd("-forward")

        # Check final height
        time.sleep(0.2)
        raw = bridge.rcon("viewpos")
        m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)", raw)
        if m:
            final_z = float(m.group(3))
            gained = final_z - start_z
            log.info("Climb result: z %.0f -> %.0f (gained %.0f in %.1fs)",
                     start_z, final_z, gained, time.time() - climb_start)
            return gained > 10

        return False

    def _turn_to_yaw(self, bridge, target_yaw: float):
        """Turn to a specific yaw angle using RCON viewpos feedback."""
        import re

        for _ in range(5):
            raw = bridge.rcon("viewpos")
            m = re.search(r":\s*(-?\d+)", raw)
            if not m:
                time.sleep(0.1)
                continue

            current_yaw = float(m.group(1))
            delta = (target_yaw - current_yaw + 180) % 360 - 180

            if abs(delta) < 5:
                bridge.cmd("-left")
                bridge.cmd("-right")
                return

            speed = min(400, max(80, abs(delta) * 3))
            duration = abs(delta) / speed

            bridge.cmd(f"cl_yawspeed {int(speed)}")
            direction = "left" if delta > 0 else "right"
            bridge.cmd(f"+{direction}")
            time.sleep(duration)
            bridge.cmd(f"-{direction}")
            time.sleep(0.05)
