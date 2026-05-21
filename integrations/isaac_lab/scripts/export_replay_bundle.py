#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from softlife_subnet.isaac_handoff import build_isaac_replay_bundle  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a validator-private Soft Life replay bundle for Isaac Lab."
    )
    parser.add_argument("--seed", type=int, default=42, help="Validator scenario seed.")
    parser.add_argument(
        "--miner",
        default="heuristic",
        choices=("heuristic", "noop"),
        help="Miner policy used to generate the trajectory.",
    )
    parser.add_argument("--out", help="Output JSON path. Prints to stdout when omitted.")
    parser.add_argument(
        "--include-private-seed",
        action="store_true",
        help="Include private seed in the validator-private bundle.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args()

    bundle = build_isaac_replay_bundle(seed=args.seed, miner=args.miner)
    payload = bundle.to_wire(include_private_seed=args.include_private_seed)
    encoded = json.dumps(
        payload,
        indent=2 if args.pretty else None,
        sort_keys=True,
        separators=None if args.pretty else (",", ":"),
    )

    if args.out:
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(encoded + "\n", encoding="utf-8")
        print(f"Wrote Isaac replay bundle: {output_path}")
        return

    print(encoded)


if __name__ == "__main__":
    main()
