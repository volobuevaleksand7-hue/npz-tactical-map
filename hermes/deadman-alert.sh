#!/usr/bin/env bash
# deadman-alert.sh — НЕЗАВИСИМЫЙ сторож публикации НПЗ-карты.
# Смотрит возраст последнего коммита на origin (radar пушит каждые ~10 мин).
# Молчит origin дольше порога → пинг в Telegram. НЕ зависит от health.json/watchdog:
# те умирают вместе с флотом (30.07: floot встал 13ч, health=healthy). Инцидент:
# осиротевшие git-стэши рушили git-sync → origin замер, а плашка была «healthy».
set -uo pipefail
REPO=/root/npz-tactical-map
TOKEN="$(cat /root/.npz-bot/token 2>/dev/null)"
CHAT="$(cat /root/.npz-bot/chat_id 2>/dev/null)"
THRESH_MIN=45                         # >45 мин тишины origin = аномалия
COOLDOWN=3600                         # не спамить: не чаще раза в час
STATE=/root/.npz-bot/deadman-last-alert
cd "$REPO" || exit 0
[ -n "$TOKEN" ] && [ -n "$CHAT" ] || exit 0
git fetch origin -q 2>/dev/null || true
last="$(git log origin/main -1 --format=%ct 2>/dev/null)"; [ -n "$last" ] || exit 0
now="$(date +%s)"; age=$(( (now - last) / 60 ))
(( age > THRESH_MIN )) || { echo "ok: origin $age мин назад"; exit 0; }
la="$(cat "$STATE" 2>/dev/null || echo 0)"
(( now - la > COOLDOWN )) || { echo "stale $age мин, но в cooldown"; exit 0; }
msg="🔴 НПЗ-карта: origin молчит ${age} мин (порог ${THRESH_MIN}). Публикация встала. Проверь на hermes: git stash list, tail agents/logs/cron.log, grep конфликт-маркеры в data/."
curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" --data-urlencode "chat_id=${CHAT}" --data-urlencode "text=${msg}" -o /dev/null && echo "$now" > "$STATE"
echo "ALERT sent: origin $age мин"
