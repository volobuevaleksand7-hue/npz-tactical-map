#!/usr/bin/env bash
# cron-briefing-evening.sh — evening briefing wrapper
set -uo pipefail
MODE="evening"
REPO="/root/npz-tactical-map"
cd "$REPO" || { echo "ERR: нет $REPO"; exit 1; }

[ -f /root/.npz-agent.env ] && . /root/.npz-agent.env

output=$(NPZ_REPO="$REPO" NPZ_BOT_DIR="$HOME/.npz-bot" \
  python3 hermes/bot/broadcast_both.py "$MODE" 2>&1)
rc=$?

today=$(date -u +%d.%m.%Y)
hour=$(date -u +%H:%M)

if [ $rc -ne 0 ]; then
  echo "❌ Вечерняя сводка $today $hour UTC — ошибка"
  echo "$output" | tail -3
else
  echo "🌆 Вечерняя сводка $today $hour UTC — ✅ отправлена"
fi
