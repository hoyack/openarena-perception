# Requirements: OpenArena Perception Bot Framework

**Defined:** 2026-04-08
**Core Value:** The bot must be a competitive deathmatch player — able to perceive enemies, navigate maps, select weapons, aim accurately, and make strategic decisions in real-time on constrained Pi hardware.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Foundation

- [x] **FOUND-01**: Project uses brain-inspired folder structure (perception/, combat/, navigation/, memory/, tactics/, strategy/, reflexes/, brainstem/, skills/, api/)
- [x] **FOUND-02**: All duplicate root-level scripts resolved — single source of truth in package
- [x] **FOUND-03**: Configuration managed via pydantic-settings with env var / .env / TOML support
- [x] **FOUND-04**: Structured logging via structlog with JSON output and context binding
- [x] **FOUND-05**: Package management via uv with lockfile
- [x] **FOUND-06**: Code quality enforced via ruff linter/formatter
- [x] **FOUND-07**: Characterization tests for strategic_brain.py capturing all state transitions before decomposition
- [x] **FOUND-08**: Immutable SituationalAwareness dataclass as central data contract between subsystems

### Perception

- [x] **PERC-01**: Perception module produces immutable SituationalAwareness snapshots at 15+ FPS on Pi 5
- [x] **PERC-02**: Enemy detection with bounding boxes via HSV thresholding (existing, extracted)
- [x] **PERC-03**: HUD state parsing — health, armor, ammo, weapon, frags, deaths via OCR (existing, extracted)
- [x] **PERC-04**: Damage direction detection from screen flash analysis
- [x] **PERC-05**: Enemy distance estimation from bounding box size
- [x] **PERC-06**: Multi-target tracking with persistent IDs across frames
- [x] **PERC-07**: Motion detection via frame differencing and optical flow (existing, extracted)
- [x] **PERC-08**: Sound awareness — parse Q3 console output for footsteps, weapon fire, item pickup events

### Memory

- [x] **MEM-01**: SQLite database replaces all JSON/pickle file persistence
- [x] **MEM-02**: Working memory — current match state, recent events, short-term buffer
- [x] **MEM-03**: Episodic memory — match history, death locations, engagement outcomes
- [x] **MEM-04**: Semantic memory — map knowledge, room surveys, item locations persisted in DB
- [x] **MEM-05**: Alembic migrations for schema evolution

### Navigation

- [x] **NAV-01**: AAS pathfinding with A* on navigation mesh (existing, extracted)
- [x] **NAV-02**: Stuck detection and recovery via scan-and-probe (existing, extracted)
- [x] **NAV-03**: Learned map with occupancy grid and edge cost tracking (existing, extracted)
- [x] **NAV-04**: Room surveyor producing 360-degree spatial documentation (existing, extracted)
- [x] **NAV-05**: Obstacle avoidance during combat — real-time path adjustment
- [x] **NAV-06**: Respawn handling — immediate orientation and navigation after death

### Combat

- [x] **CMBT-01**: Target acquisition — snap to nearest threat from perception data
- [x] **CMBT-02**: PID-based aim control with lead prediction for projectile weapons (existing, extracted)
- [x] **CMBT-03**: Fuzzy weapon selection based on range, ammo, and weapon stats (existing, extracted)
- [x] **CMBT-04**: Combat movement — circle strafing, dodge patterns, skill-scaled (existing, extracted)
- [x] **CMBT-05**: Engagement/disengage decisions based on health, weapon matchup, threat assessment
- [x] **CMBT-06**: Weapon switch timing — preemptive switch before empty
- [x] **CMBT-07**: Threat assessment model — evaluate fight-or-flight based on own vs estimated enemy state

### Reflexes

- [x] **RFLX-01**: Damage response — instant reactive behavior when taking damage (<1ms)
- [x] **RFLX-02**: Death handling — clean state reset and respawn recovery
- [x] **RFLX-03**: Stuck escape — subsumption override when movement fails
- [x] **RFLX-04**: Reactive interrupt layer — higher-priority behaviors suppress lower-priority (subsumption)

### Tactics

- [x] **TACT-01**: FSM extracted from strategic_brain.py with clean state transitions
- [x] **TACT-02**: Commander — priority-based goal selection with utility scoring
- [x] **TACT-03**: Fight-or-flight evaluator based on threat assessment

### Strategy

