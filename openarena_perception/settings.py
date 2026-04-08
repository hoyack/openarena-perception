"""Central configuration -- env vars > .env > TOML priority chain."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


class BotSettings(BaseSettings):
    """Central configuration -- env vars override .env override TOML."""

    model_config = SettingsConfigDict(
        env_prefix="OA_",
        env_file=".env",
        env_file_encoding="utf-8",
        toml_file="bot.toml",
        extra="ignore",
    )

    # Display
    screen_w: int = 800
    screen_h: int = 600

    # Game connection
    pipe_path: str = "/tmp/openarena_pipe"
    rcon_password: str = ""
    rcon_port: int = 27960

    # Perception
    enemy_color_mode: str = "red"
    ocr_upscale: int = 3
    enemy_min_area: int = 200

    # LLM
    ollama_model: str = "gemma3:4b"
    ollama_base_url: str = "http://localhost:11434"
    llm_enabled: bool = True

    # Navigation
    map_name: str = "dm4ish"
    aas_dir: str = "maps"

    # Performance
    tick_budget_ms: int = 50
    target_fps: int = 15

    # Logging
    log_json: bool = True
    log_level: str = "INFO"

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings,
                                    env_settings, dotenv_settings,
                                    file_secret_settings):
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
        )


@lru_cache
def get_settings() -> BotSettings:
    """Singleton settings instance. Import this everywhere."""
    return BotSettings()
