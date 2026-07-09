#!/usr/bin/env python3
"""Публикация одной страницы «ракетная опасность <город>» в прод.

Идемпотентно: генерит HTML в корень, добавляет live-строку в реестр и запись в
sitemap.xml (если ещё нет), перегенерит навбар, проверяет IA, коммитит с гейтом
и пушит безопасно: commit-first → git pull --rebase (БЕЗ --autostash, протокол HERMES.md §0).

  python3 agents/publish-rocket-danger.py volgograd            # опубликовать
  python3 agents/publish-rocket-danger.py volgograd --dry-run   # без commit/push

Утренняя рутина выбирает город и зовёт этот скрипт — вся вёрстка/копирайт уже в
agents/gen-rocket-danger.py, здесь только механика публикации.
"""
import sys, subprocess, pathlib, importlib.util, datetime, json

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
REG = ROOT / "data" / "seo-topics.jsonl"
SITEMAP = ROOT / "sitemap.xml"
SITE = "https://npz-tactical-map.vercel.app"

spec = importlib.util.spec_from_file_location("gen", HERE / "gen-rocket-danger.py")
gen = importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)


def sh(cmd, **kw):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=True, **kw)


def add_registry(slug_url, key):
    lines = [l for l in REG.read_text(encoding="utf-8").splitlines() if l.strip()]
    if any(json.loads(l).get("url") == slug_url for l in lines):
        print("реестр: запись уже есть"); return
    entry = subprocess.run([sys.executable, str(HERE / "gen-rocket-danger.py"), key, "--registry"],
                           cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    with REG.open("a", encoding="utf-8") as f:
        f.write(entry + "\n")
    print("реестр: добавлено", slug_url)


def add_sitemap(slug_url, today):
    xml = SITEMAP.read_text(encoding="utf-8")
    loc = f"{SITE}{slug_url}"
    if loc in xml:
        print("sitemap: уже есть"); return
    block = (f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{today}</lastmod>\n"
             f"    <changefreq>daily</changefreq>\n    <priority>0.8</priority>\n"
             f'    <xhtml:link rel="alternate" hreflang="ru" href="{loc}"/>\n  </url>\n')
    xml = xml.replace("</urlset>", block + "</urlset>", 1)
    SITEMAP.write_text(xml, encoding="utf-8")
    print("sitemap: добавлено", loc)


def main(argv):
    if not argv or argv[0] not in gen.CITIES:
        sys.exit(f"укажи город: {', '.join(gen.CITIES)}")
    key = argv[0]; dry = "--dry-run" in argv
    slug = gen.CITIES[key]["slug"]; slug_url = f"/{slug}"
    today = datetime.date.today().isoformat()

    sh([sys.executable, str(HERE / "gen-rocket-danger.py"), key, "--root"])
    add_registry(slug_url, key)
    add_sitemap(slug_url, today)
    sh([sys.executable, str(HERE / "build-nav.py")])
    sh([sys.executable, str(HERE / "check-ia.py")])

    if dry:
        print("--dry-run: коммит/пуш пропущены"); return

    sh(["git", "add", "-A"])
    env = {"ALLOW_FRONTEND_RELEASE": "1"}
    msg = (f"seo: страница «ракетная опасность {gen.CITIES[key]['nom']}» ({slug_url})\n\n"
           f"Long-tail региональная страница из хвоста freshness. Сгенерена\n"
           f"agents/gen-rocket-danger.py, воронка на /radar, нейтральный OSINT-тон.\n\n"
           f"Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
    import os
    e = {**os.environ, **env}
    subprocess.run(["git", "commit", "-m", msg], cwd=ROOT, check=True, env=e)
    # безопасный пуш (протокол HERMES.md §0): дерево чистое после commit →
    # plain --rebase, НИКОГДА --autostash (он молча сносит чужие uncommitted правки)
    for _ in range(4):
        if subprocess.run(["git", "push", "origin", "main"], cwd=ROOT).returncode == 0:
            break
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=ROOT, check=True)
    else:
        raise RuntimeError("push отклонён после 4 попыток — синхронизировать вручную")
    print(f"\n✅ опубликовано: {SITE}{slug_url}")


if __name__ == "__main__":
    main(sys.argv[1:])
