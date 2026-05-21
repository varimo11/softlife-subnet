# Soft Life Isaac Lab Integration

This directory is the Isaac-side integration workspace. It is intentionally
outside the lightweight `softlife_subnet` package so normal subnet tests and
demos do not import Isaac Sim, Isaac Lab, or Unitree dependencies.

## Current Status

Implemented here:

- Validator-private replay bundle export.
- Lightweight USDA scene export for Isaac/Omniverse inspection.
- Mock physics artifact export for offline schema testing.
- Physics artifact scoring back into Soft Life readiness.
- Deterministic scene manifest and compiled robot commands.
- Lazy Isaac Lab dependency detection.
- A task contract for the first hotel-room restore demo.

Still requiring an Isaac-capable machine:

- USD asset loading.
- Isaac Lab `ManagerBasedRLEnv` or direct simulation loop.
- Unitree robot articulation config.
- Camera rendering/video export.
- Physics truth extraction from the live simulator.

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
```

The first command emits the exact `softlife.physics_replay.v1` schema that the
real Isaac task must return. The second command ingests that artifact into the
validator scoring path.

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
