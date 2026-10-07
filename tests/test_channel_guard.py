import pytest

from openshell_teams import channel_guard

ACCESS = {"lead": ["read", "comment", "assign"], "worker": ["read", "comment"]}
ENDPOINTS = {
    "read": {"method": "GET", "path": "/v1/board/**"},
    "comment": {"method": "POST", "path": "/v1/board/items/comment"},
    "assign": {"method": "POST", "path": "/v1/board/items/assign"},
}
BOARD = channel_guard.Board(host="host.openshell.internal", port=8765)


def rules_of(entry):
    return [(r["allow"]["method"], r["allow"]["path"]) for r in entry["endpoints"][0]["rules"]]


def test_worker_gets_only_its_roles_actions():
    entry = channel_guard.compile_board_entry("worker", ACCESS, ENDPOINTS, BOARD, binaries=["/usr/bin/python3"])
    assert rules_of(entry) == [("GET", "/v1/board/**"), ("POST", "/v1/board/items/comment")]
    endpoint = entry["endpoints"][0]
    assert (endpoint["host"], endpoint["port"], endpoint["protocol"], endpoint["enforcement"]) == \
        ("host.openshell.internal", 8765, "rest", "enforce")
    assert entry["binaries"] == [{"path": "/usr/bin/python3"}]


def test_lead_gets_assign():
    entry = channel_guard.compile_board_entry("lead", ACCESS, ENDPOINTS, BOARD, binaries=["/usr/bin/python3"])
    assert ("POST", "/v1/board/items/assign") in rules_of(entry)


def test_unknown_role_is_refused():
    with pytest.raises(channel_guard.UnknownRole):
        channel_guard.compile_board_entry("admin", ACCESS, ENDPOINTS, BOARD, binaries=[])


def test_apply_replaces_any_board_rules_the_proposal_carried():
    proposed = {"network_policies": {
        "sneaky": {"endpoints": [{"host": "host.openshell.internal", "port": 8765, "protocol": "rest",
                                  "rules": [{"allow": {"method": "*", "path": "/**"}}]}],
                   "binaries": [{"path": "/usr/bin/python3"}]},
        "github": {"endpoints": [{"host": "api.github.com", "port": 443, "protocol": "rest",
                                  "rules": [{"allow": {"method": "GET", "path": "/**"}}]}],
                   "binaries": [{"path": "/usr/bin/git"}]}}}
    out = channel_guard.apply("worker", proposed, ACCESS, ENDPOINTS, BOARD, binaries=["/usr/bin/python3"])
    assert set(out["network_policies"]) == {"github", channel_guard.ENTRY_NAME}
    assert ("POST", "/v1/board/items/assign") not in rules_of(out["network_policies"][channel_guard.ENTRY_NAME])
