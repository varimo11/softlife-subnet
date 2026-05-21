#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from softlife_subnet.actions import Trajectory  # noqa: E402
from softlife_subnet.isaac_handoff import build_isaac_replay_bundle  # noqa: E402
from softlife_subnet.robotics import build_symbolic_physics_artifact  # noqa: E402
from softlife_subnet.simulation import MockSimulationAdapter  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a mock physics artifact with the same schema Isaac Lab must return."
    )
    parser.add_argument("--seed", type=int, default=42, help="Validator scenario seed.")
    parser.add_argument(
        "--miner",
        default="heuristic",
        choices=("heuristic", "noop"),
        help="Miner policy used to generate the trajectory.",
    )
    parser.add_argument("--out", required=True, help="Output artifact JSON path.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args()

    bundle = build_isaac_replay_bundle(seed=args.seed, miner=args.miner)
    trajectory = Trajectory.from_wire(bundle.trajectory)
    replay = MockSimulationAdapter(adapter_name="mock_physics_artifact_v1").replay(
        bundle.environment_state,
        trajectory,
    )
    artifact = build_symbolic_physics_artifact(
        adapter_name=replay.adapter_name,
        initial_state=replay.initial_state,
        final_state=replay.final_state,
        scene_manifest=bundle.scene_manifest,
        step_count=replay.action_count,
        action_count=replay.action_count,
        invalid_actions=replay.invalid_actions,
        command_log=tuple(bundle.compiled_commands),
    )
    encoded = json.dumps(
        artifact.to_private_wire(),
        indent=2 if args.pretty else None,
        sort_keys=True,
        separators=None if args.pretty else (",", ":"),
    )
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(encoded + "\n", encoding="utf-8")
    print(f"Wrote mock physics artifact: {output_path}")


if __name__ == "__main__":
    main()
