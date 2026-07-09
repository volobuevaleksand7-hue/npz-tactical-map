#!/usr/bin/env python3
"""Единый навбар + хаб для всех статей/лендингов — генерится из data/seo-topics.jsonl.

Источник правды один: реестр. Добавил страницу в seo-topics.jsonl (+ подписи в
LABELS/HUB ниже, если хочешь красиво) → запусти `python3 agents/build-nav.py` — и
она сама появляется в ТРЁХ местах:
  1) выпадашка «Аналитика» на всех лендингах (news-nav),
  2) дропдаун «АНАЛИТИКА» на ГЛАВНОЙ карте (index.html, tab-dropdown-menu),
  3) каталог-хаб /analytics (analytics-grid).
Это убивает сирот навсегда: забыть добавить пункт в меню руками уже нельзя.
Проверяет целостность `agents/check-ia.py`.

⚠️ index.html — фронтенд-ядро: его коммит требует ALLOW_FRONTEND_RELEASE=1.

Тип страницы (`type` в реестре) → группа меню:
  region → Регионы · explainer → Объяснялки · forecast → Прогноз ·
  reference → Справочники · tool → Карты · object(/npz/*) → скрыт, только через /refineries.
"""
import json, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
REG  = ROOT / "data" / "seo-topics.jsonl"

# Верхний уровень (порядок важен): url, emoji, label
TOP      = [("/", "🗺️", "Карта НПЗ"), ("/news", "📰", "Сводки"), ("/radar", "📡", "Радар БПЛА")]
TOP_TAIL = [("/sources", "📚", "Источники")]

# Группы выпадашки: (заголовок, [типы из реестра]). Порядок = порядок в меню и на хабе.
GROUPS = [
    ("Регионы",     ["region"]),
    ("Объяснялки",  ["explainer"]),
    ("Прогноз",     ["forecast"]),
    ("Справочники", ["reference"]),
    ("Карты",       ["tool"]),
]

# Подписи пунктов меню: url -> (emoji, label). Нет в списке → берётся primary_kw.
LABELS = {
    "/crimea":            ("🗺", "Крым"),
    "/krasnodar":         ("🌴", "Краснодар"),
    "/moskva":            ("🏙", "Москва"),
    "/raketnaya-opasnost-volgograd": ("🚀", "Ракетная опасность: Волгоград"),
    "/raketnaya-opasnost-ulyanovsk": ("🚀", "Ракетная опасность: Ульяновск"),
    "/raketnaya-opasnost-kazan":     ("🚀", "Ракетная опасность: Казань"),
    "/raketnaya-opasnost-omsk":      ("🚀", "Ракетная опасность: Омск"),
    "/raketnaya-opasnost-cheboksary": ("🚀", "Ракетная опасность: Чебоксары"),
    "/raketnaya-opasnost-moskovskaya-oblast": ("🚀", "Ракетная опасность: Московская обл."),
    "/raketnaya-opasnost-penza":     ("🚀", "Ракетная опасность: Пенза"),
    "/raketnaya-opasnost-samara":    ("🚀", "Ракетная опасность: Самара"),
    "/deficit":           ("⛽", "Почему нет бензина"),
    "/talony":            ("🎫", "Бензин по талонам"),
    "/benzin-na-trasse":  ("🛣️", "Бензин на трассе"),
    "/gde-dizel":         ("🛢️", "Где найти дизель"),
    "/crisis":            ("🔥", "Прогноз кризиса"),
    "/attacks":           ("💥", "Хроника ударов"),
    "/refineries":        ("🏭", "Список НПЗ · все заводы"),
    "/karta-benzina-krym": ("🗺️", "Карта бензина Крым"),
    "/karta-bpla":          ("📡", "Карта БПЛА"),
    "/help":              ("❓", "Как пользоваться"),
}

