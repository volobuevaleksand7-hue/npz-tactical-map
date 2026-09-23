#!/usr/bin/env python3
"""Карточки /npz/*.html: title/H1 под интент «<завод> работает или нет» + блок ответа
первым экраном из data/fuel-state.json (между маркерами CARD-STATUS).

Зачем (23.09.2026): в Вебмастере растут запросы «нпз капотня работает или нет»,
«ярославский нпз работает или нет» (CTR 13–25%), а карточки держали датированные
title вида «удар БПЛА 10 июня» и статус, застывший на июле (Куйбышевский стоит с
22.09, карточка «обновлена 9 июля»). /npz/kinef с ответом первой строкой — самая
посещаемая карточка. Обещать «работает или нет» можно только с честным ответом ниже.

Блок без даты «на сегодня» — меняется только при смене статуса, без ежедневного
перекоммита 33 файлов. Идемпотентен. Запуск: python3 agents/gen-npz-card-status.py
Самопроверка без записи: --demo.
"""
import importlib.util
import json
import os
import re
import sys
from html import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, fname):
    s = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "agents", fname))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


REF = _load("gen_refineries", "gen-refineries.py")      # CARDS, state_phrase
NAV = _load("build_nav", "build-nav.py")                # LABELS: имя завода для меню

START, END = "<!-- CARD-STATUS:START -->", "<!-- CARD-STATUS:END -->"
BLOCK_RE = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)


def label(slug):
    return NAV.LABELS[f"/npz/{slug}"][1]


def block(r, name):
    phrase = REF.state_phrase(r)
    load = " (выработка 0%)" if r["status"] == "down" else ""  # у partial процент уже в state_phrase
    src = (r.get("source_url") or "").strip()
    src_a = f' Источник: <a href="{escape(src)}" rel="nofollow noopener" target="_blank">открытая публикация ↗</a>.' if src.startswith("http") else ""
    return (f'{START}\n<p class="lead-p card-status"><strong>Работает ли {escape(name)} сейчас?</strong> '
            f'По оценке открытых источников — <strong>{escape(phrase)}</strong>{load}.{src_a} '
            f'Статус всех 33 заводов — <a href="/rabotayut-li-npz-rossii">какие НПЗ работают сейчас</a>.</p>\n{END}')


def render(html, r, slug):
    name = label(slug)
    title = f"{name} работает или нет сегодня: статус завода и удары БПЛА"
    h1 = f"{name}: работает или нет — статус завода и хроника ударов"
    html = re.sub(r"<title>.*?</title>", f"<title>{escape(title)}</title>", html, count=1, flags=re.S)
    for attr in ('property="og:title"', 'name="twitter:title"'):
        html = re.sub(r'(<meta ' + re.escape(attr) + r' content=")[^"]*(")', lambda m: m.group(1) + escape(title) + m.group(2), html, count=1)
    html = re.sub(r'("headline": ")[^"]*(")', lambda m: m.group(1) + title.replace('"', '\\"') + m.group(2), html, count=1)
    html = re.sub(r"(<h1[^>]*>).*?(</h1>)", lambda m: m.group(1) + escape(h1) + m.group(2), html, count=1, flags=re.S)
    b = block(r, name)
    if BLOCK_RE.search(html):
        html = BLOCK_RE.sub(lambda m: b, html, count=1)
    else:
        html = re.sub(r"(<h1[^>]*>.*?</h1>)", lambda m: m.group(1) + "\n" + b, html, count=1, flags=re.S)
    return html


def main(write=True):
    R = json.load(open(os.path.join(ROOT, "data", "fuel-state.json"), encoding="utf-8"))["refineries"]
    changed = 0
    for r in R:
        slug = REF.CARDS.get(r["id"])
        path = os.path.join(ROOT, "npz", f"{slug}.html") if slug else None
        if not path or not os.path.exists(path):
            print(f"!! нет карточки для {r['id']}", file=sys.stderr)
            continue
        html = open(path, encoding="utf-8").read()
        new = render(html, r, slug)
        if new != html:
            changed += 1
            if write:
                open(path, "w", encoding="utf-8").write(new)
    print(f"gen-npz-card-status: карточек изменено {changed}")
    return changed


def demo():
    r = {"id": "x", "status": "down", "est_output_pct": 0, "status_since": "2026-09-22", "source_url": "https://e.org/a"}
    page = '<title>Старый</title><meta property="og:title" content="o"><meta name="twitter:title" content="t">"headline": "h",<h1 class="x">Старый H1</h1><p>тело</p>'
    NAV.LABELS["/npz/demo"] = ("🛢️", "Куйбышевский НПЗ (Самара)")
    once = render(page, r, "demo")
    assert "Куйбышевский НПЗ (Самара) работает или нет сегодня" in once
    assert "остановлен с 22 сентября 2026" in once and "выработка 0%" in once, once
    assert once.count(START) == 1 and once.index(START) > once.index("</h1>")
    assert render(once, r, "demo") == once, "не идемпотентен"
    r2 = dict(r, status="partial", est_output_pct=40)
    assert "работает на ~40%" in render(once, r2, "demo") and render(once, r2, "demo").count(START) == 1
    print("demo OK")


if __name__ == "__main__":
    demo() if "--demo" in sys.argv else main()
