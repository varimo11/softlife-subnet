from __future__ import annotations

import importlib
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping

from integrations.isaac_lab.softlife_isaac_lab.config import SoftLifeIsaacRunConfig
from integrations.isaac_lab.softlife_isaac_lab.scene_spec import pose_for_zone
from integrations.isaac_lab.softlife_isaac_lab.usd_export import write_usda_scene
from softlife_subnet.physics_artifacts import (
    CleanlinessMeasurement,
    ObjectPhysicsState,
    PhysicsReplayArtifact,
    Vector3,
)


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

    state = _StageReplayState.from_bundle(bundle_payload)
    command_log: list[dict[str, object]] = []
    invalid_actions = 0

    for command in _compiled_commands(bundle_payload):
        ok, message = state.apply_command(command)
        if not ok:
            invalid_actions += 1
        command_log.append(
            {
                **command,
                "ok": ok,
                "message": message,
                "robot_zone_after": state.robot_zone,
                "held_object_after": state.held_object_id,
            }
        )

    return state.to_artifact(
        adapter_name=adapter_name,
        action_count=len(command_log),
        invalid_actions=invalid_actions,
        step_count=len(command_log) * frame_steps_per_command,
        command_log=tuple(command_log),
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
            state = _StageReplayState.from_bundle(bundle_payload)
            rendered_frames = _apply_commands_to_stage(
                state=state,
                bundle_payload=bundle_payload,
                frame_steps_per_command=max(1, int(1 / run_config.physics_dt / 5)),
                render_dir=None if render_dir is None else Path(render_dir),
                app=app,
            )
            artifact = state.to_artifact(
                adapter_name="isaac_sim_stage_replay_v1",
                action_count=len(_compiled_commands(bundle_payload)),
                invalid_actions=sum(
                    1 for command in state.command_log if not bool(command.get("ok", True))
                ),
                step_count=len(_compiled_commands(bundle_payload))
                * max(1, int(1 / run_config.physics_dt / 5)),
                command_log=tuple(state.command_log),
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


@dataclass
class _StageReplayState:
    room_id: str
    scene_root: str
    sim_seed: int | None
    robot_zone: str
    object_zones: dict[str, str]
    object_kinds: dict[str, str]
    object_targets: dict[str, str]
    object_prims: dict[str, str]
    surface_dirt_before: dict[str, float]
    surface_dirt_after: dict[str, float]
    surface_prims: dict[str, str]
    held_object_id: str | None = None
    command_log: list[dict[str, object]] | None = None

    @classmethod
    def from_bundle(cls, bundle_payload: Mapping[str, Any]) -> "_StageReplayState":
        private_state = _mapping(bundle_payload["validator_private_state"])
        public_state = _mapping(bundle_payload["public_state"])
        scene_manifest = _mapping(bundle_payload["scene_manifest"])
        object_prims = {
            str(key): str(value)
            for key, value in _mapping(scene_manifest["object_prims"]).items()
        }
        surface_prims = {
            str(key): str(value)
            for key, value in _mapping(scene_manifest["surface_prims"]).items()
        }
        objects = tuple(_mapping(item) for item in private_state.get("objects", ()))
        surfaces = tuple(_mapping(item) for item in private_state.get("surfaces", ()))
        raw_seed = private_state.get("private_seed")
        return cls(
            room_id=str(bundle_payload["challenge_id"]),
            scene_root=str(scene_manifest["root_prim"]),
            sim_seed=None if raw_seed is None else int(raw_seed),
            robot_zone=str(public_state.get("robot_zone", private_state.get("robot_zone", "entry"))),
            object_zones={
                str(obj["object_id"]): str(obj["location"])
                for obj in objects
            },
            object_kinds={
                str(obj["object_id"]): str(obj["kind"])
                for obj in objects
            },
            object_targets={
                str(obj["object_id"]): str(obj["target_zone"])
                for obj in objects
            },
            object_prims=object_prims,
            surface_dirt_before={
                str(surface["zone"]): float(surface.get("dirt", 0.0))
                for surface in surfaces
            },
            surface_dirt_after={
                str(surface["zone"]): float(surface.get("dirt", 0.0))
                for surface in surfaces
            },
            surface_prims=surface_prims,
            command_log=[],
        )

    def apply_command(self, command: Mapping[str, Any]) -> tuple[bool, str]:
        command_type = str(command["command_type"])
        object_id = _optional_str(command.get("object_id"))
        zone = _optional_str(command.get("zone"))

        if command_type == "navigate_to_frame":
            if zone is None:
                return False, "missing navigation zone"
            self.robot_zone = zone
            return True, f"navigated to {zone}"

        if command_type == "approach_object":
            if object_id not in self.object_zones:
                return False, "unknown object"
            self.robot_zone = self.object_zones[object_id]
            return True, f"approached {object_id}"

        if command_type == "grasp_object":
            if object_id not in self.object_zones:
                return False, "unknown object"
            if self.held_object_id is not None:
                return False, "already holding object"
            if self.object_zones[object_id] != self.robot_zone:
                return False, "object not in robot zone"
            self.held_object_id = object_id
            self.object_zones[object_id] = "__held__"
            return True, f"grasped {object_id}"

        if command_type == "release_object":
            if zone is None:
                return False, "missing release zone"
            released_object = object_id or self.held_object_id
            if released_object is None:
                return False, "no object to release"
            if self.held_object_id is not None and released_object != self.held_object_id:
                return False, "release object is not held"
            self.object_zones[released_object] = zone
            self.held_object_id = None
            self.robot_zone = zone
            return True, f"released {released_object} in {zone}"

        if command_type == "drop_in_receptacle":
            dropped_object = object_id or self.held_object_id
            if dropped_object is None:
                return False, "no object to drop"
            if self.held_object_id is not None and dropped_object != self.held_object_id:
                return False, "drop object is not held"
            self.object_zones[dropped_object] = zone or "trash_bin"
            self.held_object_id = None
            self.robot_zone = zone or "trash_bin"
            return True, f"dropped {dropped_object} in {self.robot_zone}"

        if command_type == "wipe_surface":
            if zone is None or zone not in self.surface_dirt_after:
                return False, "unknown surface"
            self.surface_dirt_after[zone] = 0.0
            self.robot_zone = zone
            return True, f"wiped {zone}"

        if command_type == "hold_position":
            return True, "held position"

        return False, f"unsupported command {command_type}"

    def to_artifact(
        self,
        *,
        adapter_name: str,
        action_count: int,
        invalid_actions: int,
        step_count: int,
        command_log: tuple[Mapping[str, Any], ...],
    ) -> PhysicsReplayArtifact:
        return PhysicsReplayArtifact(
            adapter_name=adapter_name,
            room_id=self.room_id,
            scene_root=self.scene_root,
            sim_seed=self.sim_seed,
            time_step=1.0 / 60.0,
            step_count=step_count,
            action_count=action_count,
            robot_zone=self.robot_zone,
            invalid_actions=invalid_actions,
            object_states=tuple(self._object_state(object_id) for object_id in sorted(self.object_zones)),
            cleanliness=tuple(
                self._cleanliness(zone) for zone in sorted(self.surface_dirt_after)
            ),
            command_log=command_log,
        )

    def _object_state(self, object_id: str) -> ObjectPhysicsState:
        zone = self.object_zones[object_id]
        x, y, z = pose_for_zone(zone if zone != "__held__" else self.robot_zone)
        return ObjectPhysicsState(
            object_id=object_id,
            prim_path=self.object_prims.get(object_id, ""),
            target_zone=self.object_targets[object_id],
            zone=None if zone == "__held__" else zone,
            position=Vector3(x=x, y=y, z=z),
            held=zone == "__held__",
        )

    def _cleanliness(self, zone: str) -> CleanlinessMeasurement:
        dirt_before = self.surface_dirt_before[zone]
        dirt_after = self.surface_dirt_after[zone]
        cleaned = max(0.0, dirt_before - dirt_after)
        cleaned_fraction = 0.0 if dirt_before <= 0 else min(1.0, cleaned / dirt_before)
        return CleanlinessMeasurement(
            zone=zone,
            surface_prim=self.surface_prims.get(zone, ""),
            dirt_before=dirt_before,
            dirt_after=dirt_after,
            cleaned_area_fraction=cleaned_fraction,
        )


def _apply_commands_to_stage(
    *,
    state: _StageReplayState,
    bundle_payload: Mapping[str, Any],
    frame_steps_per_command: int,
    render_dir: Path | None,
    app: Any,
) -> tuple[Path, ...]:
    rendered_frames: list[Path] = []
    if render_dir is not None:
        render_dir.mkdir(parents=True, exist_ok=True)

    for index, command in enumerate(_compiled_commands(bundle_payload)):
        ok, message = state.apply_command(command)
        enriched_command = {
            **command,
            "ok": ok,
            "message": message,
            "robot_zone_after": state.robot_zone,
            "held_object_after": state.held_object_id,
        }
        state.command_log.append(enriched_command)
        _move_stage_objects(state)
        _update_surface_attrs(state)
        _step_app(app, frame_steps_per_command)
        if render_dir is not None:
            frame = _capture_viewport_frame(render_dir, index, app)
            if frame is not None:
                rendered_frames.append(frame)
    return tuple(rendered_frames)


def _move_stage_objects(state: _StageReplayState) -> None:
    from pxr import Gf, UsdGeom

    stage = _current_stage()
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


def _update_surface_attrs(state: _StageReplayState) -> None:
    stage = _current_stage()
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


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
