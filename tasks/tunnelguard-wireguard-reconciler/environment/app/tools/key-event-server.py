#!/usr/bin/env python3
"""Serve deterministic key-event fixtures for local tunnelguard runs."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


with open(os.environ.get("EVENT_FILE", "/app/data/events.json"), encoding="utf-8") as handle:
    EVENTS = json.load(handle)


class Handler(BaseHTTPRequestHandler):
    """Return the selected peer's event list."""

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/v1/events":
            self.send_error(404)
            return
        peer_id = parse_qs(parsed.query).get("peer_id", [""])[0]
        body = json.dumps(EVENTS.get(peer_id, []), separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        """Keep fixture-server output quiet."""


ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "8765"))), Handler).serve_forever()
