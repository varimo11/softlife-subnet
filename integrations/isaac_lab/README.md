# Soft Life Isaac Lab Integration

This directory is the Isaac-side integration workspace. It is intentionally
outside the lightweight `softlife_subnet` package so normal subnet tests and
demos do not import Isaac Sim, Isaac Lab, or Unitree dependencies.

## Current Status

Implemented here:

- Validator-private replay bundle export.
- Lightweight USDA scene export for Isaac/Omniverse inspection.
- Stage-level Isaac Sim replay runner with lazy `isaacsim` / `omni.isaac.kit`
  imports.
- Stage truth extraction from USD prim transforms and `softlife:dirt`
  attributes into `softlife.physics_replay.v1`.
- `RobotReplayController` boundary with a `StageReplayController` implementation,
  ready to be replaced by a Unitree/Isaac controller.
- `UnitreeIsaacReplayController` command mapper plus `UnitreeIsaacBackend`
  protocol for real Isaac Lab / Unitree execution.
- `SimulatedUnitreeBackend` for dependency-free dry runs of the Unitree command
  path and artifact scoring contract.
- `StageBackedUnitreeBackend` for running the Unitree controller against an
  Isaac USD stage before articulated Unitree robot control is connected.
- Mock physics artifact export for offline schema testing.
- Physics artifact scoring back into Soft Life readiness.
- Deterministic scene manifest and compiled robot commands.
- Lazy Isaac Lab dependency detection.
- Canonical workflow validation across bundle export, USD export, stage replay,
  Unitree dry run, artifact hashes, and scoring.
- A task contract for the first hotel-room restore demo.

Still requiring an Isaac-capable machine:

- USD asset loading.
- Unitree robot articulation config.
- Camera rendering/video export.
- Isaac Lab `ManagerBasedRLEnv` task and robot controller physics.
- Full contact-rich physics truth extraction from the live simulator.

## Export A Replay Bundle

From the repo root:

```bash
python3 integrations/isaac_lab/scripts/export_replay_bundle.py --seed 42 --out /tmp/softlife_seed42_bundle.json --pretty
```

The bundle is validator-private. It contains hidden room truth, a scene
manifest, the miner trajectory, and compiled robot commands. Add
`--include-private-seed` only inside a trusted validator or local Isaac dev
environment.

## Export A Lightweight USDA Scene

```bash
python3 integrations/isaac_lab/scripts/export_scene_usd.py --bundle /tmp/softlife_seed42_bundle.json --out /tmp/softlife_seed42_scene.usda
```

This creates a simple USD ASCII scene with zones, target frames, objects,
surfaces, and cameras. It is a bootstrap scene for Isaac/Omniverse inspection,
not the final high-fidelity hotel room.

## Test The Artifact Round Trip Without Isaac

```bash
python3 integrations/isaac_lab/scripts/export_mock_physics_artifact.py --seed 42 --out /tmp/softlife_seed42_artifact.json --pretty
python3 integrations/isaac_lab/scripts/score_physics_artifact.py --bundle /tmp/softlife_seed42_bundle.json --artifact /tmp/softlife_seed42_artifact.json --seed 42 --pretty
python3 integrations/isaac_lab/scripts/run_unitree_isaac_replay.py --bundle /tmp/softlife_seed42_bundle.json --out-artifact /tmp/softlife_seed42_unitree_artifact.json --dry-run
python3 integrations/isaac_lab/scripts/validate_isaac_workflow.py --out-dir /tmp/softlife_isaac_validation --pretty
```

The first command emits the exact `softlife.physics_replay.v1` schema that the
real Isaac task must return. The second command ingests that artifact into the
validator scoring path. The Unitree dry run executes compiled commands through
`UnitreeIsaacReplayController` and `SimulatedUnitreeBackend`; it validates the
controller/artifact boundary, but it does not run Isaac physics.

`validate_isaac_workflow.py` is the local acceptance gate. It writes replay
bundles, USDA scenes, stage artifacts, Unitree dry-run artifacts, and a workflow
report for the canonical seeds. On an Isaac workstation, it can also run the
stage replay and Unitree USD stage-backed backend in the same report.

