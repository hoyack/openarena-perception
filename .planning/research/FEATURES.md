# Feature Landscape: FPS AI Bot Framework

**Domain:** Brain-inspired FPS AI bot management framework (deathmatch-focused, OpenArena/ioquake3)
**Researched:** 2026-04-08
**Mode:** Ecosystem research across academic, competitive, and commercial FPS AI

---

## Table Stakes

Features the framework must have or the bot is incompetent in deathmatch. Informed by Quake III Arena bot architecture (van Waveren), Pogamut framework capabilities, and competitive FPS fundamentals.

### Perception

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Enemy detection with bounding boxes | Cannot fight what you cannot see. Every FPS bot framework (Pogamut, Q3 native, BWAPI equivalent) provides this | Medium | EXISTING via HSV thresholding. Consider YOLO on Hailo NPU for robustness |
| HUD state parsing (health, armor, ammo, weapon, frags) | Bot must know its own status to make any decision. Q3 native bots read this from game state directly | Medium | EXISTING via Tesseract OCR |
| Damage direction detection | Must know where damage comes from to react. Q3 native bots get this from engine events | Low | Parse screen flash/red overlay or game console damage events |
| Enemy distance estimation | Weapon selection and engagement decisions require range. All competitive bot frameworks provide range info | Medium | EXISTING via bounding box size heuristic |
| Multi-target tracking with persistence | Deathmatch has multiple enemies; must track across frames with unique IDs | High | EXISTING via color histograms + templates |
| Sound awareness (footsteps, weapon fire, item pickup) | Audio is roughly 40% of competitive FPS information. Q3 engine emits sound events parseable from console | Medium | Critical for off-screen threats. Parse game console output |

### Navigation

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Pathfinding on navigation mesh | Must traverse maps without getting stuck. Q3 AAS system is the standard | High | EXISTING via AAS files + A* |
| Stuck detection and recovery | Bots that get stuck on geometry are useless. Every serious framework handles this | Medium | EXISTING via scan-and-probe |
| Item location knowledge | Must know where weapons, health, armor spawn on each map | Low | EXISTING via room surveys + AAS/BSP entity parsing |
| Obstacle avoidance during combat | Must dodge while fighting, not walk into walls | Medium | Requires real-time path adjustment around obstacles |
| Respawn handling | Must immediately orient and navigate after death. Q3 bots do this seamlessly | Low | Reset state, pick nearest useful item path |

### Combat

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Target acquisition (snap to nearest threat) | Must engage enemies when they appear. Core Q3 bot behavior | Medium | EXISTING via perception pipeline |
| Aim control with lead prediction | Projectile weapons require aiming ahead of target. Q3 projectile speeds are known constants | High | EXISTING via PID controller |
| Weapon selection based on range/ammo | Wrong weapon equals death. Rocket at point blank kills self, rail at distance is optimal | Medium | EXISTING via fuzzy logic |
| Combat movement (strafing, dodging) | Standing still means death. Must move unpredictably while fighting | High | Circle-strafe, dodge patterns. Partially EXISTING |
| Engagement/disengage decisions | Must know when to fight vs retreat based on health, weapon matchup | Medium | Health threshold + weapon matchup logic |
| Reload/weapon switch timing | Must not get caught with empty weapon in a fight | Low | Track ammo state, preemptive weapon switch |

### Decision Making

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| State machine or behavior tree for high-level control | Must transition between explore/fight/flee/pickup coherently. Q3 bots use behavior selector with sub-controllers | Medium | EXISTING via FSM. Consider hybrid FSM+BT |
| Priority-based goal selection | When multiple options exist, pick the best one via utility scoring | Medium | Weighted utility or behavior tree selector |
| Reactive interrupts (reflex layer) | Must instantly react to being shot or seeing enemy. Subsumption architecture principle: lower-priority behaviors suppressed by higher-priority interrupts | Medium | Brain-inspired "limbic system" - fast path bypassing deliberation |
| Context-aware item pickup | Must detour for weapons/items when strategically valuable | Low | Utility calculation: distance cost vs item value vs current loadout |