- [x] **STRT-01**: LLM brain via Ollama for high-level strategic reasoning (~0.25 Hz)
- [x] **STRT-02**: LLM receives structured game state snapshots + optional screenshots
- [x] **STRT-03**: Strategy outputs constrained to defined action vocabulary (HUNT/DEFEND/RETREAT/EXPLORE)

### Skills System

- [x] **SKIL-01**: Atomic action layer — individual game commands (move, turn, fire, weapon_select)
- [x] **SKIL-02**: Behavior layer — composed sequences (room_survey, item_tour, combat_engage, patrol)
- [x] **SKIL-03**: Mission layer — high-level goals (explore_map, deathmatch, defend_area)
- [x] **SKIL-04**: Skills are composable — behaviors built from actions, missions built from behaviors
- [x] **SKIL-05**: SKILL.md migrated to skills/ folder as a specific skill definition

### API Layer

- [x] **API-01**: FastAPI backend exposing bot control endpoints for LLM agents
- [x] **API-02**: REST endpoints for perception state, navigation commands, combat control, skill execution
- [x] **API-03**: WebSocket endpoint for real-time state streaming at 2-5 Hz
- [x] **API-04**: Pydantic models for all request/response schemas with auto-generated docs
- [x] **API-05**: Prometheus metrics endpoint (/metrics) — FPS gauge, kill counter, LLM latency, stuck frequency

### Competitive Features

- [x] **COMP-01**: Item timing — track pickup timestamps and predict next spawn for Mega Health (35s), Red Armor (25s), Quad Damage (120s)
- [ ] **COMP-02**: Spawn prediction — navigate preemptively to high-value item spawns
- [ ] **COMP-03**: Multi-timescale decision architecture formalized — fast reflexes (10-22 Hz) + slow strategy (~0.25 Hz)

### Human-Likeness

- [ ] **HUMN-01**: Aim humanization — Gaussian noise scaled by target velocity, distance, turn rate. Cap accuracy below 70%
- [ ] **HUMN-02**: Reaction time modeling — variable 150-250ms+ delay between perception and action
- [ ] **HUMN-03**: Movement variability — overshoot corners, hesitate, occasional suboptimal paths
- [ ] **HUMN-04**: Bot personality profiles — configurable aggression, caution, weapon preference, grudge tendency
- [ ] **HUMN-05**: Adaptive learning — modify behavior based on death locations and engagement outcomes mid-match
- [ ] **HUMN-06**: Hesitation pauses — 100-300ms decision delay on state transitions
- [ ] **HUMN-07**: Skill difficulty scaling — unified parameter (1-5) affecting aim noise, reaction delay, decision quality

### Testing

- [ ] **TEST-01**: Unit tests for perception pipeline (HUD parsing, enemy detection, motion detection)
- [ ] **TEST-02**: Unit tests for navigation (pathfinding, stuck detection, learned map)
- [ ] **TEST-03**: Unit tests for combat (aim control PID, weapon selection, threat assessment)
- [ ] **TEST-04**: Integration tests for full perception → decision → action loop
- [ ] **TEST-05**: Tour testing with metrics — stuck count, completion time, visual verification
- [ ] **TEST-06**: Property-based tests via hypothesis for PID math, navigation coordinates, pathfinding

### Documentation

- [ ] **DOCS-01**: Full documentation site with system architecture diagrams
- [ ] **DOCS-02**: API reference auto-generated from FastAPI OpenAPI spec
- [ ] **DOCS-03**: Subsystem documentation — perception, combat, navigation, memory, tactics, strategy
- [ ] **DOCS-04**: Skill catalog — all available actions, behaviors, and missions
- [ ] **DOCS-05**: Configuration guide — all tunable parameters with descriptions
- [ ] **DOCS-06**: Getting started guide — setup on Pi, calibration, first run

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced

