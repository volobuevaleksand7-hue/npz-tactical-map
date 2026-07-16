#!/usr/bin/env python3
"""
Генератор новостного раздела «Топливный фронт РФ» — как на нормальном новостном сайте.

Строит:
  • news.html                — ИНДЕКС /news: свежая сводка (герой + обложка + баланс) +
                               архив-лента карточек по всем датам.
  • news/<YYYY-MM-DD>.html    — отдельная страница-сводка за каждый день (удары + голоса +
                               навигация «предыдущая/следующая»), для последней даты — ещё
                               национальный баланс, таблица АЗС и биржа.
  • data/news-archive.json    — НАКОПИТЕЛЬНЫЙ архив: удары/голоса по датам переносятся из
                               append-only strikes.json/fuel-voices.json и НЕ теряются.
                               Раз попав в архив, дата остаётся.
  • sitemap.xml               — со всеми датами архива для SEO.

Запуск: python3 agents/gen-news.py
Требования: Python 3.9+, только stdlib. Весь контент — в разметке (без клиентского JS).
"""

import json
import html
import os
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # корень проекта
DATA_DIR = ROOT / "data"
NEWS_DIR = ROOT / "news"                        # /news/<date>.html
ARCHIVE_PATH = DATA_DIR / "news-archive.json"   # накопительный архив
INDEX_OUT = ROOT / "news.html"
SITEMAP_OUT = ROOT / "sitemap.xml"
SITE = "https://npz-tactical-map.vercel.app"

# Предложный падеж для заголовка: «Удар по НПЗ в Саратове», а не «в Саратов».
# Склонятор — agents/prep_case.py (без внешних зависимостей, проверен на 102
# топонимах архива). Файл недоступен — отдаём город как есть: кривой падеж
# лучше упавшей генерации всех сводок.
try:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        "prep_case", os.path.join(os.path.dirname(os.path.abspath(__file__)), "prep_case.py"))
    _pc = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_pc)
    _prep_city = _pc.prep
except Exception:
    def _prep_city(c):
        return c


# ─── Русские названия месяцев ───
MONTHS = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря"
]
# именительный падеж — для заголовков месячных хабов («Июнь 2026», а не «Июня 2026»)
MONTHS_NOM = [
    "", "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
]

SEO_KEYWORDS = (
    "дефицит бензина, лимиты АЗС, удары по НПЗ, "
    "нет бензина, топливный кризис Россия, бензин по талонам, "
    "очереди на заправках, цены на бензин, карта НПЗ, "
    "топливный фронт РФ, ситуация на АЗС, Крым бензин, Севастополь топливо"
)

# Ключевые слова, по которым удар квалифицируется как удар по НПЗ/нефтеинфраструктуре
REFINERY_KW = ("нпз", "нефт", "терминал", "переработ", "нефтебаз", "нефтехим",
               "гпз", "перекачк", "тэц", "тэс", "грэс", "подстанц", "энергет")


# ═══════════════════════════════ утилиты ═══════════════════════════════