### Framework / API

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Composable skill system (actions to behaviors to missions) | LLM agents need to operate at multiple abstraction levels. TorchCraftAI modules pattern demonstrates this | High | PLANNED. Core architectural requirement |
| API for bot control (FastAPI) | Primary consumer is LLM agents, not humans | Medium | PLANNED. Expose perception, navigation, combat, decision endpoints |
| Real-time state query | LLM must read bot state as structured JSON | Low | Expose current game state snapshot |
| Metrics and observability | Must know if bot is performing well. Frag rate, death rate, accuracy, stuck frequency | Medium | Essential for LLM agent to evaluate strategy effectiveness |
| Persistent state (database) | Surveys, maps, match metrics must survive restarts | Medium | SQLite replaces JSON/pickle files |
| Structured logging | Professional framework needs traceable debug streams | Low | structlog with JSON output |
| Configuration management | Tunable parameters without code changes | Low | pydantic-settings |
| Test suite | Framework needs automated tests for perception, navigation, combat, integration | High | pytest with game state fixtures |

---

## Differentiators

Features that make this bot competitive AND human-like. Not table stakes, but create real advantage. Informed by BotPrize competition results, DeepMind FTW architecture, anti-cheat research, and cognitive architecture patterns.

### Human-Likeness (BotPrize-Informed)

The BotPrize competition (2008-2012) was a Turing test for FPS bots in UT2004. Two bots passed in 2012: UT^2 (UT Austin, neuroevolution + human behavior modeling) and MirrorBot (Polceanu, opponent mimicry). Their findings are directly applicable to this project.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Aim humanization (imperfect accuracy) | Perfect aim is the number one bot detection signal. BotPrize winners deliberately constrained aim so rapid movements and long distances decrease accuracy. Anti-cheat research (VADNet, GAN-Aimbots, AntiCheatPT) confirms statistical aim patterns are the primary detection vector | Medium | Gaussian noise scaled by: target velocity, distance, recent turn rate. Human Q3 accuracy is roughly 30-60% |
| Reaction time modeling | Humans have 150-250ms visual reaction time. Instant reactions are immediately detectable. Research on adaptive shooting shows fixed delays feel artificial too -- need variable delays | Low | Configurable delay between perception and action. Surprised = 250ms+, expected = 150ms |
| Movement variability and imperfection | Humans overshoot corners, hesitate, change their mind mid-path. AAMAS 2025 research finding: bots that repeated same mistakes were quickly detected as non-human. Key insight: mistakes must be varied, not repetitive | Medium | Noise added to navigation waypoints. Occasional suboptimal path choice. Vary mistakes |
| Grudge/personality behavior | BotPrize critical finding: "humans tenaciously pursue specific opponents without regard for optimality." UT^2 modeled this. Bots that purely optimize are less believable than ones with irrational preferences | Medium | Track per-opponent interaction history. Sometimes chase a specific enemy even when suboptimal |
| Adaptive behavior (learning from deaths) | Humans learn mid-match. AAMAS 2025: "an agent keeping the same behavior even if it is clearly counter-productive breaks the illusion of being intelligent." Repeated same-pattern deaths are a strong non-human signal | High | Death location tracking, modify navigation cost weights. Gradually avoid death hotspots |
| Hesitation and decision pauses | Humans pause briefly when surprised or deciding between options. Instant state transitions feel robotic | Low | 100-300ms decision delay on state transitions, variable by situation urgency |

