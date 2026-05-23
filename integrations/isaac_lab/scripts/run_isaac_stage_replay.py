#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integrations.isaac_lab.softlife_isaac_lab.config import SoftLifeIsaacRunConfig  # noqa: E402
from integrations.isaac_lab.softlife_isaac_lab.isaac_sim_runner import (  # noqa: E402
    build_stage_level_artifact,
    run_isaac_sim_stage_replay,
)
from integrations.isaac_lab.softlife_isaac_lab.scene_spec import CAMERA_NAMES  # noqa: E402
from integrations.isaac_lab.softlife_isaac_lab.usd_export import (  # noqa: E402
    load_bundle_payload,
    write_usda_scene,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a Soft Life replay bundle in Isaac Sim at the USD stage level."
    )
    parser.add_argument("--bundle", required=True, help="Validator-private replay bundle JSON.")
    parser.add_argument("--scene", help="USDA/USD scene path. Generated when missing.")
    parser.add_argument("--out-artifact", required=True, help="Output physics artifact JSON path.")
    parser.add_argument("--render-dir", help="Optional directory for viewport frame capture.")
    parser.add_argument(
        "--camera",
        action="append",
        choices=CAMERA_NAMES,
        help=(
            "Validator camera to capture when --render-dir is set. Repeat to "
            "select multiple cameras. Defaults to all validator cameras."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not launch Isaac Sim; execute the same command semantics offline.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Run Isaac Sim with a visible window instead of headless mode.",
    )
    args = parser.parse_args()

    bundle_payload = load_bundle_payload(args.bundle)
    scene_path = Path(args.scene) if args.scene else _default_scene_path(args.out_artifact)
    if not scene_path.exists():
        write_usda_scene(bundle_payload, scene_path)

    if args.dry_run:
        artifact = build_stage_level_artifact(bundle_payload)
    else:
        result = run_isaac_sim_stage_replay(
            bundle_payload,
            scene_path=scene_path,
            output_artifact_path=args.out_artifact,
            render_dir=args.render_dir,
            camera_names=args.camera,
            config=SoftLifeIsaacRunConfig(headless=not args.show),
        )
        artifact = result.artifact
        if args.render_dir:
            print(f"Captured frames: {len(result.rendered_frames)}")

    output_path = Path(args.out_artifact)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact.to_private_wire(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote physics artifact: {output_path}")
    print(f"Scene path: {scene_path}")
    print(f"Artifact hash: {artifact.artifact_hash}")


def _default_scene_path(output_artifact_path: str) -> Path:
    artifact_path = Path(output_artifact_path)
    return artifact_path.with_suffix(".usda")


if __name__ == "__main__":
    main()
