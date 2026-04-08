# Roadmap: OpenArena Perception Bot Framework

## Overview

Transform an existing, functional OpenArena bot from a monolithic god-object architecture into a brain-inspired modular cognitive framework with clean subsystems, persistent memory, composable skills, and an API layer for LLM agent control. The bot must remain playable after every phase. Nine phases progress from foundation through perception, memory, behavioral extraction, decision-making, API exposure, competitive features, human-likeness, and finally comprehensive testing and documentation.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation and Characterization** - Project skeleton, config, logging, data contracts, and characterization tests before any decomposition
- [ ] **Phase 2: Perception Extraction** - Clean perception module producing immutable snapshots at 15+ FPS
- [ ] **Phase 3: Memory and Persistence** - SQLite persistence replacing JSON/pickle with working, episodic, and semantic memory
- [ ] **Phase 4: Reflexes, Combat, and Navigation Extraction** - Extract the three behavioral subsystems from the god object
- [ ] **Phase 5: Tactics and Strategy Extraction** - FSM and LLM reasoning extracted, completing strategic_brain.py decomposition
- [ ] **Phase 6: Skill System and API Layer** - Three-layer skill composition and FastAPI endpoints for LLM agent control
- [ ] **Phase 7: Competitive Features** - Item timing, sound awareness, and formalized multi-timescale architecture
- [ ] **Phase 8: Human-Likeness** - Aim humanization, reaction modeling, personality profiles, and adaptive learning
- [ ] **Phase 9: Testing and Documentation** - Comprehensive test suite and full documentation site

## Phase Details

### Phase 1: Foundation and Characterization
**Goal**: Establish the project skeleton, tooling, and safety net so that all subsequent extraction work has a stable base and a characterization test suite preventing regressions
**Depends on**: Nothing (first phase)
**Requirements**: FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05, FOUND-06, FOUND-07, FOUND-08
**Success Criteria** (what must be TRUE):
  1. Running `uv run pytest` executes characterization tests that capture all state transitions in strategic_brain.py
  2. The brain-inspired folder structure exists (perception/, combat/, navigation/, memory/, tactics/, strategy/, reflexes/, brainstem/, skills/, api/) with __init__.py files
  3. Configuration loads from environment variables, .env files, or TOML via pydantic-settings and is importable from a single location
  4. Structured JSON logs appear when any module runs, with context binding for subsystem identification
  5. No duplicate scripts exist between root level and package -- single source of truth verified
**Plans**: 5 plans
Plans:
- [x] 01-01-PLAN.md — uv init, pyproject.toml, ruff/pytest config, test scaffold
- [x] 01-02-PLAN.md — Brain-inspired folder structure, pydantic-settings, structlog
- [x] 01-03-PLAN.md — SituationalAwareness extraction to models.py (frozen+slotted)
- [x] 01-04-PLAN.md — FSM characterization tests for strategic_brain.py
- [x] 01-05-PLAN.md — Duplicate root script resolution and .gitignore

### Phase 2: Perception Extraction
**Goal**: The perception subsystem runs as a clean, independent module producing immutable SituationalAwareness snapshots that downstream systems consume
**Depends on**: Phase 1
**Requirements**: PERC-01, PERC-02, PERC-03, PERC-04, PERC-05, PERC-06, PERC-07
**Success Criteria** (what must be TRUE):
  1. Perception loop produces SituationalAwareness snapshots at 15+ FPS on Raspberry Pi 5
  2. Enemy detection returns bounding boxes with distance estimates from HSV thresholding
  3. HUD parser extracts health, armor, ammo, weapon, frags, and deaths from screen capture
  4. Multi-target tracking maintains persistent IDs across consecutive frames
  5. Motion detection identifies movement regions via frame differencing and optical flow
**Plans**: 3 plans
Plans:
- [x] 02-01-PLAN.md — Move 9 perception modules into perception/ with re-export stubs
- [x] 02-02-PLAN.md — PerceptionPipeline orchestrator with tick budget and attention priority
- [x] 02-03-PLAN.md — Comprehensive tests for PERC-01 through PERC-07

### Phase 3: Memory and Persistence
**Goal**: All bot state persists in SQLite with clean abstractions for working memory, episodic memory, and semantic knowledge -- no more JSON files or pickles on disk
**Depends on**: Phase 2
**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04, MEM-05
**Success Criteria** (what must be TRUE):
  1. SQLite database stores all persistent state -- room surveys, learned maps, match history
  2. Working memory holds current match state and recent events in a queryable short-term buffer
  3. Episodic memory records match history, death locations, and engagement outcomes retrievable by query
  4. Semantic memory persists map knowledge and item locations across bot restarts
  5. Alembic migrations can evolve the schema without data loss
