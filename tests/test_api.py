import copy

from fastapi.testclient import TestClient

from openshell_teams import passport
from openshell_teams.api import create_app
from openshell_teams.gate import AgentRequest, Caller
from test_gate import world  # noqa: F401  (fixture)

AUD = "host.openshell.internal:8766"


def test_boundary_is_shown_to_team_members_without_the_board(world, tmp_path):  # noqa: F811
    gate, reg, *_ = world
    keys = passport.load_or_create_keys(tmp_path)
    client = TestClient(create_app(gate, keys.public, AUD, "op"))
    lead_sid = reg.get("lead")["sandbox_id"]
    headers = {passport.HEADER: passport.sign(keys.private, sandbox_id=lead_sid, sandbox="lead", audience=AUD)}
    r = client.get("/v1/teams/t1/boundary", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "github" in body["network_policies"] and "board" not in body["network_policies"]
    assert body["roles"] == ["worker"]


def test_boundary_is_refused_to_outsiders(world, tmp_path):  # noqa: F811
    gate, *_ = world
    keys = passport.load_or_create_keys(tmp_path)
    client = TestClient(create_app(gate, keys.public, AUD, "op"))
    headers = {passport.HEADER: passport.sign(keys.private, sandbox_id="sb-stranger", sandbox="x", audience=AUD)}
    assert client.get("/v1/teams/t1/boundary", headers=headers).status_code == 403


def test_boundary_offers_workers_no_lead_only_entries_and_names_default_providers(world, tmp_path):  # noqa: F811
    gate, reg, *_ = world
    charter = gate.charters["t1"]
    charter.boundary = copy.deepcopy(charter.boundary)
    charter.boundary["network_policies"]["spawn"] = {"endpoints": [{"host": "host.openshell.internal", "port": 8766}]}
    charter.default_providers = ["anthropic"]
    keys = passport.load_or_create_keys(tmp_path)
    client = TestClient(create_app(gate, keys.public, AUD, "op"))
    lead_sid = reg.get("lead")["sandbox_id"]
    headers = {passport.HEADER: passport.sign(keys.private, sandbox_id=lead_sid, sandbox="lead", audience=AUD)}
    body = client.get("/v1/teams/t1/boundary", headers=headers).json()
    assert "spawn" not in body["network_policies"]
    assert body["default_providers"] == ["anthropic"]
