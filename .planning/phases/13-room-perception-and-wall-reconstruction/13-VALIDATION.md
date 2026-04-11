---
phase: 13
slug: room-perception-and-wall-reconstruction
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-11
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (+ pytest-asyncio, pytest-cov, hypothesis per pyproject) |
| **Config file** | `pyproject.toml` (dev deps group) |
| **Quick run command** | `uv run pytest tests/test_room_perception.py tests/test_learned_map.py -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | quick ~3-5s, full ~35-40s on desktop |

---

## Sampling Rate

- **After every task commit:** Run quick command (Room Perception + learned_map tests only)
- **After every plan wave:** Run full suite
- **Before `/gsd-verify-work`:** Full suite must be green, 743 Phase 12.1 tests must stay green
- **Max feedback latency:** 5 seconds per task commit, 40 seconds per wave

---

## Per-Task Verification Map

The planner will produce the actual task IDs. The mapping below is from RESEARCH.md's test-to-requirement matrix and should be propagated into each plan's `<automated>` verify block.

| Requirement | Coverage | Test File | Command | Status |
|-------------|----------|-----------|---------|--------|
| RP-01 | Per-tick raycast append | `tests/test_learned_map.py::test_raycast_capture_appends` | `uv run pytest tests/test_learned_map.py::test_raycast_capture_appends -x` | ❌ Wave 0 |
| RP-02 | Point cloud cap + decimation | `tests/test_learned_map.py::test_raycast_decimation` | `uv run pytest tests/test_learned_map.py::test_raycast_decimation -x` | ❌ Wave 0 |
| RP-03 | RANSAC 4-wall rectangle | `tests/test_room_perception.py::test_ransac_four_wall_rectangle` | `uv run pytest tests/test_room_perception.py::test_ransac_four_wall_rectangle -x` | ❌ Wave 0 |
| RP-04 | Fit cadence gating (fake clock) | `tests/test_room_perception.py::test_fit_cadence` | `uv run pytest tests/test_room_perception.py::test_fit_cadence -x` | ❌ Wave 0 |
| RP-05 | Wall merge preserves support | `tests/test_room_perception.py::test_wall_merge` | `uv run pytest tests/test_room_perception.py::test_wall_merge -x` | ❌ Wave 0 |
| RP-06 | Corner from two walls | `tests/test_room_perception.py::test_corner_from_two_walls` | `uv run pytest tests/test_room_perception.py::test_corner_from_two_walls -x` | ❌ Wave 0 |
| RP-07 | Room from closed square cycle | `tests/test_room_perception.py::test_room_from_square` | `uv run pytest tests/test_room_perception.py::test_room_from_square -x` | ❌ Wave 0 |
| RP-08 | PartialRoom + doorway | `tests/test_room_perception.py::test_partial_room_and_doorway` | `uv run pytest tests/test_room_perception.py::test_partial_room_and_doorway -x` | ❌ Wave 0 |
| RP-09 | items_seen ingestion via PIP | `tests/test_room_perception.py::test_item_ingestion_pip` | `uv run pytest tests/test_room_perception.py::test_item_ingestion_pip -x` | ❌ Wave 0 |
| RP-10 | Schema v2→v3 round trip | `tests/test_learned_map.py::test_schema_v3_roundtrip` | `uv run pytest tests/test_learned_map.py::test_schema_v3_roundtrip -x` | ❌ Wave 0 |
| RP-11 | Minimap backward-compat + new render | `tests/test_open_perception_panels.py::test_minimap_new_schema_fitted_walls` + `test_minimap_legacy_empty_walls` | `SDL_VIDEODRIVER=dummy uv run pytest tests/test_open_perception_panels.py -x` | ✅ exists, ADD cases |
| RP-12 | hud_schema backward-compat kwargs | `tests/test_hud_schema.py::test_current_room_kwargs_backward_compat` | `uv run pytest tests/test_hud_schema.py -x` | ✅ exists, ADD cases |

*Status: ⬜ pending · ✅ exists · ❌ Wave 0 (needs creation)*

---

## Wave 0 Requirements

Wave 0 sets up test infrastructure BEFORE any implementation tasks run. The planner must include a Wave 0 plan (or plan-01 wave-0 tasks) covering:

- [ ] `tests/test_room_perception.py` — CREATE (covers RP-03..RP-09, plus RP-05 merge)
- [ ] `tests/test_learned_map.py` — CREATE (covers RP-01, RP-02, RP-10; file does not currently exist per `ls tests/`)
- [ ] `tests/test_hud_schema.py` — already exists (extend with RP-12 backward-compat case)
- [ ] `tests/test_open_perception_panels.py` — already exists (extend with RP-11 new-schema + legacy fallback cases)
- [ ] Shared conftest for synthetic point cloud fixtures (4-wall rectangle, 3-wall U-shape, noisy clusters) — can live in `tests/conftest.py` or a phase-specific fixture module

Framework is already installed (pytest 8.x, pytest-asyncio, hypothesis) — no install step needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Fitted walls replace red stubs on live oa_dm1 tour | RP-11 | Visual correctness of RANSAC output on real perception data | Run `item_tour.py --no-vision` + `open_perception.py`, walk a tour, confirm minimap shows clean fitted green walls instead of red stubs |
| Room polygon outlines match real oa_dm1 architecture | RP-07 | Needs human judgment on whether inferred polygons correspond to meaningful rooms | After a full tour completes, inspect the minimap for closed polygon outlines and compare mentally to the known oa_dm1 layout |
| Current-room highlight follows the bot | RP-09 | Visual test of PIP correctness at 10 FPS | During a live tour, watch whether the brighter-outlined polygon is the one the bot is actually inside |

Live bot visual verification is expected as a human-verify checkpoint in the final plan, same pattern as Phase 12 and 12.1.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies — **enforced by planner**
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify — **enforced by planner**
- [ ] Wave 0 creates `tests/test_room_perception.py` and `tests/test_learned_map.py` before implementation tasks can claim their requirements
- [ ] No watch-mode flags (pytest runs headless)
- [ ] Feedback latency < 5s per task commit, < 40s per wave
- [ ] `nyquist_compliant: true` set in frontmatter after planner verification

**Approval:** APPROVED (planner iteration 2, 2026-04-11) — every implementation task has an `<automated>` verify, ruff/mypy gate added to Plan 13-06, perf benchmark added to Plan 13-05, OR'd cadence trigger test added to Plan 13-03.
