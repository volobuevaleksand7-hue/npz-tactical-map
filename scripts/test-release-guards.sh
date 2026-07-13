#!/usr/bin/env bash
set -euo pipefail

root_dir=$(cd "$(dirname "$0")/.." && pwd)
tmp_dir=$(mktemp -d)
server_pid=""

cleanup() {
  if test -n "$server_pid"; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

make_valid_site() {
  local site_dir=$1

  mkdir -p "$site_dir/assets/radar"
  printf '<!DOCTYPE html><html><body><main id="map">OK</main></body></html>\n' > "$site_dir/index.html"
  cp "$site_dir/index.html" "$site_dir/radar"
  printf ':root { --ok: 1; }\n' > "$site_dir/styles.css"
  printf '{"version":"1.0.0","releasedAt":"2026-07-13"}\n' > "$site_dir/version.json"
  printf 'RIFF\024\0\0\0WEBPVP8 ' > "$site_dir/assets/radar/threat-drone.webp"
}

expect_failure() {
  if "$@"; then
    echo "Expected command to fail: $*" >&2
    exit 1
  fi
}

valid_dir="$tmp_dir/valid"
wrapped_dir="$tmp_dir/wrapped"
make_valid_site "$valid_dir"
make_valid_site "$wrapped_dir"
printf '{"data":"PCFET0NUWVBFIGh0bWw+"}\n' > "$wrapped_dir/index.html"

"$root_dir/scripts/verify-release-output.sh" "$valid_dir"
expect_failure "$root_dir/scripts/verify-release-output.sh" "$wrapped_dir"

port=$(python3 -c 'import socket; socket_instance = socket.socket(); socket_instance.bind(("127.0.0.1", 0)); print(socket_instance.getsockname()[1]); socket_instance.close()')
python3 -m http.server "$port" --directory "$valid_dir" >/dev/null 2>&1 &
server_pid=$!
ready=0
for _ in $(seq 1 20); do
  if curl --silent --fail "http://127.0.0.1:$port/" >/dev/null; then
    ready=1
    break
  fi
  sleep 0.1
done
test "$ready" -eq 1 || { echo "Test HTTP server did not start" >&2; exit 1; }

"$root_dir/scripts/verify-release-url.sh" "http://127.0.0.1:$port"

kill "$server_pid"
wait "$server_pid" 2>/dev/null || true
server_pid=""
python3 -m http.server "$port" --directory "$wrapped_dir" >/dev/null 2>&1 &
server_pid=$!
ready=0
for _ in $(seq 1 20); do
  if curl --silent --fail "http://127.0.0.1:$port/" >/dev/null; then
    ready=1
    break
  fi
  sleep 0.1
done
test "$ready" -eq 1 || { echo "Test HTTP server did not restart" >&2; exit 1; }

expect_failure "$root_dir/scripts/verify-release-url.sh" "http://127.0.0.1:$port"
echo "release guard tests passed"
