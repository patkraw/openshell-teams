#!/bin/sh
# Stop the local stack started by scripts/up.sh (the gateway service keeps running).
. "$(dirname "$0")/env.sh"
pkill -f 'openshell_teams.api' ; pkill -f 'coworker.server.run' ; pkill -f 'openshell_teams.middleware' ; pkill -f 'openshell_teams.policy_lock'
[ -n "$GATEWAY_CMD" ] && pkill -f 'openshell-gateway'
echo "stack down"
