# Rendering And Demo Path

Soft Life has two rendering layers: the current lightweight browser replay and
the future Isaac Sim/Isaac Lab physics render.

## Current MVP Render

Use the browser visual demo for fast product iteration:

```bash
python3 -m softlife_subnet.visual_demo --seed 42
```

This renders the existing deterministic mock replay with the polished dashboard
UI. It is useful for pitch decks, product walkthroughs, and validating the
market flow:

```text
hidden room -> miner policy -> validator replay -> readiness score -> weights
```

This render is not physics. It is a clear frontend view of the subnet protocol.

## Isaac Lab Render

The current repo can export a validator-private bundle for an Isaac Lab
workstation:

```bash
python3 integrations/isaac_lab/scripts/export_replay_bundle.py --seed 42 --out /tmp/softlife_seed42_bundle.json --pretty
```

Rendering then happens inside Isaac Sim/Isaac Lab:

1. Load the replay bundle inside the Isaac Lab integration workspace.
2. Generate/load the USD room scene from `scene_manifest`.
3. Execute `compiled_commands` in the robot control loop.
4. Use headless mode for validator batch scoring.
5. Capture replay camera streams from fixed validator cameras for public demos.
6. Export MP4 clips or image sequences.
7. Store `softlife.physics_replay.v1` artifacts separately from public miner challenge data.

Recommended camera set:

- Wide room camera showing bed, floor, desk, hamper, and trash bin.
- Robot-follow camera for the active primitive.
- Overhead audit camera for object placement and score inspection.
- Optional close-up camera for grasp/place/clean events.

## First Isaac Visual Target

The first real physics render should be deliberately small:

1. Towel starts on the floor.
2. Cup/mug starts in the wrong zone.
3. Pillow starts off the bed.
4. Robot restores each object.
5. Validator score updates after replay.
6. The browser dashboard shows the same run summary and weights.

This proves the bridge before tackling large hotel-room randomness.

## Public Demo Versus Hidden Evaluation

Public demo mode may show:

- Rendered video.
- Redacted replay events.
- Public challenge state.
- Final score breakdown.
- Leaderboard and normalized weights.

Hidden validator mode must not show:

- Private seed.
- Full USD scene manifest.
- Hidden object poses.
- Hidden dirt maps.
- Raw scoring thresholds.
- Simulator or DDS handles.

## Suggested Completion Milestones

After the current alignment work, the next credible milestones are:

1. Implement the Isaac Lab task loop in `integrations/isaac_lab`.
2. Load one hotel-room USD scene with a Unitree-compatible robot.
3. Execute bundle `compiled_commands` through the Isaac controller.
4. Record one successful Isaac replay video.
5. Feed the final physics truth back into Soft Life `ReplayResult`.
6. Add a public playground mode with videos and a hidden eval mode without leaks.
7. Only then add ROS2/DDS execution for real robot demos.
