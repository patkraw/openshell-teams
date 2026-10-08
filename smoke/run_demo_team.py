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

from run_team_real import BOARD, HERE, OW_STATE, STATE, user_token

TEAM = f"demo{uuid.uuid4().hex[:4]}"
GATE = "http://127.0.0.1:8766"
from config import OPENSHELL  # noqa: E402
PY = "/usr/local/lib/openworker/venv/bin/python"
REPO = "https://github.com/octocat/Hello-World"

PRIVATE_TITLE = "Private: lead's notes"     # read check target: assigned to the lead, never linked
LINE = "Patched by the patcher agent."      # what the worker appends; found in its posted diff

OPEN_LINE = "Patched by an agent team."
OPEN_TASK = f"""Goal: get a one-line change made and reviewed by someone other than its author.
In {REPO}, append the line "{OPEN_LINE}" to README. Do not commit or push. The change must be
posted on the board as the output of `git diff`, and a different team member must then comment
on that same item with APPROVE or REQUEST CHANGES and one sentence why.

You coordinate only: you never write code or run commands yourself. Decide which workers the
team needs and what each needs, propose the team with propose_sandbox_team (pieces come from
team_boundary), and wait for the user's approval. Then staff it and hand out the work on the
board. Workers see only items assigned to them and items linked to those (board_link).
Personas available: swe-worker (shell, git, files) and reviewer (reads and comments)."""

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


def board_timeline() -> None:
    """Every board event so far, read from the board's store on the host (the user's view)."""
    import sqlite3
    db = sqlite3.connect(f"file:{OW_STATE / 'teams.db'}?mode=ro", uri=True)
    rows = db.execute(
        "SELECT seq, actor, kind, item_id, coalesce(json_extract(payload,'$.body'), json_extract(payload,'$.title'),"
        " json_extract(payload,'$.assignee'), json_extract(payload,'$.to'), json_extract(payload,'$.dst'), '')"
        " FROM team_events WHERE space=? ORDER BY seq", (TEAM,)).fetchall()
    print("\n=== BOARD TIMELINE (who did what, in order) ===")
    for seq, actor, kind, item, text in rows:
        text = " ".join(str(text).split())
        print(f"  #{seq:<4} {actor:9} {kind:18} item {item or '-':<3} {text[:150]}")


def _entries(net: dict, indent: str = "      ") -> None:
    for name, body in sorted((net or {}).items()):
        for e in body.get("endpoints", []):
            rules = [f"{r['allow'].get('method')} {r['allow'].get('path')}" for r in e.get("rules", [])]
            print(f"{indent}network {name:28} {e['host']}:{e.get('port') or e.get('ports')}"
                  f"  {e.get('protocol') or 'tcp'}  {'rules: ' + ', '.join(rules) if rules else 'all requests'}")
        print(f"{indent}{'':8}{'':28} used by: {', '.join(b['path'] for b in body.get('binaries', [])) or 'any binary'}")


def show_team() -> None:
    """The user's files for this team: the boundary, and the board rights of each role."""
    import yaml
    d = HERE / "charter-demo"
    boundary = yaml.safe_load((d / "team-boundary.yaml").read_text())
    access = yaml.safe_load((d / "access-rules.yaml").read_text())["roles"]
    actions = yaml.safe_load((d / "endpoint-map.yaml").read_text())["actions"]
    pol = boundary["policy"]
    print("\n=== TEAM BOUNDARY (the most any agent on this team may have) ===")
    _entries(pol.get("network_policies"))
    fs = pol.get("filesystem_policy", {})
    print(f"      files    writable {fs.get('read_write')}, read-only {fs.get('read_only')}")
    print(f"      process  {pol.get('process')}, landlock {pol.get('landlock')}")
    print(f"      keys     {boundary.get('credentials')}   limits {boundary.get('limits')}   "
          f"lead-only entries {boundary.get('lead_only', ['spawn'])}")
    print("\n=== BOARD RIGHTS PER ROLE (Channel Guard compiles these into each agent's policy) ===")
    for role, rights in access.items():
        print(f"  {role}:")
        for a in rights:
            kind = "read " if actions[a]["method"] == "GET" else "write"
            print(f"      {kind} {a:8} {actions[a]['method']:4} {actions[a]['path']}")


