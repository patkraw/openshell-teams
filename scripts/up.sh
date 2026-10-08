#!/bin/sh
# Start the local stack as detached processes (logs in ~/forks/.local/teams/run/):
# Passport middleware, Policy Lock interceptor -> OpenShell 0.1.2 gateway (registers both) -> OpenWorker server (board,
# Passport auth, approvals) -> Spawn Gate. `scripts/down.sh` stops them.
set -eu
T="$HOME/forks/.local/teams"
B="$HOME/forks/.local/openshell-0.1.2/bin"
R="$T/run"
mkdir -p "$R"
cd "$(dirname "$0")/.."

start() { name=$1; shift; nohup "$@" >"$R/$name.log" 2>&1 & echo "$!" >"$R/$name.pid"; echo "started $name ($!)"; }
wait_port() { for _ in $(seq 1 60); do nc -z 127.0.0.1 "$1" 2>/dev/null && return 0; sleep 1; done; echo "port $1 did not open"; exit 1; }

start middleware uv run python -m openshell_teams.middleware --keys "$T/keys" --port 50061
wait_port 50061
start policy-lock uv run python -m openshell_teams.policy_lock --registry "$T/gate/registry.db" --port 50062
wait_port 50062
OPENSHELL_TEAMS_GATEWAY_CONFIG="$T/gateway.toml" start gateway "$HOME/forks/.local/start-gateway.sh"
wait_port 17670
(cd "$HOME/forks/openworker" && COWORKER_STATE_DIR="$HOME/forks/.local/ow-state" \
  COWORKER_API_TOKEN="$(cat "$T/operator.token")" \
  OPENWORKER_PASSPORT_PUBLIC_KEY="$T/keys/passport.pub" \
  OPENWORKER_PASSPORT_AUDIENCE=host.openshell.internal:8765 \
  OPENWORKER_BOARD_ADMIN_TOKEN="$(cat "$T/board-admin.token")" \
  start openworker uv run python -m coworker.server.run --host 127.0.0.1 --port 8765 --model openai:gpt-test)
wait_port 8765
start gate uv run python -m openshell_teams.api --state "$T/gate" --keys "$T/keys" --port 8766 \
  --openshell "$B/openshell" --prover "$B/openshell-prover" \
  --board-admin-url http://127.0.0.1:8765 --board-admin-token-file "$T/board-admin.token" \
  --operator-token-file "$T/operator.token" --image openworker:local
wait_port 8766
echo "stack up"
