# Domain Pitfalls

**Domain:** Brain-inspired FPS AI bot management framework
**Researched:** 2026-04-08

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: Big Bang Refactor
**What goes wrong:** Attempting to restructure all 26 modules into the new folder structure in one phase. Nothing works until everything works.
**Why it happens:** The brain-inspired structure is the goal, so it feels natural to do it all at once.
**Consequences:** Weeks of broken bot. Cannot test incrementally. Regressions hide in the noise. Motivation dies.
**Prevention:** Move one subsystem at a time. After each move, the bot must still run and play. Use re-exports from the old locations during transition (thin `__init__.py` files that import from new locations).
**Detection:** If you cannot run `python play.py` after a day of refactoring, you are doing a big bang.

### Pitfall 2: Over-Abstracting the Event Bus
**What goes wrong:** Building a complex pub/sub system with middleware, filters, replay, persistence before any subsystem uses it.
**Why it happens:** The architecture diagram looks clean with an event bus connecting everything. Tempting to build the bus first.
**Consequences:** The bus API does not match what subsystems actually need. Rework the bus after discovering real requirements. Performance overhead from unnecessary generality.
**Prevention:** Start with direct function calls between subsystems. Introduce the event bus only when you have two or more concrete cases of subsystems needing to communicate asynchronously. Let the interface emerge from usage.
**Detection:** If the event bus has more lines of code than any subsystem using it, it is over-engineered.

### Pitfall 3: Breaking the Tick Budget
**What goes wrong:** Adding architectural overhead (event serialization, deep copy of awareness snapshots, logging, metrics) that pushes tick time above 50ms, dropping below 20 FPS.
**Why it happens:** Each layer adds "just a little" overhead. Death by a thousand cuts on Pi hardware.
**Consequences:** Bot becomes sluggish, loses fights it used to win, perception pipeline misses enemies.
**Prevention:** Profile every architectural addition on Pi hardware, not desktop. Set a hard tick budget alarm (log warning if tick > 50ms). Use `frozen=True` dataclasses instead of deep copy. Avoid serialization in the hot path.
**Detection:** Monitor `tick_time_ms` as a first-class metric from day one.

### Pitfall 4: Async Deadlocks from Mixed Sync/Async
**What goes wrong:** The tick loop is sync (blocking OpenCV calls), FastAPI is async, LLM calls are async. Mixing them incorrectly deadlocks the event loop or starves the tick loop.
**Why it happens:** Python asyncio is cooperative -- one blocking call freezes everything. OpenCV operations block.
**Consequences:** Bot freezes for seconds. API becomes unresponsive. LLM responses arrive too late.
**Prevention:** Keep OpenCV in the sync tick path (it is fast enough at 7-10ms). Run the tick loop as a repeating `asyncio.create_task` with `asyncio.sleep(0)` yields between phases. Never `await` anything slow in the tick path. LLM and DB operations run in separate coroutines.
**Detection:** If the API stops responding during heavy combat, the event loop is blocked.

### Pitfall 5: Losing the God Object's Implicit Knowledge
**What goes wrong:** The current `strategic_brain.py` contains implicit coordination logic embedded in its 700+ lines -- state transition guards, timing heuristics, edge case handling. Splitting it into subsystems loses these hidden dependencies.
**Why it happens:** The god object "just works" because everything is in one place. Extracting subsystems requires understanding ALL the implicit contracts.
**Consequences:** Subtle behavior regressions. Bot gets stuck in states it never got stuck in before. Combat and navigation interfere with each other.
**Prevention:** Before splitting `strategic_brain.py`, write characterization tests that capture its current behavior: given this SituationalAwareness, what state transition happens? What commands are sent? These tests become the regression safety net.
**Detection:** If the bot's win rate drops after restructuring with no logic changes, implicit coordination was lost.

## Moderate Pitfalls

### Pitfall 1: Premature Database Migration
**What goes wrong:** Migrating from JSON/pickle to SQLite before the folder structure is stable.
**Prevention:** Keep the current file-based persistence during the restructure. Add a `storage.py` interface in `memory/` that abstracts the backend. Swap to SQLite after the architecture is settled.

