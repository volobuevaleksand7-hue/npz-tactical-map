#!/usr/bin/env bash
# cron-briefing.sh — Hermes cron wrapper for Telegram briefing cards.
# usage: bash cron-briefing.sh morning|evening
# Целевое расписание (редполитика v2, 2026-07-07): morning = 05:00 UTC (08:00 МСК),
# evening = 17:00 UTC (20:00 МСК). См. docs/agents/jobs-migration-2026-07-07.md.
# no_agent=True: stdout → доставка в Telegram.
set -uo pipefail
MODE="${1:-morning}"
REPO="/root/npz-tactical-map"
cd "$REPO" || { echo "ERR: нет $REPO"; exit 1; }

[ -f /root/.npz-agent.env ] && . /root/.npz-agent.env

output=$(NPZ_REPO="$REPO" NPZ_BOT_DIR="$HOME/.npz-bot" \
  python3 hermes/bot/broadcast.py --briefing "$MODE" 2>&1)
rc=$?

today=$(date -u +%d.%m.%Y)
hour=$(date -u +%H:%M)
label=$( [ "$MODE" = "morning" ] && echo "🌅 Утренняя" || echo "🌆 Вечерняя" )

if [ $rc -ne 0 ]; then
  echo "❌ $label сводка $today $hour UTC — ошибка"
  echo "$output" | tail -3
else
  echo "$label сводка $today $hour UTC — ✅ отправлена"
fi
