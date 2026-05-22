from __future__ import annotations

from typing import Any, Mapping

from integrations.isaac_lab.softlife_isaac_lab.controllers import StageReplayController
from integrations.isaac_lab.softlife_isaac_lab.scene_spec import pose_for_zone
from softlife_subnet.physics_artifacts import (
    CleanlinessMeasurement,
    ObjectPhysicsState,
    PhysicsReplayArtifact,
    Vector3,
)


def build_stage_truth_artifact(
    *,
    stage: Any,
    bundle_payload: Mapping[str, Any],
    controller: StageReplayController,
    adapter_name: str,
    action_count: int,
    step_count: int,
    time_step: float = 1.0 / 60.0,
) -> PhysicsReplayArtifact:
    """Build a replay artifact from USD stage truth after replay.

    The stage-level runner still uses symbolic command effects, but this
    function reads final object transforms and surface dirt from the stage
    instead of trusting the controller's in-memory state. Real Unitree/Isaac
    backends should follow the same pattern with richer physics telemetry.
    """

    scene_manifest = _mapping(bundle_payload["scene_manifest"])
    private_state = _mapping(bundle_payload["validator_private_state"])
    raw_seed = private_state.get("private_seed")

    return PhysicsReplayArtifact(
        adapter_name=adapter_name,
        room_id=str(bundle_payload["challenge_id"]),
        scene_root=str(scene_manifest["root_prim"]),
        sim_seed=None if raw_seed is None else int(raw_seed),
        time_step=time_step,
        step_count=step_count,
        action_count=action_count,
        robot_zone=controller.state.robot_zone,
        invalid_actions=sum(
            1 for command in controller.command_log if not bool(command.get("ok", True))
        ),
        object_states=read_stage_object_states(
            stage=stage,
            bundle_payload=bundle_payload,
            held_object_id=controller.state.held_object_id,
        ),
        cleanliness=read_stage_cleanliness(
            stage=stage,
            bundle_payload=bundle_payload,
        ),
        command_log=tuple(controller.command_log),
    )


def read_stage_object_states(
    *,
    stage: Any,
    bundle_payload: Mapping[str, Any],
    held_object_id: str | None = None,
) -> tuple[ObjectPhysicsState, ...]:
    private_state = _mapping(bundle_payload["validator_private_state"])
    public_state = _mapping(bundle_payload["public_state"])
    scene_manifest = _mapping(bundle_payload["scene_manifest"])
    object_prims = {
        str(key): str(value)
        for key, value in _mapping(scene_manifest["object_prims"]).items()
    }
    objects = tuple(_mapping(item) for item in private_state.get("objects", ()))
    zones = tuple(str(zone) for zone in public_state.get("zones", ()))
    return tuple(
        _object_state_from_stage(
            stage=stage,
            obj=obj,
            object_prims=object_prims,
            zones=zones,
            held_object_id=held_object_id,
        )
        for obj in sorted(objects, key=lambda item: str(item["object_id"]))
    )


def read_stage_cleanliness(
    *,
    stage: Any,
    bundle_payload: Mapping[str, Any],
) -> tuple[CleanlinessMeasurement, ...]:
    private_state = _mapping(bundle_payload["validator_private_state"])
    scene_manifest = _mapping(bundle_payload["scene_manifest"])
    surface_prims = {
        str(key): str(value)
        for key, value in _mapping(scene_manifest["surface_prims"]).items()
    }
    surfaces = tuple(_mapping(item) for item in private_state.get("surfaces", ()))
    return tuple(
        _cleanliness_from_stage(
            stage=stage,
            surface=surface,
            surface_prims=surface_prims,
        )
        for surface in sorted(surfaces, key=lambda item: str(item["zone"]))
    )


