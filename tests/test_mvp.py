from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch

from integrations.isaac_lab.softlife_isaac_lab.replay_runner import (
    IsaacLabNotAvailable,
    find_isaac_lab_package,
    run_replay_bundle,
)
from integrations.isaac_lab.softlife_isaac_lab.isaac_sim_runner import (
    IsaacSimRuntimeNotAvailable,
    build_stage_level_artifact,
    find_isaac_sim_package,
    run_isaac_sim_stage_replay,
)
from integrations.isaac_lab.softlife_isaac_lab.controllers import (
    RobotReplayController,
    StageReplayController,
)
from integrations.isaac_lab.softlife_isaac_lab.scene_spec import pose_for_zone
from integrations.isaac_lab.softlife_isaac_lab.stage_truth import build_stage_truth_artifact
from integrations.isaac_lab.softlife_isaac_lab.unitree_controller import (
    BackendCommandResult,
    BackendSnapshot,
    SimulatedUnitreeBackend,
    UnitreeIsaacBackend,
    UnitreeIsaacControllerUnavailable,
    UnitreeIsaacReplayController,
)
from integrations.isaac_lab.softlife_isaac_lab.usd_export import render_usda_scene
from integrations.isaac_lab.softlife_isaac_lab.workflow_validation import (
    validate_isaac_workflow,
)
from softlife_subnet.actions import Action, ActionType, Trajectory
from softlife_subnet.artifact_ingest import replay_result_from_physics_artifact
from softlife_subnet.isaac_handoff import build_isaac_replay_bundle
from softlife_subnet.isaac_adapter import IsaacSimSimulationAdapter, IsaacSimUnavailableError
from softlife_subnet.leaderboard import Leaderboard
from softlife_subnet.miners import HeuristicMiner, NoOpMiner
from softlife_subnet.physics_artifacts import (
    CleanlinessMeasurement,
    ObjectPhysicsState,
    PhysicsReplayArtifact,
)
from softlife_subnet.robotics import (
    ActionProvider,
    HotelRoomSceneManifest,
    RobotCommandType,
    SoftLifeTrajectoryProvider,
    build_symbolic_physics_artifact,
)
from softlife_subnet.room_generator import RoomGenerator
from softlife_subnet.scoring import RoomReadinessScorer, clamp_score
from softlife_subnet.simulation import MockSimulationAdapter, ReplayResult, SimulationAdapter
from softlife_subnet.validators import Validator


