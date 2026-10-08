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
from .registry import LimitReached, NameInUse, ParentNotRunning, Registry, RequestIdReused

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
    kind: str = "staffing"            # one of KINDS
    providers: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)   # what to start in the sandbox
    persona: str = ""                                  # the harness persona to run, e.g. reviewer
    approval_id: str = ""                              # the user's approval, when the team requires one

    def digest(self) -> str:
        """Identity of the request for retries: every field that changes what would run."""
        body = json.dumps({"team": self.team, "name": self.name, "role": self.role, "policy": self.policy,
                           "providers": sorted(self.providers), "task": self.task, "kind": self.kind,
                           "command": self.command, "persona": self.persona,
                           "approval_id": self.approval_id}, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()


KINDS = ("lead", "staffing", "delegation")


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
        # A closed set: every other value is refused before anything is reserved.
        if req.kind not in KINDS:
            raise Rejected(f"unknown request kind {req.kind!r}", "bad_kind")
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
        if not charter.runtime_command:
            # Agents never choose what runs in a sandbox; without the team's runtime there
            # is nothing trusted to run.
            raise Rejected("this team defines no runtime for its agents", "no_runtime")
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
    def _ceiling(self, role: str, charter: TeamCharter) -> dict:
        """The most an agent in `role` may have, with the team's fixed middleware."""
        ceiling = channel_guard.role_ceiling(role, charter.boundary, charter.access_rules, charter.endpoint_map,
                                             charter.board, binaries=charter.board_binaries,
                                             lead_only=charter.lead_only)
        return policy.with_passport(ceiling, board_host=charter.board.host)

    def _prove(self, candidate: dict, ceiling: dict) -> str:
        provable, _ = policy.split(candidate)
        ceiling_provable, _ = policy.split(ceiling)
        verdict, _detail = self.prover.check(provable, ceiling_provable)
        return verdict

    def _check(self, grant: dict, req: AgentRequest, role: str, charter: TeamCharter) -> None:
        ceiling = self._ceiling(role, charter)
        errors = policy.check_unmodelled(grant, ceiling,
                                         fixed_middlewares=policy.passport_binding(charter.board.host))
        if errors:
            raise Rejected("; ".join(errors), "unmodelled_rules")
        bad = sorted(set(req.providers) - set(charter.credentials))
        if bad:
            raise Rejected(f"providers outside the team boundary: {bad}", "providers")
        verdict = self._prove(grant, ceiling)
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
        except ParentNotRunning as error:
            raise Rejected("the requesting agent is stopping", "parent_stopping") from error
        if slot["retry"]:
            if slot.get("error_code"):
                # The same request was refused before: refuse it the same way again.
                raise Rejected(slot["error_reason"] or "", slot["error_code"])
            return slot
        try:
            return self._admit_reserved(req, slot, parent, charter)
        except Rejected as error:
            self._abandon(req.name, error.code, error.reason)
            raise
        except Exception as error:
            self._abandon(req.name, "creation_failed", str(error))
            raise Rejected(f"creation failed: {error}", "creation_failed") from error

    def _step(self, name: str, from_state: str, to_state: str, **fields) -> None:
        """Advance one step, unless a stop got there first."""
        if not self.registry.transition(name, (from_state,), to_state, **fields):
            raise Rejected("stopped while being created", "parent_stopping")

    def _admit_reserved(self, req: AgentRequest, slot: dict, parent: str, charter: TeamCharter) -> dict:
        if charter.require_approval and req.kind == "staffing":
            # Before anything is resolved or defaulted: the digest covers exactly what was sent.
            if not req.approval_id or self.approvals is None:
                raise Rejected("this team requires the user's approval for each worker", "approval_required")
            try:
                # Bound to the lead's sandbox, not just its name: a replacement lead with
                # the same name cannot use approvals given to its predecessor.
                self.approvals.consume(req.approval_id, team=req.team, lead=parent, worker=req.name,
                                       digest=approval_digest(req), lead_instance=slot["caller"])
            except Exception as error:
                raise Rejected(f"approval refused: {error}", "approval_refused") from error
        role = slot["role"]
        if charter.runtime_command and (req.kind != "lead" or not req.command):
            # Agents never choose what runs in a sandbox: the team's runtime decides.
            req.command = charter.command_for(name=req.name, persona=req.persona, role=role)
        if not req.providers and not (charter.require_approval and req.kind == "staffing"):
            # An approved worker gets exactly the providers the user approved.
            req.providers = list(charter.default_providers)
        grant = self._resolve(req, charter)
        self._check(grant, req, role, charter)
        self._step(req.name, "reserved", "creating", providers=",".join(req.providers),
                   grant_hash=grant_hash(grant), grant_json=json.dumps(grant, sort_keys=True))
        sandbox = self.openshell.create(req.name, grant, providers=req.providers,
                                        labels={"team": req.team, "role": role})
        self._step(req.name, "creating", "created", sandbox_id=sandbox["id"],
                   generation=sandbox.get("generation"))
        # Launched = checked: the policy OpenShell runs must equal the admitted grant,
        # apart from what OpenShell itself adds for attached providers, and those
        # additions must still be within the role's ceiling.
        launched = self.openshell.effective_policy(req.name)
        differences = policy.launch_differences(grant, launched, providers=req.providers)
        if differences:
            raise Rejected("launched policy differs from the admitted grant: " + "; ".join(differences),
                           "launch_check")
        verdict = self._prove(launched, self._ceiling(role, charter))
        if verdict != "within_boundary":
            raise Rejected(f"launched policy is not within the boundary: {verdict}", "launch_check")
        self.board.register(sandbox_id=sandbox["id"], team=req.team, name=req.name, role=role)
        self._step(req.name, "created", "registered")
        self._step(req.name, "registered", "starting")
        if req.command:
            self.openshell.start(req.name, req.command)
        self._step(req.name, "starting", "running")
        return {**self.registry.get(req.name), "retry": False}

    def _remove(self, name: str) -> bool:
        """Take an agent's identity away, then its sandbox. True when both are gone."""
        row = self.registry.get(name) or {}
        try:
            if row.get("sandbox_id"):
                self.board.deregister(sandbox_id=row["sandbox_id"])
            # By name, so a sandbox whose id was never recorded is deleted too.
            self.openshell.delete(name)
            return True
        except Exception as error:
            log.error("cleanup of %s failed: %s", name, error)
            return False

    def _abandon(self, name: str, code: str, reason: str) -> None:
        state = (self.registry.get(name) or {}).get("state")
        needs_delete = state not in ("reserved",)
        if needs_delete and not self._remove(name):
            self.registry.update(name, state="cleanup_failed", error_code=code, error_reason=reason)
        elif state in ("stopping", "stopped"):
            self.registry.update(name, state="stopped", error_code=code, error_reason=reason)
        else:
            self.registry.reject(name, code, reason)

    # -- Cascade Stop -----------------------------------------------------------------
    def stop(self, name: str) -> list[str]:
        """Children first. Each agent loses its board identity, then its sandbox. An agent
        still being admitted is marked stopping, so its admission cleans up after itself."""
        order = self.registry.begin_stop(name)
        for n in order:
            if self.registry.get(n).get("state") != "stopping":
                continue
            self.registry.update(n, state="stopped" if self._remove(n) else "cleanup_failed")
        return order
