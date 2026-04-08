# Phase 5: Tactics and Strategy Extraction - Research

**Researched:** 2026-04-08
**Domain:** FSM extraction, LLM strategic reasoning, utility-based goal selection
**Confidence:** HIGH

## Summary

Phase 5 completes the decomposition of `strategic_brain.py` by extracting the remaining orchestration logic into `tactics/` and `strategy/` modules. After Phase 4, `strategic_brain.py` is a 494-line thin dispatcher that: (1) builds situational awareness, (2) evaluates state transitions via SubsumptionArbiter, (3) dispatches tick to subsystem handlers, and (4) manages utility functions (window refocus, HUD export). The FSM state machine, state enter/exit hooks, and dispatch table move to `tactics/`. The LLM brain and strategic agent move to `strategy/`.

The codebase has two separate LLM strategy implementations: `strategic_agent.py` (older, coupled to deprecated ReactiveAgent with broken Strategy enum reference) and `llm_brain.py` (newer, cleaner, standalone). Both do roughly the same thing -- query Ollama every 4-5 seconds with game state + optional screenshots. The `llm_brain.py` is the better foundation; `strategic_agent.py` should be deprecated. Commander already lives in `navigation/commander.py` with a re-export stub at root level.

The fight-or-flight evaluator already exists as `combat/threat_assess.py` (ThreatAssessor + evaluate_threat). TACT-03 is largely satisfied; what remains is wiring it into the tactics layer as a formal decision point rather than only being called during combat engagement.

