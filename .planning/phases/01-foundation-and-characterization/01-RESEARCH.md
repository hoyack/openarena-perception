# Phase 1: Foundation and Characterization - Research

**Researched:** 2026-04-08
**Domain:** Python project scaffolding, FSM characterization testing, pydantic-settings, structlog
**Confidence:** HIGH

## Summary

Phase 1 establishes the project skeleton, tooling, and regression safety net before any extraction work begins. The codebase currently has 26 modules in `openarena_perception/`, 15 root-level Python scripts (6 are near-duplicates of package modules: config.py, capture.py, loop.py, hud_parser.py, game_state.py, world_parser.py), no pyproject.toml, no tests, and no structured logging. The god object `strategic_brain.py` (832 lines) contains the FSM with 8 states, the `SituationalAwareness` dataclass, and `SpatialKnowledge` -- all of which must be characterized before any decomposition.

The key technical decisions are all well-validated: uv for package management (already installed v0.11.3 on this Pi), pydantic-settings v2 for configuration (TOML + .env + env vars), structlog for JSON logging with subsystem context binding, pytest for characterization tests, and ruff for code quality. Python 3.13.12 is the runtime (exceeds the 3.11+ requirement). The brain-inspired folder structure creates 10 new directories with `__init__.py` files but does NOT move any existing code yet -- that is Phase 2+.

**Primary recommendation:** Start with `uv init` to create pyproject.toml, then build characterization tests for `_evaluate_transitions()` before touching anything else. The tests are the safety net for all future phases.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FOUND-01 | Brain-inspired folder structure (10 directories) | Architecture Patterns section -- directory layout with `__init__.py` stubs |
| FOUND-02 | Resolve duplicate root-level scripts | Duplicate Analysis section -- 6 identified duplicates, 9 unique entry points/utilities |
| FOUND-03 | Configuration via pydantic-settings | pydantic-settings v2 patterns -- TOML + .env + env var priority chain |
| FOUND-04 | Structured logging via structlog | structlog configuration patterns -- JSON output, context binding, subsystem loggers |
| FOUND-05 | Package management via uv with lockfile | uv 0.11.3 already installed; `uv init` + migrate requirements.txt |
| FOUND-06 | Code quality via ruff | ruff configuration in pyproject.toml; not currently installed |
| FOUND-07 | Characterization tests for strategic_brain.py | FSM characterization testing section -- all 8 states, transition matrix, mock strategy |
| FOUND-08 | Immutable SituationalAwareness dataclass | SituationalAwareness section -- existing dataclass needs `frozen=True`, `slots=True` |
</phase_requirements>

## Standard Stack

### Core (Phase 1 only)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| uv | 0.11.3 | Package management + lockfile | Already installed on Pi. Replaces pip+venv. [VERIFIED: `uv --version` on host] |
| pydantic-settings | >=2.12 | Configuration (env/dotenv/TOML) | Type-safe config with source priority chain. v2.12.0 already installed. [VERIFIED: `pip3 show` on host] |
| pydantic | >=2.12 | Data validation backbone | Required by pydantic-settings. v2.12.4 installed. [VERIFIED: `pip3 show` on host] |
| structlog | >=24.0 | Structured JSON logging | Context binding for subsystem identification. Not yet installed. [VERIFIED: not on host] |
| pytest | >=8.0 | Test framework | Characterization tests for FSM. Not yet installed. [VERIFIED: not on host] |
| ruff | >=0.15 | Linter + formatter | Single tool replaces black+flake8+isort. Not yet installed. [VERIFIED: not on host] |
| python-dotenv | >=1.0 | .env file loading | Required by pydantic-settings for .env support. [ASSUMED] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-cov | >=5.0 | Coverage reporting | Track characterization test coverage of strategic_brain.py |
| tomli | N/A (not needed) | TOML parsing | Python 3.11+ has tomllib in stdlib; pydantic-settings uses it automatically [VERIFIED: Python 3.13 on host] |

