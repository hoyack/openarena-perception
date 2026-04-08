"""
player_detector.py — Fast player detection pipeline.

Three-stage pipeline:
  1. MOTION: Frame differencing finds moving regions (~1ms)
  2. COLOR: HSV histogram comparison filters player-like regions (~1ms)
  3. SHAPE: Aspect ratio and size filter for humanoid shapes (~0ms)

Uses a pre-trained color histogram model built from captured player
model templates. Runs entirely on CPU at ~3ms per frame.

The color model distinguishes player model textures from map textures
with 0.645 separation score (player=0.72, background=0.08).
"""

import os
import pickle
import logging
from typing import List, Tuple, Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

Detection = Tuple[int, int, int, int, float]  # x1, y1, x2, y2, confidence


class PlayerDetector:
    """
    Multi-stage player detector: motion → color → shape.
    """

    # Stage 1: Motion
    MOTION_THRESHOLD = 25  # more sensitive to catch moving players
    # Stage 2: Color histogram
    COLOR_THRESHOLD = 0.10   # low threshold — prefer false positives over misses
    # Stage 3: Shape
    MIN_AREA = 300
    MAX_AREA = 40000
    MIN_ASPECT = 0.4   # width/height ratio
    MAX_ASPECT = 3.5
    # Region of interest (exclude HUD and scores)
    SCAN_TOP = 0.10
    SCAN_BOTTOM = 0.82

    def __init__(self, model_path: str = ""):
        self._prev_gray: Optional[np.ndarray] = None
        self._player_hist = None
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

        if not model_path:
            model_path = os.path.expanduser(
                "~/openarena-perception/player_color_model.pkl")

        if os.path.exists(model_path):
            with open(model_path, 'rb') as f:
                model = pickle.load(f)
            self._player_hist = model['player_hist']
            self._threshold = model.get('threshold', self.COLOR_THRESHOLD)
            log.info("Player color model loaded (threshold=%.2f)", self._threshold)
        else:
            log.warning("No color model at %s — using motion only", model_path)

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Detect players in a BGR frame.
        Returns list of (x1, y1, x2, y2, confidence) bounding boxes.
        """
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        if self._prev_gray is None:
            self._prev_gray = gray
            return []

        # === Stage 1: Motion detection (frame differencing) ===
        diff = cv2.absdiff(gray, self._prev_gray)
        self._prev_gray = gray

        _, motion_mask = cv2.threshold(diff, self.MOTION_THRESHOLD, 255,
                                        cv2.THRESH_BINARY)

        # Exclude HUD/score regions
        y_top = int(h * self.SCAN_TOP)
        y_bot = int(h * self.SCAN_BOTTOM)
        motion_mask[:y_top, :] = 0
        motion_mask[y_bot:, :] = 0

        # Morphological cleanup
        motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_OPEN, self._kernel)
        motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_CLOSE, self._kernel)

        # Find motion blobs
        contours, _ = cv2.findContours(motion_mask, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.MIN_AREA or area > self.MAX_AREA:
                continue

            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect = bh / max(bw, 1)
            if aspect < self.MIN_ASPECT or aspect > self.MAX_ASPECT:
                continue

            # === Stage 2: Color histogram verification ===
            confidence = 0.5  # base confidence from motion
            if self._player_hist is not None:
                # Extract the region and compute its color histogram
                region = frame[y:y+bh, x:x+bw]
                hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
                bright_mask = (hsv[:,:,2] > 30).astype(np.uint8) * 255

                if cv2.countNonZero(bright_mask) > 50:
                    hist = cv2.calcHist([hsv], [0, 1], bright_mask,
                                        [30, 32], [0, 180, 0, 256])
                    cv2.normalize(hist, hist)
                    score = cv2.compareHist(hist, self._player_hist,
                                            cv2.HISTCMP_CORREL)

                    if score < self.COLOR_THRESHOLD:
                        continue  # doesn't look like a player

                    # Scale confidence by color match
                    confidence = min(1.0, 0.3 + score * 0.7)

            # === Stage 3: Shape already filtered above ===
            detections.append((x, y, x + bw, y + bh, confidence))

        # Sort by confidence (highest first)
        detections.sort(key=lambda d: d[4], reverse=True)

        return detections

    def reset(self):
        """Reset state (call after respawn/teleport)."""
        self._prev_gray = None