**Primary recommendation:** Extract the FSM orchestrator into `tactics/fsm.py`, move Commander to `tactics/commander.py` (it's goal selection, not navigation), create `strategy/llm_brain.py` from the existing `llm_brain.py` with constrained output validation, and reduce `strategic_brain.py` to a thin entry point that constructs and wires these modules.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TACT-01 | FSM extracted from strategic_brain.py with clean state transitions | FSM is the _evaluate_transitions + _on_enter_state + _on_exit_state + _dispatch methods. SubsumptionArbiter already extracted in Phase 4. Remaining orchestration (state machine loop, enter/exit hooks, dispatch table) goes to tactics/fsm.py |
| TACT-02 | Commander -- priority-based goal selection with utility scoring | Commander already exists in navigation/commander.py with priority-based item scoring. Move to tactics/commander.py. Enhance with utility curves from FPS Bot Spec Section 4.2 |
| TACT-03 | Fight-or-flight evaluator based on threat assessment | ThreatAssessor already exists in combat/threat_assess.py. Wire into tactics layer as formal decision point. Enhance with utility scoring rather than hard thresholds |
| STRT-01 | LLM brain via Ollama for high-level strategic reasoning (~0.25 Hz) | llm_brain.py is the foundation. Move to strategy/llm_brain.py. Use AsyncClient instead of run_in_executor for sync call |
| STRT-02 | LLM receives structured game state snapshots + optional screenshots | Both existing implementations already do this. Standardize on SituationalAwareness as input, not raw GameState |
| STRT-03 | Strategy outputs constrained to defined action vocabulary (HUNT/DEFEND/RETREAT/EXPLORE) | Both implementations already use these 4 actions. Add Pydantic model for response validation + fallback on parse failure |
</phase_requirements>

## Standard Stack

### Core (existing -- no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ollama | >=0.6.1 | LLM client for strategic reasoning | Already in project, validated on Pi with gemma4:31b-cloud [VERIFIED: pyproject.toml] |
| pydantic | >=2.6 | Response validation for LLM outputs | Already in project for data models [VERIFIED: pyproject.toml] |
| opencv-python-headless | >=4.8 | Frame encoding for vision queries | Already used by llm_brain.py for JPEG encoding [VERIFIED: codebase] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| enum (stdlib) | N/A | Strategy action vocabulary | Define StrategyAction enum for HUNT/DEFEND/RETREAT/EXPLORE |
| dataclasses (stdlib) | N/A | Snapshot and decision contracts | GameSnapshot, StrategyDecision, TacticalState |

No new dependencies required. This phase is purely a refactoring/extraction exercise using existing libraries.

## Architecture Patterns

### Recommended Project Structure

```
openarena_perception/
  tactics/
    __init__.py          # Public API: TacticalFSM, Commander, FightOrFlight
    fsm.py               # State machine orchestrator (from strategic_brain.py)
    commander.py          # Goal selection with utility scoring (from navigation/commander.py)
    fight_or_flight.py    # Wrapper around ThreatAssessor for tactical decisions
  strategy/
    __init__.py           # Public API: LLMStrategyBrain, StrategyDecision
    llm_brain.py          # LLM strategic reasoning (from root llm_brain.py)
    prompts.py            # Prompt templates and response schema
    models.py             # StrategyAction enum, StrategyDecision dataclass
  strategic_brain.py      # Thin entry point -- constructs TacticalFSM + LLMStrategyBrain
```

### Pattern 1: FSM Extraction

**What:** Move the state machine loop from StrategicBrain into tactics/fsm.py as TacticalFSM. [VERIFIED: codebase analysis]

**When to use:** This is the core extraction.

**What moves to TacticalFSM:**
- `_state`, `_state_enter_time`, `_prev_state` -- state tracking
- `_evaluate_transitions()` -- delegates to SubsumptionArbiter (already extracted)
- `_on_enter_state()` -- state entry side-effects
- `_on_exit_state()` -- state exit side-effects
- `_dispatch()` -- tick dispatch to subsystem handlers
- State transition logging

**What stays in StrategicBrain (thin orchestrator):**
- Constructor wiring (builds all subsystem modules)
- `tick()` -- calls perception update, builds SA, calls TacticalFSM.tick()
- `shutdown()` -- cleanup
- `_refocus()` -- window focus (utility, not FSM)
- `_export_hud()` -- HUD state export (utility, not FSM)
- Learned map updates (data pipeline, not FSM)

**Example:**
```python
# tactics/fsm.py
class TacticalFSM:
    """State machine orchestrator. Evaluates transitions and dispatches behavior."""
    
    def __init__(self, arbiter, death_handler, stuck_escape, engager,
                 nav_behavior, survey_behavior=None):
        self._arbiter = arbiter
        self._death_handler = death_handler
        self._stuck_escape = stuck_escape
        self._engager = engager
        self._nav_behavior = nav_behavior
        self._survey_behavior = survey_behavior
        self._state = BrainState.EXPLORING
        self._state_enter_time = time.time()
    
    @property
    def state(self) -> BrainState:
        return self._state
    
    async def tick(self, sa, gs, **context):
        """Evaluate transitions and dispatch to handler."""
        new_state = self._evaluate_transitions(sa, **context)
        if new_state != self._state:
            self._on_exit_state(self._state, sa)
            self._state = new_state
            self._state_enter_time = time.time()
            self._on_enter_state(new_state, sa)
        await self._dispatch(self._state, sa, gs)
```

### Pattern 2: Commander Relocation

**What:** Move Commander from `navigation/commander.py` to `tactics/commander.py`. [VERIFIED: codebase analysis]

**Rationale:** Commander does goal selection ("what should I do next?"), not navigation ("how do I get there?"). It selects targets based on health/armor/ammo priorities -- this is tactical decision-making. The navigator consumes Commander's output (a target to navigate to), but the decision itself belongs in tactics/.

**Migration path:**
1. Move `navigation/commander.py` to `tactics/commander.py`
2. Update `navigation/__init__.py` to re-export from `tactics.commander` (backward compat)
3. Update `openarena_perception/commander.py` stub to re-export from `tactics.commander`
4. Update direct imports in `strategic_brain.py`, `play.py`, etc.

### Pattern 3: LLM Brain with Constrained Output

**What:** Move and enhance llm_brain.py with Pydantic validation for outputs. [VERIFIED: codebase + FPS Bot Spec Section 4]

**Key design decisions:**
- Use `ollama.AsyncClient` instead of `run_in_executor` for sync calls [ASSUMED -- need to verify AsyncClient works on Pi]
- Validate LLM JSON responses with Pydantic, fallback to default on parse failure
- Separate prompt templates into `strategy/prompts.py` for testability
- Feed SituationalAwareness instead of raw GameState for consistency

**Example:**
```python
# strategy/models.py
from enum import Enum
from pydantic import BaseModel

class StrategyAction(str, Enum):
    HUNT = "HUNT"
    DEFEND = "DEFEND"
    RETREAT = "RETREAT"
    EXPLORE = "EXPLORE"

class StrategyDecision(BaseModel):
    action: StrategyAction
    weapon: str | None = None
    target_item: str | None = None
    reasoning: str = ""

# strategy/llm_brain.py
class LLMStrategyBrain:
    async def decide(self, sa: SituationalAwareness) -> StrategyDecision:
        try:
            response = await self._client.chat(...)
            return StrategyDecision.model_validate_json(response.message.content)
        except (ValidationError, json.JSONDecodeError):
            return self._fallback_decision(sa)
    
    def _fallback_decision(self, sa: SituationalAwareness) -> StrategyDecision:
        """Rule-based fallback when LLM fails or is unavailable."""
        if sa.health and sa.health < 30:
            return StrategyDecision(action=StrategyAction.RETREAT)
        if sa.enemies_visible > 0:
            return StrategyDecision(action=StrategyAction.HUNT)
        return StrategyDecision(action=StrategyAction.EXPLORE)
```

### Pattern 4: Fight-or-Flight as Tactical Decision Point

**What:** Wrap existing ThreatAssessor into a tactical-level decision that the FSM can query. [VERIFIED: combat/threat_assess.py exists]

The existing `ThreatAssessor` in `combat/threat_assess.py` already implements CMBT-05 and CMBT-07. TACT-03 formalizes this as a first-class tactical decision rather than an internal combat module detail.

**Approach:** Create `tactics/fight_or_flight.py` that wraps `combat.ThreatAssessor` and translates its output into FSM-consumable decisions. This avoids duplicating logic while giving tactics/ a clean interface.

```python
# tactics/fight_or_flight.py
from openarena_perception.combat import ThreatAssessor
from openarena_perception.models import SituationalAwareness

class FightOrFlight:
    """Tactical fight-or-flight evaluator (TACT-03).
    
    Wraps combat.ThreatAssessor and provides FSM-level decision.
    """
    def __init__(self):
        self._assessor = ThreatAssessor()
    
    def evaluate(self, sa: SituationalAwareness) -> str:
        """Returns 'FIGHT', 'RETREAT', or 'CAUTIOUS'."""
        return self._assessor.evaluate(
            own_health=sa.health or 100,
            own_armor=sa.armor or 0,
            own_weapon=sa.weapon,
            enemy_count=sa.enemies_visible,
            enemy_distance=_parse_distance(sa.nearest_enemy_distance),
        )["verdict"]
    
    def should_disengage(self, sa: SituationalAwareness) -> bool:
        return self._assessor.should_disengage(sa)
```

### Anti-Patterns to Avoid

- **Moving SubsumptionArbiter again:** It is already in reflexes/arbiter.py from Phase 4 and works. Do NOT move it to tactics/. The arbiter is a reflex-level priority evaluator, not a tactical planner. [VERIFIED: reflexes/arbiter.py]
- **Deleting strategic_brain.py entirely:** It is the construction site and entry point used by play.py. Keep it as thin orchestrator. Tests import from it. [VERIFIED: play.py, test_strategic_brain_characterization.py]
- **Duplicating threat assessment logic:** ThreatAssessor already exists in combat/. Do NOT rewrite it in tactics/. Wrap it. [VERIFIED: combat/threat_assess.py]
- **Breaking the characterization tests:** test_strategic_brain_characterization.py imports StrategicBrain and tests state transitions. The FSM extraction must keep these tests passing via delegation. [VERIFIED: tests/test_strategic_brain_characterization.py]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM response parsing | Custom JSON parser with regex | Pydantic BaseModel.model_validate_json() | Handles edge cases, provides type safety, gives clear error messages |
| Strategy action enum | String constants | StrEnum (Python 3.11+) or str Enum | Prevents typos, enables exhaustive matching, serializes cleanly |
| Async Ollama calls | run_in_executor wrapping sync client | ollama.AsyncClient | Native async, no thread pool overhead, cleaner error handling |
| Prompt template formatting | f-strings with manual escaping | Separate prompts.py with {}-style format_map | Testable, swappable, no accidental injection |

## Common Pitfalls

### Pitfall 1: Breaking Characterization Tests
**What goes wrong:** Extracting FSM logic changes how StrategicBrain delegates, breaking test_strategic_brain_characterization.py assertions.
**Why it happens:** Tests directly call `brain._evaluate_transitions()` and check `brain._state`.
**How to avoid:** StrategicBrain must expose the same API (`_evaluate_transitions`, `_state`, `state` property) by delegating to TacticalFSM. Property bridges (already used for Phase 4 extractions) are the proven pattern.
**Warning signs:** Any characterization test failure after extraction.

### Pitfall 2: Circular Imports Between tactics/ and combat/
**What goes wrong:** tactics/fight_or_flight.py imports from combat/, combat/engage.py might import from tactics/.
**Why it happens:** Fight-or-flight is a tactical decision that uses combat assessment.
**How to avoid:** Strict import direction: tactics/ imports from combat/ and reflexes/ but NEVER the reverse. Use TYPE_CHECKING imports if needed (same pattern as Phase 4).
**Warning signs:** ImportError on module load.

### Pitfall 3: LLM Response Parsing Failures
**What goes wrong:** Ollama returns markdown fences, extra text, malformed JSON, or an action not in the vocabulary.
**Why it happens:** LLMs don't reliably produce exact JSON. Both existing implementations already strip markdown fences.
**How to avoid:** Pydantic validation with strict StrategyAction enum. Fallback to rule-based decision on ANY parse failure. Log failures but never crash.
**Warning signs:** Increasing fallback rate in logs.

### Pitfall 4: Commander Location Confusion
**What goes wrong:** Commander is in navigation/ but logically belongs in tactics/. Moving it breaks import chains.
**Why it happens:** Phase 4 kept Commander in navigation/ because NavBehavior depends on it directly.
**How to avoid:** Move Commander to tactics/ and add re-export stub in navigation/__init__.py. NavBehavior can import from either location via the re-export.
**Warning signs:** ImportError in play.py or navigation/nav_behavior.py.

### Pitfall 5: strategic_agent.py Has Broken References
**What goes wrong:** strategic_agent.py references `Strategy.HUNT` etc. but never imports a `Strategy` enum.
**Why it happens:** This file was written against an older version of ReactiveAgent that had a Strategy enum. It is coupled to the deprecated ReactiveAgent.
**How to avoid:** Do NOT try to fix strategic_agent.py. Deprecate it. Use llm_brain.py as the foundation for strategy/.
**Warning signs:** ImportError if trying to use strategic_agent.py.

## Code Examples

### Current State Map of strategic_brain.py (494 lines)

Verified method-by-method analysis of what exists and where it goes:

```
Lines 1-45:   Imports + module docstring
Lines 47-126: build_situational_awareness() -- STAYS in strategic_brain.py (or moves to brainstem/)
Lines 128-204: __init__() -- STAYS (construction wiring)
Lines 206-257: Property bridges -- STAYS (backward compat for tests)
Lines 260-330: tick() -- STAYS (top-level entry point)
Lines 335-346: get_status(), state property -- STAYS
Lines 347-353: _on_area_transition() -- STAYS (learned map callback)
Lines 354-365: shutdown() -- STAYS
Lines 367-378: _evaluate_transitions() -- MOVES to TacticalFSM (delegates to arbiter)
Lines 380-404: _on_enter_state() -- MOVES to TacticalFSM
Lines 401-411: _on_exit_state() -- MOVES to TacticalFSM
Lines 413-436: _dispatch() -- MOVES to TacticalFSM
Lines 438-454: _refocus() -- STAYS (utility)
Lines 456-494: _export_hud() -- STAYS (utility)
```

**After extraction, strategic_brain.py shrinks to ~280 lines:** constructor, tick(), property bridges, utility methods. The TacticalFSM handles ~110 lines of state machine logic.

### Existing LLM Prompt Comparison

| Feature | strategic_agent.py | llm_brain.py |
|---------|-------------------|--------------|
| Action vocab | HUNT/DEFEND/RETREAT/EXPLORE | HUNT/RETREAT/CAMP/AMBUSH/GRAB_ITEM |
| Vision support | Yes (JPEG encode) | Yes (JPEG encode) |
| Async | run_in_executor (sync) | Sync only (decide()) |
| State source | GameState directly | Custom GameSnapshot |
| Response fields | strategy, weapon, reasoning | action, target_item, weapon, movement, reasoning |
| System prompt | Separate SYSTEM_PROMPT | Combined in BRAIN_PROMPT template |
| Broken refs | Yes (Strategy enum missing) | No |

**Recommendation:** Use llm_brain.py as the base. Adopt the 4-action vocabulary from STRT-03 (HUNT/DEFEND/RETREAT/EXPLORE). The `CAMP` and `AMBUSH` actions from llm_brain.py map to DEFEND. `GRAB_ITEM` maps to the Commander's goal selection (not a strategy-level decision).

### Utility Scoring Pattern (from FPS Bot Spec 4.2)

The Commander's current scoring is priority-based with hard thresholds (health < 30 = SURVIVE, etc.). The FPS Bot Spec recommends utility curves:

```python
# tactics/commander.py -- enhanced with utility curves
def _combat_desire(self, health: int, armor: int, weapon: str) -> float:
    """Utility curve for combat vs retreat."""
    effective_hp = health + armor * 0.66
    # Sigmoid-like curve: 0.0 at 0 HP, 1.0 at 100+ HP
    health_factor = min(1.0, effective_hp / 100.0) ** 0.7
    weapon_factor = 0.8 if weapon in POWER_WEAPONS else 0.4
    return health_factor * 0.6 + weapon_factor * 0.4
```

This enhancement is optional for TACT-02 but recommended. The current hard-threshold system works and is well-tested.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| strategic_agent.py sync Ollama via run_in_executor | ollama.AsyncClient native async | ollama 0.4+ (2024) | Cleaner async, no thread pool |
| Raw JSON parsing with regex strip | Pydantic model_validate_json() | pydantic 2.0+ | Type-safe, auto-fallback |
| Hard-coded priority thresholds | Utility curves (FPS Bot Spec 4.2) | Modern game AI standard | Smoother, more human-like decisions |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | ollama.AsyncClient works reliably on Pi 5 | Architecture Patterns (Pattern 3) | Would need to keep run_in_executor pattern -- minor refactor |
| A2 | Utility curve enhancement is optional for TACT-02 | Code Examples | If required, adds ~1 extra task to the plan |
| A3 | strategic_agent.py can be fully deprecated without breaking play.py | Architecture Patterns | play.py conditionally imports it; need to verify --no-llm/--brain flag paths |

## Open Questions

1. **Should build_situational_awareness() move out of strategic_brain.py?**
   - What we know: It is a pure function (lines 47-126) that builds SA from component data. It does not depend on StrategicBrain state.
   - What's unclear: Whether it belongs in brainstem/ (data pipeline) or stays where it is.
   - Recommendation: Leave it in strategic_brain.py for now. Moving it is a separate cleanup task.

2. **What happens to play.py's StrategicAgent usage?**
   - What we know: play.py creates StrategicAgent only when `--brain` is NOT set and `--no-llm` is NOT set (line 107). When `--brain` is set, it uses StrategicBrain exclusively.
   - What's unclear: Whether StrategicAgent should be removed from play.py entirely.
   - Recommendation: Add deprecation warning but keep the code path. Remove in a follow-up.

3. **Should the LLM brain be wired into TacticalFSM or remain independent?**
   - What we know: Currently LLM reasoning is completely separate from the FSM tick loop. strategic_brain.py has `_last_strategic_query` timing but never calls LLM.
   - What's unclear: Whether LLM output should influence FSM transitions or just set Commander goals.
   - Recommendation: LLM sets strategic goals that Commander translates to tactical targets. FSM does not wait on LLM. This preserves the multi-timescale architecture (10-22 Hz ticks, 0.25 Hz strategy).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 8.0 |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v --tb=short` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TACT-01 | FSM extracted with clean state transitions | unit | `uv run pytest tests/test_tactical_fsm.py -x` | Wave 0 |
| TACT-02 | Commander utility scoring | unit | `uv run pytest tests/test_commander_tactics.py -x` | Wave 0 |
| TACT-03 | Fight-or-flight evaluator | unit | `uv run pytest tests/test_fight_or_flight.py -x` | Wave 0 |
| STRT-01 | LLM brain via Ollama | unit (mocked) | `uv run pytest tests/test_llm_strategy.py -x` | Wave 0 |
| STRT-02 | Structured game state to LLM | unit | `uv run pytest tests/test_llm_strategy.py::test_state_format -x` | Wave 0 |
| STRT-03 | Constrained action vocabulary | unit | `uv run pytest tests/test_llm_strategy.py::test_response_validation -x` | Wave 0 |
| REGRESSION | Characterization tests still pass | regression | `uv run pytest tests/test_strategic_brain_characterization.py -x` | Exists |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tactical_fsm.py` -- covers TACT-01 (FSM transitions, enter/exit hooks, dispatch)
- [ ] `tests/test_commander_tactics.py` -- covers TACT-02 (priority scoring, utility curves)
- [ ] `tests/test_fight_or_flight.py` -- covers TACT-03 (fight/retreat/cautious decisions)
- [ ] `tests/test_llm_strategy.py` -- covers STRT-01/02/03 (mocked Ollama, response validation, fallback)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A -- local bot, no auth |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A |
| V5 Input Validation | yes | Pydantic validation on LLM responses (untrusted input) |
| V6 Cryptography | no | N/A |

### Known Threat Patterns for LLM Integration

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| LLM prompt injection via game state | Tampering | Sanitize game state text before prompt insertion; use structured templates |
| Malformed LLM JSON response | Denial of Service | Pydantic validation + fallback to rule-based decision; never crash |
| Resource exhaustion from slow LLM | Denial of Service | Timeout on Ollama call (10s max); independent async task; never block tick loop |

## Sources

### Primary (HIGH confidence)
- Codebase analysis: strategic_brain.py (494 lines), llm_brain.py, strategic_agent.py, combat/threat_assess.py, navigation/commander.py, reflexes/arbiter.py, models.py, play.py [VERIFIED: direct file reads]
- FPS Bot Spec Section 4: Utility AI + Behavior Trees + GOAP [VERIFIED: docs/Ultimate_Competitive_FPS_Bot_Spec.md lines 162-230]
- Phase 4 decisions and patterns [VERIFIED: STATE.md accumulated decisions]
- Test infrastructure [VERIFIED: tests/ directory, pyproject.toml]

### Secondary (MEDIUM confidence)
- ollama AsyncClient availability [ASSUMED: available since ollama 0.4+, needs Pi verification]

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing
- Architecture: HIGH -- based on thorough line-by-line analysis of strategic_brain.py
- Pitfalls: HIGH -- derived from codebase analysis and Phase 4 patterns

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (stable refactoring domain)
