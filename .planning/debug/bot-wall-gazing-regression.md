---
status: diagnosed
trigger: "After Phase 13, bot walks/spins/rotates a lot and looks at walls and corners on oa_dm1"
created: 2026-04-11
updated: 2026-04-11
---

## Current Focus

hypothesis: Phase 13 mechanically innocent. Suspect pre-existing scanning/perimeter behavior or learned_map state bias steering aim.
test: Diff Phase 13 vs baseline 47cfef3 for any motion/aim/nav touchpoints; inspect item_tour wall/scan logic; inspect learned_map.update() side effects.
expecting: Confirm learned_map.update() Phase 13 additions are pure (no aim/yaw side effects), then identify which behavior in item_tour or reactive_agent is rotating to walls.
next_action: git diff stat 47cfef3..HEAD; read learned_map.update; read item_tour wall/scan blocks.

## Symptoms

expected: On oa_dm1 bot tours items, aim along travel direction or threat vectors; rotations purposeful.
actual: Bot walks excessively, spins/rotates, deliberately looks at walls/corners.
errors: None. 774 tests pass.
reproduction: uv run python item_tour.py --no-vision on oa_dm1.
started: First live verification of Phase 13 (commits 1d1bcc7..d49899b). May predate Phase 13 (Phase 12.1 minimap was cluttered).

## Eliminated

- hypothesis: Phase 13 changed motion/aim/nav code
  evidence: `git diff 47cfef3..HEAD --stat` lists only learned_map.py, hud_schema.py, room_perception/, visualization panels, tests, docs. Zero diff in item_tour.py, navigator.py, wall_detector.py, reactive_agent.py. The wall-marking, edge-penalty, and cell_state logic in learned_map.py is byte-identical to baseline.
- hypothesis: Phase 13 per-tick current_room_id() side-effect bumps visit counts and somehow affects pathing
  evidence: rooms_per_floor is empty on disk ([0,0]) because fit_rooms() is never called from item_tour (separate known gap). The for-loop at lines 188-195 is a no-op. Block is pure observation.
- hypothesis: Room surveyor's 360-spin causes the wall-gazing
  evidence: item_tour.py:313 — `self.surveyor = RoomSurveyor(self.bridge) if use_vision else None`. With --no-vision the surveyor is None. perform_survey() never runs. Cannot be the cause for the user's reproduction.

## Evidence

- timestamp: 2026-04-11
  checked: git diff 47cfef3..HEAD --stat
  found: 26 files changed; only learned_map.py + hud_schema.py + new room_perception package + visualization panels + tests/docs. No motion/aim/nav file touched.
  implication: Phase 13 is mechanically innocent. Regression must be (a) pre-existing behavior made newly visible, or (b) state-bias (learned_map.json on disk).

- timestamp: 2026-04-11
  checked: /home/hoyack/.openarena/learned_maps/oa_dm1.json
  found: version=3 schema. Per-floor cell counts: floor0 {OPEN:9, WALL:30, VISITED:211}, floor1 {OPEN:49, WALL:88, VISITED:310}. Total 118 WALL cells across 521 VISITED cells. **edge_failures: 1958 entries (950 symmetric + 1008 directional)**. **258 directional entries with count >= 3 (penalty 10000 = effectively blocked)**. **443 symmetric entries with count >= 2 (penalty 1000+)**. edge_successes: 2142 entries / 8404 total. fitted_walls: [0,0]. rooms: [0,0]. raycasts_per_floor: [371,45].
  implication: The on-disk learned_map for oa_dm1 carries massive A* penalty bias. With 258 effectively-blocked one-way edges and 443 heavy-penalty symmetric edges, A* routes between items will take long, contorted detours through rare/unusual area chains rather than direct paths.

- timestamp: 2026-04-11
  checked: item_tour.py:284
  found: `self.agent.nav._edge_cost_fn = self.learned_map.edge_penalty` — navigator's A* cost function is wired directly to LearnedMap.edge_penalty().
  implication: All 258 blocked + 443 heavy-penalty edges are immediately active on the planner from the moment learned_map.load() runs. No reset, no decay, no success-weighting beyond `failures - successes*0.3` (and 1958 failures vs 2142 successes barely cancels — most heavy keys still dominate).

- timestamp: 2026-04-11
  checked: item_tour.py:1209-1239 _check_proactive_wall
  found: Two triggers — vision (wall_score>=0.80 OR streak>=2) and `learned_map.cell_state(lx,ly)==WALL` for a 72-unit forward projection (~1.1 grid cells). When either fires, item_tour.py:754-764 picks `turn_around` / `turn_left_and_strafe` / `turn_right_and_strafe` / `back_away`.
  implication: With 118 WALL cells already on-disk (avg ~1 wall per 4-5 visited cells), the forward look-ahead trips on a learned WALL cell whenever the planned route grazes near one. Each trip → forced rotation+strafe.

- timestamp: 2026-04-11
  checked: item_tour.py:339-341, 754-769, 786-788
  found: When proactive halt fires, `_avoidance_until = now + 0.5` and `_avoidance_hint = hint`. For the next 500ms `_execute_advisor_action(hint)` re-runs every tick (line 707-713) holding the turn+strafe action, blocking forward movement. Throttle between halts is also 0.5s (line 722).
  implication: Each halt → 500ms of committed rotation. If halts cluster (which they will when learned_map WALL cells are scattered across the planned route or when wall_detector mistriggers in a corner), the bot spends large fractions of each second rotating and strafing instead of moving. From the outside this looks like "walking and spinning and rotating around a lot and looking at walls and corners."

