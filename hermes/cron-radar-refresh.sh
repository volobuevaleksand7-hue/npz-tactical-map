#!/usr/bin/env bash
# Script-only public radar snapshot refresh. Safe for OS cron or Hermes native cron.
set -euo pipefail

[ -f /root/.npz-agent.env ] && . /root/.npz-agent.env
[ -f "$HOME/.npz-agent.env" ] && . "$HOME/.npz-agent.env"

REPO="${NPZ_REPO:-/root/npz-tactical-map}"
cd "$REPO"

python3 agents/update-radar-state.py
python3 agents/wave-detect.py
python3 agents/healthcheck.py
bash agents/git-sync.sh "data(radar): refresh public radar state $(date -u +%Y-%m-%dT%H:%MZ)" "radar-state"
