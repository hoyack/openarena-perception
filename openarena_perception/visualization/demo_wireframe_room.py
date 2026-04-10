"""Phase 11 wireframe renderer CLI demo.

Usage:
    uv run python -m openarena_perception.visualization.demo_wireframe_room \
        --aas maps/oa_dm1.aas --pos 232,1600,-112 --yaw 90 --orbit --duration 10

Records an orbit video to ./tmp/wireframe_demo.mp4 by default. Pi-native:
uses the AAS geometry backend (no neural inference).
"""
from __future__ import annotations

import argparse
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


def _synth_hud_state(frame_idx: int, pos: Point3, yaw: float) -> Dict[str, object]:
    return {
        "MODE": "DEMO",
        "HP": 100,
        "AMMO": 50,
        "POS": f"({pos[0]:.0f},{pos[1]:.0f},{pos[2]:.0f})",
        "YAW": f"{yaw:.0f}",
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
    p.add_argument("--max-distance", type=float, default=1024.0)
    p.add_argument("--max-areas", type=int, default=20)
    p.add_argument("--fps", type=int, default=30)
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

    cfg = replace(
        RoomConfig(),
        room_width=1024.0,
        room_height=512.0,
        room_depth=2048.0,
        max_depth=2048.0,
        proximity_threshold=64.0,
        camera_height=40.0,
        glow=(not args.no_glow),
        hud=(not args.no_hud),
    )

    backend = AASDepthBackend(graph, camera_height=cfg.camera_height)
    renderer = WireframeRoomRenderer(cfg)

    writer, out_path = _open_writer(args.save, args.fps, cfg.width, cfg.height)

    stage_times: Dict[str, List[float]] = {
        "build_scene": [], "render": [], "write": [], "total": [],
    }
    imshow_warn = [False]

    start = time.time()
    frame_idx = 0
    try:
        while True:
            t0 = time.perf_counter()
            if args.orbit:
                yaw = (args.yaw + frame_idx * 2.0) % 360.0
            else:
                yaw = args.yaw

            ts = time.perf_counter()
            scene = backend.build_scene(pos, yaw, args.max_distance, args.max_areas)
            stage_times["build_scene"].append((time.perf_counter() - ts) * 1000)

            ts = time.perf_counter()
            frame = renderer.render(
                pos, yaw, scene,
                extra_hud=_synth_hud_state(frame_idx, pos, yaw),
                state={"frame": frame_idx, "src_width": cfg.width, "src_height": cfg.height},
            )
            stage_times["render"].append((time.perf_counter() - ts) * 1000)

            ts = time.perf_counter()
            writer.write(frame)
            stage_times["write"].append((time.perf_counter() - ts) * 1000)

            if args.show:
                _try_imshow(frame, imshow_warn)

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
