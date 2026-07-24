#!/usr/bin/env python3
"""Генерация /skolko-skladov-wildberries-ozon — сколько складов у WB и Ozon и сколько поражено.

Цифры берутся из data/warehouses.json, а не пишутся руками: страница про количество,
и расхождение с картой здесь читается как враньё (та же грабля, что была у /refineries).

Угол намеренно отличается от соседних страниц кластера, чтобы не каннибалить:
  /udar-po-skladam-wildberries        — разбор ОДНОГО эпизода 18.07 и «почему бьют»
  /ataki-na-sklady-wildberries-hronika — хронология всех эпизодов
  /kompensacii-wildberries-posle-udara — деньги
  здесь                                — МАСШТАБ СЕТИ: сколько всего и какая доля выбыла

Запуск:  ./.venv/bin/python agents/gen-warehouses-page.py
"""
import hashlib
import json
import os
import sys
from html import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "warehouses.json")
OUT = os.path.join(ROOT, "skolko-skladov-wildberries-ozon.html")
URL = "https://npz-tactical-map.vercel.app/skolko-skladov-wildberries-ozon"
TITLE = "Сколько складов у Wildberries и Ozon в России и сколько сгорело"
DESC = ("Сколько всего складов и распределительных центров у Wildberries и Ozon в России, "
        "какая площадь выбыла после ударов БПЛА в июле 2026 года и какие объекты поражены — "
        "с картой складов.")
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]

# Потери площадей — оценка СМИ, в датасете её нет (там объекты, а не квадратные метры).
LOST_M2 = 350000
LOST_SRC = "https://www.fontanka.ru/2026/07/18/76541441/"

BASE = "https://npz-tactical-map.vercel.app"
# Обложка по той же конвенции, что карточка хаба в build-nav.cover_for(). Есть файл —
# он и в og:image, и в JSON-LD (с ?v по хэшу, чтобы шеринг не кэшировал старую); нет — дефолт.
COVER_REL = "assets/analytics-skolko-skladov-wildberries-ozon-generated.png"


def og_image():
    p = os.path.join(ROOT, COVER_REL)
    if not os.path.isfile(p):
        return BASE + "/og-image.png"
    v = hashlib.md5(open(p, "rb").read()).hexdigest()[:8]
    return "%s/%s?v=%s" % (BASE, COVER_REL, v)


def rus(iso):
    y, m, d = iso.split("-")
    return "%d %s %s" % (int(d), MONTHS[int(m) - 1], y)


def mln(n):
    return ("%.1f" % (n / 1000000.0)).replace(".", ",")


