#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integrations.isaac_lab.softlife_isaac_lab.workflow_validation import (  # noqa: E402
    CANONICAL_WORKFLOW_SEEDS,
    validate_isaac_workflow,
    write_workflow_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate Soft Life Isaac replay bundles, scenes, artifacts, and scoring."
    )
    parser.add_argument("--out-dir", required=True, help="Output directory for validation files.")
    parser.add_argument(
        "--seed",
        dest="seeds",
        action="append",
        type=int,
        help=(
            "Validator seed to check. Repeat for multiple seeds. Defaults to "
            f"{', '.join(str(seed) for seed in CANONICAL_WORKFLOW_SEEDS)}."
        ),
    )
    parser.add_argument(
        "--real-stage",
        action="store_true",
        help="Launch Isaac Sim for the stage replay instead of using the dry-run stage model.",
    )
    parser.add_argument(
        "--capture-frames",
        action="store_true",
        help="Capture viewport frames during --real-stage execution.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Run Isaac Sim with a visible window during --real-stage execution.",
    )
    parser.add_argument("--sim-steps", type=int, default=12, help="Dry-run sim steps per command.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the report JSON.")
    args = parser.parse_args()

    seeds = tuple(args.seeds) if args.seeds else CANONICAL_WORKFLOW_SEEDS
    report = validate_isaac_workflow(
        out_dir=args.out_dir,
        seeds=seeds,
        real_stage=args.real_stage,
        capture_frames=args.capture_frames,
        headless=not args.show,
        sim_steps=args.sim_steps,
    )
    report_path = Path(args.out_dir) / "softlife_isaac_workflow_report.json"
    write_workflow_report(report, report_path)
    payload = report.to_wire()
    payload["report_path"] = str(report_path)
    print(
        json.dumps(
            payload,
            indent=2 if args.pretty else None,
            sort_keys=True,
            separators=None if args.pretty else (",", ":"),
        )
    )
    raise SystemExit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