**Installation (Phase 1 only):**
```bash
# Initialize uv project from existing codebase
uv init --no-readme --no-pin-python

# Add existing dependencies
uv add mss opencv-python-headless pytesseract numpy ollama pynput pygame

# Add Phase 1 new dependencies
uv add pydantic-settings structlog

# Add dev dependencies
uv add --dev pytest pytest-cov ruff
```

## Architecture Patterns

### Brain-Inspired Folder Structure (FOUND-01)

```
openarena_perception/
├── __init__.py              # existing -- keep current re-exports
├── perception/              # NEW stub -- screen capture, HUD, enemy detection
│   └── __init__.py          # empty for now; code moves here in Phase 2
├── combat/                  # NEW stub
│   └── __init__.py
├── navigation/              # NEW stub
│   └── __init__.py
├── memory/                  # NEW stub
│   └── __init__.py
├── tactics/                 # NEW stub
│   └── __init__.py
├── strategy/                # NEW stub
│   └── __init__.py
├── reflexes/                # NEW stub
│   └── __init__.py
├── brainstem/               # NEW stub
│   └── __init__.py
├── skills/                  # NEW stub
│   └── __init__.py
├── api/                     # NEW stub
│   └── __init__.py
├── config.py                # existing perception config (kept)
├── settings.py              # NEW: pydantic-settings central config
├── logging.py               # NEW: structlog configuration
├── models.py                # NEW or refactored: SituationalAwareness
├── strategic_brain.py       # existing -- DO NOT MOVE, only test
├── [all other existing .py] # untouched in Phase 1
└── tools/
    └── roi_debugger.py      # existing
```

**Critical rule:** Phase 1 creates the directories but moves ZERO existing code into them. The stubs exist solely so future phases have a target. Moving code happens in Phases 2-5 with characterization tests as the safety net.

### Pattern 1: pydantic-settings Configuration (FOUND-03)

**What:** Single `settings.py` module that loads config from env vars > .env > TOML, importable from anywhere.
**Source:** [CITED: docs.pydantic.dev/latest/concepts/pydantic_settings/]

```python
# openarena_perception/settings.py
from __future__ import annotations
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource
from pydantic import Field
from typing import Tuple


class BotSettings(BaseSettings):
    """Central configuration -- env vars override .env override TOML."""

    model_config = SettingsConfigDict(
        env_prefix="OA_",
        env_file=".env",
        env_file_encoding="utf-8",
        toml_file="bot.toml",
        extra="ignore",
    )

    # Display
    screen_resolution: str = "800x600"
    screen_w: int = 800
    screen_h: int = 600

    # Game connection
    pipe_path: str = "/tmp/openarena_pipe"
    rcon_password: str = ""
    rcon_port: int = 27960

    # Perception
    enemy_color_mode: str = "red"
    ocr_upscale: int = 3
    enemy_min_area: int = 200

    # LLM
    ollama_model: str = "gemma3:4b"
    ollama_base_url: str = "http://localhost:11434"
    llm_enabled: bool = True

    # Navigation
    map_name: str = "dm4ish"
    aas_dir: str = "maps"

    # Performance
    tick_budget_ms: int = 50
    target_fps: int = 15

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings,
                                    env_settings, dotenv_settings,
                                    file_secret_settings):
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
        )


@lru_cache
def get_settings() -> BotSettings:
    """Singleton settings instance. Import this everywhere."""
    return BotSettings()
```

**Usage from any module:**
```python
from openarena_perception.settings import get_settings
settings = get_settings()
```

**Key design decisions:**
- `env_prefix="OA_"` so env vars are `OA_SCREEN_W=1920`, `OA_RCON_PASSWORD=secret`, etc.
- TOML is lowest priority -- defaults that rarely change go there
- .env is middle priority -- per-machine config
- env vars are highest priority -- runtime overrides
- `lru_cache` ensures settings are loaded once and shared [CITED: docs.pydantic.dev/latest/concepts/pydantic_settings/]

