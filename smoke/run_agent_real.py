"""REAL MODEL: the reviewer is a real `openworker agent` (OpenWorker image, NVIDIA inference
API through the openworker-nvidia OpenShell provider) in its own
sandbox. The lead (a bash script, for now) creates an item, assigns it to the reviewer and
staffs the reviewer through Spawn Gate; the agent wakes on the assignment, comments through
its board tools, and consumes the event.

Needs Spawn Gate started with --image openworker:local and the charter-agent charter."""

from __future__ import annotations

import json
import shlex
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from run_skeleton import HTTP  # noqa: E402  bash-only HTTP helper for the lead

STATE = Path.home() / "forks/.local/teams"
HERE = Path(__file__).parent
TEAM = "proj3"


MODEL = "openai:aws/anthropic/bedrock-claude-sonnet-5-5"
BASE_URL = "https://inference-api.nvidia.com/v1"


def reviewer_command() -> list[str]:
    return ["openworker", "agent", "--space", TEAM, "--coworker", "reviewer", "--model", MODEL,
            "--base-url", BASE_URL, "--once", "--poll-seconds", "2", "--workspace", "/tmp/ws"]


def worker_policy() -> dict:
    return json.loads((HERE / "charter-agent" / "worker-policy.json").read_text())


def lead_script() -> str:
    request = {"team": TEAM, "name": "reviewer", "role": "worker", "policy": worker_policy(),
               "task": "review item 1", "request_id": f"lead-{uuid.uuid4().hex[:6]}",
               "providers": ["openworker-nvidia"],
               "command": reviewer_command()}
    item = {"space": TEAM, "title": "Review: does 2 + 2 equal 4?", "criteria": "a comment with the answer"}
    assign = {"space": TEAM, "id": 1, "assignee": "reviewer"}
    return HTTP + f"""
echo "lead: create item"; http POST 8765 /v1/board/items {shlex.quote(json.dumps(item))}; echo
echo "lead: assign to reviewer"; http POST 8765 /v1/board/items/assign {shlex.quote(json.dumps(assign))}; echo
echo "lead: staff the reviewer"; http POST 8766 /v1/agents {shlex.quote(json.dumps(request))}; echo
sleep 900
"""


def main() -> None:
    op = {"X-Operator-Token": (STATE / "operator.token").read_text().strip()}
    gate = "http://127.0.0.1:8766"
    r = httpx.post(f"{gate}/v1/teams", headers=op, timeout=900, json={
        "team": TEAM, "charter_dir": str(HERE / "charter-agent"), "lead_name": "lead",
        "lead_command": ["bash", "-c", lead_script()], "request_id": f"team-{uuid.uuid4()}"})
    print("create team + lead:", r.status_code, r.text[:200])
    if r.status_code != 200:
        sys.exit(1)
    for _ in range(120):
        rv = httpx.get(f"{gate}/v1/agents/reviewer", headers=op, timeout=10)
        if rv.status_code == 200 and rv.json()["state"] in ("running", "stopped"):
            break
        time.sleep(3)
    print("reviewer:", rv.status_code, rv.text[:200])


if __name__ == "__main__":
    main()
