#!/usr/bin/env python3
"""Генерация /kakie-sklady-wildberries-ostalis — список складов WB/Ozon, по которым
на текущий момент нет сообщений об ударе: город, регион, оператор, тип объекта,
разбивка по федеральным округам.

Разведение интентов внутри кластера складов (8 живых страниц в data/seo-topics.jsonl):
  /skolko-skladov-wildberries-ozon     — «СКОЛЬКО»: масштаб сети целиком, счётчики, доля выбывшего
  /ataki-na-sklady-wildberries-hronika — хронология ЭПИЗОДОВ ударов и «какие ПОСТРАДАЛИ»
  /karta-skladov-wildberries           — карта
  здесь                                — «КАКИЕ»: перечень УЦЕЛЕВШИХ объектов, по округам/регионам

Данные и загрузчик — те же, что у чемпиона: agents/gen-warehouses-page.py.load_data().
Модуль подключается через importlib (дефис в имени файла блокирует обычный import —
тот же паттерн, что уже используют agents/gen-rss.py, agents/collect.py, agents/azs-pages.py).

Запуск:  python3 agents/gen-survivors-page.py
Проверка: python3 agents/gen-survivors-page.py --demo
"""
import importlib.util
import json
import os
import sys
from collections import defaultdict
from html import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_spec = importlib.util.spec_from_file_location(
    "gen_warehouses_page", os.path.join(ROOT, "agents", "gen-warehouses-page.py"))
gwp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gwp)

OUT = os.path.join(ROOT, "kakie-sklady-wildberries-ostalis.html")
BASE = gwp.BASE
URL = BASE + "/kakie-sklady-wildberries-ostalis"
TITLE = "Какие склады Wildberries и Ozon остались в 2026 году: полный список"
DESC = ("Список складов Wildberries (ВБ) и Ozon, по которым на текущий момент нет сообщений об "
        "ударе БПЛА: город, регион, оператор и федеральный округ — с разбивкой по округам.")

# Регион -> федеральный округ. Покрывает регионы, встречающиеся в data/warehouses.json на
# 06.08.2026 (полный список сверяется в demo()). Новый регион без записи не роняет генератор —
# уходит в бакет «не определён» последним, но словарь стоит дополнить при появлении.
OKRUG = {
    "Москва": "Центральный", "Московская область": "Центральный",
    "Ивановская область": "Центральный", "Тульская область": "Центральный",
    "Воронежская область": "Центральный", "Владимирская область": "Центральный",
    "Рязанская область": "Центральный", "Тверская область": "Центральный",
    "Тамбовская область": "Центральный",
    "Санкт-Петербург": "Северо-Западный", "Ленинградская область": "Северо-Западный",
    "Краснодарский край": "Южный", "Волгоградская область": "Южный",
    "Республика Крым": "Южный",
    "Ставропольский край": "Северо-Кавказский",
    "Татарстан": "Приволжский", "Самарская область": "Приволжский",
    "Саратовская область": "Приволжский", "Пензенская область": "Приволжский",
    "Пермский край": "Приволжский", "Республика Удмуртия": "Приволжский",
    "Свердловская область": "Уральский",
    "Новосибирская область": "Сибирский",
    "Бурятия": "Дальневосточный", "Хабаровский край": "Дальневосточный",
}
OKRUG_ORDER = ["Центральный", "Северо-Западный", "Южный", "Северо-Кавказский",
               "Приволжский", "Уральский", "Сибирский", "Дальневосточный", "не определён"]
TYPE_LABEL = {"rc": "РЦ Wildberries", "ffc": "ФЦ Ozon"}


def okrug_for(region):
    return OKRUG.get(region, "не определён")


def okrug_groups(ok):
    """[(округ, [объекты]), ...] в фиксированном порядке округов, регион+имя внутри."""
    buckets = defaultdict(list)
    for w in ok:
        buckets[okrug_for(w["region"])].append(w)
    return [(o, sorted(buckets[o], key=lambda w: (w["region"], w["operator"], w["name"])))
            for o in OKRUG_ORDER if buckets.get(o)]


