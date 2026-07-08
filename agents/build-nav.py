#!/usr/bin/env python3
"""Единый навбар для всех статей/лендингов — генерится из data/seo-topics.jsonl.

Источник правды один: реестр. Добавил страницу в seo-topics.jsonl (+ подпись в
LABELS ниже, если хочешь красивый лейбл) → запусти `python3 agents/build-nav.py`
и она сама появится в выпадашке «Аналитика» в нужной группе на ВСЕХ страницах.
Это убивает сирот навсегда: забыть добавить пункт в меню руками уже нельзя.

Тип страницы (`type` в реестре) → группа меню:
  region → Регионы · explainer → Объяснялки · forecast → Прогноз ·
  reference → Справочники · object(/npz/*) → в меню не показываем, только через /refineries.
"""
import json, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
REG  = ROOT / "data" / "seo-topics.jsonl"

# Верхний уровень (порядок важен): url, emoji, label
TOP      = [("/", "🗺️", "Карта НПЗ"), ("/news", "📰", "Сводки"), ("/radar", "📡", "Радар")]
TOP_TAIL = [("/sources", "📚", "Источники")]

# Группы выпадашки: (заголовок, [типы из реестра])
GROUPS = [
    ("Регионы",     ["region"]),
    ("Объяснялки",  ["explainer"]),
    ("Прогноз",     ["forecast"]),
    ("Справочники", ["reference"]),
]

# Подписи пунктов меню: url -> (emoji, label). Нет в списке → берётся primary_kw.
LABELS = {
    "/crimea":     ("🗺", "Крым"),
    "/krasnodar":  ("🌴", "Краснодар"),
    "/moskva":     ("🏙", "Москва"),
    "/deficit":    ("⛽", "Почему нет бензина"),
    "/talony":     ("🎫", "Бензин по талонам"),
    "/crisis":     ("🔥", "Прогноз кризиса"),
    "/attacks":    ("💥", "Хроника ударов"),
    "/refineries": ("🏭", "Список НПЗ · все заводы"),
}

TOP_URLS   = {u for u, _, _ in TOP + TOP_TAIL}
HIDE_TYPES = {"object"}  # /npz/* — только через /refineries, десятки заводов в меню не льём

# Страницы, получающие полный навбар
TARGETS = ["analytics.html", "attacks.html", "crimea.html", "crisis.html",
           "deficit.html", "krasnodar.html", "moskva.html", "refineries.html",
           "talony.html", "news.html", "npz/omskij-npz.html", "npz/moskovskij-npz.html"]

NAV_RE = re.compile(r'<nav class="news-nav">.*?</nav>', re.DOTALL)


def load_reg():
    rows = []
    for line in REG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def label_for(url, primary_kw):
    return LABELS.get(url, ("📄", (primary_kw or url).capitalize()))


def build_menu(rows, current):
    out = []
    for title, types in GROUPS:
        picked = [r for r in rows
                  if r.get("status", "live") == "live"
                  and r.get("type") in types
                  and r["url"] not in TOP_URLS
                  and r.get("type") not in HIDE_TYPES]
        if not picked:
            continue
        out.append(f'            <div class="nav-drop-group">{title}</div>')
        for r in picked:
            emoji, lab = label_for(r["url"], r.get("primary_kw"))
            cur = ' aria-current="page"' if r["url"] == current else ""
            out.append(f'            <a href="{r["url"]}"{cur}>{emoji} {lab}</a>')
    return "\n".join(out)


def build_nav(rows, current):
    def link(url, emoji, lab):
        cur = ' aria-current="page"' if url == current else ""
        return f'        <a href="{url}"{cur}>{emoji} {lab}</a>'
    L = [link(u, e, l) for u, e, l in TOP]
    drop_cur = ' aria-current="page"' if current == "/analytics" else ""
    L += ['        <div class="nav-dropdown" style="position:relative;display:inline-block">',
          f'          <a href="/analytics"{drop_cur} style="color:var(--teal);font-weight:700">📊 Аналитика ▾</a>',
          '          <div class="nav-dropdown-menu">',
          build_menu(rows, current),
          '          </div>',
          '        </div>']
    L += [link(u, e, l) for u, e, l in TOP_TAIL]
    return '<nav class="news-nav">\n' + "\n".join(L) + '\n      </nav>'


def main():
    rows = load_reg()
    changed = 0
    for rel in TARGETS:
        f = ROOT / rel
        if not f.exists():
            print("skip missing", rel); continue
        html = f.read_text(encoding="utf-8")
        current = "/" + rel[:-5]  # analytics.html -> /analytics
        new, n = NAV_RE.subn(build_nav(rows, current), html, count=1)
        if n == 0:
            print("!! no news-nav in", rel); continue
        if new != html:
            f.write_text(new, encoding="utf-8"); changed += 1; print("updated", rel)
    print(f"done, {changed} files changed")


if __name__ == "__main__":
    main()
