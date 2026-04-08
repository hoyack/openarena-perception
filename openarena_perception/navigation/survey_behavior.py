"""
survey_behavior.py — Room survey state behavior handler.

Extracted from strategic_brain.py: _tick_surveying logic.
Performs a 360-degree room survey on area entry, storing results
in SpatialKnowledge.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

from .room_surveyor import RoomSurveyor

if TYPE_CHECKING:
    from openarena_perception.models import SpatialKnowledge

log = logging.getLogger(__name__)


class SurveyBehavior:
    """Survey behavior handler extracted from strategic_brain.py.

    Manages the SURVEYING state tick: performs a single room survey
    per state entry, then sets a cooldown to prevent re-surveying.
    """

    def __init__(
        self,
        surveyor: RoomSurveyor,
        spatial: "SpatialKnowledge",
    ):
        self.surveyor = surveyor
        self.spatial = spatial

    async def tick(self, sa, gs, state_time: float) -> Optional[float]:
        """Execute survey behavior.

        Extracted from strategic_brain.py lines 475-492.
        Only surveys once per entry (state_time < 0.5).

        Args:
            sa: SituationalAwareness snapshot
            gs: GameState with current frame
            state_time: seconds since entering SURVEYING state

        Returns:
            Survey cooldown timestamp if survey was performed, else None.
        """
        # Only survey once per entry
        if state_time < 0.5 and self.surveyor and sa.pos:
            def capture():
                return gs.frame

            survey = self.surveyor.perform_survey(
                area_id=sa.current_area, pos=sa.pos,
                start_yaw=sa.yaw, capture_fn=capture,
            )
            if survey:
                self.spatial.store_survey(survey)
                log.info("SURVEY: %s | exits=%d | recommended=%s",
                         survey.room_type, len(survey.exits),
                         survey.recommended_exit)
            return time.time() + 45.0

        return None
