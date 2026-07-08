#!/usr/bin/env python3
"""Проверка целостности информационной архитектуры.

Каждая live-страница из data/seo-topics.jsonl обязана иметь: файл на диске,
запись в sitemap.xml и место в меню «Аналитика» (кроме top-nav и /npz/*).
Падает с exit 1, если что-то оторвано. Гонять перед пушем / в CI.
"""
import sys, pathlib, importlib.util

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

spec = importlib.util.spec_from_file_location("buildnav", HERE / "build-nav.py")
bn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bn)


def file_for(url):
    if url == "/":
        return ROOT / "index.html"
    return ROOT / (url.lstrip("/") + ".html")


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
    print(f"IA check OK — {live} live-страниц: файлы, sitemap и меню на месте.")


if __name__ == "__main__":
    main()
