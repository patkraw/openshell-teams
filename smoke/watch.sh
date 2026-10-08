#!/bin/sh
# Live, labelled feed of a demo run: Spawn Gate's admission steps and each agent's tool calls
# (with arguments) and messages. Start it before smoke/run_demo_team.py; Ctrl-C to stop.
. "$(dirname "$0")/../scripts/env.sh"
cd "$TEAMS_STATE" || exit 1
mkdir -p gate/logs && touch gate/logs/lead.log gate/logs/patcher.log gate/logs/reviewer.log run/gate.log
tail -n 0 -F gate/logs/lead.log gate/logs/patcher.log gate/logs/reviewer.log run/gate.log | awk '
  /^==> /{n=split($2,p,"/"); who=p[n]; sub(/\.log$/,"",who); next}
  who=="gate" && /admitted|rejected|step /{sub(/.*__main__ |.*openshell_teams\.gate /,""); print "[gate]     " $0; fflush(); next}
  /call |assistant_message ./{sub(/^openworker agent: /,""); sub(/^assistant_message /,"says: "); printf "[%-8s] %s\n", who, $0; fflush()}'
