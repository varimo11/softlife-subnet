# Isaac Task Mapping

This document defines the first concrete bridge from Soft Life symbolic state to
an Isaac Lab hotel-room task. It is a design contract, not a dependency on
Isaac Lab.

## Scene Root

Each hidden validator room maps to a deterministic USD root:

```text
/World/SoftLifeRooms/{room_id}
```

The lightweight code exposes this through `HotelRoomSceneManifest` in
`softlife_subnet.robotics.scene_mapping`.

## Zones

Symbolic zones map to named target frames under the scene root:

| Soft Life zone | Isaac/USD frame |
| --- | --- |
| `entry` | `/World/SoftLifeRooms/{room_id}/Zones/entry/target_frame` |
| `floor` | `/World/SoftLifeRooms/{room_id}/Zones/floor/target_frame` |
| `bed` | `/World/SoftLifeRooms/{room_id}/Zones/bed/target_frame` |
| `nightstand` | `/World/SoftLifeRooms/{room_id}/Zones/nightstand/target_frame` |
| `desk` | `/World/SoftLifeRooms/{room_id}/Zones/desk/target_frame` |
| `bathroom_counter` | `/World/SoftLifeRooms/{room_id}/Zones/bathroom_counter/target_frame` |
| `hamper` | `/World/SoftLifeRooms/{room_id}/Zones/hamper/target_frame` |
| `closet` | `/World/SoftLifeRooms/{room_id}/Zones/closet/target_frame` |
| `trash_bin` | `/World/SoftLifeRooms/{room_id}/Zones/trash_bin/target_frame` |

These frames are navigation or end-effector goals. They are not scoring by
themselves; scoring reads physics truth after replay.

## Objects

Each validator-private object receives a stable prim path:

```text
/World/SoftLifeRooms/{room_id}/Objects/{object_id}
```

Initial object pose, visibility, mass, friction, fragility, occlusion, and
target-zone metadata stay in the validator manifest. Miners receive only the
public object fields.

## Surfaces

Each cleanable surface receives a stable prim path:

```text
/World/SoftLifeRooms/{room_id}/Surfaces/{zone}
```

The Isaac task should attach hidden dirt maps or cleanliness metadata to these
surface prims. Public state may expose only quantized estimates for visible
surfaces.

## Action Compilation

Soft Life miner actions compile into robot-oriented commands:

| Miner action | Compiled command | Isaac/ROS2 meaning |
| --- | --- | --- |
| `move_to_zone(zone)` | `navigate_to_frame` | Navigate base/end-effector to zone target frame. |
| `move_to_object(object_id)` | `approach_object` | Plan to a pre-grasp pose for the object prim. |
| `pick(object_id)` | `grasp_object` | Close gripper or attach object if grasp succeeds. |
| `place(object_id, zone)` | `release_object` | Release object inside the target zone bounds. |
| `clean_surface(zone)` | `wipe_surface` | Execute a tool/contact path over the surface prim. |
| `dispose(object_id)` | `drop_in_receptacle` | Release disposable object into `trash_bin`. |

The current code implements this bridge with:

- `CompiledRobotCommand`
- `SoftLifeTrajectoryProvider`
- `HotelRoomSceneManifest`
- `IsaacSimSimulationAdapter` stub

## Validator Replay Loop

The future Isaac adapter should follow this sequence:

1. Build `HotelRoomSceneManifest` from hidden `EnvironmentState`.
2. Generate or load the matching USD scene.
3. Compile the miner `Trajectory` with `SoftLifeTrajectoryProvider`.
4. Feed compiled commands to the Isaac Lab control loop.
5. Step physics deterministically.
6. Extract final object poses, zone membership, collisions, damage, drops, and
   cleanliness.
7. Return a `ReplayResult` to the existing validator/scorer pipeline.

The miner interface does not change when mock replay is replaced by Isaac Lab.
