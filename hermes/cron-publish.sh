#!/usr/bin/env bash
# cron-publish.sh — Hermes cron wrapper for publish-vps.sh
# Запускается после каждой волны сбора данных (утро/день/вечер).
# no_agent=True: stdout → доставка в Telegram.
set -uo pipefail
REPO="/root/npz-tactical-map"
cd "$REPO" || { echo "ERR: нет $REPO"; exit 1; }

output=$(bash hermes/publish-vps.sh 2>&1)
rc=$?

# Парсим результат
news_ok=$(echo "$output" | grep -c "news обновлён")
news_skip=$(echo "$output" | grep -c "news без изменений")
tg_ok=$(echo "$output" | grep -c "отправлено [1-9]")
tg_skip=$(echo "$output" | grep -c "нет нового\|0 активных\|бот не настроен")
errors=$(echo "$output" | grep -ci "⚠\|error\|fail\|не прошёл")

today=$(date -u +%d.%m.%Y)
hour=$(date -u +%H:%M)

if [ $rc -ne 0 ] || [ "$errors" -gt 0 ]; then
  echo "❌ PUBLISH $today $hour UTC — ошибки"
  echo "$output" | grep -i "⚠\|error\|fail\|не прошёл"
else
  parts=""
  [ "$news_ok" -gt 0 ] && parts="✅ /news обновлён"
  [ "$news_skip" -gt 0 ] && parts="⬜ /news без изменений"
  [ "$tg_ok" -gt 0 ] && parts="$parts · ✅ Telegram отправлен"
  [ "$tg_skip" -gt 0 ] && parts="$parts · ⬜ Telegram: нет нового"
  echo "📡 PUBLISH $today $hour UTC"
  echo "${parts:-✅ pipeline ok}"
fi
