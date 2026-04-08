# Phase 4: Reflexes, Combat, and Navigation Extraction - Research

**Researched:** 2026-04-08
**Domain:** God object decomposition, subsumption architecture, FPS bot behavioral systems
**Confidence:** HIGH

## Summary

Phase 4 is the most complex extraction phase in the project. It decomposes the 681-line `strategic_brain.py` god object into three peer subsystem modules (`reflexes/`, `combat/`, `navigation/`) that consume `SituationalAwareness` snapshots and memory interfaces but have NO cross-imports between them. The extraction is primarily a move-and-refactor operation: most combat and navigation code already exists as standalone modules (`combat.py`, `aim_controller.py`, `navigator.py`, `aas_parser.py`, `learned_map.py`, `exit_finder.py`, `room_surveyor.py`, `commander.py`). The reflexes subsystem is new -- it extracts the reactive behaviors currently embedded in `strategic_brain.py`'s FSM transition logic and state handlers.

The key challenge is preserving the implicit subsumption priority order (DEAD > COMBAT > STUCK > PICKUP > DOOR > SURVEY > NAVIGATE > EXPLORE) that is currently encoded in `_evaluate_transitions()`. After extraction, each peer subsystem must be independently testable and the characterization tests from Phase 1 must continue to pass against the new structure. The brainstem modules (`game_bridge.py`, `virtual_controller.py`, `actions.py`) stay in their current location for now -- they are the I/O layer that all three peer subsystems write through.

**Primary recommendation:** Extract in three sequential waves -- (1) reflexes (smallest, cleanest extraction), (2) combat (move existing modules + extract state handlers), (3) navigation (move existing modules + extract state handlers) -- with characterization tests green after each wave.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RFLX-01 | Damage response instant reactive behavior (<1ms) | Method Map: `_tick_combat` damage-snap logic + DamageTracker; Architecture: reflex arc pattern |
| RFLX-02 | Death handling -- clean state reset and respawn recovery | Method Map: `_tick_dead` + `_on_enter_state(DEAD)` extraction |
| RFLX-03 | Stuck escape -- subsumption override when movement fails | Method Map: `_tick_stuck` + Navigator.handle_stuck + exit_finder.find_exit |
| RFLX-04 | Reactive interrupt layer -- higher-priority suppress lower-priority | Architecture: SubsumptionArbiter pattern; `_evaluate_transitions()` priority chain |
| CMBT-01 | Target acquisition -- snap to nearest threat from perception | Method Map: `_tick_combat` attacker_direction snap; AimController.update |
| CMBT-02 | PID aim control with lead prediction (existing) | Existing: aim_controller.py -- move to combat/ |
| CMBT-03 | Fuzzy weapon selection (existing) | Existing: combat.py select_weapon() -- move to combat/ |
| CMBT-04 | Combat movement -- circle strafing, dodge (existing) | Existing: combat.py CombatMover -- move to combat/ |
| CMBT-05 | Engagement/disengage decisions | Existing: combat.py evaluate_threat() + FSM COMBAT->NAVIGATING return transition |
| CMBT-06 | Weapon switch timing -- preemptive switch before empty | New: add ammo monitoring to combat subsystem |
| CMBT-07 | Threat assessment model | Existing: combat.py evaluate_threat() -- promote to own module |
| NAV-01 | AAS pathfinding (existing) | Existing: navigator.py + aas_parser.py -- move to navigation/ |
| NAV-02 | Stuck detection and recovery (existing) | Existing: navigator.py handle_stuck + exit_finder.py -- move to navigation/ |
| NAV-03 | Learned map with occupancy grid (existing) | Existing: learned_map.py -- move to navigation/ |
| NAV-04 | Room surveyor 360-degree documentation (existing) | Existing: room_surveyor.py -- move to navigation/ |
| NAV-05 | Obstacle avoidance during combat | New: combat movement needs wall_ahead awareness from SituationalAwareness |
| NAV-06 | Respawn handling -- immediate navigation after death | Method Map: DEAD->EXPLORING transition + path_to_random on enter |
</phase_requirements>