class MvpTests(unittest.TestCase):
    def test_room_generation_is_deterministic_for_seed(self) -> None:
        generator = RoomGenerator()

        first = generator.generate(123)
        second = generator.generate(123)

        self.assertEqual(first, second)
        self.assertEqual(first.to_public(), second.to_public())

    def test_public_state_excludes_private_seed_and_hidden_metadata(self) -> None:
        generator = RoomGenerator(
            hidden_object_probability=1.0,
            hidden_surface_probability=1.0,
        )
        room = generator.generate(7)
        public = room.to_public()
        public_json = json.dumps(public.to_wire(), sort_keys=True)

        self.assertEqual(public.objects, ())
        self.assertEqual(public.surfaces, ())
        self.assertNotIn("private_seed", public_json)
        self.assertNotIn("visible_to_miner", public_json)
        self.assertFalse(hasattr(public, "private_seed"))

    def test_challenge_wire_is_public_only(self) -> None:
        validator = Validator()
        challenge = validator.issue_challenge(seed=42)

        challenge_json = json.dumps(challenge.to_wire(), sort_keys=True)
        private_summary = validator.private_challenge_summary(challenge.challenge_id)

        self.assertIn("hidden_object_count", private_summary)
        self.assertNotIn("private_seed", challenge_json)
        self.assertNotIn("hidden_object_count", challenge_json)
        self.assertNotIn("visible_to_miner", challenge_json)

    def test_trajectory_wire_round_trip_supports_required_actions(self) -> None:
        trajectory = Trajectory.from_actions(
            (
                Action.move_to_zone("floor"),
                Action.move_to_object("towel_1"),
                Action.pick("towel_1"),
                Action.place("towel_1", "hamper"),
                Action.clean_surface("floor"),
                Action.dispose("wrapper_1"),
            )
        )

        wire = trajectory.to_wire()
        round_trip = Trajectory.from_wire(wire)
        action_types = {item["type"] for item in wire}

        self.assertEqual(round_trip, trajectory)
        self.assertEqual(
            action_types,
            {
                ActionType.MOVE_TO_ZONE.value,
                ActionType.MOVE_TO_OBJECT.value,
                ActionType.PICK.value,
                ActionType.PLACE.value,
                ActionType.CLEAN_SURFACE.value,
                ActionType.DISPOSE.value,
            },
        )
        json.dumps(wire)

    def test_mock_adapter_satisfies_simulation_adapter_interface(self) -> None:
        adapter = MockSimulationAdapter()
        room = RoomGenerator().generate(11)

        self.assertIsInstance(adapter, SimulationAdapter)
        self.assertIsInstance(adapter.replay(room, Trajectory.from_actions(())), ReplayResult)

    def test_trajectory_provider_compiles_robot_commands(self) -> None:
        room = RoomGenerator().generate(42)
        trajectory = Trajectory.from_actions(
            (
                Action.move_to_object("towel_1"),
                Action.pick("towel_1"),
                Action.move_to_zone("hamper"),
                Action.place("towel_1", "hamper"),
                Action.clean_surface("floor"),
            )
        )
        manifest = HotelRoomSceneManifest.from_environment(room)
        provider = SoftLifeTrajectoryProvider(trajectory, manifest)

        commands = tuple(provider.commands())
        command_types = {command.command_type for command in commands}

        self.assertIsInstance(provider, ActionProvider)
        self.assertEqual(len(commands), len(trajectory))
        self.assertIn(RobotCommandType.APPROACH_OBJECT, command_types)
        self.assertIn(RobotCommandType.GRASP_OBJECT, command_types)
        self.assertIn(RobotCommandType.RELEASE_OBJECT, command_types)
        json.dumps([command.to_wire() for command in commands], sort_keys=True)

    def test_isaac_adapter_stub_keeps_dependency_boundary_clear(self) -> None:
        room = RoomGenerator().generate(42)
        trajectory = HeuristicMiner().solve(room.to_public())
        adapter = IsaacSimSimulationAdapter()
        bundle = adapter.compile_replay_bundle(room, trajectory, miner_id="test_miner")

        self.assertIsInstance(adapter, SimulationAdapter)
        self.assertEqual(bundle.miner_id, "test_miner")
        self.assertEqual(len(bundle.compiled_commands), len(trajectory))
        with self.assertRaises(IsaacSimUnavailableError):
            adapter.replay(room, trajectory)

    def test_physics_artifact_schema_is_deterministic_and_redacts_public_summary(self) -> None:
        room = RoomGenerator().generate(42)
        trajectory = HeuristicMiner().solve(room.to_public())
        replay = MockSimulationAdapter().replay(room, trajectory)
        manifest = HotelRoomSceneManifest.from_environment(room)
        commands = tuple(
            command.to_wire()
            for command in SoftLifeTrajectoryProvider(trajectory, manifest).commands()
        )

        first = build_symbolic_physics_artifact(
            adapter_name=replay.adapter_name,
            initial_state=replay.initial_state,
            final_state=replay.final_state,
            scene_manifest=manifest,
            step_count=replay.action_count,
            command_log=commands,
        )
        second = build_symbolic_physics_artifact(
            adapter_name=replay.adapter_name,
            initial_state=replay.initial_state,
            final_state=replay.final_state,
            scene_manifest=manifest,
            step_count=replay.action_count,
            command_log=commands,
        )

        self.assertIsInstance(first, PhysicsReplayArtifact)
        self.assertEqual(first.artifact_hash, second.artifact_hash)
        self.assertEqual(first.to_private_wire(), second.to_private_wire())
        self.assertEqual(
            PhysicsReplayArtifact.from_wire(first.to_private_wire()),
            first,
        )
        self.assertNotIn("sim_seed", json.dumps(first.to_public_summary(), sort_keys=True))
        self.assertNotIn("/World/SoftLifeRooms", json.dumps(first.to_public_summary()))

    def test_physics_artifact_ingests_back_into_replay_result(self) -> None:
        room = RoomGenerator().generate(42)
        trajectory = HeuristicMiner().solve(room.to_public())
        mock_replay = MockSimulationAdapter().replay(room, trajectory)
        manifest = HotelRoomSceneManifest.from_environment(room)
        artifact = build_symbolic_physics_artifact(
            adapter_name="isaac_lab_test",
            initial_state=mock_replay.initial_state,
            final_state=mock_replay.final_state,
            scene_manifest=manifest,
            step_count=240,
            action_count=mock_replay.action_count,
            invalid_actions=mock_replay.invalid_actions,
        )

        physics_replay = replay_result_from_physics_artifact(
            initial_state=room,
            trajectory=trajectory,
            artifact=artifact,
        )

        self.assertEqual(physics_replay.final_state, mock_replay.final_state)
        self.assertEqual(physics_replay.action_count, mock_replay.action_count)
        self.assertEqual(physics_replay.invalid_actions, mock_replay.invalid_actions)
        self.assertEqual(physics_replay.replay_hash, artifact.artifact_hash)
        self.assertIs(physics_replay.physics_artifact, artifact)

    def test_isaac_replay_bundle_exports_commands_without_private_seed_by_default(self) -> None:
        bundle = build_isaac_replay_bundle(seed=42)
        redacted = bundle.to_wire()
        private = bundle.to_wire(include_private_seed=True)

        self.assertEqual(redacted["bundle_schema"], "softlife.isaac_replay_bundle.v1")
        self.assertGreater(len(redacted["compiled_commands"]), 0)
        self.assertEqual(
            len(redacted["compiled_commands"]),
            len(redacted["trajectory"]),
        )
        self.assertNotIn(
            "private_seed",
            json.dumps(redacted["validator_private_state"], sort_keys=True),
        )
        self.assertIn(
            "private_seed",
            json.dumps(private["validator_private_state"], sort_keys=True),
        )
        json.dumps(redacted, sort_keys=True)

    def test_isaac_replay_bundle_renders_usda_scene(self) -> None:
        bundle = build_isaac_replay_bundle(seed=42).to_wire()
        usda = render_usda_scene(bundle)

        self.assertIn("#usda 1.0", usda)
        self.assertIn('def Xform "World"', usda)
        self.assertIn('def Xform "Zones"', usda)
        self.assertIn('def Xform "Objects"', usda)
        self.assertIn('def Camera "wide_validator_camera"', usda)
        self.assertIn("softlife:asset_hint", usda)
        self.assertIn("room_1cf6ab0be52f", usda)

    def test_isaac_stage_level_replay_artifact_scores_like_validator_replay(self) -> None:
        bundle = build_isaac_replay_bundle(seed=42).to_wire()
        artifact = build_stage_level_artifact(bundle)
        room = RoomGenerator().generate(42)
        trajectory = Trajectory.from_wire(bundle["trajectory"])
        replay = replay_result_from_physics_artifact(
            initial_state=room,
            trajectory=trajectory,
            artifact=artifact,
        )
        score = RoomReadinessScorer().score(replay)

        self.assertEqual(artifact.adapter_name, "isaac_sim_stage_replay_v1")
        self.assertEqual(artifact.action_count, len(bundle["compiled_commands"]))
        self.assertEqual(artifact.invalid_actions, 0)
        self.assertEqual(replay.events[0].robot_zone_after, "nightstand")
        self.assertEqual(replay.events[1].held_object_after, "pillow_1")
        self.assertEqual(score.readiness, 97.679)

    def test_stage_replay_controller_satisfies_robot_controller_boundary(self) -> None:
        bundle = build_isaac_replay_bundle(seed=42).to_wire()
        controller = StageReplayController.from_bundle(bundle)
        first_command = bundle["compiled_commands"][0]

        result = controller.execute(first_command, sim_steps=12)
        artifact = controller.to_artifact(
            adapter_name="controller_test",
            action_count=1,
            step_count=12,
        )

        self.assertIsInstance(controller, RobotReplayController)
        self.assertTrue(result.ok)
        self.assertEqual(result.robot_zone_after, "nightstand")
        self.assertEqual(controller.command_log[0]["sim_steps"], 12)
        self.assertEqual(artifact.command_log[0]["message"], "approached pillow_1")

    def test_stage_truth_artifact_reads_final_usd_stage_values(self) -> None:
        bundle = build_isaac_replay_bundle(seed=42).to_wire()
        controller = StageReplayController.from_bundle(bundle)
        for command in bundle["compiled_commands"]:
            controller.execute(command, sim_steps=12)
        stage = _FakeUsdStage.from_controller(controller, bundle)
        stage.set_translation(
            bundle["scene_manifest"]["object_prims"]["wrapper_1"],
            pose_for_zone("closet"),
        )
        stage.set_attribute(
            bundle["scene_manifest"]["surface_prims"]["bed"],
            "softlife:dirt",
            0.2,
        )

        artifact = build_stage_truth_artifact(
            stage=stage,
            bundle_payload=bundle,
            controller=controller,
            adapter_name="stage_truth_test",
            action_count=len(bundle["compiled_commands"]),
            step_count=len(bundle["compiled_commands"]) * 12,
        )
        object_zones = {item.object_id: item.zone for item in artifact.object_states}
        surface_dirt = {item.zone: item.dirt_after for item in artifact.cleanliness}

        self.assertEqual(object_zones["wrapper_1"], "closet")
        self.assertEqual(surface_dirt["bed"], 0.2)
        self.assertEqual(artifact.invalid_actions, 0)
        self.assertEqual(len(artifact.command_log), len(bundle["compiled_commands"]))

    def test_unitree_controller_maps_commands_to_backend(self) -> None:
        bundle = build_isaac_replay_bundle(seed=42).to_wire()
        backend = _FakeUnitreeBackend(bundle)
        controller = UnitreeIsaacReplayController.from_bundle(bundle, backend=backend)

        for command in bundle["compiled_commands"][:4]:
            controller.execute(command, sim_steps=12)
        artifact = controller.to_artifact(
            adapter_name="unitree_test",
            action_count=4,
            step_count=48,
        )

        self.assertIsInstance(backend, UnitreeIsaacBackend)
        self.assertIsInstance(controller, RobotReplayController)
        self.assertEqual(
            backend.calls,
            ["approach_object", "grasp_object", "navigate_to_frame", "release_object"],
        )
        self.assertEqual(controller.command_log[1]["held_object_after"], "pillow_1")
        self.assertEqual(artifact.adapter_name, "unitree_test")
        self.assertEqual(artifact.object_states[0].zone, "bed")

    def test_simulated_unitree_backend_replays_full_bundle_artifact(self) -> None:
        bundle = build_isaac_replay_bundle(seed=42).to_wire()
        backend = SimulatedUnitreeBackend.from_bundle(bundle)
        controller = UnitreeIsaacReplayController.from_bundle(bundle, backend=backend)

        for command in bundle["compiled_commands"]:
            controller.execute(command, sim_steps=12)
        artifact = controller.to_artifact(
            adapter_name="unitree_isaac_replay_dry_run_v1",
            action_count=len(bundle["compiled_commands"]),
            step_count=len(bundle["compiled_commands"]) * 12,
        )
        room = RoomGenerator().generate(42)
        trajectory = Trajectory.from_wire(bundle["trajectory"])
        replay = replay_result_from_physics_artifact(
            initial_state=room,
            trajectory=trajectory,
            artifact=artifact,
        )
        score = RoomReadinessScorer().score(replay)
        object_zones = {item.object_id: item.zone for item in artifact.object_states}
        surface_dirt = {item.zone: item.dirt_after for item in artifact.cleanliness}

        self.assertIsInstance(backend, UnitreeIsaacBackend)
        self.assertEqual(artifact.adapter_name, "unitree_isaac_replay_dry_run_v1")
        self.assertEqual(artifact.action_count, len(bundle["compiled_commands"]))
        self.assertEqual(artifact.invalid_actions, 0)
        self.assertEqual(len(artifact.command_log), len(bundle["compiled_commands"]))
        self.assertEqual(
            artifact.command_log[0]["backend_name"],
            "simulated_unitree_backend_v1",
        )
        self.assertEqual(object_zones["wrapper_1"], "trash_bin")
        self.assertEqual(surface_dirt["bed"], 0.0)
        self.assertEqual(score.readiness, 97.679)

    def test_isaac_workflow_validation_writes_artifacts_for_seeds(self) -> None:
        with TemporaryDirectory() as tmpdir:
            report = validate_isaac_workflow(out_dir=tmpdir, seeds=(7, 42))
            report_wire = report.to_wire()

            self.assertTrue(report.ok)
            self.assertEqual(report_wire["schema_version"], "softlife.isaac_workflow_report.v1")
            self.assertEqual(report_wire["seeds"], [7, 42])
            self.assertFalse(report_wire["real_stage_requested"])
            for result in report.results:
                self.assertTrue(result.ok)
                self.assertTrue(result.bundle_path.exists())
                self.assertTrue(result.scene_path.exists())
                self.assertTrue(result.stage.artifact_path.exists())
                self.assertTrue(result.unitree_dry_run.artifact_path.exists())
                self.assertNotIn("private_seed", result.bundle_path.read_text(encoding="utf-8"))
                self.assertIn("def Xform", result.scene_path.read_text(encoding="utf-8"))
                self.assertEqual(result.stage.command_log_count, result.command_count)
                self.assertEqual(result.unitree_dry_run.command_log_count, result.command_count)
                self.assertEqual(result.stage.invalid_actions, 0)
                self.assertEqual(result.unitree_dry_run.invalid_actions, 0)
                self.assertGreater(result.stage.readiness or 0.0, 0.0)
                self.assertGreater(result.unitree_dry_run.readiness or 0.0, 0.0)

    def test_isaac_workflow_validation_requires_frames_when_requested(self) -> None:
        def fake_real_stage(bundle_payload: dict[str, object], **_: object) -> object:
            return SimpleNamespace(
                artifact=build_stage_level_artifact(bundle_payload),
                rendered_frames=(),
            )

        with TemporaryDirectory() as tmpdir:
            with patch(
                "integrations.isaac_lab.softlife_isaac_lab.workflow_validation."
                "run_isaac_sim_stage_replay",
                fake_real_stage,
            ):
                report = validate_isaac_workflow(
                    out_dir=tmpdir,
                    seeds=(42,),
                    real_stage=True,
                    capture_frames=True,
                )

        result = report.results[0]
        self.assertFalse(report.ok)
        self.assertFalse(result.stage.ok)
        self.assertTrue(result.unitree_dry_run.ok)
        self.assertEqual(result.stage.rendered_frame_count, 0)
        self.assertIn("no rendered frames", result.stage.error or "")

    def test_unitree_controller_fails_clearly_without_backend(self) -> None:
        bundle = build_isaac_replay_bundle(seed=42).to_wire()

        with self.assertRaises(UnitreeIsaacControllerUnavailable):
            UnitreeIsaacReplayController.from_bundle(bundle)

    def test_isaac_sim_stage_runner_fails_clearly_without_runtime(self) -> None:
        bundle = build_isaac_replay_bundle(seed=42).to_wire()
        if find_isaac_sim_package() is not None:
            self.skipTest("Isaac Sim is installed; runtime execution requires local GPU setup.")

        with self.assertRaises(IsaacSimRuntimeNotAvailable):
            run_isaac_sim_stage_replay(bundle)

    def test_isaac_lab_runner_fails_clearly_without_dependency(self) -> None:
        bundle = build_isaac_replay_bundle(seed=42).to_wire()
        if find_isaac_lab_package() is not None:
            self.skipTest("Isaac Lab is installed; runner implementation is intentionally pending.")

        with self.assertRaises(IsaacLabNotAvailable):
            run_replay_bundle(bundle)

    def test_replay_is_deterministic_and_does_not_mutate_private_state(self) -> None:
        room = RoomGenerator().generate(42)
        public = room.to_public()
        trajectory = HeuristicMiner().solve(public)
        adapter = MockSimulationAdapter()

        first = adapter.replay(room, trajectory)
        second = adapter.replay(room, trajectory)

        self.assertEqual(first.final_state, second.final_state)
        self.assertEqual(first.invalid_actions, second.invalid_actions)
        self.assertEqual(first.replay_hash, second.replay_hash)
        self.assertEqual(first.to_replay_log(), second.to_replay_log())
        self.assertEqual(room, RoomGenerator().generate(42))

    def test_validator_scores_same_trajectory_deterministically(self) -> None:
        validator = Validator()
        challenge = validator.issue_challenge(seed=101)
        miner = HeuristicMiner()
        trajectory = miner.solve(challenge.public_state)

        first = validator.evaluate(challenge.challenge_id, miner.miner_id, trajectory)
        second = validator.evaluate(challenge.challenge_id, miner.miner_id, trajectory)

        self.assertEqual(first.score, second.score)
        self.assertEqual(first.trajectory_hash, second.trajectory_hash)
        self.assertEqual(first.replay_summary.replay_hash, second.replay_summary.replay_hash)

    def test_invalid_actions_are_logged_and_penalized(self) -> None:
        validator = Validator()
        challenge = validator.issue_challenge(seed=5)

        bad_trajectory = Trajectory.from_actions(
            (
                Action.pick("missing_object"),
                Action.move_to_zone("missing_zone"),
                Action.dispose("wrapper_1"),
            )
        )
        bad_result = validator.evaluate(challenge.challenge_id, "bad_miner", bad_trajectory)
        noop_result = validator.evaluate(
            challenge.challenge_id,
            NoOpMiner().miner_id,
            NoOpMiner().solve(challenge.public_state),
        )

        self.assertEqual(bad_result.invalid_actions, 3)
        self.assertTrue(all(not event.ok for event in bad_result.replay_summary.events))
        self.assertLess(bad_result.score.readiness, noop_result.score.readiness)

    def test_scoring_caps(self) -> None:
        validator = Validator()
        challenge = validator.issue_challenge(seed=9)
        spam = Trajectory.from_actions(Action.pick("missing_object") for _ in range(50))
        result = validator.evaluate(challenge.challenge_id, "spam_miner", spam)

        self.assertGreaterEqual(result.score.readiness, 0.0)
        self.assertLessEqual(result.score.readiness, 100.0)
        self.assertEqual(clamp_score(-10.0), 0.0)
        self.assertEqual(clamp_score(110.0), 100.0)

    def test_leaderboard_ranks_and_normalizes_weights(self) -> None:
        validator = Validator()
        challenge = validator.issue_challenge(seed=42)
        leaderboard = Leaderboard()

        for miner in (NoOpMiner(), HeuristicMiner()):
            result = validator.evaluate(
                challenge.challenge_id,
                miner.miner_id,
                miner.solve(challenge.public_state),
            )
            leaderboard.update(result)

        ranking = leaderboard.ranking()
        weights = leaderboard.normalized_weights()

        self.assertEqual(ranking[0].miner_id, "heuristic_baseline")
        self.assertGreaterEqual(ranking[0].best_score, ranking[1].best_score)
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertGreater(weights["heuristic_baseline"], weights["noop"])

    def test_evaluation_wire_does_not_expose_private_environment(self) -> None:
        validator = Validator()
        challenge = validator.issue_challenge(seed=42)
        miner = HeuristicMiner()

        result = validator.evaluate(
            challenge.challenge_id,
            miner.miner_id,
            miner.solve(challenge.public_state),
        )
        result_json = json.dumps(result.to_wire(), sort_keys=True)

        self.assertNotIn("private_seed", result_json)
        self.assertNotIn("final_state", result_json)
        self.assertNotIn("hidden_object_count", result_json)


