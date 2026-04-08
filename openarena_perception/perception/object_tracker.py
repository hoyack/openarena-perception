"""
object_tracker.py — Persistent object tracking with bounding box lock-on.

Tracks game objects (weapons, powerups, items, enemies) across frames using:
  1. Color segmentation (HSV) for initial detection
  2. Optical flow (Lucas-Kanade) for frame-to-frame tracking
  3. Template matching for re-acquisition after occlusion
  4. Kalman-like prediction for smooth bounding box updates

Each tracked object gets a persistent ID, bounding box, velocity estimate,
and screen-space position that can be used for crosshair lock-on.

Designed for 12-20 FPS on Raspberry Pi 5 (~5ms per frame).
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger(__name__)

Detection = Tuple[int, int, int, int, float]  # x1, y1, x2, y2, confidence


@dataclass
class TrackedObject:
    """A persistently tracked object in screen space."""
    track_id: int
    cx: int                         # center x
    cy: int                         # center y
    bbox: Tuple[int, int, int, int] # x1, y1, x2, y2
    vx: float = 0.0                 # velocity x (px/frame)
    vy: float = 0.0                 # velocity y (px/frame)
    width: int = 0
    height: int = 0
    confidence: float = 0.5
    frames_seen: int = 1
    frames_lost: int = 0
    label: str = ""                 # LLM-assigned label
    category: str = ""              # weapon/health/armor/enemy/powerup
    color_hist: Optional[np.ndarray] = None  # HSV histogram for re-ID
    template: Optional[np.ndarray] = None    # small crop for template match
    first_seen: float = 0.0
    last_seen: float = 0.0
    locked: bool = False            # is crosshair locked on this?


class ObjectTracker:
    """
    Multi-object tracker using detection + optical flow + color matching.

    Usage:
        tracker = ObjectTracker()
        for frame in frames:
            objects = tracker.update(frame)
            if objects:
                locked = tracker.lock_on(objects[0].track_id)
                dx, dy = tracker.get_aim_offset(frame.shape[1], frame.shape[0])
    """

    # Detection: HSV ranges for common game objects
    # Weapons/powerups in Q3 tend to be bright, saturated, distinct colors
    ITEM_HSV_RANGES = {
        "bright": ((0, 80, 120), (180, 255, 255)),     # any bright saturated object
        "gold":   ((15, 100, 120), (35, 255, 255)),     # armor, ammo
        "green":  ((40, 80, 100), (85, 255, 255)),      # health
        "blue":   ((90, 80, 100), (130, 255, 255)),     # quad, plasma
        "red":    ((0, 120, 100), (10, 255, 255)),      # enemy (low hue)
        "red2":   ((165, 120, 100), (179, 255, 255)),   # enemy (high hue)
    }

    MIN_AREA = 150
    MAX_AREA = 50000
    SCAN_TOP = 0.08
    SCAN_BOTTOM = 0.82

    MATCH_RADIUS = 100       # px for track matching
    LOST_THRESHOLD = 15      # frames before dropping a track
    SMOOTH_ALPHA = 0.4       # exponential smoothing for bbox

    # Optical flow params
    LK_PARAMS = dict(
        winSize=(15, 15), maxLevel=2,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03),
    )

    def __init__(self):
        self._tracks: Dict[int, TrackedObject] = {}
        self._next_id = 1
        self._prev_gray: Optional[np.ndarray] = None
        self._prev_points: Dict[int, np.ndarray] = {}  # track_id -> feature points
        self._locked_id: Optional[int] = None
        self._frame_count = 0

    def update(self, frame: np.ndarray) -> List[TrackedObject]:
        """
        Process a frame: detect objects, match to existing tracks, update.
        Returns list of active tracked objects sorted by confidence.
        """
        self._frame_count += 1
        now = time.time()
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Step 1: Track existing objects using optical flow
        self._track_existing(gray)

        # Step 2: Detect new objects via color segmentation
        detections = self._detect_objects(frame)

        # Step 3: Match detections to tracks
        self._match_and_update(detections, frame, now)

        # Step 4: Age lost tracks
        self._age_tracks()

        self._prev_gray = gray

        # Return active tracks sorted by confidence
        active = [t for t in self._tracks.values() if t.frames_lost == 0]
        active.sort(key=lambda t: t.confidence, reverse=True)
        return active

    def lock_on(self, track_id: int) -> bool:
        """Lock crosshair onto a specific tracked object."""
        if track_id in self._tracks:
            # Unlock previous
            if self._locked_id and self._locked_id in self._tracks:
                self._tracks[self._locked_id].locked = False
            self._locked_id = track_id
            self._tracks[track_id].locked = True
            return True
        return False

    def unlock(self):
        """Release crosshair lock."""
        if self._locked_id and self._locked_id in self._tracks:
            self._tracks[self._locked_id].locked = False
        self._locked_id = None

    def get_locked_target(self) -> Optional[TrackedObject]:
        """Get the currently locked target, or None."""
        if self._locked_id and self._locked_id in self._tracks:
            t = self._tracks[self._locked_id]
            if t.frames_lost < 5:
                return t
        return None

    def get_aim_offset(self, screen_w: int, screen_h: int) -> Tuple[int, int]:
        """
        Get pixel offset from screen center to locked target.
        Returns (dx, dy) — positive = target is right/below crosshair.
        """
        target = self.get_locked_target()
        if not target:
            return (0, 0)

        # Predict position using velocity (lead the target)
        pred_cx = target.cx + target.vx * 0.5
        pred_cy = target.cy + target.vy * 0.5

        screen_cx = screen_w // 2
        screen_cy = screen_h // 2
        return (int(pred_cx - screen_cx), int(pred_cy - screen_cy))

    def find_nearest(self, screen_cx: int, screen_cy: int,
                     category: str = "") -> Optional[TrackedObject]:
        """Find the tracked object nearest to a screen position."""
        best = None
        best_dist = float('inf')
        for t in self._tracks.values():
            if t.frames_lost > 3:
                continue
            if category and t.category != category:
                continue
            d = math.hypot(t.cx - screen_cx, t.cy - screen_cy)
            if d < best_dist:
                best_dist = d
                best = t
        return best

    # ── Internal ──────────────────────────────────────────────────

    def _detect_objects(self, frame: np.ndarray) -> List[Detection]:
        """Detect bright/colored objects via HSV segmentation."""
        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        y_top = int(h * self.SCAN_TOP)
        y_bot = int(h * self.SCAN_BOTTOM)
        scan = hsv[y_top:y_bot, :, :]

        # Combined mask of all interesting colors
        mask = np.zeros(scan.shape[:2], dtype=np.uint8)
        for name, (lo, hi) in self.ITEM_HSV_RANGES.items():
            if name in ("red", "red2"):
                continue  # skip enemy colors for item detection
            m = cv2.inRange(scan, np.array(lo), np.array(hi))
            mask = cv2.bitwise_or(mask, m)

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.MIN_AREA or area > self.MAX_AREA:
                continue

            x, y, bw, bh = cv2.boundingRect(cnt)
            y += y_top  # offset back to full frame coords

            # Confidence from fill ratio and brightness
            roi = frame[y:y+bh, x:x+bw]
            brightness = roi.mean() / 255.0
            fill = area / max(bw * bh, 1)
            conf = min(1.0, fill * brightness * 2.0)

            if conf > 0.15:
                detections.append((x, y, x + bw, y + bh, conf))

        return detections

    def _track_existing(self, gray: np.ndarray):
        """Track existing objects using sparse optical flow."""
        if self._prev_gray is None or not self._prev_points:
            return

        for tid, pts in list(self._prev_points.items()):
            if tid not in self._tracks or len(pts) == 0:
                continue

            new_pts, status, _ = cv2.calcOpticalFlowPyrLK(
                self._prev_gray, gray, pts, None, **self.LK_PARAMS)

            if new_pts is None:
                continue

            good = status.flatten() == 1
            if good.sum() < 2:
                continue

            old_good = pts[good].reshape(-1, 2)
            new_good = new_pts[good].reshape(-1, 2)

            # Update track position from flow
            track = self._tracks[tid]
            flow = new_good - old_good
            median_dx = float(np.median(flow[:, 0]))
            median_dy = float(np.median(flow[:, 1]))

            # Smooth update
            a = self.SMOOTH_ALPHA
            new_cx = int(track.cx + median_dx)
            new_cy = int(track.cy + median_dy)
            track.vx = track.vx * (1 - a) + median_dx * a
            track.vy = track.vy * (1 - a) + median_dy * a

            x1, y1, x2, y2 = track.bbox
            track.bbox = (x1 + int(median_dx), y1 + int(median_dy),
                          x2 + int(median_dx), y2 + int(median_dy))
            track.cx = new_cx
            track.cy = new_cy

            self._prev_points[tid] = new_good.reshape(-1, 1, 2).astype(np.float32)

    def _match_and_update(self, detections: List[Detection],
                          frame: np.ndarray, now: float):
        """Match new detections to existing tracks."""
        matched_tracks = set()
        matched_dets = set()

        # Match by proximity
        for di, (x1, y1, x2, y2, conf) in enumerate(detections):
            dcx, dcy = (x1 + x2) // 2, (y1 + y2) // 2
            best_tid = None
            best_dist = float('inf')

            for tid, track in self._tracks.items():
                if tid in matched_tracks:
                    continue
                d = math.hypot(dcx - track.cx, dcy - track.cy)
                if d < self.MATCH_RADIUS and d < best_dist:
                    best_dist = d
                    best_tid = tid

            if best_tid is not None:
                # Update existing track
                track = self._tracks[best_tid]
                a = self.SMOOTH_ALPHA
                track.cx = int(track.cx * (1-a) + dcx * a)
                track.cy = int(track.cy * (1-a) + dcy * a)
                track.bbox = (x1, y1, x2, y2)
                track.width = x2 - x1
                track.height = y2 - y1
                track.confidence = max(track.confidence, conf)
                track.frames_seen += 1
                track.frames_lost = 0
                track.last_seen = now
                matched_tracks.add(best_tid)
                matched_dets.add(di)

                # Update feature points for optical flow
                self._update_features(best_tid, frame, (x1, y1, x2, y2))

                # Update color histogram
                self._update_histogram(track, frame, (x1, y1, x2, y2))
            # else: handled below

        # Create new tracks for unmatched detections
        for di, (x1, y1, x2, y2, conf) in enumerate(detections):
            if di in matched_dets:
                continue
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            track = TrackedObject(
                track_id=self._next_id,
                cx=cx, cy=cy, bbox=(x1, y1, x2, y2),
                width=x2-x1, height=y2-y1,
                confidence=conf,
                first_seen=now, last_seen=now,
            )
            self._tracks[self._next_id] = track
            self._update_features(self._next_id, frame, (x1, y1, x2, y2))
            self._update_histogram(track, frame, (x1, y1, x2, y2))
            self._next_id += 1

    def _update_features(self, tid: int, frame: np.ndarray,
                         bbox: Tuple[int, int, int, int]):
        """Extract good features inside the bbox for optical flow."""
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        gray = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        pts = cv2.goodFeaturesToTrack(gray, maxCorners=20, qualityLevel=0.1,
                                       minDistance=5, blockSize=5)
        if pts is not None and len(pts) > 0:
            pts[:, :, 0] += x1
            pts[:, :, 1] += y1
            self._prev_points[tid] = pts.astype(np.float32)

    def _update_histogram(self, track: TrackedObject, frame: np.ndarray,
                          bbox: Tuple[int, int, int, int]):
        """Update the color histogram for re-identification."""
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 - x1 < 5 or y2 - y1 < 5:
            return

        roi = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [18, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        track.color_hist = hist

        # Save template for re-acquisition
        track.template = cv2.resize(roi, (32, 32))

    def _age_tracks(self):
        """Increment lost counter, remove stale tracks."""
        to_remove = []
        for tid, track in self._tracks.items():
            # Only age tracks that weren't matched this frame
            if track.last_seen < time.time() - 0.2:
                track.frames_lost += 1
            if track.frames_lost > self.LOST_THRESHOLD:
                to_remove.append(tid)
                if tid in self._prev_points:
                    del self._prev_points[tid]
        for tid in to_remove:
            if tid == self._locked_id:
                self._locked_id = None
            del self._tracks[tid]

    def reset(self):
        """Reset all tracking state."""
        self._tracks.clear()
        self._prev_points.clear()
        self._prev_gray = None
        self._locked_id = None

    @property
    def active_count(self) -> int:
        return sum(1 for t in self._tracks.values() if t.frames_lost == 0)

    @property
    def locked_id(self) -> Optional[int]:
        return self._locked_id
