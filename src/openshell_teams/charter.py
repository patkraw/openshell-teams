"""Team Charter: the user-supplied team boundary, lead policy, and the harness's
board access rules and endpoint map."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .channel_guard import Board


@dataclass
class TeamCharter:
    team: str
    boundary: dict                 # OpenShell policy: the ceiling for every agent on the team
    credentials: list[str]         # providers any agent may receive
    max_workers: int
    max_depth: int
    lead_policy: dict
    access_rules: dict             # role -> [actions]
    endpoint_map: dict             # action -> {method, path}
    board: Board
    board_binaries: list[str] = field(default_factory=lambda: ["/usr/bin/python3"])
    # How agents are started: a command template ({team}, {name}, {persona}, {role}) and the
    # providers agents get by default. Set by the operator, not by agents.
    runtime_command: list[str] = field(default_factory=list)
    default_providers: list[str] = field(default_factory=list)
    require_approval: bool = False   # each worker needs a single-use approval ID from the user

    def command_for(self, *, name: str, persona: str, role: str) -> list[str]:
        values = {"team": self.team, "name": name, "persona": persona or role, "role": role}
        return [part.format(**values) for part in self.runtime_command]


def load(directory: Path, team: str) -> TeamCharter:
    d = Path(directory)
    boundary = yaml.safe_load((d / "team-boundary.yaml").read_text())
    lead = d / "lead-policy.yaml"
    access = yaml.safe_load((d / "access-rules.yaml").read_text())
    endpoints = yaml.safe_load((d / "endpoint-map.yaml").read_text())
    host, port = endpoints["service"].rsplit(":", 1)
    limits = boundary.get("limits", {})
    runtime_file = d / "runtime.yaml"
    runtime = yaml.safe_load(runtime_file.read_text()) if runtime_file.exists() else {}
    return TeamCharter(
        team=team,
        boundary=boundary["policy"],
        credentials=list(boundary.get("credentials", [])),
        max_workers=int(limits.get("max_workers", 2)),
        max_depth=int(limits.get("max_depth", 1)),
        lead_policy=yaml.safe_load(lead.read_text()) if lead.exists() else boundary["policy"],
        access_rules=access["roles"],
        endpoint_map=endpoints["actions"],
        board=Board(host=host, port=int(port)),
        board_binaries=list(endpoints.get("binaries", ["/usr/bin/python3"])),
        runtime_command=list(runtime.get("command", [])),
        default_providers=list(runtime.get("providers", [])),
        require_approval=bool(runtime.get("require_approval", False)),
    )