def survivors_list_html(ok):
    def card(w):
        op = "WB" if w["operator"] == "wb" else "OZON"
        t = TYPE_LABEL.get(w.get("type", ""), w.get("type", ""))
        addr = escape(w.get("address") or w["region"])
        return ('        <div class="wh-ok-card"><div class="wh-ok-top">'
                '<span class="wh-ok-op">%s</span><span class="wh-ok-type">%s</span></div>'
                '<div class="wh-ok-city">%s</div><div class="wh-ok-region">%s</div>'
                '<div class="wh-ok-addr">%s</div></div>'
                % (op, t, escape(w["name"]), escape(w["region"]), addr))

    parts = []
    for okrug, items in okrug_groups(ok):
        parts.append('      <div class="wh-ok-op-h">%s федеральный округ (%d)</div>\n'
                      '      <div class="wh-ok-grid">\n%s\n      </div>\n'
                      % (okrug, len(items), "\n".join(card(w) for w in items)))
    return "".join(parts)


def compare_operators(ok):
    """Данные для секции «чем WB отличается от Ozon» — считается из датасета, не заявляется."""
    wb = [w for w in ok if w["operator"] == "wb"]
    oz = [w for w in ok if w["operator"] == "ozon"]
    wb_okr = sorted({okrug_for(w["region"]) for w in wb})
    oz_okr = sorted({okrug_for(w["region"]) for w in oz})
    wb_types = {w.get("type") for w in wb}
    oz_types = {w.get("type") for w in oz}
    only_wb = [o for o in wb_okr if o not in oz_okr]
    only_oz = [o for o in oz_okr if o not in wb_okr]
    return {
        "wb": wb, "oz": oz, "wb_okr": wb_okr, "oz_okr": oz_okr,
        "wb_reg": len({w["region"] for w in wb}), "oz_reg": len({w["region"] for w in oz}),
        "wb_types": wb_types, "oz_types": oz_types, "only_wb": only_wb, "only_oz": only_oz,
    }


