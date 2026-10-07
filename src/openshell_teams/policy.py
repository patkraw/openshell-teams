"""Policy handling for Spawn Gate: split what the prover can model from what it cannot,
check the rest by equality, force safe defaults, and bind the Passport middleware."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

UNMODELLED_PROTOCOLS = {"mcp", "json_rpc", "json-rpc", "graphql"}
NON_ROOT_USER = "1000"


class PolicyError(ValueError):
    pass


@dataclass
class Unmodelled:
    middlewares: dict = field(default_factory=dict)
    # (host, port, endpoint) for every endpoint whose protocol the prover cannot model
    mcp_endpoints: list = field(default_factory=list)


def split(policy: dict) -> tuple[dict, Unmodelled]:
    """Return (the part the prover can check, the part checked by equality)."""
    provable = copy.deepcopy(policy)
    unmodelled = Unmodelled(middlewares=provable.pop("network_middlewares", {}) or {})
    for name in list(provable.get("network_policies", {})):
        entry = provable["network_policies"][name]
        kept = []
        for endpoint in entry.get("endpoints", []):
            if endpoint.get("protocol") in UNMODELLED_PROTOCOLS:
                unmodelled.mcp_endpoints.append((endpoint["host"], endpoint["port"], endpoint))
            else:
                kept.append(endpoint)
        if kept:
            entry["endpoints"] = kept
        else:
            del provable["network_policies"][name]
    return provable, unmodelled


def _hostports(policy: dict) -> set[tuple[str, int]]:
    return {(e["host"], e["port"])
            for entry in policy.get("network_policies", {}).values()
            for e in entry.get("endpoints", [])}


def check_unmodelled(candidate: dict, ceiling: dict, *, fixed_middlewares: dict) -> list[str]:
    """Equality fallback. Returns a list of reasons to reject; empty means accepted."""
    errors = []
    cand_provable, cand_un = split(candidate)
    _, ceil_un = split(ceiling)
    if cand_un.middlewares != fixed_middlewares:
        errors.append("network middlewares must equal the team's fixed values")
    ceiling_mcp = [e for _, _, e in ceil_un.mcp_endpoints]
    for host, port, endpoint in cand_un.mcp_endpoints:
        if endpoint not in ceiling_mcp:
            errors.append(f"MCP endpoint {host}:{port} must equal, in full, an endpoint in the ceiling")
    mcp_servers = {(h, p) for h, p, _ in ceil_un.mcp_endpoints} | {(h, p) for h, p, _ in cand_un.mcp_endpoints}
    for host, port in _hostports(cand_provable) & mcp_servers:
        errors.append(f"{host}:{port} is an MCP server; only its full MCP endpoint may grant access")
    return errors


def force_safe_defaults(policy: dict) -> dict:
    safe = copy.deepcopy(policy)
    process = safe.setdefault("process", {})
    if str(process.get("run_as_user", NON_ROOT_USER)) == "0" or str(process.get("run_as_group", NON_ROOT_USER)) == "0":
        raise PolicyError("agents may not run as root")
    process.setdefault("run_as_user", NON_ROOT_USER)
    process.setdefault("run_as_group", NON_ROOT_USER)
    safe.setdefault("landlock", {})["compatibility"] = "hard_requirement"
    for entry in safe.get("network_policies", {}).values():
        for endpoint in entry.get("endpoints", []):
            if endpoint.get("protocol") in ("rest", *UNMODELLED_PROTOCOLS):
                endpoint["enforcement"] = "enforce"
    return safe


def passport_binding(board_host: str) -> dict:
    return {"passport": {"middleware": "passport", "order": 10, "on_error": "fail_closed",
                         "endpoints": {"include": [board_host]}}}


def with_passport(policy: dict, *, board_host: str) -> dict:
    bound = copy.deepcopy(policy)
    bound["network_middlewares"] = passport_binding(board_host)
    return bound
