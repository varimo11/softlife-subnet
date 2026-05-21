# Unitree Isaac Lab Reference Notes

Reference inspected:

- `https://github.com/unitreerobotics/unitree_sim_isaaclab`
- License: Apache-2.0, with dependencies on Isaac Lab, Isaac Sim, pyzmq, and Unitree SDK2 Python.

This document captures architecture lessons for Soft Life. It is not vendored code.

## What The Unitree Repo Is

`unitree_sim_isaaclab` is a Unitree robotics simulator built on Isaac Lab. It targets Unitree G1 and H1-2 humanoids with gripper, Dex3, and Inspire hand variants. It provides:

- Isaac Lab task registration and scene construction.
- DDS communication compatible with Unitree real robot control topics.
- Action providers for DDS and replay.
- A low-level controller loop that steps an Isaac Lab environment.
- Task-specific reward and termination logic.
- Camera/data replay and data generation tools.
- Docker and Isaac Sim environment setup guidance.

The important idea for Soft Life is not any specific pick-place task; it is the separation between task scene, action source, simulator control loop, robot/DDS bridge, reward/termination logic, and replay/data tooling.

## Relevant Structure

High-signal directories:

- `action_provider/`: abstracts where actions come from. The repo has providers for DDS and replay. This maps directly to Soft Life miner trajectories and future policy/DDS action sources.
- `dds/`: Unitree communication objects and manager. It registers robot, hand, whole-body command, reset pose, sim state, and rewards publishers/subscribers.
- `layeredcontrol/`: the control loop. `RobotController` pulls actions from an `ActionProvider`, steps the Isaac Lab environment, and enforces step frequency.
- `robots/` and `tasks/common_config/robot_configs.py`: robot articulation variants and joint templates for G1/H1-2.
- `tasks/common_scene/`: Isaac Lab `InteractiveSceneCfg` scene definitions with USD assets, rigid objects, lights, cameras, and object placements.
- `tasks/common_rewards/`: task reward functions based on final object pose/height/region checks.
- `tasks/common_termination/`: reset/termination checks when objects leave valid ranges.
- `tasks/g1_tasks/` and `tasks/h1-2_tasks/`: registered task variants.
- `tools/`: data replay, USD editing/conversion, reward inspection, rerun visualization, camera augmentation, episode writing.

## Concepts To Absorb Into Soft Life

### 1. Keep Action Source Separate From Simulation

Unitree has `ActionProvider` as an interface and specific providers for DDS/replay. Soft Life already has `Trajectory` plus `SimulationAdapter`. The next bridge should add an adapter-side action-provider layer:

- `SoftLifeTrajectoryProvider`: converts symbolic miner primitives into low-level replay commands.
- `DDSActionProvider`: optional future source for real Unitree/ROS2/DDS commands.
- `ReplayFileProvider`: replays recorded trajectories for validator audits.

This prevents miners from depending on Isaac Sim or DDS directly.

### 2. Adapter Owns The Isaac Lab Control Loop

Unitree’s `RobotController` owns stepping frequency and environment stepping. Soft Life’s future `IsaacSimSimulationAdapter` should do the same:

1. Load hidden `EnvironmentState`.
2. Build Isaac Lab scene/task config.
3. Compile miner `Trajectory` into an internal action source.
4. Step Isaac Lab deterministically.
5. Collect final object poses, collisions, damage, cleanliness, and replay logs.
6. Return `ReplayResult`.

The validator should call `adapter.replay(...)`, not manage Isaac internals.

### 3. Scene Configs Should Be Reusable

Unitree keeps common scene pieces in `tasks/common_scene`. For Soft Life:

- `HotelRoomSceneCfg`: bed, nightstand, desk, bathroom counter, closet, hamper, trash bin, floor.
- `RoomObjectCfg`: towel, cup, pillow, trash, toiletry bottle.
- `RoomSurfaceCfg`: cleanable surfaces and dirt metadata.
- `HotelRoomCameraCfg`: validator/debug cameras.

Then create task variants without rewriting all scene setup.

### 4. Rewards Should Read Physics Truth

Unitree rewards inspect actual Isaac object state, such as object position and height. Soft Life scoring should similarly read validator-owned physics truth:

- Object final pose inside target zone.
- Object resting/stable state.
- Surface cleanliness state.
- Trash in bin.
- Collision/damage events.
- Invalid planning/execution events.

Miner claims should never affect scoring directly.

### 5. DDS/Real Robot Bridge Should Be Optional

Unitree starts DDS publishers/subscribers for robot, hand, reset pose, sim state, and rewards. Soft Life should not require DDS for hidden validation, but should design a bridge:

- `Trajectory` -> Isaac/ROS2/DDS primitive goals.
- Replay log -> `ReplayResult`.
- Sim state/reward topics -> validator-only telemetry.
- Real robot execution remains supervised and separate from hidden scoring until safety gates exist.

### 6. Separate Public Playground From Hidden Eval

Unitree exposes sim state/reward/data streams for control and data generation. In Soft Life:

- Playground mode can show rendered replay, public logs, and score.
- Hidden validator mode must redact scene manifests, seeds, exact hidden poses, and detailed scoring internals.

## Soft Life Mapping

Current Soft Life contract:

- `PublicRoomState`: miner-visible state.
- `EnvironmentState`: hidden validator truth.
- `Trajectory`: miner output.
- `SimulationAdapter`: replay boundary.
- `ReplayResult`: deterministic replay output.

Future Unitree/Isaac-style implementation:

```text
Validator
  -> IsaacSimSimulationAdapter
      -> HotelRoomSceneCfg
      -> SoftLifeTrajectoryProvider
      -> RobotController / Isaac Lab env loop
      -> PhysicsTruthExtractor
      -> ReplayResult
  -> RoomReadinessScorer
  -> leaderboard / weights
```

## Alignment Added To Soft Life

The lightweight codebase now includes the first adapter-side pieces inspired by
Unitree's structure:

- `softlife_subnet.robotics.ActionProvider`
- `softlife_subnet.robotics.SoftLifeTrajectoryProvider`
- `softlife_subnet.robotics.CompiledRobotCommand`
- `softlife_subnet.robotics.HotelRoomSceneManifest`
- `softlife_subnet.physics_artifacts.PhysicsReplayArtifact`
- `softlife_subnet.isaac_handoff.IsaacReplayBundle`
- `softlife_subnet.isaac_adapter.IsaacSimSimulationAdapter`
- `integrations/isaac_lab/`
- `docs/ISAAC_TASK_MAPPING.md`
- `docs/RENDERING_AND_DEMO_PATH.md`

These are intentionally dependency-free. They prepare the repo for Isaac Lab
without breaking the current mock physics demo.

## Suggested Next Milestones

1. Implement the Isaac Lab hotel-room task loop in `integrations/isaac_lab`.
2. Render one successful Isaac replay from a fixed validator camera.
3. Feed Isaac physics truth back into the existing `ReplayResult`.
4. Only after that, add optional Unitree/DDS bridge support.

## Important Constraints

- Do not import Isaac Lab, Unitree SDK, or DDS into the lightweight mock path.
- Do not let miners access DDS, simulator handles, hidden scene configs, or reward internals.
- Do not conflate public visual demos with hidden validator evaluation.
- Treat real robot execution as a separate safety-critical mode.