# Карточки хаба /analytics: url -> (заголовок, описание, обложка|None).
# Обложка None → карточка без картинки (сгенерить кавер через Codex → добавить путь).
HUB = {
    "/crimea":     ("Дефицит бензина в Крыму", "Ситуация на АЗС Крыма: почему нет топлива, какие заправки работают, цены и ограничения на продажу", "/assets/analytics-crimea-generated.png"),
    "/krasnodar":  ("Дефицит бензина в Краснодаре", "Топливная ситуация в Краснодарском крае: закрытые АЗС, очереди, цены и причины дефицита", "/assets/analytics-krasnodar-generated.png"),
    "/moskva":     ("Дефицит бензина в Москве", "Очереди на заправках, лимиты по сетям, цены и когда закончится дефицит в столице", "/assets/analytics-moskva-generated.png"),
    "/raketnaya-opasnost-volgograd": ("Ракетная опасность: Волгоград", "Что означают сигналы воздушной тревоги и ракетной опасности в Волгограде и области, чем отличаются, где смотреть обстановку по региону", None),
    "/raketnaya-opasnost-ulyanovsk": ("Ракетная опасность: Ульяновск", "Сигналы воздушной тревоги и ракетной опасности в Ульяновске: что означают, что такое отбой, где следить за обстановкой по региону", None),
    "/raketnaya-opasnost-kazan":     ("Ракетная опасность: Казань", "Воздушная тревога и ракетная опасность в Казани и Татарстане: разбор сигналов ГО и карта-радар обстановки по региону", None),
    "/raketnaya-opasnost-omsk":      ("Ракетная опасность: Омск", "Сигналы воздушной тревоги и ракетной опасности в Омске и области: что означают, что такое отбой, где смотреть обстановку по региону", None),
    "/raketnaya-opasnost-cheboksary": ("Ракетная опасность: Чебоксары", "Воздушная тревога и ракетная опасность в Чебоксарах и Чувашии: разбор сигналов ГО и карта-радар обстановки по региону", None),
    "/raketnaya-opasnost-moskovskaya-oblast": ("Ракетная опасность: Московская область", "Сигналы воздушной тревоги и ракетной опасности в Московской области: что означают, чем отличаются, где следить за обстановкой по региону", None),
    "/raketnaya-opasnost-penza":     ("Ракетная опасность: Пенза", "Воздушная тревога и ракетная опасность в Пензе и области: что означают сигналы ГО, что такое отбой, где смотреть обстановку", None),
    "/raketnaya-opasnost-samara":    ("Ракетная опасность: Самара", "Сигналы воздушной тревоги и ракетной опасности в Самаре и области: разбор, отбой и карта-радар обстановки по региону", None),
    "/deficit":    ("Почему нет бензина в России", "Причины дефицита топлива: атаки на НПЗ, экспортный отток, логистические сбои. Когда закончится кризис", "/assets/analytics-deficit-generated.png"),
    "/talony":     ("Бензин по талонам", "Где действуют талоны и лимиты, чем отличаются, как получить топливо в Крыму, Москве и регионах", "/assets/analytics-talony-generated.png"),
    "/benzin-na-trasse": ("Бензин на трассе", "Где заправиться в пути во время дефицита: как найти рабочую АЗС на федеральной трассе, что с наличием АИ-95/92 по маршруту", None),
    "/gde-dizel":  ("Где найти дизель", "Наличие дизельного топлива на АЗС во время дефицита: где смотреть ДТ, чем ситуация с дизелем отличается от бензина, очереди и лимиты", None),
    "/crisis":     ("Топливный кризис 2026", "Полная хроника кризиса: от первых ударов до дефицита. Региональные последствия и меры правительства", "/assets/analytics-crisis-generated.png"),
    "/attacks":    ("Хроника ударов по НПЗ", "Все атаки БПЛА на нефтеперерабатывающие заводы: даты, масштаб повреждений, текущий статус", "/assets/analytics-attacks-generated.png"),
    "/refineries": ("Список НПЗ России", "Полная база нефтеперерабатывающих заводов: мощность, загрузка, статус после атак, география", "/assets/analytics-refineries-generated.png"),
    "/karta-benzina-krym": ("Карта бензина в Крыму", "Интерактивная карта наличия топлива: 90+ АЗС Крыма, статус сетей АТАН и ТЭС, лимиты, цены и очереди онлайн", "/assets/analytics-karta-benzina-krym-generated.png"),
    "/karta-bpla": ("Карта БПЛА и тревог", "Карта-радар угроз БПЛА и ракет по регионам России: воздушная тревога, ракетная опасность, отбой — онлайн, оценка по OSINT", "/assets/analytics-karta-bpla-generated.png"),
}