### Competitive Advantage (DeepMind FTW / Quake Pro Informed)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Item timing and spawn prediction | Top Q3 players time Mega Health (35s), Red Armor (25s), Quad Damage (120s). Controlling spawns wins matches. This single feature separates good bots from mediocre ones. Q3 pro gameplay revolves around item control | Medium | Track pickup timestamps, predict next spawn, navigate preemptively. High impact for moderate complexity |
| Map control strategy | Dominate high-value areas (rocket launcher spawn, mega health room, red armor platform). DeepMind FTW agents emerged with territorial control behavior without explicit programming | High | Assign area values based on item density + sight lines. Prefer positions with escape routes. Requires map analysis |
| Threat assessment model | Evaluate fight-or-flight based on own health/armor/weapon vs estimated enemy loadout. THREATBOT research showed this makes bots more competent and enjoyable opponents | Medium | Estimate enemy state from last observation (weapon fired, approximate health from combat exchange duration) |
| Predictive enemy tracking | Predict where enemy went after losing line of sight. Top players maintain mental model of all opponents | High | Last-known-position + velocity extrapolation + map topology. "Where would they go from there?" |
| Sound-based spatial awareness | React to off-screen audio cues: footsteps indicate direction, weapon fire reveals enemy position and weapon type. Provides 360-degree awareness beyond screen capture | Medium | Q3 engine logs sound events to console. Parse and localize |
| Multi-timescale decision architecture | Fast reflexes (aim, dodge at 10-22Hz) plus slow strategy (resource planning at ~0.25Hz via LLM). Both OpenAI Five and DeepMind FTW use explicit multi-timescale architectures with separate fast/slow processing paths | High | Already partially present (vision at 10-22 FPS, LLM at ~4s). Formalize as explicit fast/slow decision layers |

### Architecture Differentiators (TorchCraftAI / Cognitive Architecture Informed)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Blackboard pattern for module communication | TorchCraftAI proven pattern: modules post/consume tuples from shared blackboard. Loose coupling, easy module swapping. Used in StarCraft AI for over a decade | Medium | Fits brain-inspired architecture naturally. Better than direct module-to-module coupling |
| Configurable bot personalities | Q3 original bots had per-character traits (aggression, aim skill, reaction time). Makes bots diverse and unpredictable | Low | Parameter profiles: aggressive/cautious/balanced. Affects engagement range, retreat threshold, weapon preference |
| Replay and recording system | Record all bot decisions plus game state for analysis. Essential for debugging and improvement. Pogamut framework provided similar bot logging | Medium | Timestamped state + action log. Enable post-match analysis and LLM-driven strategy review |
| LLM-driven strategic reasoning | No other FPS bot framework integrates LLM for high-level strategy. Genuinely novel in the FPS bot domain | High | EXISTING via Ollama. LLM reasons about map state, opponent patterns, resource timing in natural language |
| Skill difficulty scaling | Adjustable competence from bumbling novice to competitive player. Useful for testing, entertainment, research | Low | Unified difficulty parameter scales aim noise, reaction delay, decision quality. Map to skill 1-5 like native Q3 bots |
| Hailo NPU YOLO detection | 95 FPS object detection on dedicated NPU frees CPU for decision-making. Running competitive bot AI on 75 dollar hardware is remarkable | Medium | Hardware available. Augments HSV detection with learned object detection for robustness |

---

## Anti-Features

Features to explicitly NOT build. Each would waste effort or actively harm the bot.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Perfect aim / aimbot-level accuracy | Instantly detectable as bot. Anti-cheat research (VADNet, GAN-Aimbots) shows statistical detection of superhuman aim patterns. Ruins human-likeness goal | Humanized aim with configurable skill levels. Even at max skill, cap accuracy below 70% |
| Pixel-perfect pathfinding (always optimal) | Humans do not run perfect paths. AAMAS 2025 and anti-cheat research (pathfinding analysis) flag perfectly smooth movement as bot signal | Add path noise, occasional suboptimal choices, corner overshoot |
| Global omniscient awareness | Knowing all enemy positions without seeing them is cheating. BWAPI explicitly enforces fog-of-war for competitive bots. Breaks vision-based perception design | Only use information from perception (screen capture + sound). Track last-known-positions with time decay |
| Chat/communication system | Out of scope per PROJECT.md. Not needed for deathmatch. Consumes LLM budget | Focus LLM tokens on strategic decisions only |
| Multi-agent coordination | Out of scope per PROJECT.md. DeepMind FTW main innovation was team play -- massive complexity not relevant for solo deathmatch | Single bot, deathmatch mode only for v1 |
| End-to-end neural network control | DeepMind FTW needed 12,000 CPU cores plus 50 GPUs for training. Not feasible on Pi. Not debuggable. Not controllable by LLM | Hybrid: learned perception + engineered decisions + LLM strategy |
| Real-time audio ML processing | Audio ML models are compute-heavy. Q3 sound events available as structured text from console | Parse game engine text events, not raw audio |
| Complex emotion/mood modeling | Academic interest (ConsScale FPS) but overkill for deathmatch. Adds complexity without competitive benefit | Simple personality parameters (aggression, caution) are sufficient |
| Self-play training loop | OpenAI Five needed 10 months on 256 GPUs. Not feasible on Pi | Hand-tuned parameters refined via replay analysis. LLM reasons about improvement |
| Desktop mouse/keyboard input | Unreliable, OS-dependent, conflicts with user input | Named pipe injection only (EXISTING correct decision) |
| Plugin system for other games | OpenArena only for v1 per PROJECT.md. Premature abstraction | Clean interfaces that could extend later, no plugin API now |

