from __future__ import annotations

from dataclasses import dataclass

from softlife_subnet.actions import TrajectoryLike
from softlife_subnet.robotics import HotelRoomSceneManifest, SoftLifeTrajectoryProvider
from softlife_subnet.simulation import ReplayResult
from softlife_subnet.state import EnvironmentState


class IsaacSimUnavailableError(RuntimeError):
    """Raised when the optional Isaac Lab backend is requested but unavailable."""


@dataclass(frozen=True)
class IsaacSimSimulationAdapter:
    """Future Isaac Lab replay adapter.

    This class intentionally does not import Isaac Lab at module import time, so
    the lightweight MVP remains runnable on machines without NVIDIA/Isaac
    dependencies. A real implementation will mirror Unitree's structure:
    scene config, action provider, controller loop, physics truth extraction,
    and replay artifact generation.
    """

    task_name: str = "SoftLife-HotelRoom-Restore-v0"
    headless: bool = True
    adapter_name: str = "isaac_lab_softlife_stub_v1"

    def replay(
        self,
        environment_state: EnvironmentState,
        trajectory: TrajectoryLike,
    ) -> ReplayResult:
        scene_manifest = HotelRoomSceneManifest.from_environment(environment_state)
        action_provider = SoftLifeTrajectoryProvider(
            trajectory=trajectory,
            scene_manifest=scene_manifest,
        )
        compiled_commands = tuple(command.to_wire() for command in action_provider.commands())
        raise IsaacSimUnavailableError(
            "Isaac Lab replay is not implemented in this lightweight environment. "
            "The symbolic trajectory compiled successfully into "
            f"{len(compiled_commands)} robot commands for task {self.task_name}; "
            "install Isaac Sim/Isaac Lab and implement the adapter control loop "
            "to execute them."
        )
