"""Tests for pydantic-settings configuration (FOUND-03)."""
import os
from unittest.mock import patch
import pytest
from openarena_perception.settings import BotSettings, get_settings


class TestBotSettings:
    def test_defaults(self):
        s = BotSettings()
        assert s.screen_w == 800
        assert s.screen_h == 600
        assert s.pipe_path == "/tmp/openarena_pipe"
        assert s.rcon_port == 27960
        assert s.target_fps == 15
        assert s.tick_budget_ms == 50

    def test_env_prefix(self):
        with patch.dict(os.environ, {"OA_SCREEN_W": "1920"}):
            s = BotSettings()
            assert s.screen_w == 1920

    def test_env_override_bool(self):
        with patch.dict(os.environ, {"OA_LLM_ENABLED": "false"}):
            s = BotSettings()
            assert s.llm_enabled is False

    def test_singleton_returns_same_instance(self):
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
        get_settings.cache_clear()
