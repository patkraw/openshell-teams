# openshell-teams

OpenShell × OpenWorker: agent teams where every agent runs in its own OpenShell sandbox, and creating agents and team communication are checked and enforced outside agent-controlled processes.

Design: the RFC "Sub-agent creation and team communication" (research site). Language: [GLOSSARY.md](GLOSSARY.md). Decisions: [docs/adr/](docs/adr/).

Forks: [patkraw/OpenShell](https://github.com/patkraw/OpenShell), [patkraw/openworker](https://github.com/patkraw/openworker) (branch `teams`).

## Run the demo yourself

A lead, a patcher and a reviewer, each in its own OpenShell sandbox, on a real model; then ten
checks that must be refused. About 30 minutes the first time, 10 minutes per run after that.

**Tested on** macOS with Docker Desktop and OpenShell **0.1.2**. The steps follow OpenShell's
documented install; they have not yet been repeated on a fresh machine, so please report what
differs.

### You need

- Docker Desktop, or Docker Engine 28 or later
- `git`, `python3`, [`uv`](https://docs.astral.sh/uv/), `nc`
- An API key for an OpenAI-compatible model endpoint. The demo uses NVIDIA's inference API
  (`inference-api.nvidia.com`, model `aws/anthropic/bedrock-claude-sonnet-5-5`).

### Steps

1. **Install OpenShell 0.1.2** (CLI, prover and a local gateway service):
   ```sh
   curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | OPENSHELL_VERSION=v0.1.2 sh
   openshell status                      # should report the gateway as connected
   ```
   Using release binaries instead? Set `OPENSHELL_BIN`, `OPENSHELL_PROVER` and `GATEWAY_CMD`
   (how to start your gateway) in `~/.config/openshell-teams/env`; see `scripts/env.sh`.

2. **Clone both repositories side by side:**
   ```sh
   git clone https://github.com/patkraw/openshell-teams
   git clone -b teams https://github.com/patkraw/openworker
   ```

3. **Build the sandbox image** every agent runs in:
   ```sh
   docker build -f openworker/packaging/openshell/Dockerfile -t openworker:local openworker
   ```

4. **Register your model key as an OpenShell provider.** The key stays in OpenShell; inside a
   sandbox, agents see only a placeholder. Run this in your own terminal:
   ```sh
   openshell provider profile import -f openshell-teams/smoke/providers/openworker-nvidia.yaml
   export OPENAI_API_KEY=...             # your key
   openshell provider create --name openworker-nvidia --type openworker-nvidia --from-existing
   ```
   Another endpoint? Change the host in that profile, the `inference` entry in
   `smoke/charter-demo/team-boundary.yaml`, and `--model` / `--base-url` in
   `smoke/charter-demo/runtime.yaml`.

5. **One-time setup**: tokens, and the gateway registrations for the Sandbox Passport middleware
   and Policy Lock (appended to `~/.config/openshell/gateway.toml`):
   ```sh
   cd openshell-teams
   scripts/init.sh
   ```

6. **Start the stack**: middleware and Policy Lock, then a gateway restart so it registers them,
   then OpenWorker's board and Spawn Gate. It ends with `stack up`.
   ```sh
   scripts/up.sh
   ```

7. **Run the demo** (about 10 minutes, mostly creating sandboxes and the agents' model turns; each prover check takes well under a second):
   ```sh
   uv run python smoke/run_demo_team.py
   ```
   It plays the user: it starts the team, posts the task, shows the approval card and approves
   it. Watch the agents in `~/.local/state/openshell-teams/gate/logs/{lead,patcher,reviewer}.log`.
   Expected: the approval card, the patcher's diff and the reviewer's verdict on the board, then
   `10/10 checks refused as expected`.

8. **Stop**: the demo's last check stops the team (Cascade Stop). Then:
   ```sh
   scripts/down.sh
   openshell sandbox list                # should list no lead, patcher or reviewer
   ```

### If something goes wrong

- **`an agent named 'lead' is already running`**: a previous team is still up. Stop it:
  `curl -X POST -H "X-Operator-Token: $(cat ~/.local/state/openshell-teams/operator.token)" http://127.0.0.1:8766/v1/agents/lead/stop`
- **`stack up` never appears**: see `~/.local/state/openshell-teams/run/*.log`. If the gateway did
  not come back, check that `gateway.toml` has the two registrations and that ports 50061 and
  50062 are listening before the gateway starts.
- **`prover_inconclusive`**: the prover timed out; raise `--prover-timeout` in `scripts/up.sh`.
- **The model never answers**: check the provider (`openshell provider list`) and the key.

## Development

```sh
uv run pytest                     # unit tests (the real-prover tests run when openshell-prover is installed)
scripts/gen-protos.sh             # regenerate gRPC stubs from OpenShell v0.1.2 protos
```

How it works: [GLOSSARY.md](GLOSSARY.md), [docs/adr/](docs/adr/), and the implementation log and code walkthrough on the research site.
