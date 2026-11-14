"""Stdlib HTTP server: / serves the dashboard, /api/state the JSON snapshot."""
import json
import threading
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

INDEX = Path(__file__).parent / "static" / "index.html"


def serve(state, host="0.0.0.0", port=8000) -> ThreadingHTTPServer:
    """Start the server on a daemon thread and return it."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path  # ignore ?window=... (read by the page)
            if path == "/api/state":
                body, ctype = json.dumps(state.snapshot()).encode(), "application/json"
            elif path in ("/", "/index.html"):
                body, ctype = INDEX.read_bytes(), "text/html; charset=utf-8"
            else:
                return self.send_error(404)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep the console for detections
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[web] dashboard on http://{host}:{port}/")
    return server
