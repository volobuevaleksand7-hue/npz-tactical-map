#!/usr/bin/env bash
# Поиск для не-Claude движков (MiMo/OpenRouter): у них нет WebSearch-инструмента.
# 1) Tavily (ключ из env-файла в рантайме, в промпт агента не попадает);
# 2) если Tavily недоступен (лимит плана = HTTP 432, нет ключа, сеть) — бесплатный фолбэк:
#    Google News RSS (без ключа), результат в том же формате results[].title/url/content.
#    Добавлено 14.10.2026: лимит Tavily исчерпан, разведчик world-events оставался без поиска.
set -uo pipefail
[ -f /root/.npz-agent.env ] && . /root/.npz-agent.env
q="${1:?query required}"
if [ -n "${TAVILY_API_KEY:-}" ]; then
  if out=$(curl -sS --fail-with-body --max-time 25 https://api.tavily.com/search \
      -H 'Content-Type: application/json' \
      -d "$(python3 -c 'import json,sys;print(json.dumps({"api_key":sys.argv[1],"query":sys.argv[2],"max_results":8}))' "$TAVILY_API_KEY" "$q")" 2>/dev/null); then
    printf '%s\n' "$out"; exit 0
  fi
fi
python3 - "$q" <<'PY'
import sys, json, urllib.request, urllib.parse, xml.etree.ElementTree as ET, re, html
q = sys.argv[1]
url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:3d", "hl": "en-US", "gl": "US", "ceid": "US:en"})
try:
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read()
    res = []
    for it in ET.fromstring(raw).iter("item"):
        desc = re.sub(r"<[^>]+>", " ", html.unescape(it.findtext("description") or ""))
        src = it.findtext("source") or ""
        res.append({"title": it.findtext("title") or "", "url": it.findtext("link") or "",
                    "content": (src + " | " + it.findtext("pubDate", "") + " | " + " ".join(desc.split()))[:400]})
        if len(res) >= 8:
            break
    print(json.dumps({"engine": "google-news-rss", "results": res}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": f"search failed: {e}"})); sys.exit(1)
PY
