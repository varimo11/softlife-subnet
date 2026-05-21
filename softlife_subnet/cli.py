from __future__ import annotations

import argparse
import json
from typing import Any

from softlife_subnet.actions import ensure_trajectory
from softlife_subnet.leaderboard import Leaderboard
from softlife_subnet.miners import HeuristicMiner, NoOpMiner
from softlife_subnet.validators import Validator


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic subnet demo round.")
    parser.add_argument("--seed", type=int, default=42, help="Validator-private scenario seed.")
    parser.add_argument(
        "--show-public-state",
        action="store_true",
        help="Print the full miner-visible public state.",
    )
    args = parser.parse_args()

    validator = Validator()
    challenge = validator.issue_challenge(seed=args.seed)
    leaderboard = Leaderboard()
    miners = (HeuristicMiner(), NoOpMiner())

    _print_section(
        "1. VALIDATOR HIDDEN MESSY ROOM GENERATED",
        validator.private_challenge_summary(challenge.challenge_id),
    )

    public_payload: dict[str, Any] = challenge.to_wire()
    if not args.show_public_state:
        public_payload = {
            "challenge_id": challenge.challenge_id,
            "room_id": challenge.public_state.room_id,
            "task_name": challenge.public_state.task_name,
            "visible_objects": len(challenge.public_state.objects),
            "visible_surfaces": len(challenge.public_state.surfaces),
            "zones": list(challenge.public_state.zones),
        }
    _print_section("2. PUBLIC STATE SENT TO MINERS", public_payload)

    miner_outputs = []
    replay_outputs = []
    score_outputs = []
    for miner in miners:
        trajectory = ensure_trajectory(miner.solve(challenge.public_state))
        result = validator.evaluate(challenge.challenge_id, miner.miner_id, trajectory)
        leaderboard.update(result)

        miner_outputs.append(
            {
                "miner_id": miner.miner_id,
                "trajectory": trajectory.to_wire(),
                "trajectory_hash": result.trajectory_hash,
            }
        )
        replay_outputs.append(
            {
                "miner_id": miner.miner_id,
                **result.replay_summary.to_wire(),
            }
        )
        score_outputs.append(
            {
                "miner_id": miner.miner_id,
                "score": result.score.to_wire(),
                "invalid_actions": result.invalid_actions,
                "action_count": result.action_count,
            }
        )

    _print_section("3. TRAJECTORIES RETURNED BY MINERS", miner_outputs)
    _print_section("4. VALIDATOR REPLAY", replay_outputs)
    _print_section("5. SCORING BREAKDOWN", score_outputs)
    _print_section("6. LEADERBOARD", list(leaderboard.ranking_with_weights()))
    _print_section("7. NORMALIZED WEIGHTS", leaderboard.normalized_weights())


def _print_section(title: str, payload: object) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
