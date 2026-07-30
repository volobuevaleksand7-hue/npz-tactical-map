#!/usr/bin/env bash
# deadman-base.sh — РЕЗЕРВНЫЙ (второй эшелон) сторож публикации НПЗ-карты на base-vps.
# Дубль hermes-сторожа: если hermes ПОЛНОСТЬЮ упал, тамошний deadman мёртв — этот ловит
# тишину origin ИЗВНЕ, через GitHub API (локальный репо не нужен). Порог 60 мин (>45 у
# hermes), чтобы не дублировать алерты на транзиентах. Инцидент 30.07: паблиш встал 13ч,
# health.json=healthy. См. память npz-orphaned-stashes-publish-freeze.
set -uo pipefail
TOKEN="$(cat /root/.npz-bot/token 2>/dev/null)"
CHAT="$(cat /root/.npz-bot/chat_id 2>/dev/null)"
THRESH_MIN=60
COOLDOWN=3600
STATE=/root/.npz-bot/deadman-base-last
API="https://api.github.com/repos/volobuevaleksand7-hue/npz-tactical-map/commits/main"
[ -n "$TOKEN" ] && [ -n "$CHAT" ] || exit 0
last_iso="$(curl -s --max-time 25 "$API" | python3 -c "import sys,json;print(json.load(sys.stdin)['commit']['committer']['date'])" 2>/dev/null)"
[ -n "$last_iso" ] || { echo "API недоступна — пропуск (не паникуем)"; exit 0; }
last="$(date -d "$last_iso" +%s 2>/dev/null)"; now="$(date +%s)"; age=$(( (now-last)/60 ))
(( age > THRESH_MIN )) || { echo "ok: origin $age мин назад"; exit 0; }
la="$(cat "$STATE" 2>/dev/null||echo 0)"; (( now-la > COOLDOWN )) || { echo "stale $age мин, cooldown"; exit 0; }
if timeout 6 bash -c "cat < /dev/null > /dev/tcp/104.252.77.253/22" 2>/dev/null; then
  hz="hermes ЖИВ (порт 22 открыт) → публикация встала: проверь git stash list / cron.log на hermes"
else
  hz="hermes НЕДОСТУПЕН (порт 22 закрыт) → возможно VPS упал"
fi
msg="🔴 [резерв base-vps] НПЗ-карта: origin молчит ${age} мин (порог ${THRESH_MIN}). ${hz}"
curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" --data-urlencode "chat_id=${CHAT}" --data-urlencode "text=${msg}" -o /dev/null && echo "$now">"$STATE"
echo "ALERT sent: origin $age мин | $hz"
