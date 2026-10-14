#!/usr/bin/env python3
"""Генератор рубрики «Всемирные новости» (/world/news) и её английской версии. Без LLM, только stdlib.

  python3 agents/world/gen-news.py [--date YYYY-MM-DD] [--archive P] [--out DIR]
                                   [--events P] [--index P] [--dry] [--rebuild]

Логика (docs/world-news-plan.md):
  * новый выпуск = одобренные события (review == "approved"), которых ещё нет ни в одном выпуске;
  * не более одного выпуска в сутки; нет новых событий -> нового выпуска нет (пустых страниц не бывает);
  * снимок ИТН и тексты событий замораживаются в архиве (data/world/news-archive.json),
    старые выпуски не пересчитываются по сегодняшнему index.json;
  * лид: lead_ru / lead_en из архива (черновик агента, одобренный владельцем), иначе шаблон из фактов;
  * EN-выпуск строится только если у ВСЕХ его событий есть title_en, summary_en (и fuel_effect_en при непустом fuel_effect);
  * нейтральность: тексты проходят agents/neutrality.text_reasons, иначе выпуск не создаётся;
  * пишет: world/news.html, world/news/<date>.html, world/rss.xml, en/world/news.html,
    en/world/news/<date>.html, en/world/rss.xml, sitemap-world.xml.
--rebuild: перерисовать страницы из архива, не создавая новый выпуск.
"""
import argparse
import datetime as dt
import html
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
try:
    import neutrality as NEU
except Exception:  # noqa: BLE001
    NEU = None

SITE = "https://npz-tactical-map.vercel.app"
MONTHS_RU = ["", "января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
             "сентября", "октября", "ноября", "декабря"]
