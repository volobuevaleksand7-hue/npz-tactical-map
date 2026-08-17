#!/usr/bin/env bash
# Selfcheck для отката массового выкашивания архива санитайзером
# (блок "neutral-OSINT guard" в .githooks/pre-commit). Без сети и VPS.
#
# Сценарий 14.08.2026: коллектор оставил в дереве strikes.json, где у записей нет
# confidence. Санитайзер честно признал их браком и удалил ВСЕ 402 — архив уехал в
# прод пустым под сообщением соседней рутины. Стражи усыхания сравнивают индекс с
# HEAD ДО санитайзера и брак не видели.
#
# Требуемый исход: архив в дереве И в индексе остался прежним, коммит не заблокирован.
#
# Снипет вырезается из живого .githooks/pre-commit теми же маркерами, что и в
# test-narrow-rollback.sh — тест не может разойтись с тем, что реально едет.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
HOOK="$REPO_ROOT/.githooks/pre-commit"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
git init -q
git config user.email test@test.local
git config user.name test

mkdir -p agents data
cp "$SCRIPT_DIR/sanitize-strikes.py" "$SCRIPT_DIR/neutrality.py" agents/

# 25 валидных записей (>20 — порог стража) в HEAD.
python3 - <<'PY'
import json
recs = [{"date": "2026-08-%02d" % (d + 1), "city": "Рязань", "region": "Рязанская область",
         "target": "НПЗ", "confidence": "confirmed", "lat": 54.6, "lon": 39.7}
        for d in range(25)]
json.dump({"strikes": recs}, open("data/strikes.json", "w", encoding="utf-8"), ensure_ascii=False)
PY
git add agents data
git commit -qm base

# Коллектор сломал файл: у всех записей пропал confidence → санитайзер сочтёт браком все.
python3 - <<'PY'
import json
d = json.load(open("data/strikes.json", encoding="utf-8"))
for r in d["strikes"]:
    r.pop("confidence", None)
json.dump(d, open("data/strikes.json", "w", encoding="utf-8"), ensure_ascii=False)
PY
git add data/strikes.json

SNIPPET="$(sed -n '/^_arch_count() {/,/^fi$/p' "$HOOK")"
[ -n "$SNIPPET" ] || { echo "FAIL: не нашёл блок санитайзера в $HOOK"; exit 1; }

staged="data/strikes.json"
export staged
OUT="$(bash -c "$SNIPPET" 2>&1)" || { echo "FAIL: блок упал (коммит бы заблокировался)"; exit 1; }

ok=1
n_tree="$(python3 -c 'import json;print(len(json.load(open("data/strikes.json"))["strikes"]))')"
n_idx="$(git show :data/strikes.json | python3 -c 'import json,sys;print(len(json.load(sys.stdin)["strikes"]))')"
[ "$n_tree" = "25" ] || { echo "FAIL: в дереве $n_tree записей, ждали 25"; ok=0; }
[ "$n_idx" = "25" ] || { echo "FAIL: в индексе $n_idx записей, ждали 25"; ok=0; }
echo "$OUT" | grep -q "ОТКАЧЕНО" || { echo "FAIL: нет громкого сообщения об откате"; echo "$OUT"; ok=0; }

# Обратная сторона: одиночный брак санитайзер обязан вычищать как раньше.
git checkout -q HEAD -- data/strikes.json     # вернуть здоровый архив (25 валидных)
python3 - <<'PY'
import json
d = json.load(open("data/strikes.json", encoding="utf-8"))
d["strikes"].append({"date": "2026-08-26", "city": "X", "target": "Слава Україні",
                     "confidence": "reported", "lat": 50.0, "lon": 36.0})
json.dump(d, open("data/strikes.json", "w", encoding="utf-8"), ensure_ascii=False)
PY
git add data/strikes.json
OUT2="$(bash -c "$SNIPPET" 2>&1)" || { echo "FAIL: блок упал на одиночном браке"; exit 1; }
n_idx2="$(git show :data/strikes.json | python3 -c 'import json,sys;print(len(json.load(sys.stdin)["strikes"]))')"
[ "$n_idx2" = "25" ] || { echo "FAIL: одиночный брак не вычищен (в индексе $n_idx2, ждали 25)"; ok=0; }
echo "$OUT2" | grep -q "ОТКАЧЕНО" && { echo "FAIL: откат сработал на штатной чистке одной записи"; ok=0; }

[ "$ok" = "1" ] && echo "test-sanitize-rollback: OK" || exit 1
