import pytest
from fastapi.testclient import TestClient

from openshell_teams import passport, refboard

AUD = "host.openshell.internal:8765"
RULES = {"lead": ["read", "comment"], "worker": ["read", "comment"], "observer": ["read"]}


@pytest.fixture
def setup(tmp_path):
    keys = passport.load_or_create_keys(tmp_path)
    client = TestClient(refboard.create_app(keys.public, AUD, "admin-secret", RULES))
    admin = {refboard.ADMIN_HEADER: "admin-secret"}
    client.post("/v1/admin/agents", headers=admin,
                json={"sandbox_id": "sb-r", "team": "t1", "name": "reviewer", "role": "worker"})

    def as_(sandbox_id, audience=AUD):
        return {passport.HEADER: passport.sign(keys.private, sandbox_id=sandbox_id, sandbox="x", audience=audience)}

    return client, admin, as_


def test_comment_author_comes_from_the_passport_not_the_body(setup):
    client, _, as_ = setup
    r = client.post("/v1/board/items/comment", headers=as_("sb-r"),
                    json={"item": "42", "text": "looks good", "author": "lead"})
    assert r.status_code == 200 and r.json()["author"] == "reviewer"


def test_request_without_a_passport_is_refused(setup):
    client, _, _ = setup
    assert client.get("/v1/board/whoami").status_code == 401


def test_unregistered_sandbox_is_refused(setup):
    client, _, as_ = setup
    assert client.get("/v1/board/whoami", headers=as_("sb-unknown")).status_code == 403


def test_passport_for_another_service_is_refused(setup):
    client, _, as_ = setup
    assert client.get("/v1/board/whoami", headers=as_("sb-r", "host.openshell.internal:8766")).status_code == 401


def test_deregistered_agent_loses_access_immediately(setup):
    client, admin, as_ = setup
    client.delete("/v1/admin/agents/sb-r", headers=admin)
    assert client.get("/v1/board/whoami", headers=as_("sb-r")).status_code == 403


def test_registration_requires_the_admin_token(setup):
    client, _, _ = setup
    r = client.post("/v1/admin/agents", json={"sandbox_id": "x", "team": "t1", "name": "x", "role": "lead"})
    assert r.status_code == 403
