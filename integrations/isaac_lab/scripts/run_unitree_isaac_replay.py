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
    UnitreeIsaacControllerUnavailable,
    UnitreeIsaacReplayController,
    build_unitree_dry_run_artifact,
)
from integrations.isaac_lab.softlife_isaac_lab.scene_spec import CAMERA_NAMES  # noqa: E402
from integrations.isaac_lab.softlife_isaac_lab.unitree_stage_runner import (  # noqa: E402
    run_unitree_stage_backend_replay,
)
from integrations.isaac_lab.softlife_isaac_lab.usd_export import load_bundle_payload  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Soft Life compiled commands through a Unitree/Isaac controller backend."
    )
    parser.add_argument("--bundle", required=True, help="Validator-private replay bundle JSON.")
    parser.add_argument("--scene", help="USDA/USD scene path for --stage-backend. Generated when missing.")
    parser.add_argument("--out-artifact", required=True, help="Output physics artifact JSON path.")
    parser.add_argument("--render-dir", help="Optional viewport frame directory for --stage-backend.")
    parser.add_argument(
        "--camera",
        action="append",
        choices=CAMERA_NAMES,
        help=(
            "Validator camera to capture when --render-dir is set. Repeat to "
            "select multiple cameras. Defaults to all validator cameras."
        ),
    )
    parser.add_argument("--sim-steps", type=int, default=12, help="Simulation steps per command.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Use the deterministic simulated Unitree backend. This validates the "
            "controller/artifact path without Isaac physics or Unitree runtime."
        ),
    )
    parser.add_argument(
        "--stage-backend",
        action="store_true",
        help=(
            "Use an Isaac USD stage-backed Unitree backend. This launches Isaac "
            "Sim and mutates stage prims, but does not drive Unitree articulation."
        ),
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Run Isaac Sim with a visible window for --stage-backend.",
    )
    args = parser.parse_args()
    if args.dry_run and args.stage_backend:
        parser.error("--dry-run and --stage-backend are mutually exclusive")

    bundle_payload = load_bundle_payload(args.bundle)
    if args.dry_run:
        artifact = build_unitree_dry_run_artifact(
            bundle_payload,
            frame_steps_per_command=args.sim_steps,
        )
        rendered_frames: tuple[Path, ...] = ()
        scene_path: Path | None = None
    elif args.stage_backend:
        try:
            result = run_unitree_stage_backend_replay(
                bundle_payload,
                scene_path=args.scene or str(_default_scene_path(args.out_artifact)),
                render_dir=args.render_dir,
                camera_names=args.camera,
                sim_steps=args.sim_steps,
                headless=not args.show,
            )
            artifact = result.artifact
            scene_path = result.scene_path
            rendered_frames = result.rendered_frames
        except UnitreeIsaacControllerUnavailable as exc:
            print(f"Unitree/Isaac stage backend unavailable: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
    else:
        try:
            controller = UnitreeIsaacReplayController.from_bundle(bundle_payload)
        except UnitreeIsaacControllerUnavailable as exc:
            print(f"Unitree/Isaac backend unavailable: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        commands = tuple(bundle_payload.get("compiled_commands", ()))
        for command in commands:
            controller.execute(command, sim_steps=args.sim_steps)
        artifact = controller.to_artifact(
            adapter_name="unitree_isaac_replay_v1",
            action_count=len(commands),
            step_count=len(commands) * args.sim_steps,
        )
        rendered_frames = ()
        scene_path = None
    output_path = Path(args.out_artifact)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact.to_private_wire(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote Unitree/Isaac physics artifact: {output_path}")
    if args.dry_run:
        print("Dry run: used simulated Unitree backend; no Isaac physics was executed.")
    if args.stage_backend:
        print(f"Stage backend scene path: {scene_path}")
        print(f"Captured frames: {len(rendered_frames)}")
    print(f"Artifact hash: {artifact.artifact_hash}")


def _default_scene_path(output_artifact_path: str) -> Path:
    return Path(output_artifact_path).with_suffix(".usda")


if __name__ == "__main__":
    main()
