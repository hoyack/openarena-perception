"""Unit tests for LLM Strategy (STRT-01/02/03).

Tests StrategyDecision Pydantic validation, action normalization,
LLMStrategyBrain fallback decisions, state text, and mocked Ollama calls.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from openarena_perception.strategy.models import StrategyAction, StrategyDecision


# ===========================================================================
# StrategyDecision Pydantic validation (STRT-03)
# ===========================================================================

class TestStrategyDecision:
    """StrategyDecision validates and normalizes LLM outputs."""

    def test_valid_hunt_action(self):
        d = StrategyDecision(action="HUNT", reasoning="test")
        assert d.action == StrategyAction.HUNT
        assert d.reasoning == "test"

    def test_valid_defend_action(self):
        d = StrategyDecision(action="DEFEND", reasoning="holding")
        assert d.action == StrategyAction.DEFEND

    def test_valid_retreat_action(self):
        d = StrategyDecision(action="RETREAT", reasoning="low hp")
        assert d.action == StrategyAction.RETREAT

    def test_valid_explore_action(self):
        d = StrategyDecision(action="EXPLORE", reasoning="looking around")
        assert d.action == StrategyAction.EXPLORE

    def test_invalid_action_raises(self):
        with pytest.raises(ValidationError):
            StrategyDecision(action="INVALID", reasoning="bad")

    def test_alias_camp_normalizes_to_defend(self):
        d = StrategyDecision(action="CAMP", reasoning="camping")
        assert d.action == StrategyAction.DEFEND

    def test_alias_ambush_normalizes_to_defend(self):
        d = StrategyDecision(action="AMBUSH", reasoning="ambushing")
        assert d.action == StrategyAction.DEFEND

    def test_alias_grab_item_normalizes_to_explore(self):
        d = StrategyDecision(action="GRAB_ITEM", reasoning="getting item")
        assert d.action == StrategyAction.EXPLORE

    def test_case_insensitive(self):
        d = StrategyDecision(action="hunt", reasoning="test")
        assert d.action == StrategyAction.HUNT

    def test_optional_fields_default(self):
        d = StrategyDecision(action="HUNT")
        assert d.weapon is None
        assert d.target_item is None
        assert d.reasoning == ""

    def test_model_validate_json(self):
        raw = '{"action": "HUNT", "weapon": "rocket", "reasoning": "engaging"}'
        d = StrategyDecision.model_validate_json(raw)
        assert d.action == StrategyAction.HUNT
        assert d.weapon == "rocket"


# ===========================================================================
# LLMStrategyBrain fallback and state text (STRT-01/02)
# ===========================================================================

class TestLLMStrategyBrainFallback:
    """_fallback_decision returns correct decision based on SA."""

    def _make_brain(self):
        """Create LLMStrategyBrain with ollama import mocked out."""
        with patch.dict("sys.modules", {"ollama": MagicMock()}):
            from openarena_perception.strategy.llm_brain import LLMStrategyBrain
            return LLMStrategyBrain()

    def test_fallback_retreat_critical_health(self, make_awareness):
        brain = self._make_brain()
        sa = make_awareness(health=20)
        result = brain._fallback_decision(sa)
        assert result.action == StrategyAction.RETREAT

    def test_fallback_hunt_enemies_visible(self, make_awareness):
        brain = self._make_brain()
        sa = make_awareness(health=100, enemies_visible=2)
        result = brain._fallback_decision(sa)
        assert result.action == StrategyAction.HUNT

    def test_fallback_explore_default(self, make_awareness):
        brain = self._make_brain()
        sa = make_awareness(health=100, enemies_visible=0)
        result = brain._fallback_decision(sa)
        assert result.action == StrategyAction.EXPLORE


class TestBuildStateText:
    """_build_state_text includes key SA fields."""

    def _make_brain(self):
        with patch.dict("sys.modules", {"ollama": MagicMock()}):
            from openarena_perception.strategy.llm_brain import LLMStrategyBrain
            return LLMStrategyBrain()

    def test_includes_health(self, make_awareness):
        brain = self._make_brain()
        sa = make_awareness(health=75)
        text = brain._build_state_text(sa)
        assert "75" in text

    def test_includes_weapon(self, make_awareness):
        brain = self._make_brain()
        sa = make_awareness(weapon="railgun")
        text = brain._build_state_text(sa)
        assert "railgun" in text

    def test_includes_position(self, make_awareness):
        brain = self._make_brain()
        sa = make_awareness(pos=(500.0, 600.0, 0.0))
        text = brain._build_state_text(sa)
        assert "500" in text
        assert "600" in text

    def test_includes_enemies(self, make_awareness):
        brain = self._make_brain()
        sa = make_awareness(enemies_visible=3)
        text = brain._build_state_text(sa)
        assert "3" in text


# ===========================================================================
# LLMStrategyBrain.decide() with mocked Ollama (STRT-01)
# ===========================================================================

class TestLLMDecide:
    """decide() with mocked AsyncClient."""

    def test_decide_returns_validated_decision(self, make_awareness):
        """Mocked Ollama returns valid JSON -> StrategyDecision."""
        mock_ollama = MagicMock()
        mock_client = AsyncMock()
        mock_ollama.AsyncClient.return_value = mock_client

        valid_json = json.dumps({
            "action": "HUNT",
            "weapon": "rocket",
            "reasoning": "enemy spotted"
        })
        mock_client.chat.return_value = {
            "message": {"content": valid_json}
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            from openarena_perception.strategy.llm_brain import LLMStrategyBrain
            brain = LLMStrategyBrain()

        sa = make_awareness(health=100, enemies_visible=1)
        result = asyncio.run(brain.decide(sa))
        assert isinstance(result, StrategyDecision)
        assert result.action == StrategyAction.HUNT
        assert result.weapon == "rocket"

    def test_decide_malformed_json_returns_fallback(self, make_awareness):
        """Mocked Ollama returns garbage -> fallback decision (no crash)."""
        mock_ollama = MagicMock()
        mock_client = AsyncMock()
        mock_ollama.AsyncClient.return_value = mock_client

        mock_client.chat.return_value = {
            "message": {"content": "this is not json at all"}
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            from openarena_perception.strategy.llm_brain import LLMStrategyBrain
            brain = LLMStrategyBrain()

        sa = make_awareness(health=100, enemies_visible=0)
        result = asyncio.run(brain.decide(sa))
        assert isinstance(result, StrategyDecision)
        # Fallback: healthy + no enemies -> EXPLORE
        assert result.action == StrategyAction.EXPLORE

    def test_decide_with_markdown_fences(self, make_awareness):
        """Mocked Ollama wraps JSON in markdown fences -> still parses."""
        mock_ollama = MagicMock()
        mock_client = AsyncMock()
        mock_ollama.AsyncClient.return_value = mock_client

        valid_json = json.dumps({
            "action": "DEFEND",
            "reasoning": "holding position"
        })
        fenced = f"```json\n{valid_json}\n```"
        mock_client.chat.return_value = {
            "message": {"content": fenced}
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            from openarena_perception.strategy.llm_brain import LLMStrategyBrain
            brain = LLMStrategyBrain()

        sa = make_awareness()
        result = asyncio.run(brain.decide(sa))
        assert isinstance(result, StrategyDecision)
        assert result.action == StrategyAction.DEFEND
