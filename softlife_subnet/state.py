from __future__ import annotations

from dataclasses import dataclass
from typing import Any


HELD_LOCATION = "__held__"


@dataclass(frozen=True)
class PublicObjectState:
    object_id: str
    kind: str
    location: str
    target_zone: str

    def to_wire(self) -> dict[str, str]:
        return {
            "object_id": self.object_id,
            "kind": self.kind,
            "location": self.location,
            "target_zone": self.target_zone,
        }


@dataclass(frozen=True)
class PublicSurfaceState:
    zone: str
    dirt_estimate: float

    def to_wire(self) -> dict[str, str | float]:
        return {"zone": self.zone, "dirt_estimate": self.dirt_estimate}


@dataclass(frozen=True)
class PublicRoomState:
    """Miner-visible task state.

    This contract deliberately excludes private seeds, hidden objects, exact
    dirt values for occluded surfaces, and any simulator handle.
    """

    room_id: str
    task_name: str
    robot_zone: str
    zones: tuple[str, ...]
    objects: tuple[PublicObjectState, ...]
    surfaces: tuple[PublicSurfaceState, ...]

    def to_wire(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "task_name": self.task_name,
            "robot_zone": self.robot_zone,
            "zones": list(self.zones),
            "objects": [obj.to_wire() for obj in self.objects],
            "surfaces": [surface.to_wire() for surface in self.surfaces],
        }


@dataclass(frozen=True)
class ObjectState:
    object_id: str
    kind: str
    location: str
    target_zone: str
    visible: bool
    traits: tuple[str, ...] = ()

    def public_view(self) -> PublicObjectState | None:
        if not self.visible:
            return None
        return PublicObjectState(
            object_id=self.object_id,
            kind=self.kind,
            location=self.location,
            target_zone=self.target_zone,
        )


@dataclass(frozen=True)
class SurfaceState:
    zone: str
    dirt: float
    visible: bool
    traits: tuple[str, ...] = ()

    def public_view(self) -> PublicSurfaceState | None:
        if not self.visible:
            return None
        return PublicSurfaceState(zone=self.zone, dirt_estimate=quantize_dirt(self.dirt))


@dataclass(frozen=True)
class EnvironmentState:
    """Validator-private simulation truth.

    This object is the future Isaac Sim/ROS2 bridge point. It can contain exact
    simulator facts, hidden objects, private randomization metadata, and scoring
    state. Miners should only ever see ``PublicRoomState``.
    """

    room_id: str
    task_name: str
    private_seed: int
    robot_zone: str
    zones: tuple[str, ...]
    objects: tuple[ObjectState, ...]
    surfaces: tuple[SurfaceState, ...]

    def to_public(self) -> PublicRoomState:
        objects = tuple(
            view for obj in self.objects if (view := obj.public_view()) is not None
        )
        surfaces = tuple(
            view
            for surface in self.surfaces
            if (view := surface.public_view()) is not None
        )
        return PublicRoomState(
            room_id=self.room_id,
            task_name=self.task_name,
            robot_zone=self.robot_zone,
            zones=self.zones,
            objects=objects,
            surfaces=surfaces,
        )

    def private_summary(self, include_seed: bool = False) -> dict[str, Any]:
        """Validator-only debug summary for local demos and audits."""

        summary: dict[str, Any] = {
            "room_id": self.room_id,
            "task_name": self.task_name,
            "robot_zone": self.robot_zone,
            "object_count": len(self.objects),
            "visible_object_count": sum(1 for obj in self.objects if obj.visible),
            "hidden_object_count": sum(1 for obj in self.objects if not obj.visible),
            "surface_count": len(self.surfaces),
            "visible_surface_count": sum(1 for surface in self.surfaces if surface.visible),
            "hidden_surface_count": sum(1 for surface in self.surfaces if not surface.visible),
            "objects": [
                {
                    "object_id": obj.object_id,
                    "kind": obj.kind,
                    "location": obj.location,
                    "target_zone": obj.target_zone,
                    "visible_to_miner": obj.visible,
                    "traits": list(obj.traits),
                }
                for obj in self.objects
            ],
            "surfaces": [
                {
                    "zone": surface.zone,
                    "dirt": round(surface.dirt, 4),
                    "visible_to_miner": surface.visible,
                    "traits": list(surface.traits),
                }
                for surface in self.surfaces
            ],
        }
        if include_seed:
            summary["private_seed"] = self.private_seed
        return summary


RoomState = EnvironmentState


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def quantize_dirt(dirt: float) -> float:
    return round(round(clamp01(dirt) * 4) / 4, 2)