- timestamp: 2026-04-11
  checked: git show 47cfef3:openarena_perception/navigation/learned_map.py
  found: edge_penalty(), record_edge_failure(), cell_state(), and the wall-marking block (lines 199-212 today) are byte-identical to baseline. Wall-marking radius (30+40 distance) is unchanged.
  implication: All the mechanisms above existed at baseline. The bot has likely been doing this since Phase 12.1 (or earlier), but the user did not notice until the Phase 13 minimap rendered cleanly. Symptoms predate Phase 13; only visibility changed.

- timestamp: 2026-04-11
  checked: stat /home/hoyack/.openarena/learned_maps/oa_dm1.json
  found: Modify 2026-04-11 11:18 — learned_map for oa_dm1 was actively written during today's Phase 13 verification run. SAVE_INTERVAL = 60s (learned_map.py:68). The 1958 edge_failures were accumulated across many prior runs and continue to grow.
  implication: State bias is cumulative and persistent. Even if the bot fixed every navigation issue right now, the on-disk file would still steer A* into bad routes until the file is reset or pruned.

## Resolution

root_cause: |
  The wall-gazing/spinning behavior is NOT a Phase 13 regression. It is a pre-existing behavior with two reinforcing causes that have been growing across runs and only became visually obvious once the Phase 13 minimap stopped drawing red wall_segment stubs:

  1. **Persistent A* edge-failure bias.** /home/hoyack/.openarena/learned_maps/oa_dm1.json carries 1958 edge_failures (950 symmetric + 1008 directional). LearnedMap.edge_penalty() returns 10000 (effective block) for 258 directional edges with count>=3 and ~1000+ for 443 symmetric edges with count>=2. These penalties feed item_tour.py:284's wiring of nav._edge_cost_fn = learned_map.edge_penalty, so the navigator routes long, weird detours between items through low-traffic area chains. There is no decay, no cap, and no reset. The bias only ever grows. Symmetric/directional success-weighting (`failures - successes*0.3`) is too weak to cancel high-fail keys, so even traversed edges stay penalized.

  2. **Proactive wall halt firing on stale/scattered learned WALL cells, then committing 500ms of held rotation per fire.** _check_proactive_wall (item_tour.py:1209) projects 72 units forward and halts whenever cell_state() returns WALL. The on-disk file has 118 WALL cells across 521 VISITED cells — dense enough that any planned path running adjacent to a wall-marked cell trips a halt. Each halt picks turn_left_and_strafe / turn_right_and_strafe / turn_around / back_away (item_tour.py:754-764) and item_tour.py:339-341/786-788 commits that action for _AVOIDANCE_DURATION=0.5s. During that 500ms the bot is rotating in place. Halts can re-fire 500ms later; clusters of halts produce sustained rotation that visually reads as "spinning and looking at walls."

  Phase 13 itself only added passive observation (raycast capture, room inference state — neither of which mutates motion or aim) and rendering changes (cleaner minimap with no red wall_segment stubs). The cleaner minimap is what made the long-standing pathing pathology newly visible to the user during today's verification run.

  Note: WALL cells are also written by the same code during the run (learned_map.update() lines 199-206) using the wall_detector — so wall_detector false positives feed the proactive-halt trigger via learned_map state, creating a positive feedback loop where one mistrigger marks a WALL cell that then re-triggers next time the bot routes near that grid square.

fix: |
  Diagnose-only mode. No fix applied. Suggested fix directions:

  A. **Reset oa_dm1 state bias (immediate).** Either delete /home/hoyack/.openarena/learned_maps/oa_dm1.json before the next verification run, or selectively prune `edge_failures` entries with count>=3. This will not prevent the underlying behavior from re-accumulating but will give a clean baseline for any future fix.

  B. **Cap or decay edge_penalty (root fix #1).** LearnedMap.edge_penalty() should:
     - Cap penalty at, say, 50 instead of 10000 (so A* prefers alternates but doesn't treat anything as truly blocked).
     - Decay failure counts over time (per-session or per-N-traversals) so successful edges drop out of the penalty set.
     - Require N consecutive failures with no intervening success before raising penalty (currently a single fail bumps the count permanently).
     - Consider reducing the "directional fail >= 3 → 10000" rule, which produces 258 hard-blocked edges on this single map.

  C. **Make WALL cells less sticky (root fix #2).** learned_map.update() at lines 199-206 marks a WALL cell on a single 0.5-confidence vision read with no decay. Add:
     - Confidence accumulation: only flip a cell to WALL after K observations.
     - Auto-clear: if the bot later VISITS the cell, it should no longer be WALL (already partially handled by ray_march, but check the ordering).
     - Decay: WALL cells older than X seconds revert to UNKNOWN.

  D. **Decouple the learned_map look-ahead from rotation actions (root fix #3).** _check_proactive_wall + the action picker treat learned_map and vision identically. A learned-map-only halt should perhaps:
     - Use a smaller/no rotation (e.g. just slow down or replan), since learned_map is approximate.
     - Require corroboration from vision before committing a 500ms turn.
     - Or reduce _AVOIDANCE_DURATION to ~150ms so a single false-positive halt doesn't visibly spin the bot.

  E. **(Diagnostic) Add halt telemetry to the HUD/log.** Counter for vision-halts vs learned_map-halts vs visual_pin halts per minute, plus rotation duty cycle. This will let future verification runs quantify the pathology objectively instead of relying on subjective "looks like it's spinning."

verification: Pending — diagnose-only mode. Hand off root cause + suggested fixes to plan-phase --gaps for follow-up.
files_changed: []
