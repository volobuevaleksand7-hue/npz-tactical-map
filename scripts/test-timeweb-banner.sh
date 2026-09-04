#!/usr/bin/env bash
# Партнёрский баннер Timeweb живёт в vpn-nudge.js (его build-nav.py инжектит на все
# статические страницы). Класс багов, который ловим: регенератор выкинул <script>,
# либо имя цели разошлось с целью, заведённой в Метрике (id 608839463/608839465) —
# тогда клики считаются в никуда и это видно только через неделю пустого отчёта.
set -euo pipefail
root_dir=$(cd "$(dirname "$0")/.." && pwd)
js="$root_dir/vpn-nudge.js"

node --check "$js"
grep -q "timeweb.com/ru/?i=146483&a=413" "$js"
grep -q "'timeweb_click'" "$js"
grep -q "'timeweb_view'" "$js"
grep -q "getElementById('map')" "$js"   # на картах баннера быть не должно

pages=$(grep -rl 'vpn-nudge\.js' --include='*.html' "$root_dir" | wc -l | tr -d ' ')
if [ "$pages" -lt 200 ]; then
  echo "vpn-nudge.js (носитель баннера) остался лишь на $pages страницах — регенератор его выкинул" >&2
  exit 1
fi
echo "ok: баннер Timeweb на месте, целей 2, страниц-носителей $pages"
