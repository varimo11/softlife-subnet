from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Mapping, Protocol, runtime_checkable

from softlife_subnet.actions import Action, ActionType, Trajectory, TrajectoryLike, ensure_trajectory
from softlife_subnet.state import (
    HELD_LOCATION,
    EnvironmentState,
    ObjectState,
    SurfaceState,
    clamp01,
)


@runtime_checkable
class SimulationAdapter(Protocol):
    """Replay adapter boundary for mock physics, Isaac Sim, or hardware logs."""

    adapter_name: str

    def replay(
        self,
        environment_state: EnvironmentState,
        trajectory: TrajectoryLike,
    ) -> "ReplayResult":
        """Replay a miner trajectory inside validator-owned environment truth."""


@dataclass(frozen=True)
class ReplayEvent:
    action_index: int
    action: Action
    ok: bool
    message: str
    robot_zone_after: str
    held_object_after: str | None

    def to_wire(self) -> dict[str, object]:
        return {
            "action_index": self.action_index,
            "action": self.action.to_wire(),
            "ok": self.ok,
            "message": self.message,
            "robot_zone_after": self.robot_zone_after,
            "held_object_after": self.held_object_after,
        }


@dataclass(frozen=True)
class ReplayResult:
    """Validator-internal replay result.

    The final environment state remains validator-private. ``to_replay_log`` is
    the public-safe replay summary used by demos and future audit tooling.
    """

    initial_state: EnvironmentState
    final_state: EnvironmentState
    events: tuple[ReplayEvent, ...]
    invalid_actions: int
    action_count: int
    replay_hash: str
    adapter_name: str

    def to_replay_log(self) -> dict[str, object]:
        return {
            "adapter_name": self.adapter_name,
            "replay_hash": self.replay_hash,
            "action_count": self.action_count,
            "invalid_actions": self.invalid_actions,
            "events": [event.to_wire() for event in self.events],
        }


