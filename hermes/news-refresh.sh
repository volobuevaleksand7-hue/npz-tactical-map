#!/usr/bin/env bash
# news-refresh.sh — пересборка страницы дня /news/YYYY-MM-DD ПО СОБЫТИЮ и по таймеру.
#
# Зачем (ревизия 03.10.2026): gen-news.py гонялся только через publish-vps.sh —
# 04:55/16:55 (cron) и 08:30/14:30/20:30 (задача Гермеса NPZ PUBLISH). Страница дня
# отставала от данных до 6 часов (на проде 5 голосов при 18 в fuel-voices.json), а
# после 20:30 UTC до 04:55 следующего дня не пересобиралась вовсе.
#
# Кто зовёт:
#   • agents/git-sync.sh — в фоне после успешного push, если коммит тронул
#     data/strikes.json, data/fuel-voices.json или data/strikes-inbox.json
#     (только на VPS, см. NPZ_NEWS_AUTOREFRESH там);
#   • cron: ночной прогон 21:10 UTC (= 00:10 МСК, новый день) и плановый утренний.
#
# Как не плодить параллельные запуски:
#   1) ждём тот же /var/lock/npz-agent.lock, что и run-agent.sh (LLM-агенты и этот
#      скрипт идут строго по очереди; рабочее дерево VPS общее). Ждём до 20 мин;
#   2) второй вызов, пока первый ещё ждёт лок, НЕ ставится в очередь: он лишь кладёт
#      флаг «грязно», а работающий прогон после себя проверяет флаг и идёт ещё раз
#      (не больше 3 кругов). Данные из-под руки не теряются, очередь не растёт.
#
# Использование:  bash hermes/news-refresh.sh [причина]
set -uo pipefail

REPO="${NPZ_REPO:-/root/npz-tactical-map}"
REASON="${1:-manual}"
LOCK_AGENT=/var/lock/npz-agent.lock
LOCK_SELF=/var/lock/npz-news-refresh.lock
DIRTY=/var/lock/npz-news-refresh.dirty
LOG="$REPO/agents/logs/cron.log"

cd "$REPO" || { echo "news-refresh: нет репо $REPO" >&2; exit 2; }
mkdir -p "$(dirname "$LOG")"

# 1) очередь из одного: флаг + выход, если прогон уже идёт
touch "$DIRTY"
exec 8>"$LOCK_SELF"
if ! flock -n 8; then
  echo "=== news-refresh [$REASON] $(date -u +%FT%TZ): прогон уже идёт — флаг оставлен ==="
  exit 0
fi

# 2) общий лок агентов. fd 9 — тот же, что в run-agent.sh; если нас запустили из его
#    дерева (git-sync внутри run-agent), fd 9 унаследован с УЖЕ взятым локом — закрываем
#    его, иначе ждали бы сами себя до таймаута.
exec 9>&-
exec 9>"$LOCK_AGENT"
if ! flock -w "${NPZ_NEWS_LOCK_WAIT:-1200}" 9; then
  echo "=== news-refresh [$REASON] $(date -u +%FT%TZ): SKIP — лок агентов занят >${NPZ_NEWS_LOCK_WAIT:-1200}с ==="
  exit 0
fi

rc=0
for round in 1 2 3; do
  rm -f "$DIRTY"
  echo "=== news-refresh [$REASON] круг $round $(date -u +%FT%TZ) ==="
  bash hermes/publish-vps.sh --news-only
  rc=$?
  [ "$rc" != "0" ] && { touch "$DIRTY"; echo "news-refresh: publish-vps rc=$rc — флаг остаётся, повторит следующий вызов"; break; }
  [ -e "$DIRTY" ] || break
done
exit "$rc"
