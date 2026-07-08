#!/usr/bin/env python3
"""Генератор региональных страниц «ракетная опасность <город>» (long-tail SEO).

Одна страница = один город. Контент — нейтральный OSINT-тон (см. CLAUDE.md,
sanitize-strikes): объясняем сигналы ГО, что это оценка по открытым источникам,
воронка на /radar. НИКАКИХ жертв/пропаганды/укр-вербатима.

Использование:
  python3 agents/gen-rocket-danger.py volgograd            # → drafts/rocket-danger/raketnaya-opasnost-volgograd.html
  python3 agents/gen-rocket-danger.py volgograd --root      # → raketnaya-opasnost-volgograd.html (в корень, для публикации)
  python3 agents/gen-rocket-danger.py --list                # список городов + slug + объём

Публикация (делает утренняя рутина): --root → добавить live-строку в
data/seo-topics.jsonl → python3 agents/build-nav.py → python3 agents/check-ia.py
→ дописать URL в sitemap.xml → commit (ALLOW_FRONTEND_RELEASE=1) → push.

ponytail: строковый шаблон + словарь городов. Новый город из хвоста — одна запись
в CITIES, а не новый файл. Даты РУ-формат передаём аргументом (Date.now недоступен
в headless-рутине — берём из окружения).
"""
import sys, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://npz-tactical-map.vercel.app"

# Города хвоста «ракетная опасность <город>». volume — оценка Wordstat/мес из брифа.
# ctx — одно нейтральное предложение: почему по региону вообще проходят сигналы.
CITIES = {
    "volgograd": {
        "slug": "raketnaya-opasnost-volgograd",
        "nom": "Волгоград", "prep": "Волгограде", "gde": "в Волгограде",
        "region": "Волгоградская область", "region_prep": "Волгоградской области",
        "emoji": "🚀", "volume": "35 000",
        "ctx": "В регионе расположены крупные объекты энергетики и нефтепереработки "
               "(в том числе один из крупнейших НПЗ юга России), поэтому сообщения о "
               "воздушной тревоге и работе ПВО здесь появляются регулярно.",
    },
    "ulyanovsk": {
        "slug": "raketnaya-opasnost-ulyanovsk",
        "nom": "Ульяновск", "prep": "Ульяновске", "gde": "в Ульяновске",
        "region": "Ульяновская область", "region_prep": "Ульяновской области",
        "emoji": "🚀", "volume": "30 000",
        "ctx": "В Поволжье сосредоточены промышленные и логистические объекты, "
               "с которыми связаны периодические сообщения о воздушной тревоге и "
               "ограничениях в работе аэропортов.",
    },
    "kazan": {
        "slug": "raketnaya-opasnost-kazan",
        "nom": "Казань", "prep": "Казани", "gde": "в Казани",
        "region": "Республика Татарстан", "region_prep": "Татарстане",
        "emoji": "🚀", "volume": "28 000",
        "ctx": "В Татарстане находятся крупные промышленные и нефтеперерабатывающие "
               "объекты, поэтому сообщения о воздушной тревоге и работе систем ПВО "
               "по региону появляются периодически.",
    },
}

