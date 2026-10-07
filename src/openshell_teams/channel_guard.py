"""Channel Guard: compile a role's board rights (the harness's access rules plus its
endpoint map) into REST proxy rules, replacing any board rules a proposal carried."""

from __future__ import annotations

import copy
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


def apply(role: str, proposed: dict, access_rules: dict, endpoint_map: dict, board: Board, *, binaries) -> dict:
    """Drop every proposed rule for the board host and add the role's compiled entry."""
    out = copy.deepcopy(proposed)
    policies = out.setdefault("network_policies", {})
    for name in list(policies):
        entry = policies[name]
        kept = [e for e in entry.get("endpoints", []) if (e["host"], e["port"]) != (board.host, board.port)]
        if kept:
            entry["endpoints"] = kept
        else:
            del policies[name]
    policies[ENTRY_NAME] = compile_board_entry(role, access_rules, endpoint_map, board, binaries=binaries)
    return out