## Standard Stack

### Core (Phase 4 -- no new dependencies)

Phase 4 adds ZERO new library dependencies. It is purely a code reorganization phase using existing Python modules.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.13.12 | Runtime | Already installed, validated on Pi [VERIFIED: Phase 1 research] |
| pytest | >=8.0 | Test framework | Characterization tests already exist [VERIFIED: tests/ directory] |
| structlog | >=24.0 | Structured logging | Already configured in Phase 1 [VERIFIED: logging_config.py exists] |

### Supporting

No additional libraries needed. All subsystem code uses stdlib (math, time, dataclasses, enum, collections, heapq, re, json, os) plus numpy and cv2 which are already installed.

## Architecture Patterns

### Method-to-Subsystem Mapping (strategic_brain.py)

This is the critical decomposition map. Every method and attribute in `StrategicBrain` (681 lines) is assigned to exactly one target subsystem. [VERIFIED: full read of strategic_brain.py]

#### Reflexes Subsystem (reflexes/)

| Source | Method/Attribute | Target Module | Notes |
|--------|-----------------|---------------|-------|
| strategic_brain.py | `_tick_dead()` | `reflexes/death_handler.py` | Death detection, state reset, respawn tap |
| strategic_brain.py | `_tick_stuck()` | `reflexes/stuck_escape.py` | Delegates to navigator.handle_stuck |
| strategic_brain.py | `_on_enter_state(DEAD)` | `reflexes/death_handler.py` | Deaths counter, release_all, tracker resets |
| strategic_brain.py | `_on_enter_state(STUCK)` | `reflexes/stuck_escape.py` | Blacklist logic for stuck targets |
| strategic_brain.py | `_on_exit_state(*)` | `reflexes/__init__.py` | Look action cleanup (centerview) |
| strategic_brain.py | P1-P3 in `_evaluate_transitions()` | `reflexes/arbiter.py` | DEAD, COMBAT, STUCK priority checks |
| DamageTracker (perception/) | `update()`, `attacker_direction` | Consumed by reflexes | Already in perception/, read-only |

#### Combat Subsystem (combat/)

| Source | Method/Attribute | Target Module | Notes |
|--------|-----------------|---------------|-------|
| strategic_brain.py | `_tick_combat()` | `combat/engage.py` | Attacker snap, forward, strafe, fire |
| strategic_brain.py | `_on_enter_state(COMBAT)` | `combat/engage.py` | Fire start |
| strategic_brain.py | `_on_exit_state(COMBAT)` | `combat/engage.py` | Fire stop, strafe release |
| combat.py | `CombatMover` | `combat/combat_movement.py` | Move from root (already exists) |
| combat.py | `select_weapon()` | `combat/weapon_select.py` | Move from root |
| combat.py | `evaluate_threat()` | `combat/threat_assess.py` | Move from root |
| combat.py | `aim_lead()` | `combat/weapon_select.py` | Move from root |
| combat.py | `WEAPONS`, `WeaponInfo` | `combat/weapons.py` | Move from root |
| aim_controller.py | `AimController`, `AimProfile`, `PROFILES` | `combat/aim_controller.py` | Move from root |

#### Navigation Subsystem (navigation/)