class _FakeUnitreeBackend:
    backend_name = "fake_unitree_backend"

    def __init__(self, bundle: dict[str, object]) -> None:
        self.bundle = bundle
        manifest = bundle["scene_manifest"]
        self.scene_root = manifest["root_prim"]
        self.object_prim = manifest["object_prims"]["pillow_1"]
        self.surface_prim = manifest["surface_prims"]["bed"]
        self.robot_zone = "entry"
        self.held_object_id: str | None = None
        self.object_zone = "nightstand"
        self.calls: list[str] = []

    def navigate_to_frame(
        self,
        *,
        target_frame: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        self.calls.append("navigate_to_frame")
        self.robot_zone = zone
        return self._result(f"navigated to {zone}", sim_steps)

    def approach_object(
        self,
        *,
        object_id: str,
        object_prim: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        self.calls.append("approach_object")
        self.robot_zone = self.object_zone
        return self._result(f"approached {object_id}", sim_steps)

    def grasp_object(
        self,
        *,
        object_id: str,
        object_prim: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        self.calls.append("grasp_object")
        self.held_object_id = object_id
        self.object_zone = "__held__"
        return self._result(f"grasped {object_id}", sim_steps)

    def release_object(
        self,
        *,
        object_id: str,
        target_frame: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        self.calls.append("release_object")
        self.held_object_id = None
        self.robot_zone = zone
        self.object_zone = zone
        return self._result(f"released {object_id} in {zone}", sim_steps)

    def drop_in_receptacle(
        self,
        *,
        object_id: str,
        target_frame: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        self.calls.append("drop_in_receptacle")
        self.held_object_id = None
        self.robot_zone = zone
        self.object_zone = zone
        return self._result(f"dropped {object_id} in {zone}", sim_steps)

    def wipe_surface(
        self,
        *,
        surface_prim: str,
        zone: str,
        sim_steps: int,
    ) -> BackendCommandResult:
        self.calls.append("wipe_surface")
        self.robot_zone = zone
        return self._result(f"wiped {zone}", sim_steps)

    def hold_position(self, *, sim_steps: int) -> BackendCommandResult:
        self.calls.append("hold_position")
        return self._result("held position", sim_steps)

    def snapshot(self) -> BackendSnapshot:
        return BackendSnapshot(
            room_id=self.bundle["challenge_id"],
            scene_root=self.scene_root,
            sim_seed=None,
            robot_zone=self.robot_zone,
            object_states=(
                ObjectPhysicsState(
                    object_id="pillow_1",
                    prim_path=self.object_prim,
                    target_zone="bed",
                    zone=None if self.object_zone == "__held__" else self.object_zone,
                    held=self.object_zone == "__held__",
                ),
            ),
            cleanliness=(
                CleanlinessMeasurement(
                    zone="bed",
                    surface_prim=self.surface_prim,
                    dirt_before=0.4,
                    dirt_after=0.4,
                    cleaned_area_fraction=0.0,
                ),
            ),
        )

    def _result(self, message: str, sim_steps: int) -> BackendCommandResult:
        return BackendCommandResult(
            ok=True,
            message=message,
            robot_zone_after=self.robot_zone,
            held_object_after=self.held_object_id,
            sim_steps=sim_steps,
        )


class _FakeUsdStage:
    def __init__(self, prims: dict[str, "_FakeUsdPrim"]) -> None:
        self.prims = prims

    @classmethod
    def from_controller(
        cls,
        controller: StageReplayController,
        bundle: dict[str, object],
    ) -> "_FakeUsdStage":
        manifest = bundle["scene_manifest"]
        prims: dict[str, _FakeUsdPrim] = {}
        for object_id, prim_path in manifest["object_prims"].items():
            zone = controller.state.object_zones[object_id]
            prims[prim_path] = _FakeUsdPrim(
                {"xformOp:translate": pose_for_zone(zone)}
            )
        for zone, prim_path in manifest["surface_prims"].items():
            prims[prim_path] = _FakeUsdPrim(
                {
                    "xformOp:translate": pose_for_zone(zone),
                    "softlife:dirt": controller.state.surface_dirt_after[zone],
                }
            )
        return cls(prims)

    def GetPrimAtPath(self, prim_path: str) -> "_FakeUsdPrim | None":
        return self.prims.get(prim_path)

    def set_translation(self, prim_path: str, value: tuple[float, float, float]) -> None:
        self.prims[prim_path].attributes["xformOp:translate"].value = value

    def set_attribute(self, prim_path: str, attr_name: str, value: object) -> None:
        self.prims[prim_path].attributes[attr_name] = _FakeUsdAttribute(value)


class _FakeUsdPrim:
    def __init__(self, attributes: dict[str, object]) -> None:
        self.attributes = {
            key: _FakeUsdAttribute(value)
            for key, value in attributes.items()
        }

    def GetAttribute(self, attr_name: str) -> "_FakeUsdAttribute | None":
        return self.attributes.get(attr_name)

    def IsValid(self) -> bool:
        return True


class _FakeUsdAttribute:
    def __init__(self, value: object) -> None:
        self.value = value

    def Get(self) -> object:
        return self.value

    def IsValid(self) -> bool:
        return True


if __name__ == "__main__":
    unittest.main()