def show_grants() -> None:
    """What Spawn Gate admitted for each agent: the policy its sandbox enforces."""
    import sqlite3
    db = sqlite3.connect(f"file:{STATE / 'gate' / 'registry.db'}?mode=ro", uri=True)
    print("\n=== ADMITTED POLICIES (proved, launched and enforced by each sandbox) ===")
    for name, role, grant, providers, sid in db.execute(
            "SELECT name, role, grant_json, providers, sandbox_id FROM agents a WHERE team=? AND grant_json IS NOT NULL"
            " AND id=(SELECT MAX(id) FROM agents b WHERE b.name=a.name AND b.team=a.team) ORDER BY id", (TEAM,)):
        g = json.loads(grant)
        print(f"  {name} ({role}), sandbox {str(sid)[:8]}…, keys {providers or '-'}, "
              f"identity middleware {sorted(g.get('network_middlewares') or {})}")
        _entries(g.get("network_policies"))


def outcome(items_fn, comments_fn, line: str):
    """The item where a worker posted the diff (its author is the writer) and a verdict on the
    same item by another worker (the reader). Found by what was posted, not by agent names."""
    for item in items_fn():   # any item: a lead may have the work posted on its own task item
        cs = comments_fn(item["id"])
        diff = next((c for c in cs if c["role"] == "worker" and line in c["body"]), None)
        if not diff:
            continue
        rev = next((c for c in cs if c["role"] == "worker" and c["author"] != diff["author"]
                    and any(v in c["body"].upper() for v in ("APPROVE", "REQUEST CHANGES"))), None)
        if rev:
            return item, diff, rev
    return None


def least_privilege(proposal: dict, writer: str) -> None:
    """Did the lead AI give GitHub only to the worker that needed it?"""
    print("\n=== LEAST PRIVILEGE: what the lead AI chose ===")
    holders = []
    for w in proposal["workers"]:
        nets = sorted((w["policy"].get("network_policies") or {}))
        if "github" in nets:
            holders.append(w["name"])
        print(f"  {w['name']:12} persona={w['persona']:11} network={nets}")
    extra = [h for h in holders if h != writer]
    print("  (model access comes from the key's provider entry, which OpenShell adds for every agent)")
    if holders == [writer]:
        print(f"  -> only {writer}, who cloned the repo, got GitHub: least privilege")
    else:
        print(f"  -> GitHub given to {holders or 'nobody'}; needed only by {writer}"
              + (f"; not needed by {extra}" if extra else ""))


def main(open_task: bool = False) -> None:
    op = (STATE / "operator.token").read_text().strip()
    task_text, line = (OPEN_TASK, OPEN_LINE) if open_task else (TASK, LINE)
    show_team()
    print(f"\n=== TASK FOR THE LEAD ({'open: the lead plans the team' if open_task else 'scripted'}) ===\n{task_text}")
    r = httpx.post(f"{GATE}/v1/teams", headers={"X-Operator-Token": op}, timeout=900, json={
        "team": TEAM, "charter_dir": str(HERE / "charter-demo"), "lead_name": "lead",
        "lead_persona": "swe-lead", "request_id": f"team-{uuid.uuid4()}"})
    print("team", TEAM, "+ lead:", r.status_code, r.text[:200])
    r.raise_for_status()
    user = {"Authorization": f"Bearer {user_token()}"}
    app = {"X-OpenWorker-Token": op}
    task = httpx.post(f"{BOARD}/v1/board/items", headers=user, timeout=30, json={
        "space": TEAM, "title": "Build the demo team", "criteria": "patch reviewed",
        "description": task_text}).json()
    httpx.post(f"{BOARD}/v1/board/items/assign", headers=user, timeout=30,
               json={"space": TEAM, "id": task["id"], "assignee": "lead"}).raise_for_status()
    # A lead-only item nobody links to: no worker should ever be able to read it.
    private = httpx.post(f"{BOARD}/v1/board/items", headers=user, timeout=30, json={
        "space": TEAM, "title": PRIVATE_TITLE, "criteria": "none",
        "description": "Lead-only notes. Not part of the task."}).json()
    httpx.post(f"{BOARD}/v1/board/items/assign", headers=user, timeout=30,
               json={"space": TEAM, "id": private["id"], "assignee": "lead"}).raise_for_status()

    def pending():
        ps = httpx.get(f"{BOARD}/v1/team-proposals", headers=app, timeout=10).json()["proposals"]
        return [p for p in ps if p["space"] == TEAM and p["state"] == "pending"]

    proposal = wait("the lead's proposal", pending)[0]
    print("\n=== APPROVAL CARD: the policies the lead AI proposed (the user approves these) ===")
    for w in proposal["workers"]:
        print(f"  {w['name']}  persona={w['persona']}  role={w.get('role')}  keys={w.get('providers') or []}")
        _entries(w["policy"].get("network_policies"))
        print(f"      files    writable {w['policy'].get('filesystem_policy', {}).get('read_write')}")
        print(f"      board    (none proposed: Channel Guard adds the '{w.get('role')}' rights above)")
    httpx.post(f"{BOARD}/v1/team-proposals/{proposal['id']}/decide", headers=app, timeout=10,
               json={"approve": True}).raise_for_status()
    httpx.post(f"{BOARD}/v1/board/items/comment", headers=user, timeout=30, json={
        "space": TEAM, "id": task["id"],
        "body": f"Approved: proposal {proposal['id']}. Go ahead."}).raise_for_status()
    print("user approved; waiting for the workers to be staffed, the diff and a verdict...")

    def items():
        got = httpx.get(f"{BOARD}/v1/board/items", headers=user, params={"space": TEAM},
                        timeout=10).json()
        return got.get("items", []) if isinstance(got, dict) else got

    def comments(item_id):
        return httpx.get(f"{BOARD}/v1/board/comments", headers=user, timeout=10,
                         params={"space": TEAM, "id": item_id, "limit": 50}).json().get("comments", [])

    names = [w["name"] for w in proposal["workers"]]
    wait("work handed out", lambda: any(i.get("assignee") in names for i in items()))
    show_grants()
    patch, diff, rev = wait("the diff and a verdict", lambda: outcome(items, comments, line), seconds=1500)
    writer, reader = diff["author"], rev["author"]
    print(f"\n=== DIFF by {writer} (on item {patch['id']}) ===\n{diff['body'][:800]}")
    print(f"\n=== VERDICT by {reader} (on the same item) ===\n{rev['body'][:400]}")
    least_privilege(proposal, writer)
    board_timeline()

    run_checks(TEAM, private["id"], patch, proposal, op, app, comments, writer=writer, reader=reader)