def load_json(name: str, default=None):
    try:
        with open(DATA_DIR / name, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def rus_date(iso: str) -> str:
    """2026-07-04 → 4 июля 2026."""
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d")
        return f"{d.day} {MONTHS[d.month]} {d.year}"
    except (ValueError, IndexError):
        return str(iso)


def rus_date_nodots(iso: str) -> str:
    """2026-07-04 → 4 июля (без года — для карточек)."""
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d")
        return f"{d.day} {MONTHS[d.month]}"
    except (ValueError, IndexError):
        return str(iso)


def rus_date_short(iso: str) -> str:
    """2026-07-04 → 04.07.2026."""
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d")
        return d.strftime("%d.%m.%Y")
    except (ValueError, IndexError):
        return str(iso)


def weekday_ru(iso: str) -> str:
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d")
        return ["понедельник", "вторник", "среда", "четверг",
                "пятница", "суббота", "воскресенье"][d.weekday()]
    except (ValueError, IndexError):
        return ""


def month_label(ym: str) -> str:
    """2026-06 → июнь 2026 (именительный, для заголовков)."""
    try:
        y, m = ym.split("-")
        return f"{MONTHS_NOM[int(m)]} {y}"
    except (ValueError, IndexError):
        return ym


def cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def today_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def escape(s) -> str:
    return html.escape(str(s), quote=True)


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def asset_ver(rel: str) -> str:
    """?v=<хэш> для cache-busting: меняется при любой правке файла, поэтому браузер
    никогда не отдаёт устаревший CSS (css кэшируется на 1ч с must-revalidate)."""
    p = ROOT / rel
    try:
        h = hashlib.md5(p.read_bytes()).hexdigest()[:8]
        return f"/{rel}?v={h}"
    except Exception:
        return f"/{rel}"


def cover_for(date: str):
    """Возвращает (rel_path, exists) для обложки конкретной даты."""
    rel = f"assets/cover-{date}.png"
    return rel, (ROOT / rel).exists()


def is_refinery(s: dict) -> bool:
    t = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
    return any(k in t for k in REFINERY_KW)


def infra_label(s: dict) -> str:
    """Точная категория цели для заголовка — нефтебаза ≠ НПЗ (редполитика §3)."""
    t = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
    if "нпз" in t or "нефтеперерабат" in t:
        return "НПЗ и инфраструктуре"
    if "нефтебаз" in t:
        return "нефтебазе"
    if "терминал" in t:
        return "терминалу"
    return "топливной инфраструктуре"


def normalize_strike(s: dict) -> dict:
    """Схема strikes.json дрейфует между сборщиками (detail/description,
    lat+lon/location[]). Нормализуем на входе — единственное место, откуда
    все секции (gen_strikes, gen_index) читают удары."""
    s = dict(s)
    if not s.get("detail") and s.get("description"):
        s["detail"] = s["description"]
    if "lat" not in s and isinstance(s.get("location"), (list, tuple)) and len(s["location"]) == 2:
        s["lat"], s["lon"] = s["location"]
    return s


def level_label(level: str) -> str:
    return {
        "severe": "🔴 Критическая",
        "limited": "🟠 Ограничения",
        "strained": "🟡 Напряжённая",
        "calm": "🟢 Стабильная",
    }.get(level, level)


def level_css(level: str) -> str:
    return {"severe": "crit", "limited": "red", "strained": "amber", "calm": "green"}.get(level, "")


# ═══════════════════════════════ архив ═══════════════════════════════

def build_archive() -> dict:
    """Слить текущие strikes/voices в накопительный архив по датам и обновить снапшот.
    Старые даты, уже осевшие в архиве, сохраняются даже если источник обновился частично."""
    archive = load_json("news-archive.json", {}) if ARCHIVE_PATH.exists() else {}
    briefs = archive.get("briefs", {})

    strikes = [normalize_strike(s) for s in load_json("strikes.json").get("strikes", [])]
    voices = load_json("fuel-voices.json").get("voices", [])

    # группируем по дате
    strikes_by_date = {}
    for s in strikes:
        d = str(s.get("date", ""))[:10]
        if d:
            strikes_by_date.setdefault(d, []).append(s)
    voices_by_date = {}
    for v in voices:
        d = str(v.get("date", ""))[:10]
        if d:
            voices_by_date.setdefault(d, []).append(v)

    # для каждой даты, встреченной в текущих данных, перезаписываем содержимое архива
    for d in set(list(strikes_by_date) + list(voices_by_date)):
        entry = briefs.get(d, {})
        if d in strikes_by_date:
            entry["strikes"] = strikes_by_date[d]
        if d in voices_by_date:
            entry["voices"] = voices_by_date[d]
        entry.setdefault("strikes", [])
        entry.setdefault("voices", [])
        briefs[d] = entry

    # ВСЕГДА включаем сегодняшнюю дату (даже если нет ударов/голосов)
    today = today_iso()
    if today not in briefs:
        briefs[today] = {"strikes": [], "voices": []}

    # текущий снапшот общестрановой ситуации (баланс/АЗС/биржа) — только последняя версия
    availability = load_json("fuel-availability.json")
    fuel_state = load_json("fuel-state.json")
    timeline = load_json("capacity-timeline.json").get("timeline", [])
    # счётчики НПЗ по статусу (как на карте: стоит/частично/работает)
    counts = {"down": 0, "partial": 0, "operational": 0}
    for r in fuel_state.get("refineries", []):
        st = r.get("status")
        if st in counts:
            counts[st] += 1
    archive["snapshot"] = {
        "balance": fuel_state.get("national_balance", {}),
        "regions": availability.get("regions", []),
        "exchange": availability.get("exchange", {}),
        "refinery_counts": counts,
        "timeline": timeline,
        "deficit_regions_count": len(fuel_state.get("deficit_regions", [])),
    }
    archive["briefs"] = briefs
    archive["updated"] = today_iso()

    ARCHIVE_PATH.write_text(json.dumps(archive, ensure_ascii=False, indent=1), encoding="utf-8")
    return archive


def briefs_by_month(briefs: dict) -> dict:
    """Группирует даты архива по месяцу 'YYYY-MM' → список дат внутри месяца
    (новые сверху, как и общий порядок архива)."""
    out = {}
    for d in briefs:
        out.setdefault(d[:7], []).append(d)
    for ym in out:
        out[ym].sort(reverse=True)
    return out


def month_stats(dates: list, briefs: dict) -> dict:
    """Сводные цифры месяца для SEO-блока хаба: удары, из них по НПЗ/энергетике,
    дней в архиве, топ городов."""
    strikes_all = []
    for d in dates:
        strikes_all.extend(briefs.get(d, {}).get("strikes", []))
    n_ref = sum(1 for s in strikes_all if is_refinery(s))
    city_counts = {}
    for s in strikes_all:
        c = str(s.get("city", "")).strip()
        if c:
            city_counts[c] = city_counts.get(c, 0) + 1
    top_cities = sorted(city_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return {
        "n_strikes": len(strikes_all), "n_refinery": n_ref,
        "n_days": len(dates), "top_cities": top_cities,
    }


def brief_headline(date: str, strikes: list) -> str:
    """Заголовок-«шапка» дня в новостном стиле."""
    n = len(strikes)
    if n == 0:
        return "Сводка дня: без подтверждённых ударов"
    cities = []
    for s in strikes:
        c = str(s.get("city", "")).strip()
        if c and c not in cities:
            cities.append(c)
    # Лид дня — самый значимый удар, а не первый в списке. Трёхуровневая
    # классификация как у обложки (hermes/scripts/build-covers.py): НПЗ/нефтебаза
    # (2) > энергетика/газотранспорт (1) > прочее (0); при равенстве — confirmed
    # важнее reported. Иначе, напр., 08.07 вела подстанцией «Нижнегорская»
    # (is_refinery ложно=1) вместо Саратовского НПЗ (confirmed).
    _REF_K = ("нпз", "нефтеперераб", "нефтебаз", "нефтехим", "терминал",
              "нефтепрод", "нефтеузел", "гпз", "перекачк", "нпс")
    _GRID_K = ("подстанц", "тэц", "тэс", "грэс", "энергет", "электро",
               "компрессор", "газопровод")

    def _cls(s):
        t = (str(s.get("target", "")) + " " + str(s.get("title", ""))).lower()
        if any(k in t for k in _REF_K):
            return 2
        if any(k in t for k in _GRID_K):
            return 1
        return 0

    def _lead_key(s):
        conf = 1 if str(s.get("confidence", "")).lower() == "confirmed" else 0
        # Бонус за свежесть: сегодняшние удары приоритетнее
        sdate = str(s.get("date", ""))[:10]
        recency = 0
        if sdate == date:
            recency = 10
        return (_cls(s), conf, recency)
    refs = [s for s in strikes if is_refinery(s)]
    if refs:
        lead = max(strikes, key=_lead_key)
        rc = str(lead.get("city", "")).strip()
        rc = _prep_city(rc)
        label = infra_label(lead)
        rest = n - 1
        if rest > 0:
            return f"Удар по {label} в {rc} и ещё {rest} {plural(rest, 'удар', 'удара', 'ударов')}"
        return f"Удар по {label} в {rc}"
    head = ", ".join(cities[:3])
    if len(cities) > 3:
        head += f" и ещё {len(cities) - 3}"
    return f"{n} {plural(n, 'удар', 'удара', 'ударов')} по РФ: {head}" if head else \
        f"{n} {plural(n, 'удар', 'удара', 'ударов')} по РФ"


def brief_teaser(strikes: list, voices: list) -> str:
    """Короткий анонс для карточки архива."""
    if strikes:
        top = strikes[0]
        det = str(top.get("detail") or top.get("title") or top.get("target") or "").strip()
        if det:
            return det[:150].rstrip() + ("…" if len(det) > 150 else "")
    if voices:
        q = str(voices[0].get("quote", "")).strip()
        if q:
            return "«" + q[:130].rstrip() + ("…»" if len(q) > 130 else "»")
    return "Ежедневная OSINT-сводка по ситуации с топливом и ударам по НПЗ."


# ═══════════════════════════════ секции ═══════════════════════════════

def gen_strikes(strikes: list, max_n: int = 60) -> str:
    rows = []
    for s in strikes[:max_n]:
        date_str = rus_date(s.get("date", ""))
        city = escape(s.get("city", "?"))
        target = escape(s.get("target", ""))
        detail = escape(s.get("detail", ""))
        if len(detail) > 400:
            detail = detail[:397] + "…"
        source = escape(s.get("source_url", ""))
        conf = escape(s.get("confidence", "reported"))
        conf_badge = "✅ Подтверждено" if conf == "confirmed" else ("📡 Сообщается" if conf == "reported" else "🗣️ Слух")
        time_str = escape(s.get("time", ""))
        rows.append(f"""<article class="news-strike">
  <div class="strike-head">
    <span class="strike-date">{date_str}{' · ' + time_str if time_str else ''}</span>
    <span class="strike-city">📍 {city}</span>
    <span class="strike-conf {conf}">{conf_badge}</span>
  </div>
  <p class="strike-target"><strong>Цель:</strong> {target}</p>
  <p class="strike-detail">{detail}</p>
  {'<a class="strike-source" href="'+source+'" target="_blank" rel="noopener noreferrer">Источник →</a>' if source else ''}
</article>""")
    return "\n".join(rows) if rows else '<p class="section-sub">За эту дату подтверждённых ударов в архиве нет.</p>'


def gen_azs(regions: list, exchange: dict) -> str:
    order = {"severe": 0, "limited": 1, "strained": 2, "calm": 3}
    sorted_regions = sorted(regions, key=lambda r: order.get(r.get("level", "calm"), 99))
    rows = []
    for r in sorted_regions[:12]:
        name = escape(r.get("region", "?"))
        level = r.get("level", "calm")
        css = level_css(level)
        price = r.get("ai95_price_rub")
        price_str = f"{price} ₽/л" if price else "—"
        queues = r.get("queues_hours", 0)
        queue_str = f"{queues} ч" if queues else "нет данных"
        nets = []
        for n in r.get("networks", [])[:3]:
            net_name = escape(n.get("name", "?"))
            limit = n.get("limit_l")
            limit_str = f"до {limit} л" if limit else "ограничен"
            nets.append(f"<span class=\"azs-net\">{net_name}: {limit_str}</span>")
        nets_html = " · ".join(nets) if nets else "данные уточняются"
        rows.append(f"""<tr class="azs-row level-{css}">
  <td class="azs-region"><span class="level-dot {css}"></span> {name}</td>
  <td class="azs-status">{level_label(level)}</td>
  <td class="azs-networks">{nets_html}</td>
  <td class="azs-price">{price_str}</td>
  <td class="azs-queues">{queue_str}</td>
</tr>""")
    ex_html = ""
    if exchange:
        ai95 = exchange.get("ai95_spb_rub_t")
        ai92 = exchange.get("ai92_spb_rub_t")
        dt = exchange.get("diesel_spb_rub_t")
        ex_updated = rus_date(exchange.get("updated", ""))
        trend_arrow = {"rising": "↑", "falling": "↓"}.get(exchange.get("trend", ""), "")
        trend_col = {"rising": "var(--crit)", "falling": "var(--green)"}.get(exchange.get("trend", ""), "var(--ink-dim)")
        ex_html = f"""<div class="exchange-block">
  <h3>📊 Биржа СПбМТСБ (на {ex_updated}){f' <span style="color:{trend_col}">{trend_arrow}</span>' if trend_arrow else ''}</h3>
  <div class="exchange-prices">
    <span class="ex-item">АИ-95: <strong>{f"{ai95:,} ₽/т".replace(',', ' ') if ai95 else "—"}</strong></span>
    <span class="ex-item">АИ-92: <strong>{f"{ai92:,} ₽/т".replace(',', ' ') if ai92 else "—"}</strong></span>
    <span class="ex-item">ДТ: <strong>{f"{dt:,} ₽/т".replace(',', ' ') if dt else "—"}</strong></span>
  </div>
</div>"""
    return f"""<div class="azs-table-wrap">
<table class="azs-table">
<thead><tr><th>Регион</th><th>Ситуация</th><th>Сети и лимиты</th><th>АИ-95 цена</th><th>Очереди</th></tr></thead>
<tbody>{chr(10).join(rows)}</tbody>
</table>
</div>
{ex_html}"""


def gen_voices(voices: list, max_n: int = 8) -> str:
    rows = []
    for v in voices[:max_n]:
        quote = escape(v.get("quote", ""))
        city = escape(v.get("city", "?"))
        region = escape(v.get("region", ""))
        date_str = rus_date(v.get("date", ""))
        emoji = {"complaint": "😠", "panic": "😰", "sarcasm": "😏", "info": "ℹ️"}.get(v.get("sentiment", ""), "💬")
        rows.append(f"""<blockquote class="voice-quote">
  <p class="voice-text">{emoji} «{quote}»</p>
  <footer class="voice-meta">— {city}{', ' + region if region else ''}, {date_str}</footer>
</blockquote>""")
    return "\n".join(rows)


# ═══════════════════════════════ общие куски ═══════════════════════════════

def head_html(title, description, canonical, cover_url, jsonld="") -> str:
    return f"""<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <meta name="theme-color" content="#d23a2e">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}">
  <meta name="keywords" content="{escape(SEO_KEYWORDS)}">
  <meta name="robots" content="index, follow">
  <meta name="language" content="Russian">
  <link rel="canonical" href="{canonical}">

  <meta property="og:type" content="article">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:site_name" content="Топливный фронт РФ">
  <meta property="og:url" content="{canonical}">
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(description)}">
  <meta property="og:image" content="{cover_url}">
  <meta property="og:image:alt" content="Сводка ударов по НПЗ и дефицита бензина — Топливный фронт РФ">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(title)}">
  <meta name="twitter:description" content="{escape(description)}">
  <meta name="twitter:image" content="{cover_url}">
  <meta name="twitter:image:alt" content="NPZ Tactical Map — Russia Fuel Crisis Daily Brief">

  <link rel="alternate" type="application/rss+xml" title="Топливный фронт РФ — сводки (RSS)" href="https://npz-tactical-map.vercel.app/rss.xml">

  {jsonld}

  <script>window.va = window.va || function () {{ (window.vaq = window.vaq || []).push(arguments); }};</script>
  <script defer src="/_vercel/insights/script.js"></script>

  <link rel="stylesheet" href="/fonts.css">
  <link rel="stylesheet" href="{asset_ver('styles.css')}">
  <link rel="stylesheet" href="{asset_ver('news.css')}">
  <script src="/metrika.js" async></script>
</head>
<body data-theme="light">
"""


def header_html(date_badge: str) -> str:
    return f"""  <header class="news-header">
    <div class="news-header-inner">
      <a href="/" class="news-logo" title="На карту">
        <span class="news-logo-icon">⛽</span>
        <span class="news-logo-text">ТОПЛИВНЫЙ ФРОНТ РФ</span>
      </a>
      <nav class="news-nav"><!-- сгенерит agents/build-nav.py --></nav>
      <span class="news-date-badge">{date_badge}</span>
    </div>
  </header>
"""


FOOTER_HTML = """  <footer class="news-footer">
    <div class="news-footer-inner">
      <p>Топливный фронт РФ · OSINT-дашборд · <span class="mono">npz-tactical-map.vercel.app</span></p>
      <p class="footer-disc">Не является официальной информацией. Данные из открытых источников.</p>
    </div>
  </footer>

</body>
</html>"""

DISCLAIMER_HTML = ('<p class="news-disclaimer">⚠️ <strong>ОЦЕНКА / ESTIMATE.</strong> '
                   'Данные агрегированы из открытых OSINT-источников. '
                   'Не являются официальной информацией. Возможны неточности.</p>')

CTA_HTML = """      <section class="news-cta">
        <div class="cta-card">
          <h2>🗺️ Открыть интерактивную карту</h2>
          <p>Все НПЗ России, удары БПЛА, состояние АЗС, дефицит по регионам — с геопривязкой и фильтрацией.</p>
          <div class="cta-buttons">
            <a href="/" class="cta-btn primary">Открыть карту НПЗ →</a>
            <a href="/karta-azs" class="cta-btn secondary">Карта АЗС →</a>
          </div>
        </div>
      </section>
"""


def spark_svg(timeline: list) -> str:
    """Спарклайн динамики выбытия мощностей (как на карте): 18% → 26% + линия."""
    pts = [float(x.get("capacity_offline_pct") or 0) for x in timeline[-12:]]
    if len(pts) < 2:
        return ""
    w, hh = 600.0, 44.0
    mx, mn = max(pts), min(pts)
    rng = (mx - mn) or 1
    n = len(pts)
    d = " ".join(
        ("M" if i == 0 else "L") + f"{(i/(n-1))*w:.1f} {hh-((v-mn)/rng)*(hh-9)-5:.1f}"
        for i, v in enumerate(pts)
    )
    first, last = int(pts[0]), int(pts[-1])
    up = last >= first
    col = "var(--crit)" if up else "var(--green)"
    return f"""        <div class="balance-spark">
          <div class="spark-head"><span>динамика выбытия мощностей</span><span class="spark-delta" style="color:{col}">{first}% → {last}%</span></div>
          <svg viewBox="0 0 {w:.0f} {hh:.0f}" preserveAspectRatio="none" class="spark-svg"><path d="{d}" fill="none" stroke="var(--crit)" stroke-width="2" stroke-linejoin="round"/></svg>
        </div>
"""


def balance_section(snapshot: dict) -> str:
    balance = snapshot.get("balance", {})
    counts = snapshot.get("refinery_counts", {})
    timeline = snapshot.get("timeline", [])
    cap_offline = balance.get("capacity_offline_pct", "?")
    cap_mt = balance.get("capacity_offline_mt_year")
    cap_total = balance.get("refining_capacity_total_mt_year")
    gasoline_loss = balance.get("gasoline_output_loss_pct", "?")
    diesel_loss = balance.get("diesel_output_loss_pct", "?")
    shortfall = balance.get("throughput_shortfall_pct")
    notes = escape(balance.get("notes", ""))
    # Обрезаем только очень длинные примечания и ТОЛЬКО по границе предложения/слова,
    # чтобы не рвать текст посреди слова и не терять последний факт (напр. про OPEC+).
    NOTES_LIMIT = 1600
    if len(notes) > NOTES_LIMIT:
        cut = notes[:NOTES_LIMIT]
        b = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        if b >= NOTES_LIMIT // 2:
            notes = cut[:b + 1]
        else:
            sp = cut.rfind(" ")
            notes = (cut[:sp] if sp > 0 else cut).rstrip() + "…"
    abs_line = (f"~{cap_mt} из {cap_total} млн т/год" if cap_mt and cap_total else "")
    shortfall_line = (f" · с учётом частично работающих недобор ~{shortfall}%" if shortfall else "")

    spark = spark_svg(timeline)
    deficit_n = snapshot.get("deficit_regions_count")
    chips = ""
    if counts:
        deficit_chip = (f'<div class="bchip amber"><span class="bchip-n">{deficit_n}</span>'
                         f'<span class="bchip-l">регионов в дефиците</span></div>' if deficit_n else "")
        chips = f"""        <div class="balance-chips">
          <div class="bchip red"><span class="bchip-n">{counts.get('down', 0)}</span><span class="bchip-l">стоит</span></div>
          <div class="bchip amber"><span class="bchip-n">{counts.get('partial', 0)}</span><span class="bchip-l">частично</span></div>
          <div class="bchip green"><span class="bchip-n">{counts.get('operational', 0)}</span><span class="bchip-l">работает</span></div>
          {deficit_chip}
        </div>
"""
    return f"""      <section class="news-section" id="balance">
        <h2>📉 Национальный баланс нефтепереработки</h2>
        <div class="balance-hero">
          <span class="balance-hero-num">{cap_offline}%</span>
          <span class="balance-hero-label">мощностей переработки выбито{'<br><b>' + abs_line + '</b>' if abs_line else ''}{shortfall_line}</span>
        </div>
{spark}{chips}        <div class="balance-loss">
          <div class="lossbar"><div class="lossbar-head"><span>Потери выпуска бензина</span><span class="lossbar-pct red">{gasoline_loss}%</span></div><div class="lossbar-track"><div class="lossbar-fill red" style="width:{min(100, int(gasoline_loss) if str(gasoline_loss).isdigit() else 0)}%"></div></div></div>
          <div class="lossbar"><div class="lossbar-head"><span>Потери выпуска дизеля</span><span class="lossbar-pct amber">{diesel_loss}%</span></div><div class="lossbar-track"><div class="lossbar-fill amber" style="width:{min(100, int(diesel_loss) if str(diesel_loss).isdigit() else 0)}%"></div></div></div>
        </div>
        <div class="balance-notes"><p>{notes if notes else "Данные уточняются."}</p></div>
      </section>
"""


def brief_card_html(d: str, b: dict, is_latest: bool = False) -> str:
    """Карточка одной даты — общая для ленты /news и месячных хабов."""
    st = b.get("strikes", [])
    vo = b.get("voices", [])
    c_rel, c_ex = cover_for(d)
    c_path = asset_ver(c_rel) if c_ex else "/og-image.png"
    n_ref = sum(1 for s in st if is_refinery(s))
    meta_bits = [f"{len(st)} {plural(len(st), 'удар', 'удара', 'ударов')}"]
    if n_ref:
        meta_bits.append(f"🛢 {n_ref} по НПЗ/энергетике")
    if vo:
        meta_bits.append(f"🗣 {len(vo)} {plural(len(vo), 'голос', 'голоса', 'голосов')}")
    return f"""        <a class="brief-card{' is-latest' if is_latest else ''}" href="/news/{d}">
          <div class="brief-card-cover" style="background-image:url('{c_path}')">
            <span class="brief-card-date">{rus_date_nodots(d)}</span>
          </div>
          <div class="brief-card-body">
            <h3 class="brief-card-title">{escape(brief_headline(d, st))}</h3>
            <p class="brief-card-teaser">{escape(brief_teaser(st, vo))}</p>
            <div class="brief-card-meta">{' · '.join(escape(m) for m in meta_bits)}</div>
          </div>
        </a>"""


def month_archive_row(months: dict) -> str:
    """Компактный ряд ссылок на месячные хабы (новые месяцы слева)."""
    yms = sorted(months.keys(), reverse=True)
    chips = [f'<a class="brief-nav-btn" href="/news/{ym}">{cap(month_label(ym))} '
             f'<span style="opacity:.6">({len(months[ym])})</span></a>' for ym in yms]
    return f"""      <section class="news-section news-archive-months">
        <h2>🗓 Архив по месяцам</h2>
        <div class="brief-nav" style="flex-wrap:wrap">
{chr(10).join(chips)}
        </div>
      </section>
"""


# ═══════════════════════════════ ИНДЕКС /news ═══════════════════════════════

def gen_index(archive: dict) -> str:
    briefs = archive.get("briefs", {})
    snapshot = archive.get("snapshot", {})
    dates = sorted(briefs.keys(), reverse=True)
    if not dates:
        dates = [today_iso()]
        briefs = {dates[0]: {"strikes": [], "voices": []}}

    latest = dates[0]
    latest_brief = briefs[latest]
    latest_strikes = latest_brief.get("strikes", [])
    latest_rus = rus_date(latest)
    cover_rel, cover_exists = cover_for(latest)
    cover_path = asset_ver(cover_rel) if cover_exists else "/og-image.png"
    cover_url = SITE + cover_path

    title = f"Топливный фронт РФ — сводки по дням | удары по НПЗ и дефицит бензина"
    description = (f"Ежедневные OSINT-сводки: удары БПЛА по нефтезаводам России, дефицит бензина, "
                   f"лимиты на АЗС, очереди, цены АИ-95, биржа СПбМТСБ. Архив за каждый день. "
                   f"Последнее обновление — {latest_rus}.")

    # JSON-LD: ItemList всех сводок (лента)
    item_list = {
        "@context": "https://schema.org", "@type": "ItemList",
        "name": "Ежедневные сводки — Топливный фронт РФ",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1,
             "url": f"{SITE}/news/{d}",
             "name": f"Сводка за {rus_date(d)}"}
            for i, d in enumerate(dates)
        ],
    }
    jsonld = f'<script type="application/ld+json">{json.dumps(item_list, ensure_ascii=False)}</script>'

    # герой — свежая сводка
    hero = f"""      <section class="news-hero-lead">
        <a class="hero-cover-link" href="/news/{latest}">
          <img class="news-hero-image" src="{cover_path}" alt="Сводка за {latest_rus}" width="1200" height="630" loading="eager">
        </a>
        <div class="hero-lead-body">
          <span class="hero-kicker">🔴 Свежая сводка · {weekday_ru(latest)}, {rus_date_short(latest)}</span>
          <h1>{escape(brief_headline(latest, latest_strikes))}</h1>
          <p class="hero-lead-teaser">{escape(brief_teaser(latest_strikes, latest_brief.get('voices', [])))}</p>
          <a class="hero-read-btn" href="/news/{latest}">Читать полную сводку за {latest_rus} →</a>
        </div>
      </section>
"""

    # карточки архива (кроме свежей — она в герое)
    cards = [brief_card_html(d, briefs[d], d == latest) for d in dates]

    archive_grid = f"""      <section class="news-section news-archive">
        <h2>🗓 Все сводки по дням</h2>
        <p class="section-sub">Хроника топливного кризиса — каждый день с 7 июня 2026. Нажми на карточку, чтобы открыть сводку за дату.</p>
        <div class="brief-grid">
{chr(10).join(cards)}
        </div>
      </section>
"""

    months_row = month_archive_row(briefs_by_month(briefs))

    return (
        head_html(title, description, f"{SITE}/news", cover_url, jsonld)
        + header_html(f"Сводок в архиве: {len(dates)}")
        + '  <main class="news-main">\n    <div class="news-container">\n\n'
        + hero
        + f'      {DISCLAIMER_HTML}\n'
        + balance_section(snapshot)
        + months_row
        + archive_grid
        + CTA_HTML
        + '\n    </div>\n  </main>\n\n'
        + FOOTER_HTML
    )


