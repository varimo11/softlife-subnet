#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integrations.isaac_lab.softlife_isaac_lab.unitree_controller import (  # noqa: E402
    SimulatedUnitreeBackend,
    UnitreeIsaacControllerUnavailable,
    UnitreeIsaacReplayController,
)
from integrations.isaac_lab.softlife_isaac_lab.usd_export import load_bundle_payload  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Soft Life compiled commands through a Unitree/Isaac controller backend."
    )
    parser.add_argument("--bundle", required=True, help="Validator-private replay bundle JSON.")
    parser.add_argument("--out-artifact", required=True, help="Output physics artifact JSON path.")
    parser.add_argument("--sim-steps", type=int, default=12, help="Simulation steps per command.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Use the deterministic simulated Unitree backend. This validates the "
            "controller/artifact path without Isaac physics or Unitree runtime."
        ),
    )
    args = parser.parse_args()

    bundle_payload = load_bundle_payload(args.bundle)
    backend = SimulatedUnitreeBackend.from_bundle(bundle_payload) if args.dry_run else None
    try:
        controller = UnitreeIsaacReplayController.from_bundle(
            bundle_payload,
            backend=backend,
        )
    except UnitreeIsaacControllerUnavailable as exc:
        print(f"Unitree/Isaac backend unavailable: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    commands = tuple(bundle_payload.get("compiled_commands", ()))
    for command in commands:
        controller.execute(command, sim_steps=args.sim_steps)

    artifact = controller.to_artifact(
        adapter_name=(
            "unitree_isaac_replay_dry_run_v1"
            if args.dry_run
            else "unitree_isaac_replay_v1"
        ),
        action_count=len(commands),
        step_count=len(commands) * args.sim_steps,
    )
    output_path = Path(args.out_artifact)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact.to_private_wire(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote Unitree/Isaac physics artifact: {output_path}")
    if args.dry_run:
        print("Dry run: used simulated Unitree backend; no Isaac physics was executed.")
    print(f"Artifact hash: {artifact.artifact_hash}")


if __name__ == "__main__":
    main()
