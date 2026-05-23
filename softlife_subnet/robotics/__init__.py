"""Robot execution bridge primitives.

These classes sit between miner trajectories and future Isaac Lab, ROS2, or
Unitree/DDS replay loops. They are adapter-internal contracts; miners still
only see public room state and return symbolic trajectories.
"""

from softlife_subnet.robotics.action_provider import (
    ActionProvider,
    SoftLifeTrajectoryProvider,
)
from softlife_subnet.robotics.artifact_builder import build_symbolic_physics_artifact
from softlife_subnet.robotics.commands import CompiledRobotCommand, RobotCommandType
from softlife_subnet.robotics.scene_mapping import (
    VALIDATOR_CAMERA_NAMES,
    HotelRoomSceneManifest,
)

__all__ = [
    "ActionProvider",
    "CompiledRobotCommand",
    "HotelRoomSceneManifest",
    "RobotCommandType",
    "SoftLifeTrajectoryProvider",
    "VALIDATOR_CAMERA_NAMES",
    "build_symbolic_physics_artifact",
]
