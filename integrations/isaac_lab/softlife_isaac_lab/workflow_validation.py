from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from integrations.isaac_lab.softlife_isaac_lab.config import SoftLifeIsaacRunConfig
from integrations.isaac_lab.softlife_isaac_lab.isaac_sim_runner import (
    build_stage_level_artifact,
    find_isaac_sim_package,
    run_isaac_sim_stage_replay,
)
from integrations.isaac_lab.softlife_isaac_lab.unitree_controller import (
    build_unitree_dry_run_artifact,
)
from integrations.isaac_lab.softlife_isaac_lab.usd_export import write_usda_scene
from softlife_subnet.actions import Trajectory
from softlife_subnet.artifact_ingest import replay_result_from_physics_artifact
from softlife_subnet.isaac_handoff import build_isaac_replay_bundle
from softlife_subnet.physics_artifacts import PhysicsReplayArtifact
from softlife_subnet.room_generator import RoomGenerator
from softlife_subnet.scoring import RoomReadinessScorer


REPORT_SCHEMA_VERSION = "softlife.isaac_workflow_report.v1"
CANONICAL_WORKFLOW_SEEDS = (42, 101, 7)


@dataclass(frozen=True)
class ArtifactWorkflowCheck:
    name: str
    mode: str
    ok: bool
    artifact_path: Path
    adapter_name: str | None = None
    artifact_hash: str | None = None
    readiness: float | None = None
    invalid_actions: int | None = None
    action_count: int | None = None
    step_count: int | None = None
    command_log_count: int | None = None
    rendered_frame_count: int = 0
    rendered_frame_paths: tuple[Path, ...] = ()
    error: str | None = None

    def to_wire(self) -> dict[str, object]:
        return {
            "name": self.name,
            "mode": self.mode,
            "ok": self.ok,
            "artifact_path": str(self.artifact_path),
            "adapter_name": self.adapter_name,
            "artifact_hash": self.artifact_hash,
            "readiness": self.readiness,
            "invalid_actions": self.invalid_actions,
            "action_count": self.action_count,
            "step_count": self.step_count,
            "command_log_count": self.command_log_count,
            "rendered_frame_count": self.rendered_frame_count,
            "rendered_frame_paths": [str(path) for path in self.rendered_frame_paths],
            "error": self.error,
        }


@dataclass(frozen=True)
class SeedWorkflowResult:
    seed: int
    room_id: str
    command_count: int
    trajectory_count: int
    bundle_path: Path
    scene_path: Path
    bundle_redacts_private_seed: bool
    stage: ArtifactWorkflowCheck
    unitree_dry_run: ArtifactWorkflowCheck

    @property
    def ok(self) -> bool:
        return (
            self.bundle_redacts_private_seed
            and self.command_count == self.trajectory_count
            and self.stage.ok
            and self.unitree_dry_run.ok
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "room_id": self.room_id,
            "ok": self.ok,
            "command_count": self.command_count,
            "trajectory_count": self.trajectory_count,
            "bundle_path": str(self.bundle_path),
            "scene_path": str(self.scene_path),
            "bundle_redacts_private_seed": self.bundle_redacts_private_seed,
            "stage": self.stage.to_wire(),
            "unitree_dry_run": self.unitree_dry_run.to_wire(),
        }


@dataclass(frozen=True)
class IsaacWorkflowReport:
    output_dir: Path
    seeds: tuple[int, ...]
    real_stage_requested: bool
    capture_frames: bool
    isaac_sim_package: str | None
    results: tuple[SeedWorkflowResult, ...]
    schema_version: str = REPORT_SCHEMA_VERSION

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.results)

    def to_wire(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "ok": self.ok,
            "output_dir": str(self.output_dir),
            "seeds": list(self.seeds),
            "real_stage_requested": self.real_stage_requested,
            "capture_frames": self.capture_frames,
            "isaac_sim_package": self.isaac_sim_package,
            "results": [result.to_wire() for result in self.results],
        }


