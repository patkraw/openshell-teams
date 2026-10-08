"""Channel Guard: compile a role's board rights (the harness's access rules plus its
endpoint map) into REST proxy rules, replacing any board rules a proposal carried."""

from __future__ import annotations

import copy
import fnmatch
from dataclasses import dataclass

ENTRY_NAME = "board"


class UnknownRole(ValueError):
    pass


@dataclass(frozen=True)
class Board:
    host: str
    port: int


def compile_board_entry(role: str, access_rules: dict, endpoint_map: dict, board: Board, *, binaries) -> dict:
    if role not in access_rules:
        raise UnknownRole(role)
    rules = [{"allow": {"method": endpoint_map[a]["method"], "path": endpoint_map[a]["path"]}}
             for a in access_rules[role]]
    return {"name": ENTRY_NAME,
            "endpoints": [{"host": board.host, "port": board.port, "protocol": "rest",
                           "enforcement": "enforce", "rules": rules}],
            "binaries": [{"path": b} for b in binaries]}


def _norm_host(host: str) -> str:
    return str(host).strip().lower().rstrip(".")


def reaches(endpoint: dict, host: str, port: int) -> bool:
    """Whether an endpoint selector can match host:port, the way OpenShell matches them:
    host names are case-insensitive (wildcards allowed), `ports` takes precedence over
    `port`, and no port at all matches any port."""
    pattern = _norm_host(endpoint.get("host", ""))
    if not fnmatch.fnmatchcase(_norm_host(host), pattern):
        return False
    ports = endpoint.get("ports")
    if ports:
        return int(port) in {int(p) for p in ports}
    return endpoint.get("port") is None or int(endpoint["port"]) == int(port)


def _drop_reaching(policies: dict, host: str, port: int) -> None:
    for name in list(policies):
        entry = policies[name]
        kept = [e for e in entry.get("endpoints", []) if not reaches(e, host, port)]
        if kept:
            entry["endpoints"] = kept
        else:
            del policies[name]


def apply(role: str, proposed: dict, access_rules: dict, endpoint_map: dict, board: Board, *, binaries) -> dict:
    """Drop every proposed endpoint that can reach the board and add the role's compiled entry."""
    out = copy.deepcopy(proposed)
    policies = out.setdefault("network_policies", {})
    _drop_reaching(policies, board.host, board.port)
    policies[ENTRY_NAME] = compile_board_entry(role, access_rules, endpoint_map, board, binaries=binaries)
    return out


def role_ceiling(role: str, boundary: dict, access_rules: dict, endpoint_map: dict, board: Board, *,
                 binaries, lead_only=()) -> dict:
    """The most an agent in `role` may have: the team boundary with the board entry narrowed
    to the role's rights, and lead-only entries (e.g. the Spawn Gate route) removed for
    every other role. Grants are proved against this, not against the raw boundary."""
    ceiling = apply(role, boundary, access_rules, endpoint_map, board, binaries=binaries)
    if role != "lead":
        for name in lead_only:
            ceiling.get("network_policies", {}).pop(name, None)
    return ceiling
