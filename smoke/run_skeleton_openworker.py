"""Walking skeleton: the operator creates a lead; the lead, from inside its sandbox, asks
Spawn Gate for a reviewer; the reviewer posts a comment on the board with its Passport.

Needs: gateway with the passport middleware, the middleware, refboard on :8765 and
Spawn Gate on :8766 running (see smoke/README.md)."""

from __future__ import annotations

import json
import shlex
import sys
import time
import uuid
from pathlib import Path

import httpx

STATE = Path.home() / "forks/.local/teams"
HERE = Path(__file__).parent

# bash-only HTTP over /dev/tcp (the base image has no curl or python)
HTTP = r'''
http() { # METHOD PORT PATH [BODY]  -> prints "<status> <body>"
  exec 3<>/dev/tcp/host.openshell.internal/$2 || { echo "connect failed"; return 1; }
  printf '%s %s HTTP/1.1\r\nHost: host.openshell.internal:%s\r\nContent-Type: application/json\r\nContent-Length: %s\r\nConnection: close\r\n\r\n%s' "$1" "$3" "$2" "${#4}" "$4" >&3
  local line status len=0
  IFS= read -r line <&3; status=${line#* }; status=${status%% *}
  while IFS= read -r line <&3; do line=${line%$'\r'}; [ -z "$line" ] && break
    case "${line,,}" in content-length:*) len=${line#*: };; esac; done
  local body=""; [ "$len" -gt 0 ] && body=$(head -c "$len" <&3)
  exec 3>&-; echo "$status $body"
}
'''


def reviewer_script() -> str:
    comment = json.dumps({"space": "proj", "id": 1, "body": "Reviewed: tests pass.", "author": "lead"})
    return HTTP + f"""
echo "reviewer: whoami"; http GET 8765 /v1/board/whoami; echo
echo "reviewer: comment (claims author=lead)"; http POST 8765 /v1/board/items/comment {shlex.quote(comment)}; echo
echo "reviewer: read another team's space"; http GET 8765 '/v1/board/items?space=other-team'; echo
echo "reviewer: try to assign (lead only)"; http POST 8765 /v1/board/items/assign '{{"space":"proj","id":1,"assignee":"reviewer"}}'; echo
echo "reviewer: try to reach Spawn Gate"; http POST 8766 /v1/agents '{{}}'; echo
"""


def lead_script() -> str:
    worker_policy = {"version": 1, "filesystem_policy": {
        "include_workdir": True,
        "read_only": ["/usr", "/lib", "/etc", "/var/log", "/proc", "/dev/urandom"],
        "read_write": ["/tmp", "/dev/null"]}}
    request = {"team": "proj", "name": "reviewer", "role": "worker", "policy": worker_policy,
               "task": "review item 42", "request_id": "lead-turn-1", "command": ["bash", "-c", reviewer_script()]}
    outside = dict(request, name="exfil", request_id="lead-turn-2", policy={"version": 1, "network_policies": {
        "exfil": {"endpoints": [{"host": "evil.example", "port": 443, "protocol": "rest",
                                 "rules": [{"allow": {"method": "*", "path": "/**"}}]}],
                  "binaries": [{"path": "/usr/bin/bash"}]}}})
    return HTTP + f"""
echo "lead: create an item"; http POST 8765 /v1/board/items '{{"space":"proj","title":"Fix the failing test","criteria":"tests pass"}}'; echo
echo "lead: assign it to reviewer"; http POST 8765 /v1/board/items/assign '{{"space":"proj","id":1,"assignee":"reviewer"}}'; echo
echo "lead: ask Spawn Gate for a reviewer"; http POST 8766 /v1/agents {shlex.quote(json.dumps(request))}; echo
echo "lead: ask for a worker outside the boundary"; http POST 8766 /v1/agents {shlex.quote(json.dumps(outside))}; echo
sleep 600
"""


def main() -> None:
    op = {"X-Operator-Token": (STATE / "operator.token").read_text().strip()}
    gate = "http://127.0.0.1:8766"
    r = httpx.post(f"{gate}/v1/teams", headers=op, timeout=600, json={
        "team": "proj", "charter_dir": str(HERE / "charter-openworker"), "lead_name": "lead",
        "lead_command": ["bash", "-c", lead_script()], "request_id": f"team-{uuid.uuid4()}"})
    print("create team + lead:", r.status_code, r.text)
    if r.status_code != 200:
        sys.exit(1)
    for _ in range(90):
        rv = httpx.get(f"{gate}/v1/agents/reviewer", headers=op, timeout=10)
        if rv.status_code == 200 and rv.json()["state"] == "running":
            break
        time.sleep(3)
    print("reviewer:", rv.status_code, rv.text[:300])
    time.sleep(15)
    logs = STATE / "gate/logs"
    for name in ("lead", "reviewer"):
        f = logs / f"{name}.log"
        print(f"--- {name} sandbox output ---")
        print(f.read_text()[-1500:] if f.exists() else "(no output yet)")


if __name__ == "__main__":
    main()
