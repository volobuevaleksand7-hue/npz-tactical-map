#!/usr/bin/env bash
# Утренний рилс (cron Гермеса 06:40 UTC -> выход ~10:00 МСК): все удары ВЧЕРАШНЕГО дня (МСК) —
# к утру ночные прогоны сборщиков (04:35 UTC strikes, newswatch, strike-pipeline) день уже закрыли.
#   ./reel/morning.sh [YYYY-MM-DD]
# Рендер -> YouTube -> Telegram-канал (анонимный бот) -> реестр data/videos.json -> очистка.
set -uo pipefail
VIDEO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VIDEO"
export PATH="$HOME/.local/bin:$PATH"   # edge-tts, yt-dlp (venv, см. README)
DATE="${1:-$(TZ=Europe/Moscow date -d yesterday +%F 2>/dev/null || TZ=Europe/Moscow date -v-1d +%F)}"
rc=0
echo "[$(date -u +%FT%TZ)] morning reel $DATE"
./reel/render_reel.sh "$DATE" || { rc=$?; echo "morning: рилс $DATE не собран (rc=$rc)"; exit $rc; }
if [ -f "${NPZ_YT_SECRETS:-$HOME/.config/npz-youtube}/token.json" ]; then
  python3 upload.py reel "$DATE" || rc=$?
fi
python3 tg_post.py reel "$DATE" || rc=$?
if [ -n "$(git -C .. status --porcelain -- data/videos.json)" ]; then
  (cd .. && bash agents/git-sync.sh "data(video): реестр роликов YouTube") || rc=$?
fi
bash ./cleanup.sh || rc=$?
find .build -maxdepth 1 -name "reel-*" -mtime +3 -exec rm -rf {} + 2>/dev/null   # черновики рендера
exit $rc
