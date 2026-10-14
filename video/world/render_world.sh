#!/usr/bin/env bash
# Ролик про Индекс топливной напряжённости (/world): RU и EN из одних данных.
#   ./world/render_world.sh 2026-10-13 [ru|en|both]
# Результат: video/out/world-<дата>.{mp4,txt,jpg} (RU) и video/out/en-world-<дата>.{mp4,txt,jpg} (EN).
# Не публикует. Публикация: python3 upload.py world <дата> / NPZ_YT_SECRETS=~/.config/npz-youtube-en python3 upload.py en-world <дата>
set -euo pipefail
VIDEO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VIDEO"
DATE="${1:?дата YYYY-MM-DD}"; WHICH="${2:-both}"
[[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "render_world.sh: дата YYYY-MM-DD" >&2; exit 2; }
[ -x node_modules/.bin/hyperframes ] || { echo "render_world.sh: нет node_modules — 'npm ci' в $VIDEO" >&2; exit 2; }
export DO_NOT_TRACK=1 HYPERFRAMES_NO_TELEMETRY=1 HYPERFRAMES_NO_UPDATE_CHECK=1 \
       HYPERFRAMES_NO_FEEDBACK=1 HYPERFRAMES_NO_AUTO_INSTALL=1
mkdir -p out
for LANG_ in ru en; do
  [ "$WHICH" = both ] || [ "$WHICH" = "$LANG_" ] || continue
  PFX=world; [ "$LANG_" = en ] && PFX=en-world
  BUILD="$VIDEO/.build/$PFX-$DATE"
  OUT="$VIDEO/out/$PFX-$DATE"
  t0=$(date +%s)
  python3 world/build_world.py compose "$LANG_" "$BUILD" "$DATE"
  node_modules/.bin/hyperframes render "$BUILD" -o "$BUILD/silent.mp4" \
    --quality "${HF_QUALITY:-looks}" --workers "${HF_WORKERS:-auto}" --quiet
  python3 build.py mix "$BUILD" "$BUILD/silent.mp4" "$OUT.tmp.mp4"
  mv -f "$OUT.tmp.mp4" "$OUT.mp4"
  cp -f "$BUILD/description.txt" "$OUT.txt"
  PT=$(python3 -c "import json;print(json.load(open('$BUILD/plan.json')).get('poster_t',1.0))")
  ffmpeg -v error -y -ss "$PT" -i "$OUT.mp4" -frames:v 1 -q:v 3 "$OUT.jpg"
  echo "[$(date -u +%FT%TZ)] ok $OUT.mp4 ($(du -h "$OUT.mp4" | cut -f1), $(( $(date +%s) - t0 )) с)"
done
