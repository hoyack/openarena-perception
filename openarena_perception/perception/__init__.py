"""OpenArena Perception -- perception subsystem.

Stub created in Phase 1. Code will be extracted here in Phase 2.

Re-exports from legacy perception.py to maintain backward compatibility.
"""
import importlib.util as _ilu
import sys as _sys
from pathlib import Path as _Path

# Load the sibling perception.py that this package directory shadows.
_legacy = _Path(__file__).parent.parent / "perception.py"
_mod_name = "openarena_perception._perception_legacy"
_spec = _ilu.spec_from_file_location(_mod_name, str(_legacy))
_mod = _ilu.module_from_spec(_spec)
_sys.modules[_mod_name] = _mod
_spec.loader.exec_module(_mod)

# Re-export the Perception class so existing imports keep working:
#   from openarena_perception.perception import Perception
Perception = _mod.Perception
