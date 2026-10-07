# Smoke tests (local OpenShell 0.1.2)

Start, in order: the Passport middleware (:50061), the gateway with `~/forks/.local/teams/gateway.toml`
(registers the middleware), the reference board (:8765) and Spawn Gate (:8766). Then:

```sh
uv run python smoke/run_skeleton.py
```

Expected: the lead (in its sandbox) gets a reviewer admitted; a worker outside the boundary is
rejected by the prover; the reviewer's comment is attributed to the reviewer even though it
claims to be the lead; the reviewer cannot reach Spawn Gate. Stop the team with
`POST /v1/agents/lead/stop` (operator token) — Cascade Stop removes the reviewer, then the lead.
