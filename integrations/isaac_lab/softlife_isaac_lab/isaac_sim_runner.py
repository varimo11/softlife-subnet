from __future__ import annotations

import importlib
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from integrations.isaac_lab.softlife_isaac_lab.config import SoftLifeIsaacRunConfig
from integrations.isaac_lab.softlife_isaac_lab.controllers import StageReplayController
from integrations.isaac_lab.softlife_isaac_lab.scene_spec import pose_for_zone
from integrations.isaac_lab.softlife_isaac_lab.stage_truth import build_stage_truth_artifact
from integrations.isaac_lab.softlife_isaac_lab.usd_export import write_usda_scene
from softlife_subnet.physics_artifacts import PhysicsReplayArtifact


class IsaacSimRuntimeNotAvailable(RuntimeError):
    """Raised when Isaac Sim is required but unavailable."""


@dataclass(frozen=True)
class IsaacStageReplayResult:
    artifact: PhysicsReplayArtifact
    scene_path: Path
    rendered_frames: tuple[Path, ...] = ()


def find_isaac_sim_package() -> str | None:
    """Return the available Isaac Sim application package, if any."""

    candidates = ("isaacsim", "omni.isaac.kit")
    for candidate in candidates:
        try:
            spec = importlib.util.find_spec(candidate)
        except ModuleNotFoundError:
            spec = None
        if spec is not None:
            return candidate
    return None


def build_stage_level_artifact(
    bundle_payload: Mapping[str, Any],
    *,
    adapter_name: str = "isaac_sim_stage_replay_v1",
    frame_steps_per_command: int = 12,
) -> PhysicsReplayArtifact:
    """Execute compiled commands deterministically without launching Isaac.

    This mirrors the stage-level command semantics used by the Isaac Sim runner
    and gives validators a testable artifact contract before robot physics is
    wired in.
    """

    controller = StageReplayController.from_bundle(bundle_payload)
    commands = _compiled_commands(bundle_payload)

    for command in commands:
        controller.execute(command, sim_steps=frame_steps_per_command)

    return controller.to_artifact(
        adapter_name=adapter_name,
        action_count=len(commands),
        step_count=len(commands) * frame_steps_per_command,
    )


def run_isaac_sim_stage_replay(
    bundle_payload: Mapping[str, Any],
    *,
    scene_path: str | Path | None = None,
    output_artifact_path: str | Path | None = None,
    render_dir: str | Path | None = None,
    config: SoftLifeIsaacRunConfig | None = None,
) -> IsaacStageReplayResult:
    """Run a deterministic stage-level replay inside Isaac Sim.

    This is the first Isaac-runnable bridge. It does not yet solve manipulation
    with a Unitree robot controller; it loads the scene, applies the compiled
    command effects to USD prims, advances the Isaac app, optionally captures
    viewport frames, and writes the physics artifact schema expected by the
    validator.
    """

    run_config = config or SoftLifeIsaacRunConfig()
    isaac_package = find_isaac_sim_package()
    if isaac_package is None:
        raise IsaacSimRuntimeNotAvailable(
            "Isaac Sim is not installed in this Python environment. Run this "
            "from an Isaac Sim workstation, for example with Isaac Sim's "
            "python.sh, or use --dry-run to validate the artifact contract."
        )

    with _scene_path_context(bundle_payload, scene_path) as resolved_scene_path:
        app = _create_simulation_app(isaac_package, headless=run_config.headless)
        try:
            _open_stage(resolved_scene_path)
            controller = StageReplayController.from_bundle(bundle_payload)
            frame_steps_per_command = max(1, int(1 / run_config.physics_dt / 5))
            rendered_frames = _apply_commands_to_stage(
                controller=controller,
                bundle_payload=bundle_payload,
                frame_steps_per_command=frame_steps_per_command,
                render_dir=None if render_dir is None else Path(render_dir),
                app=app,
            )
            commands = _compiled_commands(bundle_payload)
            artifact = build_stage_truth_artifact(
                stage=_current_stage(),
                bundle_payload=bundle_payload,
                controller=controller,
                adapter_name="isaac_sim_stage_replay_v1",
                action_count=len(commands),
                step_count=len(commands) * frame_steps_per_command,
                time_step=run_config.physics_dt,
            )
            if output_artifact_path is not None:
                _write_artifact(artifact, output_artifact_path)
            return IsaacStageReplayResult(
                artifact=artifact,
                scene_path=resolved_scene_path,
                rendered_frames=tuple(rendered_frames),
            )
        finally:
            app.close()


