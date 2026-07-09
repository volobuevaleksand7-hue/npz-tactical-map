#!/usr/bin/env python3
"""Публикация объектных НПЗ-страниц из предсобранных черновиков drafts/npz/.

В отличие от rocket/fuel, контент НПЗ-страниц уникален и пишется заранее
(черновик в drafts/npz/<slug>.html). Этот скрипт только выкатывает готовый
черновик в прод: двигает файл, регистрирует в реестре/sitemap, гоняет nav+IA,
коммитит и пушит. Идемпотентно.

  python3 agents/publish-npz.py slavneft-yanos
  python3 agents/publish-npz.py --all           # все черновики из drafts/npz/, ещё не в реестре
  python3 agents/publish-npz.py slavneft-yanos --dry-run

Метаданные реестра — из REGISTRY (готовые строки ТЗ tz-articles-2026-07-08).
created проставляется датой публикации. Тип object → в топ-меню НЕ попадает
(живёт под /refineries), поэтому LABELS/HUB в build-nav не нужны.
"""
import sys, subprocess, pathlib, datetime, json, os

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
REG = ROOT / "data" / "seo-topics.jsonl"
SITEMAP = ROOT / "sitemap.xml"
SITE = "https://npz-tactical-map.vercel.app"
DRAFTS = ROOT / "drafts" / "npz"

REGISTRY = {
    "slavneft-yanos": {
        "primary_kw": "нпз янос",
        "keywords": ["удар по ярославскому нпз", "ярославль нпз бпла",
                     "ярославский нпз бпла", "ярославский нпз атака бпла",
                     "дефицит бензина в ярославле"],
        "note": "ЯНОС/Славнефть; удар 8 мая в strikes.json отдельной записью не отражён — "
                "формулировка «по данным открытых источников».",
    },
    "kujbyshevskij-npz": {
        "primary_kw": "куйбышевский нпз бпла",
        "keywords": ["куйбышевский нпз атака бпла", "удар по куйбышевскому нпз",
                     "дефицит бензина в самаре", "самара бензин по талонам"],
        "note": "НЕ путать с Новокуйбышевским НПЗ — отдельный завод, отдельная будущая страница.",
    },
    "ryazanskij-npz": {
        "primary_kw": "рязанский нпз бпла",
        "keywords": ["рязанский нпз атака бпла", "удар по рязанскому нпз",
                     "дефицит бензина в рязани", "дефицит бензина в рязанской области"],
        "note": "в strikes.json нет записей по заводу — хроника только из fuel-state.json, "
                "не выдумывать.",
    },
}


def sh(cmd, **kw):
    print("$", " ".join(cmd)); return subprocess.run(cmd, cwd=ROOT, check=True, **kw)


def published():
    urls = set()
    for l in REG.read_text(encoding="utf-8").splitlines():
        if l.strip():
            urls.add(json.loads(l).get("url"))
    return urls


def add_registry(slug, today):
    url = f"/npz/{slug}"
    if url in published():
        print("реестр: уже есть", url); return
    r = REGISTRY[slug]
    entry = {"url": url, "type": "object", "primary_kw": r["primary_kw"],
             "keywords": r["keywords"], "created": today, "status": "live",
             "note": r["note"]}
    with REG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print("реестр: добавлено", url)


def add_sitemap(slug, today):
    loc = f"{SITE}/npz/{slug}"
    xml = SITEMAP.read_text(encoding="utf-8")
    if loc in xml:
        print("sitemap: уже есть"); return
    block = (f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{today}</lastmod>\n"
             f"    <changefreq>weekly</changefreq>\n    <priority>0.7</priority>\n"
             f'    <xhtml:link rel="alternate" hreflang="ru" href="{loc}"/>\n  </url>\n')
    SITEMAP.write_text(xml.replace("</urlset>", block + "</urlset>", 1), encoding="utf-8")
    print("sitemap: добавлено", loc)


def move_draft(slug):
    src = DRAFTS / f"{slug}.html"
    dst = ROOT / "npz" / f"{slug}.html"
    if not src.exists():
        if dst.exists():
            print("черновик уже выкачен:", dst.relative_to(ROOT)); return
        sys.exit(f"нет черновика {src.relative_to(ROOT)} и нет {dst.relative_to(ROOT)}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    src.unlink()
    print(f"выкачено: {src.relative_to(ROOT)} → {dst.relative_to(ROOT)}")


def main(argv):
    dry = "--dry-run" in argv
    if "--all" in argv:
        pub = published()
        slugs = [p.stem for p in sorted(DRAFTS.glob("*.html"))
                 if f"/npz/{p.stem}" not in pub and p.stem in REGISTRY]
        if not slugs:
            print("нет невыпущенных черновиков в drafts/npz/"); return
    else:
        slugs = [a for a in argv if a in REGISTRY]
        if not slugs:
            sys.exit(f"укажи slug или --all. Известные: {', '.join(REGISTRY)}")

    today = datetime.date.today().isoformat()
    for slug in slugs:
        move_draft(slug)
        add_registry(slug, today)
        add_sitemap(slug, today)
    sh([sys.executable, str(HERE / "build-nav.py")])
    sh([sys.executable, str(HERE / "check-ia.py")])

    if dry:
        print("--dry-run: коммит/пуш пропущены"); return

    sh(["git", "add", "-A"])
    names = ", ".join(f"/npz/{s}" for s in slugs)
    msg = (f"seo: НПЗ-страница ({names})\n\n"
           f"Выкачено из drafts/npz/ (контент по ТЗ tz-articles-2026-07-08 + data/*),\n"
           f"нейтральный тон, 3 JSON-LD, крошки на /refineries.\n\n"
           f"Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
    subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True,
                   env={**os.environ, "ALLOW_FRONTEND_RELEASE": "1"})
    sh(["git", "pull", "--rebase", "--autostash", "origin", "main"])
    sh(["git", "push", "origin", "main"])
    print(f"\n✅ опубликовано: {names}\n"
          f"⚠️ добавить обратную ссылку-карточку с /refineries и из ближайшей сводки (ручной шаг реоптa).")


if __name__ == "__main__":
    main(sys.argv[1:])
