"""
motion_anomaly.py — Detect and identify non-ego-motion in the game world.

Quake 3 maps have various animated objects:
  - Spinning weapons on spawn pads
  - Floating/bobbing health packs and armor
  - Moving platforms (plats)
  - Teleporter effects
  - Lava/water surface animation
  - Enemy players (biggest threat)

This module detects ANY motion that isn't caused by the bot's own
camera movement, locks crosshairs on it, captures a close-up,
and sends it to the vision LLM for identification.

Algorithm:
  1. Compute sparse optical flow (Lucas-Kanade) between frames
  2. Estimate ego-motion (dominant flow direction from camera turning)
  3. Subtract ego-motion to find anomalous flow vectors
  4. Cluster anomalous flow into objects
  5. Track objects across frames (require 3+ frame persistence)
  6. For new persistent objects: lock crosshair, capture, identify via LLM

Runs at ~3-5ms per frame on RPi5 (sparse flow is very fast).
"""

from __future__ import annotations

import base64
import json
import logging
import math
import os
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger(__name__)


@dataclass
class TrackedAnomaly:
    """A tracked motion anomaly in screen space."""
    track_id: int
    cx: int                     # screen center x
    cy: int                     # screen center y
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    flow_magnitude: float       # average anomalous flow speed (px/frame)
    flow_angle: float           # dominant flow direction (degrees)
    frames_seen: int = 1        # how many frames this has been tracked
    frames_lost: int = 0        # consecutive frames not seen
    identified: bool = False    # has the LLM identified this?
    identity: str = ""          # LLM identification result
    category: str = ""          # threat/item/decoration/platform/unknown
    confidence: float = 0.0
    first_seen: float = 0.0
    last_seen: float = 0.0
    image_path: str = ""        # saved reference image


@dataclass
class AnomalyReport:
    """LLM identification result for an anomaly."""
    identity: str
    category: str       # threat/item/decoration/platform/hazard/unknown
    confidence: float
    action: str         # investigate/collect/avoid/attack/ignore
    description: str


# Identification prompt for the vision LLM
IDENTIFY_PROMPT = (
    "You are analyzing a close-up from a Quake 3 arena game. "
    "Something is MOVING at the crosshair location in this image.\n\n"
    "Identify what the moving object is. Common possibilities:\n"
    "- WEAPON: spinning weapon on a spawn pad (rocket launcher, railgun, shotgun, etc.)\n"
    "- HEALTH: floating/bobbing health pickup (green cross, large health, mega health)\n"
    "- ARMOR: floating armor pickup (yellow/gold shard, combat armor, body armor)\n"
    "- POWERUP: quad damage (blue glow), invisibility, haste, regeneration\n"
    "- AMMO: ammo box/crate\n"
    "- ENEMY: player character moving (usually red-tinted model)\n"
    "- PLATFORM: moving elevator or platform\n"
    "- TELEPORTER: swirling teleporter effect\n"
    "- PROJECTILE: rocket, grenade, plasma bolt in flight\n"
    "- HAZARD: lava bubbling, water surface, slime\n"
    "- DECORATION: map animation (torch, flag, banner, light fixture)\n\n"
    "Respond with ONLY a JSON object:\n"
    '{\n'
    '  "identity": "specific name (e.g. rocket launcher, mega health, Sarge)",\n'
    '  "category": "weapon" or "health" or "armor" or "powerup" or "ammo" or '
    '"enemy" or "platform" or "teleporter" or "projectile" or "hazard" or "decoration",\n'
    '  "confidence": 0.0 to 1.0,\n'
    '  "action": "collect" or "attack" or "avoid" or "investigate" or "use" or "ignore",\n'
    '  "description": "1 sentence description"\n'
    "}\n\n"
    "The bottom of the image shows HUD numbers — ignore those."
)


