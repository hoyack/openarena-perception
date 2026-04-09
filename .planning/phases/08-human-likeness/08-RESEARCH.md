# Phase 8: Human-Likeness - Research

**Researched:** 2026-04-08
**Domain:** FPS bot human-likeness / believability (aim humanization, reaction time, personality, adaptive learning)
**Confidence:** HIGH

## Summary

Phase 8 overlays human-likeness behaviors onto the bot's existing combat, navigation, reflexes, and tactics subsystems. The primary goal is making the bot pass a "smell test" for human-like behavior -- informed by the BotPrize competition (UT^2 bot, MirrorBot), anti-cheat detection research, and the FPS Bot Spec's Section 5.1 on aiming imperfections.

The implementation touches 6 existing files (aim_controller.py, combat_movement.py, engage.py, fsm.py, arbiter.py, settings.py) and creates 2-3 new modules (humanization config/models, personality profiles, adaptive learning). The key technical insight is that human-likeness is a **parameter overlay**, not a new subsystem -- it modifies existing behavior through noise injection, time delays, and configurable personality profiles that scale via a unified skill level (1-5).

**Primary recommendation:** Implement a `HumanizationConfig` dataclass driven by skill level (1-5) that propagates concrete parameter values to each subsystem. Use Perlin noise (not pure Gaussian) for aim drift because it produces temporally smooth, realistic-looking error patterns. Keep reaction time as an async delay in the arbiter's transition evaluation, not a separate queuing system. Use the existing `EpisodicMemory.get_death_heatmap()` for adaptive learning -- no new DB tables needed.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HUMN-01 | Aim humanization -- Gaussian noise scaled by target velocity, distance, turn rate. Cap accuracy below 70% | AimController.update() gets noise injection post-PID. Use Perlin noise base + Gaussian perturbation. Accuracy cap via max on-target ratio check. |
| HUMN-02 | Reaction time modeling -- variable 150-250ms+ delay between perception and action | SubsumptionArbiter.evaluate() wraps state transitions in a delay buffer. Delay sampled from truncated normal distribution. |
| HUMN-03 | Movement variability -- overshoot corners, hesitate, occasional suboptimal paths | CombatMover gets noise in strafe timing. NavBehavior gets waypoint offset noise and occasional path deviation. |
| HUMN-04 | Bot personality profiles -- configurable aggression, caution, weapon preference, grudge tendency | Pydantic dataclass with personality parameters. Presets for aggressive/cautious/balanced/grudge archetypes. |
| HUMN-05 | Adaptive learning -- modify behavior based on death locations and engagement outcomes mid-match | EpisodicMemory.get_death_heatmap() already clusters deaths. DangerZoneTracker modifies navigation cost weights. |
| HUMN-06 | Hesitation pauses -- 100-300ms decision delay on state transitions | TacticalFSM.tick() adds configurable delay between transition evaluation and state change execution. |
| HUMN-07 | Skill difficulty scaling -- unified parameter (1-5) affecting aim noise, reaction delay, decision quality | HumanizationConfig.from_skill_level(1-5) generates all sub-parameters. BotSettings gets `skill_level` field. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | >=2.4 (installed: 2.4.4) | Perlin noise generation, Gaussian sampling | Already a project dependency. Perlin noise implementable in ~30 lines with numpy. No external noise library needed. |
| pydantic | >=2.6 (installed) | HumanizationConfig, PersonalityProfile models | Already used for all data models in project |
| pydantic-settings | >=2.13 (installed) | skill_level in BotSettings | Already used for config |

### Supporting
No new dependencies required. All humanization is implementable with numpy (already installed) and standard library `random`/`time` modules. [VERIFIED: numpy 2.4.4 installed in project venv]

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| numpy Perlin implementation | opensimplex or vnoise library | External dependency for ~30 lines of code. Not worth it on Pi. |
| Truncated normal (numpy) | scipy.stats.truncnorm | scipy is heavy (~150MB). numpy random.normal + clip achieves same result. |

## Architecture Patterns

### Recommended Project Structure
```
openarena_perception/
  combat/
    aim_controller.py      # MODIFY: add noise injection post-PID
    combat_movement.py     # MODIFY: add movement variability
    engage.py              # MODIFY: pass personality to combat_mover
    humanize.py            # NEW: AimHumanizer (Perlin noise, accuracy cap)
  tactics/
    fsm.py                 # MODIFY: add hesitation delay
  reflexes/
    arbiter.py             # MODIFY: add reaction time delay
  models.py                # MODIFY: add HumanizationConfig, PersonalityProfile
  settings.py              # MODIFY: add skill_level field
```

