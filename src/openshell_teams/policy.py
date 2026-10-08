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
    # (host, port, endpoint, binaries) for every endpoint whose protocol the prover cannot
    # model; binaries are the enclosing entry's, sorted (an empty tuple means any binary)
    mcp_endpoints: list = field(default_factory=list)


def _binaries(entry: dict) -> tuple:
    return tuple(sorted(str(b.get("path", "")) for b in entry.get("binaries", []) or []))


def split(policy: dict) -> tuple[dict, Unmodelled]:
    """Return (the part the prover can check, the part checked by equality)."""
    provable = copy.deepcopy(policy)
    unmodelled = Unmodelled(middlewares=provable.pop("network_middlewares", {}) or {})
    for name in list(provable.get("network_policies", {})):
        entry = provable["network_policies"][name]
        kept = []
        for endpoint in entry.get("endpoints", []):
            if endpoint.get("protocol") in UNMODELLED_PROTOCOLS:
                unmodelled.mcp_endpoints.append((endpoint["host"], endpoint["port"], endpoint, _binaries(entry)))
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
    ceiling_mcp = [(e, b) for _, _, e, b in ceil_un.mcp_endpoints]
    for host, port, endpoint, binaries in cand_un.mcp_endpoints:
        if (endpoint, binaries) not in ceiling_mcp:
            errors.append(f"MCP endpoint {host}:{port} must equal, in full and with the same binaries,"
                          " an endpoint in the ceiling")
    mcp_servers = {(h, p) for h, p, *_ in ceil_un.mcp_endpoints} | {(h, p) for h, p, *_ in cand_un.mcp_endpoints}
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


PROVIDER_ENTRY_PREFIX = "_provider_"


def provider_entry_name(provider: str) -> str:
    return PROVIDER_ENTRY_PREFIX + provider.replace("-", "_")


def _diff(a, b, path: str, out: list) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in b:
                out.append(f"{path}/{k} missing at launch")
            elif k not in a:
                out.append(f"{path}/{k} added at launch")
            else:
                _diff(a[k], b[k], f"{path}/{k}", out)
    elif a != b:
        out.append(f"{path} changed at launch")


def launch_differences(grant: dict, launched: dict, *, providers) -> list[str]:
    """What differs between the grant Spawn Gate admitted and the policy OpenShell launched.
    The only accepted additions are what OpenShell 0.1.2 adds itself: one network entry per
    attached provider (`_provider_<name>`) and a `name` field on each middleware binding."""
    seen = copy.deepcopy(launched)
    for key, binding in (seen.get("network_middlewares") or {}).items():
        if isinstance(binding, dict) and binding.get("name") == key:
            del binding["name"]
    expected = {provider_entry_name(p) for p in providers}
    out: list[str] = []
    for key in list(seen.get("network_policies") or {}):
        if key.startswith(PROVIDER_ENTRY_PREFIX):
            if key in expected:
                del seen["network_policies"][key]
            else:
                out.append(f"/network_policies/{key} is not from an attached provider")
    _diff(grant, seen, "", out)
    return out
