"""Integration test for the full perception-to-decision-to-action loop (TEST-04).

Tests the cognitive pipeline: SituationalAwareness -> SubsumptionArbiter ->
TacticalFSM state transition -> subsystem behavior dispatch -> action output.

Uses real instances of SubsumptionArbiter, TacticalFSM, and subsystem handlers
with mocked low-level I/O (GameBridge, VirtualController). Validates that data
flows correctly through the full pipeline without a real game connection.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from openarena_perception.combat import CombatEngager, CombatMover
from openarena_perception.models import BrainState, SituationalAwareness
from openarena_perception.navigation import NavBehavior, Navigator, Commander
from openarena_perception.reflexes.arbiter import SubsumptionArbiter
from openarena_perception.reflexes.death_handler import DeathHandler
from openarena_perception.reflexes.stuck_escape import StuckEscape
from openarena_perception.tactics.fsm import TacticalFSM


# ---------------------------------------------------------------------------
# Shared Fixtures
# ---------------------------------------------------------------------------

def _make_sa(**overrides) -> SituationalAwareness:
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


def _build_fsm():
    """Build a TacticalFSM with real subsystem handlers and mocked I/O.

    Returns (fsm, ctrl_mock, bridge_mock, navigator_mock) so tests can
    inspect what actions were dispatched.
    """
    ctrl = MagicMock()
    bridge = MagicMock()
    bridge.rcon.return_value = ""

    navigator = MagicMock(spec=Navigator)
    navigator.graph = MagicMock()
    navigator.has_path = True
    navigator.is_stuck = False
    navigator.is_recovering = False
    navigator.path_to_random.return_value = True
    navigator.follow_path.return_value = None

    commander = MagicMock(spec=Commander)
    commander.should_decide.return_value = False

    aas_graph = MagicMock()

    # Build real subsystem handlers
    arbiter = SubsumptionArbiter()
    death_handler = DeathHandler(bridge, ctrl)
    stuck_escape = StuckEscape(navigator)
    mover = CombatMover()
    engager = CombatEngager(ctrl, bridge, mover)
    nav_behavior = NavBehavior(ctrl, navigator, commander, aas_graph)

    fsm = TacticalFSM(
        arbiter=arbiter,
        death_handler=death_handler,
        stuck_escape=stuck_escape,
        engager=engager,
        nav_behavior=nav_behavior,
        ctrl=ctrl,
        anomaly_tracker=MagicMock(),
        obj_tracker=MagicMock(),
    )

    return fsm, ctrl, bridge, navigator


# ---------------------------------------------------------------------------
# TEST-04: Perception to Action Loop
# ---------------------------------------------------------------------------

class TestPerceptionToActionLoop:
    """Integration tests for the full cognitive pipeline."""

    def test_combat_loop(self):
        """Enemy visible + under attack -> FSM transitions to COMBAT, engager fires."""
        fsm, ctrl, bridge, nav = _build_fsm()

        sa = _make_sa(
            under_attack=True,
            enemies_visible=2,
            attacker_direction=-1,
            seconds_since_damage=0.1,
        )
        gs = MagicMock()

        # Tick the FSM -- should transition to COMBAT and dispatch combat behavior
        asyncio.run(fsm.tick(sa, gs, tick_count=1))

        assert fsm.state == BrainState.COMBAT
        # CombatEngager.on_enter calls bridge.fire(True)
        bridge.fire.assert_any_call(True)
        # Combat tick should call ctrl.turn_degrees for target acquisition
        ctrl.turn_degrees.assert_called()

    def test_navigation_loop(self):
        """No enemies, has path -> FSM stays NAVIGATING/EXPLORING, nav produces movement."""
        fsm, ctrl, bridge, nav = _build_fsm()

        # Start in EXPLORING (default)
        assert fsm.state == BrainState.EXPLORING

        sa = _make_sa(
            enemies_visible=0,
            under_attack=False,
            has_path=True,
        )
        gs = MagicMock()

        asyncio.run(fsm.tick(sa, gs, tick_count=1))

        # Should stay in EXPLORING (no commander decision, has path)
        assert fsm.state == BrainState.EXPLORING
        # NavBehavior.tick_exploring calls ctrl.forward(True)
        ctrl.forward.assert_any_call(True)

    def test_death_loop(self):
        """alive=False -> DEAD, then alive=True -> EXPLORING."""
        fsm, ctrl, bridge, nav = _build_fsm()

        # Step 1: Die
        sa_dead = _make_sa(is_alive=False, health=0, disposition="dead")
        gs = MagicMock()

        asyncio.run(fsm.tick(sa_dead, gs, tick_count=1))
        assert fsm.state == BrainState.DEAD

        # DeathHandler should release controls and tap attack for respawn
        bridge.release_all.assert_called()
        bridge.cmd.assert_any_call("+attack")
        bridge.cmd.assert_any_call("-attack")

        # Step 2: Respawn
        sa_alive = _make_sa(is_alive=True, health=100, disposition="healthy")
        asyncio.run(fsm.tick(sa_alive, gs, tick_count=2))

        # Should transition to EXPLORING after respawn
        assert fsm.state == BrainState.EXPLORING
        # NavBehavior.on_enter_exploring calls navigator.path_to_random
        nav.path_to_random.assert_called()

    def test_reflex_override(self):
        """Damage direction set -> reflex layer drives COMBAT before FSM normal path."""
        fsm, ctrl, bridge, nav = _build_fsm()

        # Start in EXPLORING, then take damage with enemy visible
        sa = _make_sa(
            under_attack=True,
            enemies_visible=1,
            attacker_direction=1,
            seconds_since_damage=0.2,
        )
        gs = MagicMock()

        asyncio.run(fsm.tick(sa, gs, tick_count=1))

        # Arbiter should override EXPLORING -> COMBAT (P2 priority)
        assert fsm.state == BrainState.COMBAT
        # Combat snap should turn toward attacker direction
        # attacker_direction=1, so turn_degrees(-1 * 15) = -15
        ctrl.turn_degrees.assert_any_call(-15)

    def test_stuck_to_exploring(self):
        """Stuck condition -> STUCK state, then unstuck -> NAVIGATING."""
        fsm, ctrl, bridge, nav = _build_fsm()

        # First transition to NAVIGATING by providing a commander decision
        fsm._state = BrainState.NAVIGATING
        fsm._state_enter_time = time.time()

        # Now simulate stuck
        sa_stuck = _make_sa(
            is_stuck=True,
            is_recovering=False,
            has_path=True,
        )
        gs = MagicMock()

        asyncio.run(fsm.tick(sa_stuck, gs, tick_count=1))
        assert fsm.state == BrainState.STUCK

        # StuckEscape.on_enter should have been called (increments stuck attempts)
        # Now simulate recovery
        sa_unstuck = _make_sa(
            is_stuck=False,
            is_recovering=False,
            has_path=True,
        )
        asyncio.run(fsm.tick(sa_unstuck, gs, tick_count=2))

        # Should transition back to NAVIGATING after unstuck
        assert fsm.state == BrainState.NAVIGATING

    def test_dead_priority_overrides_combat(self):
        """DEAD is the highest priority -- overrides even active COMBAT."""
        fsm, ctrl, bridge, nav = _build_fsm()

        # Force into COMBAT state
        fsm._state = BrainState.COMBAT
        fsm._state_enter_time = time.time()

        # Die while in combat
        sa = _make_sa(
            is_alive=False,
            health=0,
            disposition="dead",
            under_attack=True,
            enemies_visible=1,
        )
        gs = MagicMock()

        asyncio.run(fsm.tick(sa, gs, tick_count=1))

        # DEAD overrides COMBAT (P1 > P2)
        assert fsm.state == BrainState.DEAD

    def test_full_lifecycle(self):
        """Full lifecycle: EXPLORING -> COMBAT -> DEAD -> EXPLORING."""
        fsm, ctrl, bridge, nav = _build_fsm()

        gs = MagicMock()

        # 1. Start exploring
        sa_explore = _make_sa(enemies_visible=0, under_attack=False, has_path=True)
        asyncio.run(fsm.tick(sa_explore, gs, tick_count=1))
        assert fsm.state == BrainState.EXPLORING

        # 2. Enter combat
        sa_combat = _make_sa(
            under_attack=True, enemies_visible=1,
            attacker_direction=-1, seconds_since_damage=0.1,
        )
        asyncio.run(fsm.tick(sa_combat, gs, tick_count=2))
        assert fsm.state == BrainState.COMBAT

        # 3. Die
        sa_dead = _make_sa(is_alive=False, health=0, disposition="dead")
        asyncio.run(fsm.tick(sa_dead, gs, tick_count=3))
        assert fsm.state == BrainState.DEAD

        # 4. Respawn
        sa_alive = _make_sa(is_alive=True, health=100, disposition="healthy")
        asyncio.run(fsm.tick(sa_alive, gs, tick_count=4))
        assert fsm.state == BrainState.EXPLORING
