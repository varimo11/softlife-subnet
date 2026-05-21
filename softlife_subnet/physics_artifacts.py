from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping


SCHEMA_VERSION = "softlife.physics_replay.v1"


@dataclass(frozen=True)
class Vector3:
    x: float
    y: float
    z: float

    def to_wire(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any] | None) -> "Vector3 | None":
        if payload is None:
            return None
        return cls(x=float(payload["x"]), y=float(payload["y"]), z=float(payload["z"]))


@dataclass(frozen=True)
class Quaternion:
    x: float
    y: float
    z: float
    w: float

    def to_wire(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z, "w": self.w}

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any] | None) -> "Quaternion | None":
        if payload is None:
            return None
        return cls(
            x=float(payload["x"]),
            y=float(payload["y"]),
            z=float(payload["z"]),
            w=float(payload["w"]),
        )


@dataclass(frozen=True)
class ObjectPhysicsState:
    object_id: str
    prim_path: str
    target_zone: str
    zone: str | None
    position: Vector3 | None = None
    orientation_xyzw: Quaternion | None = None
    linear_velocity: Vector3 | None = None
    angular_velocity: Vector3 | None = None
    at_rest: bool = True
    held: bool = False
    damaged: bool = False

    def to_private_wire(self) -> dict[str, object]:
        return {
            "object_id": self.object_id,
            "prim_path": self.prim_path,
            "target_zone": self.target_zone,
            "zone": self.zone,
            "position": _wire_or_none(self.position),
            "orientation_xyzw": _wire_or_none(self.orientation_xyzw),
            "linear_velocity": _wire_or_none(self.linear_velocity),
            "angular_velocity": _wire_or_none(self.angular_velocity),
            "at_rest": self.at_rest,
            "held": self.held,
            "damaged": self.damaged,
        }

    def to_public_summary(self) -> dict[str, object]:
        return {
            "object_id": self.object_id,
            "target_zone": self.target_zone,
            "zone": self.zone,
            "at_rest": self.at_rest,
            "held": self.held,
            "damaged": self.damaged,
        }

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "ObjectPhysicsState":
        return cls(
            object_id=str(payload["object_id"]),
            prim_path=str(payload["prim_path"]),
            target_zone=str(payload["target_zone"]),
            zone=_optional_str(payload.get("zone")),
            position=Vector3.from_wire(_optional_mapping(payload.get("position"))),
            orientation_xyzw=Quaternion.from_wire(
                _optional_mapping(payload.get("orientation_xyzw"))
            ),
            linear_velocity=Vector3.from_wire(_optional_mapping(payload.get("linear_velocity"))),
            angular_velocity=Vector3.from_wire(
                _optional_mapping(payload.get("angular_velocity"))
            ),
            at_rest=bool(payload.get("at_rest", True)),
            held=bool(payload.get("held", False)),
            damaged=bool(payload.get("damaged", False)),
        )


@dataclass(frozen=True)
class CollisionEvent:
    step: int
    body_a: str
    body_b: str
    impulse: float
    forbidden_contact: bool = False

    def to_private_wire(self) -> dict[str, object]:
        return {
            "step": self.step,
            "body_a": self.body_a,
            "body_b": self.body_b,
            "impulse": self.impulse,
            "forbidden_contact": self.forbidden_contact,
        }

    def to_public_summary(self) -> dict[str, object]:
        return {
            "step": self.step,
            "impulse": self.impulse,
            "forbidden_contact": self.forbidden_contact,
        }

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "CollisionEvent":
        return cls(
            step=int(payload["step"]),
            body_a=str(payload["body_a"]),
            body_b=str(payload["body_b"]),
            impulse=float(payload["impulse"]),
            forbidden_contact=bool(payload.get("forbidden_contact", False)),
        )


@dataclass(frozen=True)
class DamageEvent:
    step: int
    object_id: str
    reason: str
    severity: float

    def to_wire(self) -> dict[str, object]:
        return {
            "step": self.step,
            "object_id": self.object_id,
            "reason": self.reason,
            "severity": self.severity,
        }

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "DamageEvent":
        return cls(
            step=int(payload["step"]),
            object_id=str(payload["object_id"]),
            reason=str(payload["reason"]),
            severity=float(payload["severity"]),
        )


@dataclass(frozen=True)
class DroppedObjectEvent:
    step: int
    object_id: str
    zone: str | None
    drop_height: float | None = None

    def to_wire(self) -> dict[str, object]:
        return {
            "step": self.step,
            "object_id": self.object_id,
            "zone": self.zone,
            "drop_height": self.drop_height,
        }

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "DroppedObjectEvent":
        raw_drop_height = payload.get("drop_height")
        return cls(
            step=int(payload["step"]),
            object_id=str(payload["object_id"]),
            zone=_optional_str(payload.get("zone")),
            drop_height=None if raw_drop_height is None else float(raw_drop_height),
        )


