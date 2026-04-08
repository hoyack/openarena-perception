"""OpenArena Perception -- combat subsystem.

Stub created in Phase 1. Code will be extracted here in Phase 4.

Re-exports from legacy combat.py to maintain backward compatibility.
"""
import importlib.util as _ilu
import sys as _sys
from pathlib import Path as _Path

# Load the sibling combat.py that this package directory shadows.
_legacy = _Path(__file__).parent.parent / "combat.py"
_mod_name = "openarena_perception._combat_legacy"
_spec = _ilu.spec_from_file_location(_mod_name, str(_legacy))
_mod = _ilu.module_from_spec(_spec)
_sys.modules[_mod_name] = _mod
_spec.loader.exec_module(_mod)

# Re-export classes so existing imports keep working:
#   from openarena_perception.combat import CombatMover, WeaponInfo
CombatMover = _mod.CombatMover
WeaponInfo = _mod.WeaponInfo