## Run The Stage-Level Isaac Sim Replay

On an Isaac Sim workstation, run this with Isaac Sim's Python environment:

```bash
./python.sh /path/to/softlife-subnet-demo/integrations/isaac_lab/scripts/run_isaac_stage_replay.py \
  --bundle /tmp/softlife_seed42_bundle.json \
  --scene /tmp/softlife_seed42_scene.usda \
  --out-artifact /tmp/softlife_seed42_isaac_artifact.json \
  --render-dir /tmp/softlife_frames
```

For a local dependency-free check:

```bash
python3 integrations/isaac_lab/scripts/run_isaac_stage_replay.py \
  --bundle /tmp/softlife_seed42_bundle.json \
  --out-artifact /tmp/softlife_seed42_stage_artifact.json \
  --dry-run
```

This runner loads the USD scene, applies compiled command effects to stage
prims, advances Isaac Sim, reads final USD prim transforms and surface dirt
attributes back from the stage, optionally captures viewport frames, and writes
the same physics artifact schema used by the validator. It is the first runnable
Isaac bridge; the next step is replacing stage-level object motion with a
Unitree robot controller and real contact-rich physics.

For a multi-seed workstation gate:

```bash
./python.sh /path/to/softlife-subnet-demo/integrations/isaac_lab/scripts/validate_isaac_workflow.py \
  --out-dir /tmp/softlife_isaac_validation \
  --real-stage \
  --unitree-stage-backend \
  --capture-frames \
  --pretty
```

When `--capture-frames` is set, the gate fails if Isaac does not return at
least one existing non-empty frame file for each requested Isaac-backed replay.

The replacement point is `RobotReplayController`. A future
`UnitreeIsaacReplayController` now implements the same `execute(...)` and
`to_artifact(...)` methods. It delegates actual robot work to a
`UnitreeIsaacBackend`, which is the piece that must connect Isaac Lab scene/env
handles, Unitree articulation controllers, grippers, contacts, camera capture,
and collision telemetry.

The intended runtime command is:

```bash
./python.sh /path/to/softlife-subnet-demo/integrations/isaac_lab/scripts/run_unitree_isaac_replay.py \
  --bundle /tmp/softlife_seed42_bundle.json \
  --out-artifact /tmp/softlife_seed42_unitree_artifact.json \
  --stage-backend \
  --render-dir /tmp/softlife_unitree_frames
```

This uses `StageBackedUnitreeBackend`: the Unitree controller executes through
the backend interface, mutates USD object/surface prims, and snapshots stage
truth. It does not yet drive Unitree articulation, grippers, contacts, or robot
dynamics. Plain non-dry-run execution still fails clearly until an articulated
backend satisfying `UnitreeIsaacBackend` is configured.

For a local dependency-free check of the Unitree command path:

```bash
python3 integrations/isaac_lab/scripts/run_unitree_isaac_replay.py \
  --bundle /tmp/softlife_seed42_bundle.json \
  --out-artifact /tmp/softlife_seed42_unitree_artifact.json \
  --dry-run
```

## First Isaac Demo Target

The first render should be a fixed validation scene:

1. Generate seed `42`.
2. Load room zones under `/World/SoftLifeRooms/{room_id}`.
3. Spawn objects under `/Objects/{object_id}`.
4. Spawn target frames under `/Zones/{zone}/target_frame`.
5. Feed `compiled_commands` to the robot control loop.
6. Render wide, robot-follow, and overhead validator cameras.
7. Extract final physics truth into `softlife.physics_replay.v1`.
8. Return that artifact to the Soft Life validator/scorer.

## Isaac Execution Shape

```text
replay bundle JSON
  -> HotelRoomSceneCfg / USD generation
  -> SoftLife command provider
  -> Isaac Lab env/controller loop
  -> physics truth extractor
  -> PhysicsReplayArtifact
  -> ReplayResult
  -> RoomReadinessScorer
```

The miner never receives the bundle, USD manifest, private seed, simulator
handles, or raw scoring internals.
