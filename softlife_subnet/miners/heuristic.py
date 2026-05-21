from __future__ import annotations

from dataclasses import dataclass

from softlife_subnet.actions import Action, Trajectory
from softlife_subnet.state import PublicRoomState


@dataclass(frozen=True)
class HeuristicMiner:
    """Baseline miner that plans only from public structured state."""

    miner_id: str = "heuristic_baseline"
    clean_threshold: float = 0.25

    def solve(self, public_state: PublicRoomState) -> Trajectory:
        actions: list[Action] = []

        visible_objects = sorted(
            public_state.objects,
            key=lambda obj: (obj.target_zone, obj.kind, obj.object_id),
        )
        for obj in visible_objects:
            if obj.location == obj.target_zone:
                continue
            actions.append(Action.move_to_object(obj.object_id))
            actions.append(Action.pick(obj.object_id))
            actions.append(Action.move_to_zone(obj.target_zone))
            if obj.kind == "trash" or obj.target_zone == "trash_bin":
                actions.append(Action.dispose(obj.object_id))
            else:
                actions.append(Action.place(obj.object_id, obj.target_zone))

        dirty_surfaces = sorted(
            (
                surface
                for surface in public_state.surfaces
                if surface.dirt_estimate >= self.clean_threshold
            ),
            key=lambda surface: (-surface.dirt_estimate, surface.zone),
        )
        for surface in dirty_surfaces:
            actions.extend(
                (
                    Action.move_to_zone(surface.zone),
                    Action.clean_surface(surface.zone),
                )
            )

        return Trajectory.from_actions(actions)


@dataclass(frozen=True)
class NoOpMiner:
    miner_id: str = "noop"

    def solve(self, public_state: PublicRoomState) -> Trajectory:
        return Trajectory.from_actions(())
