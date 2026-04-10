# Phase 11 — Deferred Items

Issues observed during Phase 11 execution that are OUT OF SCOPE for Phase 11
plans. Do not fix here — track for a future cleanup plan.

## Flaky / stochastic tests

- **`tests/test_humanize.py::TestAimHumanization::test_accuracy_cap_enforced_in_aim_controller`**
  - **Observed during:** Plan 11-01 full-suite regression check (2026-04-10)
  - **Symptom:** Asserts `ratio < 0.95` on a randomised on-target ratio; occasionally
    returns exactly 1.0 when the seeded noise happens not to push any sample off target.
  - **Scope:** Pre-existing. Passes when run in isolation (`pytest ... -q` alone).
    Unrelated to `openarena_perception/visualization/`. No Phase 11 code involved.
  - **Recommended fix (future):** Seed the RNG in the test or widen the tolerance.
