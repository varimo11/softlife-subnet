from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from softlife_subnet.actions import TrajectoryLike, ensure_trajectory
from softlife_subnet.miners import HeuristicMiner, NoOpMiner
from softlife_subnet.physics_artifacts import SCHEMA_VERSION
from softlife_subnet.robotics import HotelRoomSceneManifest, SoftLifeTrajectoryProvider
from softlife_subnet.room_generator import RoomGenerator
from softlife_subnet.state import EnvironmentState, PublicRoomState


@dataclass(frozen=True)
class IsaacReplayBundle:
    """Validator-private handoff package for Isaac Lab replay."""

    seed: int
    miner_id: str
    environment_state: EnvironmentState
    public_state: PublicRoomState
    scene_manifest: HotelRoomSceneManifest
    trajectory: list[dict[str, object]]
    compiled_commands: list[dict[str, object]]

    def to_wire(self, include_private_seed: bool = False) -> dict[str, object]:
        return {
            "bundle_schema": "softlife.isaac_replay_bundle.v1",
            "warning": "Validator-private replay bundle. Do not send to miners.",
            "seed_included": include_private_seed,
            "miner_id": self.miner_id,
            "challenge_id": self.environment_state.room_id,
            "task_name": self.environment_state.task_name,
            "public_state": self.public_state.to_wire(),
            "validator_private_state": self.environment_state.private_summary(
                include_seed=include_private_seed
            ),
            "scene_manifest": self.scene_manifest.to_wire(),
            "trajectory": self.trajectory,
            "compiled_commands": self.compiled_commands,
            "expected_replay_artifact_schema": SCHEMA_VERSION,
        }


def build_isaac_replay_bundle(
    *,
    seed: int,
    miner: str = "heuristic",
) -> IsaacReplayBundle:
    generator = RoomGenerator()
    environment = generator.generate(seed)
    public_state = environment.to_public()
    miner_impl = _miner_for_name(miner)
    trajectory = miner_impl.solve(public_state)
    return compile_isaac_replay_bundle(
        environment_state=environment,
        trajectory=trajectory,
        miner_id=miner_impl.miner_id,
    )


def compile_isaac_replay_bundle(
    *,
    environment_state: EnvironmentState,
    trajectory: TrajectoryLike,
    miner_id: str,
) -> IsaacReplayBundle:
    public_state = environment_state.to_public()
    canonical_trajectory = ensure_trajectory(trajectory)
    scene_manifest = HotelRoomSceneManifest.from_environment(environment_state)
    action_provider = SoftLifeTrajectoryProvider(
        trajectory=canonical_trajectory,
        scene_manifest=scene_manifest,
    )
    return IsaacReplayBundle(
        seed=environment_state.private_seed,
        miner_id=miner_id,
        environment_state=environment_state,
        public_state=public_state,
        scene_manifest=scene_manifest,
        trajectory=canonical_trajectory.to_wire(),
        compiled_commands=[command.to_wire() for command in action_provider.commands()],
    )


def _miner_for_name(name: str) -> Any:
    normalized = name.strip().lower()
    if normalized in {"heuristic", "heuristic_baseline", "baseline"}:
        return HeuristicMiner()
    if normalized in {"noop", "no_op", "none"}:
        return NoOpMiner()
    raise ValueError(f"unknown replay-bundle miner: {name}")
