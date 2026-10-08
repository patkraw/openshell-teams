import copy

import pytest

from openshell_teams import policy

BOARD = {"host": "host.openshell.internal", "port": 8765}


def rest(host, port, rules, enforcement="enforce"):
    return {"host": host, "port": port, "protocol": "rest", "enforcement": enforcement, "rules": rules}


def mcp(host, port, tools):
    return {"host": host, "port": port, "protocol": "mcp", "enforcement": "enforce",
            "rules": [{"allow": {"method": "tools/call", "tool": t}} for t in tools]}


def base(**network):
    return {"version": 1,
            "filesystem_policy": {"read_only": ["/usr"], "read_write": ["/tmp"]},
            "network_policies": {k: {"endpoints": v, "binaries": [{"path": "/usr/bin/python3"}]}
                                 for k, v in network.items()}}


# --- splitting what the prover can model from what it cannot ---------------------------

def test_split_removes_middlewares_and_mcp_endpoints_from_the_provable_part():
    p = base(github=[rest("api.github.com", 443, [{"allow": {"method": "GET", "path": "/**"}}])],
             tools=[mcp("mcp.local", 9000, ["read"])])
    p["network_middlewares"] = {"passport": {"middleware": "passport", "order": 10}}
    provable, unmodelled = policy.split(p)
    assert "network_middlewares" not in provable
    assert "tools" not in provable["network_policies"]
    assert "github" in provable["network_policies"]
    assert unmodelled.middlewares == p["network_middlewares"]
    assert len(unmodelled.mcp_endpoints) == 1


def test_split_does_not_change_the_input():
    p = base(tools=[mcp("mcp.local", 9000, ["read"])])
    before = copy.deepcopy(p)
    policy.split(p)
    assert p == before


# --- equality fallback for what the prover cannot model ----------------------------------

def test_mcp_endpoint_equal_to_one_in_the_ceiling_is_accepted():
    ceiling = base(tools=[mcp("mcp.local", 9000, ["read", "write"])])
    candidate = base(tools=[mcp("mcp.local", 9000, ["read", "write"])])
    assert policy.check_unmodelled(candidate, ceiling, fixed_middlewares={}) == []


def test_narrowed_mcp_endpoint_is_rejected_because_it_cannot_be_proven():
    ceiling = base(tools=[mcp("mcp.local", 9000, ["read", "write"])])
    candidate = base(tools=[mcp("mcp.local", 9000, ["read"])])
    assert policy.check_unmodelled(candidate, ceiling, fixed_middlewares={})


def test_plain_rule_on_an_mcp_server_host_is_rejected():
    ceiling = base(tools=[mcp("mcp.local", 9000, ["read"])])
    candidate = base(tools=[rest("mcp.local", 9000, [{"allow": {"method": "*", "path": "/**"}}])])
    errors = policy.check_unmodelled(candidate, ceiling, fixed_middlewares={})
    assert any("mcp.local:9000" in e for e in errors)


def test_middlewares_must_equal_the_team_fixed_value():
    fixed = {"passport": {"middleware": "passport", "order": 10}}
    candidate = base()
    candidate["network_middlewares"] = {"other": {"middleware": "other", "order": 1}}
    assert policy.check_unmodelled(candidate, base(), fixed_middlewares=fixed)
    candidate["network_middlewares"] = copy.deepcopy(fixed)
    assert policy.check_unmodelled(candidate, base(), fixed_middlewares=fixed) == []


# --- safe defaults --------------------------------------------------------------------

def test_safe_defaults_enforce_rest_and_require_landlock_and_non_root():
    p = base(github=[rest("api.github.com", 443, [{"allow": {"method": "GET", "path": "/**"}}],
                          enforcement="audit")])
    safe = policy.force_safe_defaults(p)
    assert safe["landlock"]["compatibility"] == "hard_requirement"
    assert safe["process"]["run_as_user"] != "0"
    assert safe["network_policies"]["github"]["endpoints"][0]["enforcement"] == "enforce"


def test_root_process_is_refused():
    p = base()
    p["process"] = {"run_as_user": "0", "run_as_group": "0"}
    with pytest.raises(policy.PolicyError):
        policy.force_safe_defaults(p)


# --- Passport binding -----------------------------------------------------------------

def test_passport_middleware_is_bound_to_the_board_host():
    p = policy.with_passport(base(), board_host="host.openshell.internal")
    entry = p["network_middlewares"]["passport"]
    assert entry["middleware"] == "passport"
    assert entry["on_error"] == "fail_closed"
    assert entry["endpoints"]["include"] == ["host.openshell.internal"]


# --- review findings -----------------------------------------------------------------------

def test_mcp_endpoint_with_a_wider_binary_scope_is_rejected():
    """Review finding 4: equality compared endpoints but dropped the entry's binaries;
    an empty binary list means any binary."""
    ceiling = base(tools=[mcp("mcp.local", 9000, ["read"])])
    candidate = base(tools=[mcp("mcp.local", 9000, ["read"])])
    candidate["network_policies"]["tools"]["binaries"] = []
    assert policy.check_unmodelled(candidate, ceiling, fixed_middlewares={})


def test_mcp_endpoint_with_the_same_binaries_in_another_order_is_accepted():
    ceiling = base(tools=[mcp("mcp.local", 9000, ["read"])])
    ceiling["network_policies"]["tools"]["binaries"] = [{"path": "/a"}, {"path": "/b"}]
    candidate = copy.deepcopy(ceiling)
    candidate["network_policies"]["tools"]["binaries"] = [{"path": "/b"}, {"path": "/a"}]
    assert policy.check_unmodelled(candidate, ceiling, fixed_middlewares={}) == []


def test_launched_policy_may_add_only_provider_entries_and_middleware_names():
    grant = base(github=[rest("api.github.com", 443, [{"allow": {"method": "GET", "path": "/**"}}])])
    grant["network_middlewares"] = {"passport": {"middleware": "passport", "order": 10}}
    launched = copy.deepcopy(grant)
    launched["network_middlewares"]["passport"]["name"] = "passport"
    launched["network_policies"]["_provider_openworker_nvidia"] = {
        "name": "_provider_openworker_nvidia", "endpoints": [rest("inference.example", 443, [])]}
    assert policy.launch_differences(grant, launched, providers=["openworker-nvidia"]) == []


def test_launched_policy_with_extra_access_differs_from_the_grant():
    """Review finding 5: read-back must equal the admitted grant, not just fit the boundary."""
    grant = base()
    grant["network_middlewares"] = {"passport": {"middleware": "passport", "order": 10}}
    wider = copy.deepcopy(grant)
    wider["network_policies"]["github"] = {"endpoints": [rest("api.github.com", 443, [])]}
    assert policy.launch_differences(grant, wider, providers=[])
    unbound = copy.deepcopy(grant)
    del unbound["network_middlewares"]
    assert policy.launch_differences(grant, unbound, providers=[])
    stray = copy.deepcopy(grant)
    stray["network_policies"]["_provider_other"] = {"endpoints": [rest("x.example", 443, [])]}
    assert policy.launch_differences(grant, stray, providers=[])