| Source | Method/Attribute | Target Module | Notes |
|--------|-----------------|---------------|-------|
| strategic_brain.py | `_tick_navigating()` | `navigation/nav_behavior.py` | Commander + path following + bunny hop |
| strategic_brain.py | `_tick_exploring()` | `navigation/nav_behavior.py` | Random path following |
| strategic_brain.py | `_tick_surveying()` | `navigation/survey_behavior.py` | Room survey trigger |
| strategic_brain.py | `_tick_traversing_door()` | `navigation/nav_behavior.py` | Wall avoidance turn |
| strategic_brain.py | `_tick_picking_up_item()` | `navigation/nav_behavior.py` | Anomaly tracking pickup |
| navigator.py | `Navigator` | `navigation/navigator.py` | Move from root |
| aas_parser.py | `AASGraph`, `parse_aas` | `navigation/aas_parser.py` | Move from root |
| learned_map.py | `LearnedMap` | `navigation/learned_map.py` | Move from root |
| exit_finder.py | `find_exit`, `score_frame_openness` | `navigation/exit_finder.py` | Move from root |
| room_surveyor.py | `RoomSurveyor`, `RoomSurvey` | `navigation/room_surveyor.py` | Move from root |
| commander.py | `Commander`, `ItemMemory` | `navigation/commander.py` | Move from root (item prioritization = nav concern) |

#### Stays in Place

| Module | Reason |
|--------|--------|
| `models.py` (BrainState, SituationalAwareness, SpatialKnowledge) | Shared data contracts -- consumed by all subsystems |
| `game_bridge.py` | Brainstem I/O -- stays at root until Phase 5+ |
| `virtual_controller.py` | Brainstem motor output -- stays at root |
| `actions.py` | Brainstem pynput input -- stays at root |
| `game_state.py` | Shared data contract |
| `perception/` | Already extracted in Phase 2 |
| `memory/` | Already extracted in Phase 3 |
| `strategic_brain.py` | Remains as thin orchestrator until Phase 5 strips it further |

### Target Directory Structure

```
openarena_perception/
  reflexes/
    __init__.py           # Re-exports: DeathHandler, StuckEscape, SubsumptionArbiter
    death_handler.py      # RFLX-01, RFLX-02: death detection, respawn, state reset
    stuck_escape.py       # RFLX-03: stuck handling, target blacklisting
    arbiter.py            # RFLX-04: subsumption priority evaluation

  combat/
    __init__.py           # Re-exports: CombatSystem, AimController, select_weapon, etc.
    weapons.py            # WEAPONS dict, WeaponInfo dataclass
    weapon_select.py      # CMBT-03, CMBT-06: fuzzy selection + aim_lead
    aim_controller.py     # CMBT-02: PID aim tracking (moved from root)
    combat_movement.py    # CMBT-04: CombatMover circle strafe/dodge
    engage.py             # CMBT-01, CMBT-05: engagement logic from _tick_combat
    threat_assess.py      # CMBT-07: evaluate_threat + threat model

  navigation/
    __init__.py           # Re-exports: Navigator, LearnedMap, RoomSurveyor, etc.
    aas_parser.py         # NAV-01: AAS file parser (moved from root)
    navigator.py          # NAV-01, NAV-02: A* pathfinding + stuck detection
    learned_map.py        # NAV-03: occupancy grid + edge costs
    exit_finder.py        # NAV-02: scan-and-probe stuck recovery
    room_surveyor.py      # NAV-04: 360-degree room documentation
    commander.py          # Item prioritization and goal selection
    nav_behavior.py       # NAV-05, NAV-06: navigating/exploring/door/pickup behaviors
    survey_behavior.py    # NAV-04: surveying state behavior
```

### Pattern 1: Subsumption Arbiter

**What:** Centralize the priority evaluation from `_evaluate_transitions()` into a reusable arbiter that each subsystem can query.

**When:** Every tick, the orchestrator asks the arbiter "what subsystem should run?"

**Why:** The current priority chain (lines 325-396 of strategic_brain.py) is the core subsumption logic. It must be preserved exactly to keep characterization tests passing.

