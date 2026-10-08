#!/bin/sh
# Live, labelled feed of a demo run. Start it before smoke/run_demo_team.py; Ctrl-C to stop.
#   [gate]     Spawn Gate: each request and admission step (grant, prover, create, launch check, start, stop)
#   [passport] each request leaving a sandbox, with the identity the supervisor attached
#   [board]    each board call by a sandboxed agent, and its status (polling is left out)
#   [lock]     Policy Lock decisions on gateway calls
#   [lead] [patcher] [reviewer]  wake-ups, tool calls with arguments, results, messages, turn summaries
# Prover inputs and outputs are kept in $TEAMS_STATE/gate/proofs/.
. "$(dirname "$0")/../scripts/env.sh"
cd "$TEAMS_STATE" || exit 1
mkdir -p gate/logs run
for f in gate/logs/lead.log gate/logs/patcher.log gate/logs/reviewer.log run/gate.log run/middleware.log \
         run/policy-lock.log run/openworker.log; do touch "$f"; done
tail -n 0 -F gate/logs/lead.log gate/logs/patcher.log gate/logs/reviewer.log run/gate.log run/middleware.log \
     run/policy-lock.log run/openworker.log | awk '
  function out(label, text) { printf "%-10s %s\n", "[" label "]", text; fflush() }
  /^==> /{ n = split($2, p, "/"); who = p[n]; sub(/\.log$/, "", who); next }
  who == "gate"        { if ($0 ~ / (request|step|stop|admitted|rejected) /) { sub(/^.*(__main__|openshell_teams\.gate) /, ""); out("gate", $0) } next }
  who == "middleware"  { if ($0 ~ /passport / && $0 !~ /\/v1\/board\/pending/) { sub(/^.*passport /, ""); out("passport", $0) } next }
  who == "policy-lock" { if ($0 ~ /(allow|DENY) /) { sub(/^.*__main__ /, ""); out("lock", $0) } next }
  who == "openworker"  { if ($0 ~ /^board: /) { sub(/^board: /, ""); out("board", $0) } next }
  /^openworker agent: (call|wake|turn|result|assistant_message .)/ {
    sub(/^openworker agent: /, ""); sub(/^assistant_message /, "says: ")
    if (length($0) > 300) $0 = substr($0, 1, 300) "…"
    out(who, $0)
  }'