def build():
    doc = gwp.load_data()
    wh = doc["warehouses"]
    net = doc["meta"]["network"]
    hits = [w for w in wh if w["status"] == "hit"]
    ok = [w for w in wh if w["status"] == "ok"]
    wb_ok = [w for w in ok if w["operator"] == "wb"]
    oz_ok = [w for w in ok if w["operator"] == "ozon"]
    UPDATED = doc["meta"]["generated_at"][:10]
    UPD_RU = gwp.rus(UPDATED)
    cmp_ = compare_operators(ok)
    n_okrugs = len({okrug_for(w["region"]) for w in ok})
    LIST_HTML = survivors_list_html(ok)

    only_wb_txt = ("Только у Wildberries среди уцелевших объектов есть округ %s. " % ", ".join(cmp_["only_wb"])
                   if cmp_["only_wb"] else "")
    only_oz_txt = ("Только у Ozon — %s. " % ", ".join(cmp_["only_oz"]) if cmp_["only_oz"] else "")
    type_txt = (("Все уцелевшие объекты Wildberries в выборке — распределительные центры (rc), "
                 "все объекты Ozon — фулфилмент-центры (ffc): так эти сети обозначают свои крупные узлы "
                 "в открытых данных, используемых проектом.")
                if cmp_["wb_types"] <= {"rc"} and cmp_["oz_types"] <= {"ffc"} else
                "Типы объектов у обеих сетей смешанные, единого правила по типу нет.")

    faq = [
        ("Какие склады Wildberries (ВБ) остались?",
         "На %s в открытых данных проекта нет сообщений об ударе по %d складским объектам Wildberries "
         "из %d в выборке. Полный перечень с городом и регионом — в таблице на этой странице. Это не "
         "подтверждение того, что перечисленные объекты работают в штатном режиме: это лишь отсутствие "
         "сообщений об ударах по ним."
         % (UPD_RU, len(wb_ok), sum(1 for w in wh if w["operator"] == "wb"))),
        ("Какие склады вайлдберриз остались, а какие пострадали?",
         "Пострадавшие объекты (все — Wildberries) перечислены с датами и источниками на странице "
         "«Сколько складов у Wildberries и Ozon» и в хронике эпизодов. Здесь — обратный список: %d "
         "объектов Wildberries, по которым на %s сообщений об ударе нет."
         % (len(wb_ok), UPD_RU)),
        ("Какие склады остались у Ozon?",
         "На %s среди объектов Ozon в выборке проекта подтверждённых ударов БПЛА нет ни по одному: "
         "все %d фулфилмент-центра Ozon значатся без сообщений об ударе. Это объекты, о которых удалось "
         "собрать координаты и адрес по открытым источникам, а не вся сеть Ozon."
         % (UPD_RU, len(oz_ok))),
        ("Значит ли отсутствие склада в списке поражённых, что он работает исправно?",
         "Нет. Отсутствие объекта среди поражённых — это отсутствие сообщений об ударе по нему в "
         "открытых источниках на %s, а не подтверждение того, что склад работает в штатном режиме. "
         "Независимая проверка исправности объектов проектом не проводится." % UPD_RU),
        ("Чем этот список отличается от страницы «сколько складов осталось»?",
         "«Сколько складов у Wildberries и Ozon» отвечает на вопрос о МАСШТАБЕ сети целиком — сколько "
         "всего комплексов, сколько поражено, какая доля площадей выбыла. Эта страница — ПЕРЕЧЕНЬ "
         "конкретных %d объектов с городом, регионом и федеральным округом, без общей статистики сети."
         % len(ok)),
        ("Это весь список складов Wildberries и Ozon?",
         "Нет. В выборке проекта — %d крупных объекта (%d Wildberries, %d Ozon): это распределительные "
         "и фулфилмент-центры, по которым удалось собрать координаты и адрес по открытым источникам. "
         "У Wildberries, по собственным данным компании, свыше %d складских комплексов — сортировочные "
         "центры и пункты выдачи в выборку не входят, поэтому полная сеть шире этого списка."
         % (len(wh), sum(1 for w in wh if w["operator"] == "wb"),
            sum(1 for w in wh if w["operator"] == "ozon"), net["wb"]["complexes"])),
        ("В каких федеральных округах остались склады?",
         "Уцелевшие объекты выборки встречаются в %d федеральных округах. У Wildberries — %d округов "
         "(%s), у Ozon — %d округов (%s). %s%sПолная разбивка по округам — в таблице выше."
         % (n_okrugs, len(cmp_["wb_okr"]), ", ".join(cmp_["wb_okr"]),
            len(cmp_["oz_okr"]), ", ".join(cmp_["oz_okr"]), only_wb_txt, only_oz_txt)),
        ("Как часто обновляется список?",
         "Список пересчитывается из data/warehouses.json при каждом прогоне генератора страницы — "
         "как только по объекту появляется подтверждённый удар, он переходит из уцелевших в поражённые "
         "на обеих страницах кластера. Последнее обновление — %s." % UPD_RU),
    ]
    faq_ld = ",\n      ".join(
        json.dumps({"@type": "Question", "name": q,
                    "acceptedAnswer": {"@type": "Answer", "text": a}}, ensure_ascii=False)
        for q, a in faq)
    faq_html = "\n".join(
        '        <div class="faq-item">\n'
        '          <div class="faq-q" onclick="this.parentElement.classList.toggle(\'open\')">%s</div>\n'
        '          <div class="faq-a">%s</div>\n'
        '        </div>' % (escape(q), escape(a)) for q, a in faq)

    return f"""<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <meta name="theme-color" content="#d23a2e">
  <title>{TITLE}</title>
  <meta name="description" content="{DESC}">
  <meta name="keywords" content="какие склады вб остались, какие склады вайлдберриз остались, какие склады остались у вб, какие склады wildberries остались, какие склады ozon остались, список складов wildberries, список складов вб, склады вб по регионам, склады wildberries по округам">
  <meta name="robots" content="index, follow">
  <meta name="language" content="Russian">
  <link rel="canonical" href="{URL}">

  <meta property="og:type" content="article">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:site_name" content="Топливный фронт РФ">
  <meta property="og:url" content="{URL}">
  <meta property="og:title" content="{TITLE}">
  <meta property="og:description" content="{DESC}">
  <meta property="og:image" content="{BASE}/og-image.png">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{TITLE}">
  <meta name="twitter:description" content="{DESC}">
  <meta name="twitter:image" content="{BASE}/og-image.png">

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "{TITLE}",
    "datePublished": "{UPDATED}",
    "dateModified": "{UPDATED}",
    "image": ["{BASE}/og-image.png"],
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
      {faq_ld}
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
      {{"@type": "ListItem", "position": 3, "name": "Какие склады Wildberries и Ozon остались", "item": "{URL}"}}
    ]
  }}
  </script>

  <script>window.va = window.va || function () {{ (window.vaq = window.vaq || []).push(arguments); }};</script>
  <script defer src="/_vercel/insights/script.js"></script>

  <link rel="stylesheet" href="/fonts.css">
  <link rel="stylesheet" href="/styles.css?v=6c4ccd2f">
  <link rel="stylesheet" href="/news.css?v=e2bbf493">
  <style>
    .landing-wrap{{max-width:900px;margin:0 auto;padding:24px 20px 60px}}
    .landing-hero{{background:linear-gradient(135deg,rgba(210,58,46,.14),rgba(138,59,59,.08));border:1px solid rgba(210,58,46,.3);border-radius:16px;padding:32px 28px;margin-bottom:24px;position:relative;overflow:hidden}}
    .landing-hero::before{{content:"";position:absolute;top:-30px;right:-30px;width:120px;height:120px;background:radial-gradient(circle,rgba(210,58,46,.18),transparent 70%);border-radius:50%}}
    .hero-label{{display:inline-block;background:var(--red,#d23a2e);color:#fff;font-family:var(--mono);font-size:10px;font-weight:800;letter-spacing:1.5px;padding:3px 10px;border-radius:6px;margin-bottom:12px}}
    .hero-h{{font-size:26px;font-weight:800;line-height:1.2;margin-bottom:10px}}
    .hero-sub{{font-size:15px;color:var(--ink-dim);line-height:1.6;max-width:680px}}
    .map-cta{{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;margin:18px 0 4px;padding:16px 22px;background:var(--teal,#12a594);color:#fff;font-weight:800;font-size:16px;border-radius:12px;text-decoration:none;box-shadow:0 6px 20px rgba(18,165,148,.3);transition:.15s}}
    .map-cta:hover{{transform:translateY(-2px);box-shadow:0 10px 28px rgba(18,165,148,.45)}}
    .map-cta .mc-ico{{font-size:22px}}
    .map-cta.inline{{margin:20px 0;background:var(--surface);color:var(--ink);border:1.5px solid var(--teal,#12a594);box-shadow:none}}
    .map-cta.inline:hover{{background:rgba(18,165,148,.08);transform:translateY(-1px)}}
    .status-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:20px}}
    .status-card{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;text-align:center}}
    .status-card .val{{font-family:var(--mono);font-size:20px;font-weight:800;color:var(--red,#d23a2e)}}
    .status-card .lbl{{font-size:11px;color:var(--ink-dim);margin-top:4px}}
    .section-h{{font-size:20px;font-weight:800;margin:32px 0 14px;display:flex;align-items:center;gap:8px}}
    .section-h .ico{{font-size:22px}}
    .lead-p{{font-size:14px;line-height:1.7;color:var(--ink);margin-bottom:8px}}
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
    .balance-box{{background:var(--surface2);border:1px solid var(--line);border-left:3px solid var(--red,#d23a2e);border-radius:10px;padding:16px 18px;margin:18px 0;font-size:13.5px;line-height:1.7}}
    .wh-ok-op-h{{font-family:var(--mono);font-size:12px;font-weight:800;color:var(--teal);margin:18px 0 8px;letter-spacing:.5px}}
    .wh-ok-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;margin-bottom:8px}}
    .wh-ok-card{{background:var(--surface2);border:1px solid var(--line);border-radius:8px;padding:10px 12px}}
    .wh-ok-top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;gap:6px}}
    .wh-ok-op{{font-family:var(--mono);font-size:10px;font-weight:800;color:var(--teal)}}
    .wh-ok-type{{font-family:var(--mono);font-size:9px;color:var(--ink-dim);text-align:right}}
    .wh-ok-city{{font-weight:700;font-size:13px}}
    .wh-ok-region{{font-size:11px;color:var(--ink-dim);margin-top:2px}}
    .wh-ok-addr{{font-size:10.5px;color:var(--ink-dim);margin-top:2px;opacity:.8}}
</style>
  <link rel="stylesheet" href="/search.css?v=5a32b7c1">
  <script defer src="/search.js?v=8b14567c"></script>
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
        <span class="hero-label">СПРАВОЧНИК · СПИСОК ОБЪЕКТОВ</span>
        <h1 class="hero-h">Какие склады Wildberries и Ozon остались</h1>
        <p class="hero-sub">На {UPD_RU} в открытых данных проекта нет сообщений об ударе по <strong>{len(ok)} складским объектам</strong> Wildberries (ВБ) и Ozon из {len(wh)} в выборке — {len(wb_ok)} Wildberries и {len(oz_ok)} Ozon. Ниже — полный перечень с городом, регионом, оператором и федеральным округом.</p>
        <a class="map-cta" href="/?layer=warehouses"><span class="mc-ico">📦</span> Открыть слой складов на карте →</a>
        <div class="status-grid">
          <div class="status-card"><div class="val">{len(ok)}</div><div class="lbl">объектов без сообщений об ударе</div></div>
          <div class="status-card"><div class="val">{len(wb_ok)}</div><div class="lbl">Wildberries</div></div>
          <div class="status-card"><div class="val">{len(oz_ok)}</div><div class="lbl">Ozon</div></div>
          <div class="status-card"><div class="val">{n_okrugs}</div><div class="lbl">федеральных округов</div></div>
        </div>
        <div class="updated-line">Обновлено {UPD_RU}, МСК · данные последних суток уточняются</div>
      </div>

      <div class="balance-box">
        <strong>⚠️ Важная оговорка.</strong> Отсутствие объекта в списке поражённых — это <strong>отсутствие сообщений об ударе</strong> по нему в открытых источниках на {UPD_RU}, а <strong>не подтверждение того, что он работает в штатном режиме</strong>. Независимая проверка исправности объектов проектом не проводится.
      </div>

      <h2 class="section-h"><span class="ico">📍</span> Короткий ответ</h2>
      <p class="lead-p">Из {len(wh)} крупных объектов Wildberries и Ozon, которые проект отслеживает по открытым источникам, на {UPD_RU} поражено {len(hits)} (все — Wildberries), а по <strong>{len(ok)}</strong> сообщений об ударе нет: <strong>{len(wb_ok)}</strong> объектов Wildberries и <strong>{len(oz_ok)}</strong> объектов Ozon. Список ниже — не рейтинг и не хроника: это перечень конкретных объектов с адресом, регионом и федеральным округом.</p>

      <div class="link-grid">
        <a class="link-card" href="/skolko-skladov-wildberries-ozon"><div class="lc-h">📦 Сколько складов у WB и Ozon</div><div class="lc-d">Масштаб сети целиком, счётчики и доля выбывшего</div></a>
        <a class="link-card" href="/ataki-na-sklady-wildberries-hronika"><div class="lc-h">🗓 Хроника ударов по складам</div><div class="lc-d">Все эпизоды по датам и регионам</div></a>
        <a class="link-card" href="/karta-skladov-wildberries"><div class="lc-h">🗺 Карта складов ВБ и Ozon</div><div class="lc-d">Все объекты и поражённые на карте</div></a>
      </div>

      <a class="map-cta inline" href="/?layer=warehouses"><span class="mc-ico">📦</span> Склады обеих сетей на карте: поражённые отмечены красным →</a>

      <h2 class="section-h"><span class="ico">📋</span> Полный список по федеральным округам</h2>
{LIST_HTML}
      <h2 class="section-h"><span class="ico">⚖️</span> Чем Wildberries отличается от Ozon в этой картине</h2>
      <p class="lead-p">У Wildberries уцелевшие объекты встречаются в <strong>{cmp_['wb_reg']} регионах</strong> и <strong>{len(cmp_['wb_okr'])} федеральных округах</strong> ({", ".join(cmp_['wb_okr'])}). У Ozon — в <strong>{cmp_['oz_reg']} регионах</strong> и <strong>{len(cmp_['oz_okr'])} округах</strong> ({", ".join(cmp_['oz_okr'])}). {only_wb_txt}{only_oz_txt}{type_txt}</p>

      <h2 class="section-h"><span class="ico">🗂</span> Что не входит в выборку</h2>
      <p class="lead-p">Это список <strong>крупных объектов</strong> — распределительных центров Wildberries и фулфилмент-центров Ozon, по которым проект собрал координаты и адрес по открытым источникам. У Wildberries, по данным компании, свыше <strong>{net['wb']['complexes']} складских комплексов</strong>, у Ozon — {net['ozon']['fulfillment']} фулфилмент-центров и более {net['ozon']['sorting']} сортировочных центров: сортировочные центры и пункты выдачи (ПВЗ) в эту выборку не входят, поэтому полная сеть обеих компаний шире {len(wh)} объектов на этой странице.</p>

      <h2 class="section-h"><span class="ico">❓</span> Частые вопросы</h2>
      <div class="faq-wrap">
{faq_html}
      </div>

      <h2 class="section-h"><span class="ico">🔗</span> Смотрите также</h2>
      <div class="link-grid">
        <a class="link-card" href="/skolko-skladov-wildberries-ozon"><div class="lc-h">📦 Сколько складов у WB и Ozon</div><div class="lc-d">Масштаб сети, счётчики, доля выбывшего</div></a>
        <a class="link-card" href="/ataki-na-sklady-wildberries-hronika"><div class="lc-h">🗓 Хроника ударов по складам</div><div class="lc-d">Все эпизоды по датам и регионам</div></a>
        <a class="link-card" href="/udar-po-skladu-ozon"><div class="lc-h">📦 Удар по складу Ozon</div><div class="lc-d">Почему у Ozon пока нет поражённых объектов</div></a>
        <a class="link-card" href="/kompensacii-wildberries-posle-udara"><div class="lc-h">💸 Компенсации Wildberries</div><div class="lc-d">Выплаты продавцам и покупателям</div></a>
        <a class="link-card" href="/karta-skladov-wildberries"><div class="lc-h">🗺 Карта складов Wildberries и Ozon</div><div class="lc-d">Сеть и поражённые объекты на карте</div></a>
        <a class="link-card" href="/news"><div class="lc-h">📰 Сводки</div><div class="lc-d">Ежедневный архив обстановки</div></a>
      </div>

      <div class="osint-note">
        <strong>⚠️ Дисклеймер:</strong> Материал основан на <strong>открытых источниках</strong>: заявления компаний о размере логистической сети, сообщения СМИ и официальные заявления региональных властей об ударах. Список объектов и координаты — по открытым данным, независимой проверки у проекта нет. Отсутствие объекта среди поражённых означает только отсутствие сообщений об ударе по нему на {UPD_RU} — не подтверждение исправности или штатной работы объекта. Учитываются только поражения в результате ударов БПЛА и ракет. Проект придерживается нейтрального изложения и не выносит юридических вердиктов.
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
  <script defer src="/nav-dropdown.js?v=06476ddc"></script>
  <script defer src="/vpn-nudge.js?v=75a0afd9"></script>
</body>
</html>
"""