### Pattern 1: Parameter Overlay via HumanizationConfig

**What:** A single `HumanizationConfig` dataclass generated from skill_level (1-5) that contains all humanization parameters. Each subsystem reads its relevant parameters from this config.

**When to use:** Always -- this is the central pattern for Phase 8.

**Example:**
```python
# Source: project convention (pydantic dataclass pattern)
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class HumanizationConfig:
    """All humanization parameters derived from skill level."""
    # Aim (HUMN-01)
    aim_noise_base: float       # Perlin noise amplitude (pixels)
    aim_noise_velocity_scale: float  # Extra noise per px/s target velocity
    aim_noise_distance_scale: float  # Extra noise per 100px distance
    aim_noise_turn_scale: float      # Extra noise per deg/s turn rate
    max_accuracy: float         # Hard cap (0.0-1.0), always <= 0.70
    
    # Reaction time (HUMN-02)
    reaction_time_min: float    # seconds (0.15-0.35)
    reaction_time_max: float    # seconds (0.25-0.50)
    reaction_surprise_bonus: float  # extra delay when surprised
    
    # Movement (HUMN-03)
    corner_overshoot_px: float  # waypoint offset noise
    path_deviation_chance: float  # probability of suboptimal path choice
    strafe_timing_noise: float  # jitter on strafe switch interval
    
    # Hesitation (HUMN-06)
    hesitation_min: float       # seconds (0.1-0.3)
    hesitation_max: float       # seconds (0.2-0.5)
    
    # Decision quality (HUMN-07)
    decision_noise: float       # probability of suboptimal decision (0.0-0.5)

    @classmethod
    def from_skill_level(cls, level: int) -> "HumanizationConfig":
        """Map skill level 1-5 to concrete parameters."""
        ...
```

### Pattern 2: Perlin Noise for Aim Drift

**What:** Use 1D Perlin noise sampled at `time.perf_counter()` to create smooth, temporally coherent aim error. Layer Gaussian perturbation on top for moment-to-moment variance.

**When to use:** In `AimController.update()` after PID computation, before clamping.

**Why not pure Gaussian:** Gaussian noise produces independent samples each tick -- the aim "jumps" randomly. Perlin noise produces smooth, wandering error that looks like a human hand tremor or focus drift. The FPS Bot Spec Section 5.1 specifically lists Perlin noise, overshoot, and focus drift as distinct imperfection types. [CITED: docs/Ultimate_Competitive_FPS_Bot_Spec.md Section 5.1]

**Example:**
```python
# Minimal 1D Perlin noise with numpy (no external library)
import numpy as np

class PerlinNoise1D:
    """Lightweight 1D Perlin noise for aim drift."""
    
    def __init__(self, seed: int = 42):
        rng = np.random.default_rng(seed)
        self._perm = rng.permutation(256).astype(np.int32)
        
    def __call__(self, t: float) -> float:
        """Return noise value in [-1, 1] at time t."""
        t0 = int(np.floor(t)) & 255
        t1 = (t0 + 1) & 255
        frac = t - np.floor(t)
        fade = frac * frac * frac * (frac * (frac * 6 - 15) + 10)
        g0 = self._grad(self._perm[t0], frac)
        g1 = self._grad(self._perm[t1], frac - 1.0)
        return g0 + fade * (g1 - g0)
    
    @staticmethod
    def _grad(hash_val: int, x: float) -> float:
        return x if (hash_val & 1) == 0 else -x
```

### Pattern 3: Reaction Time as Transition Delay Buffer

**What:** When SubsumptionArbiter evaluates a new state, instead of returning it immediately, buffer the transition with a sampled reaction delay. The FSM only acts on the transition after the delay expires.

**When to use:** In `TacticalFSM.tick()` wrapping the transition logic.

**Critical constraint:** DEAD state must NEVER be delayed (bot must handle death instantly). COMBAT entry from surprise attack gets extra delay.

**Example:**
```python
# In TacticalFSM.tick()
new_state = self.evaluate_transitions(sa, **context)
if new_state != self._state:
    if self._pending_transition is None:
        # Sample reaction delay
        delay = self._sample_reaction_delay(new_state, self._state)
        self._pending_transition = (new_state, time.time() + delay)
    elif time.time() >= self._pending_transition[1]:
        # Delay expired, execute transition
        actual_new = self._pending_transition[0]
        self._pending_transition = None
        # ... execute state change
    else:
        # Still waiting -- re-validate transition is still correct
        if new_state != self._pending_transition[0]:
            self._pending_transition = None  # situation changed, cancel
```