```python
# reflexes/arbiter.py
from openarena_perception.models import BrainState, SituationalAwareness

class SubsumptionArbiter:
    """Priority-based state transition evaluator.
    
    Extracted from StrategicBrain._evaluate_transitions().
    Preserves exact same priority order and transition conditions.
    """
    
    def evaluate(self, sa: SituationalAwareness, current_state: BrainState,
                 state_time: float, **context) -> BrainState:
        """Return the state that should be active given current awareness.
        
        Priority order: DEAD > COMBAT > STUCK > PICKUP > DOOR > SURVEY
        Then return transitions for each active state.
        """
        # P1: Dead -- highest priority
        if not sa.is_alive:
            return BrainState.DEAD
            
        # P2: Combat
        if (sa.under_attack and sa.enemies_visible > 0 and
                current_state != BrainState.DEAD):
            return BrainState.COMBAT
            
        # P3: Stuck (not from DEAD, COMBAT, SURVEYING)
        if (sa.is_stuck and not sa.is_recovering and
                current_state not in (BrainState.DEAD, BrainState.COMBAT,
                                      BrainState.SURVEYING)):
            return BrainState.STUCK
            
        # ... remaining priorities preserved exactly
        return current_state
```

[VERIFIED: exact logic from strategic_brain.py lines 325-396]

### Pattern 2: Re-export Shims for Backward Compatibility

**What:** After moving a module (e.g., `combat.py` -> `combat/weapons.py`), leave a re-export shim at the old location so existing imports don't break.

**When:** Every module move.

**Why:** `reactive_agent.py`, `strategic_brain.py`, and characterization tests all import from the old locations. The shim approach was proven in Phase 1 (combat/ `__init__.py` already uses this pattern) and Phase 2 (perception/ extraction).

```python
# openarena_perception/combat.py (becomes shim after extraction)
"""DEPRECATED: Use openarena_perception.combat instead."""
from openarena_perception.combat.weapons import WEAPONS, WeaponInfo
from openarena_perception.combat.weapon_select import select_weapon, aim_lead
from openarena_perception.combat.threat_assess import evaluate_threat
from openarena_perception.combat.combat_movement import CombatMover
```

[VERIFIED: same pattern used for damage_tracker.py shim and perception/ __init__.py]

### Pattern 3: Subsystem Interface -- Read SituationalAwareness, Write Through Controller

**What:** Each subsystem follows the same interface pattern: receive a `SituationalAwareness` snapshot (read-only), produce commands through `VirtualController` or `GameBridge` (write-only). No subsystem reads another subsystem's internal state.

**When:** All subsystem tick methods.

**Why:** Prevents circular dependencies. The god object currently mediates all communication -- after extraction, `SituationalAwareness` is the shared data bus.

```python
# Example: combat/engage.py
class CombatEngager:
    def __init__(self, ctrl: VirtualController, combat_mover: CombatMover):
        self.ctrl = ctrl
        self.combat_mover = combat_mover
    
    def tick(self, sa: SituationalAwareness, gs: GameState):
        """Execute combat behavior for one tick."""
        # Snap aim toward attacker
        if sa.attacker_direction != 0 and sa.seconds_since_damage < 0.3:
            self.ctrl.turn_degrees(-sa.attacker_direction * 15)
        
        # Move aggressively
        self.ctrl.forward(True)
        move = self.combat_mover.get_movement(300, 'machinegun', 0.9)
        self.ctrl.strafe_left(move['strafe_left'])
        self.ctrl.strafe_right(move['strafe_right'])
        if move['jump']:
            self.ctrl.jump()
```

### Anti-Patterns to Avoid

- **Cross-subsystem imports:** `combat/engage.py` must NEVER import from `navigation/`. Communication only through SituationalAwareness or the orchestrator.
- **Moving the FSM states into subsystems:** BrainState enum stays in `models.py`. The arbiter evaluates transitions; individual subsystems don't know about other subsystems' states.
- **Extracting too much from strategic_brain.py at once:** Keep the orchestrator (`tick()`, state dispatch, HUD export) in strategic_brain.py during Phase 4. Phase 5 extracts the FSM into `tactics/`.
- **Breaking the characterization tests:** Every wave must end with `pytest tests/test_strategic_brain_characterization.py` green.

