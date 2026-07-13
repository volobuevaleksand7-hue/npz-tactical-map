#!/usr/bin/env bash
set -euo pipefail

static_dir=${1:-.vercel/output/static}

fail() {
  echo "Release artifact check failed: $1" >&2
  exit 1
}

test -d "$static_dir" || fail "missing static output directory: $static_dir"

is_data_envelope() {
  node -e '
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
  ' "$1"
}

check_text_file() {
  local file=$1

  if is_data_envelope "$file"; then
    fail "JSON/Base64 data envelope in $file"
  fi
}

check_image_file() {
  local file=$1
  local extension=$2
  local signature

  signature=$(od -An -tx1 -N12 "$file" | tr -d ' \n')
  case "$extension" in
    png) [[ ${signature:0:16} == 89504e470d0a1a0a ]] || fail "invalid PNG signature: $file" ;;
    webp) [[ ${signature:0:8} == 52494646 && ${signature:16:8} == 57454250 ]] || fail "invalid WebP signature: $file" ;;
    jpg|jpeg) [[ ${signature:0:6} == ffd8ff ]] || fail "invalid JPEG signature: $file" ;;
    gif) [[ ${signature:0:8} == 47494638 ]] || fail "invalid GIF signature: $file" ;;
    ico) [[ ${signature:0:8} == 00000100 ]] || fail "invalid ICO signature: $file" ;;
  esac
}

while IFS= read -r -d '' file; do
  extension=${file##*.}
  extension=$(printf '%s' "$extension" | tr '[:upper:]' '[:lower:]')

  case "$extension" in
    html|htm|css|js|mjs|json|txt|xml|webmanifest|svg)
      check_text_file "$file"
      ;;
    png|webp|jpg|jpeg|gif|ico)
      check_image_file "$file" "$extension"
      ;;
  esac
done < <(find "$static_dir" -type f -print0)

echo "Release artifact check passed: $static_dir"