---

## Feature Dependencies

```
Perception Layer (must exist first):
  Enemy Detection --> Target Acquisition --> Aim Control
  Enemy Detection --> Multi-Target Tracking --> Threat Assessment
  HUD Parsing --> Engagement/Disengage Decisions
  HUD Parsing --> Weapon Selection
  Distance Estimation --> Weapon Selection
  Distance Estimation --> Lead Prediction
  Sound Awareness --> Off-Screen Threat Detection

Navigation Layer (requires perception):
  AAS Pathfinding --> Item Location Knowledge --> Item Timing
  AAS Pathfinding --> Combat Movement (pathfind while fighting)
  Stuck Detection --> Stuck Recovery
  Room Surveys --> Map Knowledge --> Map Control Strategy

Combat Layer (requires perception + navigation):
  Target Acquisition --> Aim Control --> Aim Humanization
  Weapon Selection --> Engagement Decisions
  Combat Movement --> Strafing/Dodging Patterns
  Threat Assessment --> Fight/Flight Decisions

Decision Layer (requires all above):
  State Machine/BT --> Priority Goal Selection
  Reactive Interrupts --> State Machine (can override any state)
  Item Timing --> Map Control Strategy
  Threat Assessment --> Engagement Decisions
  LLM Strategy --> Mission-Level Goals
  Multi-Timescale --> Separates reflex vs strategic decisions

Human-Likeness Layer (overlays everything):
  Aim Humanization --> overlays Aim Control
  Reaction Time Modeling --> overlays all perception-to-action paths
  Movement Variability --> overlays Navigation
  Personality/Grudge --> overlays Decision Making
  Adaptive Learning --> modifies Navigation + Decision weights

Framework Layer (wraps everything):
  Skill System (actions/behaviors/missions) --> composes all above
  Blackboard --> enables module communication
  FastAPI --> exposes Skill System to LLM agents
  Metrics --> observes all layers
  Replay System --> records all layers
  Config Management --> parameterizes all layers
  Database --> persists state across all layers
```

---

## MVP Recommendation

### Phase 1: Core Framework and Existing Feature Integration
Restructure what exists into the three-layer skill system:
1. **Atomic actions** extracted from existing perception, navigation, combat code
2. **Behaviors** composed from actions (e.g., "engage_enemy" = detect + aim + fire + strafe)
3. **Blackboard** for inter-module communication (brain-inspired shared awareness)
4. **FastAPI endpoints** exposing behaviors to LLM agents
5. **Metrics collection** (frag rate, death rate, accuracy)
6. **Database** (SQLite replaces JSON/pickle)
7. **Configuration management** and **structured logging**
8. **Test suite** for core subsystems

### Phase 2: Competitive Features
9. **Item timing and spawn prediction** -- biggest competitive ROI for moderate complexity
10. **Threat assessment model** -- fight-or-flight decisions
11. **Sound awareness** -- parse Q3 console for sound events
12. **Reactive interrupt layer** -- reflexes override strategy (subsumption)
13. **Respawn handling** -- immediate post-death recovery behavior

### Phase 3: Human-Likeness
14. **Aim humanization** -- gaussian noise scaled by context
15. **Reaction time modeling** -- configurable variable delays
16. **Movement variability** -- path noise, hesitation, corner overshoot
17. **Bot personality profiles** -- aggression, caution, grudge parameters
18. **Adaptive learning from deaths** -- avoid repeat death patterns
19. **Grudge behavior** -- personality-driven irrational target selection

