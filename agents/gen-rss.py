#!/usr/bin/env python3
"""
Генератор RSS-фида и Google News sitemap для сводок «Топливный фронт РФ».

Строит из data/news-archive.json:
  • rss.xml           — RSS 2.0, последние RSS_CAP сводок (по одной на день).
  • news-sitemap.xml  — Google News sitemap, только сводки за последние 48ч (может быть пуст).

Запуск: python3 agents/gen-rss.py  (обычно вызывается из agents/gen-news.py последним
шагом, рядом с seo/generate-sitemap.py — так фид освежается на каждом publish-прогоне).
Только stdlib. Заголовки/тексты берутся из gen-news.py (brief_headline/brief_teaser),
чтобы фид и структурированные данные на страницах не расходились.
"""
import json
import importlib.util
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_PATH = ROOT / "data" / "news-archive.json"
RSS_OUT = ROOT / "rss.xml"
NEWS_SITEMAP_OUT = ROOT / "news-sitemap.xml"
SITE = "https://npz-tactical-map.vercel.app"
MSK = timezone(timedelta(hours=3))
RSS_CAP = 50
NEWS_WINDOW_HOURS = 48

# gen-news.py имеет дефис в имени — обычный import не работает, грузим через importlib.
_spec = importlib.util.spec_from_file_location("gen_news", ROOT / "agents" / "gen-news.py")
gen_news = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen_news)


def midnight_msk(date: str) -> datetime:
    return datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=MSK)


def build_rss(archive: dict) -> str:
    briefs = archive.get("briefs", {})
    dates = sorted(briefs.keys(), reverse=True)[:RSS_CAP]
    items = []
    for d in dates:
        b = briefs[d]
        strikes, voices = b.get("strikes", []), b.get("voices", [])
        url = f"{SITE}/news/{d}"
        title = gen_news.escape(gen_news.brief_headline(d, strikes))
        desc = gen_news.escape(gen_news.brief_teaser(strikes, voices))
        pub = format_datetime(midnight_msk(d))
        items.append(
            "  <item>\n"
            f"    <title>{title}</title>\n"
            f"    <link>{url}</link>\n"
            f'    <guid isPermaLink="true">{url}</guid>\n'
            f"    <pubDate>{pub}</pubDate>\n"
            f"    <description>{desc}</description>\n"
            "  </item>"
        )
    last_build = format_datetime(datetime.now(MSK))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "<channel>\n"
        "  <title>Топливный фронт РФ — сводки по дням</title>\n"
        f"  <link>{SITE}/news</link>\n"
        f'  <atom:link href="{SITE}/rss.xml" rel="self" type="application/rss+xml"/>\n'
        "  <description>Ежедневные OSINT-сводки: удары по НПЗ и нефтебазам, дефицит бензина и дизеля, лимиты на АЗС, цены и биржа СПбМТСБ.</description>\n"
        "  <language>ru</language>\n"
        f"  <lastBuildDate>{last_build}</lastBuildDate>\n"
        "  <generator>gen-rss.py — npz-tactical-map</generator>\n"
        + "\n".join(items) + "\n"
        "</channel>\n"
        "</rss>\n"
    )


def build_news_sitemap(archive: dict) -> str:
    briefs = archive.get("briefs", {})
    cutoff = datetime.now(MSK) - timedelta(hours=NEWS_WINDOW_HOURS)
    urls = []
    for d in sorted(briefs.keys(), reverse=True):
        dt = midnight_msk(d)
        if dt < cutoff:
            continue
        strikes = briefs[d].get("strikes", [])
        headline = gen_news.escape(f"Сводка за {gen_news.rus_date(d)}: {gen_news.brief_headline(d, strikes)}")
        urls.append(
            "  <url>\n"
            f"    <loc>{SITE}/news/{d}</loc>\n"
            "    <news:news>\n"
            "      <news:publication>\n"
            "        <news:name>Топливный фронт РФ</news:name>\n"
            "        <news:language>ru</news:language>\n"
            "      </news:publication>\n"
            f"      <news:publication_date>{dt.isoformat()}</news:publication_date>\n"
            f"      <news:title>{headline}</news:title>\n"
            "    </news:news>\n"
            "  </url>"
        )
    body = "\n".join(urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">\n'
        + (body + "\n" if body else "")
        + "</urlset>\n"
    )


def main():
    archive = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
    RSS_OUT.write_text(build_rss(archive), encoding="utf-8")
    NEWS_SITEMAP_OUT.write_text(build_news_sitemap(archive), encoding="utf-8")
    n = min(RSS_CAP, len(archive.get("briefs", {})))
    print(f"[gen-rss] ✅ rss.xml ({n} items)")
    print("[gen-rss] ✅ news-sitemap.xml")


if __name__ == "__main__":
    main()