### Pattern 4: Personality Profile as Named Preset

**What:** A `PersonalityProfile` with aggression, caution, weapon_preference, and grudge_factor. Presets for common archetypes.

**Example:**
```python
@dataclass(frozen=True, slots=True)
class PersonalityProfile:
    name: str
    aggression: float       # 0.0-1.0 (affects engagement range, retreat threshold)
    caution: float          # 0.0-1.0 (affects cover-seeking, health retreat threshold)
    weapon_preference: str  # preferred weapon type ("rocket", "lightning", etc.)
    grudge_factor: float    # 0.0-1.0 (probability of chasing a specific enemy)

PERSONALITIES = {
    "aggressive": PersonalityProfile("aggressive", aggression=0.9, caution=0.2, weapon_preference="rocket", grudge_factor=0.6),
    "cautious": PersonalityProfile("cautious", aggression=0.3, caution=0.8, weapon_preference="railgun", grudge_factor=0.2),
    "balanced": PersonalityProfile("balanced", aggression=0.5, caution=0.5, weapon_preference="lightning", grudge_factor=0.4),
    "grudge": PersonalityProfile("grudge", aggression=0.7, caution=0.3, weapon_preference="rocket", grudge_factor=0.9),
}
```

### Pattern 5: Adaptive Learning from Death Heatmap

**What:** Query `EpisodicMemory.get_death_heatmap()` periodically (every 30s or on respawn) and increase navigation cost for high-death areas. Feed danger zones into `SpatialKnowledge.is_dangerous()`.

**When to use:** On respawn (DEAD -> EXPLORING transition) and periodically during NAVIGATING.

**Key insight:** The existing `SpatialKnowledge.record_danger()` and `is_dangerous()` methods already support this pattern. The adaptive learning just needs to populate danger records from episodic memory death clusters. [VERIFIED: models.py SpatialKnowledge has record_danger/is_dangerous]

### Anti-Patterns to Avoid

- **Separate humanization tick loop:** Do NOT create an independent humanization system that runs on its own timer. Humanization must be injected INTO existing subsystem ticks to avoid timing issues.
- **Global random state:** Do NOT use `random.random()` without seeding per-subsystem. Use `numpy.random.Generator` instances for reproducibility.
- **Fixed reaction delays:** Do NOT use constant delays (e.g., always 200ms). Use truncated normal distribution for natural variance.
- **Aim noise that scales linearly:** Do NOT add fixed noise regardless of context. Scale by target velocity, distance, and bot turn rate as HUMN-01 requires.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Smooth noise generation | Custom interpolation from scratch | 1D Perlin noise (~30 lines with numpy) | Perlin is well-understood, produces correct frequency characteristics |
| Death location clustering | Custom spatial clustering | EpisodicMemory.get_death_heatmap() | Already built in Phase 3, rounds to 100-unit grid |
| Personality serialization | Custom config parser | Pydantic frozen dataclass | Project convention, type-safe, TOML/env support |
| Truncated normal distribution | Manual rejection sampling | numpy.random.Generator.normal() + clip | numpy handles the edge cases correctly |

**Key insight:** Phase 8 creates NO new subsystems. It modifies existing ones via parameter injection. The "don't hand-roll" principle here is: don't build a humanization framework -- build humanization parameters.

## Common Pitfalls

### Pitfall 1: Reaction Delay Breaks Tick Timing
**What goes wrong:** Adding 150-250ms delays in the arbiter's evaluate() method blocks the entire tick loop, causing FPS drops.
**Why it happens:** The arbiter runs synchronously in the hot tick path (10-22 Hz).
**How to avoid:** Reaction delay is NOT a sleep/await. It is a **timestamp comparison** in TacticalFSM.tick(). The arbiter still evaluates every tick instantly. The FSM just buffers the state transition until the delay expires. No blocking.
**Warning signs:** FPS drops when reaction time is enabled; tick budget exceeds 50ms.