### Pitfall 2: Testing the Architecture Instead of Behavior
**What goes wrong:** Writing tests that verify "perception module sends event to event bus" rather than "bot detects enemy at 400px from center and fires."
**Prevention:** Write behavior-level integration tests first: given a captured frame, does the full pipeline produce the correct commands? Unit test subsystem internals only where logic is complex (weapon selection, pathfinding).

### Pitfall 3: Circular Import Hell
**What goes wrong:** Brain-inspired modules importing each other creates circular dependency chains that Python cannot resolve.
**Prevention:** Enforce a strict import direction: brainstem <- perception <- memory <- reflexes/combat/navigation <- tactics <- strategy <- api. No backward imports. Use dependency injection (pass interfaces at construction time) instead of importing peer modules.

### Pitfall 4: WebSocket State Flooding
**What goes wrong:** Streaming full SituationalAwareness at 20 FPS over WebSocket overwhelms the client and the Pi's network stack.
**Prevention:** Stream at a reduced rate (2-5 Hz) with delta compression. Only send changed fields. Let the client request full snapshots on demand.

### Pitfall 5: Skill System Scope Creep
**What goes wrong:** The three-layer skill system (actions/behaviors/missions) becomes a framework-within-a-framework with its own execution engine, scheduling, and error handling.
**Prevention:** Skills are just Python functions with a standard signature. An action is `async def move_forward(controller, duration)`. A behavior calls actions in sequence. A mission calls behaviors. No execution engine needed.

## Minor Pitfalls

### Pitfall 1: Naming Confusion Between Brain Metaphor and Code
**What goes wrong:** Developers cannot find code because they think in code terms (e.g., "pathfinding") but the folder is named in brain terms ("hippocampus").
**Prevention:** Use functional names for folders (`navigation/`, `combat/`, `perception/`), not anatomical names. Document the brain-region mapping in a README, but do not make it the filesystem.

### Pitfall 2: Config Fragmentation
**What goes wrong:** Each subsystem has its own config file/format. Changing a shared parameter (like screen resolution) requires editing 5 files.
**Prevention:** Single `brain/config.py` with subsystem-specific sections. Each subsystem receives only its relevant config slice at construction time.

### Pitfall 3: Forgetting Root-Level Script Cleanup
**What goes wrong:** The 14 root-level scripts (play.py, loop.py, capture.py, etc.) continue to exist alongside the new structure, causing confusion about which version is canonical.
**Prevention:** Add a deprecation phase: root scripts become thin wrappers that import from the package. Then remove them in a later phase.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Foundation (brainstem + config) | Seems too simple, tempted to skip | This is the base everything depends on. Get it right. |
| Perception extraction | Performance regression from added layers | Profile on Pi before and after. Track tick_time_ms. |
| Memory system | Over-engineering the storage layer | Start with in-memory dict + file dump. SQLite comes later. |
| Reflex extraction | Missing edge cases from strategic_brain | Write characterization tests for damage/stuck/death handling first. |
| Combat extraction | Aim controller coupling to tick timing | Verify aim PID constants work at the same tick rate after extraction. |
| Navigation extraction | Learned map state not transferring | Ensure learned_map hooks (edge_cost_fn, on_area_transition) survive the split. |
| Tactics (FSM) extraction | State transition logic scattered across strategic_brain | Map ALL state transitions before extracting. Draw the FSM diagram. |
| Strategy (LLM) extraction | Async timing assumptions change | LLM task must remain truly independent of tick loop timing. |
| Skills system | Scope creep into execution engine | Skills are functions, not objects with lifecycle. Keep it simple. |
| API layer | Blocking the tick loop | FastAPI runs alongside, never inside, the tick loop. |

## Sources

- Existing codebase analysis: `strategic_brain.py` god object pattern, import graph
- [Subsumption Architecture](https://en.wikipedia.org/wiki/Subsumption_architecture) - Layer priority and override pitfalls
- [FastAPI Async](https://fastapi.tiangolo.com/async/) - Event loop blocking risks
- Common Python refactoring patterns: circular imports, big bang rewrites
