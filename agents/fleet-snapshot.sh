#!/usr/bin/env bash
# NPZ TACTICAL MAP — снимок ВСЕХ планировщиков флота в docs/agents/FLEET-SNAPSHOT.md
#
# Зачем: расписание флота живёт в трёх местах, которые друг о друге не знают
# (crontab, ~/.hermes/cron/jobs.json, systemd timers). Любая рукописная копия
# этого списка протухает — `agents/crontab.txt` протух дважды и оба раза врал
# читателю (аудит 2026-07-07 и разбор 2026-08-26). Поэтому список не пишут
# руками, а снимают.
#
# Запуск (на hermes-vps):  bash agents/fleet-snapshot.sh
#          проверка:       bash agents/fleet-snapshot.sh --check   # RC=1 если снимок разошёлся
#
# ponytail: снимок в markdown, без БД и без парсинга cron — глазами читают чаще, чем машиной.
set -uo pipefail

REPO="${NPZ_REPO:-/root/npz-tactical-map}"
OUT="$REPO/docs/agents/FLEET-SNAPSHOT.md"
JOBS="${HERMES_JOBS:-/root/.hermes/cron/jobs.json}"

render() {
  echo "# Снимок планировщиков флота НПЗ"
  echo
  echo "> Снят автоматически: \`agents/fleet-snapshot.sh\`. **Руками не править** —"
  echo "> правки затрёт следующий прогон. Источник правды — сами планировщики."
  echo ">"
  echo "> Снято: $(date -u +%Y-%m-%dT%H:%MZ) на \`$(hostname)\`"
  echo

  echo "## 1. crontab"
  echo
  if crontab -l >/dev/null 2>&1; then
    echo '```cron'
    crontab -l 2>/dev/null | grep -vE '^\s*(#|$)'
    echo '```'
  else
    echo "_crontab недоступен на этой машине._"
  fi
  echo

  echo "## 2. hermes cron (\`$JOBS\`)"
  echo
  echo "🔴 Эти задания НЕ видны ни в \`crontab -l\`, ни в syslog, ни в \`cron.log\`."
  echo
  if [ -r "$JOBS" ]; then
    python3 - "$JOBS" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
j = d if isinstance(d, list) else d.get('jobs', [])
on = [x for x in j if x.get('enabled')]
off = [x for x in j if not x.get('enabled')]
print(f"Живых: **{len(on)}** из {len(j)}.\n")
print("| вкл | расписание | имя | тип | модель | последний прогон |")
print("|---|---|---|---|---|---|")
for x in sorted(j, key=lambda x: (not x.get('enabled'), x.get('name') or '')):
    kind = 'script' if x.get('script') else ('no-agent' if x.get('no_agent') else 'llm')
    print("| %s | `%s` | %s | %s | %s | %s %s |" % (
        '✅' if x.get('enabled') else '—',
        ((x.get('schedule') or {}).get('expr') or '?'),
        (x.get('name') or '?').replace('|', '\\|'),
        kind,
        x.get('model') or '—',
        (x.get('last_run_at') or '—')[:16],
        x.get('last_status') or '',
    ))
print(f"\n_Спящих (пауза/выключены): {len(off)} — держат промпты, работы не делают._")
PY
  else
    echo "_\`$JOBS\` недоступен на этой машине._"
  fi
  echo

  echo "## 3. systemd timers (не-ОС)"
  echo
  if command -v systemctl >/dev/null 2>&1; then
    echo '```'
    systemctl list-timers --all --no-pager 2>/dev/null \
      | grep -vE 'apt-daily|dpkg-db-backup|logrotate|motd-news|systemd-tmpfiles|e2scrub|fstrim|snapd|^NEXT|^$|timers listed' \
      || echo '(нет)'
    echo '```'
  else
    echo "_systemctl недоступен на этой машине._"
  fi
}

if [ "${1:-}" = "--check" ]; then
  tmp=$(mktemp)
  render > "$tmp"
  # generated_at меняется каждый прогон — из сравнения исключаем
  if diff -q <(grep -v '^> Снято:' "$tmp") <(grep -v '^> Снято:' "$OUT" 2>/dev/null) >/dev/null 2>&1; then
    echo "fleet-snapshot: снимок актуален"
    rm -f "$tmp"; exit 0
  fi
  echo "fleet-snapshot: РАСХОЖДЕНИЕ — расписание изменилось с последнего снимка" >&2
  diff <(grep -v '^> Снято:' "$OUT" 2>/dev/null) <(grep -v '^> Снято:' "$tmp") | head -40 >&2
  rm -f "$tmp"; exit 1
fi

mkdir -p "$(dirname "$OUT")"
render > "$OUT"
echo "fleet-snapshot: записан $OUT"
