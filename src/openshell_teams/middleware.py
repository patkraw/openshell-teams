"""Passport middleware: an OpenShell supervisor middleware (RFC 0009) that stamps every
board request with a Sandbox Passport, overwriting any value the agent sent."""

from __future__ import annotations

import argparse
import logging
from concurrent import futures
from pathlib import Path

import grpc

from . import passport
from .gen import extension_pb2 as ext
from .gen import supervisor_middleware_pb2 as pb
from .gen import supervisor_middleware_pb2_grpc as pb_grpc

NAME = "passport"
log = logging.getLogger(__name__)


class PassportMiddleware(pb_grpc.SupervisorMiddlewareServicer):
    def __init__(self, keys: passport.Keys, audience: str):
        self.keys = keys
        self.audience = audience

    def Describe(self, request, context):
        return pb.MiddlewareManifest(
            name=NAME,
            service_version="0.1.0",
            bindings=[pb.MiddlewareBinding(
                operation=pb.SUPERVISOR_MIDDLEWARE_OPERATION_HTTP_REQUEST,
                phase=pb.SUPERVISOR_MIDDLEWARE_PHASE_PRE_CREDENTIALS,
                max_payload_bytes=65536,
            )],
            extension=ext.PeerMetadata(
                protocol_version=ext.ProtocolVersion(major=1, minor=0),
                implementation_name="openshell-teams/passport",
                implementation_version="0.1.0",
                supported_capabilities=["openshell.supervisor-middleware.contract"],
            ),
        )

    def ValidateConfig(self, request, context):
        return pb.ValidateConfigResponse(valid=True)

    def EvaluateHttpRequest(self, request, context):
        sandbox_id = request.context.sandbox_id
        if not sandbox_id:
            return pb.HttpRequestResult(decision=pb.DECISION_DENY, reason="no sandbox id",
                                        reason_code="passport.no_sandbox")
        token = passport.sign(self.keys.private, sandbox_id=sandbox_id,
                              sandbox=request.context.sandbox, audience=self.audience)
        log.info("passport for sandbox=%s name=%s host=%s", sandbox_id, request.context.sandbox,
                 request.target.host)
        return pb.HttpRequestResult(
            decision=pb.DECISION_ALLOW,
            header_mutations=[pb.HeaderMutation(write=pb.WriteHeader(
                name=passport.HEADER, value=token,
                on_existing=pb.EXISTING_HEADER_ACTION_OVERWRITE))],
        )


def serve(keys_dir: Path, audience: str, port: int) -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    pb_grpc.add_SupervisorMiddlewareServicer_to_server(
        PassportMiddleware(passport.load_or_create_keys(keys_dir), audience), server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    log.info("passport middleware on 127.0.0.1:%d (audience %s)", port, audience)
    server.wait_for_termination()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sandbox Passport middleware")
    parser.add_argument("--keys", type=Path, required=True)
    parser.add_argument("--audience", default="board.local")
    parser.add_argument("--port", type=int, default=50061)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    serve(args.keys, args.audience, args.port)


if __name__ == "__main__":
    main()
