from __future__ import annotations

import importlib.util
from typing import Mapping

from integrations.isaac_lab.softlife_isaac_lab.config import SoftLifeIsaacRunConfig


class IsaacLabNotAvailable(RuntimeError):
    """Raised when this integration is invoked outside an Isaac Lab runtime."""


def find_isaac_lab_package() -> str | None:
    """Return the installed Isaac Lab import path, if one is available."""

    candidates = ("isaaclab", "omni.isaac.lab")
    for candidate in candidates:
        try:
            spec = importlib.util.find_spec(candidate)
        except ModuleNotFoundError:
            spec = None
        if spec is not None:
            return candidate
    return None


def run_replay_bundle(
    bundle: Mapping[str, object],
    config: SoftLifeIsaacRunConfig | None = None,
) -> dict[str, object]:
    """Run one validator-private replay bundle in Isaac Lab.

    The real implementation should create/load the USD scene, step the robot
    controller through `compiled_commands`, and return a
    `softlife.physics_replay.v1` artifact.
    """

    run_config = config or SoftLifeIsaacRunConfig()
    isaac_package = find_isaac_lab_package()
    if isaac_package is None:
        raise IsaacLabNotAvailable(
            "Isaac Lab is not installed in this Python environment. "
            "Run this function from an Isaac Sim/Isaac Lab workstation or "
            "container, then implement the scene/controller loop."
        )

    raise NotImplementedError(
        "Isaac Lab was detected as "
        f"{isaac_package}, but the Soft Life hotel-room task loop is not "
        f"implemented yet for task {run_config.task_name}."
    )
