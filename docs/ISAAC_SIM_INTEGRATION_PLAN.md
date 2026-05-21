# Isaac Sim Integration Plan

The current MVP uses `MockSimulationAdapter` for deterministic symbolic replay. Isaac Sim should enter through the same `SimulationAdapter` boundary so miners continue to receive `PublicRoomState` and return `Trajectory`.

## Adapter Boundary

Current contract:

- Input: validator-owned `EnvironmentState`
- Input: miner `Trajectory`
- Output: `ReplayResult`

Current Isaac-aligned scaffolding:

- `HotelRoomSceneManifest`: deterministic symbolic state to USD prim/frame map.
- `SoftLifeTrajectoryProvider`: Unitree-style action source for replay loops.
- `CompiledRobotCommand`: robot-oriented primitive compiled from miner actions.
- `PhysicsReplayArtifact`: validator-private physics truth schema for final object
  poses, zone membership, collisions, damage, drops, cleanliness, and command logs.
- `IsaacReplayBundle`: validator-private JSON handoff for an Isaac Lab machine.
- `export_scene_usd.py`: bootstrap USDA scene export with zones, target frames,
  objects, surfaces, and cameras.
- `score_physics_artifact.py`: ingestion path from Isaac physics truth back into
  the validator scorer.
- `IsaacSimSimulationAdapter`: optional backend boundary that currently raises a
  clear dependency error instead of importing Isaac Lab in the lightweight MVP.

Future adapter implementation:

- `IsaacSimSimulationAdapter`
- Loads or generates a hidden USD scene from validator state.
- Compiles symbolic actions into robot commands.
- Runs physics replay.
- Produces replay events, final object poses, collision/damage metrics, cleanliness state, and a deterministic replay hash.

Miner code should not change when the adapter switches from mock physics to Isaac Sim.

## Mapping Symbolic Room State To USD Assets

`EnvironmentState` should map into a scene manifest:

- Zones become named frames or regions: `entry`, `floor`, `bed`, `nightstand`, `desk`, `bathroom_counter`, `hamper`, `closet`, `trash_bin`.
- Objects become USD prims with stable IDs: towel, pillows, mug, remote, shoes, wrapper, toiletries.
- Object `target_zone` becomes a scoring region.
- Object traits become physical/scoring metadata:
  - `fragile`: damage penalty if dropped or high-force contact occurs.
  - `disposable`: valid for `dispose`.
  - `stubborn_dirt`: requires more cleaning passes or longer tool contact.
- Surfaces become cleanable regions with hidden dirt state.

The public state should only expose visible objects, visible surface estimates, and allowed zones.

## Randomized Messy Hotel Room Generation

Scene generation should be deterministic from validator-private seeds:

1. Choose a room layout template.
2. Sample object initial zones and local poses.
3. Sample occlusions and visibility.
4. Sample surface dirt maps.
5. Sample physical parameters such as friction, mass, and fragile thresholds.
6. Save a private manifest with seed, asset versions, and sampled parameters.
7. Emit a reduced `PublicRoomState` for miners.

The public challenge should not reveal the seed or full manifest.

## Hidden Validator Scenes

Validators own the USD scene and manifest. Miners never receive:

- USD scene paths for hidden evaluations.
- Random seeds.
- Hidden object poses.
- Hidden surface dirt maps.
- Collision or scoring internals before evaluation.
- Simulator handles or ROS2 topics connected to the hidden scene.

For public playground demos, validators may expose rendered views or replay logs, but those should be treated separately from hidden mainnet evaluation.

## Trajectory Mapping

Current action primitives:

- `move_to_zone(zone)`
- `move_to_object(object_id)`
- `pick(object_id)`
- `place(object_id, zone)`
- `clean_surface(zone)`
- `dispose(object_id)`

Isaac Sim mapping:

- `move_to_zone`: navigate base/end-effector to a named region frame.
- `move_to_object`: plan to a grasp/pre-grasp pose around the object prim.
- `pick`: close gripper and validate grasp attachment.
- `place`: move to target zone and release within scoring bounds.
- `clean_surface`: execute a tool/contact trajectory over the dirty surface region.
- `dispose`: release a disposable object into the trash bin region.

Each primitive should compile into lower-level commands with deterministic validation. Failed planning, unreachable goals, collisions, and dropped objects should become replay events.

## Physics Replay Logs

Isaac Sim replay should produce:

- Ordered primitive events.
- Start/end timestamps or simulation steps.
- Success/failure messages.
- Robot pose summaries.
- Held object state.
- Collision contacts and force summaries.
- Dropped object events.
- Damage events.
- Final object poses and zone membership.
- Cleanliness measurements.
- Replay hash over the canonical log.

Hidden logs can be stored by validators. Public logs should be redacted for hidden evaluations.

The concrete schema is `softlife.physics_replay.v1` in
`softlife_subnet.physics_artifacts`. Isaac should fill this artifact from real
simulator state, then the validator can convert it into the existing
`ReplayResult` and scoring pipeline.

## Scoring From Physics

Room readiness should read final simulator truth:

- Object placement: each object inside its target zone, not merely claimed by the miner.
- Trash disposal: disposable items inside the trash bin.
- Cleanliness: surface dirt maps below threshold.
- Damage: fragile items damaged or dropped reduce score.
- Collisions: robot/object collisions with forbidden regions reduce score.
- Efficiency: trajectory length, simulated time, and invalid primitive count.
- Safety: unsafe forces, speed, or unstable interactions can cap the score.

The current symbolic scorer is a placeholder for this richer physics-backed scorer.

## ROS2 Bridge And Real Robots

ROS2 compatibility should use the same primitive trajectory semantics:

- Convert `Trajectory` into ROS2 action goals or service requests.
- Use TF frames for zones and object poses.
- Use MoveIt or a task planner for arm/base planning.
- Use perception to map observed objects into public/private state.
- Use execution logs to construct a `ReplayResult` equivalent.

Real robot demos should start as supervised replays of trajectories already validated in Isaac Sim. The real-world bridge should add safety interlocks, emergency stop, speed limits, and operator approval.

## First Visual Demo

Initial Isaac Sim demo target:

1. Hotel room with bed, floor, nightstand, desk, trash bin, and hamper.
2. Towel on floor.
3. Cup/mug misplaced on nightstand or floor.
4. Pillow off bed.
5. Robot receives public state.
6. Miner returns trajectory:
   - move to towel, pick, place in hamper.
   - move to cup, pick, place on desk.
   - move to pillow, pick, place on bed.
   - clean visible dirty surface.
7. Validator replays in Isaac Sim.
8. UI/CLI shows replay log, score breakdown, leaderboard, and normalized weights.

This demo should prove the adapter boundary, not full autonomy.

## Current Isaac Handoff Command

From the repo root:

```bash
python3 integrations/isaac_lab/scripts/export_replay_bundle.py --seed 42 --out /tmp/softlife_seed42_bundle.json --pretty
```

That file is the input contract for the Isaac Lab implementation. It is
validator-private and must not be sent to miners.

Generate the bootstrap USD scene:

```bash
python3 integrations/isaac_lab/scripts/export_scene_usd.py --bundle /tmp/softlife_seed42_bundle.json --out /tmp/softlife_seed42_scene.usda
```

Score a returned physics artifact:

```bash
python3 integrations/isaac_lab/scripts/score_physics_artifact.py --bundle /tmp/softlife_seed42_bundle.json --artifact /tmp/softlife_seed42_artifact.json --seed 42 --pretty
```