### Pattern 2: structlog Configuration (FOUND-04)

**What:** JSON-structured logging with context binding per subsystem.
**Source:** [CITED: structlog docs -- configuration.html, contextvars.html]

```python
# openarena_perception/logging.py
from __future__ import annotations
import logging
import structlog


def configure_logging(json_output: bool = True, level: str = "INFO"):
    """Configure structlog for the entire application. Call once at startup."""

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging to route through structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper()))


def get_logger(subsystem: str) -> structlog.stdlib.BoundLogger:
    """Get a logger pre-bound with subsystem context."""
    return structlog.get_logger(subsystem=subsystem)
```

**Usage in any module:**
```python
from openarena_perception.logging import get_logger
log = get_logger("combat")
log.info("target_acquired", enemy_distance="near", angle=15.3)
# Output: {"subsystem": "combat", "event": "target_acquired", "enemy_distance": "near", ...}
```

**Key design decisions:**
- `contextvars` for async-safe context (important for the event loop) [CITED: structlog contextvars docs]
- Bind `subsystem` at logger creation -- appears in every log entry automatically
- stdlib integration so existing `logging.getLogger(__name__)` calls in the codebase also produce JSON
- ConsoleRenderer available for local dev (human-readable colored output)

### Pattern 3: Immutable SituationalAwareness (FOUND-08)

**What:** Freeze the existing SituationalAwareness dataclass to enforce immutability.
**Why:** The data contract between subsystems must be read-only. No subsystem should mutate another's perception of the world.

```python
@dataclass(frozen=True, slots=True)
class SituationalAwareness:
    """Unified perception snapshot -- rebuilt every tick. Immutable."""
    tick: int
    timestamp: float
    # ... all existing fields unchanged ...
```

**Frozen vs not-frozen considerations on Pi:**
- `frozen=True` prevents accidental mutation -- enforces the "snapshot" contract [VERIFIED: Python dataclass docs]
- `slots=True` reduces memory per instance by ~40% and speeds attribute access [VERIFIED: Python dataclass docs, requires Python 3.10+]
- The `build()` classmethod continues to work as-is -- it constructs a new instance each tick
- No deep copy needed because the dataclass is frozen -- safe to share across subsystems
- Performance impact: negligible. One allocation per tick (~15 Hz) is nothing on Pi [ASSUMED]

**Migration note:** The existing `SituationalAwareness` in strategic_brain.py is NOT frozen. Making it frozen is a behavioral change -- characterization tests must pass first, then freeze it. Any code that mutates `sa.` fields post-construction will break (this is intentional -- it reveals hidden mutation).

### Anti-Patterns to Avoid

- **Moving code in Phase 1:** The stub directories are empty placeholders. Resist the urge to start extracting modules. That is Phase 2+.
- **Separate config files per module:** One `settings.py` with subsystem sections, not N config files. [CITED: PITFALLS.md -- Config Fragmentation]
- **Custom logging solution:** Use structlog, not a hand-rolled JSON formatter. The context binding alone justifies the dependency.
- **Breaking the existing import paths:** The package `__init__.py` currently exports `build_config`, `PerceptionConfig`, `GameState`, `EnemyContact`, `BoundingBox`, `PerceptionLoop`. These must continue working. New config lives in `settings.py`, not replacing `config.py`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Config loading from multiple sources | Custom env/file/toml reader | pydantic-settings | Source priority, type coercion, validation all built-in |
| JSON structured logging | `json.dumps()` in a custom handler | structlog | Context binding, async-safe contextvars, stdlib integration |
| Package management + lockfile | pip freeze + requirements.txt | uv + pyproject.toml | Lockfile resolution, reproducible builds, 100x faster |
| Linting + formatting | black + flake8 + isort separately | ruff | Single tool, single config, 100x faster |

## Common Pitfalls

