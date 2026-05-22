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
- `run_isaac_stage_replay.py`: Isaac Sim runtime bridge that loads the stage,
  applies compiled command effects, optionally captures viewport frames, and
  writes a physics artifact.
- `stage_truth.py`: final USD prim transform and surface dirt extraction into
  the validator physics artifact.
- `RobotReplayController`: controller boundary used by the Isaac runner. The
  current implementation is `StageReplayController`; the next one should be a
  Unitree/Isaac controller that drives robot articulations and grippers.
- `UnitreeIsaacReplayController`: command mapper from Soft Life compiled
  commands to backend operations such as navigate, approach, grasp, release,
  drop, and wipe.
- `UnitreeIsaacBackend`: protocol for the concrete Isaac Lab / Unitree backend
  that owns env handles, articulations, gripper commands, contacts, cameras,
  and physics snapshots.
- `StageBackedUnitreeBackend`: transitional Isaac backend that lets the Unitree
  controller mutate and snapshot a USD stage before articulated robot control is
  available.
- `score_physics_artifact.py`: ingestion path from Isaac physics truth back into
  the validator scorer.
- `IsaacSimSimulationAdapter`: validator-facing adapter bridge with local
  `stage_dry_run` and Isaac workstation `stage` modes.

Current adapter implementation:

- `IsaacSimSimulationAdapter`
- Compiles symbolic actions into robot commands.
- Returns a `ReplayResult` from `softlife.physics_replay.v1` in `stage_dry_run`.
- Lazily calls the Isaac stage runner in `stage` mode.
- Still avoids importing Isaac Lab in lightweight module import paths.

Future articulated implementation:

- Loads or generates a hidden USD scene from validator state.
- Compiles symbolic actions into robot commands.
- Runs physics replay.
- Produces replay events, final object poses, collision/damage metrics, cleanliness state, and a deterministic replay hash.

Miner code should not change when the adapter switches from mock physics to Isaac Sim.

Validator-side usage:

```python
IsaacSimSimulationAdapter(runtime_mode="stage_dry_run").replay(environment_state, trajectory)
IsaacSimSimulationAdapter(runtime_mode="stage").replay(environment_state, trajectory)
```

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

Run the current stage-level bridge inside Isaac Sim:

```bash
./python.sh /path/to/softlife-subnet-demo/integrations/isaac_lab/scripts/run_isaac_stage_replay.py \
  --bundle /tmp/softlife_seed42_bundle.json \
  --scene /tmp/softlife_seed42_scene.usda \
  --out-artifact /tmp/softlife_seed42_isaac_artifact.json \
  --render-dir /tmp/softlife_frames
```

This is not yet robot manipulation. It proves the Isaac runtime path,
stage loading, command execution, final stage truth extraction, optional frame
capture, and artifact return.

Run the current multi-seed acceptance gate:

```bash
python3 integrations/isaac_lab/scripts/validate_isaac_workflow.py \
  --out-dir /tmp/softlife_isaac_validation \
  --pretty
```

On an Isaac workstation, use the same script with Isaac Sim's Python and
`--real-stage --capture-frames` to verify actual Isaac Sim startup, stage
loading, simulation updates, artifact writing, and non-empty frame capture.

## Controller Swap Point

The Isaac runner now depends on `RobotReplayController` rather than hard-coded
stage mutation. The current `StageReplayController` executes compiled commands
deterministically by moving USD prims and updating surface dirt attributes. A
real Isaac controller should implement the same contract:

- `execute(command, sim_steps=...)`
- `to_artifact(adapter_name=..., action_count=..., step_count=...)`

That keeps the validator handoff, physics artifact schema, and scoring bridge
stable while the execution backend advances from stage replay to Unitree robot
control.

The Unitree path now has its own controller mapper, a `SimulatedUnitreeBackend`
for dependency-free dry runs, and a `StageBackedUnitreeBackend` for Isaac
workstation runs that mutate USD prims. The remaining real implementation is
the articulated Isaac/Unitree backend behind `UnitreeIsaacBackend`. That
backend should:

- open or receive an Isaac Lab environment/scene;
- resolve target frames and object prims from the bundle manifest;
- plan or command robot base/end-effector motion;
- command gripper open/close and verify grasp attachment;
- release/drop objects and wait for rest;
- execute cleaning/contact trajectories;
- collect contacts, collisions, drops, damage, and camera frames;
- return a `BackendSnapshot` for `softlife.physics_replay.v1`.
