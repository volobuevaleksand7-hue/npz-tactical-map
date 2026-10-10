#!/usr/bin/env bash
# Недельный обзор «Топливный фронт РФ» (16:9, 1920×1080, ~4-7 мин): карта -> удары недели по дням -> баланс -> ссылка.
#   ./weekly/weekly.sh [YYYY-MM-DD]       # дата = последний день недели, по умолчанию сегодня (МСК)
# Рендер -> аудит -> YouTube (RU) -> английская версия (Fuel Front) -> очистка. Telegram НЕ постим: tg_post.py вертикальный.
# Переменные: WEEKLY_UPLOAD=0 — без заливки на YouTube (тест); WEEKLY_EN=0 — без английской версии;
# WEEKLY_KEEP_PREP=1 — не пересобирать кадры/карту; HF_FPS (24), HF_WORKERS (auto), HF_QUALITY (looks).
# Блокировки (11.10.2026): рендер обзора идёт 1–2 часа на 2 ядрах — держать на нём общий /var/lock/npz-video.lock
# значит заблокировать срочные ролики и рилсы. Поэтому cron берёт ОТДЕЛЬНЫЙ замок /var/lock/npz-weekly.lock (защита от
# двойного запуска), а общий /var/lock/npz-video.lock берётся здесь только на короткие шаги (prepare, compose, mix,
# thumb, upload: общий кэш озвучки/клипов, сеть). Сам рендер идёт без общего замка, под nice 19 / ionice idle и с
# HF_WORKERS=2 (по умолчанию), так что срочный ролик (nice 10) забирает процессор первым.
# Без tty: cron не даёт pty — как и daily.sh, рендер работает из cron, пока жив родительский скрипт; из nohup/setsid
# вызов падает с render_cancelled_parent_exited, поэтому ручной прогон — только в tmux.
set -uo pipefail
VIDEO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$VIDEO"
export PATH="$HOME/.local/bin:$PATH"
export DO_NOT_TRACK=1 HYPERFRAMES_NO_TELEMETRY=1 HYPERFRAMES_NO_UPDATE_CHECK=1 HYPERFRAMES_NO_FEEDBACK=1 HYPERFRAMES_NO_AUTO_INSTALL=1
DATE="${1:-$(TZ=Europe/Moscow date +%F)}"
[[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "weekly: дата YYYY-MM-DD" >&2; exit 2; }
[ -x node_modules/.bin/hyperframes ] || { echo "weekly: нет node_modules — npm ci в $VIDEO" >&2; exit 2; }
BUILD="$VIDEO/.build/weekly-$DATE"; OUT="$VIDEO/out/weekly-$DATE.mp4"
VLOCK=/var/lock/npz-video.lock
vlock() { flock -w "${WEEKLY_LOCK_WAIT:-3600}" "$VLOCK" "$@"; }       # короткий шаг под общим замком
export HF_WORKERS="${HF_WORKERS:-2}"
rc=0
echo "[$(date -u +%FT%TZ)] weekly $DATE"
if [ -f "out/weekly-$DATE.uploaded" ]; then echo "weekly: $DATE уже залит — пропуск"; exit 0; fi
alert() {
  local t c; t="$(cat /root/.npz-bot/token 2>/dev/null)"; c="$(cat /root/.npz-bot/chat_id 2>/dev/null)"
  [ -n "$t" ] && [ -n "$c" ] && curl -s "https://api.telegram.org/bot$t/sendMessage" \
    --data-urlencode "chat_id=$c" --data-urlencode "text=$1" -o /dev/null
}
mkdir -p out
for try in 1 2; do
  t0=$(date +%s)
  if [ "${WEEKLY_KEEP_PREP:-0}" = 1 ] && [ -f "$BUILD/clips.json" ]; then :; else
    rm -rf "$BUILD"; vlock python3 weekly/build_weekly.py prepare --end-date "$DATE" || { r=$?
      [ "$r" = 4 ] && { echo "weekly: за неделю нет ударов — выпуск пропущен"; exit 0; }
      alert "🟠 НПЗ-карта: недельный обзор $DATE не собран (prepare rc=$r). Лог: agents/logs/video.log"; exit "$r"; }
  fi
  vlock python3 weekly/build_weekly.py compose --end-date "$DATE" || { r=$?
    if [ "$r" = 5 ] && [ "$try" = 1 ]; then echo "weekly: озвучка недоступна — повтор через ${WEEKLY_RETRY_WAIT:-600} с"; sleep "${WEEKLY_RETRY_WAIT:-600}"; WEEKLY_KEEP_PREP=1; continue; fi
    alert "🟠 НПЗ-карта: недельный обзор $DATE не собран (compose rc=$r)"; exit "$r"; }
  nice -n 19 ionice -c3 node_modules/.bin/hyperframes render "$BUILD" -o "$BUILD/silent.mp4" --quality "${HF_QUALITY:-looks}" \
    --workers "$HF_WORKERS" --fps "${HF_FPS:-24}" --quiet || { echo "weekly: рендер упал"; alert "🟠 НПЗ-карта: рендер недельного обзора $DATE упал"; exit 1; }
  vlock python3 build.py mix "$BUILD" "$BUILD/silent.mp4" "$OUT.tmp.mp4" && mv -f "$OUT.tmp.mp4" "$OUT" || exit 1
  python3 weekly/build_weekly.py thumb --end-date "$DATE" || true
  echo "[$(date -u +%FT%TZ)] ok $OUT ($(du -h "$OUT" | cut -f1), $(( $(date +%s) - t0 )) с)"
  audit_out="$(python3 weekly/audit_weekly.py "$DATE" weekly)" && break
  echo "$audit_out"
  if [ "$try" = 2 ]; then
    alert "🟠 НПЗ-карта: недельный обзор $DATE не прошёл аудит дважды:
$(echo "$audit_out" | grep FAIL | head -5)"; exit 3
  fi
  echo "weekly: аудит не пройден — пересборка через ${WEEKLY_RETRY_WAIT:-600} с"; sleep "${WEEKLY_RETRY_WAIT:-600}"
done
echo "$audit_out"
if [ "${WEEKLY_UPLOAD:-1}" != 0 ] && [ -f "${NPZ_YT_SECRETS:-$HOME/.config/npz-youtube}/token.json" ]; then
  vlock python3 upload.py weekly "$DATE" || rc=$?
fi
EN_SECRETS="${NPZ_YT_EN_SECRETS:-$HOME/.config/npz-youtube-en}"
if [ "${WEEKLY_EN:-1}" != 0 ] && [ -f "$BUILD/plan.json" ] && [ ! -f "out/en-weekly-$DATE.uploaded" ]; then
  if python3 weekly/en_weekly.py "$DATE"; then
    python3 weekly/audit_weekly.py "$DATE" en-weekly || rc=1
    if [ "${WEEKLY_UPLOAD:-1}" != 0 ] && [ -f "$EN_SECRETS/token.json" ]; then
      NPZ_YT_SECRETS="$EN_SECRETS" vlock python3 upload.py en-weekly "$DATE" || rc=$?
    fi
  else
    rc=1; echo "weekly: английская версия $DATE не собрана"
  fi
fi
bash ./cleanup.sh || rc=$?
find .build -maxdepth 1 \( -name "weekly-*" -o -name "en-weekly-*" \) -mtime +14 -exec rm -rf {} + 2>/dev/null
exit $rc
