# Deferred Items — Phase 12.1

## Out-of-scope test failures observed during Plan 12.1-03 execution

- `tests/test_humanize.py::TestAimHumanization::test_accuracy_cap_enforced_in_aim_controller`
  - Pre-existing flaky test: noise RNG produced ratio 0.975 > threshold 0.95.
  - Unrelated to minimap/wireframe UI polish work.
  - Tracked here per GSD scope-boundary rule.