MONTHS_EN = ["", "January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]
REGION_RU = {"europe": "Европа", "russia_cis": "Россия / СНГ", "middle_east": "Ближний Восток",
             "east_asia": "Восточная Азия", "south_asia": "Южная Азия", "north_america": "Северная Америка",
             "latin_america": "Латинская Америка", "africa": "Африка"}
REGION_EN = {"europe": "Europe", "russia_cis": "Russia / CIS", "middle_east": "Middle East",
             "east_asia": "East Asia", "south_asia": "South Asia", "north_america": "North America",
             "latin_america": "Latin America", "africa": "Africa"}
LEVEL_RU = {"calm": "спокойно", "tense": "напряжённо", "crisis": "кризис", "critical": "критично"}
LEVEL_EN = {"calm": "calm", "tense": "tense", "crisis": "crisis", "critical": "critical"}

L = {
    "ru": dict(lang="ru", locale="ru_RU", months=MONTHS_RU, reg=REGION_RU, lvl=LEVEL_RU,
               base="/world/news", home="/world", other_home="/en/world", other_base="/en/world/news",
               site_name="Всемирный топливный фронт", brand="Индекс топливной напряжённости (ИТН)", short="ИТН",
               h_index="Всемирные новости", h_index_sub="Проверенные события мирового топливного рынка и индекс топливной напряжённости. Выпуски выходят по событиям, не чаще раза в сутки.",
               idx_title="Всемирные новости о топливе — выпуски | Всемирный топливный фронт",
               idx_desc="Выпуски «Всемирных новостей»: проверенные события мирового топливного рынка (проливы, удары по судам и инфраструктуре, запасы, ОПЕК+, дефициты) и индекс топливной напряжённости. Оценка OSINT.",
               art_title="Всемирные новости о топливе, {d}: {t}", art_h="Всемирные новости, {d}",
               disc="ОЦЕНКА · OSINT, не официальные данные. Индекс считает скрипт по открытым рядам; события на балл не влияют.",
               world="Мировой ИТН", of100="из 100", d1="за сутки", cover="покрытие данных", snap="Снимок индекса",
               what="События выпуска", regions="Регионы на момент выпуска", method="Методика расчёта индекса",
               confirmed="подтверждено", reported="по сообщениям, один источник", effect="Влияние на топливо",
               sources="Источники", map_link="Карта и индекс в реальном времени", all="Все выпуски",
               prev="← Предыдущий", next="Следующий →", low="мало данных", n_ev=("событие", "события", "событий"),
               lead_t="Выпуск включает {n} {evw}. Мировой индекс топливной напряжённости на момент выпуска — {v} из 100 ({lvl}), за сутки {d}, покрытие данных {c}%. {main}",
               lead_main="Главное событие: {t}.", empty="Выпусков пока нет.", switch="English",
               lead_nv="Выпуск включает {n} {evw}. Индекс на момент выпуска не рассчитан. {main}"),
    "en": dict(lang="en", locale="en_US", months=MONTHS_EN, reg=REGION_EN, lvl=LEVEL_EN,
               base="/en/world/news", home="/en/world", other_home="/world", other_base="/world/news",
               site_name="World Fuel Front", brand="Fuel Tension Index (FTI)", short="FTI",
               h_index="World news", h_index_sub="Verified events in the global fuel market and the Fuel Tension Index. Issues are published when events occur, at most once a day.",
               idx_title="World fuel news — issues | World Fuel Front",
               idx_desc="Issues of World news: verified global fuel-market events (chokepoints, attacks on shipping and infrastructure, stocks, OPEC+, shortages) and the Fuel Tension Index. ESTIMATE based on open data (OSINT).",
               art_title="World fuel news, {d}: {t}", art_h="World news, {d}",
               disc="ESTIMATE · OSINT, not official data. The index is computed by a script from open series; events do not affect the score.",
               world="World FTI", of100="out of 100", d1="24h", cover="data coverage", snap="Index snapshot",
               what="Events in this issue", regions="Regions at the time of issue", method="Index methodology",
               confirmed="confirmed", reported="reported, single source", effect="Effect on fuel",
               sources="Sources", map_link="Live map and index", all="All issues",
               prev="← Previous", next="Next →", low="insufficient data", n_ev=("event", "events", "events"),
               lead_t="This issue covers {n} {evw}. The world Fuel Tension Index at the time of issue is {v} out of 100 ({lvl}), {d} over 24 hours, data coverage {c}%. {main}",
               lead_main="Main event: {t}.", empty="No issues yet.", switch="Русский",
               lead_nv="This issue covers {n} {evw}. The index was not available at the time of issue. {main}"),
}


def esc(x):
    return html.escape(str(x if x is not None else ""), quote=True)


def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_atomic(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def fmt_date(d, lg):
    y, m, dd = (int(x) for x in d.split("-"))
    return f"{dd} {L[lg]['months'][m]} {y}"


def plural_ru(n, forms):
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def ev_words(n, lg):
    if lg == "ru":
        return plural_ru(n, L["ru"]["n_ev"])
    return L["en"]["n_ev"][0 if n == 1 else 1]


def en_complete(e):
    if not (e.get("title_en") and e.get("summary_en")):
        return False
    return not e.get("fuel_effect") or bool(e.get("fuel_effect_en"))


def order_events(evs):
    return sorted(evs, key=lambda e: (e.get("status") != "confirmed", _neg(e.get("occurred_at")), e.get("id", "")))


def _neg(d):
    return "".join(chr(255 - ord(c)) for c in str(d or ""))


def snapshot_index(idx):
    if not idx:
        return None
    w = idx.get("world") or {}
    regs = {}
    for rid, r in (idx.get("regions") or {}).items():
        regs[rid] = {"value": r.get("value"), "level": r.get("level"), "delta_1d": r.get("delta_1d"),
                     "coverage": r.get("coverage")}
    return {"generated_at": idx.get("generated_at"), "methodology_version": idx.get("methodology_version"),
            "world": {"value": w.get("value"), "level": w.get("level"), "delta_1d": w.get("delta_1d"),
                      "coverage": w.get("coverage")}, "regions": regs}


def txt(e, f, lg):
    return (e.get(f + "_en") if lg == "en" else e.get(f)) or ""


def make_lead(issue, lg):
    custom = issue.get("lead_" + lg)
    if custom:
        return custom
    T = L[lg]
    evs = order_events(issue["events"])
    n = len(evs)
    main = T["lead_main"].format(t=txt(evs[0], "title", lg).rstrip(".")) if evs else ""
    w = (issue.get("index") or {}).get("world") or {}
    if isinstance(w.get("value"), (int, float)):
        d = w.get("delta_1d")
        ds = "без изменений" if (lg == "ru" and not d) else ("unchanged" if not d else (f"{d:+d}".replace("-", "−")))
        return T["lead_t"].format(n=n, evw=ev_words(n, lg), v=w["value"], lvl=T["lvl"].get(w.get("level"), "—"),
                                  d=ds, c=round((w.get("coverage") or 0) * 100), main=main).strip()
    return T["lead_nv"].format(n=n, evw=ev_words(n, lg), main=main).strip()


def neutral_problems(issue):
    out = []
    if NEU is None:
        return out
    texts = [issue.get("lead_ru"), issue.get("lead_en")]
    for e in issue["events"]:
        texts += [e.get(f) for f in ("title", "summary", "fuel_effect")]
    for t in texts:
        if isinstance(t, str) and t:
            out += [r[0] for r in NEU.text_reasons(t)]
    return out


# ------------------------------ HTML ------------------------------
CSS = '<link rel="stylesheet" href="/world-news.css">'


def head(lg, title, desc, canonical, alts, extra="", robots=None, og_type="article"):
    T = L[lg]
    h = ['<!doctype html>', f'<html lang="{lg}">', '<head>', '<meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">', '<meta name="color-scheme" content="light">',
         f'<title>{esc(title)}</title>', f'<meta name="description" content="{esc(desc)}">']
    if robots:
        h.append(f'<meta name="robots" content="{robots}">')
    h.append(f'<link rel="canonical" href="{SITE}{canonical}">')
    for code, path in alts:
        h.append(f'<link rel="alternate" hreflang="{code}" href="{SITE}{path}">')
    h += [f'<meta property="og:type" content="{og_type}">', f'<meta property="og:locale" content="{T["locale"]}">',
          f'<meta property="og:site_name" content="{esc(T["site_name"])}">',
          f'<meta property="og:title" content="{esc(title)}">', f'<meta property="og:description" content="{esc(desc)}">',
          f'<meta property="og:url" content="{SITE}{canonical}">', f'<meta property="og:image" content="{SITE}/og-image.png">',
          '<meta name="twitter:card" content="summary_large_image">',
          f'<link rel="alternate" type="application/rss+xml" title="{esc(T["site_name"])} (RSS)" href="{SITE}{T["base"].replace("/news", "")}/rss.xml">',
          CSS, extra, '</head>', '<body>']
    return "\n".join(h)


def topbar(lg, other_path):
    T = L[lg]
    sw = (f'<span class="lang-sw" role="group" aria-label="Language"><b aria-current="true">{lg.upper()}</b>'
          f'<a href="{other_path}" hreflang="{"en" if lg == "ru" else "ru"}" lang="{"en" if lg == "ru" else "ru"}">{"EN" if lg == "ru" else "RU"}</a></span>'
          if other_path else "")
    return (f'<header class="topbar"><a class="brand" href="{T["home"]}">{esc(T["site_name"].upper())}</a>'
            f'<nav><a href="{T["home"]}">{esc(T["map_link"])}</a><a href="{T["base"]}">{esc(T["h_index"])}</a>{sw}</nav></header>')


def event_card(e, lg):
    T = L[lg]
    st = T["confirmed"] if e.get("status") == "confirmed" else T["reported"]
    srcs = "".join(
        f'<li><a href="{esc(s.get("url"))}" rel="noopener nofollow" target="_blank">{esc(s.get("publisher") or s.get("url"))}</a>'
        f'{" · <time>" + esc(s.get("date")) + "</time>" if s.get("date") else ""}</li>' for s in (e.get("sources") or []))
    untr = lg == "en" and not en_complete(e)  # на EN-странице не бывает (выпуск не строится), страховка
    eff = txt(e, "fuel_effect", lg)
    return (f'<article class="ev" id="{esc(e["id"])}"><div class="ev-meta"><span class="badge {"c" if e.get("status") == "confirmed" else "r"}">{esc(st)}</span> '
            f'<span>{esc(T["reg"].get(e.get("region"), e.get("region")))}</span> · <time datetime="{esc(e.get("occurred_at"))}">{esc(fmt_date(e["occurred_at"], lg))}</time></div>'
            f'<h3{" lang=\"ru\"" if untr else ""}>{esc(txt(e, "title", lg))}</h3><p>{esc(txt(e, "summary", lg))}</p>'
            + (f'<p class="eff"><b>{esc(T["effect"])}.</b> {esc(eff)}</p>' if eff else "")
            + f'<h4>{esc(T["sources"])}</h4><ul>{srcs}</ul></article>')


def regions_block(issue, lg):
    T = L[lg]
    regs = (issue.get("index") or {}).get("regions") or {}
    rows = []
    for rid, r in sorted(regs.items(), key=lambda kv: -(kv[1].get("value") if isinstance(kv[1].get("value"), (int, float)) else -1)):
        v = r.get("value")
        val = f'{v}' if isinstance(v, (int, float)) else esc(T["low"])
        lv = T["lvl"].get(r.get("level"), "") if isinstance(v, (int, float)) else ""
        rows.append(f'<tr><td>{esc(T["reg"].get(rid, rid))}</td><td class="num">{val}</td><td>{esc(lv)}</td></tr>')
    return f'<table class="rt"><tbody>{"".join(rows)}</tbody></table>' if rows else ""


def issue_page(issue, lg, issues_for_lang, alt):
    T = L[lg]
    d = issue["date"]
    evs = order_events(issue["events"])
    main_t = txt(evs[0], "title", lg).rstrip(".")
    short = main_t if len(main_t) <= 90 else main_t[:88].rsplit(" ", 1)[0] + "…"
    title = T["art_title"].format(d=fmt_date(d, lg), t=short) + " | " + T["site_name"]
    lead = make_lead(issue, lg)
    desc = lead if len(lead) <= 300 else lead[:297].rsplit(" ", 1)[0] + "…"
    canonical = f'{T["base"]}/{d}'
    alts = [("ru", f"/world/news/{d}")] + ([("en", f"/en/world/news/{d}")] if alt else [])
    alts.append(("x-default", f"/world/news/{d}")) if alt else None
    if not alt:
        alts = []
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": T["art_title"].format(d=fmt_date(d, lg), t=short)[:110],
          "inLanguage": lg, "datePublished": issue.get("published_at") or d, "dateModified": issue.get("updated_at") or issue.get("published_at") or d,
          "author": {"@type": "Organization", "name": T["site_name"]},
          "publisher": {"@type": "Organization", "name": T["site_name"], "url": SITE + "/"},
          "mainEntityOfPage": SITE + canonical, "isAccessibleForFree": True, "description": desc,
          "citation": [s.get("url") for e in evs for s in (e.get("sources") or []) if s.get("url")][:12]}
    extra = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False) + '</script>'
    snap = issue.get("index") or {}
    w = snap.get("world") or {}
    gauge = ""
    if isinstance(w.get("value"), (int, float)):
        dd = w.get("delta_1d")
        gauge = (f'<section class="panel"><h2>{esc(T["snap"])}</h2><p class="big"><span class="num">{w["value"]}</span> {esc(T["of100"])} · {esc(T["lvl"].get(w.get("level"), ""))}</p>'
                 f'<p class="muted">{esc(T["world"])} · {esc(T["d1"])}: {"" if dd is None else f"{dd:+d}".replace("-", "−")} · {esc(T["cover"])}: {round((w.get("coverage") or 0) * 100)}%'
                 f'{" · " + esc(snap.get("generated_at")) if snap.get("generated_at") else ""}</p>{regions_block(issue, lg)}</section>')
    idx_sorted = sorted(issues_for_lang, key=lambda i: i["date"])
    pos = [i["date"] for i in idx_sorted].index(d)
    nav = []
    if pos > 0:
        nav.append(f'<a rel="prev" href="{T["base"]}/{idx_sorted[pos - 1]["date"]}">{esc(T["prev"])}</a>')
    nav.append(f'<a href="{T["base"]}">{esc(T["all"])}</a>')
    if pos < len(idx_sorted) - 1:
        nav.append(f'<a rel="next" href="{T["base"]}/{idx_sorted[pos + 1]["date"]}">{esc(T["next"])}</a>')
    other = f'{T["other_base"]}/{d}' if alt else None
    body = (head(lg, title, desc, canonical, alts, extra, og_type="article") + "\n" + topbar(lg, other)
            + f'<main class="wrap"><p class="est">{esc(T["disc"])}</p><h1>{esc(T["art_h"].format(d=fmt_date(d, lg)))}</h1>'
            f'<p class="lead">{esc(lead)}</p>{gauge}<h2>{esc(T["what"])}</h2>' + "".join(event_card(e, lg) for e in evs)
            + f'<p class="muted"><a href="{T["home"]}#method">{esc(T["method"])}</a> · <a href="{T["home"]}">{esc(T["map_link"])}</a></p>'
            f'<nav class="pn">{" ".join(nav)}</nav></main></body></html>\n')
    return body