- **ADV-01**: Multi-agent coordination for team game modes
- **ADV-02**: Self-play training and reinforcement learning
- **ADV-03**: End-to-end neural control as alternative to modular pipeline
- **ADV-04**: Chat/communication system
- **ADV-05**: Plugin system for other games beyond OpenArena
- **ADV-06**: Complex emotion/mood modeling
- **ADV-07**: Hailo NPU YOLO detection augmenting HSV (hardware-dependent)
- **ADV-08**: Replay and recording system for post-match analysis
- **ADV-09**: Map control strategy — area value scoring and territorial behavior
- **ADV-10**: Predictive enemy tracking — last-known-position + velocity extrapolation

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Desktop GPU optimization | Pi-first constraint; desktop works as bonus |
| Multi-game support | OpenArena only for v1; game-specific interfaces |
| Perfect aim / aimbot accuracy | Actively harmful — detected by anti-cheat, breaks human-likeness |
| Global omniscient awareness | Only use perception-derived information; no cheating |
| Docker deployment on Pi | IPC overhead and memory pressure unacceptable on Pi |
| Celery/Redis task queues | Overkill for single-bot; asyncio is sufficient |
| gRPC for game communication | Named pipe + RCON are the only available channels |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01 | Phase 1 | Complete |
| FOUND-02 | Phase 1 | Complete |
| FOUND-03 | Phase 1 | Complete |
| FOUND-04 | Phase 1 | Complete |
| FOUND-05 | Phase 1 | Complete |
| FOUND-06 | Phase 1 | Complete |
| FOUND-07 | Phase 1 | Complete |
| FOUND-08 | Phase 1 | Complete |
| PERC-01 | Phase 2 | Complete |
| PERC-02 | Phase 2 | Complete |
| PERC-03 | Phase 2 | Complete |
| PERC-04 | Phase 2 | Complete |
| PERC-05 | Phase 2 | Complete |
| PERC-06 | Phase 2 | Complete |
| PERC-07 | Phase 2 | Complete |
| PERC-08 | Phase 7 | Complete |
| MEM-01 | Phase 3 | Complete |
| MEM-02 | Phase 3 | Complete |
| MEM-03 | Phase 3 | Complete |
| MEM-04 | Phase 3 | Complete |
| MEM-05 | Phase 3 | Complete |
| NAV-01 | Phase 4 | Complete |
| NAV-02 | Phase 4 | Complete |
| NAV-03 | Phase 4 | Complete |
| NAV-04 | Phase 4 | Complete |
| NAV-05 | Phase 4 | Complete |
| NAV-06 | Phase 4 | Complete |
| CMBT-01 | Phase 4 | Complete |
| CMBT-02 | Phase 4 | Complete |
| CMBT-03 | Phase 4 | Complete |
| CMBT-04 | Phase 4 | Complete |
| CMBT-05 | Phase 4 | Complete |
| CMBT-06 | Phase 4 | Complete |
| CMBT-07 | Phase 4 | Complete |
| RFLX-01 | Phase 4 | Complete |
| RFLX-02 | Phase 4 | Complete |
| RFLX-03 | Phase 4 | Complete |
| RFLX-04 | Phase 4 | Complete |
| TACT-01 | Phase 5 | Complete |
| TACT-02 | Phase 5 | Complete |
| TACT-03 | Phase 5 | Complete |
| STRT-01 | Phase 5 | Complete |
| STRT-02 | Phase 5 | Complete |
| STRT-03 | Phase 5 | Complete |
| SKIL-01 | Phase 6 | Complete |
| SKIL-02 | Phase 6 | Complete |
| SKIL-03 | Phase 6 | Complete |
| SKIL-04 | Phase 6 | Complete |
| SKIL-05 | Phase 6 | Complete |
| API-01 | Phase 6 | Complete |
| API-02 | Phase 6 | Complete |
| API-03 | Phase 6 | Complete |
| API-04 | Phase 6 | Complete |
| API-05 | Phase 6 | Complete |
| COMP-01 | Phase 7 | Complete |
| COMP-02 | Phase 7 | Pending |
| COMP-03 | Phase 7 | Pending |
| HUMN-01 | Phase 8 | Pending |
| HUMN-02 | Phase 8 | Pending |
| HUMN-03 | Phase 8 | Pending |
| HUMN-04 | Phase 8 | Pending |
| HUMN-05 | Phase 8 | Pending |
| HUMN-06 | Phase 8 | Pending |
| HUMN-07 | Phase 8 | Pending |
| TEST-01 | Phase 9 | Pending |
| TEST-02 | Phase 9 | Pending |
| TEST-03 | Phase 9 | Pending |
| TEST-04 | Phase 9 | Pending |
| TEST-05 | Phase 9 | Pending |
| TEST-06 | Phase 9 | Pending |
| DOCS-01 | Phase 9 | Pending |
| DOCS-02 | Phase 9 | Pending |
| DOCS-03 | Phase 9 | Pending |
| DOCS-04 | Phase 9 | Pending |
| DOCS-05 | Phase 9 | Pending |
| DOCS-06 | Phase 9 | Pending |

**Coverage:**
- v1 requirements: 76 total
- Mapped to phases: 76
- Unmapped: 0

---
*Requirements defined: 2026-04-08*
*Last updated: 2026-04-08 after roadmap creation*
