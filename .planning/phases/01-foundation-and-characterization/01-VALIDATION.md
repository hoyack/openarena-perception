---
phase: 1
slug: foundation-and-characterization
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-08
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

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
| 1-01-01 | 01 | 0 | FOUND-05 | infra | `uv run pytest --version` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 0 | FOUND-06 | infra | `uv run ruff check .` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | FOUND-01 | unit | `test -d openarena_perception/perception` | ❌ W0 | ⬜ pending |
| 1-03-01 | 03 | 1 | FOUND-03 | unit | `uv run pytest tests/test_config.py -v` | ❌ W0 | ⬜ pending |
| 1-04-01 | 04 | 1 | FOUND-04 | unit | `uv run pytest tests/test_logging.py -v` | ❌ W0 | ⬜ pending |
| 1-05-01 | 05 | 1 | FOUND-08 | unit | `uv run pytest tests/test_awareness.py -v` | ❌ W0 | ⬜ pending |
| 1-06-01 | 06 | 2 | FOUND-07 | integration | `uv run pytest tests/test_strategic_brain_characterization.py -v` | ❌ W0 | ⬜ pending |
| 1-07-01 | 07 | 2 | FOUND-02 | unit | `test ! -f config.py` (root duplicate removed) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/` directory created
- [ ] `tests/conftest.py` — shared fixtures
- [ ] `pytest` added as dev dependency via `uv add --dev pytest`
- [ ] `ruff` added as dev dependency via `uv add --dev ruff`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Structured JSON logs visible | FOUND-04 | Requires running bot to produce logs | Run `uv run python -c "from openarena_perception.brainstem.logging import get_logger; log = get_logger('test'); log.info('hello')"` and verify JSON output |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