def index_page(lg, issues, any_pair):
    T = L[lg]
    issues = sorted(issues, key=lambda i: i["date"], reverse=True)
    cards = []
    for i in issues:
        evs = order_events(i["events"])
        w = (i.get("index") or {}).get("world") or {}
        v = f' · {esc(T["short"])} {w["value"]}' if isinstance(w.get("value"), (int, float)) else ""
        cards.append(f'<a class="card" href="{T["base"]}/{i["date"]}"><time datetime="{i["date"]}">{esc(fmt_date(i["date"], lg))}</time>{v}'
                     f'<strong>{esc(txt(evs[0], "title", lg))}</strong><span>{len(evs)} {esc(ev_words(len(evs), lg))}</span></a>')
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": T["h_index"], "inLanguage": lg,
          "url": SITE + T["base"], "description": T["idx_desc"]}
    extra = '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False) + '</script>'
    alts = [("ru", "/world/news"), ("en", "/en/world/news"), ("x-default", "/world/news")] if any_pair else []
    robots = None if issues else "noindex, follow"
    other = T["other_base"] if any_pair else None
    return (head(lg, T["idx_title"], T["idx_desc"], T["base"], alts, extra, robots=robots, og_type="website") + "\n" + topbar(lg, other)
            + f'<main class="wrap"><p class="est">{esc(T["disc"])}</p><h1>{esc(T["h_index"])}</h1><p class="lead">{esc(T["h_index_sub"])}</p>'
            f'<div class="cards">{"".join(cards) if cards else "<p>" + esc(T["empty"]) + "</p>"}</div></main></body></html>\n')


