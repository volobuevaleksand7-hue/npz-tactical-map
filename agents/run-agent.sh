#!/usr/bin/env bash
# NPZ TACTICAL MAP — data collector runner (VPS cron)
# Usage: ./run-agent.sh <prompt-file> <label>
# Runs Claude Code headless to refresh data/*.json, validates ALL json,
# then commits & pushes. Сайт читает data/*.json напрямую из GitHub raw —
# обновление видно БЕЗ редеплоя Vercel (на след. 5-мин опросе).
set -uo pipefail

# load local secrets (ANTHROPIC_API_KEY и пр.) — файл ВНЕ репозитория
[ -f /root/.npz-agent.env ] && . /root/.npz-agent.env
[ -f "$HOME/.npz-agent.env" ] && . "$HOME/.npz-agent.env"

REPO="${NPZ_REPO:-/root/npz-tactical-map}"
MODEL="${NPZ_MODEL:-claude-haiku-4-5-20251001}"
PROMPT_FILE="${1:?prompt file required}"
LABEL="${2:?label required}"

cd "$REPO" || { echo "repo not found: $REPO"; exit 1; }
mkdir -p agents/logs

# --- Serialize all LLM agent runs onto the single vCPU (sequential, no overlap).
# flock waits up to NPZ_LOCK_WAIT sec for the previous agent to finish; on timeout
# it logs a labelled SKIP and exits 0 so cron stays quiet. Per-label logs + this
# SKIP line show exactly which agent stalled. Non-LLM crons do not use this script.
# ponytail: one global lock; fine while everything shares a single vCPU.
exec 9>/var/lock/npz-agent.lock
if ! flock -w "${NPZ_LOCK_WAIT:-1900}" 9; then
  echo "=== [$LABEL] SKIP: another agent held the lock >${NPZ_LOCK_WAIT:-1900}s $(date -u +%FT%TZ) ==="
  exit 0
fi

echo "=== [$LABEL] model=$MODEL $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
git pull --rebase --quiet 2>/dev/null || git pull --quiet 2>/dev/null || true

PROMPT="$(cat "$PROMPT_FILE")"

# Снимок data/ ДО прогона. Сравнение до/после отличает «агент поработал» от
# «агент вышел с RC=0, не сделав ничего». Чужие правки, лежавшие тут заранее,
# в дельту не попадут.
# ponytail: снимок до/после, а не маппинг label→файл; чужой коммит ВО ВРЕМЯ прогона
# всё ещё может замаскировать пустой прогон — тогда нужен per-label целевой файл.
DATA_BEFORE="$(git status --porcelain data/ 2>/dev/null)"

# Hard cap the agent run so a hung CLI can't block the cron slot forever.
# `timeout` exits 124 on timeout (treated as failure below). Skip the wrapper
# if `timeout` is unavailable (e.g. stock macOS without coreutils).
TIMEOUT_WRAP="timeout ${NPZ_AGENT_TIMEOUT:-1800}"
command -v timeout >/dev/null 2>&1 || TIMEOUT_WRAP=""
$TIMEOUT_WRAP claude -p "$PROMPT" \
  --model "$MODEL" \
  --allowedTools "Read,Write,WebSearch,WebFetch" \
  --permission-mode acceptEdits \
  > "agents/logs/${LABEL}.log" 2>&1
RC=$?
echo "agent exit: $RC"

# A failed agent (incl. timeout=124) may have left half-written data. Revert any
# partial changes and DO NOT commit — better no update than a corrupt/partial one.
# The skipped heartbeat is the watchdog's signal that this run failed.
if [ "$RC" != "0" ]; then
  echo "!! agent failed (RC=$RC) — reverting data/, no commit"
  git checkout -- data/ 2>/dev/null || true
  exit "$RC"
fi

# Validate ALL data json — revert everything on any corruption.
# Runs BEFORE the heartbeat write so a corrupt run does not get its heartbeat
# reverted along with the bad data (the heartbeat must survive to prove liveness).
BAD=0
for f in data/*.json; do
  python3 -c "import json, sys; json.load(open(sys.argv[1]))" "$f" 2>/dev/null || { echo "!! INVALID: $f"; BAD=1; }
done
if [ "$BAD" = "1" ]; then
  echo "reverting data/ due to invalid JSON"
  git checkout -- data/
  exit 1
fi

# We only reach here on a successful, JSON-valid run (RC=0 — failures exited above).
# Stamp this label's heartbeat so the watchdog can tell "alive, no news"
# (stale_alive) from "dead" (stale_dead). git-sync.sh writes the heartbeat into the
# same commit (and re-applies it if a rebase auto-resolve takes upstream's
# heartbeats.json), so liveness can never be silently dropped.
# Commit/push via the safe helper: atomic data/last-sync.txt stamp, conflict-marker
# guard, clean-tree rebase retry (never --autostash). See agents/git-sync.sh.
# Если git-sync отказал (pre-commit guard забраковал результат — например, агент
# обрезал архив strikes.json), рабочее дерево ОСТАЁТСЯ грязным. Соседняя рутина
# через минуту делает `git add data/` и заметает чужой забракованный файл в свой
# коммит — так 11.07 (172→67) и 12.07 (75→2) архив ударов утёк в прод под чужими
# сообщениями «update AZS statuses» / «health: watchdog», хотя guard честно
# блокировал коммит самого агента. Откатываем: забракованные данные не должны
# пережить свой запуск.
DATA_AFTER="$(git status --porcelain data/ 2>/dev/null)"
if [ "$DATA_BEFORE" = "$DATA_AFTER" ]; then
  echo "!! [$LABEL] ПУСТОЙ ПРОГОН: RC=0, но data/ не тронут — heartbeat НЕ пишем."
  echo "   Ответ агента (для разбора): $(head -c 300 "agents/logs/${LABEL}.log" 2>/dev/null | tr "\n" " ")"
  exit 0
fi

if ! bash agents/git-sync.sh "data(${LABEL}): sync $(date -u +%Y-%m-%dT%H:%MZ)" "$LABEL"; then
  echo "!! git-sync отказал (guard?) — откатываю data/, чтобы сосед не закоммитил чужое"
  # 🔴 ЗДЕСЬ текла дыра усыхания архива. git-sync уже сделал `git add data/`, guard
  # заблокировал commit — файл остался В ИНДЕКСЕ. Прежний `git checkout -- data/`
  # восстанавливал ИЗ ИНДЕКСА, т.е. возвращал забракованный файл обратно в дерево.
  # Дерево оставалось грязным → сосед заметал брак своим `git add data/` под своим
  # сообщением («refresh radar state», «health: watchdog»). Так архив утекал в прод
  # 4 раза, хотя guard честно блокировал коммит самого агента.
  # HEAD чинит и дерево, и индекс. Проверено 15.07: 197→55 от newswatch, откат вернул 197.
  git checkout HEAD -- data/ 2>/dev/null || true
  exit 1
fi