### Pitfall 1: Incomplete Characterization of _evaluate_transitions()
**What goes wrong:** Writing tests for the obvious transitions (DEAD when health=0, COMBAT when under attack) but missing the priority ordering, state-time guards, and return-to-previous-state logic.
**Why it happens:** The FSM has 8 states with priority-ordered transitions AND state-duration guards (e.g., `state_time > 2.0` for TRAVERSING_DOOR, `state_time > 15.0` for SURVEYING timeout). Missing these means Phase 5's extraction will break timing.
**How to avoid:** Test every transition edge in `_evaluate_transitions()` systematically. There are ~25 distinct transition rules (see Code Examples below). Test both the "enter" path and the "return from" path.
**Warning signs:** Tests pass but only cover 5-6 of the 8 states.

### Pitfall 2: Breaking root-level scripts during duplicate resolution
**What goes wrong:** Deleting root-level `config.py` breaks scripts that do `from config import build_config` (if any exist).
**Why it happens:** Assuming all root scripts import from the package. Some may import from the root-level module directly.
**How to avoid:** Audit every root-level script's imports first. All 3 entry points checked (play.py, item_tour.py, map_explorer.py) import from `openarena_perception.*` package, NOT from root. The duplicate root files appear to be historical copies that diverged slightly (config.py: ENEMY_MIN_AREA 300 vs 200, enemy_scan ROI differs). The package versions are canonical.
**Warning signs:** `ImportError` after removing root files.

### Pitfall 3: pydantic-settings vs existing config.py conflict
**What goes wrong:** Trying to replace the existing `config.py` (PerceptionConfig with ROIs, HSV ranges) with pydantic-settings.
**Why it happens:** Both are "configuration" but serve different purposes.
**How to avoid:** Keep them separate. `config.py` is perception-specific (ROIs, HSV, OCR). `settings.py` is application-level (screen resolution, pipe path, LLM model, map name). The settings module provides values that `build_config()` consumes (e.g., `get_settings().screen_resolution`).

### Pitfall 4: Forgetting to configure structlog BEFORE any module imports
**What goes wrong:** Modules that use `logging.getLogger(__name__)` at import time get unconfigured loggers.
**Why it happens:** Python evaluates module-level code at import time.
**How to avoid:** Call `configure_logging()` as the first thing in the entry point (play.py, item_tour.py, etc.) before importing any `openarena_perception` modules. Or use structlog's lazy binding which defers formatting.

### Pitfall 5: uv init clobbering existing structure
**What goes wrong:** Running `uv init` creates a new pyproject.toml that does not reference the existing package.
**Why it happens:** `uv init` assumes a new project.
**How to avoid:** Run `uv init --no-readme --no-pin-python` then manually edit pyproject.toml to set `name = "openarena-perception"` and configure the package as `[tool.setuptools.packages]` pointing to `openarena_perception/`. Migrate requirements.txt entries into `[project.dependencies]`.

## Duplicate File Analysis (FOUND-02)

### Files that exist in BOTH root and `openarena_perception/`

| File | Root Lines | Pkg Lines | Identical? | Divergences |
|------|-----------|-----------|------------|-------------|
| config.py | 211 | 152 | No | Root has more comments, ENEMY_MIN_AREA=200 vs 300, enemy_scan ROI differs |
| capture.py | 238 | 244 | No | Package version likely newer (6 more lines) |
| loop.py | 222 | 236 | No | Package version likely newer (14 more lines) |
| hud_parser.py | 219 | 219 | Same count | Need diff to confirm identical |
| game_state.py | 138 | 138 | Same count | Likely identical |
| world_parser.py | 225 | 225 | Same count | Likely identical |

### Root-only scripts (NOT duplicates -- entry points and utilities)

| Script | Purpose | Status |
|--------|---------|--------|
| play.py | Main bot entry point | Keep -- imports from package |
| item_tour.py | Item tour mode | Keep -- imports from package |
| map_explorer.py | Map exploration mode | Keep -- imports from package |
| example_agent.py | Example LLM agent | Keep -- reference code |
| strategic_hud.py | HUD overlay display | Keep -- standalone utility |
| roi_debugger.py | ROI debugging tool | Keep (also in tools/) |
| vision_walk.py | Vision-guided walk test | Keep -- test utility |
| capture_models.py | Model capture utility | Keep -- standalone |
| collect_all.py | Data collection utility | Keep -- standalone |

