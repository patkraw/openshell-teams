from google.protobuf import json_format

from openshell_teams.gen import gateway_interceptor_pb2 as pb
from openshell_teams.policy_lock import Live, PolicyLock, decide
from openshell_teams.registry import Registry

LIVE = Live(sandboxes={"lead", "reviewer"}, providers={"openworker-nvidia"})


def test_policy_change_on_a_team_sandbox_is_refused():
    allowed, reason = decide("UpdateConfig", {"sandbox": "reviewer", "policy": {}}, LIVE)
    assert not allowed and "reviewer" in reason


def test_policy_change_on_another_sandbox_is_allowed():
    assert decide("UpdateConfig", {"sandbox": "scratch", "policy": {}}, LIVE)[0]


def test_global_policy_change_is_refused_while_a_team_runs():
    assert not decide("UpdateConfig", {"global": True, "policy": {}}, LIVE)[0]
    assert decide("UpdateConfig", {"global": True, "policy": {}}, Live(set(), set()))[0]


def test_attaching_a_provider_to_a_team_sandbox_is_refused():
    assert not decide("AttachSandboxProvider", {"sandbox": "lead", "provider": "github"}, LIVE)[0]


def test_ssh_sessions_and_exposed_services_into_team_sandboxes_are_refused():
    assert not decide("CreateSshSession", {"sandbox": "lead"}, LIVE)[0]
    assert not decide("ExposeService", {"sandbox": "reviewer", "name": "web"}, LIVE)[0]


def test_policy_advisor_approvals_on_team_sandboxes_are_refused():
    assert not decide("ApproveAllDraftChunks", {"sandbox": "reviewer"}, LIVE)[0]


def test_changing_a_provider_a_team_uses_is_refused():
    assert not decide("UpdateProvider", {"provider": {"name": "openworker-nvidia"}}, LIVE)[0]
    assert not decide("RotateProviderCredential", {"provider": "openworker-nvidia"}, LIVE)[0]
    assert decide("UpdateProvider", {"provider": {"name": "other"}}, LIVE)[0]


def test_provider_profiles_are_frozen_while_a_team_runs():
    assert not decide("UpdateProviderProfiles", {"id": "openai"}, LIVE)[0]
    assert decide("UpdateProviderProfiles", {"id": "openai"}, Live(set(), set()))[0]


def test_creating_and_deleting_sandboxes_is_not_policy_lock_s_business():
    assert decide("CreateSandbox", {"name": "x"}, LIVE)[0]
    assert decide("DeleteSandbox", {"name": "reviewer"}, LIVE)[0]


def test_live_reads_running_agents_and_their_providers(tmp_path):
    reg = Registry(tmp_path / "registry.db")
    reg.add_team("t", max_workers=2)
    reg.reserve("t", caller="operator", request_id="1", digest="d", name="lead", role="lead",
                parent=None, counts=False)
    reg.update("lead", state="running", providers="openworker-nvidia")
    reg.reserve("t", caller="sb", request_id="2", digest="d", name="old", role="worker", parent="lead")
    reg.update("old", state="stopped")
    live = Live.from_registry(tmp_path / "registry.db")
    assert live.sandboxes == {"lead"} and live.providers == {"openworker-nvidia"}


def test_evaluate_denies_through_the_grpc_servicer(tmp_path):
    reg = Registry(tmp_path / "registry.db")
    reg.add_team("t", max_workers=2)
    reg.reserve("t", caller="operator", request_id="1", digest="d", name="lead", role="lead",
                parent=None, counts=False)
    reg.update("lead", state="running")
    lock = PolicyLock(tmp_path / "registry.db")
    ev = pb.InterceptorEvaluation(service="openshell.v1.OpenShell", method="UpdateConfig",
                                  principal={"kind": "user", "subject": "someone"})
    json_format.ParseDict({"sandbox": "lead", "policy": {}}, ev.validate.proposed_operation)
    result = lock.Evaluate(ev, None)
    assert not result.allowed and result.status_code == "PERMISSION_DENIED"
    manifest = lock.Describe(pb.DescribeRequest(), None)
    assert "openshell.gateway-interceptor.contract" in manifest.extension.supported_capabilities
    assert all(b.failure_policy == "fail_closed" for b in manifest.bindings)
