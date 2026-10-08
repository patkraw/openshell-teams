#!/bin/sh
# One-time setup: state directory, operator and board-admin tokens, and the gateway
# registrations for the Passport middleware and Policy Lock. Safe to run again.
set -eu
. "$(dirname "$0")/env.sh"
[ -n "$OPENSHELL_BIN" ] || { echo "openshell not found: install OpenShell or set OPENSHELL_BIN"; exit 1; }
[ -n "$OPENSHELL_PROVER" ] || { echo "openshell-prover not found: set OPENSHELL_PROVER"; exit 1; }
mkdir -p "$TEAMS_STATE/run" "$TEAMS_STATE/gate" "$OW_STATE"
umask 077
for t in operator board-admin; do
  [ -s "$TEAMS_STATE/$t.token" ] || python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > "$TEAMS_STATE/$t.token"
done
umask 022
SNIPPET="$REPO/docs/examples/gateway-registrations.toml"
mkdir -p "$(dirname "$GATEWAY_CONFIG")"
if [ ! -f "$GATEWAY_CONFIG" ]; then
  printf '[openshell]\nversion = 2\n\n' > "$GATEWAY_CONFIG"
  cat "$SNIPPET" >> "$GATEWAY_CONFIG"
  echo "wrote $GATEWAY_CONFIG"
elif grep -q 'name = "policy-lock"' "$GATEWAY_CONFIG"; then
  echo "$GATEWAY_CONFIG already registers the middleware and Policy Lock"
else
  printf '\n' >> "$GATEWAY_CONFIG"
  cat "$SNIPPET" >> "$GATEWAY_CONFIG"
  echo "appended the registrations to $GATEWAY_CONFIG"
fi
echo "state in $TEAMS_STATE"
