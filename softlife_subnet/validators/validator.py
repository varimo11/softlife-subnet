from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass

from softlife_subnet.actions import TrajectoryLike, ensure_trajectory
from softlife_subnet.room_generator import RoomGenerator
from softlife_subnet.scoring import EvaluationScore, RoomReadinessScorer
from softlife_subnet.simulation import (
    MockSimulationAdapter,
    ReplayEvent,
    SimulationAdapter,
)
from softlife_subnet.state import EnvironmentState, PublicRoomState


@dataclass(frozen=True)
class Challenge:
    """Miner-facing challenge envelope.

    The challenge intentionally contains no validator seed, simulator state,
    hidden objects, exact dirt values for hidden surfaces, or replay handles.
    """

    challenge_id: str
    public_state: PublicRoomState

    def to_wire(self) -> dict[str, object]:
        return {
            "challenge_id": self.challenge_id,
            "public_state": self.public_state.to_wire(),
        }


@dataclass(frozen=True)
class ReplaySummary:
    adapter_name: str
    replay_hash: str
    action_count: int
    invalid_actions: int
    events: tuple[ReplayEvent, ...]

    def to_wire(self) -> dict[str, object]:
        return {
            "adapter_name": self.adapter_name,
            "replay_hash": self.replay_hash,
            "action_count": self.action_count,
            "invalid_actions": self.invalid_actions,
            "events": [event.to_wire() for event in self.events],
        }


@dataclass(frozen=True)
class EvaluationResult:
    challenge_id: str
    miner_id: str
    trajectory_hash: str
    score: EvaluationScore
    replay_summary: ReplaySummary

    @property
    def invalid_actions(self) -> int:
        return self.replay_summary.invalid_actions

    @property
    def action_count(self) -> int:
        return self.replay_summary.action_count

    def to_wire(self) -> dict[str, object]:
        return {
            "challenge_id": self.challenge_id,
            "miner_id": self.miner_id,
            "trajectory_hash": self.trajectory_hash,
            "score": self.score.to_wire(),
            "replay_log": self.replay_summary.to_wire(),
            "invalid_actions": self.invalid_actions,
            "action_count": self.action_count,
        }


class Validator:
    """Owns hidden room truth, deterministic replay, and scoring."""

    def __init__(
        self,
        generator: RoomGenerator | None = None,
        simulation_adapter: SimulationAdapter | None = None,
        simulator: SimulationAdapter | None = None,
        scorer: RoomReadinessScorer | None = None,
    ) -> None:
        self._generator = generator or RoomGenerator()
        self._simulation_adapter = simulation_adapter or simulator or MockSimulationAdapter()
        self._scorer = scorer or RoomReadinessScorer()
        self._private_environments: dict[str, EnvironmentState] = {}

    def issue_challenge(self, seed: int | None = None) -> Challenge:
        private_seed = seed if seed is not None else secrets.randbits(64)
        environment = self._generator.generate(private_seed)
        self._private_environments[environment.room_id] = environment
        return Challenge(
            challenge_id=environment.room_id,
            public_state=environment.to_public(),
        )

    def evaluate(
        self,
        challenge_id: str,
        miner_id: str,
        trajectory: TrajectoryLike,
    ) -> EvaluationResult:
        if challenge_id not in self._private_environments:
            raise KeyError(f"unknown challenge_id: {challenge_id}")

        canonical_trajectory = ensure_trajectory(trajectory)
        private_environment = self._private_environments[challenge_id]
        replay_result = self._simulation_adapter.replay(
            private_environment,
            canonical_trajectory,
        )
        score = self._scorer.score(replay_result)
        return EvaluationResult(
            challenge_id=challenge_id,
            miner_id=miner_id,
            trajectory_hash=hash_trajectory(canonical_trajectory),
            score=score,
            replay_summary=ReplaySummary(
                adapter_name=replay_result.adapter_name,
                replay_hash=replay_result.replay_hash,
                action_count=replay_result.action_count,
                invalid_actions=replay_result.invalid_actions,
                events=replay_result.events,
            ),
        )

    def private_challenge_summary(
        self,
        challenge_id: str,
        include_seed: bool = False,
    ) -> dict[str, object]:
        if challenge_id not in self._private_environments:
            raise KeyError(f"unknown challenge_id: {challenge_id}")
        return self._private_environments[challenge_id].private_summary(
            include_seed=include_seed,
        )


def hash_trajectory(trajectory: TrajectoryLike) -> str:
    payload = ensure_trajectory(trajectory).to_wire()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