**Plans**: 3 plans
Plans:
- [x] 03-01-PLAN.md — SQLite schema, storage engine, Alembic setup, deps install
- [x] 03-02-PLAN.md — WorkingMemory, EpisodicMemory, SemanticMemory, migration script
- [x] 03-03-PLAN.md — Comprehensive tests for all memory modules

### Phase 4: Reflexes, Combat, and Navigation Extraction
**Goal**: The three behavioral subsystems (reflexes, combat, navigation) are extracted from strategic_brain.py into independent modules with no cross-imports, all consuming perception snapshots and memory interfaces
**Depends on**: Phase 3
**Requirements**: RFLX-01, RFLX-02, RFLX-03, RFLX-04, CMBT-01, CMBT-02, CMBT-03, CMBT-04, CMBT-05, CMBT-06, CMBT-07, NAV-01, NAV-02, NAV-03, NAV-04, NAV-05, NAV-06
**Success Criteria** (what must be TRUE):
  1. Reflex layer interrupts lower-priority behaviors within 1ms when damage is detected or the bot is stuck
  2. Combat system acquires targets from perception data, aims with PID lead prediction, selects weapons by range/ammo, and executes combat movement patterns
  3. Navigation system pathfinds via AAS mesh, detects and recovers from stuck states, and performs 360-degree room surveys
  4. Bot plays a complete deathmatch round using the extracted modules without regression from pre-extraction behavior
  5. No circular imports exist between reflexes/, combat/, and navigation/ -- import direction is strictly downward (toward perception and memory)
**Plans**: 5 plans
Plans:
- [x] 04-01-PLAN.md — Reflexes extraction (arbiter, death handler, stuck escape)
- [x] 04-02-PLAN.md — Combat extraction (weapons, aim, movement, engage, threat)
- [x] 04-03-PLAN.md — Navigation extraction (AAS, navigator, learned map, behaviors)
- [x] 04-04-PLAN.md — Rewire strategic_brain.py orchestrator to use subsystems
- [x] 04-05-PLAN.md — Subsystem unit tests for all 17 requirements

### Phase 5: Tactics and Strategy Extraction
**Goal**: The FSM state machine and LLM strategic reasoning are extracted from strategic_brain.py, completing its full decomposition into the brain-inspired module structure
**Depends on**: Phase 4
**Requirements**: TACT-01, TACT-02, TACT-03, STRT-01, STRT-02, STRT-03
**Success Criteria** (what must be TRUE):
  1. FSM manages clean state transitions (DEAD/COMBAT/STUCK/SURVEYING/NAVIGATING/EXPLORING) extracted from strategic_brain.py
  2. Commander selects goals via priority-based utility scoring informed by game state
  3. LLM brain receives structured game state snapshots via Ollama and outputs constrained action vocabulary (HUNT/DEFEND/RETREAT/EXPLORE)
  4. strategic_brain.py is fully decomposed -- the original file is either deleted or reduced to a thin re-export wrapper
**Plans**: 4 plans
Plans:
- [x] 05-01-PLAN.md — FSM extraction to tactics/fsm.py with TacticalFSM
- [ ] 05-02-PLAN.md — Commander relocation to tactics/ + FightOrFlight wrapper
- [ ] 05-03-PLAN.md — LLM brain to strategy/ with Pydantic-validated constrained output
- [ ] 05-04-PLAN.md — Comprehensive tests for all 6 requirements

### Phase 6: Skill System and API Layer
**Goal**: LLM agents can control the bot programmatically through FastAPI endpoints that expose a three-layer skill system (actions, behaviors, missions)
**Depends on**: Phase 5
**Requirements**: SKIL-01, SKIL-02, SKIL-03, SKIL-04, SKIL-05, API-01, API-02, API-03, API-04, API-05
**Success Criteria** (what must be TRUE):
  1. Atomic actions (move, turn, fire, weapon_select) are individually callable via REST endpoints
  2. Behaviors (room_survey, item_tour, combat_engage, patrol) compose from atomic actions and are triggerable via API
  3. Missions (explore_map, deathmatch, defend_area) compose from behaviors and can be started/stopped via API
  4. WebSocket endpoint streams real-time bot state at 2-5 Hz to connected clients
  5. Prometheus metrics endpoint exposes FPS gauge, kill counter, LLM latency, and stuck frequency
