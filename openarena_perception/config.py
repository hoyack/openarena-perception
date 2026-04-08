"""
config.py — ROI definitions, HSV color ranges, resolution profiles.

All ROI coordinates are expressed as fractions of (screen_w, screen_h)
so the same config works across resolutions. Call `resolve(w, h)` to
get pixel coordinates for a specific resolution.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Tuple
import numpy as np

# ── Type aliases ────────────────────────────────────────────────────────────
FractionalROI = Tuple[float, float, float, float]   # (x, y, w, h) 0–1
PixelROI      = Tuple[int,   int,   int,   int]      # (x, y, w, h) pixels
HSVRange      = Tuple[                               # ((h_lo,s_lo,v_lo),
    Tuple[int, int, int],                            #  (h_hi,s_hi,v_hi))
    Tuple[int, int, int]
]


# ═══════════════════════════════════════════════════════════════════════════
#  RESOLUTION PROFILES
# ═══════════════════════════════════════════════════════════════════════════
KNOWN_RESOLUTIONS: Dict[str, Tuple[int, int]] = {
    "800x600":   (800, 600),
    "1024x768":  (1024, 768),
    "1280x720":  (1280, 720),
    "1280x960":  (1280, 960),
    "1920x1080": (1920, 1080),
}
DEFAULT_RESOLUTION = "800x600"


# ═══════════════════════════════════════════════════════════════════════════
#  FRACTIONAL ROI DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════
DEFAULT_ROIS: Dict[str, FractionalROI] = {
    "health_number":  (0.02,  0.88, 0.10, 0.10),
    "armor_number":   (0.15,  0.88, 0.10, 0.10),
    "ammo_number":    (0.84,  0.88, 0.12, 0.10),
    "weapon_icon":    (0.75,  0.78, 0.20, 0.10),
    "score_frags":    (0.02,  0.01, 0.08, 0.06),
    "score_deaths":   (0.10,  0.01, 0.08, 0.06),
    "enemy_scan":     (0.00,  0.08, 1.00, 0.75),
    "crosshair":      (0.50,  0.50, 0.0,  0.0),
}

RESOLUTION_OVERRIDES: Dict[str, Dict[str, FractionalROI]] = {
    "1920x1080": {
        "health_number": (0.02, 0.90, 0.08, 0.08),
        "armor_number":  (0.13, 0.90, 0.08, 0.08),
        "ammo_number":   (0.86, 0.90, 0.10, 0.08),
    },
}


# ═══════════════════════════════════════════════════════════════════════════
#  HSV COLOR RANGES  (OpenCV HSV: H=0-179, S=0-255, V=0-255)
# ═══════════════════════════════════════════════════════════════════════════
HSV_RANGES: Dict[str, HSVRange] = {
    "enemy_red_lo":  ((0,   120, 100), (10,  255, 255)),
    "enemy_red_hi":  ((165, 120, 100), (179, 255, 255)),
    "enemy_green":   ((45,  120, 100), (80,  255, 255)),
    "enemy_cyan":    ((85,  120, 100), (100, 255, 255)),
    "hud_health_green": ((45, 80, 150), (80, 255, 255)),
    "hud_armor_yellow": ((20, 80, 150), (35, 255, 255)),
}

ENEMY_COLOR_MODE = "red"


# ═══════════════════════════════════════════════════════════════════════════
#  OCR CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════
TESSERACT_CONFIG = {
    "digits": "--psm 7 --oem 1 -c tessedit_char_whitelist=0123456789",
    "signed": "--psm 7 --oem 1 -c tessedit_char_whitelist=0123456789-",
}

OCR_UPSCALE = 3
ENEMY_MIN_AREA = 300
ENEMY_MAX_AREA_FRACTION = 0.15
ENEMY_MORPH_KERNEL = (5, 5)

WEAPON_NAMES: Dict[str, str] = {
    "gauntlet":    "Gauntlet",
    "machinegun":  "Machinegun",
    "shotgun":     "Shotgun",
    "grenade":     "Grenade Launcher",
    "rocket":      "Rocket Launcher",
    "lightning":   "Lightning Gun",
    "railgun":     "Railgun",
    "plasma":      "Plasma Gun",
    "bfg":         "BFG10K",
}


# ═══════════════════════════════════════════════════════════════════════════
#  PerceptionConfig
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class PerceptionConfig:
    screen_w: int
    screen_h: int
    rois: Dict[str, PixelROI]
    hsv_ranges: Dict[str, HSVRange] = field(default_factory=lambda: HSV_RANGES.copy())
    enemy_color_mode: str = ENEMY_COLOR_MODE
    ocr_upscale: int = OCR_UPSCALE
    enemy_min_area: int = ENEMY_MIN_AREA
    enemy_max_area_fraction: float = ENEMY_MAX_AREA_FRACTION
    enemy_morph_kernel: Tuple[int, int] = ENEMY_MORPH_KERNEL
    tesseract_config: Dict[str, str] = field(default_factory=lambda: TESSERACT_CONFIG.copy())
    weapon_templates_dir: str = "weapon_templates"
    window_title: str = "ioquake3"

    @property
    def crosshair_px(self) -> Tuple[int, int]:
        return (self.screen_w // 2, self.screen_h // 2)


def build_config(
    resolution: str = DEFAULT_RESOLUTION,
    screen_w: int = 0,
    screen_h: int = 0,
    **overrides,
) -> PerceptionConfig:
    if screen_w == 0 or screen_h == 0:
        if resolution not in KNOWN_RESOLUTIONS:
            raise ValueError(f"Unknown resolution '{resolution}'. "
                             f"Pass screen_w/screen_h explicitly.")
        screen_w, screen_h = KNOWN_RESOLUTIONS[resolution]

    frac_rois = {**DEFAULT_ROIS}
    if resolution in RESOLUTION_OVERRIDES:
        frac_rois.update(RESOLUTION_OVERRIDES[resolution])

    pixel_rois: Dict[str, PixelROI] = {}
    for name, (fx, fy, fw, fh) in frac_rois.items():
        pixel_rois[name] = (
            int(fx * screen_w),
            int(fy * screen_h),
            int(fw * screen_w),
            int(fh * screen_h),
        )

    cfg = PerceptionConfig(screen_w=screen_w, screen_h=screen_h, rois=pixel_rois)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg
