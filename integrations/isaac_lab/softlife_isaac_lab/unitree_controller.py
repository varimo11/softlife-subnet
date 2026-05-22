from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from integrations.isaac_lab.softlife_isaac_lab.controllers import (
    CommandExecutionResult,
    StageReplayState,
)
from integrations.isaac_lab.softlife_isaac_lab.scene_spec import pose_for_zone
from integrations.isaac_lab.softlife_isaac_lab.stage_truth import (
    read_stage_cleanliness,
    read_stage_object_states,
)
from softlife_subnet.physics_artifacts import (
    CleanlinessMeasurement,
    CollisionEvent,
    DamageEvent,
    DroppedObjectEvent,
    ObjectPhysicsState,
    PhysicsReplayArtifact,
)


class UnitreeIsaacControllerUnavailable(RuntimeError):
    """Raised when Unitree/Isaac replay is requested without a backend."""


@dataclass(frozen=True)
class BackendCommandResult:
    ok: bool
    message: str
    robot_zone_after: str
    held_object_after: str | None = None
    sim_steps: int = 0


@dataclass(frozen=True)
class BackendSnapshot:
    room_id: str
    scene_root: str
    sim_seed: int | None
    robot_zone: str
    object_states: tuple[ObjectPhysicsState, ...]
    cleanliness: tuple[CleanlinessMeasurement, ...]
    collisions: tuple[CollisionEvent, ...] = ()
    damage_events: tuple[DamageEvent, ...] = ()
    dropped_objects: tuple[DroppedObjectEvent, ...] = ()


