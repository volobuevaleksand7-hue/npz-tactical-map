#!/usr/bin/env bash
# Lightweight script-only radar alert runner. Safe for OS cron or Hermes native cron.
set -uo pipefail

[ -f /root/.npz-agent.env ] && . /root/.npz-agent.env
[ -f "$HOME/.npz-agent.env" ] && . "$HOME/.npz-agent.env"

REPO="${NPZ_REPO:-/root/npz-tactical-map}"
BOT_DIR="${NPZ_BOT_DIR:-$HOME/.npz-bot}"
BOT="$REPO/hermes/bot"

cd "$REPO" || exit 2

if [ -f "$BOT_DIR/token" ] && [ -f "$BOT/radar_alerts.py" ]; then
  NPZ_REPO="$REPO" NPZ_BOT_DIR="$BOT_DIR" python3 "$BOT/radar_alerts.py" --send
else
  echo "radar-alerts: бот не настроен ($BOT_DIR/token нет)"
fi
