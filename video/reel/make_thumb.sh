#!/usr/bin/env bash
# Обложка YouTube «поверх карты»: снимок страницы <сборка>/thumb (её пишет build_reel.py compose) на 0,9 с -> JPG.
#   ./reel/make_thumb.sh <каталог сборки> <выход.jpg>
# Код возврата != 0 — обложка не сделана; вызывающий откатывается на кадр из mp4.
set -euo pipefail
VIDEO="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="${1:?каталог сборки}"; JPG="${2:?выходной jpg}"
[ -f "$BUILD/thumb/index.html" ] || { echo "make_thumb: нет $BUILD/thumb" >&2; exit 1; }
export DO_NOT_TRACK=1 HYPERFRAMES_NO_TELEMETRY=1 HYPERFRAMES_NO_UPDATE_CHECK=1 \
       HYPERFRAMES_NO_FEEDBACK=1 HYPERFRAMES_NO_AUTO_INSTALL=1
SNAP="$BUILD/thumb-snap"
rm -rf "$SNAP"
# --describe false: иначе hyperframes сам шлёт кадр в Gemini и доустанавливает пакет
( cd "$VIDEO" && node_modules/.bin/hyperframes snapshot "$BUILD/thumb" --at "${REEL_POSTER_T:-0.9}" --no-end \
    --describe false -o "$SNAP" >/dev/null )
PNG="$(ls "$SNAP"/frame-*.png 2>/dev/null | head -1)"
[ -n "$PNG" ] || { echo "make_thumb: снимок не получен" >&2; exit 1; }
for q in 3 6 10; do   # YouTube: обложка до 2 МБ
  ffmpeg -y -v error -i "$PNG" -frames:v 1 -vf "scale=1080:1920" -q:v "$q" "$JPG.tmp.jpg"
  [ "$(stat -f%z "$JPG.tmp.jpg" 2>/dev/null || stat -c%s "$JPG.tmp.jpg")" -le 2000000 ] && break
done
mv -f "$JPG.tmp.jpg" "$JPG"
rm -rf "$SNAP"
