# Project Research Summary

**Project:** OpenArena Perception -- Brain-Inspired AI Bot Framework
**Domain:** FPS AI bot with brain-inspired cognitive architecture, running on Raspberry Pi 5
**Researched:** 2026-04-08
**Confidence:** HIGH

## Executive Summary

OpenArena Perception is a brain-inspired FPS AI bot framework that restructures an existing, functional OpenArena bot into a modular cognitive architecture. The project already has working perception (HSV enemy detection, HUD OCR), navigation (AAS pathfinding), combat (PID aiming, fuzzy weapon selection), and LLM-driven strategy (Ollama). The core challenge is not building from scratch but decomposing a 700+ line god object (`strategic_brain.py`) into clean, testable subsystems while keeping the bot playable at every step -- then exposing it all through a FastAPI layer for LLM agent control.

The recommended approach is a layered cognitive subsumption architecture where lower layers (reflexes, perception) run fast and override higher layers (tactics, strategy). This maps directly to existing reality: HSV detection at 15+ FPS, LLM reasoning at 0.25 Hz. The stack is Python 3.11+ with asyncio, FastAPI, SQLite, and structlog -- all high-confidence choices validated on Pi 5 hardware. The single-process, single-event-loop design is correct for this constrained platform, avoiding IPC overhead while letting async handle the natural fast/slow concurrency.

The primary risk is a big-bang refactor that breaks the working bot for weeks. Every researcher flagged this independently. The mitigation is strict incremental extraction: move one subsystem at a time, verify the bot still plays after each move, and write characterization tests before touching `strategic_brain.py`. Secondary risks include tick budget death-by-a-thousand-cuts on Pi hardware and async deadlocks from mixing sync OpenCV with async FastAPI/LLM calls.

## Key Findings

### Recommended Stack

The stack is mature and well-validated. Nearly every choice is HIGH confidence because the project already runs most of these technologies. The key additions are FastAPI (async API layer), SQLite/aiosqlite (replacing JSON/pickle), structlog (replacing ad-hoc logging), and uv (modern package management).

**Core technologies:**
- **Python 3.11+ / asyncio / uvloop**: Single event loop handles game ticks, API, and LLM concurrency naturally on Pi
- **FastAPI + uvicorn**: Async API with WebSocket streaming, Pydantic validation, auto-docs
- **SQLite + aiosqlite + SQLAlchemy Core**: Zero-config persistence replacing fragile JSON/pickle files, with async access
- **mss + OpenCV + pytesseract**: Existing perception stack, validated at 15-17 FPS on Pi
- **Ollama Python SDK**: Async LLM client, validated with gemma4:31b on Pi at ~4s latency
- **HailoRT**: NPU inference for YOLOv6n at 95 FPS (future enhancement)
- **structlog + prometheus-client**: Structured JSON logging and metrics for bot observability
- **uv + ruff + pytest**: Modern Python toolchain (package management, linting, testing)

### Expected Features

**Must have (table stakes):**
- Enemy detection with bounding boxes (EXISTING)
- HUD state parsing -- health, armor, ammo, weapon (EXISTING)
- AAS pathfinding with stuck detection/recovery (EXISTING)
- Aim control with lead prediction (EXISTING)
- Weapon selection based on range/ammo (EXISTING)
- FSM for high-level state control (EXISTING, needs extraction)
- Composable skill system -- actions, behaviors, missions (PLANNED, core requirement)
- FastAPI endpoints exposing skills to LLM agents (PLANNED)
- SQLite persistence replacing JSON/pickle (PLANNED)
- Structured logging and metrics (PLANNED)
- Test suite for core subsystems (PLANNED)

**Should have (competitive advantage):**
- Item timing and spawn prediction -- single biggest competitive ROI
- Threat assessment model -- fight-or-flight decisions
- Sound awareness from Q3 console event parsing
- Reactive interrupt/reflex layer (subsumption override)
- Aim humanization with Gaussian noise scaled by context
- Reaction time modeling with variable delays
- Bot personality profiles -- aggression, caution, grudge behavior
- Hailo NPU YOLO detection augmenting HSV

