from openshell_teams import passport
from openshell_teams.gen import supervisor_middleware_pb2 as pb
from openshell_teams.middleware import PassportMiddleware


def _evaluation(sandbox_id="sb-1", sandbox="reviewer", host="host.openshell.internal", headers=()):
    return pb.HttpRequestEvaluation(
        phase=pb.SUPERVISOR_MIDDLEWARE_PHASE_PRE_CREDENTIALS,
        context=pb.RequestContext(request_id="r1", sandbox_id=sandbox_id, sandbox=sandbox),
        target=pb.HttpRequestTarget(scheme="http", host=host),
        headers=[pb.HttpHeader(name=n, value=v) for n, v in headers],
        middleware_name="passport",
    )


def test_describe_declares_protocol_1_0_and_one_request_binding(tmp_path):
    mw = PassportMiddleware(passport.load_or_create_keys(tmp_path), audience="board.local")
    manifest = mw.Describe(pb.MiddlewareDescribeRequest(), None)
    assert manifest.extension.protocol_version.major == 1
    assert manifest.extension.protocol_version.minor == 0
    [binding] = manifest.bindings
    assert binding.operation == pb.SUPERVISOR_MIDDLEWARE_OPERATION_HTTP_REQUEST
    assert binding.phase == pb.SUPERVISOR_MIDDLEWARE_PHASE_PRE_CREDENTIALS
    assert "openshell.supervisor-middleware.contract" in manifest.extension.supported_capabilities


def test_request_gets_a_passport_that_overwrites_any_agent_supplied_one(tmp_path):
    keys = passport.load_or_create_keys(tmp_path)
    mw = PassportMiddleware(keys, audience="board.local")
    result = mw.EvaluateHttpRequest(_evaluation(headers=[("X-OpenShell-Caller", "forged")]), None)
    assert result.decision == pb.DECISION_ALLOW
    [mutation] = result.header_mutations
    assert mutation.write.name == passport.HEADER
    assert mutation.write.on_existing == pb.EXISTING_HEADER_ACTION_OVERWRITE
    claims = passport.verify(mutation.write.value, keys.public, audience="board.local")
    assert claims["sbx"] == "sb-1"


def test_request_without_a_sandbox_id_is_denied(tmp_path):
    mw = PassportMiddleware(passport.load_or_create_keys(tmp_path), audience="board.local")
    result = mw.EvaluateHttpRequest(_evaluation(sandbox_id=""), None)
    assert result.decision == pb.DECISION_DENY
