#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integrations.isaac_lab.softlife_isaac_lab.usd_export import load_bundle_payload  # noqa: E402
from softlife_subnet.actions import Trajectory  # noqa: E402
from softlife_subnet.artifact_ingest import replay_result_from_physics_artifact  # noqa: E402
from softlife_subnet.physics_artifacts import PhysicsReplayArtifact  # noqa: E402
from softlife_subnet.room_generator import RoomGenerator  # noqa: E402
from softlife_subnet.scoring import RoomReadinessScorer  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score a Soft Life physics replay artifact from Isaac Lab."
    )
    parser.add_argument("--bundle", required=True, help="Validator replay bundle JSON path.")
    parser.add_argument("--artifact", required=True, help="Physics artifact JSON path.")
    parser.add_argument(
        "--seed",
        type=int,
        help="Validator seed used to reconstruct hidden state. Required unless bundle includes private seed.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print score JSON.")
    args = parser.parse_args()

    bundle_payload = load_bundle_payload(args.bundle)
    seed = _seed_from_args_or_bundle(args.seed, bundle_payload)
    artifact_payload = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    artifact = PhysicsReplayArtifact.from_wire(artifact_payload)

    environment = RoomGenerator().generate(seed)
    trajectory = Trajectory.from_wire(bundle_payload["trajectory"])
    replay_result = replay_result_from_physics_artifact(
        initial_state=environment,
        trajectory=trajectory,
        artifact=artifact,
    )
    score = RoomReadinessScorer().score(replay_result)
    payload = {
        "room_id": environment.room_id,
        "artifact_hash": artifact.artifact_hash,
        "adapter_name": replay_result.adapter_name,
        "score": score.to_wire(),
        "replay_log": replay_result.to_replay_log(),
        "physics_summary": artifact.to_public_summary(),
    }
    print(
        json.dumps(
            payload,
            indent=2 if args.pretty else None,
            sort_keys=True,
            separators=None if args.pretty else (",", ":"),
        )
    )


def _seed_from_args_or_bundle(seed: int | None, bundle_payload: object) -> int:
    if seed is not None:
        return seed
    if not isinstance(bundle_payload, dict):
        raise TypeError("bundle payload must be an object")
    private_state = bundle_payload.get("validator_private_state", {})
    if isinstance(private_state, dict) and "private_seed" in private_state:
        return int(private_state["private_seed"])
    raise ValueError("--seed is required when the bundle does not include private_seed")


if __name__ == "__main__":
    main()
