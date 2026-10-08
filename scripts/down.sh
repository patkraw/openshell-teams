#!/bin/sh
# Stop the local stack started by scripts/up.sh.
pkill -f 'openshell_teams.api' ; pkill -f 'coworker.server.run' ; pkill -f 'openshell-0.1.2/bin/openshell-gateway' ; pkill -f 'openshell_teams.middleware' ; pkill -f 'openshell_teams.policy_lock'
echo "stack down"
