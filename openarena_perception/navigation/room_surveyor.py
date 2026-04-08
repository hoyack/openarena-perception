"""
room_surveyor.py — 360 deg room survey with LLM-powered spatial documentation.

When the bot enters an undocumented area, it stops and performs a full survey:
  1. Look at 8 compass directions (0 deg, 45 deg, 90 deg, ..., 315 deg)
  2. At each direction, capture a screenshot
  3. Also look up and down at key angles for vertical awareness
  4. Send all captures to the vision LLM for analysis
  5. Document: exits, routes, stairs, vantage points, items, hazards
  6. Store as JSON + reference images keyed by AAS area cluster

Future visits to the same area skip the survey and use stored data
for navigation decisions.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from openarena_perception.game_bridge import GameBridge

log = logging.getLogger(__name__)

# Survey analysis prompt
SURVEY_PROMPT_TEMPLATE = (
    "You are analyzing 360 deg views from inside a room in a Quake 3 arena map.\n\n"
    "I'm showing you NUM_VIEWS views captured at different angles from the same position.\n"
    "The views are labeled by compass direction (N, NE, E, SE, S, SW, W, NW) plus UP and DOWN.\n\n"
    "For each view, identify:\n"
    "1. Is there an EXIT (doorway, corridor, opening leading to another area)?\n"
    "2. Are there STAIRS (up or down)?\n"
    "3. Are there ITEMS visible (weapons, health, armor pickups)?\n"
    "4. Is there a VANTAGE POINT (elevated position good for sniping)?\n"
    "5. Are there HAZARDS (lava, water, pits)?\n"
    "6. Is there a WALL (dead end in this direction)?\n\n"
    'Respond with ONLY a JSON object:\n'
    '{\n'
    '  "room_type": "corridor" or "open_room" or "arena" or "hallway" or "stairwell" or "platform" or "jail_cell",\n'
    '  "exits": [\n'
    '    {"direction": "N/NE/E/SE/S/SW/W/NW", "type": "doorway/corridor/stairs_up/stairs_down/opening/portal", "description": "brief"}\n'
    '  ],\n'
    '  "items": [\n'
    '    {"direction": "N/NE/E/SE/S/SW/W/NW", "type": "weapon/health/armor/powerup", "description": "brief"}\n'
    '  ],\n'
    '  "vantage_points": [\n'
    '    {"direction": "N/NE/E/SE/S/SW/W/NW", "description": "brief"}\n'
    '  ],\n'
    '  "hazards": [\n'
    '    {"direction": "N/NE/E/SE/S/SW/W/NW", "type": "lava/water/pit/bars", "description": "brief"}\n'
    '  ],\n'
    '  "recommended_exit": "N/NE/E/SE/S/SW/W/NW",\n'
    '  "summary": "1-2 sentence room description"\n'
    '}\n\n'
    "Be thorough but concise. The bottom of each image shows HUD elements -- ignore those."
)


@dataclass
class RoomSurvey:
    """Stored survey data for a room/area."""
    area_id: int
    position: Tuple[float, float, float]
    yaw_at_survey: float
    timestamp: float
    room_type: str = ""
    exits: List[dict] = field(default_factory=list)
    items: List[dict] = field(default_factory=list)
    vantage_points: List[dict] = field(default_factory=list)
    hazards: List[dict] = field(default_factory=list)
    recommended_exit: str = ""
    summary: str = ""
    image_paths: Dict[str, str] = field(default_factory=dict)

    def best_exit_yaw(self, base_yaw: float) -> Optional[float]:
        """Get the world yaw for the recommended exit direction."""
        if not self.recommended_exit:
            return None
        return self._direction_to_yaw(self.recommended_exit, base_yaw)

    def exit_yaws(self, base_yaw: float) -> List[Tuple[str, float, str]]:
        """Get (direction, yaw, type) for all exits."""
        results = []
        for ex in self.exits:
            yaw = self._direction_to_yaw(ex["direction"], base_yaw)
            results.append((ex["direction"], yaw, ex.get("type", "unknown")))
        return results

    @staticmethod
    def _direction_to_yaw(direction: str, base_yaw: float) -> float:
        """Convert a compass direction relative to survey yaw to world yaw."""
        offsets = {
            "N": 0, "NE": 45, "E": 90, "SE": 135,
            "S": 180, "SW": 225, "W": 270, "NW": 315,
        }
        offset = offsets.get(direction.upper(), 0)
        return (base_yaw + offset) % 360


class RoomSurveyor:
    """
    Surveys rooms by capturing views at 8 compass angles + up/down,
    then uses vision LLM to document the space.
    """

    DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    VERTICAL = ["UP", "DOWN"]

    def __init__(
        self,
        bridge: GameBridge,
        survey_dir: str = "",
        model: str = "gemma4:31b-cloud",
        ollama_url: str = "http://localhost:11434/api/generate",
    ):
        self.bridge = bridge
        self.model = model
        self.ollama_url = ollama_url

        # Storage directory for survey data + images
        if not survey_dir:
            survey_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                       "room_surveys")
        self.survey_dir = survey_dir
        os.makedirs(self.survey_dir, exist_ok=True)
        os.makedirs(os.path.join(self.survey_dir, "images"), exist_ok=True)

        # In-memory cache of surveys keyed by area_id
        self._surveys: Dict[int, RoomSurvey] = {}
        self._load_existing()

        # Track which areas we've entered to detect new rooms
        self._visited_areas: set = set()
        self._survey_count = 0

    def has_survey(self, area_id: int) -> bool:
        """Check if we already have a survey for this area."""
        return area_id in self._surveys

    def get_survey(self, area_id: int) -> Optional[RoomSurvey]:
        return self._surveys.get(area_id)

    def should_survey(self, area_id: int) -> bool:
        """Returns True if this area hasn't been surveyed yet."""
        return area_id > 0 and area_id not in self._surveys

    def perform_survey(
        self,
        area_id: int,
        pos: Tuple[float, float, float],
        start_yaw: float,
        capture_fn,
    ) -> Optional[RoomSurvey]:
        """
        Perform a full 360 deg room survey.

        Args:
            area_id: AAS area index
            pos: Current world position
            start_yaw: Current yaw angle (this becomes "North" for the survey)
            capture_fn: Callable that returns a BGR numpy frame

        Returns:
            RoomSurvey with documented exits, items, etc.
        """
        log.info("=== ROOM SURVEY: area %d at (%.0f,%.0f,%.0f) yaw=%.0f ===",
                 area_id, pos[0], pos[1], pos[2], start_yaw)

        # Stop all movement during survey
        self.bridge.stop_movement()
        self.bridge.stop_firing()
        time.sleep(0.3)

        captures = {}
        image_paths = {}

        # 1. Capture at each compass direction (45 deg increments)
        for i, direction in enumerate(self.DIRECTIONS):
            target_yaw = start_yaw + (i * 45)
            self._turn_to_yaw(target_yaw, start_yaw)

            # Center view (level pitch)
            self.bridge.cmd("centerview")
            time.sleep(0.3)

            frame = capture_fn()
            if frame is not None:
                captures[direction] = frame
                # Save reference image
                img_name = f"area_{area_id}_{direction}.jpg"
                img_path = os.path.join(self.survey_dir, "images", img_name)
                cv2.imwrite(img_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                image_paths[direction] = img_path
                log.info("  Captured %s (yaw=%.0f)", direction, target_yaw % 360)

        # 2. Look up and down from North
        self._turn_to_yaw(start_yaw, start_yaw)
        time.sleep(0.2)

        # Look up
        self.bridge.cmd("cl_pitchspeed 150")
        self.bridge.action_start("lookup")
        time.sleep(0.3)
        self.bridge.action_stop("lookup")
        time.sleep(0.2)
        frame = capture_fn()
        if frame is not None:
            captures["UP"] = frame
            img_name = f"area_{area_id}_UP.jpg"
            img_path = os.path.join(self.survey_dir, "images", img_name)
            cv2.imwrite(img_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            image_paths["UP"] = img_path
            log.info("  Captured UP")

        # Return to center
        self.bridge.cmd("centerview")
        time.sleep(0.2)

        # Look down
        self.bridge.action_start("lookdown")
        time.sleep(0.3)
        self.bridge.action_stop("lookdown")
        time.sleep(0.2)
        frame = capture_fn()
        if frame is not None:
            captures["DOWN"] = frame
            img_name = f"area_{area_id}_DOWN.jpg"
            img_path = os.path.join(self.survey_dir, "images", img_name)
            cv2.imwrite(img_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            image_paths["DOWN"] = img_path
            log.info("  Captured DOWN")

        # Return to center
        self.bridge.cmd("centerview")
        time.sleep(0.2)

        # 3. Send all captures to LLM for analysis
        log.info("  Sending %d views to vision LLM for analysis...", len(captures))
        survey_data = self._analyze_views(captures)

        # 4. Build and store the survey
        survey = RoomSurvey(
            area_id=area_id,
            position=pos,
            yaw_at_survey=start_yaw,
            timestamp=time.time(),
            room_type=survey_data.get("room_type", "unknown"),
            exits=survey_data.get("exits", []),
            items=survey_data.get("items", []),
            vantage_points=survey_data.get("vantage_points", []),
            hazards=survey_data.get("hazards", []),
            recommended_exit=survey_data.get("recommended_exit", ""),
            summary=survey_data.get("summary", ""),
            image_paths=image_paths,
        )

        self._surveys[area_id] = survey
        self._save_survey(survey)
        self._survey_count += 1

        log.info("=== SURVEY COMPLETE: %s ===", survey.summary)
        log.info("  Room type: %s | Exits: %d | Items: %d | Hazards: %d",
                 survey.room_type, len(survey.exits),
                 len(survey.items), len(survey.hazards))
        for ex in survey.exits:
            log.info("  EXIT %s: %s -- %s",
                     ex["direction"], ex.get("type", "?"), ex.get("description", ""))
        if survey.recommended_exit:
            log.info("  RECOMMENDED EXIT: %s", survey.recommended_exit)

        return survey

    def _turn_to_yaw(self, target_yaw: float, start_yaw: float):
        """Turn to a specific yaw angle using timed pipe commands."""
        delta = ((target_yaw - start_yaw + 180) % 360) - 180

        if abs(delta) < 5:
            return

        YAW_SPEED = 200
        duration = abs(delta) / YAW_SPEED
        direction = "left" if delta > 0 else "right"

        self.bridge.cmd(f"cl_yawspeed {YAW_SPEED}")
        self.bridge.action_start(direction)
        time.sleep(duration)
        self.bridge.action_stop(direction)
        time.sleep(0.1)

    def _analyze_views(self, captures: Dict[str, np.ndarray]) -> dict:
        """Send captured views to the vision LLM for room analysis."""
        import urllib.request

        # Build a composite image grid (2 rows of 5) for efficiency
        # Or send individual images -- Ollama supports multiple images
        images_b64 = []
        labels = []

        for direction in self.DIRECTIONS + self.VERTICAL:
            if direction in captures:
                frame = captures[direction]
                # Resize for efficiency
                h, w = frame.shape[:2]
                scale = min(1.0, 400 / max(h, w))
                if scale < 1.0:
                    frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

                # Add direction label to the image
                cv2.putText(frame, direction, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 55])
                images_b64.append(base64.b64encode(buf).decode())
                labels.append(direction)

        # Build prompt with direction info
        prompt = SURVEY_PROMPT_TEMPLATE.replace("NUM_VIEWS", str(len(labels)))
        prompt += f"\n\nViews provided (in order): {', '.join(labels)}"

        try:
            data = json.dumps({
                "model": self.model,
                "prompt": prompt,
                "images": images_b64,
                "stream": False,
                "options": {"num_predict": 500, "temperature": 0.1},
            }).encode()

            req = urllib.request.Request(
                self.ollama_url, data=data,
                headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read())
            text = result.get("response", "{}").strip()

            # Strip markdown fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
                text = text.rsplit("```", 1)[0].strip()

            return json.loads(text)
        except json.JSONDecodeError as e:
            log.warning("Survey LLM returned non-JSON: %s", str(e)[:80])
            return {"room_type": "unknown", "summary": "LLM parse error"}
        except Exception as e:
            log.warning("Survey LLM call failed: %s", e)
            return {"room_type": "unknown", "summary": f"LLM error: {e}"}

    def _save_survey(self, survey: RoomSurvey):
        """Save survey data as JSON."""
        path = os.path.join(self.survey_dir, f"area_{survey.area_id}.json")
        data = {
            "area_id": survey.area_id,
            "position": list(survey.position),
            "yaw_at_survey": survey.yaw_at_survey,
            "timestamp": survey.timestamp,
            "room_type": survey.room_type,
            "exits": survey.exits,
            "items": survey.items,
            "vantage_points": survey.vantage_points,
            "hazards": survey.hazards,
            "recommended_exit": survey.recommended_exit,
            "summary": survey.summary,
            "image_paths": survey.image_paths,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        log.info("Survey saved: %s", path)

    def _load_existing(self):
        """Load previously saved surveys."""
        import glob
        for path in glob.glob(os.path.join(self.survey_dir, "area_*.json")):
            try:
                with open(path) as f:
                    data = json.load(f)
                survey = RoomSurvey(
                    area_id=data["area_id"],
                    position=tuple(data["position"]),
                    yaw_at_survey=data["yaw_at_survey"],
                    timestamp=data["timestamp"],
                    room_type=data.get("room_type", ""),
                    exits=data.get("exits", []),
                    items=data.get("items", []),
                    vantage_points=data.get("vantage_points", []),
                    hazards=data.get("hazards", []),
                    recommended_exit=data.get("recommended_exit", ""),
                    summary=data.get("summary", ""),
                    image_paths=data.get("image_paths", {}),
                )
                self._surveys[survey.area_id] = survey
            except Exception as e:
                log.warning("Failed to load survey %s: %s", path, e)

        if self._surveys:
            log.info("Loaded %d existing room surveys", len(self._surveys))

    @property
    def survey_count(self) -> int:
        return self._survey_count

    @property
    def total_surveys(self) -> int:
        return len(self._surveys)
