#!/usr/bin/env bash
# Рилс дня — cron Гермеса 08:00 UTC: собирает рилс за ВЧЕРА (МСК, день уже полный, как эталон 04.10)
# и публикует ровно в 12:00 МСК (REEL_PUBLISH_AT, UTC). Перед рендером — свежий проход сборщика ударов.
#   ./reel/daily.sh [YYYY-MM-DD]
# Срочный рилс (без расписания): REEL_KIND=urgent REEL_ONLY=<id,...> ./reel/daily.sh <дата> —
# зовёт hermes/bot/strike_pipeline.py после молнии; один срочный на дату, публикуется сразу.
# Рендер -> аудит -> YouTube -> Telegram-канал (анонимный бот) -> реестр data/videos.json -> очистка.
set -uo pipefail
VIDEO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VIDEO"
export PATH="$HOME/.local/bin:$PATH"   # edge-tts, yt-dlp (venv, см. README)
KIND="${REEL_KIND:-reel}"; export REEL_KIND="$KIND"
if [ "$KIND" = urgent ]; then
  DATE="${1:-$(TZ=Europe/Moscow date +%F)}"
  REEL_REFRESH=0                       # удар только что пришёл из strikes.json — проход не нужен
  PUBLISH_AT=""                        # срочный — сразу
else
  DATE="${1:-$(TZ=Europe/Moscow date -d yesterday +%F)}"
  PUBLISH_AT="${REEL_PUBLISH_AT-09:00}" # 12:00 МСК; пусто — публиковать сразу после сборки
fi
rc=0
echo "[$(date -u +%FT%TZ)] $KIND $DATE"
if [ -f "out/$KIND-$DATE.uploaded" ]; then echo "reel: $KIND $DATE уже залит — пропуск"; exit 0; fi
# свежий проход сборщика ударов прямо перед рендером: удары дня докатываются в strikes.json
# с опозданием в часы (Волгоград 05.10 пришёл в 00:23 МСК). REEL_REFRESH=0 — без прохода.
if [ "${REEL_REFRESH:-1}" != "0" ] && [ -x ../agents/run-agent.sh ]; then
  NPZ_MODEL="${NPZ_MODEL:-claude-haiku-4-5-20251001}" NPZ_LOCK_WAIT=900 \
    ../agents/run-agent.sh "$(cd .. && pwd)/agents/update-prompt-strikes.md" strikes-reel \
    || echo "reel: сборщик ударов не отработал — рендер по текущим данным"
fi
./reel/render_reel.sh "$DATE" || { rc=$?; echo "reel: $KIND $DATE не собран (rc=$rc)"; exit $rc; }
python3 reel/audit.py "$DATE" "$KIND" || { echo "reel: аудит не пройден — YouTube/Telegram пропущены (REEL_AUDIT=0 отключает)"; [ "${REEL_AUDIT:-1}" = "0" ] || exit 3; }
if [ -n "$PUBLISH_AT" ]; then
  wait_s=$(( $(date -u -d "today $PUBLISH_AT" +%s) - $(date -u +%s) ))
  [ "$wait_s" -gt 0 ] && { echo "reel: собран, выход в $PUBLISH_AT UTC (через ${wait_s} с)"; sleep "$wait_s"; }
fi
if [ -f "${NPZ_YT_SECRETS:-$HOME/.config/npz-youtube}/token.json" ]; then
  python3 upload.py "$KIND" "$DATE" || rc=$?
fi
python3 tg_post.py "$KIND" "$DATE" || rc=$?
if [ -n "$(git -C .. status --porcelain -- data/videos.json)" ]; then
  (cd .. && bash agents/git-sync.sh "data(video): реестр роликов YouTube") || rc=$?
fi
bash ./cleanup.sh || rc=$?
find .build -maxdepth 1 \( -name "reel-*" -o -name "urgent-*" \) -mtime +3 -exec rm -rf {} + 2>/dev/null   # черновики рендера
exit $rc