def validate_isaac_workflow(
    *,
    out_dir: str | Path,
    seeds: Iterable[int] = CANONICAL_WORKFLOW_SEEDS,
    real_stage: bool = False,
    capture_frames: bool = False,
    headless: bool = True,
    sim_steps: int = 12,
) -> IsaacWorkflowReport:
    """Validate the Soft Life Isaac handoff across canonical replay bundles.

    The default mode is dependency-free and validates bundle export, USD scene
    export, stage-level replay semantics, Unitree command mapping, artifact
    hashes, and validator scoring. On an Isaac workstation, `real_stage=True`
    runs the stage replay through Isaac Sim instead of the offline stage model.
    """

    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    seed_tuple = tuple(int(seed) for seed in seeds)
    results = tuple(
        _validate_seed(
            seed=seed,
            out_dir=output_dir,
            real_stage=real_stage,
            capture_frames=capture_frames,
            headless=headless,
            sim_steps=sim_steps,
        )
        for seed in seed_tuple
    )
    return IsaacWorkflowReport(
        output_dir=output_dir,
        seeds=seed_tuple,
        real_stage_requested=real_stage,
        capture_frames=capture_frames,
        isaac_sim_package=find_isaac_sim_package(),
        results=results,
    )


def write_workflow_report(report: IsaacWorkflowReport, path: str | Path) -> Path:
    return _write_json(Path(path), report.to_wire())


def _validate_seed(
    *,
    seed: int,
    out_dir: Path,
    real_stage: bool,
    capture_frames: bool,
    headless: bool,
    sim_steps: int,
) -> SeedWorkflowResult:
    seed_dir = out_dir / f"seed_{seed}"
    seed_dir.mkdir(parents=True, exist_ok=True)

    bundle = build_isaac_replay_bundle(seed=seed)
    bundle_payload = bundle.to_wire()
    bundle_path = seed_dir / f"softlife_seed{seed}_bundle.json"
    scene_path = seed_dir / f"softlife_seed{seed}_scene.usda"
    _write_json(bundle_path, bundle_payload)
    write_usda_scene(bundle_payload, scene_path)

    command_count = len(tuple(bundle_payload.get("compiled_commands", ())))
    trajectory_count = len(tuple(bundle_payload.get("trajectory", ())))
    bundle_json = json.dumps(bundle_payload, sort_keys=True)
    stage = _validate_stage_artifact(
        seed=seed,
        bundle_payload=bundle_payload,
        scene_path=scene_path,
        artifact_path=seed_dir / f"softlife_seed{seed}_stage_artifact.json",
        real_stage=real_stage,
        capture_frames=capture_frames,
        headless=headless,
        sim_steps=sim_steps,
        command_count=command_count,
    )
    unitree_dry_run = _validate_unitree_dry_run_artifact(
        seed=seed,
        bundle_payload=bundle_payload,
        artifact_path=seed_dir / f"softlife_seed{seed}_unitree_artifact.json",
        sim_steps=sim_steps,
        command_count=command_count,
    )

    return SeedWorkflowResult(
        seed=seed,
        room_id=bundle.environment_state.room_id,
        command_count=command_count,
        trajectory_count=trajectory_count,
        bundle_path=bundle_path,
        scene_path=scene_path,
        bundle_redacts_private_seed="private_seed" not in bundle_json,
        stage=stage,
        unitree_dry_run=unitree_dry_run,
    )


def _validate_stage_artifact(
    *,
    seed: int,
    bundle_payload: Mapping[str, Any],
    scene_path: Path,
    artifact_path: Path,
    real_stage: bool,
    capture_frames: bool,
    headless: bool,
    sim_steps: int,
    command_count: int,
) -> ArtifactWorkflowCheck:
    mode = "real_stage" if real_stage else "stage_dry_run"
    try:
        if real_stage:
            result = run_isaac_sim_stage_replay(
                bundle_payload,
                scene_path=scene_path,
                output_artifact_path=artifact_path,
                render_dir=artifact_path.parent / "stage_frames" if capture_frames else None,
                config=SoftLifeIsaacRunConfig(headless=headless),
            )
            artifact = result.artifact
            rendered_frames = tuple(result.rendered_frames)
        else:
            artifact = build_stage_level_artifact(
                bundle_payload,
                frame_steps_per_command=sim_steps,
            )
            rendered_frames = ()
        _write_artifact(artifact_path, artifact)
        return _check_artifact(
            name="stage",
            mode=mode,
            seed=seed,
            bundle_payload=bundle_payload,
            artifact=artifact,
            artifact_path=artifact_path,
            command_count=command_count,
            rendered_frames=rendered_frames,
            require_rendered_frames=real_stage and capture_frames,
        )
    except Exception as exc:
        return ArtifactWorkflowCheck(
            name="stage",
            mode=mode,
            ok=False,
            artifact_path=artifact_path,
            error=f"{type(exc).__name__}: {exc}",
        )


