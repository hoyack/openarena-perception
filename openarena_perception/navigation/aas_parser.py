"""
aas_parser.py — Parse Quake 3 AAS (Area Awareness System) navigation files.

AAS files contain the nav mesh used by Q3 bots:
  - Areas: convex regions of walkable space with bounding boxes + centers
  - Reachability: how to travel between areas (walk, jump, swim, ladder, etc.)
  - Area settings: flags, cluster info, reachability indices

EAAS v5 format (ioquake3/OpenArena):
  Header: ident(4) + version(4)
  Then XOR-encrypted block: bspchecksum(4) + 14 lumps * (ofs(4) + len(4))
  XOR key: byte[i] ^= (i * 119) & 0xFF
"""

from __future__ import annotations

import json
import logging
import math
import os
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

TRAVEL_WALK = 1
TRAVEL_CROUCH = 2
TRAVEL_BARRIERJUMP = 3
TRAVEL_JUMP = 4
TRAVEL_LADDER = 5
TRAVEL_WALKOFFLEDGE = 6
TRAVEL_SWIM = 7
TRAVEL_WATERJUMP = 8
TRAVEL_TELEPORT = 9
TRAVEL_ELEVATOR = 10
TRAVEL_JUMPPAD = 17

TRAVEL_NAMES = {
    1: 'walk', 2: 'crouch', 3: 'barrierjump', 4: 'jump', 5: 'ladder',
    6: 'walkoffledge', 7: 'swim', 8: 'waterjump', 9: 'teleport',
    10: 'elevator', 11: 'rocketjump', 12: 'bfgjump', 13: 'grapple',
    14: 'doublejump', 15: 'rampjump', 16: 'strafejump', 17: 'jumppad',
}


@dataclass
class AASReach:
    """A reachability edge between two AAS areas."""
    dest_area: int
    travel_type: int
    start: Tuple[float, float, float]  # where to stand before crossing
    end: Tuple[float, float, float]    # where you arrive after crossing


@dataclass
class AASArea:
    idx: int
    cx: float
    cy: float
    cz: float
    mins: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    maxs: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    is_liquid: bool = False
    neighbors: List[int] = field(default_factory=list)
    travel_types: List[int] = field(default_factory=list)
    reaches: List[AASReach] = field(default_factory=list)


@dataclass
class AASGraph:
    """Parsed AAS nav graph ready for pathfinding."""
    areas: List[AASArea]
    num_areas: int

    def nearest_area(self, x: float, y: float, z: float) -> int:
        """Find the area closest to a world position.
        Z is weighted at 1.0 (same as XY) for proper multi-level matching."""
        best_idx = 0
        best_dist = float('inf')
        for i, a in enumerate(self.areas):
            if i == 0:
                continue  # area 0 is a dummy
            d = math.hypot(a.cx - x, a.cy - y) + abs(a.cz - z)
            if d < best_dist:
                best_dist = d
                best_idx = i
        return best_idx

    def area_center(self, idx: int) -> Tuple[float, float, float]:
        a = self.areas[idx]
        return (a.cx, a.cy, a.cz)


def parse_aas(filepath: str) -> Optional[AASGraph]:
    """Parse an EAAS v5 file and return the nav graph."""
    try:
        with open(filepath, 'rb') as f:
            data = bytearray(f.read())
    except Exception as e:
        log.error("Cannot read AAS file %s: %s", filepath, e)
        return None

    if data[:4] != b'EAAS' or struct.unpack_from('<I', data, 4)[0] != 5:
        log.error("Not a valid EAAS v5 file")
        return None

    # Decrypt lump directory
    dec = bytearray(data[8:8+116])
    for i in range(len(dec)):
        dec[i] ^= (i * 119) & 0xFF

    def lump(idx):
        return struct.unpack_from('<II', dec, 4 + idx*8)

    ofs_a, len_a = lump(7)   # areas
    ofs_s, len_s = lump(8)   # areasettings
    ofs_r, len_r = lump(9)   # reachability

    num_areas = len_a // 48
    num_reach = len_r // 44  # 44 bytes per entry (42 + 2 padding)

    # Validate
    if ofs_a + len_a > len(data) or ofs_s + len_s > len(data) or ofs_r + len_r > len(data):
        log.error("AAS lump data out of bounds")
        return None

    # Parse areas
    # NOTE: this parser reads three lumps (areas=7, areasettings=8, reach=9).
    # Lumps 0-6 contain bboxes/vertexes/planes/edges/edgeindex/faces/faceindex,
    # providing the full polyhedral mesh. Decoding them would enable pixel-accurate
    # wall rendering; currently AASDepthBackend uses the per-area AABB only.
    # See .planning/phases/11-wireframe-perception-grid/11-RESEARCH.md for the
    # full lump table and byte offsets.
    areas = []
    for i in range(num_areas):
        base = ofs_a + i * 48
        mins = struct.unpack_from('<3f', data, base + 12)
        maxs = struct.unpack_from('<3f', data, base + 24)
        center = struct.unpack_from('<3f', data, base + 36)
        areas.append(AASArea(
            idx=i,
            cx=center[0], cy=center[1], cz=center[2],
            mins=mins, maxs=maxs,
        ))

    # Parse area settings: flags (liquid detection) + firstReach
    first_reaches = []
    for i in range(num_areas):
        base = ofs_s + i * 28
        flags = struct.unpack_from('<i', data, base + 4)[0]
        first_reach = struct.unpack_from('<i', data, base + 24)[0]
        first_reaches.append(first_reach)
        areas[i].is_liquid = bool(flags & 4)  # AREA_LIQUID flag

    # Parse reachability entries (with start/end vectors)
    reaches = []
    for i in range(num_reach):
        base = ofs_r + i * 44
        dest = struct.unpack_from('<i', data, base)[0]
        start = struct.unpack_from('<3f', data, base + 12)
        end = struct.unpack_from('<3f', data, base + 24)
        ttype = struct.unpack_from('<i', data, base + 36)[0] & 0xFF
        reaches.append(AASReach(dest_area=dest, travel_type=ttype,
                                start=start, end=end))

    # Build adjacency from firstReach gaps
    sorted_starts = sorted(set(fr for fr in first_reaches if fr > 0))
    sorted_starts.append(num_reach)

    fr_to_count = {}
    for i in range(len(sorted_starts) - 1):
        fr_to_count[sorted_starts[i]] = sorted_starts[i+1] - sorted_starts[i]

    for area_idx in range(num_areas):
        fr = first_reaches[area_idx]
        count = fr_to_count.get(fr, 0)
        for j in range(count):
            ri = fr + j
            if ri < num_reach:
                r = reaches[ri]
                if 0 < r.dest_area < num_areas:
                    areas[area_idx].neighbors.append(r.dest_area)
                    areas[area_idx].travel_types.append(r.travel_type)
                    areas[area_idx].reaches.append(r)

    connected = sum(1 for a in areas if a.neighbors)
    total_edges = sum(len(a.neighbors) for a in areas)
    log.info("AAS parsed: %d areas, %d connected, %d edges", num_areas, connected, total_edges)

    return AASGraph(areas=areas, num_areas=num_areas)