## Import Dependency Graph After Extraction

```
models.py (BrainState, SituationalAwareness, SpatialKnowledge)
  ^            ^              ^
  |            |              |
reflexes/    combat/       navigation/
  |            |              |
  v            v              v
game_bridge.py / virtual_controller.py (brainstem -- stays at root)
  ^
  |
strategic_brain.py (thin orchestrator -- imports all three subsystems)
```

**Import rules (enforced):**
1. `reflexes/`, `combat/`, `navigation/` may import from `models.py`
2. `reflexes/`, `combat/`, `navigation/` may import from brainstem modules at root
3. `navigation/` may import from `navigation/aas_parser.py` (internal dependency)
4. NO cross-imports between `reflexes/`, `combat/`, `navigation/`
5. `strategic_brain.py` imports from all three (it is the orchestrator)
6. Root-level shim files (`combat.py`, `navigator.py`, etc.) re-export from subdirectories

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Priority evaluation | Custom priority queues | SubsumptionArbiter (extracted `_evaluate_transitions`) | The existing logic has edge cases captured by 15+ characterization tests |
| Backward-compat imports | sys.path hacks | `__init__.py` re-exports + root shim files | Phase 1/2 proved this pattern works |
| A* pathfinding | New pathfinding | Existing Navigator._astar | Already handles swim avoidance, learned edge costs, height penalties |
| PID aim tracking | New aim system | Existing AimController with weapon profiles | Tuned PID gains per weapon, velocity estimation, deadzone |
| Weapon selection | Rewrite fuzzy logic | Existing select_weapon() | van Waveren thesis-based fuzzy matching already works |

## Common Pitfalls

### Pitfall 1: Breaking the CombatMover Re-export Chain

**What goes wrong:** The `combat/` directory already has an `__init__.py` that uses importlib to load `combat.py` and re-export `CombatMover`. When we move `combat.py`'s contents into `combat/` subdirectories, this importlib hack must be replaced with clean imports.
**Why it happens:** Phase 1 created the `combat/__init__.py` with an importlib workaround because the directory name shadows the .py file.
**How to avoid:** Replace the importlib hack in `combat/__init__.py` with direct imports from the new submodules. Delete the root `combat.py` file (or convert to shim). Test that `from openarena_perception.combat import CombatMover` still works.
**Warning signs:** `ImportError` or `ModuleNotFoundError` in any test.

### Pitfall 2: Navigator's Callback Hooks to strategic_brain.py

**What goes wrong:** `Navigator` has callback attributes (`_edge_cost_fn`, `_on_area_transition`) that `StrategicBrain.__init__()` wires up to `LearnedMap`. After extraction, these hooks must still be connected.
**Why it happens:** The navigator currently has bidirectional coupling with strategic_brain via these callbacks.
**How to avoid:** Have the navigation subsystem's `__init__` wire `LearnedMap.edge_penalty` into `Navigator._edge_cost_fn` internally. The orchestrator (strategic_brain.py) just passes the map_name and aas_graph, and the navigation subsystem handles its own wiring.
**Warning signs:** Edge penalties stop working (bot repeatedly tries failed paths).

### Pitfall 3: Timing Constants Coupled to Tick Rate

**What goes wrong:** Combat movement timing (`_switch_interval`, `_last_jump` cooldowns) and stuck detection (`STUCK_COUNT`, `POS_INTERVAL`) rely on consistent tick rates. If extraction changes when these are called, behavior changes.
**How to avoid:** Use `time.time()` / `time.perf_counter()` for all timing (already done in existing code). Do not change tick call frequency during extraction.
**Warning signs:** Combat strafing patterns change frequency; stuck detection becomes overly sensitive or insensitive.

### Pitfall 4: Forgetting the State Entry/Exit Side Effects

