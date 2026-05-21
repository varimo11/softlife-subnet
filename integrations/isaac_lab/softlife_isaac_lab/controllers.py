from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from integrations.isaac_lab.softlife_isaac_lab.scene_spec import pose_for_zone
from softlife_subnet.physics_artifacts import (
    CleanlinessMeasurement,
    ObjectPhysicsState,
    PhysicsReplayArtifact,
    Vector3,
)


@dataclass(frozen=True)
class CommandExecutionResult:
    command: Mapping[str, Any]
    ok: bool
    message: str
    robot_zone_after: str
    held_object_after: str | None
    sim_steps: int

    def to_command_log(self) -> dict[str, object]:
        return {
            **self.command,
            "ok": self.ok,
            "message": self.message,
            "robot_zone_after": self.robot_zone_after,
            "held_object_after": self.held_object_after,
            "sim_steps": self.sim_steps,
        }


@runtime_checkable
class RobotReplayController(Protocol):
    """Command execution boundary for stage replay, Isaac robot control, or DDS."""

    controller_name: str

    def execute(
        self,
        command: Mapping[str, Any],
        *,
        sim_steps: int,
    ) -> CommandExecutionResult:
        """Execute one compiled robot command and return validator-owned telemetry."""

    def to_artifact(
        self,
        *,
        adapter_name: str,
        action_count: int,
        step_count: int,
    ) -> PhysicsReplayArtifact:
        """Convert controller truth into the validator physics artifact schema."""


@dataclass
class StageReplayState:
    """Deterministic symbolic state used by the stage-level Isaac bridge."""

    room_id: str
    scene_root: str
    sim_seed: int | None
    robot_zone: str
    object_zones: dict[str, str]
    object_kinds: dict[str, str]
    object_targets: dict[str, str]
    object_prims: dict[str, str]
    surface_dirt_before: dict[str, float]
    surface_dirt_after: dict[str, float]
    surface_prims: dict[str, str]
    held_object_id: str | None = None

    @classmethod
    def from_bundle(cls, bundle_payload: Mapping[str, Any]) -> "StageReplayState":
        private_state = _mapping(bundle_payload["validator_private_state"])
        public_state = _mapping(bundle_payload["public_state"])
        scene_manifest = _mapping(bundle_payload["scene_manifest"])
        object_prims = {
            str(key): str(value)
            for key, value in _mapping(scene_manifest["object_prims"]).items()
        }
        surface_prims = {
            str(key): str(value)
            for key, value in _mapping(scene_manifest["surface_prims"]).items()
        }
        objects = tuple(_mapping(item) for item in private_state.get("objects", ()))
        surfaces = tuple(_mapping(item) for item in private_state.get("surfaces", ()))
        raw_seed = private_state.get("private_seed")
        return cls(
            room_id=str(bundle_payload["challenge_id"]),
            scene_root=str(scene_manifest["root_prim"]),
            sim_seed=None if raw_seed is None else int(raw_seed),
            robot_zone=str(public_state.get("robot_zone", private_state.get("robot_zone", "entry"))),
            object_zones={
                str(obj["object_id"]): str(obj["location"])
                for obj in objects
            },
            object_kinds={
                str(obj["object_id"]): str(obj["kind"])
                for obj in objects
            },
            object_targets={
                str(obj["object_id"]): str(obj["target_zone"])
                for obj in objects
            },
            object_prims=object_prims,
            surface_dirt_before={
                str(surface["zone"]): float(surface.get("dirt", 0.0))
                for surface in surfaces
            },
            surface_dirt_after={
                str(surface["zone"]): float(surface.get("dirt", 0.0))
                for surface in surfaces
            },
            surface_prims=surface_prims,
        )

    def apply_command(self, command: Mapping[str, Any]) -> tuple[bool, str]:
        command_type = str(command["command_type"])
        object_id = _optional_str(command.get("object_id"))
        zone = _optional_str(command.get("zone"))

        if command_type == "navigate_to_frame":
            if zone is None:
                return False, "missing navigation zone"
            self.robot_zone = zone
            return True, f"navigated to {zone}"

        if command_type == "approach_object":
            if object_id not in self.object_zones:
                return False, "unknown object"
            self.robot_zone = self.object_zones[object_id]
            return True, f"approached {object_id}"

        if command_type == "grasp_object":
            if object_id not in self.object_zones:
                return False, "unknown object"
            if self.held_object_id is not None:
                return False, "already holding object"
            if self.object_zones[object_id] != self.robot_zone:
                return False, "object not in robot zone"
            self.held_object_id = object_id
            self.object_zones[object_id] = "__held__"
            return True, f"grasped {object_id}"

        if command_type == "release_object":
            if zone is None:
                return False, "missing release zone"
            released_object = object_id or self.held_object_id
            if released_object is None:
                return False, "no object to release"
            if self.held_object_id is not None and released_object != self.held_object_id:
                return False, "release object is not held"
            self.object_zones[released_object] = zone
            self.held_object_id = None
            self.robot_zone = zone
            return True, f"released {released_object} in {zone}"

        if command_type == "drop_in_receptacle":
            dropped_object = object_id or self.held_object_id
            if dropped_object is None:
                return False, "no object to drop"
            if self.held_object_id is not None and dropped_object != self.held_object_id:
                return False, "drop object is not held"
            self.object_zones[dropped_object] = zone or "trash_bin"
            self.held_object_id = None
            self.robot_zone = zone or "trash_bin"
            return True, f"dropped {dropped_object} in {self.robot_zone}"

        if command_type == "wipe_surface":
            if zone is None or zone not in self.surface_dirt_after:
                return False, "unknown surface"
            self.surface_dirt_after[zone] = 0.0
            self.robot_zone = zone
            return True, f"wiped {zone}"

        if command_type == "hold_position":
            return True, "held position"

        return False, f"unsupported command {command_type}"

    def object_state(self, object_id: str) -> ObjectPhysicsState:
        zone = self.object_zones[object_id]
        x, y, z = pose_for_zone(zone if zone != "__held__" else self.robot_zone)
        return ObjectPhysicsState(
            object_id=object_id,
            prim_path=self.object_prims.get(object_id, ""),
            target_zone=self.object_targets[object_id],
            zone=None if zone == "__held__" else zone,
            position=Vector3(x=x, y=y, z=z),
            held=zone == "__held__",
        )

    def cleanliness(self, zone: str) -> CleanlinessMeasurement:
        dirt_before = self.surface_dirt_before[zone]
        dirt_after = self.surface_dirt_after[zone]
        cleaned = max(0.0, dirt_before - dirt_after)
        cleaned_fraction = 0.0 if dirt_before <= 0 else min(1.0, cleaned / dirt_before)
        return CleanlinessMeasurement(
            zone=zone,
            surface_prim=self.surface_prims.get(zone, ""),
            dirt_before=dirt_before,
            dirt_after=dirt_after,
            cleaned_area_fraction=cleaned_fraction,
        )


