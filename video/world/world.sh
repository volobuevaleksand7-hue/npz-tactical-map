#!/usr/bin/env bash
# Регулярный выпуск ролика про Индекс топливной напряжённости: сборка RU+EN -> YouTube (RU и Fuel Front) -> очистка.
#   ./world/world.sh [YYYY-MM-DD]     # дата по умолчанию — сегодня (МСК)
# Cron запускает ежедневно, но ролик выходит раз в WORLD_EVERY_DAYS (по умолчанию 3) дней — по маркерам out/world-*.uploaded.
# Переменные: WORLD_FORCE=1 — игнорировать интервал; WORLD_UPLOAD=0 — собрать без заливки; WORLD_EVERY_DAYS.
# Запускать под общим замком (как daily.sh): flock -w 2400 /var/lock/npz-video.lock nice -n 10 ./world/world.sh
# Появился в 23.10.2026: до этого ролик выходил единственный раз вручную (14.10), расписания не было.
set -uo pipefail
VIDEO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VIDEO"
export PATH="$HOME/.local/bin:$PATH"
DATE="${1:-$(TZ=Europe/Moscow date +%F)}"
[[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "world: дата YYYY-MM-DD" >&2; exit 2; }
EN_SECRETS="${NPZ_YT_EN_SECRETS:-$HOME/.config/npz-youtube-en}"
alert() {
  local t c; t="$(cat /root/.npz-bot/token 2>/dev/null)"; c="$(cat /root/.npz-bot/chat_id 2>/dev/null)"
  [ -n "$t" ] && [ -n "$c" ] && curl -s "https://api.telegram.org/bot$t/sendMessage" \
    --data-urlencode "chat_id=$c" --data-urlencode "text=$1" -o /dev/null
}
mkdir -p out
if [ "${WORLD_FORCE:-0}" != 1 ]; then
  last="$(ls out/world-*.uploaded 2>/dev/null | sed -E "s/.*world-([0-9-]{10})\.uploaded/\1/" | sort | tail -1)"
  if [ -n "$last" ]; then
    age=$(python3 -c "from datetime import date;print((date.fromisoformat(\"$DATE\")-date.fromisoformat(\"$last\")).days)")
    [ "$age" -ge "${WORLD_EVERY_DAYS:-3}" ] || exit 0   # рано: молчим, это штатный день без выпуска
  fi
fi
echo "[$(date -u +%FT%TZ)] world $DATE"
rc=0
ru=0; en=0
[ -f "out/world-$DATE.uploaded" ] || ru=1
[ -f "out/en-world-$DATE.uploaded" ] || en=1
if [ $ru = 1 ] && [ $en = 1 ]; then need=both; elif [ $ru = 1 ]; then need=ru; elif [ $en = 1 ]; then need=en; else
  echo "world: $DATE уже залит — пропуск"; exit 0; fi
t0=$(date +%s)
bash world/render_world.sh "$DATE" "$need" || { alert "🟠 НПЗ-карта: ролик про индекс напряжённости (/world) $DATE не собран. Лог: agents/logs/video.log"; exit 1; }
echo "world: собрано за $(( $(date +%s) - t0 )) с"
if [ "${WORLD_UPLOAD:-1}" != 0 ]; then
  if [ ! -f "out/world-$DATE.uploaded" ] && [ -f "out/world-$DATE.mp4" ] && [ -f "${NPZ_YT_SECRETS:-$HOME/.config/npz-youtube}/token.json" ]; then
    python3 upload.py world "$DATE" || { rc=$?; alert "🟠 НПЗ-карта: ролик /world $DATE собран, но не залился на RU-канал (rc=$rc)"; }
  fi
  if [ ! -f "out/en-world-$DATE.uploaded" ] && [ -f "out/en-world-$DATE.mp4" ] && [ -f "$EN_SECRETS/token.json" ]; then
    NPZ_YT_SECRETS="$EN_SECRETS" python3 upload.py en-world "$DATE" || { rc=$?; alert "🟠 Fuel Front: ролик /world $DATE собран, но не залился на EN-канал (rc=$rc)"; }
  fi
fi
bash ./cleanup.sh || rc=$?
find .build -maxdepth 1 \( -name "world-*" -o -name "en-world-*" \) -mtime +7 -exec rm -rf {} + 2>/dev/null
exit $rc