TEMPLATE = """<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ракетная опасность {nom} сегодня — воздушная тревога и угроза БПЛА онлайн</title>
  <meta name="description" content="Ракетная опасность и воздушная тревога {gde} сегодня: что означают сигналы, где смотреть обстановку по региону на карте-радаре. Данные OSINT — оценка, не официальное оповещение.">
  <meta name="keywords" content="ракетная опасность {nom_low}, воздушная тревога {nom_low}, тревога {gde_low} сейчас, бпла {nom_low} сегодня, ракетная опасность {gde_low}, отбой тревоги {nom_low}">
  <meta name="robots" content="index, follow">
  <meta name="language" content="Russian">
  <link rel="canonical" href="{site}/{slug}">

  <meta property="og:type" content="article">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:site_name" content="Топливный фронт РФ">
  <meta property="og:url" content="{site}/{slug}">
  <meta property="og:title" content="Ракетная опасность {nom} сегодня — воздушная тревога и угроза БПЛА">
  <meta property="og:description" content="Что означают сигналы воздушной тревоги и ракетной опасности {gde}, где смотреть обстановку по региону. Оценка по открытым OSINT-источникам.">
  <meta property="og:image" content="{site}/og-image.png">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Ракетная опасность {nom} — тревога и угроза БПЛА онлайн">
  <meta name="twitter:description" content="Сигналы воздушной тревоги и ракетной опасности {gde}: что значат, где смотреть обстановку. OSINT-оценка.">
  <meta name="twitter:image" content="{site}/og-image.png">

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "Ракетная опасность {nom}: что означает сигнал и где смотреть обстановку",
    "datePublished": "{iso}",
    "dateModified": "{iso}",
    "image": ["{site}/og-image.png"],
    "author": {{"@type": "Organization", "name": "Топливный фронт РФ"}},
    "publisher": {{"@type": "Organization", "name": "Топливный фронт РФ", "url": "{site}/"}},
    "description": "Что означают сигналы воздушной тревоги и ракетной опасности {gde}, чем они отличаются и где смотреть обстановку по региону на карте-радаре. Оценка по открытым источникам.",
    "mainEntityOfPage": "{site}/{slug}",
    "isAccessibleForFree": true
  }}
  </script>

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "mainEntity": [
      {{"@type": "Question", "name": "Что означает ракетная опасность {gde}?", "acceptedAnswer": {{"@type": "Answer", "text": "Ракетная опасность — официальный сигнал гражданской обороны о вероятном ракетном ударе по территории. При нём времени на реакцию обычно меньше, чем при общей воздушной тревоге. Сигнал объявляют региональные власти и МЧС; карта-радар лишь агрегирует сообщения об угрозах из открытых источников и не заменяет систему оповещения."}}}},
      {{"@type": "Question", "name": "Чем ракетная опасность отличается от воздушной тревоги?", "acceptedAnswer": {{"@type": "Answer", "text": "Воздушная тревога — сигнал о возможной угрозе с воздуха в целом, включая беспилотники. Ракетная опасность — сигнал именно о вероятном ракетном ударе. Оба сигнала относятся к системе оповещения гражданской обороны."}}}},
      {{"@type": "Question", "name": "Где смотреть, объявлена ли тревога {gde} сейчас?", "acceptedAnswer": {{"@type": "Answer", "text": "Официальный статус объявляют региональные власти и МЧС. Обзорную картину по регионам, включая {region}, показывает карта-радар проекта: она подсвечивает, где по открытым данным отмечена угроза. Это оценка, а не официальное оповещение."}}}},
      {{"@type": "Question", "name": "Что делать при сигнале ракетной опасности?", "acceptedAnswer": {{"@type": "Answer", "text": "Следуйте официальным инструкциям МЧС и региональных властей: как правило, рекомендуется пройти в укрытие или помещение без окон и дождаться сигнала отбоя. Карта-радар не содержит рекомендаций к действию и носит справочно-аналитический характер."}}}},
      {{"@type": "Question", "name": "Что означает отбой тревоги {gde}?", "acceptedAnswer": {{"@type": "Answer", "text": "Отбой тревоги — сигнал об окончании действия угрозы, после которого режим воздушной тревоги или ракетной опасности снимается. Официальный отбой объявляют местные власти и МЧС."}}}},
      {{"@type": "Question", "name": "Откуда берутся данные по {region_prep}?", "acceptedAnswer": {{"@type": "Answer", "text": "Данные агрегируются из открытых OSINT-источников: сообщений СМИ, официальных заявлений региональных властей, публичного мониторинга. Это оценка, а не официальная или разведывательная информация и не система экстренного оповещения."}}}}
    ]
  }}
  </script>

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {{"@type": "ListItem", "position": 1, "name": "Главная", "item": "{site}/"}},
      {{"@type": "ListItem", "position": 2, "name": "Радар угроз", "item": "{site}/radar"}},
      {{"@type": "ListItem", "position": 3, "name": "Ракетная опасность {nom}", "item": "{site}/{slug}"}}
    ]
  }}
  </script>

  <script>window.va = window.va || function () {{ (window.vaq = window.vaq || []).push(arguments); }};</script>
  <script defer src="/_vercel/insights/script.js"></script>

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Rubik:wght@500;600;700;800&family=JetBrains+Mono:wght@400;600;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/styles.css">
  <link rel="stylesheet" href="/news.css">
  <style>
    .landing-wrap{{max-width:900px;margin:0 auto;padding:24px 20px 60px}}
    .landing-hero{{background:linear-gradient(135deg,rgba(210,58,46,.12),rgba(160,29,20,.08));border:1px solid rgba(210,58,46,.25);border-radius:16px;padding:32px 28px;margin-bottom:24px;position:relative;overflow:hidden}}
    .landing-hero::before{{content:"";position:absolute;top:-30px;right:-30px;width:120px;height:120px;background:radial-gradient(circle,rgba(210,58,46,.15),transparent 70%);border-radius:50%}}
    .hero-label{{display:inline-block;background:var(--red);color:#fff;font-family:var(--mono);font-size:10px;font-weight:800;letter-spacing:1.5px;padding:3px 10px;border-radius:6px;margin-bottom:12px}}
    .hero-h{{font-size:28px;font-weight:800;line-height:1.2;margin-bottom:10px}}
    .hero-sub{{font-size:15px;color:var(--ink-dim);line-height:1.6;max-width:680px}}
    .map-cta{{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;margin:18px 0 4px;padding:16px 22px;background:var(--red);color:#fff;font-weight:800;font-size:16px;border-radius:12px;text-decoration:none;box-shadow:0 6px 20px rgba(210,58,46,.3);transition:.15s}}
    .map-cta:hover{{transform:translateY(-2px);box-shadow:0 10px 28px rgba(210,58,46,.45)}}
    .map-cta .mc-ico{{font-size:22px}}
    .map-cta.inline{{margin:20px 0;background:var(--surface);color:var(--ink);border:1.5px solid var(--red);box-shadow:none}}
    .map-cta.inline:hover{{background:rgba(210,58,46,.08);transform:translateY(-1px)}}
    .status-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:20px}}
    .status-card{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;text-align:center}}
    .status-card .val{{font-family:var(--mono);font-size:22px;font-weight:800;color:var(--red)}}
    .status-card .lbl{{font-size:11px;color:var(--ink-dim);margin-top:4px}}
    .section-h{{font-size:20px;font-weight:800;margin:32px 0 14px;display:flex;align-items:center;gap:8px}}
    .section-h .ico{{font-size:22px}}
    .lead-p{{font-size:14px;line-height:1.7;color:var(--ink);margin-bottom:8px}}
    .cmp-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:6px 0 14px}}
    .cmp-card{{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px}}
    .cmp-card h3{{font-size:14px;font-weight:800;margin:0 0 6px}}
    .cmp-card p{{font-size:12.5px;color:var(--ink-dim);line-height:1.55;margin:0}}
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
</head>
<body data-theme="light">
  <header class="news-header">
    <div class="news-header-inner">
      <a href="/news" class="news-logo" title="Все сводки">
        <span class="news-logo-icon">⛽</span>
        <span class="news-logo-text">ТОПЛИВНЫЙ ФРОНТ РФ</span>
      </a>
      <nav class="news-nav"><!-- сгенерит agents/build-nav.py --></nav>
    </div>
  </header>
  <main class="news-main">
    <div class="landing-wrap">

      <div class="landing-hero">
        <span class="hero-label">ВОЗДУШНАЯ ТРЕВОГА · РЕГИОН</span>
        <h1 class="hero-h">Ракетная опасность {gde}: что означает сигнал и где смотреть обстановку</h1>
        <p class="hero-sub">Разбор сигналов воздушной тревоги и ракетной опасности {gde} и по {region_prep}: чем они отличаются, что означает отбой и где следить за обстановкой по региону на карте-радаре. Данные — оценка по открытым OSINT-источникам, не официальные оповещения.</p>
        <a class="map-cta" href="/radar"><span class="mc-ico">📡</span> Смотреть обстановку по регионам на радаре →</a>
        <div class="status-grid">
          <div class="status-card"><div class="val">{region_abbr}</div><div class="lbl">Регион</div></div>
          <div class="status-card"><div class="val">~5 мин</div><div class="lbl">Автообновление радара</div></div>
          <div class="status-card"><div class="val">БПЛА · ✷</div><div class="lbl">Типы угроз</div></div>
          <div class="status-card"><div class="val">OSINT</div><div class="lbl">Оценка, не оповещение</div></div>
        </div>
        <div class="updated-line">Обновлено {rus_date}, МСК</div>
      </div>

      <h2 class="section-h"><span class="ico">📢</span> Ракетная опасность и воздушная тревога — в чём разница</h2>
      <div class="cmp-grid">
        <div class="cmp-card">
          <h3>Воздушная тревога</h3>
          <p>Сигнал о возможной угрозе с воздуха в целом, включая беспилотники. Объявляется, когда есть вероятность появления воздушных целей над территорией.</p>
        </div>
        <div class="cmp-card">
          <h3>Ракетная опасность</h3>
          <p>Сигнал именно о вероятном ракетном ударе. Времени на реакцию при нём обычно меньше, чем при общей воздушной тревоге.</p>
        </div>
        <div class="cmp-card">
          <h3>Отбой тревоги</h3>
          <p>Сигнал об окончании угрозы — объявленный режим снимается. Официальный отбой дают местные власти и МЧС.</p>
        </div>
      </div>
      <p class="lead-p">Это официальные сигналы гражданской обороны. При реальной опасности {gde} ориентируйтесь на оповещения МЧС и региональных властей — карта-радар их не заменяет.</p>

      <h2 class="section-h"><span class="ico">🧭</span> Почему тревоги проходят по {region_prep}</h2>
      <p class="lead-p">{ctx}</p>
      <p class="lead-p">Карта-радар не показывает отдельные цели или средства ПВО — она агрегирует открытые сообщения об угрозах и подсвечивает регионы, где обстановка отмечена как напряжённая. Это справочно-аналитический инструмент для журналистов и исследователей.</p>
      <a class="map-cta inline" href="/radar"><span class="mc-ico">🗺️</span> Открыть радар угроз по регионам →</a>

      <h2 class="section-h"><span class="ico">📡</span> Где следить за обстановкой {gde}</h2>
      <p class="lead-p">Официальный статус тревоги объявляют региональные власти и МЧС. Обзорную картину по регионам, включая {region}, показывает <a href="/radar">карта-радар</a>: где по открытым данным отмечена угроза БПЛА или ракет и насколько свежие данные. Радар связан с общей <a href="/">картой НПЗ</a> и <a href="/attacks">хроникой ударов</a> — про обстановку «сейчас» и архив подтверждённых событий соответственно.</p>

      <h2 class="section-h"><span class="ico">❓</span> Частые вопросы</h2>
      <div class="faq-wrap">
        <div class="faq-item open">
          <div class="faq-q" onclick="this.parentElement.classList.toggle('open')">Что означает ракетная опасность {gde}?</div>
          <div class="faq-a">Ракетная опасность — официальный сигнал гражданской обороны о вероятном ракетном ударе. Времени на реакцию при нём обычно меньше, чем при общей воздушной тревоге. Сигнал объявляют региональные власти и МЧС; <a href="/radar">карта-радар</a> лишь агрегирует сообщения из открытых источников и не заменяет систему оповещения.</div>
        </div>
        <div class="faq-item">
          <div class="faq-q" onclick="this.parentElement.classList.toggle('open')">Чем ракетная опасность отличается от воздушной тревоги?</div>
          <div class="faq-a">Воздушная тревога — сигнал о возможной угрозе с воздуха в целом, включая беспилотники. Ракетная опасность — сигнал именно о вероятном ракетном ударе. Оба относятся к системе оповещения гражданской обороны.</div>
        </div>
        <div class="faq-item">
          <div class="faq-q" onclick="this.parentElement.classList.toggle('open')">Где смотреть, объявлена ли тревога {gde} сейчас?</div>
          <div class="faq-a">Официальный статус объявляют региональные власти и МЧС. Обзорную картину по регионам, включая {region}, показывает <a href="/radar">карта-радар</a> — где по открытым данным отмечена угроза. Это оценка, а не официальное оповещение.</div>
        </div>
        <div class="faq-item">
          <div class="faq-q" onclick="this.parentElement.classList.toggle('open')">Что делать при сигнале ракетной опасности?</div>
          <div class="faq-a">Следуйте официальным инструкциям МЧС и региональных властей: как правило, рекомендуется пройти в укрытие или помещение без окон и дождаться отбоя. Карта-радар не содержит рекомендаций к действию и носит справочный характер.</div>
        </div>
        <div class="faq-item">
          <div class="faq-q" onclick="this.parentElement.classList.toggle('open')">Что означает отбой тревоги {gde}?</div>
          <div class="faq-a">Отбой тревоги — сигнал об окончании действия угрозы, после которого режим воздушной тревоги или ракетной опасности снимается. Официальный отбой объявляют местные власти и МЧС.</div>
        </div>
        <div class="faq-item">
          <div class="faq-q" onclick="this.parentElement.classList.toggle('open')">Откуда берутся данные по {region_prep}?</div>
          <div class="faq-a">Данные агрегируются из открытых OSINT-источников: сообщений СМИ, официальных заявлений региональных властей, публичного мониторинга. Это оценка, а не официальная информация и не система экстренного оповещения.</div>
        </div>
      </div>

      <h2 class="section-h"><span class="ico">🔗</span> Смотрите также</h2>
      <div class="link-grid">
        <a class="link-card" href="/radar"><div class="lc-h">📡 Радар угроз</div><div class="lc-d">Карта БПЛА и ракет по регионам в реальном времени</div></a>
        <a class="link-card" href="/karta-bpla"><div class="lc-h">🗺️ Карта БПЛА онлайн</div><div class="lc-d">Как читать карту тревог и угроз по регионам</div></a>
        <a class="link-card" href="/"><div class="lc-h">🗺️ Карта НПЗ России</div><div class="lc-d">Состояние нефтезаводов, дефицит, логистика</div></a>
        <a class="link-card" href="/attacks"><div class="lc-h">💥 Хроника ударов</div><div class="lc-d">Архив подтверждённых атак БПЛА по НПЗ</div></a>
        <a class="link-card" href="/news"><div class="lc-h">📰 Сводки</div><div class="lc-d">Ежедневный архив мониторинга обстановки</div></a>
        <a class="link-card" href="/sources"><div class="lc-h">📚 Источники</div><div class="lc-d">Методология и перечень OSINT-источников</div></a>
      </div>

      <div class="osint-note">
        <strong>⚠️ Дисклеймер:</strong> Данные — <strong>оценка по открытым OSINT-источникам</strong> (СМИ, официальные сообщения региональных властей, публичный мониторинг). Это не официальная и не разведывательная информация и <strong>не является системой экстренного оповещения</strong>. При реальной угрозе {gde} ориентируйтесь на сигналы МЧС и местных властей. Страница носит справочно-аналитический характер и не содержит рекомендаций к действию.
      </div>
    </div>
  </main>
  <script>
    document.querySelectorAll('.nav-dropdown > a').forEach(a => {{
      a.addEventListener('click', function(e) {{
        if (window.innerWidth <= 768) {{
          e.preventDefault();
          const menu = this.nextElementSibling;
          menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
        }}
      }});
    }});
    document.addEventListener('click', function(e) {{
      if (!e.target.closest('.nav-dropdown')) {{
        document.querySelectorAll('.nav-dropdown-menu').forEach(m => m.style.display = '');
      }}
    }});
    const saved = localStorage.getItem('theme');
    if (saved) document.documentElement.dataset.theme = saved;
  </script>
</body>
</html>
"""

RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def rus_date(d):
    return f"{d.day} {RU_MONTHS[d.month - 1]} {d.year}"


def render(key, today):
    c = CITIES[key]
    return TEMPLATE.format(
        site=SITE, slug=c["slug"], nom=c["nom"], prep=c["prep"], gde=c["gde"],
        nom_low=c["nom"].lower(), gde_low=c["gde"].lower(),
        region=c["region"], region_prep=c["region_prep"],
        region_abbr=c["region"].split()[0][:3].upper() if c["region"].split()[0] != "Республика" else "РТ",
        ctx=c["ctx"], iso=today.isoformat(), rus_date=rus_date(today),
    )


def main(argv):
    if not argv or argv[0] == "--list":
        for k, c in CITIES.items():
            print(f"{k:12} → {c['slug']:36} ~{c['volume']}/мес")
        return
    key = argv[0]
    if key not in CITIES:
        sys.exit(f"нет города '{key}'. Доступны: {', '.join(CITIES)}")
    if "--registry" in argv:
        c = CITIES[key]
        import json as _json
        print(_json.dumps({
            "url": f"/{c['slug']}", "type": "region",
            "primary_kw": f"ракетная опасность {c['nom'].lower()}",
            "keywords": [f"воздушная тревога {c['nom'].lower()}",
                         f"тревога {c['gde'].lower()} сейчас",
                         f"бпла {c['nom'].lower()} сегодня",
                         f"ракетная опасность {c['gde'].lower()}",
                         f"отбой тревоги {c['nom'].lower()}"],
            "created": datetime.date.today().isoformat(), "status": "live",
            "note": "long-tail «ракетная опасность <город>»; воронка на /radar; "
                    "нейтральный OSINT-тон. Сгенерено agents/gen-rocket-danger.py.",
        }, ensure_ascii=False))
        return
    to_root = "--root" in argv
    today = datetime.date.today()
    html = render(key, today)
    if to_root:
        out = ROOT / f"{CITIES[key]['slug']}.html"
    else:
        d = ROOT / "drafts" / "rocket-danger"
        d.mkdir(parents=True, exist_ok=True)
        out = d / f"{CITIES[key]['slug']}.html"
    out.write_text(html, encoding="utf-8")
    print(f"написано: {out.relative_to(ROOT)}  (url /{CITIES[key]['slug']})")


if __name__ == "__main__":
    main(sys.argv[1:])
