"""PID-based aim tracking for twitch FPS gameplay.

Provides smooth, responsive aim tracking with:
  - PID controller for both X and Y axes
  - Predictive lead based on enemy velocity estimation
  - Configurable sensitivity per weapon type
  - Deadzone to prevent jitter when on-target
  - Acceleration curve for large vs. small corrections

The controller outputs raw (dx, dy) mouse deltas each tick.

Moved from root-level aim_controller.py in Phase 4.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Deque, Optional, Tuple

if TYPE_CHECKING:
    from .humanize import AimHumanizer


@dataclass
class PIDState:
    """Internal PID state for one axis."""
    integral: float = 0.0
    last_error: float = 0.0
    last_time: float = 0.0

    def reset(self):
        self.integral = 0.0
        self.last_error = 0.0
        self.last_time = 0.0


@dataclass
class AimProfile:
    """
    Tuning profile for a weapon type.
    Fast weapons (lightning, plasma) need tight tracking.
    Slow weapons (rocket, grenade) need predictive lead.
    """
    name: str
    # PID gains
    kp: float = 0.45        # proportional -- main tracking responsiveness
    ki: float = 0.02        # integral -- corrects persistent offset
    kd: float = 0.12        # derivative -- dampens oscillation
    # Behavior
    deadzone_px: float = 8.0      # pixels -- don't move if within this
    max_delta: float = 80.0       # max mouse move per tick (prevents wild flicks)
    lead_factor: float = 0.0      # predictive lead multiplier (0=hitscan, >0=projectile)
    accel_exponent: float = 1.2   # acceleration curve (1.0=linear, >1=accelerated)
    integral_cap: float = 50.0    # anti-windup: max integral accumulation


# Pre-built profiles
PROFILES = {
    "hitscan": AimProfile(
        name="hitscan",
        kp=0.50, ki=0.03, kd=0.15,
        deadzone_px=6, max_delta=90, lead_factor=0.0,
    ),
    "lightning": AimProfile(
        name="lightning",
        kp=0.55, ki=0.04, kd=0.10,
        deadzone_px=5, max_delta=100, lead_factor=0.0,
    ),
    "rocket": AimProfile(
        name="rocket",
        kp=0.35, ki=0.02, kd=0.08,
        deadzone_px=12, max_delta=60, lead_factor=0.15,
    ),
    "railgun": AimProfile(
        name="railgun",
        kp=0.55, ki=0.01, kd=0.20,
        deadzone_px=4, max_delta=120, lead_factor=0.0,
    ),
    "plasma": AimProfile(
        name="plasma",
        kp=0.45, ki=0.03, kd=0.12,
        deadzone_px=6, max_delta=80, lead_factor=0.08,
    ),
    "default": AimProfile(
        name="default",
        kp=0.45, ki=0.02, kd=0.12,
        deadzone_px=8, max_delta=80, lead_factor=0.0,
    ),
}

# Map weapon display names -> profile keys
WEAPON_PROFILE_MAP = {
    "machinegun": "hitscan",
    "shotgun": "hitscan",
    "lightning gun": "lightning",
    "railgun": "railgun",
    "rocket launcher": "rocket",
    "grenade launcher": "rocket",
    "plasma gun": "plasma",
    "bfg10k": "plasma",
    "gauntlet": "default",
}


@dataclass
class TargetTrack:
    """Velocity-estimated target position for predictive aim."""
    cx: float
    cy: float
    vx: float = 0.0  # pixels/sec estimated velocity
    vy: float = 0.0
    timestamp: float = 0.0


class AimController:
    """
    PID aim controller that outputs mouse deltas to track a target.

    Usage each tick:
        dx, dy = aim.update(enemy_cx, enemy_cy, screen_cx, screen_cy)
        input.mouse_move(dx, dy)
    """

    def __init__(
        self,
        profile: Optional[AimProfile] = None,
        humanize: AimHumanizer | None = None,
    ):
        self.profile = profile or PROFILES["default"]
        self._pid_x = PIDState()
        self._pid_y = PIDState()

        # Target velocity estimation
        self._target_history: Deque[Tuple[float, float, float]] = deque(maxlen=8)
        self._target_vx = 0.0
        self._target_vy = 0.0

        # Stats
        self._on_target_ticks = 0
        self._total_ticks = 0

        # HUMN-01: Humanization support
        self._humanize = humanize
        self._recent_turn_rate: float = 0.0
        self._accuracy_window: deque = deque(maxlen=100)

    def set_weapon(self, weapon_name: Optional[str]):
        """Switch aim profile based on current weapon."""
        if weapon_name is None:
            key = "default"
        else:
            key = WEAPON_PROFILE_MAP.get(weapon_name.lower(), "default")
        new_profile = PROFILES[key]
        if new_profile.name != self.profile.name:
            self.profile = new_profile
            self._pid_x.reset()
            self._pid_y.reset()

    def update(
        self,
        target_cx: float,
        target_cy: float,
        screen_cx: float,
        screen_cy: float,
    ) -> Tuple[int, int]:
        """
        Compute mouse delta to move crosshair toward target.

        Returns (dx, dy) in pixels to pass to mouse_move().
        Returns (0, 0) if within deadzone (on target).
        """
        now = time.perf_counter()
        self._total_ticks += 1

        # Estimate target velocity
        self._update_velocity(target_cx, target_cy, now)

        # --- HUMN-01: Humanization noise injection (BEFORE PID) ---
        if self._humanize is not None:
            target_velocity = math.hypot(self._target_vx, self._target_vy)
            target_distance = math.hypot(target_cx - screen_cx, target_cy - screen_cy)
            noise_x, noise_y = self._humanize.sample(
                now,
                target_velocity=target_velocity,
                target_distance=target_distance,
                turn_rate=self._recent_turn_rate,
            )
            # Accuracy cap feedback: if on_target_ratio too high, boost noise
            if len(self._accuracy_window) >= 50:
                recent_ratio = sum(self._accuracy_window) / len(self._accuracy_window)
                if recent_ratio > self._humanize._cfg.max_accuracy:
                    noise_x *= 1.5
                    noise_y *= 1.5
            target_cx += noise_x
            target_cy += noise_y

        # Apply predictive lead
        lead_x = self._target_vx * self.profile.lead_factor
        lead_y = self._target_vy * self.profile.lead_factor
        aim_x = target_cx + lead_x
        aim_y = target_cy + lead_y

        # Error = distance from crosshair to aim point
        error_x = aim_x - screen_cx
        error_y = aim_y - screen_cy

        distance = math.hypot(error_x, error_y)

        # Deadzone -- we're on target
        if distance < self.profile.deadzone_px:
            self._on_target_ticks += 1
            if self._humanize is not None:
                self._accuracy_window.append(1)
            self._pid_x.last_error = 0
            self._pid_y.last_error = 0
            return (0, 0)

        # Track off-target for accuracy window
        if self._humanize is not None:
            self._accuracy_window.append(0)

        # PID for each axis
        dx = self._pid_step(self._pid_x, error_x, now)
        dy = self._pid_step(self._pid_y, error_y, now)

        # Acceleration curve -- bigger corrections for larger errors
        if self.profile.accel_exponent != 1.0:
            mag = math.hypot(dx, dy)
            if mag > 0:
                scale = (mag ** self.profile.accel_exponent) / mag
                dx *= scale
                dy *= scale

        # Clamp to max delta
        mag = math.hypot(dx, dy)
        if mag > self.profile.max_delta:
            scale = self.profile.max_delta / mag
            dx *= scale
            dy *= scale

        return (int(round(dx)), int(round(dy)))

    def reset(self):
        """Reset PID state (e.g., when losing target)."""
        self._pid_x.reset()
        self._pid_y.reset()
        self._target_history.clear()
        self._target_vx = 0.0
        self._target_vy = 0.0
        self._accuracy_window.clear()
        self._recent_turn_rate = 0.0

    @property
    def on_target_ratio(self) -> float:
        if self._total_ticks == 0:
            return 0.0
        return self._on_target_ticks / self._total_ticks

    # -- Internals ----------------------------------------------------------

    def _pid_step(self, state: PIDState, error: float, now: float) -> float:
        """One PID step for a single axis."""
        p = self.profile

        dt = now - state.last_time if state.last_time > 0 else 1.0 / 20.0
        dt = max(dt, 0.001)  # safety floor

        # Proportional
        p_term = p.kp * error

        # Integral (with anti-windup)
        state.integral += error * dt
        state.integral = max(-p.integral_cap, min(p.integral_cap, state.integral))
        i_term = p.ki * state.integral

        # Derivative
        d_term = p.kd * (error - state.last_error) / dt

        state.last_error = error
        state.last_time = now

        return p_term + i_term + d_term

    def _update_velocity(self, cx: float, cy: float, now: float):
        """Estimate target velocity from position history."""
        self._target_history.append((cx, cy, now))

        if len(self._target_history) >= 3:
            # Use last few samples for velocity estimate
            old = self._target_history[0]
            new = self._target_history[-1]
            dt = new[2] - old[2]
            if dt > 0.01:
                # Exponential smoothing on velocity
                raw_vx = (new[0] - old[0]) / dt
                raw_vy = (new[1] - old[1]) / dt
                alpha = 0.3
                self._target_vx = alpha * raw_vx + (1 - alpha) * self._target_vx
                self._target_vy = alpha * raw_vy + (1 - alpha) * self._target_vy

                # HUMN-01: Estimate turn rate (deg/s approximation)
                prev_vx = self._target_vx
                prev_vy = self._target_vy
                delta_vx = raw_vx - prev_vx
                delta_vy = raw_vy - prev_vy
                self._recent_turn_rate = math.hypot(delta_vx, delta_vy) / dt
