#!/usr/bin/env bash
set -euo pipefail

base_url=${1:?Usage: verify-release-url.sh <deployment-url>}
base_url=${base_url%/}
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT

fail() {
  echo "Release URL check failed: $1" >&2
  exit 1
}

fetch() {
  local path=$1
  local destination=$2

  if test -n "${VERCEL_DEPLOYMENT:-}"; then
    vercel curl "$path" --deployment "$VERCEL_DEPLOYMENT" -- --silent --show-error > "$destination"
  else
    curl --fail --silent --show-error --location "$base_url$path" > "$destination"
  fi
}

assert_not_data_envelope() {
  local file=$1

  if node -e '
    const fs = require("fs");
    try {
      const value = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
      const keys = Object.keys(value || {});
      process.exit(
        keys.length === 1 && keys[0] === "data" &&
        typeof value.data === "string" &&
        /^[A-Za-z0-9+/]+={0,2}$/.test(value.data)
          ? 0
          : 1
      );
    } catch {
      process.exit(1);
    }
  ' "$file"; then
    fail "JSON/Base64 data envelope at $2"
  fi
}

assert_html() {
  local file=$1
  local path=$2
  local prefix

  assert_not_data_envelope "$file" "$path"
  prefix=$(head -c 512 "$file" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
  [[ $prefix == '<!doctypehtml>'* || $prefix == '<html'* ]] || fail "expected HTML at $path"
}

assert_webp() {
  local file=$1
  local signature

  signature=$(od -An -tx1 -N12 "$file" | tr -d ' \n')
  [[ ${signature:0:8} == 52494646 && ${signature:16:8} == 57454250 ]] || fail "expected WebP at $2"
}

fetch / "$tmp_dir/index.html"
assert_html "$tmp_dir/index.html" /

fetch /radar "$tmp_dir/radar.html"
assert_html "$tmp_dir/radar.html" /radar

fetch /styles.css "$tmp_dir/styles.css"
assert_not_data_envelope "$tmp_dir/styles.css" /styles.css
grep -qE '(:root|[[:alnum:]_-]+[[:space:]]*\{)' "$tmp_dir/styles.css" || fail "expected CSS at /styles.css"

fetch /version.json "$tmp_dir/version.json"
assert_not_data_envelope "$tmp_dir/version.json" /version.json
node -e '
  const value = require(process.argv[1]);
  if (typeof value.version !== "string" || !value.version ||
      typeof value.releasedAt !== "string" || !value.releasedAt) process.exit(1);
' "$tmp_dir/version.json" || fail "expected release version at /version.json"

fetch /assets/radar/threat-drone.webp "$tmp_dir/threat-drone.webp"
assert_webp "$tmp_dir/threat-drone.webp" /assets/radar/threat-drone.webp

echo "Release URL check passed: $base_url"
