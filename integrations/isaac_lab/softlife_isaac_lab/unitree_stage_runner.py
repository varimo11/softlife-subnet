from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from integrations.isaac_lab.softlife_isaac_lab.isaac_sim_runner import (
    _capture_validator_camera_frames,
    _compiled_commands,
    _create_simulation_app,
    _current_stage,
    _open_stage,
    _scene_path_context,
    _step_app,
    find_isaac_sim_package,
)
from integrations.isaac_lab.softlife_isaac_lab.unitree_controller import (
    StageBackedUnitreeBackend,
    UnitreeIsaacControllerUnavailable,
    UnitreeIsaacReplayController,
)
from softlife_subnet.physics_artifacts import PhysicsReplayArtifact


@dataclass(frozen=True)
class UnitreeStageReplayResult:
    artifact: PhysicsReplayArtifact
    scene_path: Path
    rendered_frames: tuple[Path, ...] = ()


def run_unitree_stage_backend_replay(
    bundle_payload: Mapping[str, Any],
    *,
    scene_path: str | Path | None = None,
    render_dir: str | Path | None = None,
    camera_names: Iterable[str] | None = None,
    sim_steps: int = 12,
    headless: bool = True,
) -> UnitreeStageReplayResult:
    """Run the Unitree controller through the Isaac USD stage-backed backend.

    This is the workstation bridge before articulated Unitree control. It
    launches Isaac Sim, opens/generates the stage, executes compiled commands
    through `UnitreeIsaacReplayController`, mutates USD prims via
    `StageBackedUnitreeBackend`, and returns the validator physics artifact.
    """

    isaac_package = find_isaac_sim_package()
    if isaac_package is None:
        raise UnitreeIsaacControllerUnavailable(
            "Isaac Sim is not installed in this Python environment. "
            "Run --stage-backend from an Isaac Sim workstation, for example "
            "with Isaac Sim's python.sh."
        )

    rendered_frames: list[Path] = []
    with _scene_path_context(bundle_payload, scene_path) as resolved_scene_path:
        app = _create_simulation_app(isaac_package, headless=headless)
        try:
            _open_stage(resolved_scene_path)
            stage = _current_stage()
            backend = StageBackedUnitreeBackend.from_bundle(
                bundle_payload,
                stage=stage,
            )
            controller = UnitreeIsaacReplayController.from_bundle(
                bundle_payload,
                backend=backend,
            )
            commands = _compiled_commands(bundle_payload)
            frame_dir = None if render_dir is None else Path(render_dir)
            if frame_dir is not None:
                frame_dir.mkdir(parents=True, exist_ok=True)

            for index, command in enumerate(commands):
                controller.execute(command, sim_steps=sim_steps)
                _step_app(app, sim_steps)
                if frame_dir is not None:
                    rendered_frames.extend(
                        _capture_validator_camera_frames(
                            frame_dir,
                            index,
                            app,
                            bundle_payload=bundle_payload,
                            camera_names=camera_names,
                        )
                    )

            artifact = controller.to_artifact(
                adapter_name="unitree_isaac_stage_backend_v1",
                action_count=len(commands),
                step_count=len(commands) * sim_steps,
            )
            return UnitreeStageReplayResult(
                artifact=artifact,
                scene_path=resolved_scene_path,
                rendered_frames=tuple(rendered_frames),
            )
        finally:
            app.close()
