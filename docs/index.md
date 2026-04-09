# OpenArena Perception -- AI Bot Framework

A brain-inspired AI bot management framework for FPS games (currently OpenArena/ioquake3) that combines real-time computer vision, machine learning, LLM strategic reasoning, and legacy Quake 3 navigation (AAS files) into an organized, testable, API-driven system.

The framework runs on **Raspberry Pi 4/5** hardware and provides a layered skill system where atomic actions compose into behaviors, behaviors compose into missions -- all controllable by LLM agents via a FastAPI backend.

## Documentation

| Page | Description |
|------|-------------|
| [Architecture](architecture.md) | Brain-inspired cognitive architecture, data flow, dependency graph |
| [API Reference](api-reference.md) | REST endpoints, WebSocket streaming, Prometheus metrics |
| [Subsystems](subsystems.md) | Detailed subsystem documentation (perception, combat, navigation, ...) |
| [Skill Catalog](skill-catalog.md) | Three-layer skill hierarchy: actions, behaviors, missions |
| [Configuration Guide](configuration.md) | BotSettings, env vars, .env, TOML configuration |
| [Getting Started](getting-started.md) | Installation, setup, running the bot |

## Subsystem Overview

The bot is organized into **9 subsystems** inspired by the structure of the brain:

| Subsystem | Brain Analogy | Purpose |
|-----------|---------------|---------|
| **Perception** | Sensory cortex | Screen capture, HUD OCR, enemy detection, motion tracking, object tracking |
| **Reflexes** | Limbic system | Event-driven interrupts: death handling, stuck escape, subsumption arbitration |
| **Combat** | Motor cortex + cerebellum | Weapon selection, PID aim control, combat movement, threat assessment |
| **Navigation** | Hippocampus (spatial) | AAS pathfinding, learned map, room surveys, exploration behaviors |
| **Memory** | Hippocampus (long-term) | SQLite persistence for surveys, maps, metrics, spatial knowledge |
| **Tactics** | Basal ganglia | FSM state management, goal selection, fight-or-flight decisions |
| **Strategy** | Prefrontal cortex | LLM-powered strategic reasoning via Ollama (gemma3/gemma4) |
| **Skills** | Procedural memory | Three-layer hierarchy: atomic actions, composed behaviors, missions |
| **API** | External interface | FastAPI REST + WebSocket for LLM agent control, Prometheus metrics |

## Hardware Requirements

- **Raspberry Pi 4** (4GB+) or **Raspberry Pi 5** (recommended)
- X11 display server (for screen capture via mss)
- OpenArena / ioquake3 running at 800x600 resolution
- Optional: **Hailo-8L NPU** for YOLOv6n inference at 95 FPS

## Quick Links

- **Source:** `openarena_perception/` package (10 subsystem directories)
- **Configuration:** `BotSettings` in `openarena_perception/settings.py` (env > .env > TOML)
- **API base URL:** `http://localhost:8420`
- **Game interface:** Named pipe (`/tmp/openarena_pipe`) + RCON UDP (port 27960)