**What goes wrong:** `_on_enter_state()` and `_on_exit_state()` have critical side effects (release_all on death, fire start/stop on combat enter/exit, centerview on exit). If these are not extracted alongside the tick handlers, the bot gets stuck in states.
**Why it happens:** Side effects are spread across two methods that handle ALL states -- easy to miss one.
**How to avoid:** Map every state's enter/exit effects explicitly (done above in the Method Map). Each subsystem's enter/exit is part of its module, not a separate concern.
**Warning signs:** Bot keeps firing after leaving combat. Bot keeps looking up/down after leaving a state. Stuck recovery doesn't release movement keys.

### Pitfall 5: SpatialKnowledge Ownership Ambiguity

**What goes wrong:** `SpatialKnowledge` is used for room surveys (navigation concern) but also for danger zone tracking (reflexes concern). Putting it in one subsystem creates a cross-import.
**Why it happens:** It is a mixed-concern class in `models.py`.
**How to avoid:** Keep `SpatialKnowledge` in `models.py` (shared data contract, like SituationalAwareness). Both navigation and reflexes read/write it, but neither owns it. The orchestrator passes it to whoever needs it.
**Warning signs:** Circular import between reflexes/ and navigation/.

## Code Examples

### Verified: Strategic Brain tick() Dispatch (Current)

This is what the orchestrator looks like today. After Phase 4, it will dispatch to subsystem modules instead of internal methods:

```python
# strategic_brain.py current dispatch (lines 266-276)
handlers = {
    BrainState.DEAD: self._tick_dead,
    BrainState.COMBAT: self._tick_combat,
    BrainState.STUCK: self._tick_stuck,
    BrainState.SURVEYING: self._tick_surveying,
    BrainState.NAVIGATING: self._tick_navigating,
    BrainState.EXPLORING: self._tick_exploring,
    BrainState.TRAVERSING_DOOR: self._tick_traversing_door,
    BrainState.PICKING_UP_ITEM: self._tick_picking_up_item,
}
await handlers[self._state](sa, gs)
```

After Phase 4, the dispatch becomes:

```python
# strategic_brain.py post-Phase-4 dispatch
handlers = {
    BrainState.DEAD: self._reflexes.death_handler.tick,
    BrainState.COMBAT: self._combat.engager.tick,
    BrainState.STUCK: self._reflexes.stuck_escape.tick,
    BrainState.SURVEYING: self._navigation.survey_behavior.tick,
    BrainState.NAVIGATING: self._navigation.nav_behavior.tick_navigating,
    BrainState.EXPLORING: self._navigation.nav_behavior.tick_exploring,
    BrainState.TRAVERSING_DOOR: self._navigation.nav_behavior.tick_door,
    BrainState.PICKING_UP_ITEM: self._navigation.nav_behavior.tick_pickup,
}
await handlers[self._state](sa, gs)
```

[VERIFIED: strategic_brain.py lines 266-276]

### Verified: Damage Response Reflex (RFLX-01)

The current damage response is embedded in `_tick_combat()`:

```python
# strategic_brain.py lines 456-458
if sa.attacker_direction != 0 and sa.seconds_since_damage < 0.3:
    self.ctrl.turn_degrees(-sa.attacker_direction * 15)
```

This 3-line reflex takes < 1ms (just a pipe command). It reads from SituationalAwareness and writes through VirtualController. [VERIFIED: strategic_brain.py]

### Verified: Navigator Callback Wiring

```python
# strategic_brain.py lines 173-177
self.learned_map = LearnedMap(map_name=map_name, aas_graph=nav.graph)
self.learned_map.load()
nav._edge_cost_fn = self.learned_map.edge_penalty
nav._on_area_transition = self._on_area_transition
```

After extraction, this wiring moves inside the navigation subsystem:

