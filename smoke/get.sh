# usage: get PATH [EXTRA_HEADER]  — raw HTTP GET to the board via bash /dev/tcp
get() {
  exec 3<>/dev/tcp/host.openshell.internal/18765 || { echo "connect failed"; return; }
  printf 'GET %s HTTP/1.1\r\nHost: host.openshell.internal:18765\r\n%sConnection: close\r\n\r\n' "$1" "${2:+$2$'\r\n'}" >&3
  cat <&3 | tail -n 1; echo; exec 3>&-
}
echo "--- allowed path, forged header:"; get /v1/board/whoami "X-OpenShell-Caller: forged-by-agent"
echo "--- path not allowed by policy:"; get /v1/other
