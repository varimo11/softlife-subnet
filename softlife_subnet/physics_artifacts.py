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


@dataclass(frozen=True)
class Quaternion:
    x: float
    y: float
    z: float
    w: float

    def to_wire(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z, "w": self.w}


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
    object_states: tuple[ObjectPhysicsState, ...]
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
            "object_states": [obj.to_public_summary() for obj in self.object_states],
            "cleanliness": [item.to_public_summary() for item in self.cleanliness],
            "collision_count": len(self.collisions),
            "forbidden_collision_count": sum(
                1 for item in self.collisions if item.forbidden_contact
            ),
            "damage_events": [item.to_wire() for item in self.damage_events],
            "dropped_objects": [item.to_wire() for item in self.dropped_objects],
        }


ReplayArtifact = PhysicsReplayArtifact


def _wire_or_none(value: Any) -> dict[str, object] | None:
    if value is None:
        return None
    return value.to_wire()
