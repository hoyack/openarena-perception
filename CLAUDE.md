<!-- GSD:project-start source:PROJECT.md -->
## Project

**OpenArena Perception — AI Bot Framework**

A brain-inspired AI bot management framework for FPS games (currently OpenArena/ioquake3) that combines real-time computer vision, machine learning, LLM strategic reasoning, and legacy Quake 3 navigation (AAS files) into an organized, testable, API-driven system. The framework runs on Raspberry Pi 4/5 hardware and provides a layered skill system where atomic actions compose into behaviors, behaviors compose into missions — all controllable by LLM agents via a FastAPI backend.

**Core Value:** The bot must be a competitive deathmatch player — able to perceive enemies, navigate maps, select weapons, aim accurately, and make strategic decisions in real-time on constrained Pi hardware.

### Constraints

- **Hardware**: Raspberry Pi 4/5 — must maintain 10+ FPS perception loop
- **Latency**: Real-time vision (OpenCV) for combat, LLM calls only for strategic decisions (~4s cycle)
- **Dependencies**: mss, opencv-python-headless, pytesseract, numpy, ollama — keep lightweight
- **Backward compat**: Existing room surveys, AAS files, trained models must keep working
- **Game interface**: Named pipe + RCON are the only communication channels
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Core Runtime
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.11+ | Runtime | Already in use, asyncio mature, Pi OS Bookworm ships 3.11. 3.12 available and recommended for new installs. | HIGH |
| uv | latest | Package manager | 10-100x faster than pip, lockfile support, replaces pip+venv+pip-tools. Astral ecosystem with Ruff. | HIGH |
| asyncio | stdlib | Concurrency | Game tick loop + API + LLM all share one event loop | HIGH |
### API Layer
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| FastAPI | >=0.115,<1.0 | HTTP + WebSocket API | Already decided. Async-native, Pydantic validation, auto-docs, WebSocket for real-time bot state streaming. Current release is 0.135.x. | HIGH |
| uvicorn | >=0.30 | ASGI server | Standard FastAPI server. Single-worker on Pi (no gunicorn needed for single-bot). | HIGH |
| uvloop | >=0.19 | Event loop | Drop-in asyncio replacement, 2x throughput on Pi ARM64 | HIGH |
| pydantic | >=2.6 | Data validation | FastAPI backbone. v2 is 5-50x faster than v1 (Rust core). Use for all data models. | HIGH |
| pydantic-settings | >=2.13 | Configuration | Type-safe config from env vars, .env files, TOML. Replaces ad-hoc config.py. Current: v2.13.1. | HIGH |
### Perception
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| mss | >=10.0 | Screen capture | Already validated at 10-22 FPS on Pi. Pure Python, no deps, X11 native. Current: v10.1.0. | HIGH |
| opencv-python-headless | >=4.8 | Vision processing | HSV detection, frame differencing, contours, optical flow -- already in use. Headless avoids Qt deps. | HIGH |
| pytesseract | >=0.3 | HUD OCR | Already validated for health/armor/ammo/weapon/frag parsing. | HIGH |
| numpy | >=1.26 | Array ops | Foundation for all vision processing. Pin >=1.26 for Pi ARM64 wheel availability. | HIGH |
| HailoRT | >=4.19 | NPU inference | YOLOv6n at 95 FPS on Hailo-8L. Upgradeable to HailoRT 5.2.0. | HIGH |
| ultralytics | >=8.3 | YOLO model management | YOLO26n export to NCNN format for Pi CPU inference (400ms PyTorch -> 80ms NCNN on Pi 5). Desktop-only for training/export. | MEDIUM |
### Navigation
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Custom AAS parser | N/A | Nav mesh | Already built, uses Q3 format directly. No external dependency. | HIGH |
### Strategy / LLM
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| ollama Python SDK | >=0.6.1 | LLM client | Already validated with gemma4:31b-cloud on Pi. Native async support via AsyncClient. Current: v0.6.1. | HIGH |
| httpx | >=0.27 | Async HTTP client | FastAPI test client + general async HTTP. Used by ollama internally. | HIGH |
### Data Persistence
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| SQLite | stdlib | Database engine | Zero-config, no server process, single-file DB. Handles 100K+ records for surveys/maps/metrics. Already on every Pi. | HIGH |
| aiosqlite | >=0.22 | Async SQLite | Non-blocking DB access from FastAPI async handlers. Wraps stdlib sqlite3. Current: v0.22.1. | HIGH |
| SQLAlchemy | >=2.0,<3.0 | Query builder | Use Core (not ORM) for lightweight query building. SA 2.0 async support works with aiosqlite. Keep thin -- raw SQL for hot paths. | MEDIUM |
| alembic | >=1.14 | Schema migrations | Industry standard for SQLite/SQLAlchemy migrations. Small footprint. Essential for evolving DB schema. | HIGH |
### Testing
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pytest | >=8.0 | Test framework | Standard. Async support via pytest-asyncio, excellent fixture/parametrize system. | HIGH |
| pytest-asyncio | >=0.24 | Async tests | Test FastAPI async endpoints and async subsystems. Use `mode=auto`. | HIGH |
| httpx | >=0.27 | API test client | FastAPI recommended async test client. AsyncClient for full async lifecycle. | HIGH |
| pytest-cov | >=5.0 | Coverage | Track test coverage per subsystem. Target 80%+ on core logic, skip vision integration. | HIGH |
| hypothesis | >=6.100 | Property-based testing | Excellent for testing navigation math, aim PID calculations, coordinate transforms. Finds edge cases humans miss. | MEDIUM |
### Logging and Observability
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| structlog | >=24.0 | Structured logging | JSON-structured logs for machine parsing. Context binding (bind bot_id, map_name once, auto-attach to all log entries). Better than loguru for correlating events across perception/navigation/combat subsystems. | HIGH |
| prometheus-client | >=0.21 | Metrics | Counters/gauges/histograms for FPS, kill rate, nav efficiency, LLM latency. FastAPI middleware exposes /metrics. Lightweight on Pi. | MEDIUM |
### Code Quality
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| ruff | >=0.15 | Linter + formatter | Replaces black + flake8 + isort + pyupgrade. 100x faster, single tool. Current: v0.15.0. | HIGH |
| mypy | >=1.11 | Type checking | Catch type errors in vision pipeline data flow. Strict on API layer, basic on legacy code. | MEDIUM |
| pre-commit | >=4.0 | Git hooks | Run ruff + mypy on commit. Prevents broken code from landing. | HIGH |
### Input Control (existing)
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Named pipes | stdlib | Game command injection | Primary control channel. Already built. No library needed. | HIGH |
| pynput | >=1.7 | Keyboard/mouse fallback | Already in use for non-pipe scenarios. Keep as optional. | HIGH |
| pygame | >=2.5 | HUD display overlay | Already in use for debug visualization. Keep for monitoring. | MEDIUM |
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| API Framework | FastAPI | Flask | No native async, no auto-validation, no WebSocket built-in |
| API Framework | FastAPI | Litestar | Less ecosystem support, fewer tutorials, FastAPI is project requirement |
| Database | SQLite + aiosqlite | PostgreSQL | Overkill for single-bot on Pi, requires server process, adds ops burden |
| Database | SQLite + aiosqlite | TinyDB | Performance degrades past 10K records, no SQL, no async, no migrations |
| Database | SQLite + aiosqlite | Redis | Good for caching but not for persistent survey/map data |
| ORM | SQLAlchemy Core | Tortoise ORM | Less mature async story, smaller ecosystem, fewer migration tools |
| ORM | SQLAlchemy Core | Peewee | No async support |
| Logging | structlog | loguru | Loguru is easier to start but structlog context binding and JSON output are better for bot observability |
| Logging | structlog | stdlib logging | Too verbose to configure for structured JSON output |
| Linting | ruff | black + flake8 | Two tools, 100x slower, separate configs |
| LLM Runtime | Ollama | vLLM | vLLM needs GPU, not practical on Pi |
| Test Framework | pytest | unittest | Less ergonomic, no plugins, no fixtures, no parametrize |
| Event Bus | Custom in-process | Redis PubSub | Unnecessary network hop for single-process bot |
| Package Manager | uv | pip + venv | Slower, no lockfile, no resolver. uv is the 2026 standard. |
## What NOT to Use
| Technology | Why Not |
|------------|---------|
| Docker on Pi | Adds overhead on constrained hardware. Native venv + systemd is lighter. |
| Celery | Overkill for single-bot task queue. Use asyncio.Queue or simple background tasks. |
| Redis | No need for distributed caching on single Pi. SQLite handles persistence. |
| gRPC | HTTP + WebSocket covers all needs. gRPC adds protobuf complexity for no benefit. |
| TensorFlow | Heavier than PyTorch/NCNN on ARM. Poor Pi support. |
| Gymnasium (OpenAI Gym) | We control a real game via named pipes, not a simulated environment. Gym abstraction adds no value. |
| SerpentAI | Abandoned project (last commit 2019). Interesting historically but dead. |
| gunicorn | Single worker is sufficient on Pi. Gunicorn multi-process adds unnecessary memory overhead. |
## Installation
# Install uv (if not present)
# Initialize project (if starting fresh)
# Core runtime
# Perception (existing deps)
# LLM
# Database
# Observability
# Input (existing deps)
# Dev dependencies
# Optional: YOLO training/export (desktop only, not on Pi)
# uv add --dev ultralytics
## Version Pinning Strategy
## Key Stack Decision: Single Process, Single Event Loop
## Sources
- FastAPI: https://pypi.org/project/fastapi/ (v0.135.3, April 2026)
- pydantic-settings: https://pypi.org/project/pydantic-settings/ (v2.13.1, Feb 2026)
- mss: https://pypi.org/project/mss/ (v10.1.0, Aug 2025)
- ollama-python: https://pypi.org/project/ollama/ (v0.6.1, Nov 2025)
- aiosqlite: https://pypi.org/project/aiosqlite/ (v0.22.1, Dec 2025)
- Ruff: https://astral.sh/blog/ruff-v0.15.0 (v0.15.0, 2026)
- Ultralytics YOLO26: https://docs.ultralytics.com/models/yolo26/
- Hailo RPi5 examples: https://github.com/hailo-ai/hailo-rpi5-examples
- HailoRT 5.2.0 upgrade guide: https://community.hailo.ai/t/upgrading-to-hailort-5-2-0-step-by-step-raspberry-pi-hailo-apps/19006
- YOLO11 on Raspberry Pi NCNN benchmarks: https://learnopencv.com/yolo11-on-raspberry-pi/
- structlog: https://last9.io/blog/python-logging-with-structlog/
- prometheus-client: https://pypi.org/project/prometheus-client/
- SQLite vs TinyDB: https://medium.com/data-science/sqlite-vs-tinydb-7d6a6a42cb97
- uvloop: https://github.com/MagicStack/uvloop
- FastAPI async testing: https://fastapi.tiangolo.com/advanced/async-tests/
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
