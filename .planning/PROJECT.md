# OpenArena Perception — AI Bot Framework

## What This Is

A brain-inspired AI bot management framework for FPS games (currently OpenArena/ioquake3) that combines real-time computer vision, machine learning, LLM strategic reasoning, and legacy Quake 3 navigation (AAS files) into an organized, testable, API-driven system. The framework runs on Raspberry Pi 4/5 hardware and provides a layered skill system where atomic actions compose into behaviors, behaviors compose into missions — all controllable by LLM agents via a FastAPI backend.

## Core Value

The bot must be a competitive deathmatch player — able to perceive enemies, navigate maps, select weapons, aim accurately, and make strategic decisions in real-time on constrained Pi hardware.

## Requirements

### Validated

- ✓ Screen capture via mss at 10-22 FPS on Pi — existing
- ✓ HUD parsing via Tesseract OCR (health, armor, ammo, weapon, frags, deaths) — existing
- ✓ Enemy detection via HSV color thresholding with bounding boxes — existing
- ✓ AAS navigation mesh parsing (areas, reachability, A* pathfinding) — existing
- ✓ Game bridge via named pipe + RCON UDP — existing
- ✓ Fuzzy weapon selection based on distance/ammo/range — existing
- ✓ PID-based aim controller with lead prediction — existing
- ✓ Motion detection via frame differencing + optical flow — existing
- ✓ 360-degree room surveys with LLM spatial documentation — existing
- ✓ FSM-based strategic brain (DEAD/COMBAT/STUCK/SURVEYING/NAVIGATING/EXPLORING) — existing
- ✓ LLM integration via Ollama for strategic decisions — existing
- ✓ Learned map with occupancy grid and edge cost tracking — existing
- ✓ Stuck recovery via scan-and-probe exit finding — existing
- ✓ Virtual controller with pipe-only turns (no desktop mouse) — existing
- ✓ Multi-object tracking with color histograms + templates — existing

### Active

- [ ] Brain-inspired code architecture with organized subsystems
- [ ] FastAPI backend for LLM agent control
- [ ] Three-layer skill system (actions → behaviors → missions)
- [ ] Comprehensive test suite (perception, navigation, combat, integration)
- [ ] Tour testing with metrics (stuck count, completion time, visual verification)
- [ ] Combat system scaffolding (target acquisition, engagement, damage dealing)
- [ ] Full documentation site with system diagrams
- [ ] Database for persistent state (surveys, maps, metrics, replays)
- [ ] Organized Pygame/web frontend for monitoring
- [ ] No duplicate files between root and package

### Out of Scope

- Desktop GPU optimization — Pi-first, desktop is a bonus
- Multi-game support — OpenArena only for v1
- Multiplayer coordination — solo bot for now
- Voice/chat integration — not needed for deathmatch
- Cloud deployment — runs locally on Pi

## Context

**Current codebase:** 26 package modules in `openarena_perception/` + 14 root-level scripts (some duplicated). No tests, no API layer, no organized docs structure. JSON files + pickles on disk for persistence.

**Platform:** Raspberry Pi 4/5, X11, OpenArena (ioquake3 fork). Screen capture at 800x600 for performance. Hailo-8L NPU available for YOLOv6n inference at 95 FPS.

**Reference spec:** `docs/Ultimate_Competitive_FPS_Bot_Spec.md` — comprehensive game-agnostic FPS bot architecture covering 5-layer design (perception, subconscious, conscious, team, meta-learning), utility AI, behavior trees, GOAP, attention mechanisms, human-like aiming (Perlin noise, overshoot, focus drift), cover system, and performance budgets. This is the north-star for architecture decisions across all phases.

**Key systems already built:**
- Perception: HSV enemy detection, OCR HUD parsing, motion detection, optical flow tracking
- Navigation: AAS pathfinding, learned maps, stuck recovery, room surveys
- Combat: Fuzzy weapon selection, PID aim control, combat movement patterns
- Control: Named pipe injection, RCON queries, keyboard/mouse via pynput
- LLM: Ollama integration (gemma4:31b-cloud), vision analysis, strategic decisions

**Primary API consumer:** LLM agents controlling the bot programmatically via FastAPI endpoints.

**Architecture inspiration:** Brain-inspired — perception (sensory cortex), navigation (hippocampus), combat (motor cortex + cerebellum), decisions (prefrontal cortex), memory (hippocampus + long-term storage), reflexes (limbic system).

## Constraints

- **Hardware**: Raspberry Pi 4/5 — must maintain 10+ FPS perception loop
- **Latency**: Real-time vision (OpenCV) for combat, LLM calls only for strategic decisions (~4s cycle)
- **Dependencies**: mss, opencv-python-headless, pytesseract, numpy, ollama — keep lightweight
- **Backward compat**: Existing room surveys, AAS files, trained models must keep working
- **Game interface**: Named pipe + RCON are the only communication channels

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FastAPI as backend framework | Standard, async-native, LLM-friendly, great docs | — Pending |
| Brain-inspired folder structure | Natural mapping to bot subsystems, intuitive organization | — Pending |
| Three-layer skill system (actions/behaviors/missions) | Composability, testability, LLM can operate at any layer | — Pending |
| Pi-first optimization | Real constraint drives efficient code, desktop is bonus | — Pending |
| LLM agents as primary API consumer | Bot is controlled by AI, not humans clicking buttons | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-08 after initialization*
