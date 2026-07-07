#!/usr/bin/env bash
# tavily.sh — веб-поиск через Tavily API (для агентов без серверного WebSearch:
# DeepSeek, MiMo). Возвращает чистый список результатов: TITLE / URL / snippet.
#
# Ключ берётся из $TAVILY_API_KEY или из ~/.tavily/api_key (формат tvly-...).
#
# Использование:
#   bash tavily.sh "<query>"                 # обычный поиск, 6 результатов
#   bash tavily.sh "<query>" 8               # 8 результатов
#   bash tavily.sh "<query>" 8 3             # topic=news за последние 3 дня (свежесть)
#   bash tavily.sh --json "<query>" ...       # сырой JSON Tavily (для парсинга)
set -uo pipefail

RAW=0
if [ "${1:-}" = "--json" ]; then RAW=1; shift; fi
Q="${1:?usage: tavily.sh [--json] \"<query>\" [max_results] [days]}"
N="${2:-6}"
DAYS="${3:-}"

KEY="${TAVILY_API_KEY:-}"
[ -z "$KEY" ] && [ -s "$HOME/.tavily/api_key" ] && KEY="$(tr -d ' \t\r\n' < "$HOME/.tavily/api_key")"
[ -z "$KEY" ] && { echo "tavily: НЕТ ключа — задай \$TAVILY_API_KEY или положи в ~/.tavily/api_key" >&2; exit 1; }

# тело запроса; если задан DAYS — это новостной свежий поиск
if [ -n "$DAYS" ]; then
  BODY="$(printf '{"query":%s,"max_results":%s,"search_depth":"advanced","topic":"news","days":%s}' \
          "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$Q")" "$N" "$DAYS")"
else
  BODY="$(printf '{"query":%s,"max_results":%s,"search_depth":"advanced"}' \
          "$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$Q")" "$N")"
fi

RESP="$(curl -sS --max-time 40 -X POST "https://api.tavily.com/search" \
  -H "Authorization: Bearer ${KEY}" \
  -H "Content-Type: application/json" \
  -d "$BODY")" || { echo "tavily: curl failed" >&2; exit 2; }

if [ "$RAW" = 1 ]; then echo "$RESP"; exit 0; fi

TAVILY_RESP="$RESP" python3 - <<'PY'
import json,os,sys
try: d=json.loads(os.environ["TAVILY_RESP"])
except Exception as e: print("tavily: bad JSON response:", e); sys.exit(0)
if isinstance(d,dict) and d.get("error"):
    print("tavily error:", d["error"]); sys.exit(0)
res=d.get("results",[]) if isinstance(d,dict) else []
if not res: print("tavily: 0 результатов"); sys.exit(0)
if d.get("answer"): print("ОТВЕТ:", d["answer"], "\n")
for i,r in enumerate(res,1):
    print(f"{i}. {r.get('title','')}")
    print(f"   URL: {r.get('url','')}")
    c=(r.get('content') or '').strip().replace('\n',' ')
    if r.get('published_date'): print(f"   дата: {r['published_date']}")
    print(f"   {c[:300]}")
    print()
PY
