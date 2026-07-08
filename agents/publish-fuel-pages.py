#!/usr/bin/env python3
"""Публикация топливных страниц (/benzin-na-trasse, /gde-dizel) в прод.

Идемпотентно, аналог publish-rocket-danger.py. Вёрстка/копирайт в
agents/gen-fuel-pages.py.

  python3 agents/publish-fuel-pages.py benzin-na-trasse       # одну
  python3 agents/publish-fuel-pages.py --all                  # все ещё не выпущенные
  python3 agents/publish-fuel-pages.py --all --dry-run
"""
import sys, subprocess, pathlib, importlib.util, datetime, json, os

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
REG = ROOT / "data" / "seo-topics.jsonl"
SITEMAP = ROOT / "sitemap.xml"
SITE = "https://npz-tactical-map.vercel.app"

spec = importlib.util.spec_from_file_location("genfuel", HERE / "gen-fuel-pages.py")
gen = importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)


def sh(cmd, **kw):
    print("$", " ".join(cmd)); return subprocess.run(cmd, cwd=ROOT, check=True, **kw)


def published():
    urls = set()
    for l in REG.read_text(encoding="utf-8").splitlines():
        if l.strip():
            urls.add(json.loads(l).get("url"))
    return urls


def add_registry(key):
    slug_url = f"/{gen.PAGES[key]['slug']}"
    if slug_url in published():
        print("реестр: уже есть", slug_url); return
    entry = subprocess.run([sys.executable, str(HERE / "gen-fuel-pages.py"), key, "--registry"],
                           cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    with REG.open("a", encoding="utf-8") as f:
        f.write(entry + "\n")
    print("реестр: добавлено", slug_url)


def add_sitemap(key, today):
    loc = f"{SITE}/{gen.PAGES[key]['slug']}"
    xml = SITEMAP.read_text(encoding="utf-8")
    if loc in xml:
        print("sitemap: уже есть"); return
    block = (f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{today}</lastmod>\n"
             f"    <changefreq>daily</changefreq>\n    <priority>0.8</priority>\n"
             f'    <xhtml:link rel="alternate" hreflang="ru" href="{loc}"/>\n  </url>\n')
    SITEMAP.write_text(xml.replace("</urlset>", block + "</urlset>", 1), encoding="utf-8")
    print("sitemap: добавлено", loc)


def main(argv):
    dry = "--dry-run" in argv
    if "--all" in argv:
        keys = [k for k in gen.PAGES if f"/{gen.PAGES[k]['slug']}" not in published()]
        if not keys:
            print("все топливные страницы уже выпущены"); return
    else:
        keys = [a for a in argv if a in gen.PAGES]
        if not keys:
            sys.exit(f"укажи страницу или --all: {', '.join(gen.PAGES)}")

    today = datetime.date.today().isoformat()
    for key in keys:
        sh([sys.executable, str(HERE / "gen-fuel-pages.py"), key, "--root"])
        add_registry(key)
        add_sitemap(key, today)
    sh([sys.executable, str(HERE / "build-nav.py")])
    sh([sys.executable, str(HERE / "check-ia.py")])

    if dry:
        print("--dry-run: коммит/пуш пропущены"); return

    sh(["git", "add", "-A"])
    names = ", ".join(f"/{gen.PAGES[k]['slug']}" for k in keys)
    msg = (f"seo: топливные страницы ({names})\n\n"
           f"Сгенерены agents/gen-fuel-pages.py, воронка на карты/deficit,\n"
           f"нейтральный тон.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
    subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True,
                   env={**os.environ, "ALLOW_FRONTEND_RELEASE": "1"})
    sh(["git", "pull", "--rebase", "--autostash", "origin", "main"])
    sh(["git", "push", "origin", "main"])
    print(f"\n✅ опубликовано: {names}")


if __name__ == "__main__":
    main(sys.argv[1:])
