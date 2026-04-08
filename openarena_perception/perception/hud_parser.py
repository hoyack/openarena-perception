"""
hud_parser.py — Extracts numeric HUD values and weapon identity from a frame.

Approach:
  1. Crop each ROI from the frame.
  2. Isolate the number by color-masking the known HUD digit color.
  3. Upscale the crop.
  4. Run Tesseract in digits-only mode.
  5. Return typed values (int or None on failure).

Weapon detection uses template matching against pre-rendered icon crops.
If no templates exist, it falls back to returning None.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

try:
    import pytesseract
except ImportError:
    raise ImportError("Install pytesseract: pip install pytesseract  "
                      "(also: sudo apt install tesseract-ocr)")

from openarena_perception.config import PerceptionConfig, WEAPON_NAMES

log = logging.getLogger(__name__)


# ─── helpers ─────────────────────────────────────────────────────────────────

def _crop(frame: np.ndarray, roi: Tuple[int, int, int, int]) -> np.ndarray:
    x, y, w, h = roi
    return frame[y:y+h, x:x+w]


def _preprocess_for_ocr(
    crop: np.ndarray,
    upscale: int = 3,
    threshold: bool = True,
) -> np.ndarray:
    """
    Upscale + threshold a HUD digit crop for Tesseract.
    Converts to grayscale, upscales, and binarizes.
    """
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    big  = cv2.resize(gray, (gray.shape[1] * upscale,
                             gray.shape[0] * upscale),
                      interpolation=cv2.INTER_CUBIC)
    if threshold:
        _, bw = cv2.threshold(big, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return bw
    return big


def _ocr_digits(img: np.ndarray, cfg: str) -> Optional[int]:
    """Run Tesseract and return parsed int, or None on failure."""
    try:
        raw = pytesseract.image_to_string(img, config=cfg).strip()
        # Strip any stray non-digit chars (except leading -)
        cleaned = "".join(c for c in raw if c.isdigit() or c == "-")
        return int(cleaned) if cleaned else None
    except Exception as exc:
        log.debug("OCR failed: %s", exc)
        return None


# ─── HUDParser ───────────────────────────────────────────────────────────────

class HUDParser:
    """
    Parses all HUD elements from a single BGR frame using the given config.

    Lifetime: create once, call parse_frame() on each frame.
    """

    def __init__(self, cfg: PerceptionConfig):
        self.cfg = cfg
        self._weapon_templates: Dict[str, np.ndarray] = {}
        self._load_weapon_templates()

    # ── Public interface ────────────────────────────────────────────────────

    def parse_health(self, frame: np.ndarray) -> Optional[int]:
        return self._parse_hud_number(frame, "health_number", "digits")

    def parse_armor(self, frame: np.ndarray) -> Optional[int]:
        return self._parse_hud_number(frame, "armor_number", "digits")

    def parse_ammo(self, frame: np.ndarray) -> Optional[int]:
        return self._parse_hud_number(frame, "ammo_number", "digits")

    def parse_frags(self, frame: np.ndarray) -> Optional[int]:
        return self._parse_hud_number(frame, "score_frags", "signed")

    def parse_deaths(self, frame: np.ndarray) -> Optional[int]:
        return self._parse_hud_number(frame, "score_deaths", "digits")

    def parse_weapon(self, frame: np.ndarray) -> Optional[str]:
        """
        Template-match against pre-captured weapon icon crops.
        Returns the weapon display name, or None if no template found.

        To create templates: run the ROI debugger and save crops for each
        weapon as `weapon_templates/<name>.png`.
        """
        if not self._weapon_templates:
            return None

        roi = self.cfg.rois.get("weapon_icon")
        if roi is None:
            return None

        crop = _crop(frame, roi)
        gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        best_name  = None
        best_score = 0.4   # minimum threshold

        for name, tmpl in self._weapon_templates.items():
            if tmpl.shape[0] > gray_crop.shape[0] or \
               tmpl.shape[1] > gray_crop.shape[1]:
                continue  # template larger than crop — skip
            result = cv2.matchTemplate(gray_crop, tmpl,
                                       cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val > best_score:
                best_score = max_val
                best_name  = name

        return WEAPON_NAMES.get(best_name) if best_name else None

    def parse_all(self, frame: np.ndarray) -> Dict:
        """Parse all HUD elements and return a dict."""
        return {
            "health": self.parse_health(frame),
            "armor":  self.parse_armor(frame),
            "ammo":   self.parse_ammo(frame),
            "weapon": self.parse_weapon(frame),
            "frags":  self.parse_frags(frame),
            "deaths": self.parse_deaths(frame),
        }

    # ── Internals ───────────────────────────────────────────────────────────

    def _parse_hud_number(
        self,
        frame: np.ndarray,
        roi_name: str,
        ocr_mode: str = "digits",
    ) -> Optional[int]:
        roi = self.cfg.rois.get(roi_name)
        if roi is None:
            return None

        crop = _crop(frame, roi)
        if crop.size == 0:
            return None

        img = _preprocess_for_ocr(crop, upscale=self.cfg.ocr_upscale)
        tess_cfg = self.cfg.tesseract_config.get(ocr_mode,
                   self.cfg.tesseract_config["digits"])
        value = _ocr_digits(img, tess_cfg)

        if value is not None:
            log.debug("HUD[%s] = %d", roi_name, value)
        return value

    def _load_weapon_templates(self):
        """Load grayscale weapon icon templates from the templates dir."""
        tmpl_dir = Path(self.cfg.weapon_templates_dir)
        if not tmpl_dir.exists():
            log.info("No weapon_templates dir found at '%s'. "
                     "Weapon detection disabled. See docs to create templates.",
                     tmpl_dir)
            return

        for path in tmpl_dir.glob("*.png"):
            name = path.stem.lower()
            img  = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                self._weapon_templates[name] = img
                log.debug("Loaded weapon template: %s (%dx%d)",
                          name, img.shape[1], img.shape[0])

        log.info("Loaded %d weapon templates from '%s'",
                 len(self._weapon_templates), tmpl_dir)


# ─── Diagnostic helper ────────────────────────────────────────────────────────

def draw_hud_rois(
    frame: np.ndarray,
    cfg: PerceptionConfig,
    color: Tuple[int, int, int] = (0, 255, 255),
) -> np.ndarray:
    """
    Draw all HUD ROI rectangles onto a copy of the frame.
    Useful for visual calibration.
    """
    vis = frame.copy()
    hud_names = ["health_number", "armor_number", "ammo_number",
                 "weapon_icon", "score_frags", "score_deaths"]
    for name in hud_names:
        roi = cfg.rois.get(name)
        if roi is None:
            continue
        x, y, w, h = roi
        cv2.rectangle(vis, (x, y), (x+w, y+h), color, 2)
        cv2.putText(vis, name, (x+2, y+14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    return vis
