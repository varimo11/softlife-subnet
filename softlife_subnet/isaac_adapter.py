from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from softlife_subnet.actions import TrajectoryLike, ensure_trajectory
from softlife_subnet.artifact_ingest import replay_result_from_physics_artifact
from softlife_subnet.isaac_handoff import IsaacReplayBundle, compile_isaac_replay_bundle
from softlife_subnet.physics_artifacts import PhysicsReplayArtifact
from softlife_subnet.simulation import ReplayResult
from softlife_subnet.state import EnvironmentState


class IsaacSimUnavailableError(RuntimeError):
    """Raised when the optional Isaac Lab backend is requested but unavailable."""


@dataclass(frozen=True)
class IsaacSimSimulationAdapter:
    """Isaac replay adapter behind the validator `SimulationAdapter` boundary.

    This class intentionally does not import Isaac Lab at module import time, so
    the lightweight MVP remains runnable on machines without NVIDIA/Isaac
    dependencies.
    """

    task_name: str = "SoftLife-HotelRoom-Restore-v0"
    headless: bool = True
    runtime_mode: str = "unavailable"
    scene_path: str | None = None
    render_dir: str | None = None
    output_artifact_path: str | None = None
    frame_steps_per_command: int = 12
    adapter_name: str = "isaac_sim_adapter_v1"

    def compile_replay_bundle(
        self,
        environment_state: EnvironmentState,
        trajectory: TrajectoryLike,
        miner_id: str = "unknown",
    ) -> IsaacReplayBundle:
        return compile_isaac_replay_bundle(
            environment_state=environment_state,
            trajectory=trajectory,
            miner_id=miner_id,
        )

    def replay(
        self,
        environment_state: EnvironmentState,
        trajectory: TrajectoryLike,
    ) -> ReplayResult:
        canonical_trajectory = ensure_trajectory(trajectory)
        bundle = self.compile_replay_bundle(environment_state, canonical_trajectory)
        bundle_payload = bundle.to_wire(include_private_seed=True)
        mode = self.runtime_mode.strip().lower()

        if mode in {"stage_dry_run", "dry_run", "offline_stage"}:
            artifact = self._build_stage_dry_run_artifact(bundle_payload)
            return replay_result_from_physics_artifact(
                initial_state=environment_state,
                trajectory=canonical_trajectory,
                artifact=artifact,
            )

        if mode in {"stage", "real_stage", "isaac_stage"}:
            artifact = self._run_stage_artifact(bundle_payload)
            return replay_result_from_physics_artifact(
                initial_state=environment_state,
                trajectory=canonical_trajectory,
                artifact=artifact,
            )

        if mode not in {"unavailable", "stub"}:
            raise ValueError(
                "unsupported IsaacSimSimulationAdapter runtime_mode: "
                f"{self.runtime_mode}"
            )

        raise IsaacSimUnavailableError(
            "Isaac Lab replay is not implemented in this lightweight environment. "
            "The symbolic trajectory compiled successfully into "
            f"{len(bundle.compiled_commands)} robot commands for task {self.task_name}; "
            "set runtime_mode='stage_dry_run' for the local artifact bridge, or "
            "run runtime_mode='stage' from an Isaac Sim workstation."
        )

    def _build_stage_dry_run_artifact(
        self,
        bundle_payload: dict[str, object],
    ) -> PhysicsReplayArtifact:
        from integrations.isaac_lab.softlife_isaac_lab.isaac_sim_runner import (
            build_stage_level_artifact,
        )

        return build_stage_level_artifact(
            bundle_payload,
            frame_steps_per_command=self.frame_steps_per_command,
        )

    def _run_stage_artifact(
        self,
        bundle_payload: dict[str, object],
    ) -> PhysicsReplayArtifact:
        from integrations.isaac_lab.softlife_isaac_lab.config import SoftLifeIsaacRunConfig
        from integrations.isaac_lab.softlife_isaac_lab.isaac_sim_runner import (
            IsaacSimRuntimeNotAvailable,
            run_isaac_sim_stage_replay,
        )

        try:
            result = run_isaac_sim_stage_replay(
                bundle_payload,
                scene_path=None if self.scene_path is None else Path(self.scene_path),
                output_artifact_path=(
                    None
                    if self.output_artifact_path is None
                    else Path(self.output_artifact_path)
                ),
                render_dir=None if self.render_dir is None else Path(self.render_dir),
                config=SoftLifeIsaacRunConfig(
                    task_name=self.task_name,
                    headless=self.headless,
                ),
            )
        except IsaacSimRuntimeNotAvailable as exc:
            raise IsaacSimUnavailableError(str(exc)) from exc
        return result.artifact
