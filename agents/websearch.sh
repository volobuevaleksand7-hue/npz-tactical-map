#!/usr/bin/env bash
# Tavily-поиск для не-Claude движков (MiMo/OpenRouter): у них нет WebSearch-инструмента.
# Ключ берётся из env-файла в рантайме — в промпт агента он не попадает.
set -euo pipefail
[ -f /root/.npz-agent.env ] && . /root/.npz-agent.env
[ -n "${TAVILY_API_KEY:-}" ] || { echo '{"error":"no TAVILY_API_KEY"}'; exit 1; }
q="${1:?query required}"
curl -sS --fail-with-body --max-time 25 https://api.tavily.com/search \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"api_key":sys.argv[1],"query":sys.argv[2],"max_results":8}))' "$TAVILY_API_KEY" "$q")"
