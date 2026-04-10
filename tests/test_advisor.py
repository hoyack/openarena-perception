"""Unit tests for the spatial advisor."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from openarena_perception.strategy.advisor import (
    SpatialAdvisor,
    TrailPoint,
    Warning,
)
from openarena_perception.strategy.advisor_prompts import (
    build_trail_summary,
    describe_goal,
)


def _make_advisor():
    return SpatialAdvisor(dispatch_interval=2.5, timeout=6.0, trail_maxlen=10)


def _frame():
    return np.zeros((600, 800, 3), dtype=np.uint8)


class TestTrailBuffer:
    def test_maxlen_respected(self):
        adv = SpatialAdvisor(trail_maxlen=5)
        for i in range(10):
            adv.record_trail((float(i), 0, 0), 0, i)
        assert len(adv._trail) == 5
        # Should contain the LAST 5 points (5..9)
        assert adv._trail[0].x == 5.0
        assert adv._trail[-1].x == 9.0

    def test_none_pos_ignored(self):
        adv = _make_advisor()
        adv.record_trail(None, 0, 0)
        assert len(adv._trail) == 0


class TestStalenessDetection:
    def test_not_stale_when_close(self):
        adv = _make_advisor()
        adv.record_trail((100, 100, 50), 0, 1)

        from openarena_perception.strategy.advisor import ThoughtSnapshot
        snap = ThoughtSnapshot(
            id="t1", sent_at=time.time() - 1.0,
            sent_pos=(90, 100, 50), sent_yaw=0, sent_area=1,
            goal_desc="test",
        )
        assert not adv._is_stale(snap)

    def test_stale_when_moved_far(self):
        adv = _make_advisor()
        adv.record_trail((500, 500, 50), 0, 1)

        from openarena_perception.strategy.advisor import ThoughtSnapshot
        snap = ThoughtSnapshot(
            id="t1", sent_at=time.time() - 1.0,
            sent_pos=(100, 100, 50), sent_yaw=0, sent_area=1,
            goal_desc="test",
        )
        assert adv._is_stale(snap)  # ~565 units moved

    def test_stale_when_old(self):
        adv = _make_advisor()
        adv.record_trail((100, 100, 50), 0, 1)

        from openarena_perception.strategy.advisor import ThoughtSnapshot
        snap = ThoughtSnapshot(
            id="t1", sent_at=time.time() - 20.0,  # 20s ago
            sent_pos=(100, 100, 50), sent_yaw=0, sent_area=1,
            goal_desc="test",
        )
        assert adv._is_stale(snap)

    def test_stale_when_vertical_change(self):
        adv = _make_advisor()
        adv.record_trail((100, 100, 200), 0, 1)  # 150 higher

        from openarena_perception.strategy.advisor import ThoughtSnapshot
        snap = ThoughtSnapshot(
            id="t1", sent_at=time.time(),
            sent_pos=(100, 100, 50), sent_yaw=0, sent_area=1,
            goal_desc="test",
        )
        assert adv._is_stale(snap)


class TestDispatchThrottle:
    def test_no_dispatch_without_trail(self):
        adv = _make_advisor()
        # No trail recorded yet
        assert not adv.maybe_dispatch(_frame())

    def test_no_dispatch_without_ollama(self):
        adv = _make_advisor()
        adv._ollama_mod = None  # force disabled
        adv.record_trail((100, 100, 50), 0, 1)
        assert not adv.maybe_dispatch(_frame())

    def test_no_dispatch_none_frame(self):
        adv = _make_advisor()
        adv.record_trail((100, 100, 50), 0, 1)
        assert not adv.maybe_dispatch(None)


class TestRequestDiagnosis:
    def test_sets_problem_note(self):
        adv = _make_advisor()
        adv._ollama_mod = None  # disabled, so no real dispatch
        adv.record_trail((100, 100, 50), 0, 1)
        adv.request_diagnosis(_frame(), "stuck 2x at area 42")
        assert "stuck 2x at area 42" in adv._last_problem

    def test_bypasses_interval_throttle(self):
        """Even if we just dispatched, force=True should allow a new dispatch."""
        import asyncio

        async def run():
            adv = _make_advisor()
            # Mock ollama so maybe_dispatch actually spawns a task
            adv._ollama_mod = MagicMock()
            mock_client = MagicMock()

            async def fake_chat(**kwargs):
                return {"message": {"content": '{"narrative":"x","hazards":[],"action_hint":"stop","confidence":0.5}'}}

            mock_client.chat = fake_chat
            adv._client = mock_client
            adv.record_trail((100, 100, 50), 0, 1)

            # First dispatch via maybe_dispatch succeeds
            assert adv.maybe_dispatch(_frame())
            # Wait for it to finish so the pending-task guard releases
            await adv._pending_task
            # Normal maybe_dispatch would be throttled (interval not elapsed)
            assert not adv.maybe_dispatch(_frame())
            # But request_diagnosis forces through
            assert adv.request_diagnosis(_frame(), "stuck test")
            await adv._pending_task
            assert adv.thoughts_sent == 2

        asyncio.run(run())

    def test_blocked_by_pending_task(self):
        """Even forced, a thought in-flight blocks new dispatch."""
        import asyncio

        async def run():
            adv = _make_advisor()
            adv._ollama_mod = MagicMock()
            mock_client = MagicMock()

            async def slow_chat(**kwargs):
                await asyncio.sleep(0.2)
                return {"message": {"content": '{"narrative":"x","hazards":[],"action_hint":"stop","confidence":0.5}'}}

            mock_client.chat = slow_chat
            adv._client = mock_client
            adv.record_trail((100, 100, 50), 0, 1)

            assert adv.maybe_dispatch(_frame())
            # Task is in flight — force should not start another one
            assert not adv.request_diagnosis(_frame(), "stuck test")
            await adv._pending_task

        asyncio.run(run())


class TestApplyResponse:
    def test_narrative_and_warnings_populated(self):
        adv = _make_advisor()
        adv.record_trail((100, 100, 50), 0, 1)

        from openarena_perception.strategy.advisor import ThoughtSnapshot
        snap = ThoughtSnapshot(
            id="t1", sent_at=time.time(),
            sent_pos=(100, 100, 50), sent_yaw=0, sent_area=1,
            goal_desc="test",
        )
        parsed = {
            "narrative": "A stone corridor with lava ahead",
            "hazards": [
                {"kind": "lava", "direction": "ahead",
                 "severity": "high", "text": "lava pool 2m ahead"}
            ],
            "action_hint": "back_away",
            "confidence": 0.9,
        }
        adv._apply_response(parsed, snap)

        assert "stone corridor" in adv.current_narrative()
        warnings = adv.current_warnings()
        assert len(warnings) == 1
        assert warnings[0].kind == "lava"
        assert warnings[0].severity == "high"
        assert adv.is_hazard_ahead() is True
        assert adv.get_recommended_action() == "back_away"

    def test_filters_none_kind_hazards(self):
        adv = _make_advisor()
        adv.record_trail((100, 100, 50), 0, 1)

        from openarena_perception.strategy.advisor import ThoughtSnapshot
        snap = ThoughtSnapshot(
            id="t1", sent_at=time.time(),
            sent_pos=(100, 100, 50), sent_yaw=0, sent_area=1,
            goal_desc="test",
        )
        parsed = {
            "narrative": "open area",
            "hazards": [{"kind": "none"}],
            "action_hint": "walk_forward",
            "confidence": 0.8,
        }
        adv._apply_response(parsed, snap)
        assert len(adv.current_warnings()) == 0
        assert not adv.is_hazard_ahead()


class TestWarningFreshness:
    def test_old_warnings_pruned(self):
        adv = _make_advisor()
        adv.record_trail((100, 100, 50), 0, 1)

        # Inject an old warning
        old_warning = Warning(
            kind="lava", direction="ahead", severity="high",
            text="old", recorded_at=time.time() - 10.0,
            recorded_pos=(100, 100, 50),
        )
        adv._warnings = [old_warning]
        assert adv.current_warnings() == []

    def test_warnings_pruned_when_bot_moved_far(self):
        adv = _make_advisor()
        adv.record_trail((600, 600, 50), 0, 1)  # bot is now far away

        old_warning = Warning(
            kind="lava", direction="ahead", severity="high",
            text="lava here", recorded_at=time.time() - 1.0,
            recorded_pos=(100, 100, 50),
        )
        adv._warnings = [old_warning]
        assert adv.current_warnings() == []


class TestHelpers:
    def test_build_trail_summary_empty(self):
        assert build_trail_summary([]) == "no trail"

    def test_build_trail_summary_movement(self):
        trail = [
            TrailPoint(t=1.0, x=0, y=0, z=0, yaw=0, area=1),
            TrailPoint(t=1.1, x=50, y=50, z=0, yaw=0, area=1),
            TrailPoint(t=1.2, x=100, y=100, z=0, yaw=0, area=2),
        ]
        summary = build_trail_summary(trail)
        assert "1" in summary  # area 1
        assert "2" in summary  # area 2

    def test_describe_goal_with_direction(self):
        desc = describe_goal((100, 100, 50), (500, 100, 50), "rocket_launcher")
        assert "rocket_launcher" in desc
        assert "400" in desc  # distance
        assert "E" in desc  # east direction

    def test_describe_goal_height_note(self):
        desc = describe_goal((100, 100, 50), (200, 100, 200), "mega_health")
        assert "UP" in desc


class TestStats:
    def test_initial_stats_zero(self):
        adv = _make_advisor()
        s = adv.stats()
        assert s["sent"] == 0
        assert s["complete"] == 0
        assert s["stale"] == 0
        assert s["failed"] == 0
        assert s["pending"] == 0

    def test_shutdown_logs_stats(self):
        adv = _make_advisor()
        adv.shutdown()  # should not raise