# ═══════════════════════════════ страница даты ═══════════════════════════════

def gen_date_page(date: str, archive: dict, prev_date, next_date) -> str:
    briefs = archive.get("briefs", {})
    snapshot = archive.get("snapshot", {})
    b = briefs.get(date, {"strikes": [], "voices": []})
    strikes = b.get("strikes", [])
    voices = b.get("voices", [])

    # ponytail: НЕ подмешивать удары за предыдущий день. Раньше сюда клеился
    # «24-часовой окно» prev_strikes + strikes, но применялось это ко ВСЕМ датам,
    # а не только к сегодняшней: страница «Удары за 15 июля» показывала карточки
    # от 14-го, один и тот же удар попадал на две даты (дубль-контент), а в дни
    # простоя сборщиков сводка выглядела живой на чужих данных. Пустой день
    # обрабатывается корректно и без костыля: brief_headline() -> «без
    # подтверждённых ударов», gen_strikes([]) -> «За эту дату ... ударов нет».

    date_rus = rus_date(date)
    is_latest = (next_date is None)

    cover_rel, cover_exists = cover_for(date)
    cover_path = asset_ver(cover_rel) if cover_exists else "/og-image.png"
    cover_url = SITE + cover_path

    headline = brief_headline(date, strikes)
    title = f"Сводка за {date_rus}: {headline} | Топливный фронт РФ"
    description = (f"Топливный фронт РФ за {date_rus}: {brief_teaser(strikes, voices)} "
                   f"Удары по НПЗ, дефицит бензина, лимиты на АЗС.")[:300]

    # JSON-LD NewsArticle
    news_article = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": f"Сводка за {date_rus}: {headline}",
        "datePublished": date, "dateModified": archive.get("updated", date),
        "image": [cover_url],
        "author": {"@type": "Organization", "name": "Топливный фронт РФ"},
        "publisher": {"@type": "Organization", "name": "Топливный фронт РФ", "url": SITE + "/"},
        "description": description,
        "mainEntityOfPage": f"{SITE}/news/{date}",
        "isAccessibleForFree": True,
    }
    jsonld = f'<script type="application/ld+json">{json.dumps(news_article, ensure_ascii=False)}</script>'

    # JSON-LD BreadcrumbList (Главная / Сводки / Месяц / дата)
    month_ym = date[:7]
    breadcrumb = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Топливный фронт РФ", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Сводки", "item": SITE + "/news"},
            {"@type": "ListItem", "position": 3, "name": cap(month_label(month_ym)), "item": f"{SITE}/news/{month_ym}"},
            {"@type": "ListItem", "position": 4, "name": date_rus, "item": f"{SITE}/news/{date}"},
        ],
    }
    jsonld += f'\n  <script type="application/ld+json">{json.dumps(breadcrumb, ensure_ascii=False)}</script>'

    # навигация «предыдущая/следующая»
    nav_prev = (f'<a class="brief-nav-btn prev" href="/news/{prev_date}">← {rus_date_nodots(prev_date)}</a>'
                if prev_date else '<span class="brief-nav-btn disabled">← раньше</span>')
    nav_next = (f'<a class="brief-nav-btn next" href="/news/{next_date}">{rus_date_nodots(next_date)} →</a>'
                if next_date else '<span class="brief-nav-btn disabled">позже →</span>')

    n_ref = sum(1 for s in strikes if is_refinery(s))
    sub_bits = [f"{len(strikes)} {plural(len(strikes), 'зафиксированный удар', 'зафиксированных удара', 'зафиксированных ударов')}"]
    if n_ref:
        sub_bits.append(f"{n_ref} по НПЗ/энергетике")

    parts = [
        head_html(title, description, f"{SITE}/news/{date}", cover_url, jsonld),
        header_html(f"Сводка за {rus_date_short(date)}"),
        '  <main class="news-main">\n    <div class="news-container">\n',
        f"""      <nav class="brief-crumb"><a href="/news">📰 Все сводки</a> <span>/</span> <a href="/news/{month_ym}">{cap(month_label(month_ym))}</a> <span>/</span> {date_rus}</nav>
      <section class="news-hero">
        <img class="news-hero-image" src="{cover_path}" alt="Сводка за {date_rus}" width="1200" height="630" loading="eager">
        <span class="hero-kicker">{weekday_ru(date)}, {rus_date_short(date)}</span>
        <h1>Топливный фронт РФ — сводка за {date_rus}</h1>
        <p class="section-sub">{escape(' · '.join(sub_bits))}. OSINT-агрегация по открытым источникам.</p>
        {DISCLAIMER_HTML}
      </section>
""",
        f"""      <section class="news-section" id="strikes">
        <h2>🎯 Удары за {date_rus}</h2>
        <div class="strikes-list">
          {gen_strikes(strikes)}
        </div>
        <p class="section-note">📡 Все удары с геопривязкой — на <a href="/">интерактивной карте</a>.</p>
      </section>
""",
    ]

    if voices:
        parts.append(f"""      <section class="news-section" id="voices">
        <h2>🗣️ Голоса людей за {date_rus}</h2>
        <p class="section-sub">Публичные отзывы с заправок, форумов и региональных СМИ.</p>
        <div class="voices-list">
          {gen_voices(voices)}
        </div>
      </section>
""")

    # На свежей сводке — текущий баланс/АЗС/биржа (актуальный срез)
    if is_latest:
        snap = snapshot
        parts.append(balance_section(snap))
        parts.append(f"""      <section class="news-section" id="azs">
        <h2>⛽ Ситуация на АЗС по регионам</h2>
        <p class="section-sub">Актуальный срез: ограничения продажи топлива, лимиты, очереди и цены АИ-95.</p>
        {gen_azs(snap.get("regions", []), snap.get("exchange", {}))}
        <p class="section-note">📍 Все точки АЗС — на <a href="/karta-azs">карте АЗС</a>.</p>
      </section>
""")

    parts.append(f"""      <nav class="brief-nav">
        {nav_prev}
        <a class="brief-nav-btn center" href="/news">Все сводки</a>
        {nav_next}
      </nav>
""")
    parts.append('      <p class="section-note">📊 По теме: '
                 '<a href="/deficit">почему нет бензина</a> · '
                 '<a href="/attacks">хроника ударов по НПЗ</a> · '
                 '<a href="/crisis">прогноз кризиса</a>.</p>\n')
    parts.append(CTA_HTML)
    parts.append('\n    </div>\n  </main>\n\n')
    parts.append(FOOTER_HTML)
    return "".join(parts)


