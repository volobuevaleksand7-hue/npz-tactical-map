#!/usr/bin/env bash
# Пауза LLM-агентов на время выкатки, которая переписывает data/*.json целиком.
#
# Зачем: 29.07.2026 релиз v1.22.0 переписал data/fuel-availability.json целиком
# (+2625 строк) за 20 минут до ротационного прохода агента, который пишет тот же
# файл каждые 4 часа. На hermes встал rebase, git-sync увидел конфликт-маркеры и
# (правильно) отказался пушить — публикация замерла на 13 часов.
#
# Как: НЕ трогаем crontab (закомментированную строку легко забыть вернуть — это
# freeze навсегда). Берём тот же /var/lock/npz-agent.lock, на котором агенты уже
# сериализуются в run-agent.sh: агент, не дождавшийся лока, пишет SKIP и выходит
# с 0 — cron остаётся тихим, слот просто пропускается.
#
# Пауза ВСЕГДА конечная: держать лок бесконечно — та же авария, что чинили.
# Отпускается по таймеру или сразу при смерти процесса (flock снимается с fd).
#
#   ssh hermes-vps 'bash /root/npz-tactical-map/agents/deploy-hold.sh 10' &
#   HOLD=$!   # ...выкатка...
#   kill $HOLD              # снять паузу досрочно
#
# ponytail: переиспользуем существующий лок, свой механизм паузы не заводим.
set -uo pipefail

LOCK_DEFAULT=/var/lock/npz-agent.lock
# Переопределяется ТОЛЬКО для тестов: боевой лок занят агентами почти постоянно,
# на нём поведение не проверить. --selfcheck всё равно сверяет DEFAULT с run-agent.sh,
# так что расхождение путей поймается даже при переопределении.
LOCK="${NPZ_AGENT_LOCK:-$LOCK_DEFAULT}"
RUNNER="$(dirname "$0")/run-agent.sh"

if [ "${1:-}" = "--selfcheck" ]; then
  # Единственное, что тут может тихо сломаться, — расхождение пути лока с
  # run-agent.sh: скрипт будет «держать паузу», которую никто не соблюдает.
  if [ ! -f "$RUNNER" ]; then
    echo "SELFCHECK: run-agent.sh не найден рядом ($RUNNER)" >&2; exit 1
  fi
  if ! grep -q "$LOCK_DEFAULT" "$RUNNER"; then
    echo "SELFCHECK FAIL: run-agent.sh не берёт $LOCK_DEFAULT — пауза будет фиктивной" >&2; exit 1
  fi
  for bad in "" 0 31 abc -5; do
    if MIN="$bad" bash "$0" "$bad" --dry-run 2>/dev/null; then
      echo "SELFCHECK FAIL: принят недопустимый аргумент '$bad'" >&2; exit 1
    fi
  done
  echo "SELFCHECK OK: лок $LOCK_DEFAULT совпадает с run-agent.sh, аргументы валидируются"
  exit 0
fi

MIN="${1:-}"
case "$MIN" in
  ''|*[!0-9]*) echo "usage: deploy-hold.sh <минут 1..30> | --selfcheck" >&2; exit 2 ;;
esac
[ "$MIN" -ge 1 ] && [ "$MIN" -le 30 ] || { echo "deploy-hold: минуты вне 1..30 (получено '$MIN')" >&2; exit 2; }
[ "${2:-}" = "--dry-run" ] && { echo "deploy-hold: аргумент принят ($MIN мин)"; exit 0; }

exec 9>"$LOCK" || { echo "deploy-hold: не открыть $LOCK" >&2; exit 1; }

# Ждём не дольше, чем живёт один прогон агента (NPZ_AGENT_TIMEOUT=1800): если за
# это время лок не освободился, значит агент завис — пауза не нужна, нужен разбор.
if ! flock -w "${HOLD_WAIT:-1800}" 9; then
  echo "deploy-hold: лок занят дольше ${HOLD_WAIT:-1800}с — агент завис, выкатку не начинай" >&2
  exit 1
fi

echo "deploy-hold: агенты на паузе, $MIN мин (до $(date -u -d "+$MIN minutes" +%H:%MZ 2>/dev/null || echo '?')); Ctrl-C или kill снимает сразу"

# 🔴 `9<&-` обязателен: без него дочерний sleep НАСЛЕДУЕТ fd 9 и продолжает держать
# lock после смерти родителя — kill «снимал» паузу только на словах (поймано тестом).
# Плюс trap, чтобы по TERM/INT не осталось висящего sleep.
trap 'kill "${SLEEP_PID:-0}" 2>/dev/null; echo "deploy-hold: пауза снята досрочно"; exit 0' INT TERM
sleep $((MIN * 60)) 9<&- &
SLEEP_PID=$!
wait "$SLEEP_PID" 2>/dev/null
echo "deploy-hold: пауза снята по таймеру"
