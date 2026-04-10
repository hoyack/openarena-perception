"""
game_bridge.py — Low-latency communication with ioquake3/OpenArena.

Two channels:
  1. Named pipe (com_pipefile) → sends client console commands instantly
     Used for: +forward, -forward, +attack, +left, centerview, weapon selection
  2. RCON (UDP) → queries server state
     Used for: player scores, server info, admin commands

The pipe is the primary control channel — it injects commands directly
into the client's command buffer with zero network overhead.
"""

from __future__ import annotations

import logging
import os
import socket
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

log = logging.getLogger(__name__)

# Quake 3 OOB packet prefix
Q3_OOB = b"\xff\xff\xff\xff"


@dataclass
class PlayerInfo:
    """Parsed player info from getstatus."""
    name: str
    score: int
    ping: int
    client_id: int = 0


@dataclass
class ServerState:
    """Parsed server state from RCON/getstatus."""
    map_name: str = ""
    players: List[PlayerInfo] = field(default_factory=list)
    our_score: int = 0
    our_client_id: int = -1
    timestamp: float = 0.0


class GameBridge:
    """
    Communicates with ioquake3 via named pipe + RCON UDP.

    Pipe: instant client command injection (movement, firing, etc.)
    RCON: server state queries (scores, map info)
    """

    def __init__(
        self,
        pipe_path: str = os.path.expanduser("~/.openarena/baseoa/oapipe"),
        rcon_host: str = "127.0.0.1",
        rcon_port: int = 27960,
        rcon_password: str = "botctl",
        our_name: str = "UnnamedPlayer",
    ):
        self.pipe_path = pipe_path
        self.rcon_host = rcon_host
        self.rcon_port = rcon_port
        self.rcon_password = rcon_password
        self.our_name = our_name

        self._pipe_fd: Optional[int] = None
        self._sock: Optional[socket.socket] = None
        self._held_actions: Set[str] = set()

        # State cache
        self._last_server_state = ServerState()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def open(self):
        """Open pipe and UDP socket."""
        # Open pipe for writing (non-blocking)
        if os.path.exists(self.pipe_path):
            try:
                self._pipe_fd = os.open(self.pipe_path, os.O_WRONLY | os.O_NONBLOCK)
                log.info("Pipe opened: %s", self.pipe_path)
            except OSError as e:
                log.warning("Could not open pipe %s: %s", self.pipe_path, e)
                self._pipe_fd = None
        else:
            log.warning("Pipe not found: %s", self.pipe_path)

        # UDP socket for RCON
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(0.5)
        log.info("RCON socket ready: %s:%d", self.rcon_host, self.rcon_port)

        # Defensive release on open — clears any keys held by a previous process
        # that crashed without cleanup (pipe state persists across our processes).
        if self._pipe_fd is not None:
            self.release_all(force=True)

    def close(self):
        """Release all held actions and close connections."""
        self.release_all()
        if self._pipe_fd is not None:
            try:
                os.close(self._pipe_fd)
            except OSError:
                pass
            self._pipe_fd = None
        if self._sock:
            self._sock.close()
            self._sock = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    # ── Pipe commands (instant, client-side) ───────────────────────────────

    def cmd(self, command: str):
        """Send a console command via the named pipe. Instant."""
        if self._pipe_fd is None:
            return
        try:
            os.write(self._pipe_fd, (command + "\n").encode())
        except OSError as e:
            log.debug("Pipe write failed: %s", e)
            # Try to reopen
            self._reopen_pipe()

    def action_start(self, action: str):
        """Start a +action (e.g., 'forward', 'attack'). Idempotent."""
        if action not in self._held_actions:
            self.cmd(f"+{action}")
            self._held_actions.add(action)

    def action_stop(self, action: str):
        """Stop a -action. Safe to call if not held."""
        if action in self._held_actions:
            self.cmd(f"-{action}")
            self._held_actions.discard(action)

    # All possible held actions — used for defensive release regardless of tracked state
    _ALL_ACTIONS = (
        "forward", "back", "moveleft", "moveright",
        "moveup", "movedown", "left", "right",
        "lookup", "lookdown", "attack", "speed",
        "strafe", "mlook",
    )

    def release_all(self, force: bool = True):
        """Release all held actions.

        Args:
          force: if True (default), unconditionally send -action for EVERY known
                 action key, even ones this process doesn't think it's holding.
                 This handles the case where a previous process crashed with
                 keys held — the pipe retains the state across processes.
        """
        if force:
            for action in self._ALL_ACTIONS:
                try:
                    self.cmd(f"-{action}")
                except Exception:
                    pass
        else:
            for action in list(self._held_actions):
                self.cmd(f"-{action}")
        self._held_actions.clear()

    # ── High-level movement ────────────────────────────────────────────────

    def move_forward(self, on: bool = True):
        (self.action_start if on else self.action_stop)("forward")

    def move_back(self, on: bool = True):
        (self.action_start if on else self.action_stop)("back")

    def strafe_left(self, on: bool = True):
        (self.action_start if on else self.action_stop)("moveleft")

    def strafe_right(self, on: bool = True):
        (self.action_start if on else self.action_stop)("moveright")

    def jump(self):
        self.cmd("+moveup")
        # Q3 needs the release on next frame for a single jump
        # We'll release it next tick

    def jump_release(self):
        self.cmd("-moveup")

    def crouch(self, on: bool = True):
        (self.action_start if on else self.action_stop)("movedown")

    def turn_left(self, on: bool = True):
        (self.action_start if on else self.action_stop)("left")

    def turn_right(self, on: bool = True):
        (self.action_start if on else self.action_stop)("right")

    def look_up(self, on: bool = True):
        (self.action_start if on else self.action_stop)("lookup")

    def look_down(self, on: bool = True):
        (self.action_start if on else self.action_stop)("lookdown")

    # ── Combat ─────────────────────────────────────────────────────────────

    def fire(self, on: bool = True):
        (self.action_start if on else self.action_stop)("attack")

    def select_weapon(self, slot: int):
        """Select weapon by slot number (1-9)."""
        self.cmd(f"weapon {slot}")

    def select_weapon_by_name(self, name: str) -> bool:
        """Select weapon by name."""
        slots = {
            "gauntlet": 1, "machinegun": 2, "shotgun": 3,
            "grenade": 4, "rocket": 5, "lightning": 6,
            "railgun": 7, "plasma": 8, "bfg": 9,
        }
        slot = slots.get(name.lower())
        if slot:
            self.select_weapon(slot)
            return True
        return False

    # ── View control ───────────────────────────────────────────────────────

    def set_view_angle(self, yaw: float, pitch: float = 0.0):
        """Set absolute view angles (requires sv_cheats 1)."""
        # cl_pitchspeed and cl_yawspeed control turn rate for +left/+right
        # For absolute angles we can use a cheat command
        self.cmd(f"setviewpos 0 0 0 {yaw} {pitch}")

    def set_turn_speed(self, yaw_speed: float = 200.0):
        """Set the turn speed for +left/+right commands."""
        self.cmd(f"cl_yawspeed {yaw_speed}")

    def set_pitch_speed(self, pitch_speed: float = 150.0):
        """Set the pitch speed for +lookup/+lookdown."""
        self.cmd(f"cl_pitchspeed {pitch_speed}")

    def center_view(self):
        """Center the view (reset pitch to 0)."""
        self.cmd("centerview")

    # ── Aiming via mouse emulation ─────────────────────────────────────────
    # ioquake3 doesn't have a direct "set yaw" client command.
    # The most reliable approach for fine aim is still mouse input (pynput).
    # But for coarse turning, +left/+right with cl_yawspeed works well.
    # We'll use a hybrid: pipe for movement/fire, pynput for mouse aim.

    # ── Stop all movement ──────────────────────────────────────────────────

    def stop_movement(self):
        """Release all movement actions."""
        for action in ["forward", "back", "moveleft", "moveright",
                       "moveup", "movedown", "left", "right",
                       "lookup", "lookdown"]:
            self.action_stop(action)

    def stop_firing(self):
        self.action_stop("attack")

    # ── RCON queries ───────────────────────────────────────────────────────

    def rcon(self, command: str) -> str:
        """Send an RCON command and return the response."""
        if not self._sock:
            return ""
        try:
            packet = Q3_OOB + f"rcon {self.rcon_password} {command}\n".encode()
            self._sock.sendto(packet, (self.rcon_host, self.rcon_port))
            data, _ = self._sock.recvfrom(16384)
            return data[4:].decode("utf-8", errors="replace").strip()
        except socket.timeout:
            return ""
        except Exception as e:
            log.debug("RCON error: %s", e)
            return ""

    def get_status(self) -> ServerState:
        """Query server status (map, player scores). ~1ms round trip."""
        if not self._sock:
            return self._last_server_state

        try:
            self._sock.sendto(
                Q3_OOB + b"getstatus\n",
                (self.rcon_host, self.rcon_port),
            )
            data, _ = self._sock.recvfrom(16384)
            text = data[4:].decode("utf-8", errors="replace")
            state = self._parse_getstatus(text)
            self._last_server_state = state
            return state
        except socket.timeout:
            return self._last_server_state
        except Exception as e:
            log.debug("getstatus error: %s", e)
            return self._last_server_state

    def _parse_getstatus(self, text: str) -> ServerState:
        """Parse the getstatus response."""
        lines = text.strip().split("\n")
        state = ServerState(timestamp=time.time())

        # Line 0: "statusResponse"
        # Line 1: \key\value\key\value... (server cvars)
        if len(lines) >= 2:
            cvars = lines[1]
            parts = cvars.split("\\")
            cvar_dict = {}
            for i in range(1, len(parts) - 1, 2):
                cvar_dict[parts[i]] = parts[i + 1]
            state.map_name = cvar_dict.get("mapname", "")

        # Lines 2+: "score ping \"name\"" per player
        for idx, line in enumerate(lines[2:]):
            line = line.strip()
            if not line:
                continue
            try:
                parts = line.split(" ", 2)
                score = int(parts[0])
                ping = int(parts[1])
                name = parts[2].strip('"') if len(parts) > 2 else ""
                player = PlayerInfo(
                    name=name, score=score, ping=ping, client_id=idx,
                )
                state.players.append(player)
                if self.our_name in name:
                    state.our_score = score
                    state.our_client_id = idx
            except (ValueError, IndexError):
                continue

        return state

    # ── Console commands ───────────────────────────────────────────────────

    def say(self, message: str):
        """Send a chat message."""
        self.cmd(f'say "{message}"')

    def load_map(self, map_name: str):
        """Change map (server command via rcon)."""
        self.rcon(f"map {map_name}")

    def add_bot(self, name: str = "sarge", skill: int = 3):
        """Add a bot to the server."""
        self.rcon(f"addbot {name} {skill}")

    def kick_bot(self, name: str):
        self.rcon(f"kick {name}")

    # ── Internals ──────────────────────────────────────────────────────────

    def _reopen_pipe(self):
        """Try to reopen the pipe if it was closed."""
        if self._pipe_fd is not None:
            try:
                os.close(self._pipe_fd)
            except OSError:
                pass
        try:
            self._pipe_fd = os.open(self.pipe_path, os.O_WRONLY | os.O_NONBLOCK)
        except OSError:
            self._pipe_fd = None
