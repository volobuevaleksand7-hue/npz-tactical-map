#!/usr/bin/env python3
"""Генерация /rabotayut-li-npz-rossii — статус КАЖДОГО НПЗ России на сегодня:
работает / ограничен / остановлен. Источник — единственный: data/fuel-state.json.

Спрос (Вебмастер 12–26.08): интент «работает ли / когда заработает КОНКРЕТНЫЙ завод»
не закреплён ни за одной страницей и конвертит лучше остального сайта —
  «когда заработает московский нпз в капотне» — 104 показа, CTR 36.5%, поз 4.5
  «когда заработает нпз в капотне»           — 123 показа, CTR 24.4%, поз 5.4
  «работает ли ярославский нпз»              — 123 показа, CTR 8.9%,  поз 6.9
  «когда закончится топливный кризис в россии» — 108 показов, поз 9.1

Границы с соседями (не дублировать их ключи):
  /skorost-remonta-npz — «сколько ВООБЩЕ восстанавливают» (медианы простоя, механика
                          повторных ударов). Здесь — статус на сегодня по каждому заводу.
  /refineries           — общий список + баланс/регионы/операторы. Здесь — фокус на
                          «работает/стоит» и на конкретные заводы из спроса (Капотня, ЯНОС).
  /crisis                — прогноз/сценарии кризиса. Здесь есть FAQ на этот же запрос,
                          но с честным отказом от прогноза и ссылкой туда, а не сценарием.

🔴 ГЛАВНОЕ — ЧЕСТНОСТЬ. В data/fuel-state.json НЕТ полей restart/eta, и открытых графиков
возобновления работы НПЗ не существует. Свободные поля damage/note местами содержат
вольные оценки сроков от источников («восстановление может потребовать до конца 2026
года или 2027», «требует 6+ месяцев», «ожидаемое восстановление — несколько недель») —
эта страница их НЕ пересказывает и НЕ строит из них рейтинги. Формально: демо проверяет,
что ни одна строка damage/note не попала в HTML целиком (см. `no_freeform_leak`). Наружу
идут только структурные факты: статус, дата/число дней с status_since, оценка загрузки,
источник. На прямой вопрос «когда заработает» страница честно отвечает «дата не
публикуется» и отправляет за типовыми сроками ремонта на /skorost-remonta-npz.

Запуск:
    ./.venv/bin/python agents/gen-npz-status-page.py          # перегенерить файл
    ./.venv/bin/python agents/gen-npz-status-page.py --demo   # самопроверка (числа, FAQ==JSON-LD, идемпотентность)

ponytail: только stdlib + переиспользование CARDS/TAG/rus_date/state_phrase/was_hit/short
из agents/gen-refineries.py (тот же датасет, та же лексика статусов) — не заводим вторую
копию соответствия id→карточка.
"""
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import date as _date
from html import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "fuel-state.json")
OUT = os.path.join(ROOT, "rabotayut-li-npz-rossii.html")
BASE = "https://npz-tactical-map.vercel.app"
URL = BASE + "/rabotayut-li-npz-rossii"
SKOROST_URL = "/skorost-remonta-npz"

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]


