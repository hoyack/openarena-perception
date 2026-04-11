# Phase 12 Deferred Items

## map_explorer.py

**File:** `map_explorer.py` (project root, UNTRACKED)

**Issue:** Not in git tracking but has references to the now-deleted
`strategic_hud.py`. Task 2 auto-fixed the file on disk (replaced
`strategic_hud.py` -> `open_perception.py` in the docstring and the
subprocess.Popen call) but did NOT add it to the commit — it was already
untracked and committing a whole new file is out of scope for this plan's
"replace legacy references" action.

**Status:** The file on disk is correctness-fixed; git does not track it.
Whoever owns map_explorer.py should decide whether to:
  1. Add it to git (then our on-disk fix gets committed alongside), or
  2. Leave it as a local script (the on-disk fix keeps it working).

**Verified:** No tracked file has any live `strategic_hud` or
`demo_wireframe_room` import; the only remaining matches are historical
docstrings and negative assertions in tests.
