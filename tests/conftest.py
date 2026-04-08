"""Shared test fixtures for openarena-perception."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_navigator():
    """A mocked Navigator with sensible defaults."""
    nav = MagicMock()
    nav.graph = MagicMock()
    nav.has_path = True
    nav._path = [1, 2, 3]
    nav.pos = (100.0, 200.0, 0.0)
    nav.yaw = 90.0
    nav.current_area = 5
    nav.is_stuck = False
    nav.is_recovering = False
    return nav


@pytest.fixture
def mock_bridge():
    """A mocked GameBridge."""
    return MagicMock()


@pytest.fixture
def mock_commander():
    """A mocked Commander that does not trigger decisions."""
    cmd = MagicMock()
    cmd.should_decide.return_value = False
    return cmd


@pytest.fixture
def mock_perception():
    """A mocked Perception module."""
    return MagicMock()


@pytest.fixture
def mock_damage_tracker():
    """A mocked DamageTracker."""
    return MagicMock()


@pytest.fixture
def mock_ctrl():
    """A mocked VirtualController."""
    return MagicMock()