**Plans**: 5 plans
Plans:
- [ ] 06-01-PLAN.md — TBD
- [ ] 06-02-PLAN.md — TBD
- [ ] 06-03-PLAN.md — TBD
- [ ] 06-04-PLAN.md — TBD
- [ ] 06-05-PLAN.md — TBD
**UI hint**: yes

### Phase 7: Competitive Features
**Goal**: The bot uses item timing, sound awareness, and formalized multi-timescale decision-making to compete effectively in deathmatch
**Depends on**: Phase 6
**Requirements**: COMP-01, COMP-02, COMP-03, PERC-08
**Success Criteria** (what must be TRUE):
  1. Bot tracks Mega Health (35s), Red Armor (25s), and Quad Damage (120s) spawn timers and navigates preemptively to predicted spawns
  2. Bot reacts to sound events (footsteps, weapon fire, item pickups) parsed from Q3 console output
  3. Multi-timescale architecture is formalized -- reflexes run at 10-22 Hz, tactics at 2-5 Hz, strategy at ~0.25 Hz with clean boundaries
**Plans**: 5 plans
Plans:
- [ ] 07-01-PLAN.md — TBD
- [ ] 07-02-PLAN.md — TBD
- [ ] 07-03-PLAN.md — TBD
- [ ] 07-04-PLAN.md — TBD
- [ ] 07-05-PLAN.md — TBD

### Phase 8: Human-Likeness
**Goal**: The bot behaves believably human -- imperfect aim, variable reaction times, movement quirks, and configurable personality profiles
**Depends on**: Phase 7
**Requirements**: HUMN-01, HUMN-02, HUMN-03, HUMN-04, HUMN-05, HUMN-06, HUMN-07
**Success Criteria** (what must be TRUE):
  1. Aim accuracy stays below 70% even at maximum skill level, with Gaussian noise scaled by target velocity and distance
  2. Reaction time varies between 150-250ms+ with no instant-response tells
  3. Bot exhibits movement variability -- overshooting corners, hesitation pauses, occasional suboptimal paths
  4. Bot personality profiles are configurable (aggression, caution, weapon preference, grudge tendency) and produce observably different play styles
  5. Skill difficulty parameter (1-5) scales aim noise, reaction delay, and decision quality in a unified way
**Plans**: 5 plans
Plans:
- [ ] 08-01-PLAN.md — TBD
- [ ] 08-02-PLAN.md — TBD
- [ ] 08-03-PLAN.md — TBD
- [ ] 08-04-PLAN.md — TBD
- [ ] 08-05-PLAN.md — TBD

### Phase 9: Testing and Documentation
**Goal**: Comprehensive test coverage validates all subsystems and a documentation site provides architecture diagrams, API reference, skill catalog, and getting-started guide
**Depends on**: Phase 8
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06, DOCS-01, DOCS-02, DOCS-03, DOCS-04, DOCS-05, DOCS-06
**Success Criteria** (what must be TRUE):
  1. Unit tests pass for perception pipeline, navigation, and combat subsystems with property-based tests for PID math and pathfinding
  2. Integration test runs a full perception-to-decision-to-action loop and verifies correct behavior
  3. Tour test completes with metrics -- stuck count, completion time, visual verification all recorded
  4. Documentation site serves architecture diagrams, auto-generated API reference from OpenAPI spec, skill catalog, and getting-started guide
  5. Configuration guide documents all tunable parameters with descriptions
**Plans**: 5 plans
Plans:
- [ ] 09-01-PLAN.md — TBD
- [ ] 09-02-PLAN.md — TBD
- [ ] 09-03-PLAN.md — TBD
- [ ] 09-04-PLAN.md — TBD
- [ ] 09-05-PLAN.md — TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation and Characterization | 5/5 | Complete | - |
| 2. Perception Extraction | 3/3 | Complete | - |
| 3. Memory and Persistence | 3/3 | Complete | - |
| 4. Reflexes, Combat, and Navigation Extraction | 5/5 | Complete | - |
| 5. Tactics and Strategy Extraction | 0/4 | Planning complete | - |
| 6. Skill System and API Layer | 0/TBD | Not started | - |
| 7. Competitive Features | 0/TBD | Not started | - |
| 8. Human-Likeness | 0/TBD | Not started | - |
| 9. Testing and Documentation | 0/TBD | Not started | - |
