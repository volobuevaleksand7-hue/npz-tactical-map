#!/usr/bin/env python3
"""Генератор топливных SEO-страниц (/benzin-na-trasse, /gde-dizel).

Тип explainer → группа меню «Объяснялки». Нейтральный тон, воронка на карты
(/, /karta-benzina-krym) и /deficit. Контент — оценка по открытым данным, не
оповещение. НИКАКОЙ пропаганды/жертв/укр-вербатима (CLAUDE.md, sanitize-strikes).

  python3 agents/gen-fuel-pages.py --list
  python3 agents/gen-fuel-pages.py benzin-na-trasse            # → drafts/fuel/<slug>.html
  python3 agents/gen-fuel-pages.py benzin-na-trasse --root     # → в корень
  python3 agents/gen-fuel-pages.py benzin-na-trasse --registry # строка для seo-topics.jsonl

ponytail: тот же news.css-лендинг, что у karta-bpla/rocket-danger; секции и FAQ
собираются из данных PAGES, чтобы контент жил в одном месте.
"""
import sys, pathlib, datetime, json

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = "https://npz-tactical-map.vercel.app"

PAGES = {}
# Обе страницы этого генератора (/benzin-na-trasse, /gde-dizel) сняты 22.08.2026:
# 2 визита за 30 дней у каждой, 301 -> /karta-azs (см. data/seo-topics.jsonl,
# status=dropped). Определения удалены, чтобы прогон генератора их не воскресил.
# Модуль остаётся живым: agents/azs-pages.py тянет отсюда рендер, шаблон и STYLE.

STYLE = """
    .landing-wrap{max-width:900px;margin:0 auto;padding:24px 20px 60px}
    .landing-hero{background:linear-gradient(135deg,rgba(230,194,89,.14),rgba(138,109,59,.08));border:1px solid rgba(230,194,89,.3);border-radius:16px;padding:32px 28px;margin-bottom:24px;position:relative;overflow:hidden}
    .landing-hero::before{content:"";position:absolute;top:-30px;right:-30px;width:120px;height:120px;background:radial-gradient(circle,rgba(230,194,89,.18),transparent 70%);border-radius:50%}
    .hero-label{display:inline-block;background:var(--gold,#e6c259);color:#2a2100;font-family:var(--mono);font-size:10px;font-weight:800;letter-spacing:1.5px;padding:3px 10px;border-radius:6px;margin-bottom:12px}
    .hero-h{font-size:28px;font-weight:800;line-height:1.2;margin-bottom:10px}
    .hero-sub{font-size:15px;color:var(--ink-dim);line-height:1.6;max-width:680px}
    .map-cta{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;margin:18px 0 4px;padding:16px 22px;background:var(--teal,#12a594);color:#fff;font-weight:800;font-size:16px;border-radius:12px;text-decoration:none;box-shadow:0 6px 20px rgba(18,165,148,.3);transition:.15s}
    .map-cta:hover{transform:translateY(-2px);box-shadow:0 10px 28px rgba(18,165,148,.45)}
    .map-cta .mc-ico{font-size:22px}
    .map-cta.inline{margin:20px 0;background:var(--surface);color:var(--ink);border:1.5px solid var(--teal,#12a594);box-shadow:none}
    .map-cta.inline:hover{background:rgba(18,165,148,.08);transform:translateY(-1px)}
    .status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:20px}
    .status-card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;text-align:center}
    .status-card .val{font-family:var(--mono);font-size:20px;font-weight:800;color:var(--gold,#b8892b)}
    .status-card .lbl{font-size:11px;color:var(--ink-dim);margin-top:4px}
    .section-h{font-size:20px;font-weight:800;margin:32px 0 14px;display:flex;align-items:center;gap:8px}
    .section-h .ico{font-size:22px}
    .lead-p{font-size:14px;line-height:1.7;color:var(--ink);margin-bottom:8px}
    .faq-wrap{margin:20px 0}
    .faq-item{background:var(--surface);border:1px solid var(--line);border-radius:12px;margin-bottom:10px;overflow:hidden}
    .faq-q{font-weight:700;font-size:14px;padding:14px 16px;cursor:pointer;display:flex;justify-content:space-between;align-items:center}
    .faq-q::after{content:"▼";font-size:10px;color:var(--ink-dim);transition:transform .2s}
    .faq-item.open .faq-q::after{transform:rotate(180deg)}
    .faq-a{padding:0 16px 14px;font-size:13px;line-height:1.6;color:var(--ink-dim);display:none}
    .faq-item.open .faq-a{display:block}
    .link-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin:16px 0}
    .link-card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px;text-decoration:none;color:var(--ink);transition:.15s}
    .link-card:hover{border-color:var(--teal);transform:translateY(-1px);box-shadow:var(--shadow-sm)}
    .link-card .lc-h{font-weight:700;font-size:13px;margin-bottom:4px}
    .link-card .lc-d{font-size:11px;color:var(--ink-dim)}
    .osint-note{margin-top:32px;font-size:11px;color:var(--ink-dim);background:var(--surface2);padding:12px;border-radius:10px;border-left:3px solid var(--amber);line-height:1.6}
    .updated-line{font-family:var(--mono);font-size:11px;color:var(--ink-dim);margin-top:6px}
"""

RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]

LINKS = [
    ("/", "🗺️ Карта НПЗ и дефицита", "Наличие топлива по сетям АЗС и регионам"),
    ("/karta-benzina-krym", "🗺️ Карта бензина Крым", "90+ АЗС Крыма: наличие, лимиты, цены"),
    ("/deficit", "⛽ Почему нет бензина", "Причины дефицита и прогноз"),
    ("/talony", "🎫 Бензин по талонам", "Где действуют талоны и лимиты"),
    ("/news", "📰 Сводки", "Ежедневный архив обстановки"),
    ("/sources", "📚 Источники", "Методология и OSINT-источники"),
]


def rus_date(d):
    return f"{d.day} {RU_MONTHS[d.month - 1]} {d.year}"


def esc_attr(s):
    return s.replace('"', "&quot;")


def render(key, today):
    p = PAGES[key]
    url = f"/{p['slug']}"
    faq_ld = ",\n      ".join(
        '{"@type": "Question", "name": "%s", "acceptedAnswer": {"@type": "Answer", "text": "%s"}}'
        % (q, _strip_tags(a)) for q, a in p["faq"]
    )
    sections_html = "\n".join(
        f'      <h2 class="section-h"><span class="ico">{ico}</span> {h}</h2>\n'
        + "\n".join(f'      <p class="lead-p">{para}</p>' for para in paras)
        for ico, h, paras in p["sections"]
    )
    faq_html = "\n".join(
        f'''        <div class="faq-item{' open' if i == 0 else ''}">
          <div class="faq-q" onclick="this.parentElement.classList.toggle('open')">{q}</div>
          <div class="faq-a">{a}</div>
        </div>''' for i, (q, a) in enumerate(p["faq"])
    )
    cards_html = "\n".join(
        f'          <div class="status-card"><div class="val">{v}</div><div class="lbl">{l}</div></div>'
        for v, l in p["cards"]
    )
    links_html = "\n".join(
        f'        <a class="link-card" href="{u}"><div class="lc-h">{h}</div><div class="lc-d">{d}</div></a>'
        for u, h, d in LINKS
    )
    cta_ico, cta_txt, cta_url = p["cta"]
    return TEMPLATE.format(
        site=SITE, url=url, title=p["title"], desc=p["desc"],
        kw=", ".join([p["primary_kw"]] + p["keywords"]),
        h1=p["h1"], sub=p["sub"], hero_label=p["hero_label"],
        cta_ico=cta_ico, cta_txt=cta_txt, cta_url=cta_url,
        cards=cards_html, sections=sections_html, faq=faq_html, links=links_html,
        faq_ld=faq_ld, iso=today.isoformat(), rus_date=rus_date(today),
        headline=esc_attr(p["title"]), desc_attr=esc_attr(p["desc"]),
    ).replace("__STYLE__", STYLE)


def _strip_tags(s):
    import re
    return re.sub(r"<[^>]+>", "", s).replace('"', '\\"')