def _object_state_from_stage(
    *,
    stage: Any,
    obj: Mapping[str, Any],
    object_prims: Mapping[str, str],
    zones: tuple[str, ...],
    held_object_id: str | None,
) -> ObjectPhysicsState:
    object_id = str(obj["object_id"])
    prim_path = object_prims[object_id]
    position = _read_prim_translation(stage, prim_path)
    held = object_id == held_object_id
    return ObjectPhysicsState(
        object_id=object_id,
        prim_path=prim_path,
        target_zone=str(obj["target_zone"]),
        zone=None if held else _nearest_zone(position, zones),
        position=position,
        held=held,
    )


def _cleanliness_from_stage(
    *,
    stage: Any,
    surface: Mapping[str, Any],
    surface_prims: Mapping[str, str],
) -> CleanlinessMeasurement:
    zone = str(surface["zone"])
    surface_prim = surface_prims[zone]
    dirt_before = float(surface.get("dirt", 0.0))
    dirt_after = float(_read_prim_attribute(stage, surface_prim, "softlife:dirt"))
    cleaned = max(0.0, dirt_before - dirt_after)
    cleaned_fraction = 0.0 if dirt_before <= 0 else min(1.0, cleaned / dirt_before)
    return CleanlinessMeasurement(
        zone=zone,
        surface_prim=surface_prim,
        dirt_before=dirt_before,
        dirt_after=dirt_after,
        cleaned_area_fraction=cleaned_fraction,
    )


def _read_prim_translation(stage: Any, prim_path: str) -> Vector3:
    prim = _require_prim(stage, prim_path)
    attr = _optional_prim_attribute(prim, "xformOp:translate")
    if attr is not None:
        value = _attribute_value(attr)
        if value is not None:
            return _vector3_from_value(value)

    try:
        from pxr import Usd, UsdGeom

        matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
            Usd.TimeCode.Default()
        )
        return _vector3_from_value(matrix.ExtractTranslation())
    except Exception as exc:
        raise RuntimeError(f"could not read translation for prim {prim_path}") from exc


def _read_prim_attribute(stage: Any, prim_path: str, attr_name: str) -> Any:
    prim = _require_prim(stage, prim_path)
    attr = _optional_prim_attribute(prim, attr_name)
    if attr is None:
        raise RuntimeError(f"prim {prim_path} is missing attribute {attr_name}")
    return _attribute_value(attr)


def _require_prim(stage: Any, prim_path: str) -> Any:
    prim = stage.GetPrimAtPath(prim_path)
    if prim is None:
        raise RuntimeError(f"stage is missing prim {prim_path}")
    if hasattr(prim, "IsValid") and not prim.IsValid():
        raise RuntimeError(f"stage prim is invalid: {prim_path}")
    return prim


def _optional_prim_attribute(prim: Any, attr_name: str) -> Any:
    if not hasattr(prim, "GetAttribute"):
        return None
    attr = prim.GetAttribute(attr_name)
    if attr is None:
        return None
    if hasattr(attr, "IsValid") and not attr.IsValid():
        return None
    return attr


def _attribute_value(attr: Any) -> Any:
    if hasattr(attr, "Get"):
        return attr.Get()
    return attr


def _vector3_from_value(value: Any) -> Vector3:
    try:
        return Vector3(x=float(value[0]), y=float(value[1]), z=float(value[2]))
    except (TypeError, KeyError, IndexError):
        pass
    if all(hasattr(value, axis) for axis in ("x", "y", "z")):
        return Vector3(x=float(value.x), y=float(value.y), z=float(value.z))
    raise TypeError(f"expected 3D vector value, got {type(value).__name__}")


def _nearest_zone(position: Vector3, zones: tuple[str, ...]) -> str | None:
    if not zones:
        return None
    return min(
        zones,
        key=lambda zone: _planar_distance_squared(position, pose_for_zone(zone)),
    )


def _planar_distance_squared(
    position: Vector3,
    zone_pose: tuple[float, float, float],
) -> float:
    return (position.x - zone_pose[0]) ** 2 + (position.y - zone_pose[1]) ** 2


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected mapping, got {type(value).__name__}")
    return value
