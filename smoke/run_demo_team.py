"""THE STAGE 1 DEMO TEAM (real model): a coordination-only lead proposes a patcher (shell,
GitHub clone access) and a reviewer (model only); the user approves; the lead staffs both
through Spawn Gate, gives the patcher a change and links a review item to it; the patcher
clones from GitHub, edits and posts its diff; the reviewer replies on the patcher's item.

Then the checks that must fail, run inside the sandboxes, and Cascade Stop.

Needs the stack from scripts/up.sh (image openworker:local) and the openworker-nvidia provider."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid

import httpx

from run_team_real import BOARD, HERE, STATE, user_token

TEAM = f"demo{uuid.uuid4().hex[:4]}"
GATE = "http://127.0.0.1:8766"
OPENSHELL = str(STATE.parent / "openshell-0.1.2/bin/openshell")
PY = "/usr/local/lib/openworker/venv/bin/python"
REPO = "https://github.com/octocat/Hello-World"

TASK = f"""You lead this team. You coordinate only: you never write code or run commands.
1) Call team_boundary.
2) Call propose_sandbox_team with two workers:
   - name 'patcher', persona 'swe-worker', task 'make the change on its board item',
     network ['inference', 'github'];
   - name 'reviewer', persona 'reviewer', task 'review the patcher's diff', network ['inference'].
   Then stop and wait.
3) When a comment on this item says the proposal is approved: call staff_approved_team with the
   proposal id. Then create item P titled 'Patch: add a line to the Hello-World README' with
   criteria 'the diff is posted as a comment' and this description: 'Run: git clone --depth 1
   {REPO} /tmp/ws/hw . Append the line "Patched by the patcher agent." to /tmp/ws/hw/README .
   Post the full output of: git -C /tmp/ws/hw diff  as a comment on this item, then move this
   item to review.' Assign P to 'patcher'.
4) Create item R titled 'Review the patch' with criteria 'a verdict is posted on the patch
   item' and the description: 'Read item P (use its real id) and its comments. When the diff is
   posted, comment on item P: APPROVE or REQUEST CHANGES, and one sentence why. Then move this
   item to review.' Call board_link with id R and parent_id P. Assign R to 'reviewer'. Stop."""


