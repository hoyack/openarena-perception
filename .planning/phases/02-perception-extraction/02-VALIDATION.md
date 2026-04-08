---
phase: 2
slug: perception-extraction
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-08
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 1 | PERC-02,03,04,05 | unit | `uv run python -c "from openarena_perception.perception.world_parser import WorldParser"` | ❌ W0 | ⬜ pending |
| 2-01-02 | 01 | 1 | PERC-06,07 | unit | `uv run python -c "from openarena_perception.perception.object_tracker import ObjectTracker"` | ❌ W0 | ⬜ pending |
| 2-02-01 | 02 | 2 | PERC-01 | unit | `uv run python -c "from openarena_perception.perception.pipeline import PerceptionPipeline"` | ❌ W0 | ⬜ pending |
| 2-02-02 | 02 | 2 | PERC-01 | unit | `uv run pytest tests/test_perception_pipeline.py -v` | ❌ W0 | ⬜ pending |
| 2-03-01 | 03 | 3 | PERC-01-07 | integration | `uv run pytest tests/test_perception_pipeline.py -v` | ❌ W0 | ⬜ pending |
| 2-03-02 | 03 | 3 | ALL | regression | `uv run pytest tests/ -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_perception_pipeline.py` — stubs for PERC-01 through PERC-07
- [ ] Phase 1 test infrastructure already exists (conftest.py, pytest config)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 15+ FPS on Pi 5 | PERC-01 | Requires running game with screen capture | Run `uv run python -c "from openarena_perception.perception.pipeline import PerceptionPipeline; ..."` with OpenArena running, measure tick rate over 100 frames |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
