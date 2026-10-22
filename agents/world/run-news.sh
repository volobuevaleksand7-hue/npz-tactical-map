#!/usr/bin/env bash
# Выпуск «Всемирных новостей» по cron (19.10.2026, по «да» владельца).
# Сначала --dry: если новых одобренных событий нет, страницы НЕ перерисовываются
# (иначе каждый прогон пачкает rss.xml/lastBuildDate и клинит git-sync).
set -u
cd "$(dirname "$0")/../.."
out="$(python3 agents/world/gen-news.py --dry 2>&1)" || { echo "run-news: dry упал: $out"; exit 1; }
echo "$out" | grep -q "^новый выпуск" || { echo "run-news: $(date -u +%FT%TZ) $out"; exit 0; }
python3 agents/world/gen-news.py || { echo "run-news: генерация упала"; git checkout -- world en/world sitemap-world.xml data/world/news-archive.json 2>/dev/null; exit 1; }
git add world/news.html world/news world/rss.xml en/world/news.html en/world/news en/world/rss.xml sitemap-world.xml
bash agents/git-sync.sh "data(world): выпуск «Всемирных новостей» $(date -u +%F)"