def build():
    with open(SRC, encoding="utf8") as f:
        doc = json.load(f)
    wh = doc["warehouses"]
    net = doc["meta"]["network"]
    hits = [w for w in wh if w["status"] == "hit"]
    burned = [w for w in hits if w.get("damage") == "burned"]
    # 🔴 дата и формулировки выводятся из датасета: захардкоженное «22 июля» и «все — WB»
    # соврали бы на следующем ударе, особенно по Ozon
    UPDATED = doc["meta"]["generated_at"][:10]
    ops = {w["operator"] for w in hits}
    ops_txt = ("все принадлежат Wildberries" if ops == {"wb"}
               else "все принадлежат Ozon" if ops == {"ozon"}
               else "среди них объекты обеих сетей")
    wb_n = sum(1 for w in wh if w["operator"] == "wb")
    oz_n = sum(1 for w in wh if w["operator"] == "ozon")
    hit_oz = [w for w in hits if w["operator"] == "ozon"]
    share = LOST_M2 * 100.0 / net["wb"]["area_m2"]
    OG = og_image()

    def src_cell(w):
        u = w.get("source_url", "")
        if not u.startswith("https://"):
            raise ValueError("удар без источника: %s" % w["name"])   # правило проекта
        return '<a href="%s" rel="nofollow noopener" target="_blank">источник ↗</a>' % escape(u)

    rows = "\n".join(
        '        <tr><td><strong>%s</strong></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
        % (escape(w["name"]), escape(w["region"]), rus(w["date"]),
           escape(w.get("note", "")), src_cell(w))
        for w in sorted(hits, key=lambda w: (w["date"], w["name"])))

    faq = [
        ("Сколько складов у Wildberries в России?",
         "По данным компании на начало 2026 года логистическая инфраструктура Wildberries насчитывает более %d складских комплексов общей площадью свыше %s млн м². В это число входят и крупные распределительные центры, и сортировочные центры; отдельно публикуемой разбивки по типам компания не даёт."
         % (net["wb"]["complexes"], mln(net["wb"]["area_m2"]))),
        ("Сколько складов у Ozon?",
         "На начало 2026 года площадь логистической инфраструктуры Ozon составляла около %s млн м²: %d фулфилмент-центров и более %d сортировочных центров."
         % (mln(net["ozon"]["area_m2"]), net["ozon"]["fulfillment"], net["ozon"]["sorting"])),
        ("Сколько складов поражено ударами?",
         "По открытым данным на %s поражены %d складских объектов, %s: %s. Из них пожар подтверждён на %d объектах."
         % (rus(UPDATED), len(hits), ops_txt, ", ".join(w["name"] for w in hits), len(burned))),
        ("Пострадали ли склады Ozon?",
         "На %s среди поражённых объектов %s. Крупный пожар на складе Ozon в Истре произошёл в августе 2022 года и с ударами БПЛА не связан — на этой странице он не учитывается."
         % (rus(UPDATED), "объектов Ozon нет" if "ozon" not in ops else "есть объекты Ozon")),
        ("Какая доля складских мощностей выбыла?",
         "По оценкам в СМИ, Wildberries потерял около %d тыс. м² складских площадей — это порядка %.0f%% от заявленных %s млн м². Оценка приблизительная: компания не публиковала официальных данных о выбывших площадях."
         % (LOST_M2 // 1000, share, mln(net["wb"]["area_m2"]))),
        ("Сколько складов показано на карте?",
         "На слое «Склады ВБ/Озон» нанесены %d крупных объекта: %d распределительных центров Wildberries и %d фулфилмент-центров Ozon. Это выборка крупных объектов, а не вся сеть из %d+ комплексов — сортировочные центры и пункты выдачи на карту не наносятся."
         % (len(wh), wb_n, oz_n, net["wb"]["complexes"])),
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
  <meta name="keywords" content="сколько складов у wildberries, сколько складов у ozon, склады wildberries в россии количество, сколько складов сгорело, площадь складов wildberries, логистика маркетплейсов россия, карта складов маркетплейсов">
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
    "datePublished": "{UPDATED}",
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
      {{"@type": "ListItem", "position": 3, "name": "Сколько складов у Wildberries и Ozon", "item": "{URL}"}}
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
    .wh-table{{width:100%;border-collapse:collapse;margin:16px 0;font-size:13px}}
    .wh-table th{{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--ink-dim);padding:8px 10px;border-bottom:1px solid var(--line)}}
    .wh-table td{{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}}
    .wh-scroll{{overflow-x:auto}}
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
        <span class="hero-label">СПРАВОЧНИК · ЛОГИСТИКА</span>
        <h1 class="hero-h">Сколько складов у Wildberries и Ozon в России и сколько из них сгорело</h1>
        <p class="hero-sub">Два маркетплейса держат в России около {mln(net['wb']['area_m2'] + net['ozon']['area_m2'])} млн м² складов. В июле 2026 года часть этой сети выбыла после ударов беспилотников. Ниже — сколько объектов у каждой компании, сколько поражено, какая доля мощностей потеряна и что из этого проверяемо по открытым источникам.</p>
        <a class="map-cta" href="/?layer=warehouses"><span class="mc-ico">📦</span> Открыть слой складов на карте →</a>
        <div class="status-grid">
          <div class="status-card"><div class="val">{net['wb']['complexes']}+</div><div class="lbl">складских комплексов Wildberries</div></div>
          <div class="status-card"><div class="val">{net['ozon']['fulfillment']}</div><div class="lbl">фулфилмент-центров Ozon</div></div>
          <div class="status-card"><div class="val">{len(hits)}</div><div class="lbl">складов поражено ударами</div></div>
          <div class="status-card"><div class="val">≈{share:.0f}%</div><div class="lbl">площадей Wildberries выбыло</div></div>
        </div>
        <div class="updated-line">Обновлено {rus(UPDATED)}, МСК · данные последних суток уточняются</div>
      </div>

      <h2 class="section-h"><span class="ico">📍</span> Короткий ответ</h2>
      <p class="lead-p">У <strong>Wildberries</strong> — более <strong>{net['wb']['complexes']} складских комплексов</strong> общей площадью свыше <strong>{mln(net['wb']['area_m2'])} млн м²</strong> (данные компании на начало 2026 года). У <strong>Ozon</strong> — <strong>{net['ozon']['fulfillment']} фулфилмент-центров</strong> и более <strong>{net['ozon']['sorting']} сортировочных центров</strong>, суммарно около <strong>{mln(net['ozon']['area_m2'])} млн м²</strong>.</p>
      <p class="lead-p">Ударами беспилотников поражено <strong>{len(hits)}</strong> из них — {ops_txt}; пожар подтверждён на {len(burned)}. {"Подтверждённых ударов по складам Ozon в открытых источниках на " + rus(UPDATED) + " нет." if "ozon" not in ops else ""} Потери площадей оцениваются примерно в <strong>{LOST_M2 // 1000} тыс. м²</strong> — около <strong>{share:.0f}%</strong> складских мощностей Wildberries.</p>

      <h2 class="section-h"><span class="ico">🔥</span> Какие склады поражены</h2>
      <div class="wh-scroll">
      <table class="wh-table">
        <thead><tr><th>Объект</th><th>Регион</th><th>Дата удара</th><th>Что известно</th><th>Источник</th></tr></thead>
        <tbody>
{rows}
        </tbody>
      </table>
      </div>
      <p class="lead-p">Хронология эпизодов с числом пострадавших и статусом работы — на странице <a href="/ataki-na-sklady-wildberries-hronika">«Атаки на склады Wildberries: хроника»</a>. Разбор эпизода 18 июля и версий сторон — <a href="/udar-po-skladam-wildberries">здесь</a>. Что с выплатами продавцам и покупателям — на странице <a href="/kompensacii-wildberries-posle-udara">о компенсациях</a>.</p>

      <a class="map-cta inline" href="/?layer=warehouses"><span class="mc-ico">📦</span> Склады обеих сетей на карте: поражённые отмечены красным →</a>

      <h2 class="section-h"><span class="ico">📊</span> Масштаб сети против масштаба потерь</h2>
      <div class="balance-box">
        <strong>Что это значит в пропорции.</strong> {LOST_M2 // 1000} тыс. м² — это около {share:.0f}% складских площадей Wildberries (<a href="{LOST_SRC}" rel="nofollow noopener" target="_blank">оценка СМИ ↗</a>). Ограничение: компания не публиковала официальных данных о выбывших площадях, поэтому цифра приблизительная и может быть уточнена. Проект не даёт собственной оценки того, критична эта доля или нет.
      </div>
      <p class="lead-p">Важно и то, где именно выбыли мощности. Электросталь — один из ключевых узлов доставки для Московского региона, Краснодар и Невинномысск закрывают юг. Потеря узла бьёт не пропорционально его площади, а пропорционально плечу доставки, которое он обслуживал: заказы переносятся на соседние центры, сроки растут именно в тех регионах, где выбыл узел.</p>

      <h2 class="section-h"><span class="ico">🗺</span> Что показано на карте</h2>
      <p class="lead-p">На слое «Склады ВБ/Озон» нанесены <strong>{len(wh)} крупных объекта</strong>: {wb_n} распределительных центров Wildberries и {oz_n} фулфилмент-центров Ozon. Поражённые ударами отмечены <strong>красным</strong> с пульсацией, остальные — фирменным цветом сети: по ним в этом наборе удары не зафиксированы, что не является утверждением о том, что склад работает. В карточке каждого поражённого объекта — дата удара и ссылка на источник.</p>
      <p class="lead-p">Это <strong>выборка крупных объектов</strong>, а не полная сеть: сортировочные центры и пункты выдачи на карту не наносятся — достоверного открытого датасета по ним нет, а на карте страны они превратились бы в сплошное пятно. Координаты складов получены геокодированием открытых адресов через OpenStreetMap и для части объектов указывают на населённый пункт, а не на конкретное здание.</p>

      <h2 class="section-h"><span class="ico">❓</span> Частые вопросы</h2>
      <div class="faq-wrap">
{faq_html}
      </div>

      <h2 class="section-h"><span class="ico">🔗</span> Смотрите также</h2>
      <div class="link-grid">
        <a class="link-card" href="/ataki-na-sklady-wildberries-hronika"><div class="lc-h">🗓 Хроника ударов по складам</div><div class="lc-d">Все эпизоды по датам и регионам</div></a>
        <a class="link-card" href="/udar-po-skladam-wildberries"><div class="lc-h">📦 Разбор эпизода 18 июля</div><div class="lc-d">Что известно об ударе и версии сторон</div></a>
        <a class="link-card" href="/kompensacii-wildberries-posle-udara"><div class="lc-h">💸 Компенсации Wildberries</div><div class="lc-d">Выплаты семьям, продавцам, покупателям</div></a>
        <a class="link-card" href="/karta-bpla"><div class="lc-h">📡 Карта БПЛА</div><div class="lc-d">Удары и активность беспилотников</div></a>
        <a class="link-card" href="/attacks"><div class="lc-h">💥 Хроника ударов</div><div class="lc-d">История ударов по объектам</div></a>
        <a class="link-card" href="/news"><div class="lc-h">📰 Сводки</div><div class="lc-d">Ежедневный архив обстановки</div></a>
      </div>

      <div class="osint-note">
        <strong>⚠️ Дисклеймер:</strong> Материал основан на <strong>открытых источниках</strong>: заявления компаний о размере логистической сети, сообщения СМИ и официальные заявления региональных властей об ударах. Данные о количестве и площади складов — <strong>заявления самих компаний</strong>, независимой проверки у проекта нет. Оценка выбывших площадей приблизительная и может измениться. Учитываются <strong>только поражения в результате ударов БПЛА и ракет</strong>; бытовые пожары на складах (Шушары, январь 2024; Истра, август 2022) в статистику этой страницы не входят. Проект придерживается нейтрального изложения и не выносит юридических вердиктов.
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
  <script defer src="/vpn-nudge.js?v=7009410b"></script>
</body>
</html>
"""


def main():
    html = build()
    with open(OUT, "w", encoding="utf8") as f:
        f.write(html)
    print("gen-warehouses-page: %s (%.1f КБ)" % (os.path.basename(OUT), len(html.encode()) / 1024))
    return 0


def demo():
    """Самопроверка: цифры в тексте совпадают с датасетом, у каждого удара есть источник.

    Раньше здесь стоял assert «поражённых Ozon не бывает» — он превращал появление
    такого удара в падение генератора вместо корректного текста. Теперь проверяется
    согласованность, а не конкретный оператор.
    """
    with open(SRC, encoding="utf8") as f:
        doc = json.load(f)
    hits = [w for w in doc["warehouses"] if w["status"] == "hit"]
    html = build()
    assert html.count("<h1") == 1
    for w in hits:                       # каждый поражённый объект виден в тексте и со ссылкой
        assert w["name"] in html, w["name"]
        assert w["source_url"] in html, w["name"]
    assert str(len(hits)) in html and str(len(doc["warehouses"])) in html
    assert mln(doc["meta"]["network"]["wb"]["area_m2"]) in html
    assert LOST_SRC in html, "оценка потерь без ссылки на источник"
    assert "работающие" not in html, "непроверяемое утверждение о работе складов"
    print("demo OK")


if __name__ == "__main__":
    sys.exit(demo() if "--demo" in sys.argv else main())
