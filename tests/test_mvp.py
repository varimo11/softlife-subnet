from __future__ import annotations

import json
import unittest

from softlife_subnet.actions import Action, ActionType, Trajectory
from softlife_subnet.leaderboard import Leaderboard
from softlife_subnet.miners import HeuristicMiner, NoOpMiner
from softlife_subnet.room_generator import RoomGenerator
from softlife_subnet.scoring import clamp_score
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


if __name__ == "__main__":
    unittest.main()