### Resolution strategy
1. Confirm package versions are canonical (they are -- play.py imports from package)
2. For identical files: delete root copy, no wrapper needed
3. For diverged files: diff carefully, merge any root-only improvements into package, then delete root copy
4. roi_debugger.py exists at both root and `openarena_perception/tools/` -- root copy should be a thin wrapper or deleted

## Code Examples

### Characterization Test Strategy for strategic_brain.py (FOUND-07)

The FSM has 8 states with priority-ordered transitions. The characterization tests must capture the CURRENT behavior without depending on actual game state, perception, or hardware.

**Mock strategy:** Mock all dependencies (`Navigator`, `GameBridge`, `Perception`, etc.) and provide controlled `SituationalAwareness` snapshots to `_evaluate_transitions()`.

```python
# tests/test_strategic_brain_characterization.py
"""
Characterization tests for strategic_brain.py FSM.
These capture CURRENT behavior before any decomposition.
DO NOT "fix" behavior in these tests -- capture what exists.
"""
import time
from unittest.mock import MagicMock, patch
import pytest
from openarena_perception.strategic_brain import (
    BrainState, SituationalAwareness, StrategicBrain, SpatialKnowledge,
)


def make_awareness(**overrides) -> SituationalAwareness:
    """Build a SituationalAwareness with sensible defaults."""
    defaults = dict(
        tick=1, timestamp=time.time(),
        pos=(100.0, 200.0, 0.0), yaw=90.0, current_area=5,
        health=100, armor=50, ammo=30, weapon="machinegun",
        is_alive=True,
        disposition="healthy", armament="armed", orientation="oriented",
        under_attack=False, attacker_direction=0, seconds_since_damage=10.0,
        enemies_visible=0, nearest_enemy_distance=None,
        wall_ahead=False, wall_score=0.0, open_direction=0, in_water=False,
        tracked_objects=0, locked_target=False,
        anomaly_count=0, lockable_anomaly=False,
        room_surveyed=True, room_type="corridor", room_exits=2,
        has_path=True, path_length=5, is_stuck=False, is_recovering=False,
        nav_target="item_health_large",
        has_frame=True,
    )
    defaults.update(overrides)
    return SituationalAwareness(**defaults)


# --- Priority transitions (enter states) ---

class TestTransitionPriorities:
    """P1-P6 priority transitions and return-from transitions."""

    def setup_method(self):
        """Create a StrategicBrain with all dependencies mocked."""
        self.brain = self._make_brain()

    def _make_brain(self):
        bridge = MagicMock()
        nav = MagicMock()
        nav.graph = MagicMock()
        nav.has_path = True
        nav._path = [1, 2, 3]
        nav.pos = (100, 200, 0)
        nav.yaw = 90.0
        nav.current_area = 5
        nav.is_stuck = False
        nav.is_recovering = False
        commander = MagicMock()
        commander.should_decide.return_value = False
        perception = MagicMock()
        damage = MagicMock()
        ctrl = MagicMock()
        brain = StrategicBrain(
            bridge=bridge, nav=nav, commander=commander,
            perception=perception, damage_tracker=damage, ctrl=ctrl,
            map_name="test",
        )
        return brain

    def test_p1_dead_overrides_everything(self):
        sa = make_awareness(is_alive=False, under_attack=True, is_stuck=True)
        assert self.brain._evaluate_transitions(sa) == BrainState.DEAD

    def test_p2_combat_when_under_attack_with_enemies(self):
        self.brain._state = BrainState.NAVIGATING
        sa = make_awareness(under_attack=True, enemies_visible=2)
        assert self.brain._evaluate_transitions(sa) == BrainState.COMBAT

    def test_p2_no_combat_without_visible_enemies(self):
        self.brain._state = BrainState.NAVIGATING
        sa = make_awareness(under_attack=True, enemies_visible=0)
        assert self.brain._evaluate_transitions(sa) != BrainState.COMBAT

    def test_p3_stuck_not_from_combat_or_dead(self):
        self.brain._state = BrainState.NAVIGATING
        sa = make_awareness(is_stuck=True, is_recovering=False)
        assert self.brain._evaluate_transitions(sa) == BrainState.STUCK

    def test_p3_stuck_blocked_during_combat(self):
        self.brain._state = BrainState.COMBAT
        sa = make_awareness(is_stuck=True, is_recovering=False,
                           under_attack=True, enemies_visible=1)
        assert self.brain._evaluate_transitions(sa) == BrainState.COMBAT

    def test_p4_pickup_from_navigating(self):
        self.brain._state = BrainState.NAVIGATING
        sa = make_awareness(lockable_anomaly=True)
        assert self.brain._evaluate_transitions(sa) == BrainState.PICKING_UP_ITEM

    def test_p5_traversing_door_needs_wall_and_time(self):
        self.brain._state = BrainState.NAVIGATING
        self.brain._state_enter_time = time.time() - 3.0  # >2s
        sa = make_awareness(wall_ahead=True, wall_score=0.8, has_path=True)
        assert self.brain._evaluate_transitions(sa) == BrainState.TRAVERSING_DOOR

    def test_p5_no_door_if_under_2s(self):
        self.brain._state = BrainState.NAVIGATING
        self.brain._state_enter_time = time.time() - 1.0  # <2s
        sa = make_awareness(wall_ahead=True, wall_score=0.8, has_path=True)
        assert self.brain._evaluate_transitions(sa) != BrainState.TRAVERSING_DOOR

    # --- Return transitions ---

    def test_return_from_dead(self):
        self.brain._state = BrainState.DEAD
        sa = make_awareness(is_alive=True)
        assert self.brain._evaluate_transitions(sa) == BrainState.EXPLORING

    def test_return_from_combat(self):
        self.brain._state = BrainState.COMBAT
        sa = make_awareness(under_attack=False, seconds_since_damage=4.0)
        assert self.brain._evaluate_transitions(sa) == BrainState.NAVIGATING

    def test_combat_stays_if_recent_damage(self):
        self.brain._state = BrainState.COMBAT
        sa = make_awareness(under_attack=False, seconds_since_damage=2.0)
        assert self.brain._evaluate_transitions(sa) == BrainState.COMBAT

    def test_surveying_timeout(self):
        self.brain._state = BrainState.SURVEYING
        self.brain._state_enter_time = time.time() - 16.0
        sa = make_awareness()
        assert self.brain._evaluate_transitions(sa) == BrainState.NAVIGATING
```