```python
# navigation/__init__.py
class NavigationSubsystem:
    def __init__(self, bridge, aas_path, map_name):
        from .aas_parser import parse_aas
        from .navigator import Navigator
        from .learned_map import LearnedMap
        
        graph = parse_aas(aas_path) if aas_path else None
        self.navigator = Navigator(bridge, aas_path=aas_path)
        self.learned_map = LearnedMap(map_name=map_name, aas_graph=graph)
        self.learned_map.load()
        
        # Internal wiring -- no external dependency
        self.navigator._edge_cost_fn = self.learned_map.edge_penalty
        self.navigator._on_area_transition = self._on_area_transition
    
    def _on_area_transition(self, from_area, to_area, success):
        if success:
            self.learned_map.record_edge_success(from_area, to_area)
        else:
            self.learned_map.record_edge_failure(from_area, to_area)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| God object orchestrator | Subsumption peer modules | Phase 4 (now) | Testable, maintainable subsystems |
| Importlib hacks for directory shadows | Clean re-exports in `__init__.py` | Phase 2 precedent | Simpler import resolution |
| Callbacks wired by orchestrator | Internal subsystem wiring | Phase 4 (now) | Reduced coupling |
| Direct mouse movement (pynput) | Pipe-only VirtualController | Pre-Phase 1 | No desktop cursor interference |

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >= 8.0 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_strategic_brain_characterization.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements --> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RFLX-01 | Damage snap <1ms | unit | `uv run pytest tests/test_reflexes.py::test_damage_response -x` | Wave 0 |
| RFLX-02 | Death reset + respawn | unit | `uv run pytest tests/test_reflexes.py::test_death_handler -x` | Wave 0 |
| RFLX-03 | Stuck escape override | unit | `uv run pytest tests/test_reflexes.py::test_stuck_escape -x` | Wave 0 |
| RFLX-04 | Subsumption priority | unit | `uv run pytest tests/test_strategic_brain_characterization.py -x` | Existing (Phase 1) |
| CMBT-01 | Target acquisition snap | unit | `uv run pytest tests/test_combat.py::test_target_acquisition -x` | Wave 0 |
| CMBT-02 | PID aim control | unit | `uv run pytest tests/test_combat.py::test_aim_controller -x` | Wave 0 |
| CMBT-03 | Fuzzy weapon selection | unit | `uv run pytest tests/test_combat.py::test_weapon_select -x` | Wave 0 |
| CMBT-04 | Combat movement | unit | `uv run pytest tests/test_combat.py::test_combat_mover -x` | Wave 0 |
| CMBT-05 | Engage/disengage | unit | `uv run pytest tests/test_combat.py::test_threat_evaluate -x` | Wave 0 |
| CMBT-06 | Weapon switch timing | unit | `uv run pytest tests/test_combat.py::test_weapon_switch -x` | Wave 0 |
| CMBT-07 | Threat assessment | unit | `uv run pytest tests/test_combat.py::test_threat_assess -x` | Wave 0 |
| NAV-01 | AAS pathfinding | unit | `uv run pytest tests/test_navigation.py::test_pathfinding -x` | Wave 0 |
| NAV-02 | Stuck detection | unit | `uv run pytest tests/test_navigation.py::test_stuck_detection -x` | Wave 0 |
| NAV-03 | Learned map | unit | `uv run pytest tests/test_navigation.py::test_learned_map -x` | Wave 0 |
| NAV-04 | Room surveyor | unit | `uv run pytest tests/test_navigation.py::test_room_surveyor -x` | Wave 0 |
| NAV-05 | Obstacle avoidance | unit | `uv run pytest tests/test_navigation.py::test_obstacle_avoidance -x` | Wave 0 |
| NAV-06 | Respawn navigation | unit | `uv run pytest tests/test_reflexes.py::test_respawn_navigation -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_strategic_brain_characterization.py -x` (existing safety net)
- **Per wave merge:** `uv run pytest tests/ -x` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_reflexes.py` -- covers RFLX-01 through RFLX-03, NAV-06
- [ ] `tests/test_combat.py` -- covers CMBT-01 through CMBT-07
- [ ] `tests/test_navigation.py` -- covers NAV-01 through NAV-05

