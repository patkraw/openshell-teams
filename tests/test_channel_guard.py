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


@pytest.mark.parametrize("endpoint", [
    {"host": "HOST.OPENSHELL.INTERNAL", "port": 8765},
    {"host": "host.openshell.internal.", "port": 8765},
    {"host": "host.openshell.internal", "ports": [8765, 9999]},
    {"host": "host.openshell.internal"},
])
def test_equivalent_board_selectors_are_removed_too(endpoint):
    """Review finding 3: only a literal host/port match was removed."""
    proposed = {"network_policies": {"sneaky": {
        "endpoints": [{**endpoint, "protocol": "rest", "rules": [{"allow": {"method": "*", "path": "/**"}}]}],
        "binaries": [{"path": "/usr/bin/python3"}]}}}
    out = channel_guard.apply("worker", proposed, ACCESS, ENDPOINTS, BOARD, binaries=["/usr/bin/python3"])
    assert set(out["network_policies"]) == {"board"}


def test_role_ceiling_gives_the_board_entry_only_the_roles_rights():
    boundary = {"network_policies": {
        "board": {"endpoints": [{"host": BOARD.host, "port": BOARD.port, "protocol": "rest",
                                 "rules": [{"allow": {"method": "*", "path": "/v1/board/**"}}]}]},
        "spawn": {"endpoints": [{"host": BOARD.host, "port": 8766, "protocol": "rest", "rules": []}]},
        "model": {"endpoints": [{"host": "api.example", "port": 443}]}}}
    worker = channel_guard.role_ceiling("worker", boundary, ACCESS, ENDPOINTS, BOARD,
                                        binaries=["/usr/bin/python3"], lead_only=["spawn"])
    assert set(worker["network_policies"]) == {"board", "model"}
    assert rules_of(worker["network_policies"]["board"]) == [("GET", "/v1/board/**"),
                                                             ("POST", "/v1/board/items/comment")]
    lead = channel_guard.role_ceiling("lead", boundary, ACCESS, ENDPOINTS, BOARD,
                                      binaries=["/usr/bin/python3"], lead_only=["spawn"])
    assert "spawn" in lead["network_policies"]