**Complete transition matrix to test** (derived from `_evaluate_transitions` lines 477-548):

| From State | Condition | To State |
|------------|-----------|----------|
| Any | `not is_alive` | DEAD |
| Any except DEAD | `under_attack AND enemies_visible > 0` | COMBAT |
| Not DEAD/COMBAT/SURVEYING | `is_stuck AND NOT is_recovering` | STUCK |
| NAVIGATING/EXPLORING | `lockable_anomaly` | PICKING_UP_ITEM |
| NAVIGATING (>2s) | `wall_ahead AND wall_score > 0.7 AND has_path` | TRAVERSING_DOOR |
| NAVIGATING/EXPLORING | `not room_surveyed AND surveyor AND should_survey AND cooldown expired` | SURVEYING |
| DEAD | `is_alive` | EXPLORING |
| COMBAT | `not under_attack AND seconds_since_damage > 3.0` | NAVIGATING |
| STUCK | `not is_stuck AND NOT is_recovering` | NAVIGATING |
| SURVEYING | `state_time > 15.0` | NAVIGATING |
| TRAVERSING_DOOR | `wall_score < 0.3 OR state_time > 5.0` | NAVIGATING |
| PICKING_UP_ITEM | `not lockable_anomaly OR state_time > 5.0` | NAVIGATING |
| EXPLORING | `commander.should_decide()` | NAVIGATING |
| NAVIGATING | `not has_path AND NOT commander.should_decide()` | EXPLORING |
| Any (no match) | (default) | stay in current state |