def _validate_unitree_dry_run_artifact(
    *,
    seed: int,
    bundle_payload: Mapping[str, Any],
    artifact_path: Path,
    sim_steps: int,
    command_count: int,
) -> ArtifactWorkflowCheck:
    try:
        artifact = build_unitree_dry_run_artifact(
            bundle_payload,
            frame_steps_per_command=sim_steps,
        )
        _write_artifact(artifact_path, artifact)
        return _check_artifact(
            name="unitree",
            mode="unitree_dry_run",
            seed=seed,
            bundle_payload=bundle_payload,
            artifact=artifact,
            artifact_path=artifact_path,
            command_count=command_count,
        )
    except Exception as exc:
        return ArtifactWorkflowCheck(
            name="unitree",
            mode="unitree_dry_run",
            ok=False,
            artifact_path=artifact_path,
            error=f"{type(exc).__name__}: {exc}",
        )


def _check_artifact(
    *,
    name: str,
    mode: str,
    seed: int,
    bundle_payload: Mapping[str, Any],
    artifact: PhysicsReplayArtifact,
    artifact_path: Path,
    command_count: int,
    rendered_frames: tuple[Path, ...] = (),
    require_rendered_frames: bool = False,
) -> ArtifactWorkflowCheck:
    score = _score_artifact(seed, bundle_payload, artifact)
    command_log_count = len(artifact.command_log)
    round_trip = PhysicsReplayArtifact.from_wire(artifact.to_private_wire())
    rendered_frame_error = _rendered_frame_error(rendered_frames, require_rendered_frames)
    ok = (
        round_trip == artifact
        and artifact.action_count == command_count
        and artifact.invalid_actions == 0
        and command_log_count == command_count
        and rendered_frame_error is None
    )
    return ArtifactWorkflowCheck(
        name=name,
        mode=mode,
        ok=ok,
        artifact_path=artifact_path,
        adapter_name=artifact.adapter_name,
        artifact_hash=artifact.artifact_hash,
        readiness=score,
        invalid_actions=artifact.invalid_actions,
        action_count=artifact.action_count,
        step_count=artifact.step_count,
        command_log_count=command_log_count,
        rendered_frame_count=len(rendered_frames),
        rendered_frame_paths=rendered_frames,
        error=rendered_frame_error,
    )


def _score_artifact(
    seed: int,
    bundle_payload: Mapping[str, Any],
    artifact: PhysicsReplayArtifact,
) -> float:
    environment = RoomGenerator().generate(seed)
    trajectory = Trajectory.from_wire(bundle_payload["trajectory"])
    replay_result = replay_result_from_physics_artifact(
        initial_state=environment,
        trajectory=trajectory,
        artifact=artifact,
    )
    return RoomReadinessScorer().score(replay_result).readiness


def _rendered_frame_error(
    rendered_frames: tuple[Path, ...],
    require_rendered_frames: bool,
) -> str | None:
    if not require_rendered_frames:
        return None
    if not rendered_frames:
        return "frame capture requested but no rendered frames were returned"
    missing_or_empty = tuple(
        path for path in rendered_frames
        if not path.exists() or path.stat().st_size <= 0
    )
    if missing_or_empty:
        paths = ", ".join(str(path) for path in missing_or_empty)
        return f"frame capture returned missing or empty files: {paths}"
    return None


def _write_artifact(path: Path, artifact: PhysicsReplayArtifact) -> Path:
    return _write_json(path, artifact.to_private_wire())


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