**Defer (v2+):**
- Multi-agent coordination, self-play training, end-to-end neural control
- Chat/communication system, plugin system for other games
- Complex emotion/mood modeling
- Map control strategy and predictive enemy tracking (late phases, not deferred entirely)

### Architecture Approach

The architecture is a hybrid of Brooks' subsumption (layered behaviors with priority override) and SOAR-inspired cognitive modules. Eight brain-region modules communicate via an immutable SituationalAwareness snapshot (produced by perception each tick), a typed EventBus for async signals, and a priority-based action queue for motor output. FastAPI runs as an external observer in the same event loop, never driving the tick loop.

**Major components:**
1. **perception/** -- Screen capture, HUD OCR, enemy detection, tracking (15-20 Hz, read-only producer)
2. **reflexes/** -- Damage response, death handling, stuck escape (<1ms event-driven override)
3. **combat/** -- Aim control, weapon selection, fire control, combat movement (15-20 Hz)
4. **navigation/** -- AAS pathfinding, learned map, room surveys, spatial awareness (5-10 Hz)
5. **memory/** -- Working memory, episodic buffer, semantic knowledge, DB persistence (async)
6. **tactics/** -- FSM state management, behavior selection, fight-or-flight (2-5 Hz)
7. **strategy/** -- LLM reasoning, goal setting, strategic analysis (0.25 Hz)
8. **brainstem/** -- Game bridge, named pipe I/O, virtual controller, atomic actions (always on)
9. **skills/** -- Three-layer composition: atomic actions, behaviors, missions
10. **api/** -- FastAPI + WebSocket for LLM agent control

### Critical Pitfalls

1. **Big bang refactor** -- Move one subsystem at a time. Bot must play after every extraction. Use re-exports from old locations during transition.
2. **Losing implicit knowledge from god object** -- Write characterization tests for `strategic_brain.py` before splitting it. Capture state transitions, timing heuristics, edge cases.
3. **Breaking the tick budget** -- Profile every addition on Pi, not desktop. Hard alarm at 50ms/tick. Use frozen dataclasses, avoid serialization in hot path.
4. **Async deadlocks (sync/async mixing)** -- Keep OpenCV in sync tick path (7-10ms is fine). LLM and DB run in separate coroutines. Never await slow operations in the tick loop.
5. **Over-abstracting the event bus** -- Start with direct function calls. Introduce pub/sub only when two or more subsystems need async communication. Let the interface emerge.

## Implications for Roadmap

### Phase 1: Foundation and Characterization
**Rationale:** Everything depends on the base layer. Must establish project structure, config, and safety net before touching any subsystems.
**Delivers:** Project skeleton with uv, brainstem extraction, unified config (pydantic-settings), SituationalAwareness dataclass, characterization test suite for `strategic_brain.py`, structured logging.
**Addresses:** Configuration management, structured logging, test suite foundation
**Avoids:** Big bang refactor (establishes incremental migration path), losing implicit knowledge (characterization tests)

### Phase 2: Perception Extraction
**Rationale:** Perception is the read-only data producer that all other systems depend on. Extract it first so everything downstream has a stable interface to consume.
**Delivers:** Clean `perception/` module with capture, HUD parser, world parser, motion detector, object tracker. Perception loop producing immutable SituationalAwareness snapshots.
**Addresses:** Enemy detection, HUD parsing, multi-target tracking, distance estimation
**Avoids:** Tick budget regression (profile on Pi before and after)

### Phase 3: Memory and Persistence
**Rationale:** Memory module provides the storage abstraction needed by all subsequent subsystems. Migrate from JSON/pickle to SQLite here, before combat/navigation extraction creates more moving parts.
**Delivers:** `memory/` module with working memory, episodic buffer, semantic store. SQLite backend via aiosqlite. Alembic migrations.
**Addresses:** Persistent state, database, room survey storage, match history
**Avoids:** Premature DB migration (architecture stable enough by this point), over-engineering storage (start with interface, swap backends)

### Phase 4: Reflexes, Combat, and Navigation Extraction
**Rationale:** These three subsystems are the behavioral core. They depend on perception and memory but are relatively independent of each other, so they can be extracted in parallel or rapid sequence.
**Delivers:** `reflexes/` (damage response, death handler, stuck escape), `combat/` (aim controller, weapon selection, fire control, combat movement), `navigation/` (AAS pathfinding, navigator, learned map, room surveyor). Import direction enforced: no cross-imports between peers.
**Addresses:** All table-stakes combat and navigation features, stuck detection/recovery, respawn handling
**Avoids:** Circular import hell (strict import direction), aim PID coupling to tick timing (verify constants post-extraction), losing learned map hooks

### Phase 5: Tactics and Strategy Extraction
**Rationale:** The FSM and LLM reasoning are the final pieces of `strategic_brain.py`. By this point all subsystems they orchestrate are already extracted, so the decomposition is clean.
**Delivers:** `tactics/` (FSM, commander, threat evaluator), `strategy/` (LLM brain, strategic agent, prompt templates). Complete decomposition of `strategic_brain.py`. Root-level script cleanup (deprecation wrappers then removal).
**Addresses:** FSM state management, LLM-driven strategic reasoning, fight-or-flight decisions
**Avoids:** State transition logic scattered (map ALL transitions before extracting), async timing assumptions changing (LLM task remains independent)

### Phase 6: Skill System and API Layer
**Rationale:** The skill system composes extracted subsystems into LLM-consumable actions/behaviors/missions. The API layer exposes them. Both require all subsystems to be stable.
**Delivers:** `skills/` (atomic actions, composed behaviors, high-level missions), `api/` (FastAPI app, REST routes for perception/combat/navigation/skills/strategy/memory, WebSocket state streaming, Pydantic models). Prometheus metrics endpoint.
**Addresses:** Composable skill system, FastAPI endpoints, real-time state query, metrics/observability, WebSocket streaming
**Avoids:** Skill system scope creep (skills are functions, not objects with lifecycle), WebSocket state flooding (delta compression at 2-5 Hz), blocking tick loop from API

### Phase 7: Competitive Features
**Rationale:** With the framework stable and API-accessible, add the features that make the bot actually competitive in deathmatch.
**Delivers:** Item timing/spawn prediction, sound awareness (Q3 console parsing), reactive interrupt layer (subsumption override formalized), threat assessment model, respawn recovery behavior.
**Addresses:** All "should have" competitive features from FEATURES.md
**Avoids:** N/A -- standard game AI patterns, well-documented

### Phase 8: Human-Likeness
**Rationale:** Human-likeness features overlay everything and benefit from a stable, well-tested framework underneath. BotPrize research provides clear implementation patterns.
**Delivers:** Aim humanization, reaction time modeling, movement variability, bot personality profiles, adaptive learning from deaths, grudge behavior, skill difficulty scaling.
**Addresses:** All human-likeness differentiators from FEATURES.md
**Avoids:** Perfect aim detection (constrain accuracy below 70% even at max skill)

### Phase 9: Advanced Strategy and Polish
**Rationale:** Map control, predictive tracking, and replay analysis require all prior systems working together. These are the capstone features.
**Delivers:** Map control strategy, predictive enemy tracking, LLM mission system, replay/recording system, Hailo NPU YOLO integration.
**Addresses:** Advanced strategy features, NPU hardware acceleration
**Avoids:** N/A -- late-stage features with flexible scope

### Phase Ordering Rationale

- **Phases 1-2 first** because perception is the data producer everything reads. Foundation + perception gives a testable, running perception pipeline.
- **Phase 3 before 4** because combat and navigation both need storage interfaces for learned data. Get persistence right before extracting consumers.
- **Phase 4 as a batch** because reflexes, combat, and navigation are peers with no cross-dependencies. They can be extracted in rapid sequence against the stable perception/memory interface.
- **Phase 5 after 4** because the FSM and LLM orchestrate the subsystems extracted in Phase 4. Cannot cleanly extract the orchestrator before the things it orchestrates.
- **Phase 6 after 5** because the API exposes the complete system. Partial exposure creates confusing contracts.
- **Phases 7-9 are feature phases** that build on the stable framework. They can be reordered based on priorities.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Reflexes/Combat/Navigation):** Complex extraction from god object. Needs careful characterization testing and import graph analysis.
- **Phase 6 (Skills + API):** The skill system design needs concrete API contract definition. How does an LLM agent compose behaviors? What does the WebSocket protocol look like?
- **Phase 7 (Competitive Features):** Sound awareness from Q3 console parsing needs investigation of what events are available and their format.
- **Phase 9 (Advanced):** Hailo NPU integration has hardware-specific complexity. HailoRT 5.2.0 migration path needs validation.

Phases with standard patterns (skip deeper research):
- **Phase 1 (Foundation):** Standard Python project setup, pydantic-settings, structlog -- all well-documented.
- **Phase 2 (Perception):** Extraction/refactoring of existing working code. Patterns are clear.
- **Phase 3 (Memory/DB):** SQLite + aiosqlite + Alembic is a well-trodden path.
- **Phase 5 (Tactics/Strategy):** FSM extraction is straightforward once subsystems are extracted.
- **Phase 8 (Human-Likeness):** BotPrize research provides concrete implementation patterns with parameters.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Nearly all technologies already validated on Pi. Versions checked against PyPI. Only SQLAlchemy Core (MEDIUM) is new. |
| Features | HIGH | Grounded in Q3 bot architecture, BotPrize research, DeepMind FTW, and AAMAS 2025. 30+ academic and framework sources. |
| Architecture | HIGH | Subsumption + SOAR hybrid is well-researched. Maps cleanly to existing system's natural fast/slow split. Folder structure is detailed. |
| Pitfalls | HIGH | Pitfalls derived from codebase analysis (god object, import graph) and standard Python async/refactoring patterns. Actionable mitigations. |

**Overall confidence:** HIGH

### Gaps to Address

- **Q3 console sound event format:** Sound awareness depends on parsing game console output. Exact event format and available events need validation against running OpenArena instance.
- **Hailo NPU model pipeline:** YOLOv6n at 95 FPS is benchmarked, but the full pipeline (capture -> preprocess -> NPU -> postprocess -> SituationalAwareness) latency on Pi 5 needs measurement.
- **LLM agent API contract:** How an LLM agent actually composes skills via the API needs concrete protocol design. Current research suggests REST + WebSocket but the interaction patterns are underspecified.
- **SQLAlchemy Core vs raw SQL boundary:** Research recommends Core for query building but raw SQL for hot paths. The exact boundary needs profiling.
- **Characterization test coverage:** The implicit knowledge in `strategic_brain.py` is acknowledged but not yet catalogued. This is Phase 1 work.

## Sources

### Primary (HIGH confidence)
- Quake III Arena Bot Architecture (van Waveren) -- original Q3 bot design, production rules
- DeepMind FTW (arXiv:1807.01281) -- multi-timescale architecture
- BotPrize competition results (2008-2012) -- human-likeness evaluation
- TorchCraftAI architecture docs -- blackboard pattern, module system
- Subsumption Architecture (Brooks) -- layered behavior priority override
- SOAR Cognitive Architecture -- working/procedural/semantic/episodic memory
- FastAPI, SQLAlchemy, structlog, Ruff official documentation
- Existing OpenArena Perception codebase analysis

### Secondary (MEDIUM confidence)
- AAMAS 2025: Many Challenges of Human-Like Agents -- believability patterns
- THREATBOT (QUT thesis) -- threat assessment models
- GAN-Aimbots / VADNet / AntiCheatPT -- aim detection methods informing humanization
- Hailo RPi5 examples and HailoRT 5.2.0 community guide
- YOLO11 NCNN benchmarks on Raspberry Pi (LearnOpenCV)

### Tertiary (LOW confidence)
- Neural Brain framework (arXiv:2505.07634) -- brain-region mapping, theoretical
- ConsScale FPS emotion modeling -- rejected as anti-feature but informed scope decisions

---
*Research completed: 2026-04-08*
*Ready for roadmap: yes*
