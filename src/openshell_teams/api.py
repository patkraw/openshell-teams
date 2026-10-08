"""Spawn Gate HTTP API (creation service).

Operators (the trusted harness server on the host) register teams and create leads;
agents ask for workers with their Sandbox Passport."""

from __future__ import annotations

import argparse
import logging
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import charter as charter_mod
from . import passport
from .boardclient import ApprovalClient, BoardRegistrar
from .gate import AgentRequest, Caller, Rejected, SpawnGate
from .openshell import OpenShellCLI
from .prover import Prover
from .registry import Registry

OPERATOR_HEADER = "X-Operator-Token"
log = logging.getLogger(__name__)


class TeamIn(BaseModel):
    team: str
    charter_dir: str
    lead_name: str = "lead"
    lead_command: list[str] = Field(default_factory=list)
    lead_persona: str = ""
    providers: list[str] = Field(default_factory=list)
    request_id: str


class AgentIn(BaseModel):
    team: str
    name: str
    role: str
    policy: dict
    task: str
    request_id: str
    kind: str = "staffing"
    providers: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    persona: str = ""
    approval_id: str = ""


def create_app(gate: SpawnGate, public_key, audience: str, operator_token: str) -> FastAPI:
    app = FastAPI()

    def operator(token: str = Header("", alias=OPERATOR_HEADER)) -> Caller:
        if not secrets.compare_digest(token, operator_token):
            raise HTTPException(403, "operator only")
        return Caller("operator")

    def agent(request: Request) -> Caller:
        try:
            claims = passport.verify(request.headers.get(passport.HEADER, ""), public_key, audience=audience)
        except passport.InvalidPassport as error:
            raise HTTPException(401, f"no valid Sandbox Passport: {error}")
        return Caller("agent", claims.get("name"), claims["sbx"])

    def run(req: AgentRequest, caller: Caller) -> dict:
        try:
            row = gate.admit(req, caller)
        except Rejected as error:
            log.info("rejected %s for %s: %s (%s)", req.name, caller, error.reason, error.code)
            raise HTTPException(403, {"code": error.code, "reason": error.reason})
        log.info("admitted %s (%s) sandbox=%s", row["name"], row["role"], row["sandbox_id"])
        return {k: row[k] for k in ("name", "team", "role", "parent", "state", "sandbox_id", "grant_hash")}

    @app.post("/v1/teams")
    def create_team(body: TeamIn, caller: Caller = Depends(operator)):
        charter = charter_mod.load(Path(body.charter_dir), body.team)
        gate.charters[body.team] = charter
        gate.registry.add_team(body.team, max_workers=charter.max_workers)
        return run(AgentRequest(body.team, body.lead_name, "lead", {}, "lead the team", body.request_id,
                                kind="lead", command=body.lead_command, persona=body.lead_persona,
                                providers=body.providers), caller)

    @app.get("/v1/teams/{team}/boundary")
    def boundary(team: str, caller: Caller = Depends(agent)):
        """What a team member may ask for: the team boundary, by name. Used by the lead to
        build workers' proposed policies from the boundary's own pieces."""
        me = gate.registry.by_sandbox(caller.sandbox_id or "")
        charter = gate.charters.get(team)
        if not me or not charter or me["team"] != team or me["state"] != "running":
            raise HTTPException(403, "not a running member of this team")
        policy = charter.boundary
        board = (charter.board.host, charter.board.port)
        return {
            "team": team,
            "filesystem_policy": policy.get("filesystem_policy", {}),
            # Full entries, so a proposal can copy them exactly as the prover expects.
            "network_policies": {name: entry for name, entry in policy.get("network_policies", {}).items()
                                 if all((e["host"], e["port"]) != board for e in entry.get("endpoints", []))},
            "providers": charter.credentials,
            "roles": sorted(r for r in charter.access_rules if r != "lead"),
            "max_workers": charter.max_workers,
        }

    @app.post("/v1/agents")
    def create_agent(body: AgentIn, caller: Caller = Depends(agent)):
        return run(AgentRequest(**body.model_dump()), caller)

    @app.post("/v1/agents/{name}/stop")
    def stop(name: str, caller: Caller = Depends(operator)):
        return {"stopped": gate.stop(name)}

    @app.get("/v1/agents/{name}")
    def get(name: str, caller: Caller = Depends(operator)):
        row = gate.registry.get(name)
        if not row:
            raise HTTPException(404)
        return row

    return app


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser(description="Spawn Gate (creation service)")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--keys", type=Path, required=True)
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--openshell", required=True)
    p.add_argument("--prover", required=True)
    p.add_argument("--board-admin-url", required=True)
    p.add_argument("--board-admin-token-file", type=Path, required=True)
    p.add_argument("--operator-token-file", type=Path, required=True)
    p.add_argument("--prover-timeout", type=int, default=90, help="seconds; a timeout is a rejection")
    p.add_argument("--image", default=None, help="sandbox image for every agent (default: OpenShell's base image)")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    a.state.mkdir(parents=True, exist_ok=True)
    gate = SpawnGate({}, Registry(a.state / "registry.db"), Prover(a.prover, a.prover_timeout),
                     OpenShellCLI(a.openshell, a.state / "logs", image=a.image),
                     BoardRegistrar(a.board_admin_url, a.board_admin_token_file.read_text().strip()),
                     ApprovalClient(a.board_admin_url, a.board_admin_token_file.read_text().strip()))
    keys = passport.load_or_create_keys(a.keys)
    app = create_app(gate, keys.public, passport.audience_for("host.openshell.internal", a.port),
                     a.operator_token_file.read_text().strip())
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="info")


if __name__ == "__main__":
    main()
