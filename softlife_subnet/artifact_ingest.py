from __future__ import annotations

from dataclasses import replace

from softlife_subnet.actions import Trajectory, TrajectoryLike, ensure_trajectory
from softlife_subnet.physics_artifacts import PhysicsReplayArtifact
from softlife_subnet.simulation import ReplayEvent, ReplayResult
from softlife_subnet.state import HELD_LOCATION, EnvironmentState


def replay_result_from_physics_artifact(
    *,
    initial_state: EnvironmentState,
    trajectory: TrajectoryLike,
    artifact: PhysicsReplayArtifact,
) -> ReplayResult:
    """Convert Isaac/hardware physics truth back into validator replay output."""

    canonical_trajectory = ensure_trajectory(trajectory)
    final_state = final_state_from_physics_artifact(
        initial_state=initial_state,
        artifact=artifact,
    )
    events = _events_from_artifact(
        trajectory=canonical_trajectory,
        final_robot_zone=final_state.robot_zone,
        artifact=artifact,
    )
    return ReplayResult(
        initial_state=initial_state,
        final_state=final_state,
        events=events,
        invalid_actions=artifact.invalid_actions,
        action_count=artifact.action_count,
        replay_hash=artifact.artifact_hash,
        adapter_name=artifact.adapter_name,
        physics_artifact=artifact,
    )


def final_state_from_physics_artifact(
    *,
    initial_state: EnvironmentState,
    artifact: PhysicsReplayArtifact,
) -> EnvironmentState:
    if artifact.room_id != initial_state.room_id:
        raise ValueError(
            f"artifact room_id {artifact.room_id} does not match {initial_state.room_id}"
        )

    physics_objects = {item.object_id: item for item in artifact.object_states}
    dirt_after_by_zone = {item.zone: item.dirt_after for item in artifact.cleanliness}

    objects = []
    for obj in initial_state.objects:
        physics_obj = physics_objects.get(obj.object_id)
        if physics_obj is None:
            objects.append(obj)
            continue
        if physics_obj.held:
            location = HELD_LOCATION
        elif physics_obj.zone is None:
            location = obj.location
        else:
            location = physics_obj.zone
        objects.append(replace(obj, location=location))

    surfaces = []
    for surface in initial_state.surfaces:
        if surface.zone in dirt_after_by_zone:
            surfaces.append(replace(surface, dirt=dirt_after_by_zone[surface.zone]))
        else:
            surfaces.append(surface)

    return replace(
        initial_state,
        robot_zone=artifact.robot_zone or initial_state.robot_zone,
        objects=tuple(objects),
        surfaces=tuple(surfaces),
    )


def _events_from_artifact(
    *,
    trajectory: Trajectory,
    final_robot_zone: str,
    artifact: PhysicsReplayArtifact,
) -> tuple[ReplayEvent, ...]:
    command_by_index = {
        int(command.get("action_index", index)): command
        for index, command in enumerate(artifact.command_log)
    }
    events = []
    for index, action in enumerate(trajectory):
        command = command_by_index.get(index, {})
        ok = bool(command.get("ok", True))
        message = str(command.get("message", "physics replay command accepted"))
        events.append(
            ReplayEvent(
                action_index=index,
                action=action,
                ok=ok,
                message=message,
                robot_zone_after=final_robot_zone,
                held_object_after=None,
            )
        )
    return tuple(events)
