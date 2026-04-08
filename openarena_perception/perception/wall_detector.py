"""
perception.py — Visual perception: wall detection + object identification.

Wall detection (fast, every tick):
  - Analyze the center strip of the frame for wall proximity
  - Walls are dark, uniform texture filling most of the view
  - Open paths show depth variation, floor/ceiling perspective lines

Object detection (periodic, using CV):
  - Green orbs = health pickups
  - Yellow/gold items = armor
  - Weapon silhouettes
  - Red/colored player models = enemies

Orientation awareness:
  - Is the bot facing an open corridor or a wall?
  - Which direction has the most open space?
"""

from __future__ import annotations

import logging
from typing import Tuple, Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)


class Perception:
    """
    Analyzes game frames for wall proximity and object detection.
    Runs every tick for wall detection, less often for object ID.
    """

    # Wall detection: sample the center band of the frame
    # If the center is very dark and uniform → wall is close
    WALL_STRIP_TOP = 0.25     # fraction of frame height
    WALL_STRIP_BOTTOM = 0.65
    WALL_STRIP_LEFT = 0.3
    WALL_STRIP_RIGHT = 0.7

    def __init__(self):
        self._last_wall_score = 0.0
        self._last_open_direction = 0  # -1=left, 0=center, 1=right

    def detect_wall_ahead(self, frame: np.ndarray) -> Tuple[bool, float, int]:
        """
        Wall detection using edge density analysis.

        Open corridors have many perspective edges (floor/ceiling lines).
        Close walls have few edges (flat surface fills view).

        Returns:
          wall_ahead: True if a wall is very close ahead
          wall_score: 0.0 (open) to 1.0 (solid wall)
          open_direction: -1 (left more open), 0 (center), 1 (right)
        """
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        y1 = int(h * self.WALL_STRIP_TOP)
        y2 = int(h * self.WALL_STRIP_BOTTOM)

        # Edge density in center strip — key wall indicator
        center = gray[y1:y2, int(w*0.25):int(w*0.75)]
        edges = cv2.Canny(center, 50, 150)
        edge_density = float(edges.mean())

        # Open corridor: edge_density > 10 (perspective lines)
        # Close wall: edge_density < 6 (flat surface)
        wall_score = max(0.0, min(1.0, 1.0 - (edge_density - 3.0) / 10.0))

        wall_ahead = wall_score > 0.6

        # Which side is more open? Use edge density per third
        left_edges = cv2.Canny(gray[y1:y2, 0:w//3], 50, 150).mean()
        center_edges = edge_density
        right_edges = cv2.Canny(gray[y1:y2, 2*w//3:w], 50, 150).mean()

        if left_edges > right_edges + 2:
            open_direction = -1
        elif right_edges > left_edges + 2:
            open_direction = 1
        else:
            open_direction = 0

        self._last_wall_score = wall_score
        self._last_open_direction = open_direction
        return wall_ahead, wall_score, open_direction

    def detect_objects(self, frame: np.ndarray) -> dict:
        """
        Detect game objects in the frame using color analysis.

        Returns dict with:
          green_pickups: list of (cx, cy, area) for green health orbs
          gold_items: list of (cx, cy, area) for yellow/gold pickups
          red_objects: list of (cx, cy, area) for potential enemies
          open_left: bool - is the left side open
          open_right: bool - is the right side open
          open_center: bool - is the center open
        """
        h, w = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        result = {
            'green_pickups': [],
            'gold_items': [],
            'red_objects': [],
            'open_left': False,
            'open_right': False,
            'open_center': False,
        }

        # Exclude HUD region (bottom 15%)
        scan = hsv[:int(h * 0.85), :, :]

        # Green pickups (health orbs): H=40-80, S>100, V>100
        green_mask = cv2.inRange(scan, np.array([40, 100, 100]), np.array([80, 255, 255]))
        green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, np.ones((3, 3)))
        contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            if area > 50:
                M = cv2.moments(c)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    result['green_pickups'].append((cx, cy, area))

        # Gold/yellow items (armor, ammo): H=15-35, S>100, V>120
        gold_mask = cv2.inRange(scan, np.array([15, 100, 120]), np.array([35, 255, 255]))
        gold_mask = cv2.morphologyEx(gold_mask, cv2.MORPH_OPEN, np.ones((3, 3)))
        contours, _ = cv2.findContours(gold_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            if area > 50:
                M = cv2.moments(c)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    result['gold_items'].append((cx, cy, area))

        # Openness analysis: brightness in left/center/right strips
        gray = cv2.cvtColor(frame[:int(h*0.8), :, :], cv2.COLOR_BGR2GRAY)
        third = w // 3
        left_bright = gray[:, :third].mean()
        center_bright = gray[:, third:2*third].mean()
        right_bright = gray[:, 2*third:].mean()

        # Brighter = more depth/open space (darker = close wall)
        threshold = 15
        result['open_left'] = left_bright > threshold
        result['open_center'] = center_bright > threshold
        result['open_right'] = right_bright > threshold

        return result

    def detect_underwater(self, frame: np.ndarray) -> bool:
        """
        Detect if the player is underwater from the frame.
        Underwater has a strong blue/green tint across the entire frame.
        """
        h, w = frame.shape[:2]
        # Sample the top half (less HUD interference)
        sample = frame[:h//2, :, :]
        b, g, r = sample[:,:,0].mean(), sample[:,:,1].mean(), sample[:,:,2].mean()
        # Underwater: blue channel dominates, or green+blue >> red
        if b > r * 1.5 and b > 30:
            return True
        if (b + g) > r * 3 and (b + g) > 60:
            return True
        return False

    @property
    def wall_score(self) -> float:
        return self._last_wall_score

    @property
    def open_direction(self) -> int:
        return self._last_open_direction