# ═══════════════════════════════ хаб /news/YYYY-MM ═══════════════════════════════

def gen_month_page(ym: str, dates: list, archive: dict, prev_ym, next_ym) -> str:
    """Месячный архив-хаб: SEO-лендинг «удары по НПЗ <месяц> <год>» + список дней
    месяца, ссылающихся на уже существующие /news/<date> страницы."""
    briefs = archive.get("briefs", {})
    stats = month_stats(dates, briefs)
    label = month_label(ym)          # "июнь 2026"
    label_cap = cap(label)           # "Июнь 2026"
    n_strikes_word = plural(stats["n_strikes"], "удар", "удара", "ударов")
    n_days_word = plural(stats["n_days"], "день", "дня", "дней")
    canonical = f"{SITE}/news/{ym}"

    cover_rel, cover_exists = cover_for(dates[0]) if dates else ("", False)
    cover_path = asset_ver(cover_rel) if cover_exists else "/og-image.png"
    cover_url = SITE + cover_path

    title = f"Удары по НПЗ и топливная обстановка — {label} | Топливный фронт РФ"
    description = (f"Архив сводок за {label}: {stats['n_strikes']} {n_strikes_word} по РФ, "
                    f"из них {stats['n_refinery']} по НПЗ/энергетике, за {stats['n_days']} {n_days_word} "
                    f"в архиве. Хроника по дням с картой и источниками.")[:300]

    # JSON-LD: CollectionPage со списком дневных сводок месяца
    item_list = {
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "url": f"{SITE}/news/{d}", "name": f"Сводка за {rus_date(d)}"}
            for i, d in enumerate(dates)
        ],
    }
    collection = {
        "@context": "https://schema.org", "@type": "CollectionPage",
        "name": title, "description": description, "url": canonical,
        "mainEntity": item_list,
    }
    jsonld = f'<script type="application/ld+json">{json.dumps(collection, ensure_ascii=False)}</script>'
    breadcrumb = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Топливный фронт РФ", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Сводки", "item": SITE + "/news"},
            {"@type": "ListItem", "position": 3, "name": label_cap, "item": canonical},
        ],
    }
    jsonld += f'\n  <script type="application/ld+json">{json.dumps(breadcrumb, ensure_ascii=False)}</script>'

    top_cities_str = ", ".join(f"{escape(c)} ({n})" for c, n in stats["top_cities"])
    lead_extra = f", основные цели — {top_cities_str}" if top_cities_str else ""

    chips = f"""        <div class="balance-chips">
          <div class="bchip red"><span class="bchip-n">{stats['n_strikes']}</span><span class="bchip-l">{n_strikes_word} за месяц</span></div>
          <div class="bchip amber"><span class="bchip-n">{stats['n_refinery']}</span><span class="bchip-l">по НПЗ/энергетике</span></div>
          <div class="bchip green"><span class="bchip-n">{stats['n_days']}</span><span class="bchip-l">{n_days_word} в архиве</span></div>
        </div>
"""

    nav_prev = (f'<a class="brief-nav-btn prev" href="/news/{prev_ym}">← {cap(month_label(prev_ym))}</a>'
                if prev_ym else '<span class="brief-nav-btn disabled">← раньше</span>')
    nav_next = (f'<a class="brief-nav-btn next" href="/news/{next_ym}">{cap(month_label(next_ym))} →</a>'
                if next_ym else '<span class="brief-nav-btn disabled">позже →</span>')

    cards = [brief_card_html(d, briefs.get(d, {"strikes": [], "voices": []})) for d in dates]

    parts = [
        head_html(title, description, canonical, cover_url, jsonld),
        header_html(f"Архив за {label}"),
        '  <main class="news-main">\n    <div class="news-container">\n',
        f"""      <nav class="brief-crumb"><a href="/news">📰 Все сводки</a> <span>/</span> {label_cap}</nav>
      <section class="news-hero">
        <img class="news-hero-image" src="{cover_path}" alt="Архив сводок за {label}" width="1200" height="630" loading="eager">
        <span class="hero-kicker">Архив по месяцам</span>
        <h1>Удары по НПЗ и топливная обстановка — {label}</h1>
        <p class="section-sub">Хроника ударов и дефицита топлива за {label}: {stats['n_strikes']} {n_strikes_word} за {stats['n_days']} {n_days_word}{lead_extra}.</p>
        {DISCLAIMER_HTML}
      </section>
""",
        f"""      <section class="news-section" id="month-stats">
        <h2>📊 Итоги месяца — {label}</h2>
{chips}      </section>
""",
        f"""      <section class="news-section news-archive">
        <h2>🗓 Сводки по дням — {label}</h2>
        <div class="brief-grid">
{chr(10).join(cards)}
        </div>
      </section>
""",
        f"""      <nav class="brief-nav">
        {nav_prev}
        <a class="brief-nav-btn center" href="/news">Все сводки</a>
        {nav_next}
      </nav>
""",
        CTA_HTML,
        '\n    </div>\n  </main>\n\n',
        FOOTER_HTML,
    ]
    return "".join(parts)


