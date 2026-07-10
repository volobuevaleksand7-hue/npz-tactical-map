#!/usr/bin/env python3
"""Проверка целостности информационной архитектуры.

Каждая live-страница из data/seo-topics.jsonl обязана иметь: файл на диске,
запись в sitemap.xml и место в меню «Аналитика» (кроме top-nav и /npz/*).
Падает с exit 1, если что-то оторвано. Гонять перед пушем / в CI.

Обратный проход: каждый <loc> из sitemap.xml обязан быть либо top-nav
(TOP_URLS), либо в реестре, либо в ручном списке инфра-страниц (KNOWN_EXTRA_URLS)
/ архивом /news/YYYY-MM-DD. Иначе — не fail, а warning про осиротевший/чужой URL
в sitemap (так утекли exilenova.html/radarrusiia.html и дубль moskovskij-npz).
"""
import sys, re, pathlib, importlib.util

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

spec = importlib.util.spec_from_file_location("buildnav", HERE / "build-nav.py")
bn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bn)

# Страницы, которые живут в sitemap, но не идут через реестр seo-topics.jsonl —
# добавлять сюда руками при появлении новой фиксированной страницы вне registry.
KNOWN_EXTRA_URLS = {"/analytics", "/install"}
NEWS_ARCHIVE_RE = re.compile(r"^/news/\d{4}-\d{2}-\d{2}$")
LOC_RE = re.compile(r"<loc>https?://[^/]+(/[^<]*)</loc>")


def file_for(url):
    if url == "/":
        return ROOT / "index.html"
    return ROOT / (url.lstrip("/") + ".html")


def check_orphans(sitemap, rows):
    known = bn.TOP_URLS | KNOWN_EXTRA_URLS | {r["url"] for r in rows}
    warnings = []
    for url in LOC_RE.findall(sitemap):
        if url not in known and not NEWS_ARCHIVE_RE.match(url):
            warnings.append(f"{url}: есть в sitemap.xml, но не в реестре/TOP_URLS — осиротевший/мусорный URL?")
    return warnings


# Обязательные head-элементы для лендингов/инфо-страниц. Ловит head-находки аудита
# (install/support без OG, нет viewport-fit) без рискованной централизации head.
# index.html/radar.html исключены — у них своя шапка/голова (карта, гейт).
HEAD_CHECKS = [
    ("canonical",      'rel="canonical"'),
    ("og:type",        'property="og:type"'),
    ("og:url",         'property="og:url"'),
    ("og:title",       'property="og:title"'),
    ("og:description", 'property="og:description"'),
    ("og:image",       'property="og:image"'),
    ("twitter:card",   'name="twitter:card"'),
    ("viewport-fit",   'viewport-fit=cover'),
    ("theme-color",    'name="theme-color"'),
    ("/fonts.css",     '/fonts.css'),
    ("styles.css",     'styles.css'),
]
HEAD_SKIP = {"index.html", "radar.html"}


def check_head_meta():
    warnings = []
    for f in sorted(ROOT.glob("*.html")):
        if f.name in HEAD_SKIP:
            continue
        head = f.read_text(encoding="utf-8").split("</head>", 1)[0]
        missing = [label for label, needle in HEAD_CHECKS if needle not in head]
        if missing:
            warnings.append(f"{f.name}: нет head-элементов: {', '.join(missing)}")
    return warnings


def main():
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    rows = bn.load_reg()
    menu = bn.build_menu(rows, None)
    problems, live = [], 0
    for r in rows:
        if r.get("status", "live") != "live":
            continue
        live += 1
        url, typ = r["url"], r.get("type")
        if not file_for(url).exists():
            problems.append(f"{url}: нет файла {file_for(url).relative_to(ROOT)}")
        if url not in sitemap:
            problems.append(f"{url}: нет в sitemap.xml")
        if url not in bn.TOP_URLS and typ not in bn.HIDE_TYPES:
            if f'href="{url}"' not in menu:
                problems.append(f"{url}: нет пункта в меню (type={typ})")
    if problems:
        print("IA CHECK FAILED:")
        for p in problems:
            print("  -", p)
        sys.exit(1)

    warnings = check_orphans(sitemap, rows)
    if warnings:
        print("IA CHECK WARNINGS (не блокирует):")
        for w in warnings:
            print("  -", w)

    head_warnings = check_head_meta()
    if head_warnings:
        print("HEAD-META WARNINGS (не блокирует):")
        for w in head_warnings:
            print("  -", w)

    print(f"IA check OK — {live} live-страниц: файлы, sitemap и меню на месте.")


if __name__ == "__main__":
    main()
