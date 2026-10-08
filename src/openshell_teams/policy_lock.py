"""Policy Lock: a gateway interceptor (RFC 0010) that refuses changes which would widen a
team sandbox after Spawn Gate admitted it.

The gateway sends each selected control-plane call here before applying it (validate
phase, fail closed). Team membership comes from Spawn Gate's registry: a sandbox is
locked while its agent is not stopped. Not covered: ExecSandbox, a streaming call the
gateway cannot intercept."""

from __future__ import annotations

import argparse
import logging
import sqlite3
from concurrent import futures
from dataclasses import dataclass
from pathlib import Path

import grpc
from google.protobuf import json_format

from .gen import extension_pb2 as ext
from .gen import gateway_interceptor_pb2 as pb
from .gen import gateway_interceptor_pb2_grpc as pb_grpc

log = logging.getLogger(__name__)
NAME = "openshell-teams/policy-lock"
SERVICE = "openshell.v1.OpenShell"

# Calls that change one sandbox: its policy, credentials or ways in.
SANDBOX_METHODS = ("UpdateConfig", "AttachSandboxProvider", "DetachSandboxProvider", "CreateSshSession",
                   "ExposeService", "ApproveDraftChunk", "ApproveAllDraftChunks", "EditDraftChunk",
                   "UndoDraftChunk")
# Calls that change a provider every sandbox using it sees.
PROVIDER_METHODS = ("UpdateProvider", "RotateProviderCredential", "DeleteProvider",
                    "ConfigureProviderRefresh", "DeleteProviderRefresh")
# Provider profiles shape every provider's network entry.
PROFILE_METHODS = ("ImportProviderProfiles", "UpdateProviderProfiles", "DeleteProviderProfile")


@dataclass
class Live:
    sandboxes: set[str]
    providers: set[str]

    @classmethod
    def from_registry(cls, path: Path) -> "Live":
        # Opened read-only, so a missing registry raises instead of reading as "no teams".
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = db.execute("SELECT name, providers FROM agents a WHERE state != 'stopped' AND "
                              "id = (SELECT MAX(id) FROM agents b WHERE b.name = a.name)").fetchall()
        finally:
            db.close()
        return cls({name for name, _ in rows},
                   {p for _, ps in rows for p in (ps or "").split(",") if p})


def _strings(value) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set().union(*(_strings(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_strings(v) for v in value)) if value else set()
    return set()


def decide(method: str, op: dict, live: Live) -> tuple[bool, str]:
    if method in SANDBOX_METHODS:
        if method == "UpdateConfig" and op.get("global") and live.sandboxes:
            return False, "global policy is locked while a team is running"
        target = op.get("sandbox", "")
        if target in live.sandboxes:
            return False, f"{target!r} is a team sandbox: its policy and access are fixed at admission"
    elif method in PROVIDER_METHODS:
        used = sorted(_strings(op) & live.providers)
        if used:
            return False, f"provider {used[0]!r} is in use by a running team"
    elif method in PROFILE_METHODS and live.sandboxes:
        return False, "provider profiles are locked while a team is running"
    return True, ""


class PolicyLock(pb_grpc.GatewayInterceptorServicer):
    def __init__(self, registry_path: Path):
        self.registry_path = Path(registry_path)

    def Describe(self, request, context):
        methods = SANDBOX_METHODS + PROVIDER_METHODS + PROFILE_METHODS
        return pb.InterceptorManifest(
            name=NAME,
            failure_policy="fail_closed",
            bindings=[pb.InterceptorBinding(
                id=f"lock-{m}", selector=pb.InterceptorSelector(rpc=f"{SERVICE}/{m}"),
                phases=[pb.GATEWAY_INTERCEPTOR_PHASE_VALIDATE], failure_policy="fail_closed")
                for m in methods],
            extension=ext.PeerMetadata(
                protocol_version=ext.ProtocolVersion(major=1, minor=0),
                implementation_name=NAME, implementation_version="0.1.0",
                supported_capabilities=["openshell.gateway-interceptor.contract"],
            ),
        )

    def Evaluate(self, request, context):
        if not request.HasField("validate"):
            return pb.InterceptorResult(allowed=True)
        op = json_format.MessageToDict(request.validate.proposed_operation)
        try:
            live = Live.from_registry(self.registry_path)
        except sqlite3.Error as error:
            # Fail closed: without Spawn Gate's state, no team sandbox can be told apart.
            log.error("registry unavailable: %s", error)
            return pb.InterceptorResult(allowed=False, reason="Policy Lock: team state unavailable",
                                        status_code="UNAVAILABLE")
        allowed, reason = decide(request.method, op, live)
        who = dict(request.principal)
        log.info("%s %s by %s: %s", "allow" if allowed else "DENY", request.method,
                 who.get("subject") or who.get("sandbox_id") or who.get("kind"), reason)
        if allowed:
            return pb.InterceptorResult(allowed=True)
        return pb.InterceptorResult(allowed=False, reason=f"Policy Lock: {reason}",
                                    status_code="PERMISSION_DENIED",
                                    log_annotations={"policy_lock": "deny"})


def serve(registry_path: Path, port: int) -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    pb_grpc.add_GatewayInterceptorServicer_to_server(PolicyLock(registry_path), server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    log.info("policy lock on 127.0.0.1:%d, registry %s", port, registry_path)
    server.wait_for_termination()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registry", type=Path, required=True)
    p.add_argument("--port", type=int, default=50062)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    serve(a.registry, a.port)


if __name__ == "__main__":
    main()