### Phase 4: Advanced Strategy
20. **Map control strategy** -- area value scoring, territorial behavior
21. **Predictive enemy tracking** -- last-known-position extrapolation
22. **LLM mission system** -- strategic goal generation and adaptation
23. **Replay/recording system** for post-match analysis
24. **Skill difficulty scaling** -- unified difficulty parameter

**Defer indefinitely:** Multi-agent coordination, self-play training, end-to-end neural control, emotion modeling, plugin system, chat integration. Out of scope or infeasible on Pi.

---

## Sources

### Academic / Research
- [DeepMind FTW: Human-level performance in first-person multiplayer games](https://arxiv.org/pdf/1807.01281) - Multi-timescale architecture, internal reward learning
- [BotPrize / Computer Game Bot Turing Test](https://en.wikipedia.org/wiki/Computer_game_bot_Turing_test) - Human-likeness evaluation for FPS bots
- [UT^2 Bot Passed BotPrize 2012](https://news.utexas.edu/2012/09/26/artificially-intelligent-game-bots-pass-the-turing-test-on-turings-centenary/) - Neuroevolution, grudge behavior, aim constraints
- [OpenAI Five: Dota 2 with Large Scale Deep RL](https://arxiv.org/abs/1912.06680) - Reward shaping, multi-timescale decisions
- [THREATBOT: Improving FPS Experiences](https://eprints.qut.edu.au/90077/1/David_Conroy_Thesis.pdf) - Threat assessment models
- [Human-like Bots for Tactical Shooters](https://arxiv.org/html/2501.00078v1) - Compute-efficient sensors, believability evaluation
- [Adaptive Shooting for Bots in FPS Games](https://arxiv.org/pdf/1806.05554) - Learned vs handicapped shooting
- [The Many Challenges of Human-Like Agents (AAMAS 2025)](https://arxiv.org/html/2505.20011v1) - Comprehensive believability challenges
- [GAN-Aimbots: ML for Cheating in FPS](https://arxiv.org/pdf/2205.07060) - How ML aim is detected
- [VADNet: Visual Anti-Cheating Detection](https://www.iieta.org/journals/ts/paper/10.18280/ts.410137) - Bot aim detection methods
- [ACT-R and SOAR Comparison](https://arxiv.org/abs/2201.09305) - Cognitive architecture design patterns
- [Navigates Like Me (CHI 2023)](https://dl.acm.org/doi/fullHtml/10.1145/3544548.3581348) - Human-likeness evaluation in navigation

### Framework / Implementation
- [Quake III Arena Bot Architecture (Fabien Sanglard)](https://fabiensanglard.net/quake3/a.i.php) - Original Q3 bot source, behavior selector
- [The Quake III Arena Bot (van Waveren)](https://www.researchgate.net/publication/240430519_The_Quake_III_Arena_Bot) - Production rules, character traits
- [TorchCraftAI Architecture](https://torchcraft.github.io/TorchCraftAI/docs/architecture.html) - Blackboard pattern, module system
- [BWAPI Framework](https://bwapi.github.io/) - Fog-of-war enforcement, micro/macro separation
- [Pogamut 3 Framework](https://www.researchgate.net/publication/221611519_Pogamut_3_Can_Assist_Developers_in_Building_AI_Not_Only_for_Their_Videogame_Agents) - High/low level bot API
- [Intelligent Mistakes in AI Code](https://www.gamedeveloper.com/programming/intelligent-mistakes-how-to-incorporate-stupidity-into-your-ai-code) - Practical believable imperfection
- [Behavior Trees for Computer Games](https://www.researchgate.net/publication/312869797_Behavior_Trees_for_Computer_Games) - BT vs FSM trade-offs

### Anti-Cheat / Detection
- [Cheating Detection in FPS Games (SPIE 2024)](https://www.spiedigitallibrary.org/conference-proceedings-of-spie/13562/1356233/Advancements-in-cheating-detection-algorithms-in-FPS-games/10.1117/12.3061748.full) - Movement and aim pattern detection
- [AntiCheatPT: Transformer Cheat Detection](https://arxiv.org/html/2508.06348v1) - Sequential behavior analysis
- [Identify As A Human Does: Next-Gen Anti-Cheat](https://arxiv.org/html/2409.14830v2) - Pathfinding-based bot detection
