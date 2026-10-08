"""REAL MODEL + APPROVAL: the lead proposes its team; the user sees the proposal (the
approval card) and approves it; the lead then staffs the approved worker through Spawn
Gate, which consumes the single-use approval ID; the reviewer answers a question."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import httpx

from run_team_real import BOARD, HERE, OW_STATE, STATE, user_token  # noqa: F401

TEAM = f"appr{uuid.uuid4().hex[:4]}"
TASK = (
    "You lead this team. 1) Call team_boundary. 2) Call propose_sandbox_team with one worker: "
    "name 'reviewer', persona 'reviewer', task 'answer the question on the board', network "
    "['inference'] (nothing else). Then stop and wait. Later, when a comment on this item says "
    "the proposal is approved, call staff_approved_team with the proposal id, then create an item "
    "titled 'Question: what is 19 * 21?' with criteria 'a comment with the answer', assign it to "
    "'reviewer', and stop."
)


def main() -> None:
    op = (STATE / "operator.token").read_text().strip()
    gate = "http://127.0.0.1:8766"
    r = httpx.post(f"{gate}/v1/teams", headers={"X-Operator-Token": op}, timeout=900, json={
        "team": TEAM, "charter_dir": str(HERE / "charter-approval"), "lead_name": "lead",
        "lead_persona": "swe-lead", "request_id": f"team-{uuid.uuid4()}"})
    print("team", TEAM, "+ lead:", r.status_code)
    r.raise_for_status()
    user = {"Authorization": f"Bearer {user_token()}"}
    item = httpx.post(f"{BOARD}/v1/board/items", headers=user, timeout=30, json={
        "space": TEAM, "title": "Build a small team", "criteria": "reviewer answered", "description": TASK}).json()
    httpx.post(f"{BOARD}/v1/board/items/assign", headers=user, timeout=30,
               json={"space": TEAM, "id": item["id"], "assignee": "lead"}).raise_for_status()
    print("user posted the task; waiting for the lead's proposal...")
    app = {"X-OpenWorker-Token": op}
    for _ in range(120):
        pending = [p for p in httpx.get(f"{BOARD}/v1/team-proposals", headers=app, timeout=10).json()["proposals"]
                   if p["space"] == TEAM]
        if pending:
            break
        time.sleep(3)
    else:
        raise SystemExit("no proposal from the lead")
    proposal = pending[0]
    print("\n=== APPROVAL CARD ===")
    for w in proposal["workers"]:
        net = sorted((w["policy"].get("network_policies") or {}).keys())
        print(f"  worker {w['name']} (persona {w['persona']}): network {net}, "
              f"writable {w['policy']['filesystem_policy']['read_write']}")
    decided = httpx.post(f"{BOARD}/v1/team-proposals/{proposal['id']}/decide", headers=app, timeout=10,
                         json={"approve": True}).json()
    print("user approved:", decided["state"])
    httpx.post(f"{BOARD}/v1/board/items/comment", headers=user, timeout=30, json={
        "space": TEAM, "id": item["id"], "body": f"Approved: proposal {proposal['id']}. Go ahead."}).raise_for_status()
    print("told the lead; watch", STATE / "gate/logs")
    print(json.dumps({"team": TEAM}))


if __name__ == "__main__":
    main()
