"""Tests for openarena_perception.hud_schema (Phase 10-01)."""
from __future__ import annotations

import json
from collections import deque

import pytest

from openarena_perception import hud_schema
from openarena_perception.hud_schema import (
    LOG_DIR,
    PROJECT_ROOT,
    STATE_FILE,
    TMP_DIR,
    build_hud_payload,
    ensure_runtime_dirs,
    write_hud_state,
)


def test_state_file_is_anchored_to_project_root():
    """STATE_FILE must resolve under PROJECT_ROOT/tmp/, not /tmp/ and not cwd."""
    assert STATE_FILE == PROJECT_ROOT / "tmp" / "oa_hud_state.json"
    # Prove it is NOT the old absolute path
    assert str(STATE_FILE) != "/tmp/oa_hud_state.json"
    # Project root is <repo>/, this file lives in <repo>/openarena_perception/
    assert (PROJECT_ROOT / "openarena_perception" / "hud_schema.py").is_file()


def test_tmp_and_log_dirs_anchored():
    assert TMP_DIR == PROJECT_ROOT / "tmp"
    assert LOG_DIR == PROJECT_ROOT / "logs"


def test_ensure_runtime_dirs_creates_missing_dirs(tmp_path, monkeypatch):
    fake_tmp = tmp_path / "tmp"
    fake_log = tmp_path / "logs"
    monkeypatch.setattr(hud_schema, "TMP_DIR", fake_tmp)
    monkeypatch.setattr(hud_schema, "LOG_DIR", fake_log)
    assert not fake_tmp.exists()
    assert not fake_log.exists()
    ensure_runtime_dirs()
    assert fake_tmp.is_dir()
    assert fake_log.is_dir()
    # Idempotent
    ensure_runtime_dirs()
    assert fake_tmp.is_dir()


def test_build_payload_minimal_has_timestamp_and_map():
    p = build_hud_payload(map_name="q3dm17")
    assert "timestamp" in p
    assert isinstance(p["timestamp"], float)
    assert p["map_name"] == "q3dm17"


def test_build_payload_with_sa_like_object():
    class FakeSA:
        health = 100
        armor = 50
        ammo = 40
        weapon = "rocket"
        pos = (1.0, 2.0, 3.0)
        yaw = 90.0

    p = build_hud_payload(sa=FakeSA(), map_name="q3dm1")
    assert p["health"] == 100
    assert p["armor"] == 50
    assert p["ammo"] == 40
    assert p["weapon"] == "rocket"
    assert p["pos"] == [1.0, 2.0, 3.0]   # list, not tuple
    assert p["yaw"] == 90.0


def test_build_payload_extras_override_and_merge():
    p = build_hud_payload(
        map_name="q3dm1",
        extras={"route_idx": 5, "route_len": 13, "proactive_halts": 2},
    )
    assert p["route_idx"] == 5
    assert p["route_len"] == 13
    assert p["proactive_halts"] == 2


def test_build_payload_deque_must_be_converted_by_caller(tmp_path):
    """Pitfall 7: deques are not JSON serializable. The caller must convert.
    build_hud_payload does not auto-convert -- it trusts the caller. This test
    documents the contract: a raw deque in extras will fail json.dump."""
    p = build_hud_payload(map_name="x", extras={"history": deque([1, 2, 3])})
    # The payload holds the deque verbatim
    assert isinstance(p["history"], deque)
    # And json.dump blows up on it -- proving the contract
    out = tmp_path / "x.json"
    with pytest.raises(TypeError):
        with open(out, "w") as f:
            json.dump(p, f)


def test_write_hud_state_atomic(tmp_path):
    """write_hud_state uses tmp + os.replace; no .tmp left behind on success."""
    target = tmp_path / "out.json"
    write_hud_state({"hello": "world"}, state_file=target)
    assert target.is_file()
    assert json.loads(target.read_text()) == {"hello": "world"}
    assert not (tmp_path / "out.json.tmp").exists()


def test_write_hud_state_creates_parent_dir(tmp_path):
    target = tmp_path / "sub" / "dir" / "out.json"
    assert not target.parent.exists()
    write_hud_state({"k": 1}, state_file=target)
    assert target.is_file()
