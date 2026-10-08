#!/bin/sh
# Start the local stack as detached processes (logs in $TEAMS_STATE/run/):
# Passport middleware and Policy Lock -> the OpenShell gateway (restarted so it registers both)
# -> the OpenWorker server (board, Passport auth, approvals) -> Spawn Gate.
# `scripts/down.sh` stops them. Run scripts/init.sh once first.
set -eu
. "$(dirname "$0")/env.sh"
T="$TEAMS_STATE"; R="$T/run"
mkdir -p "$R"
cd "$REPO"

start() { name=$1; shift; nohup "$@" >"$R/$name.log" 2>&1 & echo "$!" >"$R/$name.pid"; echo "started $name ($!)"; }
wait_port() { for _ in $(seq 1 60); do nc -z 127.0.0.1 "$1" 2>/dev/null && return 0; sleep 1; done; echo "port $1 did not open"; exit 1; }

start middleware uv run python -m openshell_teams.middleware --keys "$T/keys" --port 50061
wait_port 50061
start policy-lock uv run python -m openshell_teams.policy_lock --registry "$T/gate/registry.db" --port 50062
wait_port 50062
if [ -n "$GATEWAY_CMD" ]; then
  start gateway sh -c "$GATEWAY_CMD"
elif command -v brew >/dev/null 2>&1 && brew services list 2>/dev/null | grep -q '^openshell'; then
  brew services restart openshell
elif systemctl --user cat openshell-gateway >/dev/null 2>&1; then
  systemctl --user restart openshell-gateway
else
  echo "no gateway service found: start the gateway yourself with $GATEWAY_CONFIG, or set GATEWAY_CMD"; exit 1
fi
wait_port 17670
(cd "$OPENWORKER_DIR" && COWORKER_STATE_DIR="$OW_STATE" \
  COWORKER_API_TOKEN="$(cat "$T/operator.token")" \
  OPENWORKER_PASSPORT_PUBLIC_KEY="$T/keys/passport.pub" \
  OPENWORKER_PASSPORT_AUDIENCE=host.openshell.internal:8765 \
  OPENWORKER_BOARD_ADMIN_TOKEN="$(cat "$T/board-admin.token")" \
  start openworker uv run python -m coworker.server.run --host 127.0.0.1 --port 8765 --model openai:gpt-test)
wait_port 8765
start gate uv run python -m openshell_teams.api --state "$T/gate" --keys "$T/keys" --port 8766 \
  --openshell "$OPENSHELL_BIN" --prover "$OPENSHELL_PROVER" \
  --board-admin-url http://127.0.0.1:8765 --board-admin-token-file "$T/board-admin.token" \
  --operator-token-file "$T/operator.token" --image openworker:local
wait_port 8766
echo "stack up"
