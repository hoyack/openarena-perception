"""Prompt templates for the async spatial advisor."""

SPATIAL_ADVISOR_PROMPT = """You are a real-time spatial advisor for a Q3 arena bot. The attached screenshot shows what the bot sees RIGHT NOW. You must answer fast — the bot keeps moving.

CURRENT STATE:
Position: ({px}, {py}, {pz})  Yaw: {yaw}°  AAS area: {area}
Goal: {goal_desc}
Recent trail (last ~3s): {trail_summary}
Last problem: {last_problem}

YOUR JOB:
1. Describe the spatial context in 1 short sentence (room type, key features)
2. List ANY immediate hazards visible in front of the bot within ~3 meters:
   - lava/slime pits or pools
   - ledges/drops (the bot is on a raised platform with empty space ahead)
   - walls or dead ends directly ahead
   - locked doors/bars blocking the path
3. Suggest an immediate action if the bot should change direction
4. Confidence 0.0-1.0

SEVERITY guide:
- high: walking forward WILL cause death or major setback (lava, fatal drop)
- medium: walking forward WILL cause minor stuck/damage (wall, short drop)
- low: advisory only

RESPOND WITH JSON ONLY (no markdown, no explanation):
{{
  "narrative": "short spatial description",
  "hazards": [
    {{"kind": "lava", "direction": "ahead", "severity": "high", "text": "lava pool 2m ahead, backing away required"}}
  ],
  "action_hint": "walk_forward",
  "confidence": 0.7
}}

action_hint must be one of: walk_forward, turn_left_90, turn_right_90, turn_around, back_away, stop, strafe_left, strafe_right
hazard kind must be one of: lava, ledge, drop, wall, bars, dead_end, none"""


def build_trail_summary(trail_points) -> str:
    """Build a compact summary of the recent position trail."""
    if not trail_points:
        return "no trail"

    points = list(trail_points)[-6:]  # last 6 points ~ 3s at 2Hz sampling
    if len(points) < 2:
        return f"just arrived at area {points[0].area}"

    areas = []
    last_area = None
    for p in points:
        if p.area != last_area:
            areas.append(p.area)
            last_area = p.area

    start = points[0]
    end = points[-1]
    dx = end.x - start.x
    dy = end.y - start.y
    dz = end.z - start.z

    direction = ""
    if abs(dz) > 16:
        direction = "going up" if dz > 0 else "going down"
    elif abs(dx) > 30 or abs(dy) > 30:
        direction = "moving"
    else:
        direction = "roughly stationary"

    area_path = " -> ".join(str(a) for a in areas[-4:])
    return f"{direction}, through areas [{area_path}], net delta ({dx:+.0f},{dy:+.0f},{dz:+.0f})"


def describe_goal(pos, goal_pos, goal_name: str) -> str:
    """Build a compact goal description with relative direction."""
    if not pos or not goal_pos:
        return goal_name or "explore"

    import math
    dx = goal_pos[0] - pos[0]
    dy = goal_pos[1] - pos[1]
    dz = goal_pos[2] - pos[2]
    dist = math.hypot(dx, dy)

    # Direction as compass bearing
    bearing = math.degrees(math.atan2(dy, dx)) % 360
    dirs = ["E", "NE", "N", "NW", "W", "SW", "S", "SE"]
    compass = dirs[int((bearing + 22.5) % 360 / 45)]

    height_note = ""
    if dz > 20:
        height_note = f", UP {dz:.0f} units"
    elif dz < -20:
        height_note = f", DOWN {abs(dz):.0f} units"

    return f"{goal_name} at ({goal_pos[0]:.0f},{goal_pos[1]:.0f},{goal_pos[2]:.0f}) — {compass} {dist:.0f} units away{height_note}"
