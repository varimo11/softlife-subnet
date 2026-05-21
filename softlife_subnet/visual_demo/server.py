from __future__ import annotations

import argparse
import json
import mimetypes
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from softlife_subnet.visual_demo.data import build_visual_demo


STATIC_DIR = Path(__file__).with_name("static")


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    seed: int = 42,
) -> ThreadingHTTPServer:
    handler_class = _make_handler(seed)
    return ThreadingHTTPServer((host, port), handler_class)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Soft Life visual subnet demo.")
    parser.add_argument("--seed", type=int, default=42, help="Validator-private demo seed.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to serve on.")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Start the server without opening a browser.",
    )
    args = parser.parse_args()

    server = create_server(host=args.host, port=args.port, seed=args.seed)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/?seed={args.seed}"
    print(f"Soft Life visual demo running at {url}")
    print("Press Ctrl+C to stop.")

    if not args.no_open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping visual demo.")
    finally:
        server.server_close()


def _make_handler(default_seed: int) -> Callable[..., BaseHTTPRequestHandler]:
    class VisualDemoHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path in {"", "/"}:
                self._serve_static("index.html")
                return
            if parsed.path == "/api/demo":
                seed = _seed_from_query(parsed.query, default_seed)
                self._serve_json(build_visual_demo(seed))
                return

            relative_path = parsed.path.lstrip("/")
            if not relative_path or ".." in Path(relative_path).parts:
                self.send_error(404)
                return
            self._serve_static(relative_path)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _serve_json(self, payload: object) -> None:
            encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _serve_static(self, relative_path: str) -> None:
            path = (STATIC_DIR / relative_path).resolve()
            try:
                path.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self.send_error(404)
                return
            if not path.is_file():
                self.send_error(404)
                return

            content = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return VisualDemoHandler


def _seed_from_query(query: str, default_seed: int) -> int:
    values = urllib.parse.parse_qs(query)
    raw_seed = values.get("seed", [str(default_seed)])[0]
    try:
        return int(raw_seed)
    except ValueError:
        return default_seed