@dataclass(frozen=True)
class MockSimulationAdapter:
    """Deterministic symbolic physics for the MVP validator."""

    clean_power: float = 0.62
    stubborn_clean_power: float = 0.38
    adapter_name: str = "mock_symbolic_v1"

    def replay(
        self,
        environment_state: EnvironmentState,
        trajectory: TrajectoryLike,
    ) -> ReplayResult:
        canonical_trajectory = ensure_trajectory(trajectory)
        robot_zone = environment_state.robot_zone
        held_object_id: str | None = None
        objects = {obj.object_id: obj for obj in environment_state.objects}
        surfaces = {surface.zone: surface for surface in environment_state.surfaces}
        zones = set(environment_state.zones)

        events: list[ReplayEvent] = []
        invalid_actions = 0

        for index, action in enumerate(canonical_trajectory):
            ok, message = self._apply_action(
                action=action,
                robot_zone=robot_zone,
                held_object_id=held_object_id,
                objects=objects,
                surfaces=surfaces,
                zones=zones,
            )

            if ok:
                robot_zone, held_object_id = self._commit_action(
                    action=action,
                    robot_zone=robot_zone,
                    held_object_id=held_object_id,
                    objects=objects,
                    surfaces=surfaces,
                    zones=zones,
                )
            else:
                invalid_actions += 1

            events.append(
                ReplayEvent(
                    action_index=index,
                    action=action,
                    ok=ok,
                    message=message,
                    robot_zone_after=robot_zone,
                    held_object_after=held_object_id,
                )
            )

        final_state = replace(
            environment_state,
            robot_zone=robot_zone,
            objects=tuple(objects[obj.object_id] for obj in environment_state.objects),
            surfaces=tuple(surfaces[surface.zone] for surface in environment_state.surfaces),
        )
        replay_hash = _hash_replay_log(self.adapter_name, events)
        return ReplayResult(
            initial_state=environment_state,
            final_state=final_state,
            events=tuple(events),
            invalid_actions=invalid_actions,
            action_count=len(canonical_trajectory),
            replay_hash=replay_hash,
            adapter_name=self.adapter_name,
        )

    def _apply_action(
        self,
        action: Action,
        robot_zone: str,
        held_object_id: str | None,
        objects: Mapping[str, ObjectState],
        surfaces: Mapping[str, SurfaceState],
        zones: set[str],
    ) -> tuple[bool, str]:
        if action.type == ActionType.WAIT:
            return True, "wait"

        if action.type == ActionType.MOVE_TO_ZONE:
            if action.zone not in zones:
                return False, "unknown move zone"
            return True, f"moved to zone {action.zone}"

        if action.type == ActionType.MOVE_TO_OBJECT:
            if action.object_id is None or action.object_id not in objects:
                return False, "unknown move object"
            obj = objects[action.object_id]
            if obj.location == HELD_LOCATION:
                return False, "object is currently held"
            return True, f"moved to object {action.object_id}"

        if action.type == ActionType.PICK:
            if action.object_id is None or action.object_id not in objects:
                return False, "unknown object"
            if held_object_id is not None:
                return False, "gripper already occupied"
            obj = objects[action.object_id]
            if obj.location != robot_zone:
                return False, "object is not reachable"
            return True, f"picked {action.object_id}"

        if action.type == ActionType.PLACE:
            if action.zone not in zones:
                return False, "unknown place zone"
            if held_object_id is None:
                return False, "no object held"
            if action.object_id is not None and action.object_id != held_object_id:
                return False, "place target is not held"
            if robot_zone != action.zone:
                return False, "robot is not at place zone"
            return True, f"placed {held_object_id} in {action.zone}"

        if action.type == ActionType.CLEAN_SURFACE:
            if action.zone not in surfaces:
                return False, "unknown surface"
            if robot_zone != action.zone:
                return False, "surface is not reachable"
            return True, f"cleaned {action.zone}"

        if action.type == ActionType.DISPOSE:
            if held_object_id is None:
                return False, "no object held"
            if action.object_id is not None and action.object_id != held_object_id:
                return False, "dispose target is not held"
            held_object = objects[held_object_id]
            if "disposable" not in held_object.traits and held_object.kind != "trash":
                return False, "held object is not disposable"
            if robot_zone != "trash_bin":
                return False, "robot is not at trash bin"
            return True, f"disposed {held_object_id}"

        return False, "unsupported action"

    def _commit_action(
        self,
        action: Action,
        robot_zone: str,
        held_object_id: str | None,
        objects: dict[str, ObjectState],
        surfaces: dict[str, SurfaceState],
        zones: set[str],
    ) -> tuple[str, str | None]:
        if action.type == ActionType.MOVE_TO_ZONE and action.zone in zones:
            return action.zone, held_object_id

        if action.type == ActionType.MOVE_TO_OBJECT and action.object_id in objects:
            return objects[action.object_id].location, held_object_id

        if action.type == ActionType.PICK and action.object_id is not None:
            objects[action.object_id] = replace(
                objects[action.object_id],
                location=HELD_LOCATION,
            )
            return robot_zone, action.object_id

        if action.type == ActionType.PLACE and action.zone is not None and held_object_id:
            objects[held_object_id] = replace(objects[held_object_id], location=action.zone)
            return robot_zone, None

        if action.type == ActionType.DISPOSE and held_object_id:
            objects[held_object_id] = replace(objects[held_object_id], location="trash_bin")
            return robot_zone, None

        if action.type == ActionType.CLEAN_SURFACE and action.zone is not None:
            surface = surfaces[action.zone]
            clean_power = (
                self.stubborn_clean_power
                if "stubborn_dirt" in surface.traits
                else self.clean_power
            )
            surfaces[action.zone] = replace(surface, dirt=clamp01(surface.dirt - clean_power))
            return robot_zone, held_object_id

        return robot_zone, held_object_id


def _hash_replay_log(adapter_name: str, events: list[ReplayEvent]) -> str:
    payload = {
        "adapter_name": adapter_name,
        "events": [event.to_wire() for event in events],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


SimulationEvent = ReplayEvent
SimulationResult = ReplayResult
RoomSimulator = MockSimulationAdapter
