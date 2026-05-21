from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from softlife_subnet.actions import Action, Trajectory, ensure_trajectory
from softlife_subnet.leaderboard import Leaderboard
from softlife_subnet.miners import HeuristicMiner, NoOpMiner
from softlife_subnet.room_generator import RoomGenerator
from softlife_subnet.scoring import RoomReadinessScorer
from softlife_subnet.simulation import MockSimulationAdapter, ReplayResult
from softlife_subnet.state import HELD_LOCATION, EnvironmentState, ObjectState, SurfaceState
from softlife_subnet.validators import EvaluationResult, Validator


ROOM_LAYOUT: dict[str, dict[str, int | str]] = {
    "entry": {"label": "Entry", "x": 3, "y": 70, "w": 18, "h": 24},
    "floor": {"label": "Open Floor", "x": 24, "y": 40, "w": 30, "h": 35},
    "bed": {"label": "Bed", "x": 57, "y": 8, "w": 36, "h": 32},
    "nightstand": {"label": "Nightstand", "x": 44, "y": 9, "w": 11, "h": 20},
    "desk": {"label": "Desk", "x": 6, "y": 8, "w": 28, "h": 24},
    "bathroom_counter": {"label": "Bath Counter", "x": 5, "y": 38, "w": 17, "h": 25},
    "hamper": {"label": "Hamper", "x": 75, "y": 47, "w": 16, "h": 19},
    "closet": {"label": "Closet", "x": 57, "y": 69, "w": 17, "h": 22},
    "trash_bin": {"label": "Trash Bin", "x": 80, "y": 72, "w": 13, "h": 18},
}

OBJECT_LABELS = {
    "towel": "Towel",
    "pillow": "Pillow",
    "mug": "Cup",
    "remote": "Remote",
    "shoes": "Shoes",
    "trash": "Trash",
    "toiletry": "Bottle",
}

OBJECT_SHORT_LABELS = {
    "towel": "TWL",
    "pillow": "PIL",
    "mug": "CUP",
    "remote": "REM",
    "shoes": "SHO",
    "trash": "TRS",
    "toiletry": "BTL",
}


@dataclass(frozen=True)
class VisualMinerRun:
    miner_id: str
    trajectory: Trajectory
    final_replay: ReplayResult
    evaluation: EvaluationResult


def build_visual_demo(seed: int = 42) -> dict[str, Any]:
    generator = RoomGenerator()
    adapter = MockSimulationAdapter()
    scorer = RoomReadinessScorer()
    validator = Validator(
        generator=generator,
        simulation_adapter=adapter,
        scorer=scorer,
    )
    environment = generator.generate(seed)
    challenge = validator.issue_challenge(seed)
    public_state = challenge.public_state
    miners = (HeuristicMiner(), NoOpMiner())

    runs: list[VisualMinerRun] = []
    leaderboard = Leaderboard()
    leaderboard_snapshots: list[dict[str, Any]] = []
    for miner in miners:
        trajectory = ensure_trajectory(miner.solve(public_state))
        final_replay = adapter.replay(environment, trajectory)
        evaluation = validator.evaluate(
            challenge.challenge_id,
            miner.miner_id,
            trajectory,
        )
        runs.append(
            VisualMinerRun(
                miner_id=miner.miner_id,
                trajectory=trajectory,
                final_replay=final_replay,
                evaluation=evaluation,
            )
        )
        leaderboard.update(evaluation)
        leaderboard_snapshots.append(
            {
                "after_miner": miner.miner_id,
                "ranking": list(leaderboard.ranking_with_weights()),
                "weights": leaderboard.normalized_weights(),
            }
        )

    active_run = runs[0]
    timeline = _build_timeline(
        environment=environment,
        trajectory=active_run.trajectory,
        adapter=adapter,
        scorer=scorer,
    )

    miner_payloads = []
    for run in runs:
        miner_payloads.append(
            {
                "miner_id": run.miner_id,
                "trajectory": run.trajectory.to_wire(),
                "trajectory_hash": run.evaluation.trajectory_hash,
                "score": run.evaluation.score.to_wire(),
                "replay": run.evaluation.replay_summary.to_wire(),
                "action_count": run.evaluation.action_count,
                "invalid_actions": run.evaluation.invalid_actions,
            }
        )

    return {
        "seed": seed,
        "task_name": environment.task_name,
        "challenge_id": challenge.challenge_id,
        "adapter": adapter.adapter_name,
        "layout": _layout_payload(environment),
        "hidden_room": environment.private_summary(),
        "public_state": public_state.to_wire(),
        "objects": [_object_payload(obj) for obj in environment.objects],
        "surfaces": [_surface_payload(surface) for surface in environment.surfaces],
        "miners": miner_payloads,
        "active_miner_id": active_run.miner_id,
        "timeline": timeline,
        "leaderboard": list(leaderboard.ranking_with_weights()),
        "leaderboard_snapshots": leaderboard_snapshots,
        "weights": leaderboard.normalized_weights(),
    }