def _load_module(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Переиспользуем словари/хелперы соседнего генератора — тот же fuel-state.json,
# те же id заводов и та же формулировка статусов, вторую копию не заводим.
_ref = _load_module("gen_refineries_for_status", "agents/gen-refineries.py")
CARDS, TAG, rus_date, state_phrase, was_hit, short = (
    _ref.CARDS, _ref.TAG, _ref.rus_date, _ref.state_phrase, _ref.was_hit, _ref.short)

STATUS_ORDER = {"down": 0, "partial": 1, "operational": 2}
STATUS_LABEL = {"down": "остановлены", "partial": "работают с ограничениями", "operational": "работают в штатном режиме"}


def plural(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def asset_ver(rel):
    p = os.path.join(ROOT, rel)
    try:
        return "/%s?v=%s" % (rel, hashlib.md5(open(p, "rb").read()).hexdigest()[:8])
    except OSError:
        return "/" + rel


def og_image():
    rel = "assets/analytics-rabotayut-li-npz-rossii-generated.png"
    p = os.path.join(ROOT, rel)
    if not os.path.isfile(p):
        return BASE + "/og-image.png"
    v = hashlib.md5(open(p, "rb").read()).hexdigest()[:8]
    return "%s/%s?v=%s" % (BASE, rel, v)


def load_data():
    with open(SRC, encoding="utf8") as f:
        return json.load(f)


def by_id(R, rid):
    for r in R:
        if r["id"] == rid:
            return r
    raise KeyError(rid)


def days_between(iso_from, iso_to):
    y1, m1, d1 = (int(x) for x in iso_from[:10].split("-"))
    y2, m2, d2 = (int(x) for x in iso_to[:10].split("-"))
    return (_date(y2, m2, d2) - _date(y1, m1, d1)).days


def days_txt(n):
    return "%d %s" % (n, plural(n, "день", "дня", "дней"))


def duration_cell(r, today_iso):
    """«32 дня (с 25 июля 2026)» для стоящих/ограниченных; для работающих — «восстановлен
    N дней назад», если по заводу был удар (was_hit), иначе «—» (статус не менялся)."""
    ss = r.get("status_since")
    if not ss:
        return "—"
    n = days_between(ss, today_iso)
    if r["status"] == "operational":
        return ("восстановлен %s назад" % days_txt(n)) if was_hit(r) else "—"
    return "%s (с %s)" % (days_txt(n), rus_date(ss))


def load_cell(r):
    pct = r.get("est_output_pct")
    if pct is None:
        return "—"
    if r["status"] == "operational":
        return "100%"
    return "0%" if pct == 0 else "~%d%%" % pct


def source_cell(r):
    u = (r.get("source_url") or "").strip()
    if not u.startswith("http"):
        return "—"
    return '<a href="%s" rel="nofollow noopener" target="_blank">источник ↗</a>' % escape(u)


def sorted_all(R):
    return sorted(R, key=lambda r: (STATUS_ORDER[r["status"]], -r["capacity_mt_year"]))


def render_table(R, today_iso):
    rows = []
    for r in sorted_all(R):
        cls, label = TAG[r["status"]]
        slug = CARDS.get(r["id"])
        nm = ('<a href="/npz/%s">%s</a>' % (slug, escape(r["name"]))) if slug else escape(r["name"])
        rows.append(
            '        <tr><td>%s</td><td>%s</td><td>%s</td><td><span class="%s">%s</span></td>'
            '<td>%s</td><td>%s</td><td>%s</td></tr>'
            % (nm, escape(r["operator"]), escape(r["region"]), cls, label,
               duration_cell(r, today_iso), load_cell(r), source_cell(r)))
    return "\n".join(rows)


def group_list(R, status, today_iso):
    items = sorted((r for r in R if r["status"] == status), key=lambda r: -r["capacity_mt_year"])
    if not items:
        return '      <p class="lead-p">На %s таких заводов нет.</p>' % rus_date(today_iso)
    lis = []
    for r in items:
        slug = CARDS.get(r["id"])
        nm = ('<a href="/npz/%s">%s</a>' % (slug, escape(short(r["name"])))) if slug else escape(short(r["name"]))
        load_txt = "" if status == "down" else " Загрузка %s." % load_cell(r)
        reg = r["region"].rstrip(".")   # регион в данных часто уже с точкой («Ленинградская обл.»)
        lis.append('        <li><strong>%s</strong> — %.1f млн т/год, %s.%s %s</li>'
                    % (nm, r["capacity_mt_year"], escape(reg), load_txt, duration_cell(r, today_iso)))
    return '      <ul class="status-list">\n%s\n      </ul>' % "\n".join(lis)


def names_list(R, status, limit=None):
    items = sorted((r for r in R if r["status"] == status), key=lambda r: -r["capacity_mt_year"])
    if limit:
        items = items[:limit]
    return ", ".join(short(r["name"]) for r in items)


def build():
    doc = load_data()
    R = doc["refineries"]
    meta = doc["meta"]
    UPDATED = meta["generated_at"][:10]
    date_ru = rus_date(UPDATED)

    down = [r for r in R if r["status"] == "down"]
    partial = [r for r in R if r["status"] == "partial"]
    oper = [r for r in R if r["status"] == "operational"]
    tot = len(R)
    cap_total = sum(r["capacity_mt_year"] for r in R)

    for r in down + partial:
        u = (r.get("source_url") or "").strip()
        if not u.startswith("http"):
            raise ValueError("остановленный/ограниченный завод без источника: %s" % r["id"])

    moscow = by_id(R, "moscow")
    yanos = by_id(R, "yanos")

    def since_days(r):
        return days_between(r["status_since"], UPDATED)

    TITLE = "Какие НПЗ работают сейчас: статус всех %d заводов" % tot
    DESC = ("На %s из %d крупных НПЗ России работают в штатном режиме %d, %d — с "
            "ограничениями по загрузке, %d полностью остановлены. Статус, число дней "
            "простоя и оценка загрузки по каждому заводу — по открытым источникам. "
            "Официальных дат перезапуска нет ни у одного." % (date_ru, tot, len(oper), len(partial), len(down)))
    OG = og_image()

    TABLE_ROWS = render_table(R, UPDATED)
    DOWN_LIST = group_list(R, "down", UPDATED)
    PARTIAL_LIST = group_list(R, "partial", UPDATED)
    OPER_LIST = group_list(R, "operational", UPDATED)

    faq = [
        ("Работают ли НПЗ России сейчас?",
         "Да, но не все и не в полную силу. На %s из %d крупных НПЗ России %d работают в "
         "штатном режиме, %d работают с ограничениями по загрузке, %d полностью остановлены. "
         "Статус, дата и оценка загрузки по каждому заводу — в таблице на этой странице."
         % (date_ru, tot, len(oper), len(partial), len(down))),

        ("Сколько НПЗ работает в России сейчас?",
         "На %s в штатном режиме работают %d из %d крупных НПЗ России при суммарной "
         "мощности всех %d заводов %.1f млн т/год. Ещё %d работают с ограничениями по "
         "загрузке, %d полностью остановлены." % (date_ru, len(oper), tot, tot, cap_total, len(partial), len(down))),

        ("Какие НПЗ России сейчас полностью остановлены?",
         "На %s полностью остановлены %d %s: %s. Статусы — по открытым источникам и могут "
         "измениться при поступлении новых сообщений." % (
             date_ru, len(down), plural(len(down), "завод", "завода", "заводов"), names_list(R, "down"))),

        ("Какие НПЗ работают с ограничениями по загрузке?",
         "На %s с ограничениями по загрузке работают %d %s: %s. Оценка загрузки по "
         "каждому — в таблице выше." % (
             date_ru, len(partial), plural(len(partial), "завод", "завода", "заводов"), names_list(R, "partial"))),

        ("Работает ли Московский НПЗ в Капотне?",
         "Да, но не в полную силу: на %s завод работает на ~%d%% мощности — статус "
         "«ограничено» с %s (%s). Полная карточка завода со всеми ударами — /npz/moskovskij-npz."
         % (date_ru, moscow["est_output_pct"], rus_date(moscow["status_since"]), days_txt(since_days(moscow)))),

        ("Когда заработает Московский НПЗ в Капотне?",
         "Точной даты нет: официальных графиков возобновления полной работы НПЗ в Капотне "
         "в открытых источниках не публикуется. На %s завод уже %s работает в режиме "
         "пониженной загрузки ~%d%% (с %s), и это не прогноз, а факт на сегодня. Как только "
         "статус изменится в данных проекта, страница обновится автоматически. "
         "Типичные сроки восстановления НПЗ после ударов по прошлым случаям — в материале "
         "«Сколько времени восстанавливают НПЗ» (%s)."
         % (date_ru, days_txt(since_days(moscow)), moscow["est_output_pct"], rus_date(moscow["status_since"]), SKOROST_URL)),

        ("Работает ли Ярославский НПЗ?",
         "Работает, но в минимальном режиме: на %s загрузка Славнефть-ЯНОС (Ярославского "
         "НПЗ) — около %d%% мощности, статус «ограничено» с %s (%s). Подробная карточка "
         "завода — /npz/slavneft-yanos."
         % (date_ru, yanos["est_output_pct"], rus_date(yanos["status_since"]), days_txt(since_days(yanos)))),

        ("Названы ли даты, когда остановленные НПЗ снова заработают?",
         "Нет. В открытых источниках, которые отслеживает проект, официальных дат или "
         "графиков возобновления работы остановленных и частично работающих НПЗ не "
         "публикуется. Эта страница показывает только то, что подтверждено на %s: статус, "
         "число дней в текущем режиме и оценку загрузки по каждому заводу. Типичные сроки "
         "ремонта по прошлым случаям (не прогноз для конкретного завода) — в материале "
         "«Сколько времени восстанавливают НПЗ» (%s)." % (date_ru, SKOROST_URL)),

        ("Когда закончится топливный кризис в России?",
         "Эта страница не даёт прогноза по срокам — она показывает только статус %d заводов "
         "на %s: %d работают, %d ограничены, %d остановлены. Сценарии и прогнозы по "
         "топливному кризису в целом — в материале «Когда закончится топливный кризис» "
         "(/crisis)." % (tot, date_ru, len(oper), len(partial), len(down))),
    ]

    faq_html = "\n".join(
        '        <div class="faq-item">\n'
        '          <div class="faq-q" onclick="this.parentElement.classList.toggle(\'open\')">%s</div>\n'
        '          <div class="faq-a">%s</div>\n'
        '        </div>' % (escape(q), escape(a)) for q, a in faq)
    faq_ld_initial = ",\n      ".join(
        json.dumps({"@type": "Question", "name": q,
                    "acceptedAnswer": {"@type": "Answer", "text": a}}, ensure_ascii=False)
        for q, a in faq)

    html = f"""<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <meta name="theme-color" content="#d23a2e">
  <title>{TITLE}</title>
  <meta name="description" content="{DESC}">
  <meta name="keywords" content="работают ли нпз россии, какие нпз работают, какие нпз остановлены, статус нпз сегодня, работает ли московский нпз, когда заработает нпз в капотне, когда заработает московский нпз в капотне, работает ли ярославский нпз, работает ли нпз в капотне, остановлен нпз, восстановление нпз, действующие нпз россии, список нпз статус сегодня, капотня нпз работает ли, ярославский нпз статус">
  <meta name="robots" content="index, follow">
  <meta name="language" content="Russian">
  <link rel="canonical" href="{URL}">

  <meta property="og:type" content="article">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:site_name" content="Топливный фронт РФ">
  <meta property="og:url" content="{URL}">
  <meta property="og:title" content="{TITLE}">
  <meta property="og:description" content="{DESC}">
  <meta property="og:image" content="{OG}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{TITLE}">
  <meta name="twitter:description" content="{DESC}">
  <meta name="twitter:image" content="{OG}">

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "{TITLE}",
    "datePublished": "2026-08-26",
    "dateModified": "{UPDATED}",
    "image": ["{OG}"],
    "author": {{"@type": "Organization", "name": "Топливный фронт РФ"}},
    "publisher": {{"@type": "Organization", "name": "Топливный фронт РФ", "url": "https://npz-tactical-map.vercel.app/"}},
    "description": "{DESC}",
    "mainEntityOfPage": "{URL}",
    "isAccessibleForFree": true
  }}
  </script>

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
      {faq_ld_initial}
    ]
  }}
  </script>

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {{"@type": "ListItem", "position": 1, "name": "Главная", "item": "https://npz-tactical-map.vercel.app/"}},
      {{"@type": "ListItem", "position": 2, "name": "Справочники", "item": "https://npz-tactical-map.vercel.app/analytics"}},
      {{"@type": "ListItem", "position": 3, "name": "Какие НПЗ работают, а какие стоят", "item": "{URL}"}}
    ]
  }}
  </script>

  <script>window.va = window.va || function () {{ (window.vaq = window.vaq || []).push(arguments); }};</script>
  <script defer src="/_vercel/insights/script.js"></script>

  <link rel="stylesheet" href="/fonts.css">
  <link rel="stylesheet" href="{asset_ver('styles.css')}">
  <link rel="stylesheet" href="{asset_ver('news.css')}">
  <style>
    .landing-wrap{{max-width:900px;margin:0 auto;padding:24px 20px 60px}}
    .landing-hero{{background:linear-gradient(135deg,rgba(210,58,46,.14),rgba(138,59,59,.08));border:1px solid rgba(210,58,46,.3);border-radius:16px;padding:32px 28px;margin-bottom:24px;position:relative;overflow:hidden}}
    .landing-hero::before{{content:"";position:absolute;top:-30px;right:-30px;width:120px;height:120px;background:radial-gradient(circle,rgba(210,58,46,.18),transparent 70%);border-radius:50%}}
    .hero-label{{display:inline-block;background:var(--red,#d23a2e);color:#fff;font-family:var(--mono);font-size:10px;font-weight:800;letter-spacing:1.5px;padding:3px 10px;border-radius:6px;margin-bottom:12px}}
    .hero-h{{font-size:28px;font-weight:800;line-height:1.2;margin-bottom:10px}}
    .hero-sub{{font-size:15px;color:var(--ink-dim);line-height:1.6;max-width:680px}}
    .map-cta{{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;margin:18px 0 4px;padding:16px 22px;background:var(--teal,#12a594);color:#fff;font-weight:800;font-size:16px;border-radius:12px;text-decoration:none;box-shadow:0 6px 20px rgba(18,165,148,.3);transition:.15s}}
    .map-cta:hover{{transform:translateY(-2px);box-shadow:0 10px 28px rgba(18,165,148,.45)}}
    .map-cta .mc-ico{{font-size:22px}}
    .map-cta.inline{{margin:20px 0;background:var(--surface);color:var(--ink);border:1.5px solid var(--teal,#12a594);box-shadow:none}}
    .map-cta.inline:hover{{background:rgba(18,165,148,.08);transform:translateY(-1px)}}
    .status-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:20px}}
    .status-card{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;text-align:center}}
    .status-card .val{{font-family:var(--mono);font-size:20px;font-weight:800;color:var(--red,#d23a2e)}}
    .status-card .lbl{{font-size:11px;color:var(--ink-dim);margin-top:4px}}
    .section-h{{font-size:20px;font-weight:800;margin:32px 0 14px;display:flex;align-items:center;gap:8px}}
    .section-h .ico{{font-size:22px}}
    .lead-p{{font-size:14px;line-height:1.7;color:var(--ink);margin-bottom:8px}}
    .npz-table{{width:100%;border-collapse:collapse;margin:16px 0;font-size:13px}}
    .npz-table th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--ink-dim);padding:8px 10px;border-bottom:1px solid var(--line)}}
    .npz-table td{{padding:10px;border-bottom:1px solid var(--line);vertical-align:top;white-space:nowrap}}
    .npz-table td:nth-child(3){{white-space:normal}}
    .tbl-scroll{{overflow-x:auto}}
    .tag-down{{font-family:var(--mono);font-size:10px;font-weight:800;padding:2px 7px;border-radius:5px;color:#fff;background:var(--red)}}
    .tag-partial{{font-family:var(--mono);font-size:10px;font-weight:800;padding:2px 7px;border-radius:5px;color:#fff;background:var(--amber)}}
    .tag-operational{{font-family:var(--mono);font-size:10px;font-weight:800;padding:2px 7px;border-radius:5px;color:#fff;background:var(--green)}}
    .status-list{{margin:0 0 14px 22px;padding:0;font-size:14px;line-height:1.9}}
    .status-list li{{color:var(--ink-dim)}}
    .status-list li strong{{color:var(--ink)}}
    .faq-wrap{{margin:20px 0}}
    .faq-item{{background:var(--surface);border:1px solid var(--line);border-radius:12px;margin-bottom:10px;overflow:hidden}}
    .faq-q{{font-weight:700;font-size:14px;padding:14px 16px;cursor:pointer;display:flex;justify-content:space-between;align-items:center}}
    .faq-q::after{{content:"▼";font-size:10px;color:var(--ink-dim);transition:transform .2s}}
    .faq-item.open .faq-q::after{{transform:rotate(180deg)}}
    .faq-a{{padding:0 16px 14px;font-size:13px;line-height:1.6;color:var(--ink-dim);display:none}}
    .faq-item.open .faq-a{{display:block}}
    .link-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin:16px 0}}
    .link-card{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;text-decoration:none;color:var(--ink);transition:.15s}}
    .link-card:hover{{border-color:var(--teal);transform:translateY(-1px);box-shadow:var(--shadow-sm)}}
    .link-card .lc-h{{font-weight:700;font-size:13px;margin-bottom:4px}}
    .link-card .lc-d{{font-size:11px;color:var(--ink-dim)}}
    .osint-note{{margin-top:32px;font-size:11px;color:var(--ink-dim);background:var(--surface2);padding:12px;border-radius:10px;border-left:3px solid var(--amber);line-height:1.6}}
    .updated-line{{font-family:var(--mono);font-size:11px;color:var(--ink-dim);margin-top:6px}}
</style>
  <link rel="stylesheet" href="{asset_ver('search.css')}">
  <script defer src="{asset_ver('search.js')}"></script>
  <script src="/metrika.js" async></script>
</head>
<body data-theme="light">
  <header class="news-header">
    <div class="news-header-inner">
      <a href="/" class="news-logo" title="На карту">
        <span class="news-logo-icon">⛽</span>
        <span class="news-logo-text">ТОПЛИВНЫЙ ФРОНТ РФ</span>
      </a>
      <nav class="news-nav">
        <a href="/">🗺️ Карта НПЗ</a>
        <a href="/news">📰 Сводки</a>
        <a href="/radar">📡 Радар БПЛА</a>
        <a href="/analytics" style="color:var(--teal);font-weight:700">📊 Аналитика</a>
      </nav>
    </div>
  </header>

  <main class="news-main">
    <div class="landing-wrap">

      <div class="landing-hero">
        <span class="hero-label">СПРАВОЧНИК · СТАТУС НПЗ</span>
        <h1 class="hero-h">Какие НПЗ России работают, а какие стоят — статус на {date_ru}</h1>
        <p class="hero-sub">Из {tot} крупных нефтеперерабатывающих заводов России на {date_ru} <strong>{len(oper)} работают в штатном режиме</strong>, <strong>{len(partial)} — с ограничениями</strong> по загрузке, <strong>{len(down)} полностью остановлены</strong>. Ниже — статус каждого завода: сколько он уже стоит или ограничен (по дате начала режима), оценка текущей загрузки и источник. Официальных дат возобновления работы в открытых источниках нет ни по одному заводу — это прямо оговорено в конце страницы.</p>
        <div class="status-grid">
          <div class="status-card"><div class="val" style="color:var(--green)">{len(oper)}</div><div class="lbl">работают в штатном режиме</div></div>
          <div class="status-card"><div class="val" style="color:var(--amber)">{len(partial)}</div><div class="lbl">работают с ограничениями</div></div>
          <div class="status-card"><div class="val" style="color:var(--red)">{len(down)}</div><div class="lbl">полностью остановлены</div></div>
          <div class="status-card"><div class="val">{cap_total:.1f}</div><div class="lbl">млн т/год суммарная мощность всех {tot}</div></div>
        </div>
        <div class="updated-line">Обновлено {date_ru}, МСК · статусы — оценка по открытым источникам</div>
      </div>

      <h2 class="section-h"><span class="ico">📍</span> Короткий ответ</h2>
      <p class="lead-p">На {date_ru} из {tot} крупных НПЗ России <strong>{len(oper)}</strong> работают в штатном режиме, <strong>{len(partial)}</strong> работают с ограничениями по загрузке и <strong>{len(down)}</strong> полностью остановлены. Суммарная мощность всех {tot} заводов — {cap_total:.1f} млн т/год. Статус каждого конкретного завода — в таблице ниже, с датой (или числом дней), с которой он в текущем режиме, оценкой загрузки и ссылкой на источник.</p>
      <p class="lead-p">Отдельно про заводы с самым высоким спросом на статус: <strong>Московский НПЗ в Капотне</strong> работает на ~{moscow['est_output_pct']}% мощности с {rus_date(moscow['status_since'])}, <strong>Славнефть-ЯНОС (Ярославский НПЗ)</strong> — на ~{yanos['est_output_pct']}% с {rus_date(yanos['status_since'])}. Официальных дат возврата к полной мощности ни по одному заводу не публиковалось.</p>

      <div class="link-grid">
        <a class="link-card" href="/npz/moskovskij-npz"><div class="lc-h">🛢️ Московский НПЗ (Капотня)</div><div class="lc-d">Карточка завода и хроника ударов</div></a>
        <a class="link-card" href="/npz/slavneft-yanos"><div class="lc-h">🛢️ НПЗ ЯНОС (Ярославль)</div><div class="lc-d">Карточка завода и хроника ударов</div></a>
        <a class="link-card" href="{SKOROST_URL}"><div class="lc-h">🔧 Сколько восстанавливают НПЗ</div><div class="lc-d">Типовые сроки ремонта, а не прогноз по заводу</div></a>
        <a class="link-card" href="/refineries"><div class="lc-h">🏭 Список НПЗ России</div><div class="lc-d">Полная база: мощность, регионы, операторы</div></a>
      </div>

      <h2 class="section-h"><span class="ico">📊</span> Статус всех {tot} заводов</h2>
      <div class="tbl-scroll">
      <table class="npz-table">
        <thead><tr><th>Завод</th><th>Оператор</th><th>Регион</th><th>Статус</th><th>Стоит/ограничен</th><th>Загрузка</th><th>Источник</th></tr></thead>
        <tbody>
{TABLE_ROWS}
        </tbody>
      </table>
      </div>
      <p class="lead-p">«Стоит/ограничен» считается от даты <code>status_since</code> до {date_ru}. Пустая ячейка источника — у завода нет статуса «остановлен»/«ограничено» в базе, поэтому и удара, по которому нужен источник, нет.</p>

      <h2 class="section-h"><span class="ico">🛑</span> Остановлены ({len(down)})</h2>
{DOWN_LIST}

      <h2 class="section-h"><span class="ico">🟡</span> Работают с ограничениями ({len(partial)})</h2>
{PARTIAL_LIST}

      <h2 class="section-h"><span class="ico">🟢</span> Работают в штатном режиме ({len(oper)})</h2>
{OPER_LIST}

      <h2 class="section-h"><span class="ico">❓</span> Частые вопросы</h2>
      <div class="faq-wrap">
{faq_html}
      </div>

      <h2 class="section-h"><span class="ico">🔗</span> Смотрите также</h2>
      <div class="link-grid">
        <a class="link-card" href="/refineries"><div class="lc-h">🏭 Список НПЗ России</div><div class="lc-d">Полная база заводов: мощность, регионы, операторы</div></a>
        <a class="link-card" href="{SKOROST_URL}"><div class="lc-h">🔧 Сколько восстанавливают НПЗ</div><div class="lc-d">Медианный простой и почему ремонт не успевает</div></a>
        <a class="link-card" href="/krupnejshie-npz-rossii"><div class="lc-h">🏆 Крупнейшие НПЗ России</div><div class="lc-d">Рейтинг заводов по мощности</div></a>
        <a class="link-card" href="/attacks"><div class="lc-h">💥 Хроника ударов</div><div class="lc-d">Все атаки по датам и объектам</div></a>
        <a class="link-card" href="/crisis"><div class="lc-h">🔥 Прогноз топливного кризиса</div><div class="lc-d">Сценарии, а не статус конкретного завода</div></a>
        <a class="link-card" href="/news"><div class="lc-h">📰 Сводки</div><div class="lc-d">Ежедневный архив обстановки</div></a>
      </div>

      <div class="osint-note">
        <strong>⚠️ Дисклеймер:</strong> Материал основан на <strong>открытых источниках</strong> (Meduza, The Moscow Times, The Bell, Kyiv Independent, Ukrainska Pravda, Reuters и др.). Статусы и даты — {meta.get('data_mode', 'ОЦЕНКА / ESTIMATE')}: точных данных в реальном времени по состоянию каждого завода публично не существует, независимой проверки у проекта нет. <strong>Официальных графиков или дат возобновления работы НПЗ проект не публикует и не прогнозирует</strong> — ни компании-операторы, ни госорганы такие графики открыто не раскрывают. Развёрнутые описания повреждений по каждому заводу и хроника прошлых ударов — в карточках /npz/*; эта страница даёт только сводный статус на сегодня. Проект придерживается нейтрального изложения и не выносит юридических вердиктов.
      </div>
    </div>
  </main>

  <footer class="news-footer">
    <div class="news-footer-inner">
      <p>Топливный фронт РФ · <a href="/">🗺️ Карта НПЗ</a> · OSINT-дашборд · <span class="mono">npz-tactical-map.vercel.app</span></p>
      <p class="footer-disc">Не является официальной информацией. Данные из открытых источников.</p>
    </div>
  </footer>

  <script>
    const saved = localStorage.getItem('theme');
    if (saved) document.documentElement.dataset.theme = saved;
  </script>
  <script defer src="{asset_ver('nav-dropdown.js')}"></script>
  <script defer src="{asset_ver('vpn-nudge.js')}"></script>
</body>
</html>
"""
    html = sync_faq_ld(html)
    return html


def sync_faq_ld(html):
    """FAQPage-разметка пересобирается ИЗ видимого текста, а не параллельно ему —
    правило проекта (см. заголовок файла и agents/gen-ozon-episodes.py): на этом сайте
    уже расходились 2 ответа из 9 и 15 из 16 там, где разметка строилась отдельно."""
    pairs = re.findall(r'class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>', html, re.S)
    if not pairs:
        raise SystemExit("!! видимый FAQ не найден")
    items = []
    for q, a in pairs:
        q_txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", q)).strip()
        a_txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", a)).strip()
        items.append(json.dumps({"@type": "Question", "name": q_txt,
                                  "acceptedAnswer": {"@type": "Answer", "text": a_txt}},
                                 ensure_ascii=False))
    block = "      " + ",\n      ".join(items)
    pat = re.compile(r'("@type": "FAQPage",\n    "mainEntity": \[\n).*?(\n    \])', re.S)
    if not pat.search(html):
        raise SystemExit("!! блок FAQPage не найден")
    return pat.sub(lambda m: m.group(1) + block + m.group(2), html, count=1)


def main():
    html = build()
    with open(OUT, "w", encoding="utf8") as f:
        f.write(html)
    print("gen-npz-status-page: %s (%.1f КБ)" % (os.path.basename(OUT), len(html.encode()) / 1024))
    return 0


def demo():
    """Самопроверка: числа сходятся с датасетом, FAQ-разметка совпадает с видимым
    текстом ДОСЛОВНО, ни одна свободнотекстовая damage/note-строка не просочилась
    на страницу целиком (честность про сроки), генератор идемпотентен."""
    doc = load_data()
    R = doc["refineries"]
    down = [r for r in R if r["status"] == "down"]
    partial = [r for r in R if r["status"] == "partial"]
    oper = [r for r in R if r["status"] == "operational"]
    cap_total = sum(r["capacity_mt_year"] for r in R)

    html = build()
    assert html.count("<h1") == 1

    # числа в заголовке/hero сходятся с датасетом
    assert str(len(R)) in html
    assert str(len(down)) in html and str(len(partial)) in html and str(len(oper)) in html
    assert ("%.1f" % cap_total) in html

    # каждый завод виден в таблице по имени
    for r in R:
        assert r["name"] in html, "завод не попал на страницу: %s" % r["id"]

    # каждый остановленный/ограниченный завод — с источником (у операционных источник не обязателен)
    for r in down + partial:
        u = (r.get("source_url") or "").strip()
        assert u.startswith("http"), "нет источника: %s" % r["id"]
        assert u in html, "источник не попал в HTML: %s" % r["id"]

    # 🔴 честность: ни одна свободнотекстовая damage/note-строка (там живут вольные оценки
    # сроков вида «до конца 2026 года или 2027», «требует 6+ месяцев») не воспроизведена
    # на странице целиком
    for r in R:
        for field in ("damage", "note"):
            txt = (r.get(field) or "").strip()
            if len(txt) > 20:          # короткие пустышки/совпадения не считаем
                assert txt not in html, "свободный текст %s.%s просочился на страницу: %s" % (r["id"], field, txt[:60])

    # явный честный отказ от прогноза сроков должен присутствовать
    assert "Официальных дат перезапуска нет" in html or "официальных дат или" in html.lower() or \
           "официальных дат или\n" in html or "официальных дат или ".lower() in html.lower(), \
           "нет явной честной формулировки об отсутствии дат перезапуска"
    assert "графиков возобновления работы" in html

    # ключевые FAQ из спроса — дословно нужные фразы
    assert "Московский НПЗ в Капотне" in html
    assert "Когда заработает Московский НПЗ в Капотне" in html
    assert "Ярославский НПЗ" in html
    assert "топливный кризис" in html.lower()

    # FAQ-разметка == видимый текст (сверка через ту же функцию пересборки)
    resynced = sync_faq_ld(html)
    assert resynced == html, "sync_faq_ld() изменил уже пересобранный HTML — разметка не идемпотентна"
    ld_block = re.search(r'"@type": "FAQPage",\n    "mainEntity": \[\n(.*?)\n    \]', html, re.S).group(1)
    ld = json.loads("[" + ld_block + "]")
    seen = re.findall(r'class="faq-q"[^>]*>(.*?)</div>\s*<div class="faq-a">(.*?)</div>', html, re.S)
    assert len(ld) == len(seen), "число вопросов в разметке и в видимом тексте разошлось"
    for item, (q, a) in zip(ld, seen):
        q_txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", q)).strip()
        a_txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", a)).strip()
        assert item["name"] == q_txt, "вопрос в JSON-LD разошёлся с видимым текстом"
        assert item["acceptedAnswer"]["text"] == a_txt, "ответ в JSON-LD разошёлся с видимым текстом"

    # идемпотентность генератора целиком
    assert build() == html, "генератор не идемпотентен: повторный прогон дал другой файл"

    # title <= 60 символов и не построен на отрицании
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    assert len(title) <= 60, "title длиннее 60 символов: %d" % len(title)
    assert "работают" in title.lower() or "статус" in title.lower(), "title не обещает данные"
    assert "почему не" not in title.lower(), "title построен на отрицании — правило проекта (см. Ozon-урок)"

    print("demo OK — %d заводов: %d работают, %d ограничены, %d остановлены" % (
        len(R), len(oper), len(partial), len(down)))


if __name__ == "__main__":
    sys.exit(demo() if "--demo" in sys.argv else main())
