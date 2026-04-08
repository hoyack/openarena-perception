"""
world_parser.py — Enemy and world-state perception via HSV color thresholding.

Core strategy:
  Force enemy model skins to a single distinct color in OpenArena
  (via /cg_enemyColors) then use OpenCV HSV thresholding + contour
  analysis to locate, size, and score each enemy silhouette.

This is far more reliable and Pi-friendly than ML-based detection because:
  - No model weights / inference overhead
  - Deterministic and debuggable
  - Runs at 20-30 FPS on Pi 4

Setup in OpenArena (add to autoexec.cfg):
  seta cg_enemyColors "ff0000"   // force enemy skins red
  seta cg_forceModel "1"         // ensure color applies to all models
"""

from __future__ import annotations

import logging
import math
from typing import List, Optional, Tuple

import cv2
import numpy as np

from openarena_perception.config import PerceptionConfig, HSV_RANGES
from openarena_perception.game_state import BoundingBox, EnemyContact

log = logging.getLogger(__name__)


class WorldParser:
    """
    Detects enemy contacts in a BGR frame using HSV color segmentation.

    Lifetime: create once, call parse_enemies() on each frame.
    """

    def __init__(self, cfg: PerceptionConfig):
        self.cfg = cfg
        self._morph_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, cfg.enemy_morph_kernel
        )

    # ── Public interface ────────────────────────────────────────────────────

    def parse_enemies(self, frame: np.ndarray) -> List[EnemyContact]:
        """
        Find all enemy contacts in the frame.
        Returns a list ordered by pixel_mass descending (largest = nearest).
        """
        scan_roi = self.cfg.rois["enemy_scan"]
        x, y, w, h = scan_roi
        crop = frame[y:y+h, x:x+w]

        mask = self._build_enemy_mask(crop)
        contours = self._find_contours(mask)
        contacts = self._contours_to_contacts(contours, offset_x=x, offset_y=y,
                                               scan_w=w, scan_h=h)

        log.debug("WorldParser: %d enemy contacts", len(contacts))
        return sorted(contacts, key=lambda e: e.pixel_mass, reverse=True)

    def parse_crosshair_state(
        self,
        frame: np.ndarray,
        enemies: List[EnemyContact],
    ) -> bool:
        """Returns True if any enemy bounding box overlaps the crosshair."""
        cx, cy = self.cfg.crosshair_px
        return any(e.bbox.contains(cx, cy) for e in enemies)

    # ── Mask construction ────────────────────────────────────────────────────

    def _build_enemy_mask(self, crop_bgr: np.ndarray) -> np.ndarray:
        """
        Convert crop to HSV and apply the configured color range(s).
        Returns a binary mask (255=enemy, 0=background).
        """
        hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
        mode = self.cfg.enemy_color_mode

        if mode == "red":
            # Red wraps around H=0/180 in OpenCV HSV — need two ranges
            lo_range = HSV_RANGES["enemy_red_lo"]
            hi_range = HSV_RANGES["enemy_red_hi"]
            mask_lo = cv2.inRange(hsv,
                                  np.array(lo_range[0], np.uint8),
                                  np.array(lo_range[1], np.uint8))
            mask_hi = cv2.inRange(hsv,
                                  np.array(hi_range[0], np.uint8),
                                  np.array(hi_range[1], np.uint8))
            mask = cv2.bitwise_or(mask_lo, mask_hi)

        elif mode in ("green", "cyan"):
            key = f"enemy_{mode}"
            r = HSV_RANGES[key]
            mask = cv2.inRange(hsv,
                               np.array(r[0], np.uint8),
                               np.array(r[1], np.uint8))
        else:
            raise ValueError(f"Unknown enemy_color_mode: {mode!r}")

        # Morphological cleaning — close small holes, remove pepper noise
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._morph_kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  self._morph_kernel)
        return mask

    # ── Contour analysis ────────────────────────────────────────────────────

    def _find_contours(self, mask: np.ndarray) -> List:
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        return list(contours)

    def _contours_to_contacts(
        self,
        contours: List,
        offset_x: int,
        offset_y: int,
        scan_w: int,
        scan_h: int,
    ) -> List[EnemyContact]:
        """
        Convert raw contours to EnemyContact objects, filtering by area bounds
        and computing screen-space metadata.
        """
        min_area  = self.cfg.enemy_min_area
        max_area  = int(scan_w * scan_h * self.cfg.enemy_max_area_fraction)
        cx_screen = self.cfg.crosshair_px[0]
        cy_screen = self.cfg.crosshair_px[1]

        contacts: List[EnemyContact] = []

        for cnt in contours:
            area = int(cv2.contourArea(cnt))
            if area < min_area or area > max_area:
                continue

            bx, by, bw, bh = cv2.boundingRect(cnt)

            # Translate to screen-space coordinates
            sx = bx + offset_x
            sy = by + offset_y

            bbox = BoundingBox(sx, sy, bw, bh)

            # Confidence: ratio of contour area to bounding box area
            # (a tight silhouette of a player model is ~0.5–0.7)
            bbox_area  = bw * bh if bw * bh > 0 else 1
            confidence = min(1.0, area / bbox_area)

            # Angle from crosshair to enemy center (0°=up, CW positive)
            dx = bbox.cx - cx_screen
            dy = bbox.cy - cy_screen
            angle_deg = math.degrees(math.atan2(dx, -dy))   # nav convention

            # Distance estimate from bounding box area
            if area > 8000:
                dist = "near"
            elif area > 2000:
                dist = "mid"
            else:
                dist = "far"

            contacts.append(EnemyContact(
                bbox=bbox,
                confidence=confidence,
                pixel_mass=area,
                screen_angle=angle_deg,
                distance_estimate=dist,
            ))

        return contacts


# ─── Diagnostic helpers ────────────────────────────────────────────────────────

def draw_enemies(
    frame: np.ndarray,
    enemies: List[EnemyContact],
    color: Tuple[int, int, int] = (0, 0, 255),
    crosshair_color: Tuple[int, int, int] = (0, 255, 0),
) -> np.ndarray:
    """Draw enemy bounding boxes and crosshair onto a copy of the frame."""
    vis = frame.copy()
    h, w = vis.shape[:2]

    # Crosshair
    cx, cy = w // 2, h // 2
    cv2.line(vis, (cx - 15, cy), (cx + 15, cy), crosshair_color, 1)
    cv2.line(vis, (cx, cy - 15), (cx, cy + 15), crosshair_color, 1)

    for i, e in enumerate(enemies):
        b = e.bbox
        cv2.rectangle(vis, (b.x, b.y), (b.x+b.w, b.y+b.h), color, 2)
        label = (f"E{i} {e.distance_estimate} "
                 f"{e.screen_angle:+.0f}° conf={e.confidence:.2f}")
        cv2.putText(vis, label, (b.x, b.y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

    return vis


def draw_enemy_mask(
    frame: np.ndarray,
    cfg: PerceptionConfig,
    parser: "WorldParser",
) -> np.ndarray:
    """Return a side-by-side view of the raw frame and the enemy color mask."""
    scan_roi = cfg.rois["enemy_scan"]
    x, y, w, h = scan_roi
    crop = frame[y:y+h, x:x+w]
    mask = parser._build_enemy_mask(crop)
    mask_bgr = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

    # Resize mask to match crop height for display
    display_w = min(w, 640)
    scale = display_w / w
    crop_sm = cv2.resize(crop, (display_w, int(h * scale)))
    mask_sm = cv2.resize(mask_bgr, (display_w, int(h * scale)))
    return np.hstack([crop_sm, mask_sm])
