"""Phase 11 wireframe renderer CLI demo.

Usage:
    uv run python -m openarena_perception.visualization.demo_wireframe_room \
        --aas maps/oa_dm1.aas --pos 232,1600,-112 --yaw 90 --orbit --duration 10

Records an orbit video to ./tmp/wireframe_demo.mp4 by default. Pi-native:
uses the AAS geometry backend (no neural inference).
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import statistics
import sys
import time
from dataclasses import replace
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from openarena_perception.navigation.aas_parser import parse_aas
from openarena_perception.visualization import (
    AASDepthBackend,
    RoomConfig,
    WireframeRoomRenderer,
)

LIVE_STATE_PATH_DEFAULT = "./tmp/oa_hud_state.json"

log = logging.getLogger("wireframe_demo")

Point3 = Tuple[float, float, float]


def _parse_pos(s: str) -> Point3:
    parts = s.split(",")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"--pos must be X,Y,Z (got {s!r})")
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"--pos values must be numbers: {e}")


def _default_pos_from_graph(graph) -> Point3:
    for area in graph.areas[1:]:
        if area.mins != (0.0, 0.0, 0.0):
            return (area.cx, area.cy, area.cz)
    return (0.0, 0.0, 0.0)


def _verify_pos_in_walkable_area(graph, pos: Point3) -> None:
    idx = graph.nearest_area(*pos)
    area = graph.areas[idx]
    inside = (
        area.mins[0] <= pos[0] <= area.maxs[0]
        and area.mins[1] <= pos[1] <= area.maxs[1]
        and area.mins[2] <= pos[2] <= area.maxs[2]
    )
    if not inside:
        log.warning(
            "--pos %s is outside nearest area %d AABB mins=%s maxs=%s — "
            "demo will still render, but the camera may be inside geometry",
            pos, idx, area.mins, area.maxs,
        )
    else:
        log.info("--pos %s is inside area %d (mins=%s maxs=%s)",
                 pos, idx, area.mins, area.maxs)


def _open_writer(path: str, fps: int, width: int, height: int):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
    if writer.isOpened():
        log.info("Opened VideoWriter with mp4v at %s", path)
        return writer, path
    log.warning("mp4v writer failed; falling back to MJPG/.avi")
    alt = os.path.splitext(path)[0] + ".avi"
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(alt, fourcc, fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError("Cannot open any VideoWriter (tried mp4v and MJPG)")
    log.info("Opened VideoWriter with MJPG at %s", alt)
    return writer, alt


def _try_imshow(frame: np.ndarray, warned: List[bool]) -> bool:
    try:
        cv2.imshow("PERCEPTION", frame)
        cv2.waitKey(1)
        return True
    except cv2.error as e:
        if not warned[0]:
            log.warning(
                "cv2.imshow not available (headless build?): %s — "
                "install opencv-python (non-headless) if you need live display",
                e,
            )
            warned[0] = True
        return False


class _PygameDisplay:
    """Pygame-based live display for the wireframe frames.

    Works with opencv-python-headless where cv2.imshow is stripped. Uses
    the same pygame runtime Phase 10's strategic_hud.py relies on.
    """

    def __init__(self, width: int, height: int, title: str = "PERCEPTION") -> None:
        import pygame
        self._pygame = pygame
        pygame.init()
        pygame.display.init()
        self._screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption(title)
        self._running = True
        self._clock = pygame.time.Clock()

    def show(self, bgr_frame: np.ndarray) -> bool:
        """Display a BGR numpy frame. Returns False if the window was closed."""
        if not self._running:
            return False
        # Pump events so the window stays responsive and we can detect close
        for event in self._pygame.event.get():
            if event.type == self._pygame.QUIT:
                self._running = False
                return False
        # cv2 gives BGR, pygame wants RGB. Also pygame.surfarray expects (W,H,3)
        rgb = bgr_frame[:, :, ::-1]
        surface = self._pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
        self._screen.blit(surface, (0, 0))
        self._pygame.display.flip()
        self._clock.tick(30)
        return True

    def close(self) -> None:
        try:
            self._pygame.display.quit()
            self._pygame.quit()
        except Exception:
            pass


def _synth_hud_state(frame_idx: int, pos: Point3, yaw: float) -> Dict[str, object]:
    return {
        "MODE": "DEMO",
        "HP": 100,
        "AMMO": 50,
        "POS": f"({pos[0]:.0f},{pos[1]:.0f},{pos[2]:.0f})",
        "YAW": f"{yaw:.0f}",
    }


def _read_live_state(path: str) -> Optional[Dict[str, object]]:
    """Read the HUD state file written by item_tour.py every 6 ticks.

    Returns None if the file is missing or malformed. Tolerant of races
    where item_tour.py is mid-write: errors are swallowed so the demo
    loop keeps running with the previous frame's pose.
    """
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _extract_pose_from_state(state: Dict[str, object]) -> Optional[Tuple[Point3, float]]:
    """Pull (pos, yaw) from the HUD JSON payload if present."""
    try:
        x = float(state.get("x", 0.0))
        y = float(state.get("y", 0.0))
        z = float(state.get("z", 0.0))
        yaw = float(state.get("yaw", 0.0))
        return ((x, y, z), yaw)
    except (TypeError, ValueError):
        return None


def _live_hud_extras(state: Dict[str, object]) -> Dict[str, object]:
    """Build the extra_hud dict from a live HUD state payload.

    Surfaces the most bot-relevant fields so the overlay shows what the
    bot is thinking in real time alongside what it's seeing.
    """
    intent = state.get("intent") or {}
    target = intent.get("sub") or intent.get("description") or ""
    macro = intent.get("macro") or ""
    area = state.get("current_room_type") or ""
    return {
        "MODE": str(macro or "LIVE"),
        "HP": str(state.get("health", "?")),
        "AMMO": str(state.get("ammo", "?")),
        "POS": f"({float(state.get('x', 0)):.0f},{float(state.get('y', 0)):.0f},{float(state.get('z', 0)):.0f})",
        "YAW": f"{float(state.get('yaw', 0)):.0f}",
        "AREA": str(area),
        "INTENT": str(target)[:40],
        "PAUSED": "YES" if state.get("is_paused_for_assess") else "no",
        "TICK": str(state.get("tick_count", 0)),
    }


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="demo_wireframe_room",
        description="Phase 11 wireframe perception grid demo (Version B — AAS-driven)",
    )
    p.add_argument("--aas", default="maps/oa_dm1.aas", help="path to AAS file")
    p.add_argument("--pos", type=_parse_pos, default=None, help="X,Y,Z bot position")
    p.add_argument("--yaw", type=float, default=90.0, help="bot yaw in degrees")
    p.add_argument("--orbit", action="store_true", help="animate yaw each frame")
    p.add_argument("--duration", type=float, default=10.0, help="runtime seconds")
    p.add_argument("--save", default="./tmp/wireframe_demo.mp4", help="output video path")
    p.add_argument("--show", action="store_true", help="attempt live cv2.imshow")
    p.add_argument("--no-glow", action="store_true")
    p.add_argument("--no-hud", action="store_true")
    p.add_argument("--profile", action="store_true", help="print per-stage timings")
    p.add_argument("--max-distance", type=float, default=384.0,
                   help="cull faces farther than this (smaller = less see-through)")
    p.add_argument("--max-areas", type=int, default=20)
    p.add_argument("--fps", type=int, default=30)
    # Alignment/size overrides — let the user match OpenArena's exact settings
    p.add_argument("--width", type=int, default=None,
                   help="render width in px (default 960, or 320 with --live)")
    p.add_argument("--height", type=int, default=None,
                   help="render height in px (default 600, or 240 with --live)")
    p.add_argument("--fov", type=float, default=None,
                   help="horizontal FOV in degrees (default 90, match game cg_fov)")
    p.add_argument("--camera-height", type=float, default=None,
                   help="eye offset above bot origin in Q3 units "
                        "(default 26 = DEFAULT_VIEWHEIGHT)")
    p.add_argument(
        "--live",
        action="store_true",
        help=f"read bot pose from {LIVE_STATE_PATH_DEFAULT} each frame (requires "
             "item_tour.py running in parallel)",
    )
    p.add_argument(
        "--live-state",
        default=LIVE_STATE_PATH_DEFAULT,
        help="path to HUD state JSON (defaults to ./tmp/oa_hud_state.json)",
    )
    p.add_argument(
        "--no-room",
        action="store_true",
        help="skip the holodeck room-frame aesthetic chrome; render only the "
             "AAS world geometry (recommended with --live for a clean first-"
             "person view of what the bot sees)",
    )
    p.add_argument(
        "--show-pygame",
        action="store_true",
        help="display frames in a pygame window (works with "
             "opencv-python-headless, unlike --show which needs cv2.imshow)",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _build_argparser().parse_args(argv)

    if not math.isfinite(args.yaw) or not (0.1 <= args.duration <= 3600):
        log.error("invalid --yaw or --duration")
        return 2

    log.info("Loading AAS: %s", args.aas)
    graph = parse_aas(args.aas)
    if graph is None:
        log.error("Failed to parse AAS file: %s", args.aas)
        return 1
    log.info("AAS loaded: %d areas", graph.num_areas)

    pos = args.pos if args.pos is not None else _default_pos_from_graph(graph)
    _verify_pos_in_walkable_area(graph, pos)

    # Resolve render size. Defaults: 960x600 for static/orbit runs; 320x240
    # for live runs so the wireframe fits next to the game + HUD windows.
    default_w = 320 if args.live and args.width is None else (args.width or 960)
    default_h = 240 if args.live and args.height is None else (args.height or 600)
    width = args.width if args.width is not None else default_w
    height = args.height if args.height is not None else default_h

    cfg = replace(
        RoomConfig(),
        width=width,
        height=height,
        room_width=1024.0,
        room_height=512.0,
        room_depth=2048.0,
        max_depth=2048.0,
        proximity_threshold=64.0,
        fov_deg=args.fov if args.fov is not None else 90.0,
        camera_height=args.camera_height if args.camera_height is not None else 26.0,
        glow=(not args.no_glow),
        hud=(not args.no_hud),
    )
    log.info("Render: %dx%d fov=%.1f camera_height=%.1f max_distance=%.0f",
             cfg.width, cfg.height, cfg.fov_deg, cfg.camera_height, args.max_distance)

    backend = AASDepthBackend(graph, camera_height=cfg.camera_height)
    renderer = WireframeRoomRenderer(cfg)

    writer, out_path = _open_writer(args.save, args.fps, cfg.width, cfg.height)

    stage_times: Dict[str, List[float]] = {
        "build_scene": [], "render": [], "write": [], "total": [],
    }
    imshow_warn = [False]

    # --live mode: read pose + extras from the HUD state file every frame.
    # Keep the last-good pose if the file vanishes mid-tour so we don't
    # stutter on momentary write races.
    live_pos: Point3 = pos
    live_yaw: float = args.yaw
    live_extras: Optional[Dict[str, object]] = None
    draw_room = not args.no_room
    if args.live:
        log.info("LIVE mode: polling %s for bot pose", args.live_state)
        log.info("draw_room_frame=%s (use --no-room to disable)", draw_room)

    # --show-pygame: open a pygame window that displays each frame
    pg_display: Optional[_PygameDisplay] = None
    if args.show_pygame:
        try:
            pg_display = _PygameDisplay(cfg.width, cfg.height,
                                        title="Phase 11 — Wireframe Perception")
            log.info("pygame display opened (%dx%d)", cfg.width, cfg.height)
        except Exception as e:
            log.warning("pygame display failed to open: %s", e)

    start = time.time()
    frame_idx = 0
    try:
        while True:
            t0 = time.perf_counter()

            if args.live:
                state = _read_live_state(args.live_state)
                if state is not None:
                    pose = _extract_pose_from_state(state)
                    if pose is not None:
                        live_pos, live_yaw = pose
                    live_extras = _live_hud_extras(state)
                pos_this_frame = live_pos
                yaw_this_frame = live_yaw
                hud_extras = live_extras or _synth_hud_state(frame_idx, live_pos, live_yaw)
            elif args.orbit:
                pos_this_frame = pos
                yaw_this_frame = (args.yaw + frame_idx * 2.0) % 360.0
                hud_extras = _synth_hud_state(frame_idx, pos_this_frame, yaw_this_frame)
            else:
                pos_this_frame = pos
                yaw_this_frame = args.yaw
                hud_extras = _synth_hud_state(frame_idx, pos_this_frame, yaw_this_frame)

            ts = time.perf_counter()
            scene = backend.build_scene(
                pos_this_frame, yaw_this_frame, args.max_distance, args.max_areas
            )
            stage_times["build_scene"].append((time.perf_counter() - ts) * 1000)

            ts = time.perf_counter()
            frame = renderer.render(
                pos_this_frame, yaw_this_frame, scene,
                extra_hud=hud_extras,
                state={"frame": frame_idx, "src_width": cfg.width, "src_height": cfg.height},
                draw_room_frame=draw_room,
            )
            stage_times["render"].append((time.perf_counter() - ts) * 1000)

            ts = time.perf_counter()
            writer.write(frame)
            stage_times["write"].append((time.perf_counter() - ts) * 1000)

            if args.show:
                _try_imshow(frame, imshow_warn)
            if pg_display is not None:
                if not pg_display.show(frame):
                    log.info("pygame window closed by user — exiting")
                    break

            stage_times["total"].append((time.perf_counter() - t0) * 1000)

            if time.time() - start > args.duration:
                break
            frame_idx += 1
    finally:
        writer.release()
        if args.show:
            try:
                cv2.destroyAllWindows()
            except cv2.error:
                pass
        if pg_display is not None:
            pg_display.close()

    log.info("Wrote %d frames to %s", frame_idx + 1, out_path)
    if args.profile and stage_times["total"]:
        n = len(stage_times["total"])
        print(f"── Per-stage timing (ms, median / p95 over {n} frames) ──")
        for stage, samples in stage_times.items():
            if samples:
                sorted_samples = sorted(samples)
                p95_idx = min(int(n * 0.95), n - 1)
                print(
                    f"  {stage:12s} median={statistics.median(samples):6.2f} "
                    f"p95={sorted_samples[p95_idx]:6.2f} "
                    f"n={len(samples)}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
