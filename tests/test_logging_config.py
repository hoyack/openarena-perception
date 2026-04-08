"""Tests for structlog configuration (FOUND-04)."""
import io
import logging
import pytest
from openarena_perception.logging_config import configure_logging, get_logger


class TestLoggingConfig:
    def setup_method(self):
        configure_logging(json_output=True, level="DEBUG")

    def test_configure_does_not_raise(self):
        configure_logging(json_output=True)

    def test_json_output(self):
        # Attach a StringIO handler to capture log output directly,
        # bypassing pytest's log capture which intercepts StreamHandler.
        import structlog
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(logging.getLogger().handlers[0].formatter)
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            log = get_logger("test_subsystem")
            log.info("hello_world")
            output = buf.getvalue()
            assert "hello_world" in output
            assert "test_subsystem" in output
        finally:
            root.removeHandler(handler)

    def test_subsystem_binding(self):
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setFormatter(logging.getLogger().handlers[0].formatter)
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            log = get_logger("combat")
            log.info("target_acquired", distance=42)
            output = buf.getvalue()
            assert "combat" in output
            assert "target_acquired" in output
        finally:
            root.removeHandler(handler)

    def test_console_renderer_does_not_raise(self):
        configure_logging(json_output=False)
        log = get_logger("dev")
        log.info("dev_mode")