### Pitfall 2: Aim Noise Adds to PID Output Instead of Target
**What goes wrong:** Adding noise to the PID output (dx, dy) causes the PID to fight the noise on the next tick, creating oscillation.
**Why it happens:** PID integral term accumulates the noise as error.
**How to avoid:** Add noise to the **aim target point** (before PID), not to the PID output. This way the PID smoothly tracks the noisy target. Alternatively, add noise after PID but reset integral to prevent windup from noise.
**Warning signs:** Oscillating aim, increasing integral term, jittery crosshair.

### Pitfall 3: Perfect Accuracy at Close Range
**What goes wrong:** Gaussian noise scaled by distance becomes zero at close range, producing perfect aim that flags anti-cheat.
**Why it happens:** HUMN-01 says "scaled by distance" but doesn't define a minimum noise floor.
**How to avoid:** Always have a base noise level (`aim_noise_base`) that applies regardless of distance. The scaling adds ON TOP of the base.
**Warning signs:** on_target_ratio > 0.70 at any range.

### Pitfall 4: Hesitation Delay Prevents Death Handling
**What goes wrong:** Bot hesitates 300ms before handling death state, causing missed respawn timing.
**Why it happens:** Hesitation delay applied uniformly to all state transitions.
**How to avoid:** Exempt DEAD transitions from all delays. DEAD is P1 priority and must execute immediately.
**Warning signs:** Bot stays in previous state while dead for 100-300ms.

### Pitfall 5: Personality Affects Core Safety Behaviors
**What goes wrong:** High-aggression personality prevents retreat when health is critical, bot dies unnecessarily.
**Why it happens:** Personality modifiers applied to fight-or-flight threshold without floor.
**How to avoid:** Personality modifies engagement preferences but never overrides survival reflexes. Minimum health retreat threshold (e.g., 15 HP) is absolute regardless of aggression.
**Warning signs:** Aggressive bot dies at 5 HP instead of retreating.

### Pitfall 6: Adaptive Learning Creates Death-Loop Avoidance
**What goes wrong:** Bot dies in area A, avoids area A, gets funneled to area B, dies there, avoids B, runs out of paths.
**Why it happens:** Danger zones accumulate without decay, eventually blocking all routes.
**How to avoid:** Danger zones decay over time (existing `is_dangerous()` has 30s window). Limit maximum number of concurrent danger zones. Never block ALL paths to high-value items.
**Warning signs:** Bot stuck in spawn area avoiding all navigation targets.

## Code Examples

### Skill Level to Parameter Mapping (HUMN-07)

```python
# Source: derived from FPS Bot Spec Section 5.1 + BotPrize research [ASSUMED]
SKILL_PARAMS = {
    1: {  # Novice
        "aim_noise_base": 25.0,  # pixels
        "aim_noise_velocity_scale": 0.15,
        "max_accuracy": 0.25,
        "reaction_time_min": 0.35,
        "reaction_time_max": 0.55,
        "hesitation_min": 0.25,
        "hesitation_max": 0.50,
        "corner_overshoot_px": 40.0,
        "path_deviation_chance": 0.30,
        "decision_noise": 0.40,
    },
    2: {  # Beginner
        "aim_noise_base": 18.0,
        "aim_noise_velocity_scale": 0.12,
        "max_accuracy": 0.35,
        "reaction_time_min": 0.28,
        "reaction_time_max": 0.45,
        "hesitation_min": 0.20,
        "hesitation_max": 0.40,
        "corner_overshoot_px": 30.0,
        "path_deviation_chance": 0.20,
        "decision_noise": 0.30,
    },
    3: {  # Intermediate (default)
        "aim_noise_base": 12.0,
        "aim_noise_velocity_scale": 0.08,
        "max_accuracy": 0.50,
        "reaction_time_min": 0.20,
        "reaction_time_max": 0.35,
        "hesitation_min": 0.12,
        "hesitation_max": 0.30,
        "corner_overshoot_px": 20.0,
        "path_deviation_chance": 0.12,
        "decision_noise": 0.20,
    },
    4: {  # Advanced
        "aim_noise_base": 7.0,
        "aim_noise_velocity_scale": 0.05,
        "max_accuracy": 0.60,
        "reaction_time_min": 0.15,
        "reaction_time_max": 0.28,
        "hesitation_min": 0.08,
        "hesitation_max": 0.20,
        "corner_overshoot_px": 12.0,
        "path_deviation_chance": 0.06,
        "decision_noise": 0.10,
    },
    5: {  # Expert
        "aim_noise_base": 4.0,
        "aim_noise_velocity_scale": 0.03,
        "max_accuracy": 0.70,  # HARD CAP per HUMN-01
        "reaction_time_min": 0.12,
        "reaction_time_max": 0.22,
        "hesitation_min": 0.05,
        "hesitation_max": 0.12,
        "corner_overshoot_px": 6.0,
        "path_deviation_chance": 0.03,
        "decision_noise": 0.05,
    },
}
```

