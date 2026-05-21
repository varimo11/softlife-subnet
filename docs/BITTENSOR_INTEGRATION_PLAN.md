# Bittensor Integration Plan

This project is a subnet-style evaluation market for embodied service intelligence. The current code is not a Bittensor subnet implementation yet. It provides the local contracts that can later map into miner/validator processes.

## Miner Interface

Current local miner interface:

- Input: `PublicRoomState`
- Output: `Trajectory`

Future Bittensor miner behavior:

- Receive a synapse containing a public challenge.
- Produce a JSON-serializable trajectory.
- Never connect to validator simulators.
- Never receive hidden seeds, hidden scenes, or exact hidden scoring state.
- Sign/respond through the normal Bittensor request path.

Miner implementations can be heuristic planners, learned policies, VLM planners, ROS2 planners, or remote robot policy servers, as long as they return the trajectory contract.

## Validator Interface

Current local validator behavior:

- Generate hidden `EnvironmentState`.
- Send public `Challenge`.
- Replay trajectory using `SimulationAdapter`.
- Score room readiness.
- Update leaderboard and normalized weights.

Future Bittensor validator behavior:

- Sample miners.
- Issue hidden evaluation challenges.
- Collect trajectories.
- Replay in validator-owned mock physics, Isaac Sim, or approved replay backend.
- Score outputs.
- Convert scores into subnet weights.
- Submit weights on chain.

Validators must keep hidden evaluation state private.

## Synapse Design

Proposed synapse fields:

- `challenge_id`: opaque public ID.
- `task_name`: `restore_hotel_room`.
- `public_state`: serialized `PublicRoomState`.
- `trajectory`: serialized `Trajectory`, returned by miner.
- `trajectory_hash`: validator-computed canonical hash.
- Optional playground fields: public replay log, public rendered preview, public score.

Fields that must not be in the miner request:

- private seed.
- hidden object list.
- exact hidden dirt maps.
- simulator scene path.
- scoring implementation internals.
- validator replay handles.

## Hidden Evaluations

Hidden evaluation flow:

1. Validator creates private environment from a hidden seed.
2. Validator emits only public challenge state.
3. Miner returns trajectory.
4. Validator replays trajectory privately.
5. Validator calculates score.
6. Validator stores replay/score audit artifacts.
7. Validator updates miner weights.

Public playground flow can expose more logs and visuals, but it must not be confused with hidden mainnet evaluation.

## Score-To-Weight Flow

The current `Leaderboard.normalized_weights()` method is a local stand-in:

1. Track best/latest readiness per miner.
2. Clamp negative values to zero.
3. Normalize positive scores so weights sum to one.
4. Expose normalized weights in CLI output.

Future subnet validators would convert rolling hidden-eval scores into Bittensor weights. The exact production formula should account for recency, repeated tasks, score confidence, invalid action rate, safety penalties, and validator consensus.

## Yuma Weights Conceptual Mapping

Conceptually:

- Miners compete by producing trajectories for embodied service tasks.
- Validators score hidden replays.
- Higher reliable scores produce higher validator-assigned weights.
- The chain aggregation mechanism then combines validator opinions into network incentives.

This repository only models the local score-to-weight concept. It does not implement Yuma consensus or chain submission.

## Public Playground vs Hidden Mainnet Evals

Public playground:

- Useful for demos, debugging, and onboarding.
- Can show public state, trajectories, replay logs, and scores.
- May use fixed seeds and visual replays.
- Should not be used as the only incentive signal.

Hidden mainnet evaluation:

- Uses withheld seeds and scenes.
- Redacts replay internals from miners.
- Uses private validator simulation.
- Feeds score-to-weight updates.
- Requires audit and anti-leak controls.

## Not Implemented Yet

- Bittensor synapse class.
- Miner Axon server.
- Validator process loop.
- Wallet, subtensor, metagraph, and weight submission.
- Validator consensus, audits, or slashing.
- Isaac Sim replay backend.
- ROS2 bridge.
- Real robot execution.

The current codebase is the local deterministic contract layer these pieces should integrate with.
