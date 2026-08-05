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
NEWS_ARCHIVE_RE = re.compile(r"^/news/\d{4}-\d{2}(-\d{2})?$")  # день YYYY-MM-DD или месячный хаб YYYY-MM
WAVE_SNAPSHOT_RE = re.compile(r"^/volna-dronov/\d{4}-\d{2}-\d{2}-\d{4}$")  # вечный снимок волны, не в реестре
LOC_RE = re.compile(r"<loc>https?://[^/]+(/[^<]*)</loc>")


def file_for(url):
    if url == "/":
        return ROOT / "index.html"
    return ROOT / (url.lstrip("/") + ".html")


def check_orphans(sitemap, rows):
    known = bn.TOP_URLS | KNOWN_EXTRA_URLS | {r["url"] for r in rows}
    warnings = []
    for url in LOC_RE.findall(sitemap):
        if url not in known and not NEWS_ARCHIVE_RE.match(url) and not WAVE_SNAPSHOT_RE.match(url):
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


def check_nav_hygiene(rows):
    """Гигиена меню для НОВЫХ страниц — ловит ровно две регрессии, которые уже случались:

    1. нет подписи в build-nav.LABELS → пункт печатается сырым SEO-ключом и заглушкой 📄
       («сгорел склад wildberries что делать»);
    2. страница не попала ни в одну подгруппу → висит пином в корне группы, и меню
       постепенно снова превращается в портянку.
    Не блокирует сборку: страница-одиночка в новой теме — это нормально, пока их мало.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_nav", ROOT / "agents" / "build-nav.py")
    bn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bn)

    live = [r for r in rows if r.get("status") == "live"]
    out = []
    for r in sorted(live, key=lambda x: x["url"]):
        if r.get("type") == "hub":            # /analytics — сам каталог, пунктом меню не бывает
            continue
        if r["url"] not in bn.LABELS and r["url"] not in {u for u, _, _ in bn.TOP + bn.TOP_TAIL}:
            out.append(f"{r['url']}: нет подписи в build-nav.LABELS — в меню будет сырой ключ "
                       f"«{r.get('primary_kw', '')}»")
    # указана подгруппа, которой нет в SUBGROUPS — страница молча уедет в пины
    known = {s.lower() for subs in bn.SUBGROUPS.values() for _, s, _ in subs}
    for r in live:
        g = (r.get("group") or "").strip()
        if g and g.lower() not in known:
            out.append(f"{r['url']}: group=«{g}» не найдена в build-nav.SUBGROUPS")
    # раздувшийся корень группы = пора заводить подгруппу. collapse-группы пропускаем:
    # они и так свёрнуты целиком, длина внутри них на меню не влияет.
    for title, _pred, _collapse in bn.GROUPS:
        if _collapse:
            continue
        picked = [r for r in live if _pred(r)]
        pinned, _subs = bn.split_subgroups(title, picked)
        if len(pinned) > 8:
            out.append(f"группа «{title}»: {len(pinned)} пунктов подряд без подгруппы — "
                       f"меню снова растёт портянкой, заведи подгруппу в build-nav.SUBGROUPS")
    return out


def check_cyrillic_hrefs():
    """Внутренние ссылки со славянскими буквами в слаге = гарантированный 404.

    Как это случилось (05.08): цензор нейтральности гоняется по СЫРОМУ HTML, без
    strip_markup, и правило LATIN_FIX «TAIF-NK → ТАИФ-НК» переписывало не только текст,
    но и href="/npz/taif-nk" → href="/npz/ТАИФ-НК". Битая ссылка разъехалась по 91
    странице, включая /refineries и все архивы /news, и жила на проде незамеченной.
    Лукбихайнд в самом правиле закрывает ровно этот случай — а проверка закрывает КЛАСС:
    любое будущее правило словаря, которое залезет в атрибут, упрётся здесь.
    """
    bad = []
    for p in sorted(ROOT.rglob("*.html")):
        if ".claude" in p.parts or "node_modules" in p.parts:
            continue
        for m in re.finditer(r'href="(/[^"]*)"', p.read_text(encoding="utf-8")):
            if re.search(r"[А-Яа-яЁё]", m.group(1)):
                bad.append(f"{p.relative_to(ROOT)}: href=\"{m.group(1)}\" — кириллица в слаге, это 404")
    return bad


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
    problems += check_cyrillic_hrefs()
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

    nav_warnings = check_nav_hygiene(rows)
    if nav_warnings:
        print("NAV WARNINGS (не блокирует):")
        for w in nav_warnings:
            print("  -", w)

    print(f"IA check OK — {live} live-страниц: файлы, sitemap и меню на месте.")


if __name__ == "__main__":
    main()
