#!/usr/bin/env python3
"""Генератор «Волна дронов»: живая страница /volna-dronov + вечные снимки событий.

Читает data/wave-state.json (текущий статус, пишет agents/wave-detect.py) и
data/wave-events.json (append-only архив волн) и строит:
  - volna-dronov.html            — evergreen LIVE-страница (hero фетчит
    wave-state.json КЛИЕНТСКИ, как radar.html фетчит RADAR_URL, cache:"no-store";
    ниже — серверная лента архива волн)
  - volna-dronov/<id>.html        — вечный снимок КАЖДОГО события архива
    (id = "YYYY-MM-DD-HHMM", как в wave-events.json)

Текст статьи — детерминированный шаблон из фактов радара (ТЗ §5), БЕЗ LLM:
нейтральный OSINT-тон, без атрибуции сторон и алармизма, обязательный дисклеймер.

Обложка — через agents/wave_cover.py (пишет другой агент, контракт ТЗ §3):
build_card(event, out_dir) -> {"inline_svg": str, "png_path": str|None}.
Пока модуля нет — try/except на fallback-плашку; сам вызов не комментировать.

Использование (без аргументов — идемпотентная пересборка всего):
  python3 agents/gen-wave.py

Публикация (делает крон/детектор): после генерации — build-nav.py (меню +
шапка + vpn-nudge на volna-dronov.html И volna-dronov/*.html — оба пути в
landings-glob build-nav.py) → check-ia.py → sitemap.xml/news-sitemap.xml
(разово руками при первом релизе слайса, дальше — тоже сюда добавить в
generate при желании; MVP руками, YAGNI на авто-sitemap) → commit → push.

ponytail: один файл на весь слайс (генератор + шаблоны), без ORM/CMS —
данных мало (архив волн растёт медленно, ≤6ч кулдаун), plain-string
шаблоны с token-replace дешевле Jinja для двух HTML-страниц.
"""
import datetime
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://npz-tactical-map.vercel.app"
STATE_PATH = ROOT / "data" / "wave-state.json"
EVENTS_PATH = ROOT / "data" / "wave-events.json"
OUT_LIVE = ROOT / "volna-dronov.html"
OUT_DIR = ROOT / "volna-dronov"
BOT = "https://t.me/BPLAlert_bot"  # ⚠️ именно этот бот, НЕ @fuelalert

RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]

DISCLAIMER_TEXT = ("Данные — предварительно, по открытым источникам "
                    "(мониторинговые чаты и каналы); это не официальная "
                    "информация. Следите за официальными оповещениями МЧС и "
                    "региональных властей.")


# ───────────────────────── helpers: даты/время (РУ-формат, МСК) ─────────────────────────

def plural(n, one, few, many):
    """Русское склонение по числу: 1 город / 2 города / 5 городов."""
    n = abs(int(n)); a = n % 10; b = n % 100
    if a == 1 and b != 11:
        return one
    if 2 <= a <= 4 and not (12 <= b <= 14):
        return few
    return many


def cities_n(n):
    return f"{n} {plural(n, 'город', 'города', 'городов')}"


def regions_n(n):
    return f"{n} {plural(n, 'регион', 'региона', 'регионов')}"


def regions_in(n):
    """Предложный: «в 1 регионе / в 4 регионах / в 11 регионах»."""
    return f"{n} {plural(n, 'регионе', 'регионах', 'регионах')}"


def punkt_n(n):
    return f"{n} {plural(n, 'населённый пункт', 'населённых пункта', 'населённых пунктов')}"


def punkt_in(n):
    """Предложный: «в 1 населённом пункте / в 5 населённых пунктах»."""
    return f"{n} {plural(n, 'населённом пункте', 'населённых пунктах', 'населённых пунктах')}"


