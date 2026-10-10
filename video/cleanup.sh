#!/usr/bin/env bash
# Хранение роликов: залитый ролик удаляется; хранится только то, что ещё не
# загружено, но не больше KEEP (по умолчанию 7) последних.
#  1) out/npz-<дата>.mp4 + маркер out/npz-<дата>.uploaded (его пишет загрузчик после
#     успешной загрузки) -> mp4 удаляем, маркер ОСТАВЛЯЕМ (по нему загрузчик видит,
#     что дата уже залита, и не зальёт повторно), факт пишем в out/uploaded.log.
#  2) страховка, пока загрузчика нет: из оставшихся mp4 держим KEEP самых свежих по дате.
set -euo pipefail
OUT="$(cd "$(dirname "$0")" && pwd)/out"
KEEP="${KEEP:-7}"
[ -d "$OUT" ] || exit 0
cd "$OUT"
shopt -s nullglob

for marker in npz-*.uploaded reel-*.uploaded urgent-*.uploaded en-reel-*.uploaded en-urgent-*.uploaded weekly-*.uploaded en-weekly-*.uploaded; do
  [ -e "$marker" ] || continue
  mp4="${marker%.uploaded}.mp4"
  [ -f "$mp4" ] || continue
  rm -f -- "$mp4" "${mp4%.mp4}.jpg"
  printf '%s\tdeleted %s\t%s\n' "$(date -u +%FT%TZ)" "$mp4" "$(head -c 300 "$marker" | tr '\n\t' '  ')" >> uploaded.log
  echo "cleanup: $mp4 залит — удалён"
done

# имена npz-YYYY-MM-DD.mp4 сортируются как даты; tmp-файлы недорендера не трогаем
# (без mapfile — на Маке системный bash 3.2)
n=0
# Без ls: при nullglob пустой глоб давал голый `ls -1` = ВСЕ файлы out/, и «храним 7» сносил
# reel-shown.json и маркеры .uploaded -> повторы сюжетов и повторные заливки (07.10).
for v in $(printf '%s\n' npz-????-??-??.mp4 | sort -r); do
  n=$((n + 1))
  [ "$n" -le "$KEEP" ] && continue
  rm -f -- "$v" "${v%.mp4}.jpg"
  echo "cleanup: $v удалён (храним $KEEP последних)"
done
