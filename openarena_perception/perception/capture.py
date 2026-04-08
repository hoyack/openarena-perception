"""
capture.py — Fast screen capture for Raspberry Pi X11 (mss-based).

Three capture modes:
  1. FULLSCREEN  — captures the entire display (fastest)
  2. WINDOW      — finds the OA window by title and captures only it
  3. REGION      — captures a fixed pixel region (for multi-monitor setups)

On Pi with X11, mss is the fastest Python screen capture library
(pure C under the hood, no subprocess overhead like scrot/import).
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Tuple

import numpy as np

try:
    import mss
    import mss.tools
except ImportError:
    raise ImportError("Install mss: pip install mss")

try:
    import cv2
except ImportError:
    raise ImportError("Install opencv: pip install opencv-python-headless")

log = logging.getLogger(__name__)


class CaptureMode(Enum):
    FULLSCREEN = auto()
    WINDOW     = auto()
    REGION     = auto()


@dataclass
class CaptureRegion:
    """Explicit pixel region for REGION mode."""
    left:   int
    top:    int
    width:  int
    height: int

    def as_mss_dict(self) -> dict:
        return {"left": self.left, "top": self.top,
                "width": self.width, "height": self.height}


class ScreenCapture:
    """
    Wraps mss for fast, repeated screen capture.
    Re-uses a single mss.mss() instance across frames for performance.
    """

    def __init__(
        self,
        mode: CaptureMode = CaptureMode.FULLSCREEN,
        monitor_index: int = 1,          # 1 = primary monitor in mss
        region: Optional[CaptureRegion] = None,
        window_title: str = "ioquake3",
        target_w: Optional[int] = None,  # resize output to this width
        target_h: Optional[int] = None,
    ):
        self.mode          = mode
        self.monitor_index = monitor_index
        self.region        = region
        self.window_title  = window_title
        self.target_w      = target_w
        self.target_h      = target_h

        self._sct: Optional[mss.mss] = None
        self._monitor: Optional[dict] = None
        self._frame_count = 0
        self._last_capture_time = 0.0

    def open(self) -> "ScreenCapture":
        """Initialize the mss context. Call once before the loop."""
        self._sct = mss.mss()

        if self.mode == CaptureMode.FULLSCREEN:
            self._monitor = self._sct.monitors[self.monitor_index]
            log.info("Capture: FULLSCREEN %dx%d",
                     self._monitor["width"], self._monitor["height"])

        elif self.mode == CaptureMode.REGION:
            if self.region is None:
                raise ValueError("CaptureMode.REGION requires a CaptureRegion")
            self._monitor = self.region.as_mss_dict()
            log.info("Capture: REGION %dx%d @ (%d,%d)",
                     self.region.width, self.region.height,
                     self.region.left, self.region.top)

        elif self.mode == CaptureMode.WINDOW:
            self._monitor = self._find_window_region()

        return self

    def close(self):
        if self._sct:
            self._sct.close()
            self._sct = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *_):
        self.close()

    # ── Core capture ────────────────────────────────────────────────────────

    def grab(self) -> np.ndarray:
        """
        Capture one frame. Returns BGR numpy array (OpenCV convention).
        This is the hot path — kept allocation-lean.
        """
        t0 = time.perf_counter()
        raw = self._sct.grab(self._monitor)
        # mss returns BGRA; drop alpha channel → BGR
        frame = np.array(raw)[:, :, :3]

        if self.target_w and self.target_h:
            frame = cv2.resize(frame, (self.target_w, self.target_h),
                               interpolation=cv2.INTER_LINEAR)

        self._frame_count += 1
        self._last_capture_time = time.perf_counter() - t0
        return frame

    def grab_roi(self, roi: Tuple[int, int, int, int]) -> np.ndarray:
        """
        Grab a sub-region (x, y, w, h) from the current monitor.
        Faster than grab() when you only need a small slice.
        """
        x, y, w, h = roi
        mon = {
            "left":   self._monitor["left"] + x,
            "top":    self._monitor["top"]  + y,
            "width":  w,
            "height": h,
        }
        raw = self._sct.grab(mon)
        return np.array(raw)[:, :, :3]

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def frame_count(self) -> int:
        return self._frame_count

    @property
    def last_capture_ms(self) -> float:
        return self._last_capture_time * 1000

    @property
    def screen_size(self) -> Tuple[int, int]:
        if self._monitor is None:
            raise RuntimeError("Call open() first")
        return self._monitor["width"], self._monitor["height"]

    # ── Window detection (X11 via xdotool) ─────────────────────────────────

    def _find_window_region(self) -> dict:
        """
        Use xdotool to locate the OA window geometry on X11.
        Falls back to fullscreen if xdotool is unavailable.
        """
        import subprocess
        import os
        try:
            env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}

            # Find window ID by name
            wid_result = subprocess.run(
                ["xdotool", "search", "--name", self.window_title],
                capture_output=True, text=True, timeout=5, env=env,
            )
            if wid_result.returncode != 0 or not wid_result.stdout.strip():
                raise RuntimeError(f"Window '{self.window_title}' not found")

            wid = wid_result.stdout.strip().split("\n")[0]

            # Get geometry
            geo_result = subprocess.run(
                ["xdotool", "getwindowgeometry", wid],
                capture_output=True, text=True, timeout=5, env=env,
            )
            # Parse "Position: 564,300 (screen: 0)\n  Geometry: 800x600"
            import re
            lines = geo_result.stdout.strip()
            pos_match = re.search(r"Position:\s*(\d+),(\d+)", lines)
            size_match = re.search(r"Geometry:\s*(\d+)x(\d+)", lines)
            if not pos_match or not size_match:
                raise RuntimeError(f"Could not parse geometry: {lines}")
            x, y = int(pos_match.group(1)), int(pos_match.group(2))
            w, h = int(size_match.group(1)), int(size_match.group(2))

            log.info("Capture: WINDOW '%s' at (%d,%d) %dx%d",
                     self.window_title, x, y, w, h)
            return {"left": x, "top": y, "width": w, "height": h}

        except Exception as exc:
            log.warning("xdotool window detection failed (%s); "
                        "falling back to primary monitor.", exc)
            return self._sct.monitors[self.monitor_index]


# ── Convenience factory ──────────────────────────────────────────────────────

def make_capture(
    mode: str = "fullscreen",
    region: Optional[CaptureRegion] = None,
    window_title: str = "ioquake3",
    monitor_index: int = 1,
    target_w: int = 0,
    target_h: int = 0,
) -> ScreenCapture:
    """
    Factory helper. mode ∈ {"fullscreen", "window", "region"}.

    Example:
        cap = make_capture("window", window_title="OpenArena")
        with cap:
            frame = cap.grab()
    """
    mode_map = {
        "fullscreen": CaptureMode.FULLSCREEN,
        "window":     CaptureMode.WINDOW,
        "region":     CaptureMode.REGION,
    }
    return ScreenCapture(
        mode=mode_map[mode.lower()],
        monitor_index=monitor_index,
        region=region,
        window_title=window_title,
        target_w=target_w or None,
        target_h=target_h or None,
    )