TEMPLATE = """<!DOCTYPE html>
<html lang="ru" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <meta name="theme-color" content="#d23a2e">
  <title>{title}</title>
  <meta name="description" content="{desc}">
  <meta name="keywords" content="{kw}">
  <meta name="robots" content="index, follow">
  <meta name="language" content="Russian">
  <link rel="canonical" href="{site}{url}">

  <meta property="og:type" content="article">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:site_name" content="Топливный фронт РФ">
  <meta property="og:url" content="{site}{url}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:image" content="{site}/og-image.png">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{desc}">
  <meta name="twitter:image" content="{site}/og-image.png">

  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "{headline}",
    "datePublished": "{iso}",
    "dateModified": "{iso}",
    "image": ["{site}/og-image.png"],
    "author": {{"@type": "Organization", "name": "Топливный фронт РФ"}},
    "publisher": {{"@type": "Organization", "name": "Топливный фронт РФ", "url": "{site}/"}},
    "description": "{desc_attr}",
    "mainEntityOfPage": "{site}{url}",
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

  <script>window.va = window.va || function () {{ (window.vaq = window.vaq || []).push(arguments); }};</script>
  <script defer src="/_vercel/insights/script.js"></script>

  <link rel="stylesheet" href="/fonts.css">
  <link rel="stylesheet" href="/styles.css">
  <link rel="stylesheet" href="/news.css">
  <style>__STYLE__</style>
  <script src="/metrika.js" async></script>
</head>
<body data-theme="light">
  <header class="news-header">
    <div class="news-header-inner">
      <a href="/" class="news-logo" title="На карту">
        <span class="news-logo-icon">⛽</span>
        <span class="news-logo-text">ТОПЛИВНЫЙ ФРОНТ РФ</span>
      </a>
      <nav class="news-nav"><!-- сгенерит agents/build-nav.py --></nav>
    </div>
  </header>
  <main class="news-main">
    <div class="landing-wrap">

      <div class="landing-hero">
        <span class="hero-label">{hero_label}</span>
        <h1 class="hero-h">{h1}</h1>
        <p class="hero-sub">{sub}</p>
        <a class="map-cta" href="{cta_url}"><span class="mc-ico">{cta_ico}</span> {cta_txt}</a>
        <div class="status-grid">
{cards}
        </div>
        <div class="updated-line">Обновлено {rus_date}, МСК</div>
      </div>

{sections}
      <a class="map-cta inline" href="/"><span class="mc-ico">🗺️</span> Смотреть наличие топлива по регионам →</a>

      <h2 class="section-h"><span class="ico">❓</span> Частые вопросы</h2>
      <div class="faq-wrap">
{faq}
      </div>

      <h2 class="section-h"><span class="ico">🔗</span> Смотрите также</h2>
      <div class="link-grid">
{links}
      </div>

      <div class="osint-note">
        <strong>⚠️ Дисклеймер:</strong> Данные — <strong>оценка по открытым источникам</strong> (сообщения СМИ, данные сетей АЗС, публичный мониторинг). Это не официальная информация и <strong>не гарантия наличия топлива на конкретной заправке</strong>. Ситуация меняется быстро; при планировании поездки ориентируйтесь на свежие данные и официальные сообщения. Страница носит справочно-аналитический характер.
      </div>
    </div>
  </main>
  <script>
    const saved = localStorage.getItem('theme');
    if (saved) document.documentElement.dataset.theme = saved;
  </script>
  <script defer src="/nav-dropdown.js"></script>
</body>
</html>
"""

def main(argv):
    if not argv or argv[0] == "--list":
        for k, p in PAGES.items():
            print(f"{k:20} → /{p['slug']:20} [{p['type']}] {p['primary_kw']}")
        return
    key = argv[0]
    if key not in PAGES:
        sys.exit(f"нет страницы '{key}'. Доступны: {', '.join(PAGES)}")
    p = PAGES[key]
    if "--registry" in argv:
        print(json.dumps({
            "url": f"/{p['slug']}", "type": p["type"], "primary_kw": p["primary_kw"],
            "keywords": p["keywords"], "created": datetime.date.today().isoformat(),
            "status": "live",
            "note": "топливная ветка; воронка на карты/deficit; нейтральный тон. "
                    "Сгенерено agents/gen-fuel-pages.py.",
        }, ensure_ascii=False))
        return
    today = datetime.date.today()
    html = render(key, today)
    if "--root" in argv:
        out = ROOT / f"{p['slug']}.html"
    else:
        d = ROOT / "drafts" / "fuel"; d.mkdir(parents=True, exist_ok=True)
        out = d / f"{p['slug']}.html"
    out.write_text(html, encoding="utf-8")
    print(f"написано: {out.relative_to(ROOT)}  (url /{p['slug']})")


if __name__ == "__main__":
    main(sys.argv[1:])