class MotionAnomalyTracker:
    """
    Detects world-object motion independent of camera ego-motion.
    Uses sparse optical flow with ego-motion compensation.
    """

    # Optical flow parameters
    LK_PARAMS = dict(
        winSize=(21, 21),
        maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
    )

    # Feature detection for sparse flow
    FEATURE_PARAMS = dict(
        maxCorners=200,
        qualityLevel=0.05,
        minDistance=15,
        blockSize=7,
    )

    # Anomaly detection thresholds
    EGO_FLOW_CONSENSUS = 0.6    # fraction of points that must agree for ego-motion
    ANOMALY_MIN_SPEED = 2.0     # min px/frame to be "anomalous" after ego subtraction
    ANOMALY_MAX_SPEED = 40.0    # max — filter out ego-motion leakage and tracking failures
    MIN_CLUSTER_POINTS = 3      # minimum flow points to form an anomaly cluster
    CLUSTER_RADIUS = 60         # pixels — max distance between cluster members
    PERSISTENCE_THRESHOLD = 3   # frames before we identify an anomaly
    LOST_THRESHOLD = 5          # frames before we drop a track
    MATCH_RADIUS = 80           # pixels — max distance to match track across frames

    # Scan region (exclude HUD)
    SCAN_TOP = 0.08
    SCAN_BOTTOM = 0.82

    # Rate limiting
    IDENTIFY_COOLDOWN = 5.0     # seconds between LLM identification attempts
    MAX_PENDING_IDS = 2         # max concurrent LLM queries

    def __init__(
        self,
        model: str = "gemma4:31b-cloud",
        ollama_url: str = "http://localhost:11434/api/generate",
        save_dir: str = "",
    ):
        self.model = model
        self.ollama_url = ollama_url

        if not save_dir:
            save_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                    "anomaly_captures")
        self.save_dir = save_dir
        os.makedirs(save_dir, exist_ok=True)

        self._prev_gray: Optional[np.ndarray] = None
        self._prev_points: Optional[np.ndarray] = None

        # Tracking state
        self._tracks: Dict[int, TrackedAnomaly] = {}
        self._next_id = 1
        self._frame_count = 0

        # LLM rate limiting
        self._last_identify_time = 0.0
        self._pending_ids = 0
        self._identify_count = 0

        # Identified objects catalog
        self._catalog: List[TrackedAnomaly] = []

        # Is the bot currently stationary? (better detection when still)
        self._bot_stationary = False
        self._last_pos: Optional[Tuple[float, float]] = None

    def update(
        self,
        frame: np.ndarray,
        bot_pos: Optional[Tuple[float, float]] = None,
        bot_yaw: Optional[float] = None,
    ) -> List[TrackedAnomaly]:
        """
        Process a frame and return any active anomaly tracks.

        Args:
            frame: BGR game frame
            bot_pos: (x, y) world position for ego-motion estimation
            bot_yaw: current yaw angle

        Returns:
            List of active TrackedAnomaly objects
        """
        self._frame_count += 1
        now = time.time()
        h, w = frame.shape[:2]

        # Check if bot is stationary (better motion detection)
        if bot_pos and self._last_pos:
            dist = math.hypot(bot_pos[0] - self._last_pos[0],
                              bot_pos[1] - self._last_pos[1])
            self._bot_stationary = dist < 5.0
        self._last_pos = bot_pos

        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if self._prev_gray is None:
            self._prev_gray = gray
            return []

        # === Step 1: Compute sparse optical flow ===
        # Get features to track in previous frame
        y_top = int(h * self.SCAN_TOP)
        y_bot = int(h * self.SCAN_BOTTOM)

        mask = np.zeros_like(gray)
        mask[y_top:y_bot, :] = 255

        prev_pts = cv2.goodFeaturesToTrack(
            self._prev_gray, mask=mask, **self.FEATURE_PARAMS)

        if prev_pts is None or len(prev_pts) < 10:
            self._prev_gray = gray
            self._age_tracks()
            return list(self._tracks.values())

        # Track points to current frame
        curr_pts, status, err = cv2.calcOpticalFlowPyrLK(
            self._prev_gray, gray, prev_pts, None, **self.LK_PARAMS)

        # Filter valid tracks
        good_mask = status.flatten() == 1
        if err is not None:
            good_mask &= err.flatten() < 15.0

        prev_good = prev_pts[good_mask]
        curr_good = curr_pts[good_mask]

        if len(prev_good) < 5:
            self._prev_gray = gray
            self._age_tracks()
            return list(self._tracks.values())

        # === Step 2: Estimate ego-motion (dominant flow) ===
        flow_vectors = curr_good - prev_good  # shape (N, 1, 2)
        flow_vectors = flow_vectors.reshape(-1, 2)

        # Median flow = robust ego-motion estimate
        ego_dx = np.median(flow_vectors[:, 0])
        ego_dy = np.median(flow_vectors[:, 1])

        # === Step 3: Subtract ego-motion → anomalous flow ===
        anomaly_vectors = flow_vectors - np.array([ego_dx, ego_dy])
        anomaly_speeds = np.linalg.norm(anomaly_vectors, axis=1)

        # Find points with significant anomalous motion
        anomaly_mask = (
            (anomaly_speeds > self.ANOMALY_MIN_SPEED) &
            (anomaly_speeds < self.ANOMALY_MAX_SPEED)
        )

        anomaly_pts = curr_good[anomaly_mask].reshape(-1, 2)
        anomaly_flows = anomaly_vectors[anomaly_mask]
        anomaly_spds = anomaly_speeds[anomaly_mask]

        # === Step 4: Cluster anomalous points into objects ===
        clusters = self._cluster_points(anomaly_pts, anomaly_flows, anomaly_spds)

        # === Step 5: Update tracks ===
        self._update_tracks(clusters, now)

        self._prev_gray = gray
        return list(self._tracks.values())

    def get_lockable_anomaly(self) -> Optional[TrackedAnomaly]:
        """
        Get the most interesting unidentified anomaly that should be
        locked on and identified. Returns None if nothing needs ID.
        """
        now = time.time()
        if now - self._last_identify_time < self.IDENTIFY_COOLDOWN:
            return None
        if self._pending_ids >= self.MAX_PENDING_IDS:
            return None

        candidates = [
            t for t in self._tracks.values()
            if (t.frames_seen >= self.PERSISTENCE_THRESHOLD and
                not t.identified and
                t.frames_lost == 0)
        ]

        if not candidates:
            return None

        # Prioritize by flow magnitude (most motion = most interesting)
        candidates.sort(key=lambda t: t.flow_magnitude, reverse=True)
        return candidates[0]

    def identify_anomaly(
        self,
        track: TrackedAnomaly,
        frame: np.ndarray,
    ) -> Optional[AnomalyReport]:
        """
        Capture a close-up of the anomaly and send to LLM for identification.
        This is a BLOCKING call (~0.75s).
        """
        self._last_identify_time = time.time()
        self._pending_ids += 1

        h, w = frame.shape[:2]
        x1, y1, x2, y2 = track.bbox

        # Expand bbox for context (50% padding)
        pad_x = max(40, (x2 - x1) // 2)
        pad_y = max(40, (y2 - y1) // 2)
        rx1 = max(0, x1 - pad_x)
        ry1 = max(0, y1 - pad_y)
        rx2 = min(w, x2 + pad_x)
        ry2 = min(h, y2 + pad_y)

        # Save reference image
        crop = frame[ry1:ry2, rx1:rx2].copy()

        # Draw crosshair on the anomaly center
        cv2.circle(crop, (track.cx - rx1, track.cy - ry1), 8, (0, 255, 0), 2)
        cv2.line(crop, (track.cx - rx1 - 15, track.cy - ry1),
                 (track.cx - rx1 + 15, track.cy - ry1), (0, 255, 0), 1)
        cv2.line(crop, (track.cx - rx1, track.cy - ry1 - 15),
                 (track.cx - rx1, track.cy - ry1 + 15), (0, 255, 0), 1)

        img_name = f"anomaly_{track.track_id}_{int(time.time())}.jpg"
        img_path = os.path.join(self.save_dir, img_name)
        cv2.imwrite(img_path, crop, [cv2.IMWRITE_JPEG_QUALITY, 80])
        track.image_path = img_path

        # Also save full frame with marker
        full_marked = frame.copy()
        cv2.rectangle(full_marked, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(full_marked, f"ANOMALY #{track.track_id}",
                    (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 255, 0), 2)
        full_path = os.path.join(self.save_dir,
                                 f"anomaly_{track.track_id}_full.jpg")
        cv2.imwrite(full_path, full_marked, [cv2.IMWRITE_JPEG_QUALITY, 70])

        # Send the FULL frame to LLM (more context than just crop)
        # But draw attention to the crosshair area
        try:
            report = self._ask_llm(full_marked)
            track.identified = True
            track.identity = report.identity
            track.category = report.category
            track.confidence = report.confidence
            self._identify_count += 1
            self._catalog.append(track)

            log.info("ANOMALY #%d IDENTIFIED: %s (%s) confidence=%.2f — %s",
                     track.track_id, report.identity, report.category,
                     report.confidence, report.description)
            log.info("  Action: %s | Image: %s", report.action, img_path)

            return report
        except Exception as e:
            log.warning("Anomaly identification failed: %s", e)
            return None
        finally:
            self._pending_ids -= 1

    def _ask_llm(self, frame: np.ndarray) -> AnomalyReport:
        """Send frame to Ollama for identification."""
        h, w = frame.shape[:2]
        scale = min(1.0, 512 / max(h, w))
        if scale < 1.0:
            small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        else:
            small = frame
        _, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 60])
        b64 = base64.b64encode(buf).decode()

        data = json.dumps({
            "model": self.model,
            "prompt": IDENTIFY_PROMPT,
            "images": [b64],
            "stream": False,
            "options": {"num_predict": 150, "temperature": 0.1},
        }).encode()

        req = urllib.request.Request(
            self.ollama_url, data=data,
            headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        text = result.get("response", "{}").strip()

        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0].strip()

        d = json.loads(text)
        return AnomalyReport(
            identity=d.get("identity", "unknown"),
            category=d.get("category", "unknown"),
            confidence=d.get("confidence", 0.0),
            action=d.get("action", "investigate"),
            description=d.get("description", ""),
        )

    def _cluster_points(
        self,
        pts: np.ndarray,
        flows: np.ndarray,
        speeds: np.ndarray,
    ) -> List[Tuple[int, int, Tuple[int, int, int, int], float, float]]:
        """
        Simple proximity clustering of anomalous flow points.
        Returns list of (cx, cy, bbox, avg_speed, avg_angle).
        """
        if len(pts) < self.MIN_CLUSTER_POINTS:
            return []

        # Simple greedy clustering
        used = set()
        clusters = []

        for i in range(len(pts)):
            if i in used:
                continue

            cluster_pts = [i]
            used.add(i)

            for j in range(i + 1, len(pts)):
                if j in used:
                    continue
                d = math.hypot(pts[j][0] - pts[i][0], pts[j][1] - pts[i][1])
                if d < self.CLUSTER_RADIUS:
                    cluster_pts.append(j)
                    used.add(j)

            if len(cluster_pts) >= self.MIN_CLUSTER_POINTS:
                c_pts = pts[cluster_pts]
                c_flows = flows[cluster_pts]
                c_speeds = speeds[cluster_pts]

                cx = int(np.mean(c_pts[:, 0]))
                cy = int(np.mean(c_pts[:, 1]))
                x1 = int(np.min(c_pts[:, 0])) - 10
                y1 = int(np.min(c_pts[:, 1])) - 10
                x2 = int(np.max(c_pts[:, 0])) + 10
                y2 = int(np.max(c_pts[:, 1])) + 10
                avg_speed = float(np.mean(c_speeds))
                avg_dx = float(np.mean(c_flows[:, 0]))
                avg_dy = float(np.mean(c_flows[:, 1]))
                avg_angle = math.degrees(math.atan2(avg_dy, avg_dx))

                clusters.append((cx, cy, (x1, y1, x2, y2), avg_speed, avg_angle))

        return clusters

    def _update_tracks(self, clusters, now: float):
        """Match clusters to existing tracks, create new ones, age lost ones."""
        matched_tracks = set()
        matched_clusters = set()

        # Match existing tracks to new clusters by proximity
        for tid, track in list(self._tracks.items()):
            best_dist = float('inf')
            best_ci = -1
            for ci, (cx, cy, bbox, speed, angle) in enumerate(clusters):
                if ci in matched_clusters:
                    continue
                d = math.hypot(cx - track.cx, cy - track.cy)
                if d < self.MATCH_RADIUS and d < best_dist:
                    best_dist = d
                    best_ci = ci

            if best_ci >= 0:
                cx, cy, bbox, speed, angle = clusters[best_ci]
                track.cx = cx
                track.cy = cy
                track.bbox = bbox
                track.flow_magnitude = speed
                track.flow_angle = angle
                track.frames_seen += 1
                track.frames_lost = 0
                track.last_seen = now
                matched_tracks.add(tid)
                matched_clusters.add(best_ci)

        # Create new tracks for unmatched clusters
        for ci, (cx, cy, bbox, speed, angle) in enumerate(clusters):
            if ci in matched_clusters:
                continue
            track = TrackedAnomaly(
                track_id=self._next_id,
                cx=cx, cy=cy, bbox=bbox,
                flow_magnitude=speed,
                flow_angle=angle,
                first_seen=now,
                last_seen=now,
            )
            self._tracks[self._next_id] = track
            self._next_id += 1

        # Age unmatched tracks
        self._age_tracks(matched_tracks)

    def _age_tracks(self, matched: set = None):
        """Increment lost counter for unmatched tracks, remove old ones."""
        if matched is None:
            matched = set()
        to_remove = []
        for tid, track in self._tracks.items():
            if tid not in matched:
                track.frames_lost += 1
                if track.frames_lost > self.LOST_THRESHOLD:
                    to_remove.append(tid)
        for tid in to_remove:
            del self._tracks[tid]

    def get_crosshair_offset(self, track: TrackedAnomaly,
                              screen_w: int, screen_h: int) -> Tuple[int, int]:
        """
        Get the mouse movement needed to center crosshair on the anomaly.
        Returns (dx, dy) in pixels.
        """
        cx = screen_w // 2
        cy = screen_h // 2
        return (track.cx - cx, track.cy - cy)

    def reset(self):
        """Reset all state (call after respawn/teleport)."""
        self._prev_gray = None
        self._tracks.clear()
        self._next_id = 1

    @property
    def active_tracks(self) -> int:
        return len(self._tracks)

    @property
    def identified_count(self) -> int:
        return self._identify_count

    @property
    def catalog(self) -> List[TrackedAnomaly]:
        return self._catalog

    def get_status(self) -> str:
        persistent = sum(1 for t in self._tracks.values()
                         if t.frames_seen >= self.PERSISTENCE_THRESHOLD)
        identified = sum(1 for t in self._tracks.values() if t.identified)
        return (f"anomalies={self.active_tracks} "
                f"persistent={persistent} "
                f"identified={self._identify_count}")