TOP_URLS   = {u for u, _, _ in TOP + TOP_TAIL}
HIDE_TYPES = {"object"}  # /npz/* — только через /refineries, десятки заводов в меню/хабе не льём


def load_reg():
    rows = []
    for line in REG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def label_for(url, primary_kw):
    return LABELS.get(url, ("📄", (primary_kw or url).capitalize()))


def ordered_pages(rows):
    """Все видимые live-страницы в порядке групп → как в реестре."""
    out = []
    for _title, types in GROUPS:
        for r in rows:
            if (r.get("status", "live") == "live"
                    and r.get("type") in types
                    and r["url"] not in TOP_URLS
                    and r.get("type") not in HIDE_TYPES):
                out.append(r)
    return out


# ---- 1) news-nav на лендингах (сгруппированная выпадашка) ----
NAV_RE = re.compile(r'<nav class="news-nav">.*?</nav>', re.DOTALL)


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


# ---- 1b) единый брендированный футер на SEO-лендингах + /analytics ----
FOOTER_HTML = ('  <footer class="news-footer">\n'
               '    <div class="news-footer-inner">\n'
               '      <p>Топливный фронт РФ · <a href="/">🗺️ Карта НПЗ</a> · OSINT-дашборд · '
               '<span class="mono">npz-tactical-map.vercel.app</span></p>\n'
               '      <p class="footer-disc">Не является официальной информацией. Данные из открытых источников.</p>\n'
               '    </div>\n'
               '  </footer>\n')
FOOTER_RE = re.compile(r'[ \t]*<footer class="news-footer">.*?</footer>\n?', re.DOTALL)
FOOTER_SKIP = {"radar.html"}  # тикер живых сводок, не SEO-футер — не трогаем


def apply_footer(html, fname):
    if fname in FOOTER_SKIP:
        return html
    if FOOTER_RE.search(html):
        return FOOTER_RE.sub(FOOTER_HTML, html, count=1)
    if "</main>" in html:
        return html.replace("</main>", "</main>\n\n" + FOOTER_HTML, 1)
    return html


# ---- 2) дропдаун на ГЛАВНОЙ (index.html, плоский список) ----
INDEX_MENU_RE = re.compile(r'(<div class="tab-dropdown-menu">)(.*?)(</div>)', re.DOTALL)


def build_index_menu(rows):
    lines = ["\n"]
    for r in ordered_pages(rows):
        emoji, lab = label_for(r["url"], r.get("primary_kw"))
        lines.append(f'            <a href="{r["url"]}">{emoji} {lab}</a>\n')
    return "".join(lines) + "          "


# ---- 2c) мобильный drawer в radar.html — плоский список «Аналитика» (по маркерам) ----
DRAWER_RE = re.compile(r'(<!-- DRAWER-ANALYTICS:START -->)(.*?)(<!-- DRAWER-ANALYTICS:END -->)', re.DOTALL)
DRAWER_SKIP = {"/help"}  # /help закреплён в группе «Разделы» drawer'а — не дублируем в «Аналитике»


def build_drawer_analytics(rows):
    lines = ["\n"]
    for r in ordered_pages(rows):
        if r["url"] in DRAWER_SKIP:
            continue
        emoji, lab = label_for(r["url"], r.get("primary_kw"))
        lines.append(f'      <a class="ndp-item" href="{r["url"]}">{emoji} {lab}</a>\n')
    return "".join(lines) + "      "


# ---- 2b) «Свежее»-чип на ГЛАВНОЙ (в status-strip → .ss-nav) ----
FRESH_RE  = re.compile(r'<!-- FRESH:START -->.*?<!-- FRESH:END -->', re.DOTALL)
SSNAV_RE  = re.compile(r'(<nav class="ss-nav"[^>]*>)')

FRESH_TYPES = {"region", "explainer", "forecast", "tool"}  # не reference/object — те не «свежий контент»


def newest_page(rows):
    # «новейшая» = последняя добавленная в реестр live-страница из контентных типов
    cands = [r for r in rows if r.get("status", "live") == "live"
             and r.get("type") in FRESH_TYPES and r["url"] not in TOP_URLS]
    return cands[-1] if cands else None