class StageReplayController:
    """Stage-backed controller used before the real Unitree/Isaac controller."""

    controller_name = "stage_replay_controller_v1"

    def __init__(self, state: StageReplayState) -> None:
        self.state = state
        self.command_log: list[dict[str, object]] = []

    @classmethod
    def from_bundle(cls, bundle_payload: Mapping[str, Any]) -> "StageReplayController":
        return cls(StageReplayState.from_bundle(bundle_payload))

    def execute(
        self,
        command: Mapping[str, Any],
        *,
        sim_steps: int,
    ) -> CommandExecutionResult:
        ok, message = self.state.apply_command(command)
        result = CommandExecutionResult(
            command=command,
            ok=ok,
            message=message,
            robot_zone_after=self.state.robot_zone,
            held_object_after=self.state.held_object_id,
            sim_steps=sim_steps,
        )
        self.command_log.append(result.to_command_log())
        return result

    def to_artifact(
        self,
        *,
        adapter_name: str,
        action_count: int,
        step_count: int,
    ) -> PhysicsReplayArtifact:
        return PhysicsReplayArtifact(
            adapter_name=adapter_name,
            room_id=self.state.room_id,
            scene_root=self.state.scene_root,
            sim_seed=self.state.sim_seed,
            time_step=1.0 / 60.0,
            step_count=step_count,
            action_count=action_count,
            robot_zone=self.state.robot_zone,
            invalid_actions=sum(
                1 for command in self.command_log if not bool(command.get("ok", True))
            ),
            object_states=tuple(
                self.state.object_state(object_id)
                for object_id in sorted(self.state.object_zones)
            ),
            cleanliness=tuple(
                self.state.cleanliness(zone)
                for zone in sorted(self.state.surface_dirt_after)
            ),
            command_log=tuple(self.command_log),
        )


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected mapping, got {type(value).__name__}")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