@dataclass(frozen=True)
class CleanlinessMeasurement:
    zone: str
    surface_prim: str
    dirt_before: float
    dirt_after: float
    cleaned_area_fraction: float

    def to_private_wire(self) -> dict[str, object]:
        return {
            "zone": self.zone,
            "surface_prim": self.surface_prim,
            "dirt_before": self.dirt_before,
            "dirt_after": self.dirt_after,
            "cleaned_area_fraction": self.cleaned_area_fraction,
        }

    def to_public_summary(self) -> dict[str, object]:
        return {
            "zone": self.zone,
            "dirt_after": self.dirt_after,
            "cleaned_area_fraction": self.cleaned_area_fraction,
        }

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "CleanlinessMeasurement":
        return cls(
            zone=str(payload["zone"]),
            surface_prim=str(payload["surface_prim"]),
            dirt_before=float(payload["dirt_before"]),
            dirt_after=float(payload["dirt_after"]),
            cleaned_area_fraction=float(payload["cleaned_area_fraction"]),
        )


@dataclass(frozen=True)
class PhysicsReplayArtifact:
    """Validator-private physics truth produced by Isaac or hardware replay.

    `to_public_summary` redacts simulator paths and private seeds for playground
    displays. Hidden validators should keep `to_private_wire` internal.
    """

    adapter_name: str
    room_id: str
    scene_root: str
    sim_seed: int | None
    time_step: float
    step_count: int
    action_count: int
    robot_zone: str | None
    object_states: tuple[ObjectPhysicsState, ...]
    invalid_actions: int = 0
    cleanliness: tuple[CleanlinessMeasurement, ...] = ()
    collisions: tuple[CollisionEvent, ...] = ()
    damage_events: tuple[DamageEvent, ...] = ()
    dropped_objects: tuple[DroppedObjectEvent, ...] = ()
    command_log: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    schema_version: str = SCHEMA_VERSION

    @property
    def artifact_hash(self) -> str:
        payload = self.to_private_wire(include_hash=False)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_private_wire(self, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "room_id": self.room_id,
            "scene_root": self.scene_root,
            "sim_seed": self.sim_seed,
            "time_step": self.time_step,
            "step_count": self.step_count,
            "action_count": self.action_count,
            "invalid_actions": self.invalid_actions,
            "robot_zone": self.robot_zone,
            "object_states": [obj.to_private_wire() for obj in self.object_states],
            "cleanliness": [item.to_private_wire() for item in self.cleanliness],
            "collisions": [item.to_private_wire() for item in self.collisions],
            "damage_events": [item.to_wire() for item in self.damage_events],
            "dropped_objects": [item.to_wire() for item in self.dropped_objects],
            "command_log": [dict(item) for item in self.command_log],
        }
        if include_hash:
            payload["artifact_hash"] = self.artifact_hash
        return payload

    def to_public_summary(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "adapter_name": self.adapter_name,
            "room_id": self.room_id,
            "artifact_hash": self.artifact_hash,
            "step_count": self.step_count,
            "action_count": self.action_count,
            "invalid_actions": self.invalid_actions,
            "robot_zone": self.robot_zone,
            "object_states": [obj.to_public_summary() for obj in self.object_states],
            "cleanliness": [item.to_public_summary() for item in self.cleanliness],
            "collision_count": len(self.collisions),
            "forbidden_collision_count": sum(
                1 for item in self.collisions if item.forbidden_contact
            ),
            "damage_events": [item.to_wire() for item in self.damage_events],
            "dropped_objects": [item.to_wire() for item in self.dropped_objects],
        }

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "PhysicsReplayArtifact":
        schema_version = str(payload["schema_version"])
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported physics replay schema: {schema_version}")
        raw_seed = payload.get("sim_seed")
        artifact = cls(
            adapter_name=str(payload["adapter_name"]),
            room_id=str(payload["room_id"]),
            scene_root=str(payload["scene_root"]),
            sim_seed=None if raw_seed is None else int(raw_seed),
            time_step=float(payload["time_step"]),
            step_count=int(payload["step_count"]),
            action_count=int(payload.get("action_count", payload["step_count"])),
            robot_zone=_optional_str(payload.get("robot_zone")),
            invalid_actions=int(payload.get("invalid_actions", 0)),
            object_states=tuple(
                ObjectPhysicsState.from_wire(_require_mapping(item))
                for item in payload.get("object_states", ())
            ),
            cleanliness=tuple(
                CleanlinessMeasurement.from_wire(_require_mapping(item))
                for item in payload.get("cleanliness", ())
            ),
            collisions=tuple(
                CollisionEvent.from_wire(_require_mapping(item))
                for item in payload.get("collisions", ())
            ),
            damage_events=tuple(
                DamageEvent.from_wire(_require_mapping(item))
                for item in payload.get("damage_events", ())
            ),
            dropped_objects=tuple(
                DroppedObjectEvent.from_wire(_require_mapping(item))
                for item in payload.get("dropped_objects", ())
            ),
            command_log=tuple(
                _require_mapping(item) for item in payload.get("command_log", ())
            ),
            schema_version=schema_version,
        )
        expected_hash = payload.get("artifact_hash")
        if expected_hash is not None and str(expected_hash) != artifact.artifact_hash:
            raise ValueError("physics replay artifact hash mismatch")
        return artifact


ReplayArtifact = PhysicsReplayArtifact


def _wire_or_none(value: Any) -> dict[str, object] | None:
    if value is None:
        return None
    return value.to_wire()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    return _require_mapping(value)


def _require_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected mapping payload, got {type(value).__name__}")
    return value
