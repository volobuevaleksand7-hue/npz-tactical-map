#!/usr/bin/env bash
# Рилс «Топливный фронт РФ»: карта сайта -> удары дня -> кадры очевидцев -> итог.
#   ./reel/render_reel.sh 2026-10-02
# Результат: video/out/reel-<дата>.mp4 (1080×1920) + reel-<дата>.txt (заголовок/описание).
# Нужны: node_modules в video/ (npm ci), Chrome (скриншот карты), ffmpeg, yt-dlp (необязательно), сеть
# (сайт, тайлы OSM, t.me). Клипы кэшируются в video/reel/cache/.
set -euo pipefail
VIDEO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VIDEO"
DATE="${1:?дата YYYY-MM-DD}"
[[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "render_reel.sh: дата YYYY-MM-DD" >&2; exit 2; }
[ -x node_modules/.bin/hyperframes ] || { echo "render_reel.sh: нет node_modules — 'npm ci' в $VIDEO" >&2; exit 2; }
export DO_NOT_TRACK=1 HYPERFRAMES_NO_TELEMETRY=1 HYPERFRAMES_NO_UPDATE_CHECK=1 \
       HYPERFRAMES_NO_FEEDBACK=1 HYPERFRAMES_NO_AUTO_INSTALL=1
KIND="${REEL_KIND:-reel}"   # reel — рилс дня; urgent — срочный по REEL_ONLY (см. build_reel.py)
BUILD="$VIDEO/.build/$KIND-$DATE"
OUT="$VIDEO/out/$KIND-$DATE.mp4"
mkdir -p "$VIDEO/out"
t0=$(date +%s)
[ "${REEL_KEEP_PREP:-0}" = 1 ] && [ -f "$BUILD/clips.json" ] || { rm -rf "$BUILD"; python3 reel/build_reel.py prepare "$DATE" "$BUILD"; }
python3 reel/build_reel.py compose "$DATE" "$BUILD"
node_modules/.bin/hyperframes render "$BUILD" -o "$BUILD/silent.mp4" \
  --quality "${HF_QUALITY:-looks}" --workers "${HF_WORKERS:-auto}" --quiet
python3 build.py mix "$BUILD" "$BUILD/silent.mp4" "$OUT.tmp.mp4"
mv -f "$OUT.tmp.mp4" "$OUT"
echo "[$(date -u +%FT%TZ)] ok $OUT ($(du -h "$OUT" | cut -f1), $(( $(date +%s) - t0 )) с)"
