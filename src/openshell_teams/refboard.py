"""Reference board: a minimal board service for harnesses without one, and for tests.

Agents are known only after Spawn Gate registers them; every agent request must carry a
valid Sandbox Passport for this service, from a registered sandbox."""

from __future__ import annotations

import argparse
import secrets
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from . import passport

ADMIN_HEADER = "X-Board-Admin"


class Registration(BaseModel):
    sandbox_id: str
    team: str
    name: str
    role: str


class Comment(BaseModel):
    item: str
    text: str
    author: str | None = None   # ignored: the author comes from the Passport


def create_app(public_key, audience: str, admin_token: str, access_rules: dict) -> FastAPI:
    app = FastAPI()
    lock = threading.Lock()
    agents: dict[str, Registration] = {}
    comments: list[dict] = []

    def admin(token: str = Header("", alias=ADMIN_HEADER)):
        if not secrets.compare_digest(token, admin_token):
            raise HTTPException(403, "admin only")

    def caller(request: Request) -> Registration:
        try:
            claims = passport.verify(request.headers.get(passport.HEADER, ""), public_key, audience=audience)
        except passport.InvalidPassport as error:
            raise HTTPException(401, f"no valid Sandbox Passport: {error}")
        with lock:
            reg = agents.get(claims["sbx"])
        if not reg:
            raise HTTPException(403, "sandbox is not registered")
        return reg

    def allowed(reg: Registration, action: str) -> None:
        if action not in access_rules.get(reg.role, []):
            raise HTTPException(403, f"role {reg.role} may not {action}")

    @app.post("/v1/admin/agents", dependencies=[Depends(admin)])
    def register(reg: Registration):
        with lock:
            agents[reg.sandbox_id] = reg
        return {"ok": True}

    @app.delete("/v1/admin/agents/{sandbox_id}", dependencies=[Depends(admin)])
    def deregister(sandbox_id: str):
        with lock:
            agents.pop(sandbox_id, None)
        return {"ok": True}

    @app.get("/v1/board/whoami")
    def whoami(reg: Registration = Depends(caller)):
        allowed(reg, "read")
        return reg.model_dump()

    @app.get("/v1/board/items")
    def items(reg: Registration = Depends(caller)):
        allowed(reg, "read")
        with lock:
            return [c for c in comments if c["team"] == reg.team]

    @app.post("/v1/board/items/comment")
    def comment(body: Comment, reg: Registration = Depends(caller)):
        allowed(reg, "comment")
        entry = {"team": reg.team, "item": body.item, "text": body.text, "author": reg.name}
        with lock:
            comments.append(entry)
        return entry

    return app


def main() -> None:
    import uvicorn
    import yaml

    parser = argparse.ArgumentParser()
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--audience", default=None, help="defaults to host.openshell.internal:<port>")
    parser.add_argument("--admin-token-file", type=Path, required=True)
    parser.add_argument("--access-rules", type=Path, required=True)
    args = parser.parse_args()
    keys = passport.load_or_create_keys(args.keys)
    rules = yaml.safe_load(args.access_rules.read_text())["roles"]
    audience = args.audience or passport.audience_for("host.openshell.internal", args.port)
    app = create_app(keys.public, audience, args.admin_token_file.read_text().strip(), rules)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
