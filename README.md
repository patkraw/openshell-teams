# openshell-teams

OpenShell × OpenWorker: agent teams where every agent runs in its own OpenShell sandbox, and creating agents and team communication are checked and enforced outside agent-controlled processes.

Design: the RFC "Sub-agent creation and team communication" (research site). Language: [GLOSSARY.md](GLOSSARY.md). Decisions: [docs/adr/](docs/adr/).

Forks: [patkraw/OpenShell](https://github.com/patkraw/OpenShell), [patkraw/openworker](https://github.com/patkraw/openworker) (branch `teams`).

## Run locally

```sh
uv run pytest                     # unit tests
scripts/gen-protos.sh             # regenerate gRPC stubs from OpenShell v0.1.2 protos
uv run python -m openshell_teams.middleware --keys <dir> --audience board.local --port 50061
```

The gateway must register the middleware before it starts (see `smoke/` and the gateway TOML in the docs).