def run_checks(TEAM, private_id, patch, proposal, op, app, comments, writer="patcher", reader="reviewer") -> None:
    """`writer` posted the diff (has GitHub); `reader` gave the verdict (a plain worker)."""
    print("\n=== CHECKS THAT MUST FAIL ===")
    results = []

    def check(label: str, refused: bool, detail):
        results.append(refused)
        print(f"  [{'PASS' if refused else 'FAIL'}] {label}: {str(detail)[:200]}")

    inside_board = "http://host.openshell.internal:8765"
    inside_gate = "http://host.openshell.internal:8766"

    # Each check asserts the specific refusal, and where it matters a control showing the
    # same call succeeds for an agent that is allowed to make it (review finding 19).
    def denied_by_proxy(r: dict) -> bool:
        body = str(r.get("body") or "") + str(r.get("error") or "")
        return ("policy_denied" in body and r.get("status") == 403) or "Permission denied" in body

    def code_of(r: dict) -> str:
        try:
            return json.loads(r.get("body") or "{}").get("detail", {}).get("code", "")
        except (ValueError, AttributeError):
            return ""

    # 1. Unauthorized creation: a worker has no route to Spawn Gate; the lead does.
    r = call(reader, "POST", f"{inside_gate}/v1/agents", json={"team": TEAM, "name": "x"})
    control = call("lead", "GET", f"{inside_gate}/v1/teams/{TEAM}/boundary")
    check("reviewer creates an agent", denied_by_proxy(r) and control.get("status") == 200,
          f"reviewer={r} lead_control={control.get('status')}")

    # 2. Staffing without approval: refused by Spawn Gate with approval_required.
    reviewer_policy = next(w for w in proposal["workers"] if w["name"] == reader)["policy"]
    r = call("lead", "POST", f"{inside_gate}/v1/agents", json={
        "team": TEAM, "name": "extra", "role": "worker", "persona": "reviewer", "task": "t",
        "policy": reviewer_policy, "providers": [], "request_id": f"x-{uuid.uuid4().hex[:6]}"})
    check("lead staffs without an approval", r.get("status") == 403 and code_of(r) == "approval_required", r)

    # 3. Excess permissions, even when the user approves them: the prover refuses.
    wide = json.loads(json.dumps(reviewer_policy))
    wide.setdefault("network_policies", {})["exfil"] = {
        "name": "exfil", "endpoints": [{"host": "example.com", "port": 443}],
        "binaries": [{"path": PY}]}
    r = call("lead", "POST", f"{inside_board}/v1/board/team-proposals", json={
        "space": TEAM, "workers": [{"name": "intruder", "persona": "reviewer", "role": "worker",
                                    "task": "t", "policy": wide, "providers": []}]})
    pid = json.loads(r.get("body") or "{}").get("id")
    approval = None
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
    check("approved worker outside the boundary",
          bool(approval) and r.get("status") == 403 and code_of(r) == "prover_exceeds_boundary", r)

    # 4. Impersonation: the forged header is replaced; the comment is created and the
    #    board names the reviewer as its author.
    r = call(reader, "POST", f"{inside_board}/v1/board/items/comment",
             headers={"X-OpenShell-Caller": "forged.lead.token"},
             json={"space": TEAM, "id": patch["id"], "body": "forged-as-lead check"})
    forged = next((c for c in comments(patch["id"]) if c["body"] == "forged-as-lead check"), None)
    check("reviewer posts as the lead", r.get("status") == 200 and forged is not None
          and forged["author"] == reader, f"status={r.get('status')} author={forged and forged['author']}")

    # 5. Outside communication rights: create is not a worker right (Channel Guard), and
    #    the lead's item is not in the reviewer's slice while the patch item is.
    r = call(reader, "POST", f"{inside_board}/v1/board/items",
             json={"space": TEAM, "title": "t", "criteria": "c"})
    check("reviewer creates a board item", denied_by_proxy(r), r)
    r = call(reader, "GET", f"{inside_board}/v1/board/item",
             params={"space": TEAM, "id": private_id})
    control = call(reader, "GET", f"{inside_board}/v1/board/item",
                   params={"space": TEAM, "id": patch["id"]})
    check("reviewer reads the lead's private item", r.get("status") == 404 and control.get("status") == 200,
          f"lead_item={r.get('status')} patch_item_control={control.get('status')}")

    # 6. The lead does the patcher's job itself: no GitHub route from the lead's sandbox,
    #    while the patcher can reach GitHub.
    out = in_sandbox("lead", "git", "ls-remote", REPO)
    control = in_sandbox(writer, "git", "ls-remote", REPO)
    check("lead clones from GitHub", "HEAD" not in out and "connect" in out.lower() and "HEAD" in control,
          f"lead: {out.splitlines()[-1] if out else out} | patcher control: {'HEAD' in control}")

    # 7. Widening after launch: Policy Lock (gateway interceptor) refuses policy and
    #    credential changes to team sandboxes, even from the operator's own CLI. The CLI
    #    may show only "permission denied", so the denial is confirmed in Policy Lock's log.
    lock_log = STATE / "run/policy-lock.log"

    def widen(label: str, method: str, *cmd: str) -> None:
        before = lock_log.read_text().count(f"DENY {method}") if lock_log.exists() else 0
        r = sh(OPENSHELL, *cmd)
        denied = lock_log.read_text().count(f"DENY {method}") > before if lock_log.exists() else False
        out = (r.stdout + r.stderr).strip()
        check(label, r.returncode != 0 and denied,
              f"exit={r.returncode} policy_lock={'DENY' if denied else 'no deny'}: "
              f"{out.splitlines()[-1].strip() if out else ''}")

    widen("operator widens the reviewer's policy", "UpdateConfig",
          "policy", "update", reader, "--add-endpoint", "example.com:443", "--binary", PY)
    widen("operator attaches a credential to the reviewer", "AttachSandboxProvider",
          "sandbox", "provider", "attach", reader, "my-claude")

    # 8. Worker outliving its lead: Cascade Stop.
    stopped = httpx.post(f"{GATE}/v1/agents/lead/stop", headers={"X-Operator-Token": op},
                         timeout=600).json()
    gone = {n: "not found" in (sh(OPENSHELL, "sandbox", "get", n).stderr or "")
            for n in ("lead", *(w["name"] for w in proposal["workers"]))}
    alive = [n for n, g in gone.items() if not g]
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
    found = outcome(lambda: items, comments, LINE) or outcome(lambda: items, comments, OPEN_LINE)
    patch, diff, rev = found
    pid = next(m.group(0) for c in comments(task["id"]) for m in [re.search(r"tp_[0-9a-f]+", c["body"])] if m)
    got = call("lead", "GET", f"http://host.openshell.internal:8765/v1/board/team-proposals/{pid}",
               params={"space": team})
    proposal = json.loads(got["body"])
    private = next((i for i in items if i.get("title") == PRIVATE_TITLE), task)
    run_checks(team, private["id"], patch, proposal, op, {"X-OpenWorker-Token": op}, comments,
               writer=diff["author"], reader=rev["author"])


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--checks":
        checks_only(sys.argv[2])
    else:
        # --open-task: give the lead only the goal; it plans the team and each worker's access.
        main(open_task="--open-task" in sys.argv)