# ═══════════════════════════════ sitemap ═══════════════════════════════

def sitemap_priority(date: str, today: str, base: float = 0.7) -> str:
    """Age-decay приоритета: свежие даты — base, старше 30 дней — 0.5, старше 60 — 0.4."""
    try:
        d0 = datetime.strptime(date, "%Y-%m-%d")
        d1 = datetime.strptime(today, "%Y-%m-%d")
        age_days = (d1 - d0).days
    except ValueError:
        return f"{base:.1f}"
    if age_days > 60:
        return "0.4"
    if age_days > 30:
        return "0.5"
    return f"{base:.1f}"


def gen_sitemap(archive: dict) -> str:
    dates = sorted(archive.get("briefs", {}).keys(), reverse=True)
    today = today_iso()
    urls = [
        (f"{SITE}/", today, "daily", "1.0"),
        (f"{SITE}/news", today, "daily", "0.9"),
        (f"{SITE}/sources", "2026-06-21", "weekly", "0.6"),
        (f"{SITE}/crimea", today, "daily", "0.85"),
        (f"{SITE}/deficit", today, "weekly", "0.8"),
        (f"{SITE}/npz/omskij-npz", today, "weekly", "0.7"),
    ]
    for d in dates:
        urls.append((f"{SITE}/news/{d}", d, "monthly", sitemap_priority(d, today)))
    body = []
    for loc, lastmod, freq, prio in urls:
        body.append(f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{prio}</priority>
    <xhtml:link rel="alternate" hreflang="ru" href="{loc}"/>
  </url>""")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
            '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n\n'
            + "\n".join(body)
            + "\n\n</urlset>\n")


# ═══════════════════════════════ main ═══════════════════════════════

def main():
    print(f"[gen-news] Сборка архива из {DATA_DIR}...")
    archive = build_archive()
    dates = sorted(archive.get("briefs", {}).keys(), reverse=True)
    print(f"[gen-news] Дат в архиве: {len(dates)} ({dates[-1] if dates else '—'} … {dates[0] if dates else '—'})")

    # индекс
    INDEX_OUT.write_text(gen_index(archive), encoding="utf-8")
    print(f"[gen-news] ✅ {INDEX_OUT.name} (индекс)")

    # страницы по датам
    NEWS_DIR.mkdir(exist_ok=True)
    for i, d in enumerate(dates):
        prev_date = dates[i + 1] if i + 1 < len(dates) else None   # старее
        next_date = dates[i - 1] if i - 1 >= 0 else None           # свежее
        (NEWS_DIR / f"{d}.html").write_text(
            gen_date_page(d, archive, prev_date, next_date), encoding="utf-8")
    print(f"[gen-news] ✅ news/<date>.html — {len(dates)} страниц")

    # месячные архив-хабы news/<YYYY-MM>.html — SEO-лендинги «удары по нпз <месяц> <год>»
    months = briefs_by_month(archive.get("briefs", {}))
    yms = sorted(months.keys())  # по возрастанию — для соседей prev/next по месяцу
    for i, ym in enumerate(yms):
        prev_ym = yms[i - 1] if i - 1 >= 0 else None   # старее
        next_ym = yms[i + 1] if i + 1 < len(yms) else None  # свежее
        (NEWS_DIR / f"{ym}.html").write_text(
            gen_month_page(ym, months[ym], archive, prev_ym, next_ym), encoding="utf-8")
    print(f"[gen-news] ✅ news/<YYYY-MM>.html — {len(yms)} месячных хабов ({', '.join(yms)})")

    # nav/footer в news.html + news/*.html — заполняет плейсхолдер выше единым
    # меню/футером из реестра (иначе свежесгенеренные страницы теряют
    # Радар/Аналитику до ручного перезапуска build-nav.py).
    _r = subprocess.run(["python3", str(ROOT / "agents" / "build-nav.py")], capture_output=True, text=True)
    if _r.returncode != 0:
        raise RuntimeError("build-nav.py failed:\n" + _r.stderr)
    print("[gen-news] ✅ nav/footer (agents/build-nav.py)")

    # sitemap — единый полный генератор (индекс + ВСЕ лендинги + архив news),
    # чтобы новостная сборка НЕ затирала посадочные (фикс 2026-07-08).
    _r = subprocess.run(["python3", str(ROOT / "seo" / "generate-sitemap.py")], capture_output=True, text=True)
    if _r.returncode != 0:
        raise RuntimeError("generate-sitemap.py failed:\n" + _r.stderr)
    print(f"[gen-news] ✅ {SITEMAP_OUT.name} (полный, через seo/generate-sitemap.py)")

    # RSS-фид + Google News sitemap для сводок (agents/gen-rss.py).
    _r = subprocess.run(["python3", str(ROOT / "agents" / "gen-rss.py")], capture_output=True, text=True)
    if _r.returncode != 0:
        raise RuntimeError("gen-rss.py failed:\n" + _r.stderr)
    print("[gen-news] ✅ rss.xml + news-sitemap.xml (agents/gen-rss.py)")
    print(f"[gen-news] Готово. Свежая сводка: {rus_date(dates[0]) if dates else '—'}")


if __name__ == "__main__":
    main()
