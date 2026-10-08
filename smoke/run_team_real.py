"""REAL MODEL, REAL LEAD: the user posts a task for the lead; the lead (openworker agent,
Claude Sonnet 5.5 via NVIDIA's API) reads the team boundary, staffs a reviewer through
Spawn Gate, and assigns it work; the reviewer (also a real model) does it.

Needs Spawn Gate with --image openworker:local, the OpenWorker server on :8765 with
Passport auth, and the openworker-nvidia provider."""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx

from config import OW_STATE, OPENWORKER_DIR, STATE  # noqa: E402
HERE = Path(__file__).parent
TEAM = f"team{uuid.uuid4().hex[:4]}"
BOARD = "http://127.0.0.1:8765"

TASK = (
    "You lead this team. Do exactly this: 1) call team_boundary; 2) call staff_worker with "
    "name='reviewer', persona='reviewer', task='answer the question on the board', "
    "network=['inference'] (it needs nothing else); 3) create a board item titled "
    "'Question: what is 17 * 23?' with criteria 'a comment with the answer'; 4) assign it to "
    "'reviewer'. Then stop."
)


def user_token() -> str:
    out = subprocess.run(
        ["uv", "run", "python", "-m", "coworker.teams.cli", "board", "token", "mint",
         "--actor", "user", "--role", "user"],
        cwd=OPENWORKER_DIR, capture_output=True, text=True, check=True,
        env={**os.environ, "COWORKER_STATE_DIR": str(OW_STATE)})
    return next(line.strip() for line in out.stdout.splitlines() if line.strip().startswith("owb_"))


def main() -> None:
    op = {"X-Operator-Token": (STATE / "operator.token").read_text().strip()}
    gate = "http://127.0.0.1:8766"
    r = httpx.post(f"{gate}/v1/teams", headers=op, timeout=900, json={
        "team": TEAM, "charter_dir": str(HERE / "charter-team"), "lead_name": "lead",
        "lead_persona": "swe-lead", "request_id": f"team-{uuid.uuid4()}"})
    print("team", TEAM, "+ lead:", r.status_code, r.text[:160])
    r.raise_for_status()
    user = {"Authorization": f"Bearer {user_token()}"}
    item = httpx.post(f"{BOARD}/v1/board/items", headers=user, timeout=30, json={
        "space": TEAM, "title": "Staff a reviewer and ask it a question", "criteria": "reviewer answered",
        "description": TASK}).json()
    httpx.post(f"{BOARD}/v1/board/items/assign", headers=user, timeout=30,
               json={"space": TEAM, "id": item["id"], "assignee": "lead"}).raise_for_status()
    print("user posted task item", item["id"], "for the lead")
    print("watch:", STATE / "gate/logs")


if __name__ == "__main__":
    main()