### Aim Noise Injection Point in AimController

```python
# In AimController.update(), after PID computation, before clamp:
# Source: FPS Bot Spec Section 5.1 [CITED: docs/Ultimate_Competitive_FPS_Bot_Spec.md]

def update(self, target_cx, target_cy, screen_cx, screen_cy):
    now = time.perf_counter()
    self._update_velocity(target_cx, target_cy, now)
    
    # --- Humanization: add noise to aim target ---
    if self._humanize:
        noise_x, noise_y = self._humanize.sample(
            now,
            target_velocity=math.hypot(self._target_vx, self._target_vy),
            target_distance=math.hypot(target_cx - screen_cx, target_cy - screen_cy),
            turn_rate=self._recent_turn_rate,
        )
        target_cx += noise_x
        target_cy += noise_y
    
    # ... existing PID logic unchanged ...
```

### Reaction Time in TacticalFSM

```python
# In TacticalFSM.tick():
def _sample_reaction_delay(self, new_state: BrainState, old_state: BrainState) -> float:
    """Sample reaction delay based on humanization config and context."""
    cfg = self._humanize_config
    if cfg is None or new_state == BrainState.DEAD:
        return 0.0  # Never delay death handling
    
    base = np.random.default_rng().normal(
        loc=(cfg.reaction_time_min + cfg.reaction_time_max) / 2,
        scale=(cfg.reaction_time_max - cfg.reaction_time_min) / 4,
    )
    base = np.clip(base, cfg.reaction_time_min, cfg.reaction_time_max)
    
    # Surprise bonus: entering COMBAT from non-combat state
    if new_state == BrainState.COMBAT and old_state not in (BrainState.COMBAT, BrainState.DEAD):
        base += cfg.reaction_surprise_bonus
    
    return float(base)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fixed accuracy handicap | Context-scaled noise (velocity/distance/turn) | BotPrize 2012 | More believable, harder to detect |
| Fixed reaction delay (200ms) | Variable truncated normal | AAMAS 2025 | Fixed delays still detectable |
| No personality | Per-bot personality parameters | Q3 original + BotPrize | Diverse bot pool feels more human |
| No adaptive learning | Death heatmap avoidance | UT^2 2012 | Bots that don't learn are detected as non-human |
| Pure Gaussian aim noise | Perlin noise + Gaussian | FPS Bot Spec 2025 | Smooth drift looks like hand tremor |

**Deprecated/outdated:**
- Fixed skill handicapping (just reduce damage) -- detected by anti-cheat research as non-human
- Perfect pathfinding with no deviation -- flagged by pathfinding-based bot detection (CHI 2023)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Skill level 1-5 parameter values (aim_noise_base, reaction times, etc.) | Code Examples | Values may need tuning against actual gameplay. LOW risk -- easily adjusted via config. |
| A2 | Perlin noise is implementable in ~30 lines with numpy | Standard Stack | If the implementation is buggy, aim drift will look wrong. MEDIUM risk -- but algorithm is well-documented. |
| A3 | 70% accuracy cap is appropriate for max skill | Architecture Patterns | May be too high or low for OpenArena specifically. LOW risk -- configurable. |
| A4 | 30s danger zone decay window is sufficient | Pattern 5 | May need per-skill-level tuning. LOW risk -- SpatialKnowledge.is_dangerous() already parameterized. |
| A5 | Reaction time as timestamp comparison has negligible tick cost | Pitfall 1 | If the pending transition check adds meaningful overhead. VERY LOW risk -- single float comparison. |

## Open Questions

1. **Grudge tracking implementation**
   - What we know: BotPrize showed grudge behavior is critical for human-likeness. PersonalityProfile has grudge_factor.
   - What's unclear: Where to track per-opponent interaction history. Working memory? New field on SituationalAwareness?
   - Recommendation: Track in working memory as a dict of {opponent_name: grudge_score}. Update on kill/death events. Inject into combat target selection.

2. **Aim accuracy measurement**
   - What we know: HUMN-01 says "cap accuracy below 70%". AimController already tracks on_target_ratio.
   - What's unclear: How to enforce the cap in real-time -- reduce noise until ratio drops, or add noise when ratio is too high?
   - Recommendation: Monitor on_target_ratio over sliding window (last 100 ticks). If above max_accuracy, increase aim_noise_base by 50% until ratio drops. Simple feedback loop.

3. **Movement variability injection point**
   - What we know: HUMN-03 says overshoot corners, hesitate, suboptimal paths.
   - What's unclear: NavBehavior's exact waypoint following logic (whether it uses raw AAS waypoints or smoothed paths).
   - Recommendation: Add noise to the target position passed to the navigation system, not to the path itself. This preserves pathfinding correctness while creating overshoot.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 |
| Config file | pyproject.toml (pytest section) |
| Quick run command | `python -m pytest tests/test_combat.py tests/test_tactical_fsm.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HUMN-01 | Aim noise scales with velocity/distance/turn; accuracy capped at 70% | unit | `python -m pytest tests/test_humanize.py::TestAimHumanization -x` | Wave 0 |
| HUMN-02 | Reaction delay 150-250ms+; no delay on DEAD transition | unit | `python -m pytest tests/test_humanize.py::TestReactionTime -x` | Wave 0 |
| HUMN-03 | Movement noise in strafe timing and waypoint offset | unit | `python -m pytest tests/test_humanize.py::TestMovementVariability -x` | Wave 0 |
| HUMN-04 | Personality presets produce different parameter values | unit | `python -m pytest tests/test_humanize.py::TestPersonality -x` | Wave 0 |
| HUMN-05 | Death heatmap modifies danger zones | unit | `python -m pytest tests/test_humanize.py::TestAdaptiveLearning -x` | Wave 0 |
| HUMN-06 | Hesitation delay 100-300ms on state transitions; none on DEAD | unit | `python -m pytest tests/test_humanize.py::TestHesitation -x` | Wave 0 |
| HUMN-07 | Skill level 1-5 produces monotonically scaled parameters | unit | `python -m pytest tests/test_humanize.py::TestSkillScaling -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_humanize.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_humanize.py` -- covers HUMN-01 through HUMN-07
- [ ] Framework install: none needed (pytest already installed and configured)

