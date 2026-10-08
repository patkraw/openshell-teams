#!/bin/sh
# Settings shared by init.sh, up.sh, down.sh and the smoke scripts. Override any of them
# in the environment or in $TEAMS_ENV (default ~/.config/openshell-teams/env, KEY=VALUE lines).
TEAMS_ENV="${TEAMS_ENV:-$HOME/.config/openshell-teams/env}"
# shellcheck disable=SC1090
[ -f "$TEAMS_ENV" ] && . "$TEAMS_ENV"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
OPENSHELL_BIN="${OPENSHELL_BIN:-$(command -v openshell || true)}"
OPENSHELL_PROVER="${OPENSHELL_PROVER:-$(command -v openshell-prover || true)}"
TEAMS_STATE="${TEAMS_STATE:-$HOME/.local/state/openshell-teams}"   # tokens, keys, registry, logs
OW_STATE="${OW_STATE:-$TEAMS_STATE/openworker}"                       # the OpenWorker board's state
OPENWORKER_DIR="${OPENWORKER_DIR:-$REPO/../openworker}"               # checkout of patkraw/openworker, branch teams
GATEWAY_CONFIG="${GATEWAY_CONFIG:-$HOME/.config/openshell/gateway.toml}"
# How to (re)start the gateway after the middleware and Policy Lock are up. Empty: restart the
# service the OpenShell installer set up (Homebrew on macOS, systemd user service on Linux).
GATEWAY_CMD="${GATEWAY_CMD:-}"
export OPENSHELL_BIN OPENSHELL_PROVER TEAMS_STATE OW_STATE OPENWORKER_DIR GATEWAY_CONFIG GATEWAY_CMD
