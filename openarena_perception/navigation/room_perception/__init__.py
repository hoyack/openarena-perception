"""Phase 13: Room perception subsystem.

Entities and algorithms for turning raycast point clouds into architectural
walls, corners, rooms, and doorways. Keeps navigation/ self-contained —
no imports into perception/ or combat/ per the Phase 4 extraction boundary.
"""
from openarena_perception.navigation.room_perception.corner_detector import (
    CornerDetector,
)
from openarena_perception.navigation.room_perception.doorway_detector import (
    DoorwayDetector,
)
from openarena_perception.navigation.room_perception.types import (
    Corner,
    Doorway,
    PartialRoom,
    Room,
    Wall,
)

__all__ = [
    "Wall",
    "Corner",
    "Room",
    "PartialRoom",
    "Doorway",
    "CornerDetector",
    "DoorwayDetector",
]
