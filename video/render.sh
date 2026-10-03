#!/usr/bin/env bash
# Ежедневный ролик-сводка «Топливный фронт РФ».
#   ./render.sh               — последняя дата, для которой есть news/<дата>.html
#   ./render.sh 2026-09-26    — конкретная дата
# Результат: video/out/npz-<дата>.mp4 (1080×1920, H.264 + AAC).
# Переменные: HF_WORKERS (по умолчанию auto; на машинах <=8 ГБ HyperFrames сам
# включает low-memory режим с 1 воркером), HF_QUALITY (draft|looks|delivery, по умолчанию looks).
set -euo pipefail
VIDEO="$(cd "$(dirname "$0")" && pwd)"
cd "$VIDEO"

DATE="${1:-$(python3 build.py latest)}"
[[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "render.sh: дата YYYY-MM-DD, получено '$DATE'" >&2; exit 2; }
[ -x node_modules/.bin/hyperframes ] || { echo "render.sh: нет node_modules — сначала 'npm ci' в $VIDEO" >&2; exit 2; }

# Рендер полностью офлайн: без телеметрии, проверок обновлений и автоустановок.
export DO_NOT_TRACK=1 HYPERFRAMES_NO_TELEMETRY=1 HYPERFRAMES_NO_UPDATE_CHECK=1 \
       HYPERFRAMES_NO_FEEDBACK=1 HYPERFRAMES_NO_AUTO_INSTALL=1

BUILD="$VIDEO/.build/$DATE"
OUT="$VIDEO/out/npz-$DATE.mp4"
mkdir -p "$VIDEO/out"
t0=$(date +%s)
echo "[$(date -u +%FT%TZ)] render $DATE"

python3 build.py compose "$DATE" "$BUILD"
node_modules/.bin/hyperframes render "$BUILD" -o "$BUILD/silent.mp4" \
  --quality "${HF_QUALITY:-looks}" --workers "${HF_WORKERS:-auto}" --quiet
python3 build.py mix "$BUILD" "$BUILD/silent.mp4" "$OUT.tmp.mp4"
mv -f "$OUT.tmp.mp4" "$OUT"
rm -rf "$BUILD"   # при ошибке каталог остаётся для разбора

echo "[$(date -u +%FT%TZ)] ok $OUT ($(du -h "$OUT" | cut -f1), $(( $(date +%s) - t0 )) с)"