def _build_timeline(
    environment: EnvironmentState,
    trajectory: Trajectory,
    adapter: MockSimulationAdapter,
    scorer: RoomReadinessScorer,
) -> list[dict[str, Any]]:
    actions = tuple(trajectory)
    frames: list[dict[str, Any]] = []

    for step in range(len(actions) + 1):
        prefix = Trajectory.from_actions(actions[:step])
        replay = adapter.replay(environment, prefix)
        previous_event = replay.events[-1].to_wire() if replay.events else None
        previous_action = actions[step - 1].to_wire() if step > 0 else None
        frames.append(
            {
                "step": step,
                "total_steps": len(actions),
                "action": previous_action,
                "event": previous_event,
                "robot_zone": replay.final_state.robot_zone,
                "held_object_id": _held_object_id(replay),
                "objects": [
                    _object_frame_payload(obj, replay.final_state.robot_zone)
                    for obj in replay.final_state.objects
                ],
                "surfaces": [
                    _surface_payload(surface)
                    for surface in replay.final_state.surfaces
                ],
                "score": scorer.score(replay).to_wire(),
                "invalid_actions": replay.invalid_actions,
                "action_count": replay.action_count,
                "replay_hash": replay.replay_hash,
            }
        )

    return frames


def _layout_payload(environment: EnvironmentState) -> list[dict[str, int | str]]:
    return [
        {"zone": zone, **ROOM_LAYOUT[zone]}
        for zone in environment.zones
        if zone in ROOM_LAYOUT
    ]


def _object_payload(obj: ObjectState) -> dict[str, Any]:
    return {
        "object_id": obj.object_id,
        "kind": obj.kind,
        "display_kind": OBJECT_LABELS.get(obj.kind, obj.kind.title()),
        "short_label": OBJECT_SHORT_LABELS.get(obj.kind, obj.kind[:3].upper()),
        "location": obj.location,
        "target_zone": obj.target_zone,
        "visible_to_miner": obj.visible,
        "traits": list(obj.traits),
    }


def _object_frame_payload(obj: ObjectState, robot_zone: str) -> dict[str, Any]:
    payload = _object_payload(obj)
    payload["held"] = obj.location == HELD_LOCATION
    payload["display_zone"] = robot_zone if obj.location == HELD_LOCATION else obj.location
    payload["at_target"] = obj.location == obj.target_zone
    return payload


def _surface_payload(surface: SurfaceState) -> dict[str, Any]:
    return {
        "zone": surface.zone,
        "dirt": round(surface.dirt, 4),
        "visible_to_miner": surface.visible,
        "traits": list(surface.traits),
    }


def _held_object_id(replay: ReplayResult) -> str | None:
    if not replay.events:
        return None
    return replay.events[-1].held_object_after

