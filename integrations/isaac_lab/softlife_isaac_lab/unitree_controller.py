from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from integrations.isaac_lab.softlife_isaac_lab.controllers import CommandExecutionResult
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


def _has_package(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False
