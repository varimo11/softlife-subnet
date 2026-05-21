from __future__ import annotations

import json
import threading
import unittest
import urllib.request

from softlife_subnet.visual_demo import build_visual_demo
from softlife_subnet.visual_demo.server import create_server


class VisualDemoTests(unittest.TestCase):
    def test_visual_payload_contains_required_room_objects(self) -> None:
        payload = build_visual_demo(seed=42)
        display_kinds = {obj["display_kind"] for obj in payload["objects"]}

        self.assertTrue({"Towel", "Cup", "Pillow", "Trash", "Bottle"} <= display_kinds)
        self.assertEqual(payload["active_miner_id"], "heuristic_baseline")
        self.assertGreater(len(payload["layout"]), 0)

    def test_visual_timeline_comes_from_replay_steps(self) -> None:
        payload = build_visual_demo(seed=42)
        active_miner = payload["miners"][0]
        timeline = payload["timeline"]

        self.assertEqual(len(timeline), len(active_miner["trajectory"]) + 1)
        self.assertEqual(timeline[0]["step"], 0)
        self.assertEqual(timeline[-1]["score"], active_miner["score"])
        self.assertEqual(timeline[-1]["invalid_actions"], active_miner["invalid_actions"])

    def test_visual_timeline_moves_objects_between_zones(self) -> None:
        payload = build_visual_demo(seed=42)
        first_frame = payload["timeline"][0]
        final_frame = payload["timeline"][-1]
        first_locations = {
            obj["object_id"]: obj["display_zone"]
            for obj in first_frame["objects"]
        }
        final_locations = {
            obj["object_id"]: obj["display_zone"]
            for obj in final_frame["objects"]
        }

        moved_objects = [
            object_id
            for object_id, start_zone in first_locations.items()
            if final_locations[object_id] != start_zone
        ]
        self.assertGreaterEqual(len(moved_objects), 1)

    def test_visual_weights_are_normalized(self) -> None:
        payload = build_visual_demo(seed=7)

        self.assertAlmostEqual(sum(payload["weights"].values()), 1.0)
        self.assertGreater(payload["weights"]["heuristic_baseline"], 0.0)
        self.assertGreater(payload["weights"]["noop"], 0.0)

    def test_visual_server_serves_html_and_demo_json(self) -> None:
        try:
            server = create_server(port=0, seed=42)
        except PermissionError as exc:
            self.skipTest(f"local socket binding is blocked in this sandbox: {exc}")

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address[:2]
        base_url = f"http://{host}:{port}"

        try:
            with urllib.request.urlopen(f"{base_url}/", timeout=3) as response:
                html = response.read().decode("utf-8")
            with urllib.request.urlopen(f"{base_url}/api/demo?seed=7", timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

        self.assertIn("Soft Life Visual Subnet Demo", html)
        self.assertEqual(payload["seed"], 7)
        self.assertIn("timeline", payload)


if __name__ == "__main__":
    unittest.main()