## Security Domain

Not applicable to this phase. Human-likeness is an internal behavior modification with no external attack surface. No authentication, access control, input validation, or cryptography changes.

## Sources

### Primary (HIGH confidence)
- [VERIFIED: codebase] AimController.update() in combat/aim_controller.py -- PID output, velocity estimation, deadzone logic
- [VERIFIED: codebase] SubsumptionArbiter.evaluate() in reflexes/arbiter.py -- priority ordering, state transition logic
- [VERIFIED: codebase] TacticalFSM.tick() in tactics/fsm.py -- transition + dispatch flow
- [VERIFIED: codebase] CombatMover.get_movement() in combat/combat_movement.py -- skill-scaled movement
- [VERIFIED: codebase] EpisodicMemory.get_death_heatmap() in memory/episodic.py -- death clustering
- [VERIFIED: codebase] SpatialKnowledge.record_danger()/is_dangerous() in models.py -- danger zone tracking
- [VERIFIED: codebase] BotSettings in settings.py -- pydantic-settings config pattern
- [CITED: docs/Ultimate_Competitive_FPS_Bot_Spec.md Section 5.1] Perlin noise, overshoot, focus drift aim imperfections

### Secondary (MEDIUM confidence)
- [CITED: BotPrize competition results] UT^2 grudge behavior, aim constraints, neuroevolution approach -- https://news.utexas.edu/2012/09/26/artificially-intelligent-game-bots-pass-the-turing-test-on-turings-centenary/
- [CITED: FEATURES.md Human-Likeness section] BotPrize-informed feature list with complexity ratings
- [CITED: AAMAS 2025] Variable mistakes, adaptive behavior, hesitation as believability signals -- https://arxiv.org/html/2505.20011v1

### Tertiary (LOW confidence)
- [ASSUMED] Specific skill level parameter values (aim_noise_base, reaction time ranges) -- derived from general FPS AI knowledge, will need gameplay tuning
- [ASSUMED] 1D Perlin noise implementation correctness -- standard algorithm but untested in this context

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all modifications to existing code
- Architecture: HIGH -- parameter overlay pattern is simple and well-understood; all injection points verified in codebase
- Pitfalls: HIGH -- derived from direct codebase analysis (PID windup, tick timing, death handling priority)
- Skill parameter values: MEDIUM -- reasonable estimates but need gameplay validation

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (stable domain, no fast-moving dependencies)