def parse_iso(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def to_msk(d):
    return d.astimezone(datetime.timezone(datetime.timedelta(hours=3)))


def rus_date(d):
    """d — datetime/date или ISO/'YYYY-MM-DD' строка. Возвращает «12 июля 2026»."""
    if isinstance(d, str):
        d = parse_iso(d) if "T" in d else datetime.date.fromisoformat(d)
    return f"{d.day} {RU_MONTHS[d.month - 1]} {d.year}"


def rus_datetime_msk(iso_str):
    """ISO (UTC) -> «12 июля 2026, 22:00 МСК»."""
    d = to_msk(parse_iso(iso_str))
    return f"{rus_date(d)}, {d.hour:02d}:{d.minute:02d} МСК"


def time_of_day_msk(iso_str):
    h = to_msk(parse_iso(iso_str)).hour
    if h < 6:
        return "ночью"
    if h < 12:
        return "утром"
    if h < 18:
        return "днём"
    return "вечером"


def duration_str(started_iso, ended_iso):
    a = parse_iso(started_iso)
    b = parse_iso(ended_iso) if ended_iso else datetime.datetime.now(datetime.timezone.utc)
    total_min = max(0, int((b - a).total_seconds() // 60))
    h, m = divmod(total_min, 60)
    if h and m:
        return f"{h} ч {m} мин"
    if h:
        return f"{h} ч"
    return f"{m} мин"


def esc(s):
    return (str("" if s is None else s)
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def asset_ver(name):
    p = ROOT / name
    return hashlib.md5(p.read_bytes()).hexdigest()[:8] if p.exists() else "0"


def load_json(p, default):
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


SUMMARIES_PATH = ROOT / "data" / "wave-summaries.json"


def load_wave_summary(wave_id):
    """Загружает сводку итогов волны из wave-summaries.json, если есть."""
    summaries = load_json(SUMMARIES_PATH, {})
    return summaries.get(wave_id)


# ───────────────────────── обложка (agents/wave_cover.py, контракт ТЗ §3) ─────────────────────────

def build_cover(event_for_cover):
    """event_for_cover = {date, cities, regions, region_list, started_at}."""
    card = None
    try:
        import sys
        sys.path.insert(0, "agents")
        import wave_cover
        card = wave_cover.build_card(event_for_cover, str(ROOT / "assets"))
    except Exception:
        card = None  # ponytail: wave_cover.py ещё может не существовать — фолбэк ниже
    return cover_html(card)


def cover_html(card):
    if not card:
        return ('<div class="wave-cover-fallback">🛩<br>ВОЛНА ДРОНОВ'
                '</div>')  # ponytail: плейсхолдер до появления agents/wave_cover.py
    png = card.get("png_path")
    if png:
        p = pathlib.Path(png)
        try:
            url = "/" + str(p.relative_to(ROOT))
        except ValueError:
            url = "/" + p.name
        return f'<img class="wave-cover-img" src="{esc(url)}" alt="Волна дронов" loading="lazy">'
    return f'<div class="wave-cover-svg">{card.get("inline_svg", "")}</div>'


# ───────────────────────── общие блоки head/шапки/футера ─────────────────────────

CSS_BLOCK = """
    .landing-wrap{max-width:900px;margin:0 auto;padding:24px 20px 60px}
    .landing-hero{background:linear-gradient(135deg,rgba(210,58,46,.12),rgba(160,29,20,.08));border:1px solid rgba(210,58,46,.25);border-radius:16px;padding:32px 28px;margin-bottom:24px;position:relative;overflow:hidden}
    .landing-hero::before{content:"";position:absolute;top:-30px;right:-30px;width:120px;height:120px;background:radial-gradient(circle,rgba(210,58,46,.15),transparent 70%);border-radius:50%}
    .hero-label{display:inline-block;background:var(--red);color:#fff;font-family:var(--mono);font-size:10px;font-weight:800;letter-spacing:1.5px;padding:3px 10px;border-radius:6px;margin-bottom:12px}
    .hero-h{font-size:26px;font-weight:800;line-height:1.25;margin-bottom:10px}
    .hero-sub{font-size:14px;color:var(--ink-dim);line-height:1.6;max-width:680px;margin-bottom:4px}
    .map-cta{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;margin:14px 0 4px;padding:16px 22px;background:var(--red);color:#fff;font-weight:800;font-size:16px;border-radius:12px;text-decoration:none;box-shadow:0 6px 20px rgba(210,58,46,.3);transition:.15s}
    .map-cta:hover{transform:translateY(-2px);box-shadow:0 10px 28px rgba(210,58,46,.45)}
    .map-cta .mc-ico{font-size:22px}
    .map-cta.inline{margin:10px 0;background:var(--surface);color:var(--ink);border:1.5px solid var(--red);box-shadow:none}
    .map-cta.inline:hover{background:rgba(210,58,46,.08);transform:translateY(-1px)}
    .status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:16px}
    .status-card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;text-align:center}
    .status-card .val{font-family:var(--mono);font-size:20px;font-weight:800;color:var(--red)}
    .status-card .lbl{font-size:11px;color:var(--ink-dim);margin-top:4px}
    .section-h{font-size:20px;font-weight:800;margin:32px 0 14px;display:flex;align-items:center;gap:8px}
    .section-h .ico{font-size:22px}
    .lead-p{font-size:14px;line-height:1.7;color:var(--ink);margin-bottom:8px}
    .link-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin:16px 0}
    .link-card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;text-decoration:none;color:var(--ink);transition:.15s}
    .link-card:hover{border-color:var(--teal);transform:translateY(-1px);box-shadow:var(--shadow-sm)}
    .link-card .lc-h{font-weight:700;font-size:13px;margin-bottom:4px}
    .link-card .lc-d{font-size:11px;color:var(--ink-dim)}
    .osint-note{margin-top:32px;font-size:11px;color:var(--ink-dim);background:var(--surface2);padding:12px;border-radius:10px;border-left:3px solid var(--amber);line-height:1.6}
    .updated-line{font-family:var(--mono);font-size:11px;color:var(--ink-dim);margin-top:6px}
    .wave-region-chips{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0 4px}
    .wave-chip{background:var(--surface2);border:1px solid var(--line);border-radius:999px;padding:5px 12px;font-size:12px;font-weight:700;color:var(--ink)}
    .wave-cover-fallback{width:100%;max-width:420px;aspect-ratio:1200/630;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:6px;background:var(--surface2);border:1px dashed var(--line);border-radius:12px;font-weight:800;color:var(--ink-dim);margin:16px 0;font-size:14px;text-align:center}
    .wave-cover-img{width:100%;max-width:480px;border-radius:12px;margin:16px 0;display:block}
    .wave-cover-svg svg{width:100%;max-width:480px;border-radius:12px;margin:16px 0;display:block}
    .archive-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px;margin:16px 0 8px}
    .archive-card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px;text-decoration:none;color:var(--ink);transition:.15s;display:block}
    .archive-card:hover{border-color:var(--teal);transform:translateY(-1px);box-shadow:var(--shadow-sm)}
    .archive-card .ac-live{display:inline-block;background:var(--red);color:#fff;font-size:10px;font-weight:800;padding:2px 8px;border-radius:6px;margin-bottom:6px}
    .archive-card .ac-date{font-family:var(--mono);font-size:11px;color:var(--ink-dim);margin-bottom:6px}
    .archive-card .ac-h{font-weight:800;font-size:15px;margin-bottom:6px}
    .archive-card .ac-regions{font-size:12px;color:var(--ink-dim);line-height:1.5}
    .archive-empty{padding:20px;text-align:center;color:var(--ink-dim);background:var(--surface);border:1px dashed var(--line);border-radius:12px}
    .wave-summary-section{margin-top:24px;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:20px}
    .wave-summary-section .ws-head{font-size:16px;font-weight:800;margin-bottom:14px;display:flex;align-items:center;gap:8px}
    .wave-summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin-bottom:14px}
    .wave-summary-card{background:var(--surface2);border-radius:8px;padding:12px;text-align:center}
    .wave-summary-card .ws-val{font-family:var(--mono);font-size:18px;font-weight:800;color:var(--ink)}
    .wave-summary-card .ws-lbl{font-size:11px;color:var(--ink-dim);margin-top:3px}
    .wave-summary-strikes{margin-top:8px}
    .wave-summary-strike{background:var(--surface2);border-left:3px solid var(--red);border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:8px;font-size:13px;line-height:1.5}
    .wave-summary-strike .ws-city{font-weight:700}
    .wave-summary-strike .ws-cas{color:var(--red);font-weight:600}
    .wave-summary-sources{margin-top:12px;font-size:11px;color:var(--ink-dim)}
    .wave-summary-text{font-size:13px;line-height:1.6;color:var(--ink);margin:12px 0 0;padding:12px;background:var(--surface2);border-radius:8px}
"""

HEADER_HTML = """  <header class="news-header">
    <div class="news-header-inner">
      <a href="/" class="news-logo" title="На карту">
        <span class="news-logo-icon">⛽</span>
        <span class="news-logo-text">ТОПЛИВНЫЙ ФРОНТ РФ</span>
      </a>
      <nav class="news-nav"><!-- сгенерит agents/build-nav.py --></nav>
    </div>
  </header>"""

SUBSCRIBE_CTA = (f'<a class="map-cta inline" href="{BOT}" target="_blank" rel="noopener">'
                  f'<span class="mc-ico">🚨</span> Подписаться на оповещения о волнах в '
                  f'Telegram-боте →</a>')

LINK_GRID = """      <div class="link-grid">
        <a class="link-card" href="/radar"><div class="lc-h">📡 Радар угроз</div><div class="lc-d">Карта БПЛА и ракет по регионам в реальном времени</div></a>
        <a class="link-card" href="/karta-bpla"><div class="lc-h">🗺️ Карта БПЛА онлайн</div><div class="lc-d">Как читать карту тревог и угроз по регионам</div></a>
        <a class="link-card" href="/attacks"><div class="lc-h">💥 Хроника ударов</div><div class="lc-d">Архив подтверждённых атак БПЛА по НПЗ</div></a>
        <a class="link-card" href="/news"><div class="lc-h">📰 Сводки</div><div class="lc-d">Ежедневный архив мониторинга обстановки</div></a>
      </div>"""

FOOT_SCRIPTS = """  <script>
    const saved = localStorage.getItem('theme');
    if (saved) document.documentElement.dataset.theme = saved;
  </script>
  <script defer src="/nav-dropdown.js"></script>
  <script defer src="/vpn-nudge.js?v=__VPN_VER__"></script>
  <!-- ponytail: sub-nudge.js инертен без #map (arm() ищет getElementById('map')) — на этой
       странице подписку тянет статичный CTA-блок выше; скрипт подключён для консистентности
       include-паттерна карт-страниц (index.html), поведения не меняет. -->
  <script defer src="/sub-nudge.js?v=__SUB_VER__"></script>
</body>
</html>
"""


def head_common(title, desc, keywords, canonical_url, og_title, og_desc):
    return f"""<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <meta name="theme-color" content="#d23a2e">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}">
  <meta name="keywords" content="{esc(keywords)}">
  <meta name="robots" content="index, follow">
  <meta name="language" content="Russian">
  <link rel="canonical" href="{canonical_url}">

  <meta property="og:type" content="article">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:site_name" content="Топливный фронт РФ">
  <meta property="og:url" content="{canonical_url}">
  <meta property="og:title" content="{esc(og_title)}">
  <meta property="og:description" content="{esc(og_desc)}">
  <meta property="og:image" content="{SITE}/og-image.png">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{esc(og_title)}">
  <meta name="twitter:description" content="{esc(og_desc)}">
  <meta name="twitter:image" content="{SITE}/og-image.png">

  <script>window.va = window.va || function () {{ (window.vaq = window.vaq || []).push(arguments); }};</script>
  <script defer src="/_vercel/insights/script.js"></script>

  <link rel="stylesheet" href="/fonts.css">
  <link rel="stylesheet" href="/styles.css">
  <link rel="stylesheet" href="/news.css">
  <style>{CSS_BLOCK}</style>
  <script src="/metrika.js" async></script>
</head>
<body data-theme="light">
{HEADER_HTML}
  <main class="news-main">
    <div class="landing-wrap">
"""


def breadcrumb_jsonld(name, url):
    return f"""  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {{"@type": "ListItem", "position": 1, "name": "Главная", "item": "{SITE}/"}},
      {{"@type": "ListItem", "position": 2, "name": "Волна дронов", "item": "{SITE}/volna-dronov"}},
      {{"@type": "ListItem", "position": 3, "name": "{esc(name)}", "item": "{url}"}}
    ]
  }}
  </script>
"""


# ───────────────────────── лента архива (серверный рендер) ─────────────────────────

def render_archive_cards(events):
    if not events:
        return '<div class="archive-empty">Волн повышенной активности пока не зафиксировано.</div>'
    items = sorted(events, key=lambda e: e.get("started_at", ""), reverse=True)
    cards = []
    for ev in items:
        slug = ev.get("id", "")
        is_live = not ev.get("ended_at")
        badge = '<div class="ac-live">ИДЁТ СЕЙЧАС</div>' if is_live else ""
        region_list = ev.get("region_list") or []
        preview = ", ".join(region_list[:4])
        extra = len(region_list) - 4
        if extra > 0:
            preview += f" и ещё {extra}"
        dur = duration_str(ev.get("started_at"), ev.get("ended_at"))
        when = rus_datetime_msk(ev["started_at"]) if ev.get("started_at") else ""
        cards.append(
            f'<a class="archive-card" href="/volna-dronov/{esc(slug)}">'
            f'{badge}'
            f'<div class="ac-date">{esc(when)}</div>'
            f'<div class="ac-h">{cities_n(ev.get("peak_cities", 0))} · {regions_n(ev.get("peak_regions", 0))}</div>'
            f'<div class="ac-regions">{esc(preview)} · длительность {esc(dur)}</div>'
            f'</a>'
        )
    return '<div class="archive-grid">' + "".join(cards) + '</div>'


# ───────────────────────── /volna-dronov (evergreen live) ─────────────────────────

def build_live_page(state, events):
    active = bool(state.get("active"))
    if active:
        cover_event = {
            "date": (state.get("started_at") or "")[:10],
            "cities": state.get("cities"),
            "regions": state.get("regions"),
            "region_list": state.get("region_list") or [],
            "started_at": state.get("started_at"),
        }
        cover = build_cover(cover_event)
        active_title = (f'🛩 Волна дронов идёт прямо сейчас — {cities_n(state.get("cities", 0))} '
                         f'в {regions_in(state.get("regions", 0))}')
        chips = "".join(f'<span class="wave-chip">{esc(r)}</span>' for r in (state.get("region_list") or []))
        updated = f'Обновлено {rus_datetime_msk(state["updated_at"])}' if state.get("updated_at") else ""
        active_style, quiet_style = "", "display:none"
    else:
        cover, active_title, chips, updated = "", "", "", ""
        active_style, quiet_style = "display:none", ""
    # last_event: agents/wave-detect.py пишет объект {"date","event_id"} (не голую строку —
    # расходится с прозой ТЗ §2, код детектора канон); поддержим и строку на всякий случай.
    _last_ev = state.get("last_event")
    _last_ev_date = _last_ev.get("date") if isinstance(_last_ev, dict) else _last_ev
    last_event_txt = rus_date(_last_ev_date) if _last_ev_date else "нет данных"

    title = "Волна дронов сейчас — карта активности БПЛА в реальном времени"
    desc = ("Идёт ли сейчас волна дронов: сколько городов и регионов затронуто, где смотреть "
            "обстановку. Архив прошлых волн. Оценка по открытому OSINT-мониторингу.")
    keywords = "волна дронов сейчас, куда летят дроны, волна бпла онлайн, дроны над россией сейчас"
    canonical = f"{SITE}/volna-dronov"
    og_title = "Волна дронов сейчас — активность БПЛА по регионам России"
    og_desc = "Идёт ли волна дронов прямо сейчас: города, регионы, архив прошлых волн. OSINT-оценка."

    html = [head_common(title, desc, keywords, canonical, og_title, og_desc)]
    html.append(f"""      <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "WebPage",
    "name": "{esc(title)}",
    "url": "{canonical}",
    "description": "{esc(desc)}",
    "isPartOf": {{"@type": "WebSite", "name": "Топливный фронт РФ", "url": "{SITE}/"}}
  }}
  </script>
""")
    html.append(f"""
      <div class="landing-hero">
        <span class="hero-label">ВОЛНА ДРОНОВ · LIVE</span>
        <div id="waveActive" style="{active_style}">
          <h1 class="hero-h" id="waveTitle">{esc(active_title)}</h1>
          <p class="hero-sub">Оценка по открытым источникам (мониторинговые чаты и каналы), не официальное оповещение. Обновляется автоматически.</p>
          {cover}
          <div class="wave-region-chips" id="waveChips">{chips}</div>
          <div class="updated-line" id="waveUpdated">{esc(updated)}</div>
        </div>
        <div id="waveQuiet" style="{quiet_style}">
          <h1 class="hero-h">Крупных волн дронов сейчас не зафиксировано</h1>
          <p class="hero-sub">Последняя волна повышенной активности БПЛА: <b id="waveLastDate">{esc(last_event_txt)}</b>. Обстановка может меняться быстро — смотрите живой радар.</p>
        </div>
        <a class="map-cta" href="/radar"><span class="mc-ico">📡</span> Радар угроз в реальном времени →</a>
        <a class="map-cta inline" href="/karta-bpla"><span class="mc-ico">🗺️</span> Карта БПЛА онлайн →</a>
      </div>

      <h2 class="section-h"><span class="ico">🛩</span> Что такое «волна дронов»</h2>
      <p class="lead-p">Волной мы называем всплеск одновременной активности БПЛА сразу во многих городах и регионах — по данным из открытых источников: мониторинговых чатов и каналов. Это не прогноз и не официальное оповещение, а агрегированная оценка: цифры выше обновляются автоматически по мере поступления новых данных.</p>
      <p class="lead-p">{DISCLAIMER_TEXT}</p>

      <h2 class="section-h"><span class="ico">🔔</span> Узнавать о волнах первым</h2>
      <p class="lead-p">Чтобы не проверять страницу вручную, подпишитесь на Telegram-бота: он присылает оповещения об угрозе БПЛА и ракетной опасности по вашему региону.</p>
      {SUBSCRIBE_CTA}

      <h2 class="section-h"><span class="ico">🗂</span> Лента волн — архив</h2>
      {render_archive_cards(events)}

      <h2 class="section-h"><span class="ico">🔗</span> Смотрите также</h2>
{LINK_GRID}

      <div class="osint-note">
        <strong>⚠️ Дисклеймер:</strong> {DISCLAIMER_TEXT} Страница носит справочно-аналитический характер и не содержит рекомендаций к действию.
      </div>
    </div>
  </main>
""")
    html.append(FOOT_SCRIPTS.replace("__VPN_VER__", asset_ver("vpn-nudge.js")).replace("__SUB_VER__", asset_ver("sub-nudge.js")))
    return "".join(html)


# ───────────────────────── /volna-dronov/<id> (вечный снимок события) ─────────────────────────

def build_snapshot_page(ev):
    slug = ev["id"]
    cover_event = {
        "date": ev.get("date"),
        "cities": ev.get("peak_cities"),
        "regions": ev.get("peak_regions"),
        "region_list": ev.get("region_list") or [],
        "started_at": ev.get("started_at"),
    }
    cover = build_cover(cover_event)
    region_list = ev.get("region_list") or []
    regions_str = ", ".join(region_list)
    when = rus_datetime_msk(ev["started_at"]) if ev.get("started_at") else ""
    tod = time_of_day_msk(ev["started_at"]) if ev.get("started_at") else ""
    rdate = rus_date(ev["date"]) if ev.get("date") else ""
    dur = duration_str(ev.get("started_at"), ev.get("ended_at"))
    is_live = not ev.get("ended_at")
    status_label = "идёт сейчас" if is_live else "завершена"

    # ── итоги волны (wave-summaries.json) ──
    summary = load_wave_summary(slug)
    summary_html = ""
    if summary:
        cas = summary.get("casualties", {})
        strikes_html = ""
        for s in summary.get("strikes", []):
            d = s.get("destroyed", 0)
            de = s.get("dead", 0)
            inj = s.get("injured", 0)
            cas_str = ""
            parts = []
            if de:
                parts.append(f'<span class="ws-cas">{de} погиб.</span>')
            if inj:
                parts.append(f'<span class="ws-cas">{inj} ран.</span>')
            if parts:
                cas_str = " · ".join(parts)
            destroyed_str = f" — {d} {plural(d, 'дом разрушен', 'дома разрушено', 'домов разрушено')}" if d else ""
            strikes_html += (
                f'<div class="wave-summary-strike">'
                f'<span class="ws-city">📍 {esc(s.get("city", "?"))}</span>'
                f': {esc(s.get("target", ""))}{destroyed_str}'
                f'{(" · " + cas_str) if cas_str else ""}'
                f'</div>'
            )
        sources_str = ", ".join(summary.get("sources", [])) if summary.get("sources") else ""
        summary_html = f"""
      <section class="wave-summary-section">
        <div class="ws-head">📊 Итоги волны</div>
        <div class="wave-summary-grid">
          <div class="wave-summary-card"><div class="ws-val">{summary.get("total_drones", "?")}</div><div class="ws-lbl">Всего БПЛА</div></div>
          <div class="wave-summary-card"><div class="ws-val">{summary.get("shot_down", "?")}</div><div class="ws-lbl">Сбито</div></div>
          <div class="wave-summary-card"><div class="ws-val">{summary.get("reached_targets", "?")}</div><div class="ws-lbl">Нас. пунктов</div></div>
          <div class="wave-summary-card"><div class="ws-val">{cas.get("dead", 0) + cas.get("injured", 0)}</div><div class="ws-lbl">Пострадавших</div></div>
        </div>
        <div class="wave-summary-strikes">{strikes_html}</div>
        {f'<div class="wave-summary-text">{esc(summary.get("summary_text", ""))}</div>' if summary.get("summary_text") else ""}
        {f'<div class="wave-summary-sources">Источники: {esc(sources_str)}</div>' if sources_str else ""}
      </section>
"""

    title = f"Волна дронов {rdate}: {cities_n(ev.get('peak_cities', 0))} в {regions_in(ev.get('peak_regions', 0))}"
    desc = (f"Волна активности БПЛА {rdate}: {punkt_n(ev.get('peak_cities', 0))}, "
            f"{regions_n(ev.get('peak_regions', 0))} — {regions_str}. Оценка по открытому OSINT-мониторингу.")
    keywords = f"волна дронов {rdate}, куда летели дроны {rdate}, бпла {rdate}"
    canonical = f"{SITE}/volna-dronov/{slug}"
    og_title = f"Волна дронов {rdate} — {cities_n(ev.get('peak_cities', 0))}"
    og_desc = desc

    article_text = (f"По данным из открытых источников (мониторинговые чаты и каналы), {tod} {rdate} фиксируется "
                     f"повышенная активность БПЛА: отметки в {punkt_in(ev.get('peak_cities', 0))} "
                     f"{regions_n(ev.get('peak_regions', 0))} — {regions_str}. Это "
                     f"предварительные данные мониторинга, не официальная сводка. Следите за "
                     f"официальными оповещениями МЧС и региональных властей.")

    html = [head_common(title, desc, keywords, canonical, og_title, og_desc)]
    html.append(f"""  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "{esc(title)}",
    "datePublished": "{ev.get('published_at', ev.get('started_at', ''))}",
    "dateModified": "{ev.get('ended_at') or ev.get('published_at', ev.get('started_at', ''))}",
    "image": ["{SITE}/og-image.png"],
    "author": {{"@type": "Organization", "name": "Топливный фронт РФ"}},
    "publisher": {{"@type": "Organization", "name": "Топливный фронт РФ", "url": "{SITE}/"}},
    "description": "{esc(desc)}",
    "mainEntityOfPage": "{canonical}",
    "isAccessibleForFree": true
  }}
  </script>
""")
    html.append(breadcrumb_jsonld(f"Волна {rdate}", canonical))
    html.append(f"""
      <div class="landing-hero">
        <span class="hero-label">ВОЛНА ДРОНОВ · АРХИВ</span>
        <h1 class="hero-h">{esc(title)}</h1>
        <p class="hero-sub">{esc(article_text)}</p>
        {cover}
        <div class="wave-region-chips">{"".join(f'<span class="wave-chip">{esc(r)}</span>' for r in region_list)}</div>
        <div class="status-grid">
          <div class="status-card"><div class="val">{ev.get('peak_cities', 0)}</div><div class="lbl">Городов (пик)</div></div>
          <div class="status-card"><div class="val">{ev.get('peak_regions', 0)}</div><div class="lbl">Регионов (пик)</div></div>
          <div class="status-card"><div class="val">{esc(dur)}</div><div class="lbl">Длительность</div></div>
          <div class="status-card"><div class="val">{esc(status_label)}</div><div class="lbl">Статус волны</div></div>
        </div>
        <div class="updated-line">Началась {esc(when)}</div>
      </div>
{summary_html}
      <h2 class="section-h"><span class="ico">🔔</span> Узнавать о волнах первым</h2>
      {SUBSCRIBE_CTA}

      <h2 class="section-h"><span class="ico">🔗</span> Смотрите также</h2>
      <div class="link-grid">
        <a class="link-card" href="/volna-dronov"><div class="lc-h">🛩 Волна дронов — сейчас</div><div class="lc-d">Живая страница: идёт ли волна прямо сейчас</div></a>
        <a class="link-card" href="/radar"><div class="lc-h">📡 Радар угроз</div><div class="lc-d">Карта БПЛА и ракет по регионам в реальном времени</div></a>
        <a class="link-card" href="/karta-bpla"><div class="lc-h">🗺️ Карта БПЛА онлайн</div><div class="lc-d">Как читать карту тревог и угроз по регионам</div></a>
      </div>

      <div class="osint-note">
        <strong>⚠️ Дисклеймер:</strong> {DISCLAIMER_TEXT} Страница носит справочно-аналитический характер и не содержит рекомендаций к действию.
      </div>
    </div>
  </main>
""")
    html.append(FOOT_SCRIPTS.replace("__VPN_VER__", asset_ver("vpn-nudge.js")).replace("__SUB_VER__", asset_ver("sub-nudge.js")))
    return "".join(html)


# ───────────────────────── hero client-fetch JS (вставляется отдельным <script>) ─────────────────────────

HERO_SCRIPT = """  <script>
  (function () {
    "use strict";
    var STATE_URL = "/data/wave-state.json";
    var REFRESH_MS = 5 * 60 * 1000;
    var MONTHS = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"];
    function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
    function rusDate(iso) {
      if (!iso) return "";
      var m = /^(\\d{4})-(\\d{2})-(\\d{2})/.exec(iso);
      if (!m) return iso;
      return parseInt(m[3], 10) + " " + MONTHS[parseInt(m[2], 10) - 1] + " " + m[1];
    }
    function rusDateTimeMsk(iso) {
      if (!iso) return "";
      var d = new Date(new Date(iso).getTime() + 3 * 3600 * 1000); // МСК = UTC+3
      function p(n) { return (n < 10 ? "0" : "") + n; }
      return rusDate(iso) + ", " + p(d.getUTCHours()) + ":" + p(d.getUTCMinutes()) + " МСК";
    }
    function plu(n, o, f, m) { n = Math.abs(n | 0); var a = n % 10, b = n % 100; if (a === 1 && b !== 11) return o; if (a >= 2 && a <= 4 && (b < 12 || b > 14)) return f; return m; }
    function render(state) {
      var activeEl = document.getElementById("waveActive");
      var quietEl = document.getElementById("waveQuiet");
      if (!activeEl || !quietEl || !state) return;
      if (state.active) {
        activeEl.style.display = "";
        quietEl.style.display = "none";
        var t = document.getElementById("waveTitle");
        var nc = state.cities || 0, nr = state.regions || 0;
        if (t) t.textContent = "\\ud83d\\udee9 Волна дронов идёт прямо сейчас — " + nc + " " + plu(nc, "город", "города", "городов") + " в " + nr + " " + plu(nr, "регионе", "регионах", "регионах");
        var chipsWrap = document.getElementById("waveChips");
        if (chipsWrap && Array.isArray(state.region_list)) {
          chipsWrap.innerHTML = state.region_list.map(function (r) { return '<span class="wave-chip">' + esc(r) + '</span>'; }).join("");
        }
        var upd = document.getElementById("waveUpdated");
        if (upd) upd.textContent = state.updated_at ? "Обновлено " + rusDateTimeMsk(state.updated_at) : "";
      } else {
        activeEl.style.display = "none";
        quietEl.style.display = "";
        var ld = document.getElementById("waveLastDate");
        if (ld) {
          // last_event — объект {date,event_id} от wave-detect.py; строку поддержим тоже
          var lastDate = state.last_event && typeof state.last_event === "object" ? state.last_event.date : state.last_event;
          ld.textContent = lastDate ? rusDate(lastDate) : "нет данных";
        }
      }
    }
    function tick() {
      fetch(STATE_URL, { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : null; }).then(render).catch(function () {});
    }
    tick();
    setInterval(tick, REFRESH_MS);
  })();
  </script>
"""


def main():
    state = load_json(STATE_PATH, {"active": False, "current_event_id": None})
    events = load_json(EVENTS_PATH, [])

    live_html = build_live_page(state, events)
    live_html = live_html.replace("</main>", "</main>\n" + HERO_SCRIPT, 1)
    OUT_LIVE.write_text(live_html, encoding="utf-8")
    print(f"написано: {OUT_LIVE.relative_to(ROOT)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for ev in events:
        out = OUT_DIR / f"{ev['id']}.html"
        out.write_text(build_snapshot_page(ev), encoding="utf-8")
        print(f"написано: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
