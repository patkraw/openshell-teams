"""Spawn Gate: admission for every new agent.

authorize the caller -> resolve the grant -> check it (prover + equality fallback + other
checks) -> create the sandbox without starting the agent -> read the policy back and check
again -> register the agent with the board -> start it.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field

from . import channel_guard, policy
from .charter import TeamCharter
from .registry import LimitReached, NameInUse, Registry, RequestIdReused

log = logging.getLogger(__name__)


class Rejected(Exception):
    def __init__(self, reason: str, code: str):
        super().__init__(reason)
        self.reason, self.code = reason, code


@dataclass(frozen=True)
class Caller:
    """Who is asking. kind: 'operator' (trusted harness server on the host) or 'agent'."""
    kind: str
    name: str | None = None
    sandbox_id: str | None = None


@dataclass
class AgentRequest:
    team: str
    name: str
    role: str
    policy: dict
    task: str
    request_id: str
    kind: str = "staffing"            # staffing | delegation | lead
    providers: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)   # what to start in the sandbox
    persona: str = ""                                  # the harness persona to run, e.g. reviewer
    approval_id: str = ""                              # the user's approval, when the team requires one

    def digest(self) -> str:
        body = json.dumps({"name": self.name, "role": self.role, "policy": self.policy,
                           "providers": sorted(self.providers), "task": self.task,
                           "kind": self.kind}, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()


def approval_digest(req: "AgentRequest") -> str:
    """What the user approved for one worker; the harness computes the same digest."""
    canonical = {"name": req.name, "role": req.role, "persona": req.persona, "policy": req.policy,
                 "providers": sorted(req.providers)}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def grant_hash(grant: dict) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(grant, sort_keys=True).encode()).hexdigest()


class SpawnGate:
    def __init__(self, charters: dict[str, TeamCharter], registry: Registry, prover, openshell, board,
                 approvals=None):
        self.charters, self.registry = charters, registry
        self.prover, self.openshell, self.board = prover, openshell, board
        self.approvals = approvals   # consumes approval IDs with the harness (None: not supported)

    # -- step 2: authorize ------------------------------------------------------------
    def _authorize(self, req: AgentRequest, caller: Caller, charter: TeamCharter) -> str:
        if req.kind == "lead":
            if caller.kind != "operator":
                raise Rejected("only the trusted harness server may create a team's lead", "not_authorized")
            return "operator"
        if caller.kind != "agent":
            raise Rejected("workers are requested by an agent", "not_authorized")
        me = self.registry.by_sandbox(caller.sandbox_id or "")
        if not me or me["team"] != req.team or me["state"] != "running":
            raise Rejected("caller is not a running agent of this team", "not_authorized")
        if self.registry.is_stopping(me["name"]):
            raise Rejected("caller is stopping", "parent_stopping")
        if req.kind == "staffing" and me["role"] != "lead":
            raise Rejected("only the team's lead may staff workers", "not_authorized")
        if req.kind == "delegation":
            raise Rejected("delegation is not enabled for this team", "not_authorized")
        if req.role not in charter.access_rules or req.role == "lead":
            raise Rejected(f"unknown or reserved role {req.role!r}", "bad_role")
        return me["name"]

    # -- step 3: resolve --------------------------------------------------------------
    def _resolve(self, req: AgentRequest, charter: TeamCharter) -> dict:
        proposed = charter.lead_policy if req.kind == "lead" else req.policy
        role = "lead" if req.kind == "lead" else req.role
        guarded = channel_guard.apply(role, proposed, charter.access_rules, charter.endpoint_map,
                                      charter.board, binaries=charter.board_binaries)
        try:
            safe = policy.force_safe_defaults(guarded)
        except policy.PolicyError as error:
            raise Rejected(str(error), "unsafe_policy") from error
        return policy.with_passport(safe, board_host=charter.board.host)

    # -- step 4: check ----------------------------------------------------------------
    def _check(self, grant: dict, req: AgentRequest, charter: TeamCharter) -> None:
        ceiling = policy.with_passport(charter.boundary, board_host=charter.board.host)
        errors = policy.check_unmodelled(grant, ceiling,
                                         fixed_middlewares=policy.passport_binding(charter.board.host))
        if errors:
            raise Rejected("; ".join(errors), "unmodelled_rules")
        bad = sorted(set(req.providers) - set(charter.credentials))
        if bad:
            raise Rejected(f"providers outside the team boundary: {bad}", "providers")
        provable, _ = policy.split(grant)
        ceiling_provable, _ = policy.split(ceiling)
        verdict, detail = self.prover.check(provable, ceiling_provable)
        if verdict != "within_boundary":
            raise Rejected(f"prover: {verdict}", f"prover_{verdict}")

    # -- the whole admission ----------------------------------------------------------
    def admit(self, req: AgentRequest, caller: Caller) -> dict:
        charter = self.charters.get(req.team)
        if not charter:
            raise Rejected(f"unknown team {req.team}", "unknown_team")
        parent = self._authorize(req, caller, charter)
        try:
            slot = self.registry.reserve(
                req.team, caller=caller.sandbox_id or caller.kind, request_id=req.request_id,
                digest=req.digest(), name=req.name, role="lead" if req.kind == "lead" else req.role,
                parent=None if req.kind == "lead" else parent, counts=req.kind != "lead")
        except LimitReached as error:
            raise Rejected(str(error), "limit") from error
        except RequestIdReused as error:
            raise Rejected("request ID reused for a different request", "request_id_reused") from error
        except NameInUse as error:
            raise Rejected(f"an agent named {req.name!r} is already running", "name_in_use") from error
        if slot["retry"]:
            return slot
        if charter.require_approval and req.kind == "staffing":
            # Before anything is resolved or defaulted: the digest covers exactly what was sent.
            try:
                if not req.approval_id or self.approvals is None:
                    raise Rejected("this team requires the user's approval for each worker", "approval_required")
                self.approvals.consume(req.approval_id, team=req.team, lead=parent, worker=req.name,
                                       digest=approval_digest(req))
            except Rejected:
                self.registry.update(req.name, state="stopped")
                raise
            except Exception as error:
                self.registry.update(req.name, state="stopped")
                raise Rejected(f"approval refused: {error}", "approval_refused") from error
        role = slot["role"]
        if charter.runtime_command and (caller.kind == "agent" or not req.command):
            # Agents never choose what runs in a sandbox: the team's runtime decides.
            req.command = charter.command_for(name=req.name, persona=req.persona, role=role)
        if not req.providers:
            req.providers = list(charter.default_providers)
        try:
            grant = self._resolve(req, charter)
            self._check(grant, req, charter)
            sandbox = self.openshell.create(req.name, grant, providers=req.providers,
                                            labels={"team": req.team, "role": slot["role"]})
            self.registry.update(req.name, state="created", sandbox_id=sandbox["id"],
                                 generation=sandbox.get("generation"), grant_hash=grant_hash(grant),
                                 grant_json=json.dumps(grant, sort_keys=True))
            launched = self.openshell.effective_policy(req.name)
            launched_provable, _ = policy.split(launched)
            ceiling_provable, _ = policy.split(policy.with_passport(charter.boundary, board_host=charter.board.host))
            verdict, _ = self.prover.check(launched_provable, ceiling_provable)
            if verdict != "within_boundary":
                raise Rejected(f"launched policy is not within the boundary: {verdict}", "launch_check")
            self.board.register(sandbox_id=sandbox["id"], team=req.team, name=req.name, role=slot["role"])
            self.registry.update(req.name, state="registered")
            if req.command:
                self.openshell.start(req.name, req.command)
            self.registry.update(req.name, state="running")
        except Rejected:
            self._abandon(req.name)
            raise
        except Exception as error:
            self._abandon(req.name)
            raise Rejected(f"creation failed: {error}", "creation_failed") from error
        return {**self.registry.get(req.name), "retry": False}

    def _abandon(self, name: str) -> None:
        row = self.registry.get(name)
        if row and row.get("sandbox_id"):
            try:
                self.board.deregister(sandbox_id=row["sandbox_id"])
            finally:
                self.openshell.delete(name)
        self.registry.update(name, state="stopped")

    # -- Cascade Stop -----------------------------------------------------------------
    def stop(self, name: str) -> list[str]:
        order = self.registry.begin_stop(name)
        for n in order:
            row = self.registry.get(n)
            if row.get("sandbox_id"):
                self.board.deregister(sandbox_id=row["sandbox_id"])
                self.openshell.delete(n)
            self.registry.update(n, state="stopped")
        return order
