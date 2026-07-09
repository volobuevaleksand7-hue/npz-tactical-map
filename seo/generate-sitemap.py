#!/usr/bin/env python3
"""
Auto-generate sitemap.xml for NPZ Tactical Map.

Scans all .html files under the project root, classifies them by type,
and outputs a valid XML sitemap to the project root.

Usage:
    python3 seo/generate-sitemap.py

Rules:
  - index.html         → priority 1.0, changefreq daily
  - news/*.html         → priority 0.8, changefreq daily
  - all other .html     → priority 0.6, changefreq weekly
  - lastmod taken from file mtime (ISO date)
  - Base URL: https://npz-tactical-map.vercel.app
"""

import os
from datetime import datetime

BASE_URL = "https://npz-tactical-map.vercel.app"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "sitemap.xml")

# Files to exclude from the sitemap (verification files, drafts, etc.)
EXCLUDE = {
    "yandex_3043c11e2e96ee23.html",
    "news-07-07.html",       # stray draft
    "2026-07-07.html",       # stray file at root (duplicate of news/2026-07-07.html)
    "seo/meta-tags.html",    # internal template, not public
    "support.html",          # скрытая страница донатов — НЕ индексировать
    "404.html",              # кастомная 404 (noindex) — не место в sitemap
}


def file_to_url(rel_path: str) -> str:
    """Convert a relative file path to a clean URL path (no .html extension)."""
    if rel_path == "index.html":
        return "/"
    if rel_path.endswith(".html"):
        return "/" + rel_path[:-5]
    return "/" + rel_path


def classify(rel_path: str):
    """Return (priority, changefreq) based on file type."""
    if rel_path == "index.html":
        return "1.0", "daily"
    if rel_path.startswith("news/") and rel_path.endswith(".html"):
        return "0.8", "daily"
    return "0.6", "weekly"


def get_lastmod(filepath: str) -> str:
    """Return ISO date from file mtime."""
    mtime = os.path.getmtime(filepath)
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


def xml_escape(text: str) -> str:
    """Escape special XML characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_sitemap():
    # Collect all .html files
    all_html = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Exclude hidden directories and development/ignored/draft folders
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {
            "drafts", "docs", "dashboard", "agents", "seo", ".git", ".github", 
            ".venv", ".vercel", "__pycache__", "node_modules", "temp"
        }]
        for f in files:
            if not f.endswith(".html"):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, PROJECT_ROOT)
            rel = rel.replace(os.sep, "/")
            if rel in EXCLUDE:
                continue
            all_html.append((rel, full))

    # Sort: index first, then news descending, then others alphabetically
    index_files = [(r, f) for r, f in all_html if r == "index.html"]
    news_files = sorted(
        [(r, f) for r, f in all_html if r.startswith("news/")],
        key=lambda x: x[0],
        reverse=True,
    )
    other_files = sorted(
        [(r, f) for r, f in all_html if r != "index.html" and not r.startswith("news/")],
        key=lambda x: x[0],
    )
    ordered = index_files + news_files + other_files

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">',
        "",
    ]

    count = 0
    for rel, full in ordered:
        url_path = file_to_url(rel)
        priority, changefreq = classify(rel)
        lastmod = get_lastmod(full)
        loc = xml_escape(BASE_URL + url_path)

        lines.append("  <url>")
        lines.append(f"    <loc>{loc}</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append(f"    <priority>{priority}</priority>")
        lines.append(f'    <xhtml:link rel="alternate" hreflang="ru" href="{loc}"/>')
        lines.append("  </url>")
        count += 1

    lines.append("")
    lines.append("</urlset>")
    lines.append("")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✅ sitemap.xml generated: {OUTPUT_PATH}")
    print(f"   {count} URLs included")
    print(f"   Base URL: {BASE_URL}")
    print(f"   Excluded: {len(EXCLUDE)} files")


if __name__ == "__main__":
    build_sitemap()