def sh(*args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def in_sandbox(name: str, *cmd: str) -> str:
    r = sh(OPENSHELL, "sandbox", "exec", "--name", name, "--no-tty", "--", *cmd)
    return (r.stdout + r.stderr).strip()


def py_in(name: str, code: str, **args) -> dict:
    out = in_sandbox(name, PY, "-c", code, json.dumps(args))
    try:
        return json.loads(out.splitlines()[-1])
    except (ValueError, IndexError):
        return {"raw": out[-400:]}


HTTP = """
import json, sys, httpx
a = json.loads(sys.argv[1])
try:
    r = httpx.request(a["method"], a["url"], json=a.get("json"), params=a.get("params"),
                      headers=a.get("headers") or {}, timeout=60)
    body = r.text[:20000]
    print(json.dumps({"status": r.status_code, "body": body}))
except Exception as e:
    print(json.dumps({"status": None, "error": type(e).__name__ + ": " + str(e)[:200]}))
"""


def call(name: str, method: str, url: str, **kw) -> dict:
    return py_in(name, HTTP, method=method, url=url, **kw)


def wait(what: str, check, seconds: int = 900, every: int = 5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        got = check()
        if got:
            return got
        time.sleep(every)
    raise SystemExit(f"timed out waiting for {what}")


def main() -> None:
    op = (STATE / "operator.token").read_text().strip()
    r = httpx.post(f"{GATE}/v1/teams", headers={"X-Operator-Token": op}, timeout=900, json={
        "team": TEAM, "charter_dir": str(HERE / "charter-demo"), "lead_name": "lead",
        "lead_persona": "swe-lead", "request_id": f"team-{uuid.uuid4()}"})
    print("team", TEAM, "+ lead:", r.status_code, r.text[:200])
    r.raise_for_status()
    user = {"Authorization": f"Bearer {user_token()}"}
    app = {"X-OpenWorker-Token": op}
    task = httpx.post(f"{BOARD}/v1/board/items", headers=user, timeout=30, json={
        "space": TEAM, "title": "Build the demo team", "criteria": "patch reviewed",
        "description": TASK}).json()
    httpx.post(f"{BOARD}/v1/board/items/assign", headers=user, timeout=30,
               json={"space": TEAM, "id": task["id"], "assignee": "lead"}).raise_for_status()

    def pending():
        ps = httpx.get(f"{BOARD}/v1/team-proposals", headers=app, timeout=10).json()["proposals"]
        return [p for p in ps if p["space"] == TEAM and p["state"] == "pending"]

    proposal = wait("the lead's proposal", pending)[0]
    print("\n=== APPROVAL CARD ===")
    for w in proposal["workers"]:
        print(f"  {w['name']} (persona {w['persona']}): network "
              f"{sorted((w['policy'].get('network_policies') or {}).keys())}")
    httpx.post(f"{BOARD}/v1/team-proposals/{proposal['id']}/decide", headers=app, timeout=10,
               json={"approve": True}).raise_for_status()
    httpx.post(f"{BOARD}/v1/board/items/comment", headers=user, timeout=30, json={
        "space": TEAM, "id": task["id"],
        "body": f"Approved: proposal {proposal['id']}. Go ahead."}).raise_for_status()
    print("user approved; waiting for the patcher's diff and the reviewer's verdict...")

    def items():
        got = httpx.get(f"{BOARD}/v1/board/items", headers=user, params={"space": TEAM},
                        timeout=10).json()
        return got.get("items", []) if isinstance(got, dict) else got

    def comments(item_id):
        return httpx.get(f"{BOARD}/v1/board/comments", headers=user, timeout=10,
                         params={"space": TEAM, "id": item_id, "limit": 50}).json().get("comments", [])

    def patch_item():
        return next((i for i in items() if i.get("assignee") == "patcher"), None)

    patch = wait("the patch item", patch_item)

    def verdict():
        cs = comments(patch["id"])
        diff = next((c for c in cs if c["author"] == "patcher" and "Patched by" in c["body"]), None)
        rev = next((c for c in cs if c["author"] == "reviewer"), None)
        return (diff, rev) if diff and rev else None

    diff, rev = wait("diff and verdict", verdict, seconds=1200)
    print("\n=== PATCHER (on item %s) ===\n%s" % (patch["id"], diff["body"][:800]))
    print("\n=== REVIEWER (on the same item) ===\n%s" % rev["body"][:400])

    run_checks(TEAM, task["id"], patch, proposal, op, app, comments)


def run_checks(TEAM, task_id, patch, proposal, op, app, comments) -> None:
    print("\n=== CHECKS THAT MUST FAIL ===")
    results = []

    def check(label: str, refused: bool, detail):
        results.append(refused)
        print(f"  [{'PASS' if refused else 'FAIL'}] {label}: {str(detail)[:200]}")

    inside_board = "http://host.openshell.internal:8765"
    inside_gate = "http://host.openshell.internal:8766"

    # 1. Unauthorized creation: a worker has no route to Spawn Gate.
    r = call("reviewer", "POST", f"{inside_gate}/v1/agents", json={"team": TEAM, "name": "x"})
    check("reviewer creates an agent", r.get("status") in (None, 403) and "admitted" not in str(r), r)

    # 2. Staffing without approval.
    reviewer_policy = next(w for w in proposal["workers"] if w["name"] == "reviewer")["policy"]
    r = call("lead", "POST", f"{inside_gate}/v1/agents", json={
        "team": TEAM, "name": "extra", "role": "worker", "persona": "reviewer", "task": "t",
        "policy": reviewer_policy, "providers": [], "request_id": f"x-{uuid.uuid4().hex[:6]}"})
    check("lead staffs without an approval", r.get("status") == 403, r)

    # 3. Excess permissions, even when the user approves them: the prover refuses.
    wide = json.loads(json.dumps(reviewer_policy))
    wide.setdefault("network_policies", {})["exfil"] = {
        "name": "exfil", "endpoints": [{"host": "example.com", "port": 443}],
        "binaries": [{"path": PY}]}
    r = call("lead", "POST", f"{inside_board}/v1/board/team-proposals", json={
        "space": TEAM, "workers": [{"name": "intruder", "persona": "reviewer", "role": "worker",
                                    "task": "t", "policy": wide, "providers": []}]})
    pid = json.loads(r.get("body") or "{}").get("id")
    if pid:
        httpx.post(f"{BOARD}/v1/team-proposals/{pid}/decide", headers=app, timeout=10,
                   json={"approve": True}).raise_for_status()
        got = call("lead", "GET", f"{inside_board}/v1/board/team-proposals/{pid}",
                   params={"space": TEAM})
        approval = json.loads(got.get("body") or "{}").get("approvals", {}).get("intruder")
        r = call("lead", "POST", f"{inside_gate}/v1/agents", json={
            "team": TEAM, "name": "intruder", "role": "worker", "persona": "reviewer", "task": "t",
            "policy": wide, "providers": [], "approval_id": approval,
            "request_id": f"x-{uuid.uuid4().hex[:6]}"})
        check("approved worker outside the boundary", r.get("status") == 403, r)
    else:
        check("worker outside the boundary (refused at proposal)", r.get("status") in (400, 403, 422), r)

    # 4. Impersonation: a forged identity header is replaced; the board names the real caller.
    r = call("reviewer", "POST", f"{inside_board}/v1/board/items/comment",
             headers={"X-OpenShell-Caller": "forged.lead.token"},
             json={"space": TEAM, "id": patch["id"], "body": "forged-as-lead check"})
    forged = next((c for c in comments(patch["id"]) if c["body"] == "forged-as-lead check"), None)
    check("reviewer posts as the lead", forged is None or forged["author"] == "reviewer",
          f"author={forged and forged['author']}")

    # 5. Outside communication rights: create is not a worker right; the lead's item is not
    #    in the reviewer's slice.
    r = call("reviewer", "POST", f"{inside_board}/v1/board/items",
             json={"space": TEAM, "title": "t", "criteria": "c"})
    check("reviewer creates a board item", r.get("status") == 403, r)
    r = call("reviewer", "GET", f"{inside_board}/v1/board/item",
             params={"space": TEAM, "id": task_id})
    check("reviewer reads the lead's task item", r.get("status") in (403, 404), r)

    # 6. The lead does the patcher's job itself: no GitHub route from the lead's sandbox.
    out = in_sandbox("lead", "git", "ls-remote", REPO)
    check("lead clones from GitHub", "HEAD" not in out, out.splitlines()[-1] if out else out)

    # 7. Worker outliving its lead: Cascade Stop.
    stopped = httpx.post(f"{GATE}/v1/agents/lead/stop", headers={"X-Operator-Token": op},
                         timeout=600).json()
    alive = [n for n in ("lead", "patcher", "reviewer")
             if sh(OPENSHELL, "sandbox", "get", n).returncode == 0]
    check("workers outlive the lead", not alive, f"stopped={stopped} alive={alive}")

    print(f"\n{sum(results)}/{len(results)} checks refused as expected")
    print(json.dumps({"team": TEAM, "patch_item": patch["id"]}))
    sys.exit(0 if all(results) else 1)


def checks_only(team: str) -> None:
    """Run only the checks against a team that already ran the flow."""
    import re
    op = (STATE / "operator.token").read_text().strip()
    user = {"Authorization": f"Bearer {user_token()}"}

    def comments(item_id):
        return httpx.get(f"{BOARD}/v1/board/comments", headers=user, timeout=10,
                         params={"space": team, "id": item_id, "limit": 50}).json().get("comments", [])

    items = httpx.get(f"{BOARD}/v1/board/items", headers=user, params={"space": team}, timeout=10).json()["items"]
    task = next(i for i in items if i.get("assignee") == "lead")
    patch = next(i for i in items if i.get("assignee") == "patcher")
    pid = next(m.group(0) for c in comments(task["id"]) for m in [re.search(r"tp_[0-9a-f]+", c["body"])] if m)
    got = call("lead", "GET", f"http://host.openshell.internal:8765/v1/board/team-proposals/{pid}",
               params={"space": team})
    proposal = json.loads(got["body"])
    run_checks(team, task["id"], patch, proposal, op, {"X-OpenWorker-Token": op}, comments)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--checks":
        checks_only(sys.argv[2])
    else:
        main()
