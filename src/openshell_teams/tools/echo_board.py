"""A tiny stand-in board for smoke tests: reports whether the request carried a valid Passport."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .. import passport


def make_handler(public_key, audience):
    class Handler(BaseHTTPRequestHandler):
        def _reply(self):
            token = self.headers.get(passport.HEADER, "")
            try:
                claims = passport.verify(token, public_key, audience=audience)
                body = {"passport": "valid", "sandbox_id": claims["sbx"], "name": claims["name"]}
            except passport.InvalidPassport as error:
                body = {"passport": "invalid", "error": str(error), "raw": token[:24]}
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = _reply

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--audience", default="host.openshell.internal:18765")
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    keys = passport.load_or_create_keys(args.keys)
    HTTPServer(("127.0.0.1", args.port), make_handler(keys.public, args.audience)).serve_forever()


if __name__ == "__main__":
    main()
