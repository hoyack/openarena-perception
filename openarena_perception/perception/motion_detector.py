"""
motion_detector.py — Fast motion-based enemy detection.

Instead of trying to classify game characters with ML (which fails on
stylized Q3 models), detect enemies by what MOVES in the frame.

Algorithm:
  1. Keep a rolling background model (average of recent frames)
  2. Compute absolute difference between current frame and background
  3. Threshold to find moving regions
  4. Filter by size (player-sized blobs, not tiny particles)
  5. Filter by position (exclude HUD at bottom, scoreboard at top)
  6. Return bounding boxes of moving objects

This works because: walls don't move, Sarge does.
Runs at full frame rate with zero ML overhead.
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional
from collections import deque

Detection = Tuple[int, int, int, int, float]  # x1, y1, x2, y2, confidence


class MotionDetector:
    """
    Detects moving objects (enemies) via frame differencing + velocity tracking.
    No ML — pure OpenCV, runs in <2ms per frame.

    Tracks detections across frames to distinguish real enemies (moving)
    from static false positives (bobbing items, lighting).
    """

    DIFF_THRESHOLD = 40       # high threshold reduces false positives from turning
    MIN_AREA = 800            # only player-sized or larger blobs
    MAX_AREA = 25000
    MORPH_KERNEL = (7, 7)
    BG_HISTORY = 10
    SCAN_TOP = 0.10           # ignore top 10% (scores)
    SCAN_BOTTOM = 0.80        # ignore bottom 20% (HUD)
    STATIC_FRAMES = 8         # if detection stays same position this long, ignore it
    VELOCITY_MIN = 3.0        # minimum pixels/frame to count as "moving"

    def __init__(self):
        self._bg_frames: deque = deque(maxlen=self.BG_HISTORY)
        self._bg_model: Optional[np.ndarray] = None
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, self.MORPH_KERNEL)
        self._frame_count = 0
        # Tracking: list of (cx, cy, frames_static)
        self._tracked: List[Tuple[int, int, int]] = []
        self._last_detections: List[Detection] = []

    def update_background(self, frame: np.ndarray):
        """Add a frame to the background model. Call when NOT in combat."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        self._bg_frames.append(gray.astype(np.float32))
        if len(self._bg_frames) >= 3:
            self._bg_model = np.mean(list(self._bg_frames), axis=0).astype(np.uint8)

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Detect moving objects using consecutive frame differencing.
        Works even when the bot is moving — detects objects that move
        DIFFERENTLY from the background (enemies move independently).
        """
        self._frame_count += 1

        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        # Two-frame skip differencing: compare with frame N-2
        # This reduces noise from gradual camera movement
        self._bg_frames.append(gray)
        if len(self._bg_frames) < 3:
            return []

        prev = self._bg_frames[-3]  # 2 frames ago
        diff = cv2.absdiff(gray, prev)

        # Threshold
        _, thresh = cv2.threshold(diff, self.DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)

        # Morphological cleanup
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, self._kernel)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, self._kernel)

        # Mask out HUD and score regions
        y_top = int(h * self.SCAN_TOP)
        y_bottom = int(h * self.SCAN_BOTTOM)
        thresh[:y_top, :] = 0
        thresh[y_bottom:, :] = 0

        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.MIN_AREA or area > self.MAX_AREA:
                continue

            x, y, bw, bh = cv2.boundingRect(cnt)

            # Aspect ratio filter: players are taller than wide (roughly 1:2 to 1:3)
            aspect = bh / max(bw, 1)
            if aspect < 0.5 or aspect > 5.0:
                continue

            # Confidence based on how much motion is in the bounding box
            roi_mask = thresh[y:y+bh, x:x+bw]
            fill_ratio = cv2.countNonZero(roi_mask) / max(bw * bh, 1)
            confidence = min(1.0, fill_ratio * 2.0)

            if confidence > 0.2:
                detections.append((x, y, x + bw, y + bh, confidence))

        # Sort by area (largest = closest)
        detections.sort(key=lambda d: (d[2]-d[0]) * (d[3]-d[1]), reverse=True)

        # Filter static false positives using tracking
        moving_detections = self._filter_static(detections)

        # No background update needed — using frame-to-frame diff

        self._last_detections = moving_detections
        return moving_detections

    def _filter_static(self, detections: List[Detection]) -> List[Detection]:
        """Remove detections that stay at the same position across frames."""
        new_tracked = []
        moving = []

        for x1, y1, x2, y2, conf in detections:
            cx, cy = (x1+x2)//2, (y1+y2)//2

            # Find closest existing track
            best_dist = float('inf')
            best_idx = -1
            for i, (tx, ty, static_count) in enumerate(self._tracked):
                d = ((cx-tx)**2 + (cy-ty)**2) ** 0.5
                if d < best_dist:
                    best_dist = d
                    best_idx = i

            if best_dist < 30:
                # Same position as before — increment static counter
                _, _, old_count = self._tracked[best_idx]
                if best_dist < self.VELOCITY_MIN:
                    new_count = old_count + 1
                else:
                    new_count = 0  # it moved!
                new_tracked.append((cx, cy, new_count))

                # Only include if it hasn't been static too long
                if new_count < self.STATIC_FRAMES:
                    moving.append((x1, y1, x2, y2, conf))
            else:
                # New detection — include it
                new_tracked.append((cx, cy, 0))
                moving.append((x1, y1, x2, y2, conf))

        self._tracked = new_tracked[-20:]  # keep max 20 tracks
        return moving

    def reset_background(self):
        """Reset background model (call after respawn or teleport)."""
        self._bg_frames.clear()
        self._bg_model = None
