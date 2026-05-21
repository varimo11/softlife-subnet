#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integrations.isaac_lab.softlife_isaac_lab.usd_export import (  # noqa: E402
    load_bundle_payload,
    write_usda_scene,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a lightweight Isaac-loadable USDA scene from a replay bundle."
    )
    parser.add_argument("--bundle", required=True, help="Replay bundle JSON path.")
    parser.add_argument("--out", required=True, help="Output .usda path.")
    args = parser.parse_args()

    payload = load_bundle_payload(args.bundle)
    output_path = write_usda_scene(payload, args.out)
    print(f"Wrote Isaac USDA scene: {output_path}")


if __name__ == "__main__":
    main()