def main():
    html = build()
    with open(OUT, "w", encoding="utf8") as f:
        f.write(html)
    print("gen-survivors-page: %s (%.1f КБ)" % (os.path.basename(OUT), len(html.encode()) / 1024))
    return 0


def demo():
    """Самопроверка: каждый уцелевший объект виден в списке (город+регион), счётчики совпадают
    с датасетом, осторожная оговорка присутствует, ни один регион датасета не остаётся вне OKRUG."""
    doc = gwp.load_data()
    wh = doc["warehouses"]
    ok = [w for w in wh if w["status"] == "ok"]
    html = build()

    assert html.count("<h1") == 1
    for w in ok:
        assert w["name"] in html, "нет в списке уцелевших: %s" % w["name"]
        assert w["region"] in html, "нет региона в тексте: %s" % w["region"]
    assert str(len(ok)) in html and str(len(wh)) in html
    assert "не подтверждение того, что он работает в штатном режиме" in html, \
        "пропала осторожная оговорка про статус уцелевших складов"
    assert "/skolko-skladov-wildberries-ozon" in html, "нет ссылки на чемпиона кластера (масштаб сети)"
    assert "/ataki-na-sklady-wildberries-hronika" in html, "нет ссылки на хронику ударов"

    unmapped = sorted({w["region"] for w in wh} - set(OKRUG))
    assert not unmapped, "регионы без записи в OKRUG (страница покажет 'не определён'): %s" % unmapped

    # sample-limitation: сеть шире выборки
    assert str(doc["meta"]["network"]["wb"]["complexes"]) in html

    print("demo OK")


if __name__ == "__main__":
    sys.exit(demo() if "--demo" in sys.argv else main())
