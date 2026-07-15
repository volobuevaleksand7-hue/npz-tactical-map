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
  region → Регионы · region + /raketnaya-opasnost-* → свёрнутый блок «Ракетная опасность» ·
  explainer → Топливо · forecast → Прогноз · reference → Справочники · tool → Карты ·
  object(/npz/*) → скрыт, только через /refineries.
"""
import json, re, pathlib, hashlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
REG  = ROOT / "data" / "seo-topics.jsonl"

# Верхний уровень (порядок важен): url, emoji, label
TOP      = [("/", "🗺️", "Карта НПЗ"), ("/news", "📰", "Сводки"), ("/radar", "📡", "Радар БПЛА")]
TOP_TAIL = [("/sources", "📚", "Источники")]

ROCKET_PREFIX = "/raketnaya-opasnost-"


def is_rocket(r):
    return r["url"].startswith(ROCKET_PREFIX)


# Группы выпадашки: (заголовок, предикат(row)->bool, collapse). Порядок = порядок в меню и на хабе.
# collapse=True → группа рисуется свёрнутым <details> (город-лонгтейлы не раздувают меню).
GROUPS = [
    ("Регионы",            lambda r: r.get("type") == "region" and not is_rocket(r), False),
    ("Ракетная опасность", is_rocket,                                                True),
    ("Топливо",            lambda r: r.get("type") == "explainer",                   False),
    ("Прогноз",            lambda r: r.get("type") == "forecast",                    False),
    ("Справочники",        lambda r: r.get("type") == "reference",                   False),
    ("Карты",              lambda r: r.get("type") == "tool",                        False),
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
    "/volna-dronov":      ("🛩", "Волна дронов сейчас"),
    "/karta-benzina-krym": ("🗺️", "Карта бензина Крым"),
    "/karta-bpla":          ("📡", "Карта БПЛА"),
    "/karta-azs":           ("⛽", "Карта АЗС"),
    "/azs-ryadom":          ("📍", "АЗС рядом со мной"),
    "/help":              ("❓", "Как пользоваться"),
    "/metodologiya":      ("🔬", "Методология"),
    # без записи здесь label_for берёт SEO-ключ и делает .capitalize() — а он гасит все
    # остальные заглавные («удары по азовскому морю» → «Удары по азовскому морю»)
    "/udary-azovskoe-more":  ("💥", "Удары по Азовскому морю"),
    "/tankery-azovskoe-more": ("🚢", "Танкеры в Азовском море"),
    "/vozmozhen-li-golod":   ("🌾", "Будет ли голод в России"),
    "/udary-po-tankeram":    ("🚢", "Удары по танкерам теневого флота"),
}

# Карточки хаба /analytics: url -> (заголовок, описание).
# Обложка НЕ прописывается руками: build_hub берёт /assets/analytics-<slug>-generated.png,
# если файл существует (cover_for). Сгенерил кавер через Codex в это имя → карточка сама
# его подхватит; нет файла → карточка без картинки (без битых <img>).
HUB = {
    "/crimea":     ("Дефицит бензина в Крыму", "Ситуация на АЗС Крыма: почему нет топлива, какие заправки работают, цены и ограничения на продажу"),
    "/krasnodar":  ("Дефицит бензина в Краснодаре", "Топливная ситуация в Краснодарском крае: закрытые АЗС, очереди, цены и причины дефицита"),
    "/moskva":     ("Дефицит бензина в Москве", "Очереди на заправках, лимиты по сетям, цены и когда закончится дефицит в столице"),
    "/raketnaya-opasnost-volgograd": ("Ракетная опасность: Волгоград", "Что означают сигналы воздушной тревоги и ракетной опасности в Волгограде и области, чем отличаются, где смотреть обстановку по региону"),
    "/raketnaya-opasnost-ulyanovsk": ("Ракетная опасность: Ульяновск", "Сигналы воздушной тревоги и ракетной опасности в Ульяновске: что означают, что такое отбой, где следить за обстановкой по региону"),
    "/raketnaya-opasnost-kazan":     ("Ракетная опасность: Казань", "Воздушная тревога и ракетная опасность в Казани и Татарстане: разбор сигналов ГО и карта-радар обстановки по региону"),
    "/raketnaya-opasnost-omsk":      ("Ракетная опасность: Омск", "Сигналы воздушной тревоги и ракетной опасности в Омске и области: что означают, что такое отбой, где смотреть обстановку по региону"),
    "/raketnaya-opasnost-cheboksary": ("Ракетная опасность: Чебоксары", "Воздушная тревога и ракетная опасность в Чебоксарах и Чувашии: разбор сигналов ГО и карта-радар обстановки по региону"),
    "/raketnaya-opasnost-moskovskaya-oblast": ("Ракетная опасность: Московская область", "Сигналы воздушной тревоги и ракетной опасности в Московской области: что означают, чем отличаются, где следить за обстановкой по региону"),
    "/raketnaya-opasnost-penza":     ("Ракетная опасность: Пенза", "Воздушная тревога и ракетная опасность в Пензе и области: что означают сигналы ГО, что такое отбой, где смотреть обстановку"),
    "/raketnaya-opasnost-samara":    ("Ракетная опасность: Самара", "Сигналы воздушной тревоги и ракетной опасности в Самаре и области: разбор, отбой и карта-радар обстановки по региону"),
    "/deficit":    ("Почему нет бензина в России", "Причины дефицита топлива: атаки на НПЗ, экспортный отток, логистические сбои. Когда закончится кризис"),
    "/talony":     ("Бензин по талонам", "Где действуют талоны и лимиты, чем отличаются, как получить топливо в Крыму, Москве и регионах"),
    "/benzin-na-trasse": ("Бензин на трассе", "Где заправиться в пути во время дефицита: как найти рабочую АЗС на федеральной трассе, что с наличием АИ-95/92 по маршруту"),
    "/gde-dizel":  ("Где найти дизель", "Наличие дизельного топлива на АЗС во время дефицита: где смотреть ДТ, чем ситуация с дизелем отличается от бензина, очереди и лимиты"),
    "/crisis":     ("Топливный кризис 2026", "Полная хроника кризиса: от первых ударов до дефицита. Региональные последствия и меры правительства"),
    "/attacks":    ("Хроника ударов по НПЗ", "Все атаки БПЛА на нефтеперерабатывающие заводы: даты, масштаб повреждений, текущий статус"),
    "/refineries": ("Список НПЗ России", "Полная база нефтеперерабатывающих заводов: мощность, загрузка, статус после атак, география"),
    "/karta-benzina-krym": ("Карта бензина в Крыму", "Интерактивная карта наличия топлива: 90+ АЗС Крыма, статус сетей АТАН и ТЭС, лимиты, цены и очереди онлайн"),
    "/karta-bpla": ("Карта БПЛА и тревог", "Карта-радар угроз БПЛА и ракет по регионам России: воздушная тревога, ракетная опасность, отбой — онлайн, оценка по OSINT"),
    "/metodologiya": ("Методология оценки данных", "Как карта считает статусы НПЗ и АЗС, откуда берутся данные, как перепроверяются удары и как часто всё обновляется — открытая методология OSINT-агрегации"),
    "/azs-ryadom": ("АЗС рядом со мной", "Как найти ближайшую работающую заправку через геолокацию: бесплатная карта с фильтром «есть топливо» — честная OSINT-оценка по сети и региону, без фейковых статусов колонок"),
    "/volna-dronov": ("Волна дронов сейчас", "Идёт ли сейчас волна повышенной активности БПЛА: сколько городов и регионов затронуто, архив прошлых волн — оценка по открытому OSINT-мониторингу"),
}


def cover_for(url):
    """Обложка карточки по конвенции имени, только если файл реально есть на диске."""
    slug = url.strip("/").replace("/", "-")
    p = ROOT / "assets" / f"analytics-{slug}-generated.png"
    return f"/assets/{p.name}" if p.exists() else None

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


def pick(rows, pred):
    """Видимые live-страницы группы (по предикату), исключая верхний уровень и /npz/*."""
    return [r for r in rows
            if r.get("status", "live") == "live"
            and pred(r)
            and r["url"] not in TOP_URLS
            and r.get("type") not in HIDE_TYPES]


def short_label(url, primary_kw):
    """Подпись внутри блока «Ракетная опасность» — только город (префикс не дублируем)."""
    emoji, lab = label_for(url, primary_kw)
    return emoji, lab.replace("Ракетная опасность: ", "")


def ordered_pages(rows):
    """Все видимые live-страницы в порядке групп (плоско, для хаба/drawer)."""
    out = []
    for _title, pred, _collapse in GROUPS:
        out.extend(pick(rows, pred))
    return out


# ---- 1) news-nav на лендингах (сгруппированная выпадашка) ----
NAV_RE = re.compile(r'<nav class="news-nav">.*?</nav>', re.DOTALL)


def build_menu(rows, current):
    out = []
    for title, pred, collapse in GROUPS:
        picked = pick(rows, pred)
        if not picked:
            continue
        if collapse:
            # свёрнутый блок; авто-раскрыт, если открыта одна из его страниц
            op = " open" if any(r["url"] == current for r in picked) else ""
            out.append(f'            <details class="nav-drop-sub"{op}>')
            out.append(f'              <summary>🚀 {title}</summary>')
            for r in picked:
                _e, lab = short_label(r["url"], r.get("primary_kw"))
                cur = ' aria-current="page"' if r["url"] == current else ""
                out.append(f'              <a href="{r["url"]}"{cur}>📍 {lab}</a>')
            out.append('            </details>')
        else:
            out.append(f'            <div class="nav-drop-group">{title}</div>')
            for r in picked:
                emoji, lab = label_for(r["url"], r.get("primary_kw"))
                cur = ' aria-current="page"' if r["url"] == current else ""
                out.append(f'            <a href="{r["url"]}"{cur}>{emoji} {lab}</a>')
    # каталог-хаб последним — /analytics достижим, т.к. клик по самому «Аналитика ▾» теперь
    # открывает меню (preventDefault в nav-dropdown.js), а не переходит на хаб.
    out.append('            <a class="nav-drop-all" href="/analytics">📊 Все статьи · каталог →</a>')
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


# ---- 1a) единая шапка (лого + nav) на news-header-лендингах ----
# build-nav владеет всем <header class="news-header">, а не только внутренним <nav>:
# логотип больше не копируется руками (был разнобой — 86 страниц вели логотипом на /news,
# 4 на /). radar.html (topbar) и index.html (tab-бар) — свои шапки, их не трогаем (у них
# управляется только внутренний nav, ниже в main()).
HEADER_RE = re.compile(r'<header class="news-header">.*?</header>', re.DOTALL)
LOGO_HTML = ('      <a href="/" class="news-logo" title="На карту">\n'
             '        <span class="news-logo-icon">⛽</span>\n'
             '        <span class="news-logo-text">ТОПЛИВНЫЙ ФРОНТ РФ</span>\n'
             '      </a>')


SEARCH_BTN = ('<button type="button" class="nav-search-btn" id="searchOpenBtn" '
              'title="Поиск по сайту" aria-label="Поиск по сайту">🔍</button>')


def build_header(rows, current):
    return ('<header class="news-header">\n'
            '    <div class="news-header-inner">\n'
            + LOGO_HTML + '\n'
            '      ' + build_nav(rows, current) + '\n'
            '      ' + SEARCH_BTN + '\n'
            '    </div>\n'
            '  </header>')


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


# ---- 2) дропдаун на ГЛАВНОЙ (index.html) — сгруппирован по маркерам ----
# Маркеры (а не regex по <div>) потому что группы содержат вложенные </div>/<details>.
INDEX_MENU_RE = re.compile(r'(<!-- INDEX-MENU:START -->)(.*?)(<!-- INDEX-MENU:END -->)', re.DOTALL)


def build_index_menu(rows):
    lines = ["\n"]
    for title, pred, collapse in GROUPS:
        picked = pick(rows, pred)
        if not picked:
            continue
        if collapse:
            lines.append('            <details class="tdm-sub">\n')
            lines.append(f'              <summary>🚀 {title}</summary>\n')
            for r in picked:
                _e, lab = short_label(r["url"], r.get("primary_kw"))
                lines.append(f'              <a href="{r["url"]}">📍 {lab}</a>\n')
            lines.append('            </details>\n')
        else:
            lines.append(f'            <div class="tdm-group">{title}</div>\n')
            for r in picked:
                emoji, lab = label_for(r["url"], r.get("primary_kw"))
                lines.append(f'            <a href="{r["url"]}">{emoji} {lab}</a>\n')
    lines.append('            <a class="tdm-all" href="/analytics">📊 Все статьи · каталог →</a>\n')
    return "".join(lines) + "          "


# ---- 2c) мобильный drawer в radar.html — «Аналитика» (плоско + свёрнутая ракетная, по маркерам) ----
DRAWER_RE = re.compile(r'(<!-- DRAWER-ANALYTICS:START -->)(.*?)(<!-- DRAWER-ANALYTICS:END -->)', re.DOTALL)
DRAWER_SKIP = {"/help"}  # /help закреплён в группе «Разделы» drawer'а — не дублируем в «Аналитике»


def build_drawer_analytics(rows):
    lines = ["\n"]
    for _title, pred, collapse in GROUPS:
        picked = [r for r in pick(rows, pred) if r["url"] not in DRAWER_SKIP]
        if not picked:
            continue
        if collapse:
            lines.append('      <details class="ndp-sub">\n')
            lines.append('        <summary class="ndp-item">🚀 Ракетная опасность</summary>\n')
            for r in picked:
                _e, lab = short_label(r["url"], r.get("primary_kw"))
                lines.append(f'        <a class="ndp-item ndp-subitem" href="{r["url"]}">📍 {lab}</a>\n')
            lines.append('      </details>\n')
        else:
            for r in picked:
                emoji, lab = label_for(r["url"], r.get("primary_kw"))
                lines.append(f'      <a class="ndp-item" href="{r["url"]}">{emoji} {lab}</a>\n')
    return "".join(lines) + "      "


# ---- 2b) «Свежее»-чип на ГЛАВНОЙ (в status-strip → .ss-nav) ----
FRESH_RE  = re.compile(r'<!-- FRESH:START -->.*?<!-- FRESH:END -->', re.DOTALL)
SSNAV_RE  = re.compile(r'(<nav class="ss-nav"[^>]*>)')

# 🆕-чип светит ТОЛЬКО статьи, фичи не светим (решение 15.07).
# reference нужен ради разборов (/udary-azovskoe-more, /udary-po-tankeram) — но в нём же лежат
# фича-страница и служебные разделы, тип их не различает → отсекаем поимённо ниже.
# tool = ВСЕ карты (/karta-bpla, /radar, /karta-azs, /gde-est-benzin…) = фичи → не светим.
# object = страницы НПЗ → не статьи.
# Свежесть = ПОРЯДОК СТРОК в реестре (дат в нём нет), TOP_URLS отсеиваются ниже.
FRESH_TYPES = {"region", "explainer", "forecast", "reference"}
FRESH_EXCLUDE = {"/volna-dronov", "/help", "/metodologiya"}  # лежат как reference, но не статьи


def newest_page(rows):
    # «новейшая» = последняя добавленная в реестр live-страница из контентных типов
    cands = [r for r in rows if r.get("status", "live") == "live"
             and r.get("type") in FRESH_TYPES
             and r["url"] not in TOP_URLS
             and r["url"] not in FRESH_EXCLUDE]
    return cands[-1] if cands else None

def build_fresh_chip(rows):
    r = newest_page(rows)
    if not r:
        return "<!-- FRESH:START --><!-- FRESH:END -->"
    _, lab = label_for(r["url"], r.get("primary_kw"))
    return ('<!-- FRESH:START --><a class="ss-src ss-fresh" href="%s" '
            'style="background:var(--teal,#12a594);color:#fff;font-weight:700;border-radius:8px">'
            '🆕 %s →</a><!-- FRESH:END -->') % (r["url"], lab)


# ---- 3) каталог-хаб /analytics (маркеры) ----
HUB_RE = re.compile(r'(<!-- ANALYTICS-CARDS:START -->)(.*?)(<!-- ANALYTICS-CARDS:END -->)', re.DOTALL)


def build_hub(rows):
    cards = ["\n"]
    for r in ordered_pages(rows):
        url = r["url"]
        title, desc = HUB.get(url, (label_for(url, r.get("primary_kw"))[1], r.get("primary_kw", "")))
        cover = cover_for(url)  # обложка по конвенции имени, только если файл есть на диске
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


# ---- 4) cache-busting ассетов в index.html ----
# Лендинги штампует gen-news.py (?v=md5[:8]); index.html их не касался → у вернувшихся
# посетителей висел кэш styles.css/app.js и правки шапки/меню не доезжали. Штампуем тут,
# на каждом regenerate — само-заживает: правка styles.css → новый хэш → браузер перекачает.
# опциональный ведущий слэш: index.html линкует "styles.css", лендинги — "/styles.css".
ASSET_RE = re.compile(r'(href|src)="(/?)(styles\.css|news\.css|app\.js|nav-dropdown\.js|search\.css|search\.js|vpn-nudge\.js)(\?v=[0-9a-f]+)?"')


# ---- 4a) единый инжект поиска (search.css/search.js) в <head> на всех страницах ----
# build-nav — единственный владелец: добавил страницу → поиск на ней есть автоматически.
# Идемпотентно (если /search.js уже линкован — не трогаем; stamp_assets потом навесит ?v).
SEARCH_HEAD = ('  <link rel="stylesheet" href="/search.css">\n'
               '  <script defer src="/search.js"></script>\n')


def ensure_search_assets(html):
    if '/search.js' in html:
        return html
    if '</head>' in html:
        return html.replace('</head>', SEARCH_HEAD + '</head>', 1)
    return html


# ---- 4b) единый инжект VPN-баннера (vpn-nudge.js) на всех статических страницах ----
# build-nav — единственный владелец: добавил страницу → баннер на ней есть автоматически и
# переживает любой regenerate (раньше баннер вставляли вручную → рутины его затирали при
# пересборке news/SEO). Идемпотентно. Карту (app.js) НЕ трогаем — там баннер уже в попапах.
VPN_SCRIPT_TAG = '  <script defer src="/vpn-nudge.js"></script>\n'
# app.js ЗАГРУЖЕН как скрипт (карта) — не по упоминанию в комменте (radar пишет «app.js initMobile»).
APP_JS_LOADED = re.compile(r'src="[^"]*app\.js')


def ensure_vpn_asset(html):
    if 'vpn-nudge.js' in html or APP_JS_LOADED.search(html):
        return html
    if '</body>' in html:
        return html.replace('</body>', VPN_SCRIPT_TAG + '</body>', 1)
    return html


def stamp_assets(html):
    def repl(m):
        attr, slash, fname = m.group(1), m.group(2), m.group(3)
        p = ROOT / fname
        if not p.exists():
            return m.group(0)
        h = hashlib.md5(p.read_bytes()).hexdigest()[:8]
        return f'{attr}="{slash}{fname}?v={h}"'
    return ASSET_RE.sub(repl, html)


# ---- 5) единая клик-выпадашка «Аналитика» на лендингах ----
# Инлайн-JS дропдауна дрейфовал по 30+ страницам (4 разных копии), а сводки/npz были вовсе
# без JS (hover-only → не открыть на тач-планшетах >768). Теперь один shared /nav-dropdown.js
# (клик-фиксация .open + клик-вне/Esc, зеркалит index.html). Здесь вырезаем СТАРЫЕ инлайн-
# конструкции дропдауна (тему/SW/прочее в том же <script> НЕ трогаем) и линкуем shared-скрипт.
# ponytail: регэкспы бьют по 4 известным формам инлайна; генераторы их больше не эмитят, 5-я не заведётся.
DROP_FOREACH_RE = re.compile(
    r"[ \t]*(?://[^\n]*\n[ \t]*)?document\.querySelectorAll\((['\"])\.nav-dropdown > a\1\)"
    r"\.forEach\(.*?\}\);\s*\}\);\n?",
    re.DOTALL)
DROP_OUTSIDE_RE = re.compile(
    r"[ \t]*(?://[^\n]*\n[ \t]*)?document\.addEventListener\((['\"])click\1,\s*function\(e\)\s*\{\s*"
    r"if\s*\(!e\.target\.closest\((['\"])\.nav-dropdown\2\)\).*?\}\);\n?",
    re.DOTALL)
DROP_SCRIPT_TAG = '  <script defer src="/nav-dropdown.js"></script>\n'


def wire_dropdown(html):
    """Срезать старый инлайн-JS дропдауна и вставить shared /nav-dropdown.js перед </body>."""
    html = DROP_FOREACH_RE.sub("", html)
    html = DROP_OUTSIDE_RE.sub("", html)
    if "/nav-dropdown.js" not in html and "</body>" in html:
        html = html.replace("</body>", DROP_SCRIPT_TAG + "</body>", 1)
    return html


def main():
    rows = load_reg()
    changed = 0
    # «Свежее»-чип считаем один раз и применяем ко ВСЕМ страницам с маркерами (не только к
    # index): у karta-azs / karta-azs-lab свои FRESH-маркеры, и раньше их не обновлял никто —
    # чип там застревал навсегда.
    fresh_chip = build_fresh_chip(rows)

    # 1) news-nav + футер на всех лендингах, у которых он есть (авто-обнаружение —
    # не забыть добавить в список больше нельзя); news/*.html — архив сводок,
    # volna-dronov/*.html — вечные снимки волн (agents/gen-wave.py), тот же паттерн.
    landings = sorted(list(ROOT.glob("*.html")) + list(ROOT.glob("npz/*.html"))
                       + list(ROOT.glob("news/*.html")) + list(ROOT.glob("volna-dronov/*.html")))
    for f in landings:
        if f.name == "index.html":
            continue
        html = f.read_text(encoding="utf-8")
        # обрабатываем страницу, если есть ЛЮБОЙ маркер: news-header (build-nav наполнит
        # шапку целиком — так новая страница = пустой <header class="news-header"></header>)
        # или news-nav без header (radar — только внутренний nav).
        if '<nav class="news-nav">' not in html and '<header class="news-header">' not in html:
            continue
        current = "/" + str(f.relative_to(ROOT))[:-5]
        # news-header-лендинги → build-nav владеет всей шапкой (лого + nav);
        # radar (topbar, без news-header) → только внутренний nav, как раньше.
        if '<header class="news-header">' in html:
            new = HEADER_RE.sub(build_header(rows, current), html, count=1)
        else:
            new = NAV_RE.sub(build_nav(rows, current), html, count=1)
        new = apply_footer(new, f.name)
        new = DRAWER_RE.sub(lambda m: m.group(1) + build_drawer_analytics(rows) + m.group(3), new, count=1)
        new = wire_dropdown(new)  # срезать старый инлайн-JS дропдауна + линковать shared /nav-dropdown.js
        new = ensure_search_assets(new)  # search.css/search.js в <head> (поиск на всех страницах)
        new = ensure_vpn_asset(new)  # vpn-nudge.js перед </body> (VPN-баннер на всех статических страницах)
        new = stamp_assets(new)  # освежить ?v на styles.css/news.css/nav-dropdown.js — иначе правка не доедет до вернувшихся
        if new != html:
            f.write_text(new, encoding="utf-8"); changed += 1; print("nav/footer updated", f.relative_to(ROOT))

    # 1b) «Свежее»-чип на НЕ-index страницах с маркерами. Отдельным проходом, потому что цикл
    # выше пропускает страницы без news-nav/news-header (karta-azs* — карты, у них topbar),
    # а FRESH-маркеры у них есть → чип там застревал навсегда (был /gde-est-benzin).
    for f in landings:
        if f.name == "index.html":
            continue
        html = f.read_text(encoding="utf-8")
        if not FRESH_RE.search(html):
            continue
        new = FRESH_RE.sub(fresh_chip, html, count=1)
        # эти же страницы цикл выше не штампует → их ?v протухал молча (karta-azs тянула
        # старый vpn-nudge). Штампуем здесь, иначе правки ассетов до них не доезжают.
        new = stamp_assets(new)
        if new != html:
            f.write_text(new, encoding="utf-8"); changed += 1; print("fresh chip + asset ver updated", f.relative_to(ROOT))

    # 2) главная — дропдаун (⚠️ фронтенд-ядро, коммит под ALLOW_FRONTEND_RELEASE=1)
    idx = ROOT / "index.html"
    if idx.exists():
        html = idx.read_text(encoding="utf-8")
        new, n = INDEX_MENU_RE.subn(lambda m: m.group(1) + build_index_menu(rows) + m.group(3), html, count=1)
        if n == 0:
            print("!! no tab-dropdown-menu in index.html")
        # «Свежее»-чип: обновить между маркерами, либо вставить первым в .ss-nav
        chip = fresh_chip
        if FRESH_RE.search(new):
            new = FRESH_RE.sub(chip, new, count=1)
        elif SSNAV_RE.search(new):
            new = SSNAV_RE.sub(lambda m: m.group(1) + "\n        " + chip, new, count=1)
        else:
            print("!! no .ss-nav in index.html (chip skipped)")
        # мобильный drawer «Аналитика» — из того же реестра (был hand-maintained → дрейфовал)
        new = DRAWER_RE.sub(lambda m: m.group(1) + build_drawer_analytics(rows) + m.group(3), new, count=1)
        new = ensure_search_assets(new)  # search.css/search.js в <head>
        new = stamp_assets(new)  # ?v=<хэш> на styles.css/app.js — иначе кэш прячет правки шапки
        if new != html:
            idx.write_text(new, encoding="utf-8"); changed += 1; print("index.html dropdown + drawer + fresh chip + asset ver updated")

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
