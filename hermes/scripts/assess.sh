#!/usr/bin/env bash
# assess.sh — показать свежесть всех слоёв карты npz-tactical-map относительно сегодня.
# Выводит по каждому файлу generated_at, возраст в днях и пометку STALE (порог из WATCH).
# Использование:  bash assess.sh [REPO_DIR]
set -uo pipefail
REPO="${1:-$HOME/Documents/npz-tactical-map}"
cd "$REPO" || { echo "no repo at $REPO" >&2; exit 2; }

git fetch origin --quiet 2>/dev/null

# --autostash ЗАПРЕЩЁН (см. HERMES.md): он был корнем конфликт-маркеров в data/
# при параллельных рутинах. Вместо него — явная проверка чистоты дерева перед pull.
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  echo "assess.sh: рабочее дерево грязное — pull пропущен, показываю то, что есть локально" >&2
else
  git pull --rebase origin main --quiet 2>/dev/null || git pull --rebase origin master --quiet 2>/dev/null || \
    echo "assess.sh: git pull не удался (нет сети/веток?) — показываю локальные данные" >&2
fi

python3 - "$REPO" <<'PY'
import json, os, sys, datetime
repo = sys.argv[1]
now = datetime.datetime.now(datetime.timezone.utc)
# файл -> (heartbeat-key или "-", порог свежести данных в часах)
WATCH = {
  "strikes.json":           ("strikes",           18),
  "fuel-state.json":        ("npz-status",         24),
  "history-crimea.json":    ("history-crimea",     36),
  "roads.json":             ("roads",              36),
  "grid-state.json":        ("grid-status",        18),
  "fuel-availability.json": ("fuel-availability",  18),
  "fuel-voices.json":       ("fuel-voices",        24),
  "forecast.json":          ("forecast",          200),
  "economy.json":           ("economy",           200),
  "capacity-timeline.json": ("-",                 200),
  "strike-confirm.json":    ("-",                  18),
}
def parse(ts):
    if not ts: return None
    ts = str(ts).replace("Z","").strip()
    for f in ("%Y-%m-%dT%H:%M:%S","%Y-%m-%dT%H:%M","%Y-%m-%d"):
        try: return datetime.datetime.strptime(ts, f).replace(tzinfo=datetime.timezone.utc)
        except Exception: pass
    return None
print(f"# Свежесть слоёв на {now:%Y-%m-%d %H:%MZ}\n")
print(f"{'file':22} {'generated_at':22} {'age':>7}  status")
for fn,(hk,thr) in WATCH.items():
    p = os.path.join(repo,"data",fn)
    try: d = json.load(open(p, encoding="utf-8"))
    except Exception: print(f"{fn:22} {'MISSING/BAD':22}"); continue
    ga = d.get("generated_at") or d.get("meta",{}).get("generated_at")
    dt = parse(ga)
    if dt is None:
        print(f"{fn:22} {str(ga)[:22]:22} {'?':>7}  (no parseable date)"); continue
    age_h = (now-dt).total_seconds()/3600
    mark = "STALE" if age_h > thr else "ok"
    print(f"{fn:22} {str(ga)[:22]:22} {age_h/24:6.1f}d  {mark}  (thr {thr}h, hb={hk})")
PY
