"""Unit tests for FightOrFlight (TACT-03).

Tests fight/retreat/cautious decisions and disengage logic.
"""
from __future__ import annotations

import pytest

from openarena_perception.tactics.fight_or_flight import FightOrFlight


class TestFightOrFlight:
    """FightOrFlight.evaluate returns correct verdict for scenarios."""

    def test_fight_when_strong(self, make_awareness):
        """Health=100, armor=50, power weapon, 1 enemy -> FIGHT."""
        fof = FightOrFlight()
        sa = make_awareness(health=100, armor=50, weapon="rocket", enemies_visible=1,
                            nearest_enemy_distance="medium")
        result = fof.evaluate(sa)
        assert result == "FIGHT"

    def test_retreat_when_critical(self, make_awareness):
        """Health=20, no armor -> RETREAT."""
        fof = FightOrFlight()
        sa = make_awareness(health=20, armor=0, weapon="machinegun", enemies_visible=1,
                            nearest_enemy_distance="close")
        result = fof.evaluate(sa)
        assert result == "RETREAT"

    def test_cautious_when_weak_weapon(self, make_awareness):
        """Health=40, no power weapon -> CAUTIOUS or RETREAT."""
        fof = FightOrFlight()
        sa = make_awareness(health=40, armor=0, weapon="machinegun", enemies_visible=1,
                            nearest_enemy_distance="medium")
        result = fof.evaluate(sa)
        # effective_hp=40, no power weapon, below 50 -> RETREAT
        assert result in ("CAUTIOUS", "RETREAT")

    def test_retreat_when_outnumbered_low_health(self, make_awareness):
        """3 enemies, low health -> RETREAT."""
        fof = FightOrFlight()
        sa = make_awareness(health=50, armor=0, weapon="machinegun", enemies_visible=3,
                            nearest_enemy_distance="medium")
        result = fof.evaluate(sa)
        assert result == "RETREAT"

    def test_fight_high_hp_no_power_weapon(self, make_awareness):
        """High effective HP but no power weapon -> FIGHT (>50 hp rule)."""
        fof = FightOrFlight()
        sa = make_awareness(health=80, armor=30, weapon="shotgun", enemies_visible=1,
                            nearest_enemy_distance="medium")
        result = fof.evaluate(sa)
        assert result == "FIGHT"

    def test_parse_distance_none(self, make_awareness):
        """nearest_enemy_distance=None -> defaults to 999.0."""
        fof = FightOrFlight()
        sa = make_awareness(health=100, armor=50, weapon="rocket", enemies_visible=0,
                            nearest_enemy_distance=None)
        # Should not crash
        result = fof.evaluate(sa)
        assert result in ("FIGHT", "RETREAT", "CAUTIOUS")


class TestShouldDisengage:
    """FightOrFlight.should_disengage checks critical health."""

    def test_disengage_critical_health(self, make_awareness):
        """Health < 25 -> should disengage."""
        fof = FightOrFlight()
        sa = make_awareness(health=20, weapon="rocket")
        assert fof.should_disengage(sa) is True

    def test_no_disengage_healthy(self, make_awareness):
        """Health > 50 -> should NOT disengage."""
        fof = FightOrFlight()
        sa = make_awareness(health=80, weapon="rocket")
        assert fof.should_disengage(sa) is False

    def test_disengage_low_health_weak_weapon_close(self, make_awareness):
        """Health < 50 + machinegun + close enemy -> disengage."""
        fof = FightOrFlight()
        sa = make_awareness(health=40, weapon="machinegun",
                            nearest_enemy_distance="close")
        assert fof.should_disengage(sa) is True

    def test_no_disengage_low_health_power_weapon(self, make_awareness):
        """Health < 50 but power weapon -> no disengage (weapon check)."""
        fof = FightOrFlight()
        sa = make_awareness(health=40, weapon="rocket",
                            nearest_enemy_distance="close")
        assert fof.should_disengage(sa) is False
