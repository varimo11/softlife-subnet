"""Isaac Lab-side Soft Life integration package.

Modules in this package must import Isaac Lab lazily so the repo remains usable
on machines without NVIDIA/Isaac dependencies.
"""

from integrations.isaac_lab.softlife_isaac_lab.config import SoftLifeIsaacRunConfig
from integrations.isaac_lab.softlife_isaac_lab.controllers import (
    CommandExecutionResult,
    RobotReplayController,
    StageReplayController,
)
from integrations.isaac_lab.softlife_isaac_lab.isaac_sim_runner import (
    IsaacSimRuntimeNotAvailable,
    build_stage_level_artifact,
    find_isaac_sim_package,
    run_isaac_sim_stage_replay,
)
from integrations.isaac_lab.softlife_isaac_lab.replay_runner import (
    IsaacLabNotAvailable,
    find_isaac_lab_package,
    run_replay_bundle,
)
from integrations.isaac_lab.softlife_isaac_lab.unitree_controller import (
    BackendCommandResult,
    BackendSnapshot,
    UnitreeIsaacBackend,
    UnitreeIsaacControllerUnavailable,
    UnitreeIsaacReplayController,
)

__all__ = [
    "BackendCommandResult",
    "BackendSnapshot",
    "IsaacLabNotAvailable",
    "IsaacSimRuntimeNotAvailable",
    "CommandExecutionResult",
    "RobotReplayController",
    "SoftLifeIsaacRunConfig",
    "StageReplayController",
    "UnitreeIsaacBackend",
    "UnitreeIsaacControllerUnavailable",
    "UnitreeIsaacReplayController",
    "build_stage_level_artifact",
    "find_isaac_lab_package",
    "find_isaac_sim_package",
    "run_isaac_sim_stage_replay",
    "run_replay_bundle",
]
