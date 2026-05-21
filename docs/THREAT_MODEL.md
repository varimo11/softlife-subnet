# Soft Life Subnet Threat Model

This MVP evaluates embodied service intelligence for a messy hotel room restoration task. Validators own hidden environment truth, replay miner trajectories, and publish scoring outputs. Miners receive only public structured state and return a trajectory.

## Security Goals

- Miners cannot access private validator state, hidden seeds, hidden objects, exact hidden surface dirt, simulator handles, or scoring internals.
- Same hidden environment and same trajectory produce the same replay result.
- Scores reflect room readiness rather than quirks of the mock simulator.
- Validators can audit replay logs and trajectory hashes.
- The architecture can move from symbolic replay to Isaac Sim without changing the miner-facing challenge contract.

## Miners Overfitting Public States

Risk: miners memorize public room IDs, visible object layouts, or challenge templates instead of learning reusable embodied policies.

Controls:
- Hidden seeds and hidden scene state remain validator-owned.
- Public state is partial and quantized: some objects/surfaces are hidden, and visible dirt values are estimates.
- Production validators should use large private seed spaces, challenge salts, and withheld scene variants.
- Public playground challenges should be clearly separated from hidden mainnet evaluations.

Future controls:
- Rotate task catalogs and asset libraries.
- Use evaluator-only scene perturbations such as object pose jitter, lighting, friction, occlusion, and distractors.
- Track suspiciously brittle miner performance across public vs hidden challenge distributions.

## Invalid Action Spam

Risk: miners submit very long trajectories or repeated invalid actions hoping that one action eventually improves the score.

Current controls:
- Replay logs count invalid actions.
- Scoring applies an invalid action penalty.
- Efficiency score drops as trajectories exceed the expected action budget.

Future controls:
- Hard trajectory length caps per task.
- Rate limits and validation before replay.
- Early replay termination after too many invalid or unsafe actions.
- Separate reliability metrics that affect subnet weight.

## Unsafe Fast Policies

Risk: a miner optimizes for speed and ignores collisions, dropped objects, robot limits, or unsafe motions.

Current MVP:
- The mock adapter is symbolic and does not model collision, acceleration, force, breakage, or human safety.

Required Isaac Sim controls:
- Replay robot motion against joint limits, velocity limits, collision geometry, and object damage thresholds.
- Penalize collisions, dropped fragile items, blocked paths, and excessive contact forces.
- Require trajectory primitives to compile into feasible robot actions before scoring readiness.
- Keep real-world robot demos behind additional safety checks and operator supervision.

## Exploiting Scoring Loopholes

Risk: miners discover actions that maximize readiness without producing genuinely guest-ready rooms.

Controls:
- Scoring should be based on final validator-observed state, not miner claims.
- Object placement, cleanliness, damage, collisions, invalid actions, and efficiency should be measured separately.
- Score components should be capped and auditable.

Future controls:
- Add human-readable score reports and randomized hidden checks.
- Use multiple validators or repeated hidden scenes to reduce single-scorer quirks.
- Regression-test known exploit trajectories.

## Leaking Hidden Seeds

Risk: private seeds leak through challenge IDs, logs, public states, stack traces, or debugging output.

Current controls:
- `Challenge` contains only a challenge ID and `PublicRoomState`.
- `PublicRoomState` excludes `private_seed`, hidden objects, hidden surfaces, and exact hidden dirt values.
- `Validator.private_challenge_summary()` is validator-only debug output and is not passed to miners.

Hardening needed before mainnet:
- Do not derive public challenge IDs directly from small seed spaces.
- Use validator-private salts or opaque IDs.
- Keep debug summaries disabled outside local demos.
- Scrub logs for seeds, simulator scene paths, and hidden metadata.

## Validator Manipulation

Risk: a validator manipulates hidden scenes, replay results, or score-to-weight outputs.

Controls:
- Replay logs and trajectory hashes are deterministic and auditable.
- Scoring output is separated from replay output.
- The same adapter contract can be run by multiple validators.

Future controls:
- Publish commitments to hidden challenge sets before evaluation windows.
- Cross-check miner trajectories across independent validators.
- Use challenge/replay/score hashes for audit trails.
- Add validator reputation and slashing rules at the subnet layer.

## Replay Nondeterminism

Risk: the same seed and trajectory produce different scores due to floating-point variance, simulator nondeterminism, dependency drift, or hidden randomness.

Current controls:
- The mock adapter uses deterministic symbolic state transitions.
- Replay logs include ordered events and a replay hash.
- Tests assert deterministic replay for the same seed and trajectory.

Isaac Sim controls required:
- Pin simulator, USD asset, physics, controller, and scoring versions.
- Record random seeds and scene generation manifests privately.
- Disable uncontrolled randomness during replay.
- Store deterministic replay artifacts for validator audits.
- Treat nondeterministic replays as invalid evaluations until reproduced.