def rss(lg, issues):
    T = L[lg]
    items = []
    for i in sorted(issues, key=lambda x: x["date"], reverse=True)[:30]:
        evs = order_events(i["events"])
        pub = dt.datetime.strptime(i["date"], "%Y-%m-%d").strftime("%a, %d %b %Y 00:00:00 +0000")
        items.append(f'<item><title>{esc(T["art_h"].format(d=fmt_date(i["date"], lg)) + ": " + txt(evs[0], "title", lg))}</title>'
                     f'<link>{SITE}{T["base"]}/{i["date"]}</link><guid>{SITE}{T["base"]}/{i["date"]}</guid><pubDate>{pub}</pubDate>'
                     f'<description>{esc(make_lead(i, lg))}</description></item>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            f'<title>{esc(T["site_name"] + " — " + T["h_index"])}</title><link>{SITE}{T["base"]}</link>'
            f'<description>{esc(T["idx_desc"])}</description><language>{lg}</language>' + "".join(items) + '</channel></rss>\n')


def sitemap(ru_issues, en_issues):
    en_dates = {i["date"] for i in en_issues}
    ents = [("/world", "/en/world", "daily", "0.7"), ("/world/news", "/en/world/news" if en_issues else None, "daily", "0.7")]
    for i in sorted(ru_issues, key=lambda x: x["date"], reverse=True):
        d = i["date"]
        ents.append((f"/world/news/{d}", f"/en/world/news/{d}" if d in en_dates else None, "monthly", "0.6"))
    body = []
    for ru, en, fr, pr in ents:
        alt = f'<xhtml:link rel="alternate" hreflang="ru" href="{SITE}{ru}"/>'
        if en:
            alt += f'<xhtml:link rel="alternate" hreflang="en" href="{SITE}{en}"/><xhtml:link rel="alternate" hreflang="x-default" href="{SITE}{ru}"/>'
        body.append(f'  <url><loc>{SITE}{ru}</loc><changefreq>{fr}</changefreq><priority>{pr}</priority>{alt}</url>')
        if en:
            body.append(f'  <url><loc>{SITE}{en}</loc><changefreq>{fr}</changefreq><priority>{pr}</priority>{alt}</url>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "\n".join(body) + '\n</urlset>\n')


def create_issue(events, archive, idx, date):
    """-> новый выпуск (dict) или None. Чистая функция по входным данным."""
    issues = archive.get("issues", [])
    if any(i["date"] == date for i in issues):
        return None  # не более одного выпуска в сутки
    used = {eid for i in issues for eid in i.get("event_ids", [])}
    new = [e for e in events if e.get("review") == "approved" and e.get("id") not in used]
    if not new:
        return None
    new = order_events(new)
    return {"date": date, "published_at": now_iso(), "updated_at": None, "event_ids": [e["id"] for e in new],
            "events": new, "index": snapshot_index(idx), "lead_ru": None, "lead_en": None}


def build_all(archive, out):
    issues = archive.get("issues", [])
    ru = sorted(issues, key=lambda i: i["date"])
    en = [i for i in ru if all(en_complete(e) for e in i["events"])]
    en_dates = {i["date"] for i in en}
    for i in ru:
        write_atomic(os.path.join(out, "world", "news", i["date"] + ".html"), issue_page(i, "ru", ru, i["date"] in en_dates))
    for i in en:
        write_atomic(os.path.join(out, "en", "world", "news", i["date"] + ".html"), issue_page(i, "en", en, True))
    write_atomic(os.path.join(out, "world", "news.html"), index_page("ru", ru, bool(en)))
    write_atomic(os.path.join(out, "en", "world", "news.html"), index_page("en", en, bool(en)))
    write_atomic(os.path.join(out, "world", "rss.xml"), rss("ru", ru))
    write_atomic(os.path.join(out, "en", "world", "rss.xml"), rss("en", en))
    write_atomic(os.path.join(out, "sitemap-world.xml"), sitemap(ru, en))
    return len(ru), len(en)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--archive", default=os.path.join(ROOT, "data", "world", "news-archive.json"))
    ap.add_argument("--events", default=os.path.join(ROOT, "data", "world", "events.json"))
    ap.add_argument("--index", default=os.path.join(ROOT, "data", "world", "index.json"))
    ap.add_argument("--out", default=ROOT)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args(argv)
    archive = load(a.archive, {"issues": []})
    archive.setdefault("issues", [])
    if not a.rebuild:
        ev = (load(a.events, {}) or {}).get("events", [])
        issue = create_issue(ev, archive, load(a.index, None), a.date)
        if issue:
            bad = neutral_problems(issue)
            if bad:
                print("ОТКАЗ: нейтральность:", "; ".join(sorted(set(bad))))
                return 2
            archive["issues"].append(issue)
            print(f"новый выпуск {issue['date']}: {len(issue['events'])} соб.")
        else:
            print("нового выпуска нет")
    if a.dry:
        return 0
    archive["generated_at"] = now_iso()
    write_atomic(a.archive, json.dumps(archive, ensure_ascii=False, indent=1) + "\n")
    n_ru, n_en = build_all(archive, a.out)
    print(f"страницы: RU {n_ru}, EN {n_en}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