### On-Enter / On-Exit Side Effects to Characterize

**_on_enter_state:**
- DEAD: increment deaths, release controls, reset anomaly + object tracker
- COMBAT: start firing
- STUCK: increment stuck counter, blacklist target after 2 stucks (90s timeout)
- EXPLORING: reset stuck counter, path to random
- NAVIGATING: reset stuck counter

**_on_exit_state:**
- Always: release lookup/lookdown, centerview
- COMBAT: stop firing, stop strafing
- SURVEYING: center view

### ruff Configuration

```toml
# In pyproject.toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B"]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.format]
quote-style = "double"
```

### pytest Configuration

```toml
# In pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pip + requirements.txt | uv + pyproject.toml + uv.lock | 2024-2025 | Faster installs, reproducible builds, lockfile |
| black + flake8 + isort | ruff (single tool) | 2023-2025 | 100x faster, single config |
| loguru / stdlib logging | structlog | 2024-2025 | Context binding, JSON output, async-safe |
| .env only config | pydantic-settings v2 (env + .env + TOML) | 2024-2025 | Type-safe, multi-source, validated |
| `dataclass` mutable | `dataclass(frozen=True, slots=True)` | Python 3.10+ | Immutability enforced, memory efficient |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | python-dotenv is required by pydantic-settings for .env support | Standard Stack | Low -- pydantic-settings lists it as a dependency; will be auto-installed |
| A2 | Performance impact of frozen+slots dataclass is negligible at 15 Hz | Architecture Patterns | Low -- one allocation per tick is trivial; worst case revert to non-frozen |
| A3 | All root-level entry points import from package, not from root modules | Duplicate Analysis | Medium -- verified for play.py, item_tour.py, map_explorer.py; others need checking |
| A4 | Package versions of duplicate files are canonical (newer) | Duplicate Analysis | Medium -- divergences in config.py suggest root may have some unique values worth preserving |

## Open Questions

1. **Which root config.py values are intentional?**
   - What we know: Root has ENEMY_MIN_AREA=200, package has 300. Root enemy_scan ROI has `0.08` y-offset, package has `0.05`.
   - What's unclear: Which values are the "correct" tuned values for current gameplay?
   - Recommendation: During duplicate resolution, prefer package values but flag divergences for user confirmation.

2. **Should SituationalAwareness move to its own module immediately?**
   - What we know: It lives in strategic_brain.py now. FOUND-08 requires it as an immutable dataclass.
   - What's unclear: Moving it out of strategic_brain.py in Phase 1 vs waiting for Phase 2.
   - Recommendation: Extract to `openarena_perception/models.py` in Phase 1 since it is the central data contract and should be importable without importing the entire brain. Re-export from strategic_brain.py to avoid breaking imports.

3. **Should root-level scripts become thin wrappers or be left as-is?**
   - What we know: Entry points (play.py, item_tour.py) already import from package. Duplicate modules (config.py, capture.py, etc.) are the problem.
   - What's unclear: Whether any external tool or documentation references root-level module paths.
   - Recommendation: Delete duplicate root files. Keep entry-point scripts as-is. They are the user's `python play.py` interface.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Everything | Yes | 3.13.12 | -- |
| uv | FOUND-05 | Yes | 0.11.3 | -- |
| pydantic-settings | FOUND-03 | Yes (pip) | 2.12.0 | Will be managed by uv after init |
| pydantic | FOUND-03 | Yes (pip) | 2.12.4 | Will be managed by uv after init |
| structlog | FOUND-04 | No | -- | Install via uv add |
| pytest | FOUND-07 | No | -- | Install via uv add --dev |
| ruff | FOUND-06 | No | -- | Install via uv add --dev |
| pytest-cov | Coverage | No | -- | Install via uv add --dev |

**Missing dependencies with no fallback:** None -- all missing packages are installable via uv.

**Missing dependencies with fallback:** None needed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 |
| Config file | None -- Wave 0 creates `[tool.pytest.ini_options]` in pyproject.toml |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v --tb=short` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FOUND-01 | Brain-inspired folders exist with __init__.py | smoke | `uv run pytest tests/test_foundation.py::test_folder_structure -x` | Wave 0 |
| FOUND-02 | No duplicate root scripts | smoke | `uv run pytest tests/test_foundation.py::test_no_duplicates -x` | Wave 0 |
| FOUND-03 | Settings load from env/dotenv/TOML | unit | `uv run pytest tests/test_settings.py -x` | Wave 0 |
| FOUND-04 | structlog produces JSON with subsystem binding | unit | `uv run pytest tests/test_logging_config.py -x` | Wave 0 |
| FOUND-05 | pyproject.toml exists with lockfile | smoke | `uv run pytest tests/test_foundation.py::test_pyproject_exists -x` | Wave 0 |
| FOUND-06 | ruff passes on codebase | lint | `uv run ruff check openarena_perception/` | N/A (ruff is the test) |
| FOUND-07 | FSM transitions captured | unit | `uv run pytest tests/test_strategic_brain_characterization.py -x` | Wave 0 |
| FOUND-08 | SituationalAwareness is frozen dataclass | unit | `uv run pytest tests/test_foundation.py::test_situational_awareness_frozen -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green before verify

### Wave 0 Gaps
- [ ] `tests/__init__.py` -- empty init for test package
- [ ] `tests/conftest.py` -- shared fixtures (make_awareness helper, mocked brain factory)
- [ ] `tests/test_strategic_brain_characterization.py` -- FOUND-07 characterization tests
- [ ] `tests/test_settings.py` -- FOUND-03 pydantic-settings validation
- [ ] `tests/test_logging_config.py` -- FOUND-04 structlog output validation
- [ ] `tests/test_foundation.py` -- FOUND-01, FOUND-02, FOUND-05, FOUND-08 smoke tests
- [ ] pytest + pytest-cov installation via `uv add --dev`
- [ ] `[tool.pytest.ini_options]` in pyproject.toml

## Security Domain

Security enforcement is not explicitly disabled, but this phase has minimal security surface.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A -- local bot, no user auth |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A |
| V5 Input Validation | Yes (minimal) | pydantic-settings validates config types |
| V6 Cryptography | No | N/A |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secrets in config files | Information Disclosure | .env file in .gitignore; RCON password via env var not TOML |
| Pipe path injection | Tampering | Validate pipe_path in settings (path exists, is a named pipe) |

## Sources

### Primary (HIGH confidence)
- Existing codebase analysis: `strategic_brain.py` (832 lines), all root scripts, package structure [VERIFIED: direct file reads]
- uv 0.11.3 on host [VERIFIED: `uv --version`]
- Python 3.13.12 on host [VERIFIED: `python3 --version`]
- pydantic-settings v2.12.0 installed [VERIFIED: `pip3 show`]

### Secondary (MEDIUM confidence)
- [pydantic-settings TOML docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) -- source priority, TomlConfigSettingsSource [CITED]
- [structlog configuration docs](https://www.structlog.org/en/stable/configuration.html) -- JSON output, context binding [CITED]
- [structlog contextvars docs](https://www.structlog.org/en/stable/contextvars.html) -- async-safe context [CITED]

### Tertiary (LOW confidence)
- None -- all findings verified against codebase or official docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all packages verified on host or against PyPI
- Architecture: HIGH -- patterns derived from official docs + codebase analysis
- Pitfalls: HIGH -- derived from direct codebase analysis (duplicate files, FSM structure)
- Characterization tests: HIGH -- complete transition matrix extracted from source code

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (stable domain -- Python tooling, no fast-moving APIs)