@runtime_checkable
class UnitreeIsaacBackend(Protocol):
    """Backend operations a real Unitree/Isaac controller must implement."""

    backend_name: str

    def navigate_to_frame(
        self,
        *,
        target_frame: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        """Move the robot base/end-effector to a named zone frame."""

    def approach_object(
        self,
        *,
        object_id: str,
        object_prim: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        """Move to a pre-grasp pose around an object prim."""

    def grasp_object(
        self,
        *,
        object_id: str,
        object_prim: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        """Close gripper and verify object attachment."""

    def release_object(
        self,
        *,
        object_id: str,
        target_frame: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        """Release held object inside a target zone."""

    def drop_in_receptacle(
        self,
        *,
        object_id: str,
        target_frame: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        """Drop held object into a receptacle such as the trash bin."""

    def wipe_surface(
        self,
        *,
        surface_prim: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        """Execute a cleaning/contact trajectory over a surface."""

    def hold_position(self, *, sim_steps: int) -> BackendCommandResult:
        """Hold current robot command for the requested simulation steps."""

    def snapshot(self) -> BackendSnapshot:
        """Return validator-owned final physics truth."""


class SimulatedUnitreeBackend:
    """Deterministic backend for exercising the Unitree command path locally.

    This backend uses the same symbolic state transition model as the
    stage-level bridge. It is useful for validating command mapping and artifact
    ingestion on machines without Isaac/Unitree dependencies, but it does not
    run Isaac physics or Unitree articulation control.
    """

    backend_name = "simulated_unitree_backend_v1"

    def __init__(self, state: StageReplayState) -> None:
        self.state = state

    @classmethod
    def from_bundle(cls, bundle_payload: Mapping[str, Any]) -> "SimulatedUnitreeBackend":
        return cls(StageReplayState.from_bundle(bundle_payload))

    def navigate_to_frame(
        self,
        *,
        target_frame: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        return self._apply(
            {
                "command_type": "navigate_to_frame",
                "target_frame": target_frame,
                "zone": zone,
            },
            sim_steps=sim_steps,
        )

    def approach_object(
        self,
        *,
        object_id: str,
        object_prim: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        return self._apply(
            {
                "command_type": "approach_object",
                "target_frame": object_prim,
                "object_id": object_id,
            },
            sim_steps=sim_steps,
        )

    def grasp_object(
        self,
        *,
        object_id: str,
        object_prim: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        return self._apply(
            {
                "command_type": "grasp_object",
                "target_frame": object_prim,
                "object_id": object_id,
            },
            sim_steps=sim_steps,
        )

    def release_object(
        self,
        *,
        object_id: str,
        target_frame: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        return self._apply(
            {
                "command_type": "release_object",
                "target_frame": target_frame,
                "object_id": object_id,
                "zone": zone,
            },
            sim_steps=sim_steps,
        )

    def drop_in_receptacle(
        self,
        *,
        object_id: str,
        target_frame: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        return self._apply(
            {
                "command_type": "drop_in_receptacle",
                "target_frame": target_frame,
                "object_id": object_id,
                "zone": zone,
            },
            sim_steps=sim_steps,
        )

    def wipe_surface(
        self,
        *,
        surface_prim: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        return self._apply(
            {
                "command_type": "wipe_surface",
                "target_frame": surface_prim,
                "zone": zone,
            },
            sim_steps=sim_steps,
        )

    def hold_position(self, *, sim_steps: int) -> BackendCommandResult:
        return self._apply({"command_type": "hold_position"}, sim_steps=sim_steps)

    def snapshot(self) -> BackendSnapshot:
        return BackendSnapshot(
            room_id=self.state.room_id,
            scene_root=self.state.scene_root,
            sim_seed=self.state.sim_seed,
            robot_zone=self.state.robot_zone,
            object_states=tuple(
                self.state.object_state(object_id)
                for object_id in sorted(self.state.object_zones)
            ),
            cleanliness=tuple(
                self.state.cleanliness(zone)
                for zone in sorted(self.state.surface_dirt_after)
            ),
        )

    def _apply(
        self,
        command: Mapping[str, Any],
        *,
        sim_steps: int,
    ) -> BackendCommandResult:
        ok, message = self.state.apply_command(command)
        return BackendCommandResult(
            ok=ok,
            message=message,
            robot_zone_after=self.state.robot_zone,
            held_object_after=self.state.held_object_id,
            sim_steps=sim_steps,
        )


class StageBackedUnitreeBackend:
    """USD-stage implementation of the Unitree backend contract.

    This backend is a workstation bridge between the pure dry run and a future
    articulated Unitree controller. It executes the Unitree command mapping,
    mutates USD object/surface prims, and snapshots final truth back from the
    stage. It does not command robot joints, grippers, contacts, or dynamics.
    """

    backend_name = "stage_backed_unitree_backend_v1"

    def __init__(
        self,
        *,
        bundle_payload: Mapping[str, Any],
        stage: Any,
        state: StageReplayState | None = None,
    ) -> None:
        self.bundle_payload = bundle_payload
        self.stage = stage
        self.state = state or StageReplayState.from_bundle(bundle_payload)

    @classmethod
    def from_bundle(
        cls,
        bundle_payload: Mapping[str, Any],
        *,
        stage: Any,
    ) -> "StageBackedUnitreeBackend":
        return cls(bundle_payload=bundle_payload, stage=stage)

    def navigate_to_frame(
        self,
        *,
        target_frame: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        return self._apply(
            {
                "command_type": "navigate_to_frame",
                "target_frame": target_frame,
                "zone": zone,
            },
            sim_steps=sim_steps,
        )

    def approach_object(
        self,
        *,
        object_id: str,
        object_prim: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        return self._apply(
            {
                "command_type": "approach_object",
                "target_frame": object_prim,
                "object_id": object_id,
            },
            sim_steps=sim_steps,
        )

    def grasp_object(
        self,
        *,
        object_id: str,
        object_prim: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        return self._apply(
            {
                "command_type": "grasp_object",
                "target_frame": object_prim,
                "object_id": object_id,
            },
            sim_steps=sim_steps,
        )

    def release_object(
        self,
        *,
        object_id: str,
        target_frame: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        return self._apply(
            {
                "command_type": "release_object",
                "target_frame": target_frame,
                "object_id": object_id,
                "zone": zone,
            },
            sim_steps=sim_steps,
        )

    def drop_in_receptacle(
        self,
        *,
        object_id: str,
        target_frame: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        return self._apply(
            {
                "command_type": "drop_in_receptacle",
                "target_frame": target_frame,
                "object_id": object_id,
                "zone": zone,
            },
            sim_steps=sim_steps,
        )

    def wipe_surface(
        self,
        *,
        surface_prim: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        return self._apply(
            {
                "command_type": "wipe_surface",
                "target_frame": surface_prim,
                "zone": zone,
            },
            sim_steps=sim_steps,
        )

    def hold_position(self, *, sim_steps: int) -> BackendCommandResult:
        return self._apply({"command_type": "hold_position"}, sim_steps=sim_steps)

    def snapshot(self) -> BackendSnapshot:
        return BackendSnapshot(
            room_id=self.state.room_id,
            scene_root=self.state.scene_root,
            sim_seed=self.state.sim_seed,
            robot_zone=self.state.robot_zone,
            object_states=read_stage_object_states(
                stage=self.stage,
                bundle_payload=self.bundle_payload,
                held_object_id=self.state.held_object_id,
            ),
            cleanliness=read_stage_cleanliness(
                stage=self.stage,
                bundle_payload=self.bundle_payload,
            ),
        )

    def _apply(
        self,
        command: Mapping[str, Any],
        *,
        sim_steps: int,
    ) -> BackendCommandResult:
        ok, message = self.state.apply_command(command)
        if ok:
            try:
                self._sync_stage()
            except Exception as exc:
                ok = False
                message = f"stage sync failed: {exc}"
        return BackendCommandResult(
            ok=ok,
            message=message,
            robot_zone_after=self.state.robot_zone,
            held_object_after=self.state.held_object_id,
            sim_steps=sim_steps,
        )

    def _sync_stage(self) -> None:
        for object_id, zone in self.state.object_zones.items():
            prim_path = self.state.object_prims.get(object_id)
            if not prim_path:
                continue
            pose_zone = self.state.robot_zone if zone == "__held__" else zone
            _set_stage_translation(self.stage, prim_path, pose_for_zone(pose_zone))

        for zone, dirt in self.state.surface_dirt_after.items():
            prim_path = self.state.surface_prims.get(zone)
            if prim_path:
                _set_stage_attribute(self.stage, prim_path, "softlife:dirt", float(dirt))


class UnitreeIsaacReplayController:
    """Robot replay controller for future Unitree/Isaac execution.

    The controller maps Soft Life `CompiledRobotCommand` payloads to backend
    robot operations. A real backend owns Isaac Lab scene handles, Unitree
    articulation controllers, gripper state, contact telemetry, and cameras.
    """

    controller_name = "unitree_isaac_replay_controller_v1"

    def __init__(
        self,
        *,
        bundle_payload: Mapping[str, Any],
        backend: UnitreeIsaacBackend,
    ) -> None:
        self.bundle_payload = bundle_payload
        self.backend = backend
        self.command_log: list[dict[str, object]] = []

    @classmethod
    def from_bundle(
        cls,
        bundle_payload: Mapping[str, Any],
        *,
        backend: UnitreeIsaacBackend | None = None,
    ) -> "UnitreeIsaacReplayController":
        resolved_backend = backend or create_unitree_isaac_backend(bundle_payload)
        return cls(bundle_payload=bundle_payload, backend=resolved_backend)

    def execute(
        self,
        command: Mapping[str, Any],
        *,
        sim_steps: int,
    ) -> CommandExecutionResult:
        backend_result = self._execute_backend(command, sim_steps=sim_steps)
        result = CommandExecutionResult(
            command=command,
            ok=backend_result.ok,
            message=backend_result.message,
            robot_zone_after=backend_result.robot_zone_after,
            held_object_after=backend_result.held_object_after,
            sim_steps=backend_result.sim_steps or sim_steps,
        )
        self.command_log.append(
            {
                **result.to_command_log(),
                "controller_name": self.controller_name,
                "backend_name": self.backend.backend_name,
            }
        )
        return result

    def to_artifact(
        self,
        *,
        adapter_name: str,
        action_count: int,
        step_count: int,
    ) -> PhysicsReplayArtifact:
        snapshot = self.backend.snapshot()
        return PhysicsReplayArtifact(
            adapter_name=adapter_name,
            room_id=snapshot.room_id,
            scene_root=snapshot.scene_root,
            sim_seed=snapshot.sim_seed,
            time_step=1.0 / 60.0,
            step_count=step_count,
            action_count=action_count,
            robot_zone=snapshot.robot_zone,
            invalid_actions=sum(
                1 for command in self.command_log if not bool(command.get("ok", True))
            ),
            object_states=snapshot.object_states,
            cleanliness=snapshot.cleanliness,
            collisions=snapshot.collisions,
            damage_events=snapshot.damage_events,
            dropped_objects=snapshot.dropped_objects,
            command_log=tuple(self.command_log),
        )

    def _execute_backend(
        self,
        command: Mapping[str, Any],
        *,
        sim_steps: int,
    ) -> BackendCommandResult:
        command_type = str(command["command_type"])

        if command_type == "navigate_to_frame":
            zone = _required_str(command.get("zone"), "zone")
            target_frame = _required_str(command.get("target_frame"), "target_frame")
            return self.backend.navigate_to_frame(
                target_frame=target_frame,
                zone=zone,
                sim_steps=sim_steps,
            )

        if command_type == "approach_object":
            object_id = _required_str(command.get("object_id"), "object_id")
            target_frame = _required_str(command.get("target_frame"), "target_frame")
            return self.backend.approach_object(
                object_id=object_id,
                object_prim=target_frame,
                sim_steps=sim_steps,
            )

        if command_type == "grasp_object":
            object_id = _required_str(command.get("object_id"), "object_id")
            target_frame = _required_str(command.get("target_frame"), "target_frame")
            return self.backend.grasp_object(
                object_id=object_id,
                object_prim=target_frame,
                sim_steps=sim_steps,
            )

        if command_type == "release_object":
            object_id = _required_str(command.get("object_id"), "object_id")
            zone = _required_str(command.get("zone"), "zone")
            target_frame = _required_str(command.get("target_frame"), "target_frame")
            return self.backend.release_object(
                object_id=object_id,
                target_frame=target_frame,
                zone=zone,
                sim_steps=sim_steps,
            )

        if command_type == "drop_in_receptacle":
            object_id = _required_str(command.get("object_id"), "object_id")
            zone = _required_str(command.get("zone"), "zone")
            target_frame = _required_str(command.get("target_frame"), "target_frame")
            return self.backend.drop_in_receptacle(
                object_id=object_id,
                target_frame=target_frame,
                zone=zone,
                sim_steps=sim_steps,
            )

        if command_type == "wipe_surface":
            zone = _required_str(command.get("zone"), "zone")
            target_frame = _required_str(command.get("target_frame"), "target_frame")
            return self.backend.wipe_surface(
                surface_prim=target_frame,
                zone=zone,
                sim_steps=sim_steps,
            )

        if command_type == "hold_position":
            return self.backend.hold_position(sim_steps=sim_steps)

        return BackendCommandResult(
            ok=False,
            message=f"unsupported Unitree/Isaac command {command_type}",
            robot_zone_after=self.backend.snapshot().robot_zone,
            sim_steps=sim_steps,
        )


def build_unitree_dry_run_artifact(
    bundle_payload: Mapping[str, Any],
    *,
    adapter_name: str = "unitree_isaac_replay_dry_run_v1",
    frame_steps_per_command: int = 12,
) -> PhysicsReplayArtifact:
    """Replay compiled commands through the simulated Unitree backend."""

    commands = _compiled_commands(bundle_payload)
    backend = SimulatedUnitreeBackend.from_bundle(bundle_payload)
    controller = UnitreeIsaacReplayController.from_bundle(
        bundle_payload,
        backend=backend,
    )
    for command in commands:
        controller.execute(command, sim_steps=frame_steps_per_command)

    return controller.to_artifact(
        adapter_name=adapter_name,
        action_count=len(commands),
        step_count=len(commands) * frame_steps_per_command,
    )


def create_unitree_isaac_backend(bundle_payload: Mapping[str, Any]) -> UnitreeIsaacBackend:
    """Create the real Unitree/Isaac backend when dependencies are available.

    This intentionally fails clearly today. The controller contract is ready;
    the missing work is connecting actual Isaac Lab scene/env handles and
    Unitree robot controllers on an Isaac workstation.
    """

    available = {
        "isaaclab": _has_package("isaaclab"),
        "omni.isaac.lab": _has_package("omni.isaac.lab"),
        "unitree_sdk2py": _has_package("unitree_sdk2py"),
    }
    raise UnitreeIsaacControllerUnavailable(
        "No concrete Unitree/Isaac backend is configured. "
        "Implement a backend that satisfies UnitreeIsaacBackend and pass it to "
        "UnitreeIsaacReplayController.from_bundle(..., backend=...). "
        f"Detected packages: {available}"
    )


def _required_str(value: Any, field_name: str) -> str:
    if value is None:
        raise ValueError(f"command is missing {field_name}")
    return str(value)


def _compiled_commands(bundle_payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    return tuple(_mapping(command) for command in bundle_payload.get("compiled_commands", ()))


def _set_stage_translation(
    stage: Any,
    prim_path: str,
    value: tuple[float, float, float],
) -> None:
    prim = _stage_prim(stage, prim_path)
    attr = _stage_attribute(prim, "xformOp:translate")
    if attr is not None and _set_attribute_value(attr, value):
        return

    try:
        from pxr import Gf, UsdGeom

        xformable = UsdGeom.Xformable(prim)
        vec = Gf.Vec3d(*value)
        for op in xformable.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                op.Set(vec)
                return
        xformable.AddTranslateOp().Set(vec)
        return
    except Exception as exc:
        raise RuntimeError(f"could not set translation for {prim_path}") from exc


def _set_stage_attribute(stage: Any, prim_path: str, attr_name: str, value: object) -> None:
    prim = _stage_prim(stage, prim_path)
    attr = _stage_attribute(prim, attr_name)
    if attr is None:
        raise RuntimeError(f"prim {prim_path} is missing attribute {attr_name}")
    if not _set_attribute_value(attr, value):
        raise RuntimeError(f"attribute {attr_name} on {prim_path} is not writable")


def _stage_prim(stage: Any, prim_path: str) -> Any:
    prim = stage.GetPrimAtPath(prim_path)
    if prim is None:
        raise RuntimeError(f"stage is missing prim {prim_path}")
    if hasattr(prim, "IsValid") and not prim.IsValid():
        raise RuntimeError(f"stage prim is invalid: {prim_path}")
    return prim


def _stage_attribute(prim: Any, attr_name: str) -> Any:
    if not hasattr(prim, "GetAttribute"):
        return None
    attr = prim.GetAttribute(attr_name)
    if attr is None:
        return None
    if hasattr(attr, "IsValid") and not attr.IsValid():
        return None
    return attr


def _set_attribute_value(attr: Any, value: object) -> bool:
    if hasattr(attr, "Set"):
        attr.Set(value)
        return True
    if hasattr(attr, "value"):
        attr.value = value
        return True
    return False


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected mapping, got {type(value).__name__}")
    return value


def _has_package(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False