Note: RFLX-04 is already covered by `test_strategic_brain_characterization.py` (TestTransitionPriorities class).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Commander belongs in navigation/ (item routing is a nav concern) | Method Map | Commander could be argued as tactics -- but it currently only drives pathfinding targets, so navigation is correct for Phase 4. Phase 5 may elevate it to tactics/. |
| A2 | SpatialKnowledge stays in models.py as shared contract | Pitfall 5 | If it grows too large it may need its own module, but for now it is a data container like SituationalAwareness. |
| A3 | strategic_brain.py continues as thin orchestrator after Phase 4 | Architecture | Phase 5 will extract the FSM into tactics/. Keeping it during Phase 4 reduces blast radius. |
| A4 | CMBT-06 (weapon switch timing) is new logic, not existing extraction | Requirements | The existing code has no preemptive weapon switching. This needs ~20 lines of new code in combat/weapon_select.py. |

## Open Questions

1. **Should `reactive_agent.py` be updated to use the new subsystem imports?**
   - What we know: reactive_agent.py imports from root-level modules (combat.py, navigator.py)
   - What's unclear: Is reactive_agent.py still actively used, or has strategic_brain.py replaced it?
   - Recommendation: Leave reactive_agent.py as-is with shims. It can be updated in Phase 5 or deprecated.

2. **How deep should the `combat/__init__.py` re-export go?**
   - What we know: Phase 1 created an importlib hack to shadow combat.py
   - What's unclear: Should we re-export everything or just CombatMover/WeaponInfo?
   - Recommendation: Re-export all public symbols from all combat/ submodules for drop-in compatibility.

## Environment Availability

Step 2.6: SKIPPED (no external dependencies -- this is a code-only refactoring phase)

## Security Domain

Step not applicable -- this phase involves no authentication, input validation from external sources, cryptography, or network-facing changes. All code is internal refactoring of existing game bot logic.

## Sources

### Primary (HIGH confidence)
- `strategic_brain.py` -- Full 681-line read, every method mapped [VERIFIED: Read tool]
- `combat.py` -- 232 lines, all functions catalogued [VERIFIED: Read tool]
- `aim_controller.py` -- 263 lines, PID controller [VERIFIED: Read tool]
- `navigator.py` -- 517 lines, A* + stuck recovery [VERIFIED: Read tool]
- `learned_map.py` -- 395 lines, occupancy grid + edge tracking [VERIFIED: Read tool]
- `exit_finder.py` -- 171 lines, scan-and-probe [VERIFIED: Read tool]
- `room_surveyor.py` -- 413 lines, LLM survey [VERIFIED: Read tool]
- `commander.py` -- 285 lines, item prioritization [VERIFIED: Read tool]
- `models.py` -- BrainState, SituationalAwareness, SpatialKnowledge [VERIFIED: Read tool]
- Phase 1 characterization tests -- 15+ tests [VERIFIED: Read tool]
- Phase 2 perception extraction pattern [VERIFIED: perception/__init__.py]
- Phase 1 research (FSM transition matrix) [VERIFIED: 01-RESEARCH.md]

### Secondary (MEDIUM confidence)
- ARCHITECTURE.md -- subsumption layer definitions and priority table [VERIFIED: Read tool]
- SUMMARY.md -- phase ordering rationale [VERIFIED: Read tool]
- FPS Bot Spec -- behavior tree / utility AI / GOAP patterns [VERIFIED: Read tool]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, purely refactoring
- Architecture: HIGH -- every method mapped from source code, patterns proven in Phase 1-2
- Pitfalls: HIGH -- derived from actual code coupling analysis, not theoretical
- Method mapping: HIGH -- every line of strategic_brain.py accounted for

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (stable -- internal refactoring, no external dependency drift)
