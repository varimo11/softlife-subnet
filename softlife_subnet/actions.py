from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Iterator, Mapping, Sequence, Union


class ActionType(str, Enum):
    MOVE_TO_ZONE = "move_to_zone"
    MOVE_TO_OBJECT = "move_to_object"
    PICK = "pick"
    PLACE = "place"
    CLEAN_SURFACE = "clean_surface"
    DISPOSE = "dispose"
    WAIT = "wait"


@dataclass(frozen=True)
class Action:
    """Wire-friendly robot primitive used by miners and replayed by validators."""

    type: ActionType
    object_id: str | None = None
    zone: str | None = None

    @classmethod
    def move_to_zone(cls, zone: str) -> "Action":
        return cls(ActionType.MOVE_TO_ZONE, zone=zone)

    @classmethod
    def move_to_object(cls, object_id: str) -> "Action":
        return cls(ActionType.MOVE_TO_OBJECT, object_id=object_id)

    @classmethod
    def move_to(cls, target: str) -> "Action":
        """Backward-compatible alias for older demo trajectories.

        New miners should choose either ``move_to_zone`` or ``move_to_object``.
        """

        return cls.move_to_zone(target)

    @classmethod
    def pick(cls, object_id: str) -> "Action":
        return cls(ActionType.PICK, object_id=object_id)

    @classmethod
    def place(cls, object_id: str, zone: str) -> "Action":
        return cls(ActionType.PLACE, object_id=object_id, zone=zone)

    @classmethod
    def clean_surface(cls, zone: str) -> "Action":
        return cls(ActionType.CLEAN_SURFACE, zone=zone)

    @classmethod
    def dispose(cls, object_id: str | None = None) -> "Action":
        return cls(ActionType.DISPOSE, object_id=object_id)

    @classmethod
    def wait(cls) -> "Action":
        return cls(ActionType.WAIT)

    def to_wire(self) -> dict[str, str | None]:
        return {
            "type": self.type.value,
            "object_id": self.object_id,
            "zone": self.zone,
        }

    @classmethod
    def from_wire(cls, payload: Mapping[str, Any]) -> "Action":
        raw_type = str(payload["type"])
        if raw_type == "move_to":
            return cls.move_to_zone(str(payload.get("target") or payload.get("zone")))
        return cls(
            type=ActionType(raw_type),
            object_id=_optional_str(payload.get("object_id", payload.get("target"))),
            zone=_optional_str(payload.get("zone")),
        )

    @property
    def target(self) -> str | None:
        """Compatibility accessor for earlier mock actions."""

        return self.object_id or self.zone


@dataclass(frozen=True)
class Trajectory:
    """Canonical miner output: an ordered, JSON-serializable action sequence."""

    actions: tuple[Action, ...]

    def __iter__(self) -> Iterator[Action]:
        return iter(self.actions)

    def __len__(self) -> int:
        return len(self.actions)

    def __getitem__(self, index: int) -> Action:
        return self.actions[index]

    def to_wire(self) -> list[dict[str, str | None]]:
        return [action.to_wire() for action in self.actions]

    @classmethod
    def from_actions(cls, actions: Iterable[Action]) -> "Trajectory":
        return cls(tuple(actions))

    @classmethod
    def from_wire(cls, payload: Sequence[Mapping[str, Any]]) -> "Trajectory":
        return cls(tuple(Action.from_wire(item) for item in payload))


TrajectoryLike = Union[Trajectory, Sequence[Action]]


def ensure_trajectory(trajectory: TrajectoryLike) -> Trajectory:
    if isinstance(trajectory, Trajectory):
        return trajectory
    return Trajectory.from_actions(trajectory)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