def _apply_commands_to_stage(
    *,
    controller: StageReplayController,
    bundle_payload: Mapping[str, Any],
    frame_steps_per_command: int,
    render_dir: Path | None,
    app: Any,
) -> tuple[Path, ...]:
    rendered_frames: list[Path] = []
    if render_dir is not None:
        render_dir.mkdir(parents=True, exist_ok=True)

    for index, command in enumerate(_compiled_commands(bundle_payload)):
        controller.execute(command, sim_steps=frame_steps_per_command)
        _move_stage_objects(controller)
        _update_surface_attrs(controller)
        _step_app(app, frame_steps_per_command)
        if render_dir is not None:
            frame = _capture_viewport_frame(render_dir, index, app)
            if frame is not None:
                rendered_frames.append(frame)
    return tuple(rendered_frames)


def _move_stage_objects(controller: StageReplayController) -> None:
    from pxr import Gf, UsdGeom

    stage = _current_stage()
    state = controller.state
    for object_id, zone in state.object_zones.items():
        prim_path = state.object_prims.get(object_id)
        if not prim_path:
            continue
        prim = stage.GetPrimAtPath(prim_path)
        if not prim:
            continue
        x, y, z = pose_for_zone(zone if zone != "__held__" else state.robot_zone)
        xformable = UsdGeom.Xformable(prim)
        _set_translate(xformable, Gf.Vec3d(x, y, z))


def _update_surface_attrs(controller: StageReplayController) -> None:
    stage = _current_stage()
    state = controller.state
    for zone, dirt in state.surface_dirt_after.items():
        prim_path = state.surface_prims.get(zone)
        if not prim_path:
            continue
        prim = stage.GetPrimAtPath(prim_path)
        if prim:
            attr = prim.GetAttribute("softlife:dirt")
            if attr:
                attr.Set(float(dirt))


def _set_translate(xformable: Any, value: Any) -> None:
    from pxr import UsdGeom

    for op in xformable.GetOrderedXformOps():
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            op.Set(value)
            return
    xformable.AddTranslateOp().Set(value)


def _create_simulation_app(isaac_package: str, *, headless: bool) -> Any:
    if isaac_package == "isaacsim":
        module = importlib.import_module("isaacsim")
    else:
        module = importlib.import_module("omni.isaac.kit")
    simulation_app_cls = getattr(module, "SimulationApp")
    return simulation_app_cls({"headless": headless})


def _open_stage(scene_path: Path) -> None:
    import omni.usd

    context = omni.usd.get_context()
    if not context.open_stage(str(scene_path)):
        raise RuntimeError(f"failed to open USD stage: {scene_path}")
    _step_app(_app(), 5)


def _current_stage() -> Any:
    import omni.usd

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        raise RuntimeError("Isaac USD stage is not open")
    return stage


def _step_app(app: Any, count: int) -> None:
    for _ in range(max(0, count)):
        app.update()


def _app() -> Any:
    import omni.kit.app

    return omni.kit.app.get_app()


def _capture_viewport_frame(render_dir: Path, index: int, app: Any) -> Path | None:
    try:
        import omni.kit.viewport.utility as viewport_utility

        viewport = viewport_utility.get_active_viewport()
        frame_path = render_dir / f"softlife_replay_{index:04d}.png"
        viewport_utility.capture_viewport_to_file(viewport, str(frame_path))
        _step_app(app, 3)
        return frame_path
    except Exception:
        return None


def _scene_path_context(bundle_payload: Mapping[str, Any], scene_path: str | Path | None) -> Any:
    class ScenePathContext:
        def __enter__(self) -> Path:
            if scene_path is not None:
                self.path = Path(scene_path)
                if not self.path.exists():
                    write_usda_scene(bundle_payload, self.path)
                self.tmpdir = None
                return self.path
            self.tmpdir = TemporaryDirectory()
            self.path = Path(self.tmpdir.name) / "softlife_scene.usda"
            write_usda_scene(bundle_payload, self.path)
            return self.path

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            if self.tmpdir is not None:
                self.tmpdir.cleanup()

    return ScenePathContext()


def _write_artifact(artifact: PhysicsReplayArtifact, output_artifact_path: str | Path) -> None:
    output_path = Path(output_artifact_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact.to_private_wire(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _compiled_commands(bundle_payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    return tuple(_mapping(command) for command in bundle_payload.get("compiled_commands", ()))


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected mapping, got {type(value).__name__}")
    return value
