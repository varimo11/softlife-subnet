from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Protocol, runtime_checkable

from softlife_subnet.actions import Action, ActionType, TrajectoryLike, ensure_trajectory
from softlife_subnet.robotics.commands import CompiledRobotCommand, RobotCommandType
from softlife_subnet.robotics.scene_mapping import HotelRoomSceneManifest


@runtime_checkable
class ActionProvider(Protocol):
    """Unitree-style source of compiled robot commands for replay loops."""

    provider_name: str

    def commands(self) -> Iterator[CompiledRobotCommand]:
        """Yield deterministic robot commands for an adapter control loop."""


@dataclass(frozen=True)
class SoftLifeTrajectoryProvider:
    """Compiles miner symbolic actions into adapter-internal robot commands."""

    trajectory: TrajectoryLike
    scene_manifest: HotelRoomSceneManifest
    provider_name: str = "softlife_trajectory_provider_v1"

    def commands(self) -> Iterator[CompiledRobotCommand]:
        canonical_trajectory = ensure_trajectory(self.trajectory)
        for index, action in enumerate(canonical_trajectory):
            yield compile_action(
                action=action,
                action_index=index,
                scene_manifest=self.scene_manifest,
            )


def compile_action(
    action: Action,
    action_index: int,
    scene_manifest: HotelRoomSceneManifest,
) -> CompiledRobotCommand:
    if action.type == ActionType.MOVE_TO_ZONE:
        return CompiledRobotCommand(
            command_type=RobotCommandType.NAVIGATE_TO_FRAME,
            action_index=action_index,
            source_action_type=action.type.value,
            target_frame=scene_manifest.zone_frame(action.zone),
            zone=action.zone,
        )

    if action.type == ActionType.MOVE_TO_OBJECT:
        return CompiledRobotCommand(
            command_type=RobotCommandType.APPROACH_OBJECT,
            action_index=action_index,
            source_action_type=action.type.value,
            target_frame=scene_manifest.object_prim(action.object_id),
            object_id=action.object_id,
        )

    if action.type == ActionType.PICK:
        return CompiledRobotCommand(
            command_type=RobotCommandType.GRASP_OBJECT,
            action_index=action_index,
            source_action_type=action.type.value,
            target_frame=scene_manifest.object_prim(action.object_id),
            object_id=action.object_id,
        )

    if action.type == ActionType.PLACE:
        return CompiledRobotCommand(
            command_type=RobotCommandType.RELEASE_OBJECT,
            action_index=action_index,
            source_action_type=action.type.value,
            target_frame=scene_manifest.zone_frame(action.zone),
            object_id=action.object_id,
            zone=action.zone,
        )

    if action.type == ActionType.CLEAN_SURFACE:
        return CompiledRobotCommand(
            command_type=RobotCommandType.WIPE_SURFACE,
            action_index=action_index,
            source_action_type=action.type.value,
            target_frame=scene_manifest.surface_prim(action.zone),
            zone=action.zone,
            parameters={"cleaning_passes": 1},
        )

    if action.type == ActionType.DISPOSE:
        return CompiledRobotCommand(
            command_type=RobotCommandType.DROP_IN_RECEPTACLE,
            action_index=action_index,
            source_action_type=action.type.value,
            target_frame=scene_manifest.zone_frame("trash_bin"),
            object_id=action.object_id,
            zone="trash_bin",
        )

    return CompiledRobotCommand(
        command_type=RobotCommandType.HOLD_POSITION,
        action_index=action_index,
        source_action_type=action.type.value,
    )