def build_fresh_chip(rows):
    r = newest_page(rows)
    if not r:
        return "<!-- FRESH:START --><!-- FRESH:END -->"
    _, lab = label_for(r["url"], r.get("primary_kw"))
    return ('<!-- FRESH:START --><a class="ss-src ss-fresh" href="%s" '
            'style="background:var(--teal,#12a594);color:#fff;font-weight:700;border-radius:8px">'
            '🆕 Новое: %s →</a><!-- FRESH:END -->') % (r["url"], lab)


# ---- 3) каталог-хаб /analytics (маркеры) ----
HUB_RE = re.compile(r'(<!-- ANALYTICS-CARDS:START -->)(.*?)(<!-- ANALYTICS-CARDS:END -->)', re.DOTALL)


def build_hub(rows):
    cards = ["\n"]
    for r in ordered_pages(rows):
        url = r["url"]
        title, desc, cover = HUB.get(url, (label_for(url, r.get("primary_kw"))[1], r.get("primary_kw", ""), None))
        # ponytail: alt = заголовок карточки (осмысленный, не decorative) — было alt="" на всех обложках
        img = f'\n        <img class="card-cover" src="{cover}" alt="{title}" loading="lazy">' if cover else ""
        cards.append(
            f'      <a href="{url}" class="analytics-card">{img}\n'
            f'        <div class="card-body">\n'
            f'          <h2>{title}</h2>\n'
            f'          <p>{desc}</p>\n'
            f'          <div class="card-meta">→ Читать</div>\n'
            f'        </div>\n'
            f'      </a>\n\n'
        )
    return "".join(cards) + "      "


def main():
    rows = load_reg()
    changed = 0

    # 1) news-nav + футер на всех лендингах, у которых он есть (авто-обнаружение —
    # не забыть добавить в список больше нельзя); news/*.html — архив сводок.
    landings = sorted(list(ROOT.glob("*.html")) + list(ROOT.glob("npz/*.html")) + list(ROOT.glob("news/*.html")))
    for f in landings:
        if f.name == "index.html":
            continue
        html = f.read_text(encoding="utf-8")
        if '<nav class="news-nav">' not in html:
            continue
        current = "/" + str(f.relative_to(ROOT))[:-5]
        new = NAV_RE.sub(build_nav(rows, current), html, count=1)
        new = apply_footer(new, f.name)
        new = DRAWER_RE.sub(lambda m: m.group(1) + build_drawer_analytics(rows) + m.group(3), new, count=1)
        if new != html:
            f.write_text(new, encoding="utf-8"); changed += 1; print("nav/footer updated", f.relative_to(ROOT))

    # 2) главная — дропдаун (⚠️ фронтенд-ядро, коммит под ALLOW_FRONTEND_RELEASE=1)
    idx = ROOT / "index.html"
    if idx.exists():
        html = idx.read_text(encoding="utf-8")
        new, n = INDEX_MENU_RE.subn(lambda m: m.group(1) + build_index_menu(rows) + m.group(3), html, count=1)
        if n == 0:
            print("!! no tab-dropdown-menu in index.html")
        # «Свежее»-чип: обновить между маркерами, либо вставить первым в .ss-nav
        chip = build_fresh_chip(rows)
        if FRESH_RE.search(new):
            new = FRESH_RE.sub(chip, new, count=1)
        elif SSNAV_RE.search(new):
            new = SSNAV_RE.sub(lambda m: m.group(1) + "\n        " + chip, new, count=1)
        else:
            print("!! no .ss-nav in index.html (chip skipped)")
        if new != html:
            idx.write_text(new, encoding="utf-8"); changed += 1; print("index.html dropdown + fresh chip updated")

    # 3) хаб /analytics — сетка карточек (по маркерам)
    hub = ROOT / "analytics.html"
    if hub.exists():
        html = hub.read_text(encoding="utf-8")
        new, n = HUB_RE.subn(lambda m: m.group(1) + build_hub(rows) + m.group(3), html, count=1)
        if n == 0:
            print("!! no ANALYTICS-CARDS markers in analytics.html")
        elif new != html:
            hub.write_text(new, encoding="utf-8"); changed += 1; print("analytics.html hub updated")

    print(f"done, {changed} files changed")


if __name__ == "__main__":
    main()
