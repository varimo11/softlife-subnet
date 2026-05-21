from __future__ import annotations

from typing import Mapping

from softlife_subnet.physics_artifacts import (
    CleanlinessMeasurement,
    ObjectPhysicsState,
    PhysicsReplayArtifact,
)
from softlife_subnet.robotics.scene_mapping import HotelRoomSceneManifest
from softlife_subnet.state import HELD_LOCATION, EnvironmentState, ObjectState, SurfaceState


def build_symbolic_physics_artifact(
    *,
    adapter_name: str,
    initial_state: EnvironmentState,
    final_state: EnvironmentState,
    scene_manifest: HotelRoomSceneManifest,
    step_count: int,
    action_count: int | None = None,
    invalid_actions: int = 0,
    command_log: tuple[Mapping[str, object], ...] = (),
) -> PhysicsReplayArtifact:
    """Create a physics artifact from symbolic replay.

    The mock backend cannot produce real poses or contact forces, but this gives
    the validator pipeline the same artifact shape that Isaac Lab will fill with
    measured physics truth.
    """

    initial_surfaces = {surface.zone: surface for surface in initial_state.surfaces}
    object_states = tuple(
        _object_state(obj=obj, scene_manifest=scene_manifest) for obj in final_state.objects
    )
    cleanliness = tuple(
        _cleanliness_measurement(
            initial=initial_surfaces[surface.zone],
            final=surface,
            scene_manifest=scene_manifest,
        )
        for surface in final_state.surfaces
    )
    return PhysicsReplayArtifact(
        adapter_name=adapter_name,
        room_id=final_state.room_id,
        scene_root=scene_manifest.root_prim,
        sim_seed=final_state.private_seed,
        time_step=1.0,
        step_count=step_count,
        action_count=step_count if action_count is None else action_count,
        robot_zone=final_state.robot_zone,
        invalid_actions=invalid_actions,
        object_states=object_states,
        cleanliness=cleanliness,
        command_log=command_log,
    )


def _object_state(
    *,
    obj: ObjectState,
    scene_manifest: HotelRoomSceneManifest,
) -> ObjectPhysicsState:
    return ObjectPhysicsState(
        object_id=obj.object_id,
        prim_path=scene_manifest.object_prim(obj.object_id) or "",
        target_zone=obj.target_zone,
        zone=None if obj.location == HELD_LOCATION else obj.location,
        held=obj.location == HELD_LOCATION,
    )


def _cleanliness_measurement(
    *,
    initial: SurfaceState,
    final: SurfaceState,
    scene_manifest: HotelRoomSceneManifest,
) -> CleanlinessMeasurement:
    cleaned = max(0.0, initial.dirt - final.dirt)
    cleaned_fraction = 0.0 if initial.dirt <= 0 else min(1.0, cleaned / initial.dirt)
    return CleanlinessMeasurement(
        zone=final.zone,
        surface_prim=scene_manifest.surface_prim(final.zone) or "",
        dirt_before=initial.dirt,
        dirt_after=final.dirt,
        cleaned_area_fraction=cleaned_fraction,
    )
