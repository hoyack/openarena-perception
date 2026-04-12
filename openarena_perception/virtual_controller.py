"""
virtual_controller.py — Pipe-only game controller (no real mouse movement).

All aim/look/movement commands go through the ioquake3 named pipe.
Never touches the desktop mouse cursor.

Converts pixel-space aim offsets to calibrated pipe turn commands:
  - Horizontal aim: +left/+right with cl_yawspeed (timed duration)
  - Vertical aim: +lookup/+lookdown with cl_pitchspeed (timed duration)
  - Movement: +forward/+back/+moveleft/+moveright via pipe
  - Actions: +attack, +moveup (jump), weapon selection via pipe

The key calibration:
  Q3 default FOV = 90° horizontal over 800px = 0.1125°/px
  Vertical FOV = 73.74° over 600px = 0.1229°/px
  cl_yawspeed N means N degrees/second of turning
  So to turn X degrees: duration = X / cl_yawspeed
"""

from __future__ import annotations

import logging
import math
import time
from typing import Optional, Tuple

from .game_bridge import GameBridge

log = logging.getLogger(__name__)


class VirtualController:
    """
    Pipe-only controller. All inputs go through the named pipe.
    No pynput, no real mouse, no desktop cursor movement.
    """

    # FOV calibration (default Q3 settings at 800x600)
    SCREEN_W = 800
    SCREEN_H = 600
    H_FOV = 90.0    # horizontal FOV in degrees
    V_FOV = 73.74   # vertical FOV (derived from 4:3 aspect + 90° hfov)

    # Degrees per pixel
    DEG_PER_PX_H = H_FOV / SCREEN_W   # 0.1125
    DEG_PER_PX_V = V_FOV / SCREEN_H   # 0.1229

    # Turn speed ranges (degrees/second)
    YAW_SPEED_FINE = 80       # for small corrections (<10°)
    YAW_SPEED_MEDIUM = 200    # for medium turns (10-45°)
    YAW_SPEED_FAST = 400      # for large turns (>45°)
    PITCH_SPEED = 120

    # Minimum turn (below this, don't bother)
    MIN_TURN_DEG = 1.0
    # Minimum duration (pipe timing resolution)
    MIN_DURATION = 0.015

    def __init__(self, bridge: GameBridge, screen_w: int = 800, screen_h: int = 600):
        self.bridge = bridge
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.deg_per_px_h = self.H_FOV / screen_w
        self.deg_per_px_v = self.V_FOV / screen_h

    # ── Aim at screen position ────────────────────────────────────

    def aim_at_pixel(self, target_x: int, target_y: int):
        """
        Turn to aim the crosshair at a screen pixel position.
        (screen_w/2, screen_h/2) = crosshair center = no movement.
        """
        cx = self.screen_w // 2
        cy = self.screen_h // 2
        dx_px = target_x - cx
        dy_px = target_y - cy
        self.aim_offset(dx_px, dy_px)

    def aim_offset(self, dx_px: int, dy_px: int):
        """
        Turn by a pixel offset from crosshair center.
        Positive dx = target is RIGHT of crosshair.
        Positive dy = target is BELOW crosshair.
        """
        # Convert pixels to degrees
        yaw_deg = dx_px * self.deg_per_px_h
        pitch_deg = dy_px * self.deg_per_px_v

        # Apply horizontal turn
        if abs(yaw_deg) > self.MIN_TURN_DEG:
            self._turn_yaw(yaw_deg)

        # Apply vertical turn
        if abs(pitch_deg) > self.MIN_TURN_DEG:
            self._turn_pitch(pitch_deg)

    def aim_at_world(self, target_x: float, target_y: float,
                     player_x: float, player_y: float, player_yaw: float):
        """
        Turn to face a world-space position. Uses atan2 to compute
        desired yaw, then turns the difference via pipe.
        """
        desired_yaw = math.degrees(math.atan2(
            target_y - player_y, target_x - player_x))
        delta = self._yaw_diff(player_yaw, desired_yaw)

        if abs(delta) > self.MIN_TURN_DEG:
            self._turn_yaw(-delta)  # negative because +left is positive yaw

    def aim_at_world_corrected(self, target_x: float, target_y: float,
                                bridge=None, max_iterations: int = 4,
                                tolerance: float = 2.0) -> float:
        """
        Closed-loop aim at a world position.
        Turns, reads viewpos, corrects, repeats until within tolerance.
        Returns final yaw error in degrees.

        Requires bridge for viewpos queries.
        """
        import re
        b = bridge or self.bridge

        for i in range(max_iterations):
            raw = b.rcon("viewpos")
            m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)\s*:\s*(-?\d+)", raw)
            if not m:
                break
            px = float(m.group(1))
            py = float(m.group(2))
            current_yaw = float(m.group(4))

            desired = math.degrees(math.atan2(target_y - py, target_x - px))
            error = self._yaw_diff(current_yaw, desired)

            if abs(error) <= tolerance:
                log.debug("Aim converged: error=%.1f° after %d iterations", error, i + 1)
                return error

            # Use progressively finer speed for each correction
            speed = max(40, min(150, abs(error) * 5))
            duration = abs(error) / speed
            duration = max(self.MIN_DURATION, duration)

            direction = "left" if error > 0 else "right"
            opposite = "right" if error > 0 else "left"

            self.bridge.cmd(f"cl_yawspeed {int(speed)}")
            self.bridge.action_stop(opposite)
            self.bridge.action_start(direction)
            time.sleep(duration)
            self.bridge.action_stop(direction)
            time.sleep(0.05)  # settle time for viewpos to update

        # Final error check
        raw = b.rcon("viewpos")
        m = re.search(r"\((-?\d+)\s+(-?\d+)\s+(-?\d+)\)\s*:\s*(-?\d+)", raw)
        if m:
            px = float(m.group(1))
            py = float(m.group(2))
            current_yaw = float(m.group(4))
            desired = math.degrees(math.atan2(target_y - py, target_x - px))
            final_error = self._yaw_diff(current_yaw, desired)
            log.debug("Aim final error: %.1f° after %d iterations", final_error, max_iterations)
            return final_error
        return 999.0

    # ── Movement ──────────────────────────────────────────────────

    def forward(self, on: bool = True):
        self.bridge.move_forward(on)

    def back(self, on: bool = True):
        self.bridge.move_back(on)

    def strafe_left(self, on: bool = True):
        self.bridge.strafe_left(on)

    def strafe_right(self, on: bool = True):
        self.bridge.strafe_right(on)

    def jump(self):
        self.bridge.cmd("+moveup")
        self.bridge.cmd("-moveup")

    def crouch(self, on: bool = True):
        self.bridge.crouch(on)

    # ── Combat ────────────────────────────────────────────────────

    def fire(self, on: bool = True):
        self.bridge.fire(on)

    def select_weapon(self, slot: int):
        self.bridge.select_weapon(slot)

    def select_weapon_by_name(self, name: str):
        self.bridge.select_weapon_by_name(name)

    # ── View ──────────────────────────────────────────────────────

    def center_view(self):
        """Reset pitch to level."""
        self.bridge.cmd("centerview")

    def turn_degrees(self, degrees: float):
        """Turn left (positive) or right (negative) by exact degrees."""
        self._turn_yaw(degrees)

    def look_degrees(self, degrees: float):
        """Look up (negative) or down (positive) by exact degrees."""
        self._turn_pitch(degrees)

    # ── Stop all ──────────────────────────────────────────────────

    def stop_all(self):
        self.bridge.stop_movement()
        self.bridge.stop_firing()

    def release_all(self):
        self.bridge.release_all()

    # ── Smooth tracking (call every tick for lock-on) ─────────────

    def track_target(self, dx_px: int, dy_px: int, smoothing: float = 0.3):
        """
        Smooth aim adjustment toward a target offset.
        Call every tick with the current pixel offset from crosshair.
        smoothing: 0.0 = no movement, 1.0 = instant snap.
        """
        # Scale down the offset for smooth tracking
        adj_dx = int(dx_px * smoothing)
        adj_dy = int(dy_px * smoothing)

        # Only adjust if significant
        if abs(adj_dx) > 2 or abs(adj_dy) > 2:
            yaw_deg = adj_dx * self.deg_per_px_h
            pitch_deg = adj_dy * self.deg_per_px_v

            if abs(yaw_deg) > 0.5:
                self._turn_yaw_nonblocking(yaw_deg)
            if abs(pitch_deg) > 0.5:
                self._turn_pitch_nonblocking(pitch_deg)

    # ── Internal: calibrated pipe turns ───────────────────────────

    def _turn_yaw(self, degrees: float):
        """
        Turn horizontally by exact degrees using timed pipe commands.
        Positive = turn right, Negative = turn left.
        BLOCKING — sleeps for the turn duration.
        """
        if abs(degrees) < self.MIN_TURN_DEG:
            return

        # Pick speed based on magnitude
        abs_deg = abs(degrees)
        if abs_deg < 10:
            speed = self.YAW_SPEED_FINE
        elif abs_deg < 45:
            speed = self.YAW_SPEED_MEDIUM
        else:
            speed = self.YAW_SPEED_FAST

        duration = abs_deg / speed
        duration = max(self.MIN_DURATION, duration)

        direction = "right" if degrees > 0 else "left"
        opposite = "left" if degrees > 0 else "right"

        self.bridge.cmd(f"cl_yawspeed {speed}")
        self.bridge.action_stop(opposite)
        self.bridge.action_start(direction)
        time.sleep(duration)
        self.bridge.action_stop(direction)

    def _turn_pitch(self, degrees: float):
        """
        Turn vertically. Positive = look down, Negative = look up.
        BLOCKING.
        """
        if abs(degrees) < self.MIN_TURN_DEG:
            return

        speed = self.PITCH_SPEED
        duration = abs(degrees) / speed
        duration = max(self.MIN_DURATION, duration)

        direction = "lookdown" if degrees > 0 else "lookup"
        opposite = "lookup" if degrees > 0 else "lookdown"

        self.bridge.cmd(f"cl_pitchspeed {speed}")
        self.bridge.action_stop(opposite)
        self.bridge.action_start(direction)
        time.sleep(duration)
        self.bridge.action_stop(direction)

    def _turn_yaw_nonblocking(self, degrees: float):
        """
        Start a yaw turn without blocking. The turn will be stopped
        on the next call or by stop_all(). Good for per-tick tracking.
        """
        if abs(degrees) < 0.5:
            self.bridge.action_stop("left")
            self.bridge.action_stop("right")
            return

        # Speed proportional to offset — small offset = slow, large = fast
        speed = min(400, max(40, abs(degrees) * 15))

        direction = "right" if degrees > 0 else "left"
        opposite = "left" if degrees > 0 else "right"

        self.bridge.cmd(f"cl_yawspeed {int(speed)}")
        self.bridge.action_stop(opposite)
        self.bridge.action_start(direction)

    def _turn_pitch_nonblocking(self, degrees: float):
        """Start a pitch turn without blocking."""
        if abs(degrees) < 0.5:
            self.bridge.action_stop("lookup")
            self.bridge.action_stop("lookdown")
            return

        speed = min(200, max(30, abs(degrees) * 10))
        direction = "lookdown" if degrees > 0 else "lookup"
        opposite = "lookup" if degrees > 0 else "lookdown"

        self.bridge.cmd(f"cl_pitchspeed {int(speed)}")
        self.bridge.action_stop(opposite)
        self.bridge.action_start(direction)

    @staticmethod
    def _yaw_diff(current: float, target: float) -> float:
        """Signed yaw difference. Positive = turn left."""
        return (target - current + 180) % 360 - 180
