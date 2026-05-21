# Softlife Subnet Demo

This repository is an MVP scaffold for a decentralized robotics intelligence market inspired by Bittensor.

The first task is restoring a messy hotel room to guest-ready condition. A validator owns the hidden environment state and replay adapter. Miners receive only a public structured room state and return a JSON-serializable action trajectory. The validator replays that trajectory deterministically and scores room readiness.

This is not a hotel management app. It is a lightweight evaluation market for embodied service intelligence that can later map into Bittensor, Isaac Sim, ROS2, and real robot hardware.

## Architecture

- `softlife_subnet.room_generator`: deterministic hidden scenario generation from a private seed.
- `softlife_subnet.state`: private `EnvironmentState` and miner-facing `PublicRoomState` contracts.
- `softlife_subnet.actions`: wire-friendly `Action` and `Trajectory` primitives.
- `softlife_subnet.simulation`: `SimulationAdapter`, `MockSimulationAdapter`, and `ReplayResult`.
- `softlife_subnet.robotics`: Unitree/Isaac-style action provider, command compiler, and scene manifest bridge.
- `softlife_subnet.isaac_adapter`: optional Isaac Lab adapter stub kept outside the mock backend.
- `softlife_subnet.physics_artifacts`: validator-private physics truth schema for Isaac/hardware replay.
- `softlife_subnet.isaac_handoff`: deterministic Isaac replay bundle exporter.
- `softlife_subnet.scoring`: room readiness scoring.
- `softlife_subnet.validators`: validator boundary and private challenge storage.
- `softlife_subnet.miners`: miner interface and baseline heuristic miner.
- `softlife_subnet.leaderboard`: score aggregation and normalized weights.
- `docs/`: integration plans and threat model.

## Run The Demo

```bash
python3 -m softlife_subnet.cli --seed 42 --show-public-state
```

The seed is supplied to the validator only. Miners receive a `PublicRoomState` with visible objects, visible surface dirt estimates, allowed zones, and no private simulation state. The CLI shows the local validator-only hidden summary, public miner state, returned trajectories, replay logs, score breakdown, leaderboard, and normalized weights.

## Run The Visual Demo

```bash
python3 -m softlife_subnet.visual_demo --seed 42
```

This starts a lightweight local web demo and opens it in a browser. The page renders room zones, object tokens for towel, cup, pillows, trash, and toiletry bottle, the miner trajectory, validator replay events, live readiness scoring, and normalized leaderboard weights.

For a server-only run:

```bash
python3 -m softlife_subnet.visual_demo --seed 42 --no-open
```

## Run Tests

```bash
python3 -m unittest discover -s tests
```

The tests cover deterministic room generation, deterministic replay logs, hidden-state boundaries, invalid action penalties, scoring caps, adapter conformance, trajectory serialization, and leaderboard weights.

For sandboxed macOS Python bytecode compilation:

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/softlife_pycache python3 -m compileall -q softlife_subnet tests
```

## Export An Isaac Replay Bundle

```bash
python3 integrations/isaac_lab/scripts/export_replay_bundle.py --seed 42 --out /tmp/softlife_seed42_bundle.json --pretty
python3 integrations/isaac_lab/scripts/export_scene_usd.py --bundle /tmp/softlife_seed42_bundle.json --out /tmp/softlife_seed42_scene.usda
```

This produces a validator-private JSON bundle for an Isaac Lab workstation:
hidden room truth, scene manifest, miner trajectory, compiled robot commands,
and the expected `softlife.physics_replay.v1` artifact schema. The second
command exports a bootstrap USDA scene for Isaac/Omniverse inspection.

Offline artifact round-trip check:

```bash
python3 integrations/isaac_lab/scripts/export_mock_physics_artifact.py --seed 42 --out /tmp/softlife_seed42_artifact.json --pretty
python3 integrations/isaac_lab/scripts/score_physics_artifact.py --bundle /tmp/softlife_seed42_bundle.json --artifact /tmp/softlife_seed42_artifact.json --seed 42 --pretty
python3 integrations/isaac_lab/scripts/run_isaac_stage_replay.py --bundle /tmp/softlife_seed42_bundle.json --out-artifact /tmp/softlife_seed42_stage_artifact.json --dry-run
```

On an Isaac Sim workstation, run `run_isaac_stage_replay.py` with Isaac Sim's
Python instead of `--dry-run` to load the scene, apply compiled commands on the
USD stage, optionally capture viewport frames, and write the validator artifact.

The Unitree controller path is wired as a backend contract:

```bash
./python.sh integrations/isaac_lab/scripts/run_unitree_isaac_replay.py --bundle /tmp/softlife_seed42_bundle.json --out-artifact /tmp/softlife_seed42_unitree_artifact.json
```

That command is ready for an implementation of `UnitreeIsaacBackend`, which is
where Isaac Lab robot/env handles and Unitree gripper/control APIs plug in.

## Docs

- `docs/THREAT_MODEL.md`: overfitting, invalid action spam, unsafe policies, scoring loopholes, seed leaks, validator manipulation, and replay nondeterminism.
- `docs/ISAAC_SIM_INTEGRATION_PLAN.md`: mapping symbolic room state into USD scenes, deterministic hidden scene generation, replay logs, scoring, ROS2 bridge, and first visual demo.
- `docs/ISAAC_TASK_MAPPING.md`: concrete zone/object/surface mappings into future USD prim paths and compiled robot commands.
- `docs/UNITREE_ISAACLAB_REFERENCE.md`: notes absorbed from Unitree's Isaac Lab simulator architecture.
- `docs/RENDERING_AND_DEMO_PATH.md`: how to render the current browser demo and the future Isaac Lab replay.
- `docs/BITTENSOR_INTEGRATION_PLAN.md`: miner/validator interfaces, synapse shape, hidden evaluations, score-to-weight flow, Yuma mapping, and what is not implemented yet.

## Extension Points

- Implement `IsaacSimSimulationAdapter` behind the existing `SimulationAdapter` protocol.
- Feed `SoftLifeTrajectoryProvider` commands into an Isaac Lab control loop.
- Convert Isaac final physics truth into `PhysicsReplayArtifact` and then `ReplayResult`.
- Replace `Validator` storage/evaluation with a Bittensor validator process.
- Replace `Miner.solve()` implementations with policy inference, planning, ROS2 action servers, or remote miner RPC.
- Add richer physics facts to `EnvironmentState` while preserving a reduced `PublicRoomState` for miners.
