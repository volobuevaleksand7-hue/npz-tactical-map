#!/usr/bin/env bash
# Пересборка слоя складов маркетплейсов + догон счётчика на страницах кластера.
#
# 🔴 Зачем отдельный крон: fetch-warehouses.py не был подключён НИ К ОДНОМУ планировщику —
# ни к системному crontab, ни к крону Гермеса. Он запускался, только когда про него
# вспоминал человек или агент. Итог рецидивный: 04.08 счётчик врал 4 дня («13 складов»),
# 18.08 обнаружено отставание на 11 дней (25 вместо 28) — и всё это на странице-чемпионе,
# топ-1 источнике трафика сайта.
#
# Сеть дёргается только для НОВЫХ адресов (geocache в agents/.geocache-warehouses.json),
# поэтому прогон дешёвый и его не жалко гонять несколько раз в сутки.
#
# ponytail: обёртка, а не строка в crontab — в crontab уже резал команды неэкранированный %.
set -uo pipefail

REPO="${NPZ_REPO:-/root/npz-tactical-map}"
cd "$REPO" || exit 1

python3 agents/fetch-warehouses.py   || { echo "refresh-warehouses: fetch упал" >&2; exit 1; }
python3 agents/gen-warehouses-page.py || { echo "refresh-warehouses: gen упал" >&2; exit 1; }
python3 agents/sync-warehouse-counts.py || { echo "refresh-warehouses: sync упал" >&2; exit 1; }

# Коммитим ТОЛЬКО свои файлы поимённо: `git add data/` соседа уже дважды уносил чужую работу.
FILES="data/warehouses.json skolko-skladov-wildberries-ozon.html udar-po-skladu-ozon.html ceny-marketpleysy-posle-udarov.html"
CHANGED=""
for f in $FILES; do
  [ -f "$f" ] && ! git diff --quiet -- "$f" && CHANGED="$CHANGED $f"
done
if [ -z "$CHANGED" ]; then
  echo "refresh-warehouses: изменений нет"
  exit 0
fi

# Страницы кластера — фронтенд, поэтому коммит под релизным гейтом.
git add $CHANGED || exit 1
ALLOW_FRONTEND_RELEASE=1 git commit -q -m "data(warehouses): плановая пересборка слоя складов" || exit 0
echo "refresh-warehouses: закоммичено:$CHANGED (git-sync запушит)"
