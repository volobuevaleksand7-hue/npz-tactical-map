#!/usr/bin/env bash
# deepseek-web.sh — запустить DeepSeek (через Claude Code harness) с РАСШИРЕННЫМИ
# правами Bash+WebFetch, чтобы он мог реально собирать веб-данные через curl.
#
# ВАЖНО: штатный лаунчер `deepseek` намеренно ограничен Read/Write/Edit/Glob/Grep
# (без bash, без web) — им OSINT-сбор НЕВОЗМОЖЕН. Этот враппер снимает ограничение.
# DeepSeek не имеет серверных веб-тулзов Anthropic, поэтому он ищет через:
#   - Tavily (ОСНОВНОЙ, чистый JSON, без CAPTCHA): bash <SKILL_DIR>/scripts/tavily.sh "<query>" [N] [days]
#     (в задаче агенту явно укажи полный путь — $TAVILY_SCRIPT ниже подставлен как подсказка)
#   - Telegram веб-зеркала (второй канал):  curl -s -A "Mozilla/5.0" https://t.me/s/<channel>
#
# Использование:  bash deepseek-web.sh "<task prompt>" [REPO_DIR]
# Работает в REPO_DIR (cwd). Пишет результат агента в stdout.
set -uo pipefail
TASK="${1:?task prompt required}"
REPO="${2:-$HOME/Documents/npz-tactical-map}"
KEY_FILE="$HOME/.deepseek/api_key"
[[ -s "$KEY_FILE" ]] || { echo "❌ нет ключа DeepSeek ($KEY_FILE)" >&2; exit 1; }
cd "$REPO" || { echo "no repo at $REPO" >&2; exit 2; }
TOKEN="$(tr -d ' \t\r\n' < "$KEY_FILE")"
CFG_DIR="$HOME/.deepseek/claude-cfg"; mkdir -p "$CFG_DIR"
unset ANTHROPIC_API_KEY

TAVILY_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/tavily.sh"
TAVILY_KEY=""
[[ -s "$HOME/.tavily/api_key" ]] && TAVILY_KEY="$(tr -d ' \t\r\n' < "$HOME/.tavily/api_key")"

TASK_FULL="Инструмент веб-поиска: bash ${TAVILY_SCRIPT} \"<query>\" [max_results] [days]  — вызывай его через Bash для поиска (напр. bash ${TAVILY_SCRIPT} \"НПЗ удар июль 2026\" 6 3). Ключ уже прокинут в окружение, ничего настраивать не нужно.

${TASK}"

CLAUDE_CONFIG_DIR="$CFG_DIR" \
ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic" \
ANTHROPIC_AUTH_TOKEN="$TOKEN" \
ANTHROPIC_MODEL="deepseek-v4-pro" \
ANTHROPIC_DEFAULT_OPUS_MODEL="deepseek-v4-pro" \
ANTHROPIC_DEFAULT_SONNET_MODEL="deepseek-v4-pro" \
ANTHROPIC_DEFAULT_HAIKU_MODEL="deepseek-v4-flash" \
ANTHROPIC_SMALL_FAST_MODEL="deepseek-v4-flash" \
TAVILY_API_KEY="$TAVILY_KEY" \
claude -p "$TASK_FULL" --permission-mode acceptEdits \
  --allowedTools "Read,Write,Edit,Glob,Grep,Bash,WebFetch"
