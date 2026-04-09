"""
commander.py — Strategic command & control layer.

Manages high-level goals:
  - Powerup collection routes (cycle through weapons, health, armor)
  - Enemy avoidance (flee when spotted, detour around known positions)
  - Survival priority (health > armor > weapons when low HP)
  - Score tracking via RCON

Runs every few seconds, sets navigation targets for the reactive agent.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)


@dataclass
class ItemMemory:
    """Tracks when we last visited/collected an item."""
    classname: str
    x: float
    y: float
    z: float
    last_visited: float = 0.0
    visit_count: int = 0
    priority: float = 1.0  # higher = more desirable


@dataclass
class EnemySighting:
    """Records where and when an enemy was seen."""
    x: float
    y: float
    timestamp: float
    threat_level: float = 1.0  # based on proximity and damage taken


class Commander:
    """
    Strategic decision maker. Picks navigation targets based on:
    - Current health/armor/ammo
    - Item respawn timing
    - Enemy positions (avoid or engage)
    - Overall survival strategy
    """

    # Item respawn times in Q3 (seconds)
    RESPAWN_WEAPON = 5.0
    RESPAWN_AMMO = 40.0
    RESPAWN_HEALTH = 35.0
    RESPAWN_ARMOR = 25.0
    RESPAWN_MEGA = 35.0  # Q3 source: RESPAWN_MEGAHEALTH = 35 (not RESPAWN_POWERUP = 120)

    # Strategy thresholds
    HEALTH_CRITICAL = 30
    HEALTH_LOW = 60
    ARMOR_DESIRE = 50  # seek armor when below this
    ENEMY_DANGER_RADIUS = 400.0  # avoid areas near recent enemy sightings
    ENEMY_MEMORY_DURATION = 15.0  # forget enemy positions after this

    DECISION_INTERVAL = 3.0  # seconds between strategic decisions

    def __init__(self, items: List[Tuple[str, float, float, float]], *,
                 item_timing: Optional[object] = None):
        self._item_timing = item_timing
        self.item_memory: List[ItemMemory] = []
        for classname, x, y, z in items:
            priority = self._item_priority(classname)
            self.item_memory.append(ItemMemory(
                classname=classname, x=x, y=y, z=z, priority=priority,
            ))

        self.enemy_sightings: List[EnemySighting] = []
        self._last_decision_time = 0.0
        self._current_goal: Optional[str] = None
        self._current_target: Optional[ItemMemory] = None
        self._alive_since: float = time.time()
        self._deaths = 0
        self._items_collected = 0

    def record_enemy(self, x: float, y: float):
        """Record an enemy sighting at a position."""
        now = time.time()
        self.enemy_sightings.append(EnemySighting(x=x, y=y, timestamp=now))
        # Prune old sightings
        self.enemy_sightings = [
            s for s in self.enemy_sightings
            if now - s.timestamp < self.ENEMY_MEMORY_DURATION
        ]

    def record_death(self):
        """Track deaths for strategy adjustment."""
        self._deaths += 1
        self._alive_since = time.time()

    def record_item_visited(self, classname: str, x: float, y: float):
        """Mark an item as collected."""
        for item in self.item_memory:
            if item.classname == classname and \
               math.hypot(item.x - x, item.y - y) < 200:
                item.last_visited = time.time()
                item.visit_count += 1
                self._items_collected += 1
                break

    def should_decide(self) -> bool:
        return time.time() - self._last_decision_time >= self.DECISION_INTERVAL

    def decide(self, health: Optional[int], armor: Optional[int],
               ammo: Optional[int], pos_x: float, pos_y: float,
               enemies_visible: int) -> Optional[ItemMemory]:
        """
        Make a strategic decision about what to do next.
        Returns the target ItemMemory to navigate to, or None for explore.
        """
        self._last_decision_time = time.time()
        now = time.time()

        hp = health if health is not None else 100
        ar = armor if armor is not None else 0

        # Record enemy positions if visible
        # (actual positions come from the perception system)

        # Priority 1: Critical health -- find health NOW
        if hp < self.HEALTH_CRITICAL:
            target = self._find_best_item(pos_x, pos_y, now,
                                           filter_fn=lambda i: "health" in i.classname,
                                           avoid_enemies=True)
            if target:
                self._current_goal = "SURVIVE"
                self._current_target = target
                log.info("CMD: SURVIVE -> %s at (%.0f,%.0f)",
                         target.classname, target.x, target.y)
                return target

        # Priority 2: Low health -- prefer health/armor
        if hp < self.HEALTH_LOW:
            target = self._find_best_item(pos_x, pos_y, now,
                                           filter_fn=lambda i: "health" in i.classname or "armor" in i.classname,
                                           avoid_enemies=True)
            if target:
                self._current_goal = "HEAL"
                self._current_target = target
                log.info("CMD: HEAL -> %s at (%.0f,%.0f)",
                         target.classname, target.x, target.y)
                return target

        # Priority 3: Collect weapons (if we haven't visited them recently)
        target = self._find_best_item(pos_x, pos_y, now,
                                       filter_fn=lambda i: "weapon" in i.classname and \
                                           now - i.last_visited > self.RESPAWN_WEAPON,
                                       avoid_enemies=enemies_visible > 0)
        if target:
            self._current_goal = "ARM"
            self._current_target = target
            log.info("CMD: ARM -> %s at (%.0f,%.0f)",
                     target.classname, target.x, target.y)
            return target

        # Priority 4: Collect armor
        if ar < self.ARMOR_DESIRE:
            target = self._find_best_item(pos_x, pos_y, now,
                                           filter_fn=lambda i: "armor" in i.classname and \
                                               now - i.last_visited > self.RESPAWN_ARMOR)
            if target:
                self._current_goal = "ARMOR"
                self._current_target = target
                log.info("CMD: ARMOR -> %s at (%.0f,%.0f)",
                         target.classname, target.x, target.y)
                return target

        # Priority 5: Mega health (if available)
        target = self._find_best_item(pos_x, pos_y, now,
                                       filter_fn=lambda i: "mega" in i.classname and \
                                           now - i.last_visited > self.RESPAWN_MEGA)
        if target:
            self._current_goal = "MEGA"
            self._current_target = target
            log.info("CMD: MEGA -> %s at (%.0f,%.0f)",
                     target.classname, target.x, target.y)
            return target

        # Default: visit the least-recently-visited item
        target = self._find_best_item(pos_x, pos_y, now,
                                       filter_fn=lambda i: True,
                                       prefer_stale=True)
        if target:
            self._current_goal = "PATROL"
            self._current_target = target
            log.info("CMD: PATROL -> %s at (%.0f,%.0f)",
                     target.classname, target.x, target.y)
            return target

        self._current_goal = "EXPLORE"
        return None

    def get_status(self) -> str:
        alive_time = time.time() - self._alive_since
        return (f"goal={self._current_goal or '?'} "
                f"alive={alive_time:.0f}s "
                f"items={self._items_collected} "
                f"deaths={self._deaths} "
                f"enemies_mem={len(self.enemy_sightings)}")

    def process_sound_events(self, events: list) -> None:
        """Feed game log events to item timing service."""
        if self._item_timing is not None:
            self._item_timing.process_events(events)

    # -- Internal -----------------------------------------------------------

    def _find_best_item(self, px: float, py: float, now: float,
                        filter_fn=None, avoid_enemies: bool = False,
                        prefer_stale: bool = False) -> Optional[ItemMemory]:
        """Find the best item to go to based on criteria."""
        candidates = [i for i in self.item_memory if filter_fn(i)]
        if not candidates:
            return None

        def score(item: ItemMemory) -> float:
            dist = math.hypot(item.x - px, item.y - py)
            # Base score: priority / distance
            s = item.priority * 1000.0 / max(dist, 50.0)

            # Penalize recently visited items (they haven't respawned)
            time_since = now - item.last_visited
            if item.last_visited > 0 and time_since < self._respawn_time(item.classname):
                s *= 0.1  # heavily penalize -- item hasn't respawned

            # Enhanced scoring with precise spawn prediction (COMP-02)
            if self._item_timing is not None:
                timer = self._item_timing.get_timer(item.classname)
                if timer is not None and not timer.is_available:
                    seconds_until = timer.seconds_until_spawn
                    if seconds_until > 5.0:
                        s *= 0.05  # not spawning soon, heavy penalty
                    else:
                        # Spawning soon -- boost based on travel-time match
                        travel_time = dist / 320.0  # Q3 run speed ~320 units/sec
                        timing_match = 1.0 - abs(seconds_until - travel_time) / max(seconds_until, 1.0)
                        s *= max(0.3, timing_match)

            # Prefer stale items (for patrol mode)
            if prefer_stale and item.last_visited > 0:
                s *= min(time_since / 30.0, 3.0)

            # Avoid areas near enemies
            if avoid_enemies:
                for sighting in self.enemy_sightings:
                    enemy_dist = math.hypot(item.x - sighting.x, item.y - sighting.y)
                    if enemy_dist < self.ENEMY_DANGER_RADIUS:
                        s *= 0.3

            return s

        return max(candidates, key=score)

    @staticmethod
    def _item_priority(classname: str) -> float:
        """Base priority for item types."""
        if "mega" in classname:
            return 5.0
        if "weapon_rocketlauncher" in classname:
            return 4.0
        if "weapon_lightning" in classname:
            return 3.5
        if "armor_body" in classname:
            return 3.0
        if "weapon" in classname:
            return 2.5
        if "armor_combat" in classname:
            return 2.0
        if "health_large" in classname:
            return 2.0
        if "health" in classname and "small" not in classname:
            return 1.5
        if "armor_shard" in classname:
            return 0.8
        if "health_small" in classname:
            return 0.7
        if "ammo" in classname:
            return 1.0
        return 0.5

    def _respawn_time(self, classname: str) -> float:
        if "mega" in classname:
            return self.RESPAWN_MEGA
        if "weapon" in classname:
            return self.RESPAWN_WEAPON
        if "armor" in classname:
            return self.RESPAWN_ARMOR
        if "health" in classname:
            return self.RESPAWN_HEALTH
        if "ammo" in classname:
            return self.RESPAWN_AMMO
        return 30.0
