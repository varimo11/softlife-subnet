from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from softlife_subnet.state import EnvironmentState, ObjectState, SurfaceState


ZONES: tuple[str, ...] = (
    "entry",
    "floor",
    "bed",
    "nightstand",
    "desk",
    "bathroom_counter",
    "hamper",
    "closet",
    "trash_bin",
)

OBJECT_CATALOG: tuple[tuple[str, str, str], ...] = (
    ("towel_1", "towel", "hamper"),
    ("pillow_1", "pillow", "bed"),
    ("pillow_2", "pillow", "bed"),
    ("mug_1", "mug", "desk"),
    ("remote_1", "remote", "nightstand"),
    ("shoes_1", "shoes", "closet"),
    ("wrapper_1", "trash", "trash_bin"),
    ("soap_1", "toiletry", "bathroom_counter"),
)

SURFACE_ZONES: tuple[str, ...] = ("floor", "bed", "nightstand", "desk", "bathroom_counter")


@dataclass(frozen=True)
class RoomGenerator:
    """Creates hidden validator scenarios from deterministic seeds."""

    task_name: str = "restore_hotel_room"
    hidden_object_probability: float = 0.18
    hidden_surface_probability: float = 0.22

    def generate(self, seed: int) -> EnvironmentState:
        rng = random.Random(seed)
        room_id = _room_id(seed)

        objects: list[ObjectState] = []
        for object_id, kind, target_zone in OBJECT_CATALOG:
            location = _messy_location(rng, target_zone)
            visible = rng.random() >= self.hidden_object_probability
            traits = _object_traits(rng, kind)
            objects.append(
                ObjectState(
                    object_id=object_id,
                    kind=kind,
                    location=location,
                    target_zone=target_zone,
                    visible=visible,
                    traits=traits,
                )
            )

        surfaces: list[SurfaceState] = []
        for zone in SURFACE_ZONES:
            dirt = rng.uniform(0.12, 0.92)
            visible = rng.random() >= self.hidden_surface_probability
            traits = ("stubborn_dirt",) if rng.random() < 0.2 else ()
            surfaces.append(SurfaceState(zone=zone, dirt=dirt, visible=visible, traits=traits))

        return EnvironmentState(
            room_id=room_id,
            task_name=self.task_name,
            private_seed=seed,
            robot_zone="entry",
            zones=ZONES,
            objects=tuple(objects),
            surfaces=tuple(surfaces),
        )


def _room_id(seed: int) -> str:
    digest = hashlib.sha256(f"softlife-room:{seed}".encode("utf-8")).hexdigest()
    return f"room_{digest[:12]}"


def _messy_location(rng: random.Random, target_zone: str) -> str:
    if rng.random() < 0.2:
        return target_zone
    candidates = [zone for zone in ZONES if zone != target_zone]
    return rng.choice(candidates)


def _object_traits(rng: random.Random, kind: str) -> tuple[str, ...]:
    traits: list[str] = []
    if kind in {"mug", "remote", "toiletry"} and rng.random() < 0.25:
        traits.append("fragile")
    if kind == "trash":
        traits.append("disposable")
    return tuple(traits)
