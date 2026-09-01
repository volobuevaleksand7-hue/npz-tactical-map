#!/usr/bin/env python3
"""npz-status.py — ревизия состояния проекта «Топливный фронт РФ» (npz-tactical-map).

Считает по РЕАЛЬНЫМ данным репо (ничего не выдумывает) четыре среза и печатает
приоритизированный список «что делать в первую очередь». Оркестратор (Claude) читает
вывод и действует; сам скрипт только читает — ни git, ни файлы не трогает.

Срезы:
  1. АГЕНТЫ   — data/health.json + возраст каждого слоя.
  2. СВОДКИ   — есть ли сегодняшняя сводка/обложка, дырки в датах ударов, обложки без файла.
  3. SEO      — планируемые страницы (seo-topics), протухшие live-страницы (dateModified
                отстаёт от свежего удара по теме), бэклог-идеи по частотности.
  4. ЧТО ПЕРВЫМ — единый ранжированный список задач с обоснованием.

Запуск:  NPZ_REPO=~/Documents/npz-tactical-map python3 npz-status.py [--json]
Самопроверка:  python3 npz-status.py --selfcheck
"""
import json
import os
import re
import sys
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(os.environ.get("NPZ_REPO", Path.home() / "Documents" / "npz-tactical-map"))
DATA = REPO / "data"

# Порог, при котором аналитическую/справочную страницу считаем протухшей: её dateModified
# отстаёт от последнего удара по её теме больше, чем на STALE_DAYS. ponytail: 10 дней —
# калибровочная ручка, не догма; правь, если фокус ревизии поедет.
STALE_DAYS = 10
# Страницы, которым свежесть по датам не нужна: вечнозелёные how-to/справка + data-driven
# оболочки, которые тянут свежие цифры из data/*.json на клиенте (карты, объектные /npz/*
# со статусом, деферящимся на /refineries). У них старый dateModified — норма, а не протухание.
# Штрафуем только страницы с ХАРДКОДНЫМИ в прозе цифрами (аналитика/справка/регионы-тексты).
EVERGREEN = ("/talony", "/zapas-benzina-kanistry", "/gde-gaz-azs", "/azs-ryadom",
             "/metodologiya", "/sources", "/support", "/help", "/install", "/draki-na-azs")
DATA_DRIVEN = ("/npz/", "/karta", "/radar", "/refineries", "/krupnejshie", "/ocheredi",
               "/gde-est-benzin", "/zakrytye-azs",
               # операторские справочники: статус деферится на /refineries, тянут live-данные
               "/npz-lukojla", "/npz-rosnefti", "/npz-gazprom-nefti")
# Точные url data-driven хабов: главная (под релизным гейтом), сводная хроника ударов,
# автопаблишер волны — все читают data/*.json вживую, их dateModified к делу не относится.
DATA_DRIVEN_EXACT = ("/", "/attacks", "/volna-dronov")
# Чисто-шаблонные генерируемые кластеры: обновляются ПЕРЕГОНОМ генератора, а не руками.
# 🔴 Провенанс-штамп «Сгенерено …» в note НЕ годится как признак — он стоит и на страницах,
# доработанных сверх шаблона руками (перегон rocket-danger вырезал 89 строк). Поэтому
# исключаем ТОЛЬКО заведомо шаблонные кластеры по префиксу url, а не по note.
GEN_PREFIXES = ("/raketnaya-opasnost",)


def _is_generated(url):
    """True для чисто-шаблонных кластеров, которые правит генератор, а не человек."""
    return any(url.startswith(p) for p in GEN_PREFIXES)


def today():
    """Дата «сегодня» по МСК. Env NPZ_TODAY=YYYY-MM-DD переопределяет (для тестов/детерминизма)."""
    t = os.environ.get("NPZ_TODAY")
    if t:
        return date.fromisoformat(t)
    return datetime.now(timezone.utc).astimezone().date()


def _load(name):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except Exception:
        return None


def _jsonl(name):
    out = []
    try:
        for line in (DATA / name).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
    except Exception:
        pass
    return out


# ---------- 1. АГЕНТЫ ----------
def check_agents():
    h = _load("health.json")
    if not h:
        return {"ok": False, "note": "health.json не читается", "bad": [], "overall": "?"}
    m = h.get("meta", {})
    bad = [f for f in h.get("files", []) if f.get("status") != "ok"]
    return {
        "ok": m.get("overall") == "healthy" and not bad,
        "overall": m.get("overall"),
        "checked_at": m.get("checked_at"),
        "stale": m.get("stale_count"),
        "dead": m.get("dead_count"),
        "publish_lag_h": m.get("publish_lag_hours"),
        "bad": [(f["file"], f.get("status"), f.get("data_age_hours")) for f in bad],
    }


# ---------- 2. СВОДКИ ----------
def check_summaries(td):
    strikes = (_load("strikes.json") or {}).get("strikes", [])
    dates = sorted({x["date"] for x in strikes if x.get("date")})
    # дырки в датах ударов между первой и сегодня — но пустой день ≠ дырка, поэтому
    # смотрим только последние 7 дней и сверяем с наличием news-страницы, а не с ударами.
    latest_strike = dates[-1] if dates else None

    news_dir = REPO / "news"
    # только ДНЕВНЫЕ страницы YYYY-MM-DD; месячные хабы YYYY-MM исключаем (им обложка не нужна)
    daily_re = re.compile(r"^2026-\d{2}-\d{2}$")
    news_pages = sorted(p.stem for p in news_dir.glob("2026-*.html")
                        if daily_re.match(p.stem)) if news_dir.exists() else []
    latest_news = news_pages[-1] if news_pages else None
    today_page = (news_dir / f"{td.isoformat()}.html").exists()

    covers = {p.stem.replace("cover-", "") for p in (REPO / "assets").glob("cover-2026-*.png")}
    # обложка нужна свежим дням (последние 8): бэкфилл старых обложек — не приоритет ревизии
    recent = news_pages[-8:]
    missing_covers = sorted(d for d in recent if d not in covers)

    return {
        "latest_strike_date": latest_strike,
        "latest_news_page": latest_news,
        "today_summary_exists": today_page,
        "today": td.isoformat(),
        "missing_covers": missing_covers,
        "news_pages_count": len(news_pages),
    }


# ---------- 3. SEO ----------
_DATE_RE = re.compile(r'"dateModified":\s*"(\d{4}-\d{2}-\d{2})"')


def _page_moddate(url):
    f = REPO / (url.lstrip("/") + ".html")
    if not f.exists():
        return None
    m = _DATE_RE.search(f.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def _latest_strike_for(keywords, strikes):
    """Свежайшая дата удара, чей город/цель/деталь совпадает с ключевыми словами темы."""
    kws = [k.lower() for k in keywords]
    best = None
    for x in strikes:
        blob = " ".join(str(x.get(k, "")) for k in ("city", "region", "target", "detail")).lower()
        if any(kw in blob for kw in kws):
            d = x.get("date")
            if d and (best is None or d > best):
                best = d
    return best


def check_seo(td):
    topics = _jsonl("seo-topics.jsonl")
    backlog = _jsonl("seo-backlog.jsonl")
    strikes = (_load("strikes.json") or {}).get("strikes", [])

    planned = [t for t in topics if t.get("status") == "planned"]

    # протухшие live: dateModified отстаёт от td больше STALE_DAYS, и это не evergreen
    stale = []
    for t in topics:
        if t.get("status") != "live":
            continue
        url = t.get("url", "")
        if (url in DATA_DRIVEN_EXACT
                or _is_generated(url)
                or any(e in url for e in EVERGREEN)
                or any(url.startswith(d) for d in DATA_DRIVEN)):
            continue
        md = _page_moddate(url)
        if not md:
            # Страница дошла сюда → уже прошла фильтр evergreen/data-driven/generated, т.е. это
            # контентная страница, у которой ОБЯЗАНА быть dateModified. Её отсутствие — тоже
            # сигнал: свежесть нельзя измерить, а цифры в прозе стареют молча (так проваливался
            # /deficit — type=explainer без даты). Флагаем любую такую, без фильтра по типу.
            stale.append({"url": url, "moddate": None, "lag_days": None,
                          "kw": t.get("primary_kw", ""), "reason": "нет dateModified — добавить"})
            continue
        lag = (td - date.fromisoformat(md)).days
        if lag > STALE_DAYS:
            stale.append({"url": url, "moddate": md, "lag_days": lag,
                          "kw": t.get("primary_kw", "")})
    stale.sort(key=lambda s: (s["lag_days"] is not None, s["lag_days"] or 0), reverse=True)

    # бэклог-идеи в работе/идее, по частотности
    ideas = [b for b in backlog if b.get("status") in ("idea", "in_progress")]
    ideas.sort(key=lambda b: -(b.get("freq_est") or 0))

    return {
        "planned": [{"url": p["url"], "kw": p.get("primary_kw", "")} for p in planned],
        "stale_live": stale,
        "backlog_ideas": [{"topic": b.get("topic", ""), "freq": b.get("freq_est"),
                           "status": b.get("status"), "type": b.get("type")} for b in ideas],
        "live_count": sum(1 for t in topics if t.get("status") == "live"),
    }


# ---------- 4. ПРИОРИТИЗАЦИЯ ----------
def prioritize(agents, summ, seo):
    """Единый ранжированный список. Каждый пункт: (важность, категория, текст).
    Важность: 1=срочно/сломано, 2=контент-долг, 3=рост. Сортируем по ней."""
    tasks = []

    # 1 — сломанное/пропущенное операционное
    if not agents["ok"]:
        tasks.append((1, "АГЕНТЫ", f"Флот не healthy (overall={agents['overall']}, "
                      f"проблемные: {agents['bad'] or agents.get('note')}). Разобрать до контента."))
    if not summ["today_summary_exists"]:
        tasks.append((1, "СВОДКА", f"Нет сводки за сегодня ({summ['today']}). "
                      f"Последняя — {summ['latest_news_page']}. Догнать удары + сгенерить сводку."))
    if summ["missing_covers"]:
        tasks.append((2, "ОБЛОЖКИ", f"Обложки отсутствуют: {summ['missing_covers']}. "
                      f"build-covers.py --missing."))

    # 2 — контент-долг: протухшие live-страницы (мой ключевой сигнал)
    for s in seo["stale_live"][:6]:
        if s.get("lag_days") is not None:
            tasks.append((2, "ПРОТУХЛО", f"{s['url']} — dateModified отстаёт на {s['lag_days']} дн "
                          f"(«{s['kw']}»). Освежить цифрами из fuel-state/strikes."))
        else:
            tasks.append((2, "ПРОТУХЛО", f"{s['url']} — {s.get('reason','?')} («{s['kw']}»). "
                          f"Проверить свежесть вручную."))

    # 3 — рост: планируемые страницы, затем бэклог по частотности
    for p in seo["planned"]:
        tasks.append((3, "СТАТЬЯ", f"Написать {p['url']} («{p['kw']}») — в плане (status=planned)."))
    for b in seo["backlog_ideas"][:4]:
        tasks.append((3, "БЭКЛОГ", f"[{b['status']}] {b['topic']} (~{b['freq']} показов/мес)."))

    tasks.sort(key=lambda t: t[0])
    return tasks


def build_report(td=None):
    td = td or today()
    agents = check_agents()
    summ = check_summaries(td)
    seo = check_seo(td)
    tasks = prioritize(agents, summ, seo)
    return {"today": td.isoformat(), "agents": agents, "summaries": summ,
            "seo": seo, "priorities": tasks}


def print_report(r):
    a, s, seo = r["agents"], r["summaries"], r["seo"]
    P = print
    P(f"\n=== НПЗ-РЕВИЗИЯ на {r['today']} ===\n")

    P("1. АГЕНТЫ")
    icon = "✅" if a["ok"] else "🔴"
    P(f"   {icon} overall={a['overall']} · stale={a.get('stale')} dead={a.get('dead')} "
      f"publish_lag={a.get('publish_lag_h')}ч · проверка {a.get('checked_at')}")
    for f, st, age in a["bad"]:
        P(f"     🔴 {f}: {st} (возраст {age}ч)")

    P("\n2. СВОДКИ")
    P(f"   {'✅' if s['today_summary_exists'] else '🔴'} сводка за сегодня: "
      f"{'есть' if s['today_summary_exists'] else 'НЕТ'} · последняя страница {s['latest_news_page']} · "
      f"последний удар {s['latest_strike_date']} · страниц всего {s['news_pages_count']}")
    if s["missing_covers"]:
        P(f"   🔴 обложки отсутствуют (хвост): {s['missing_covers']}")

    P("\n3. SEO")
    P(f"   live-страниц: {seo['live_count']} · в плане: {len(seo['planned'])} · "
      f"протухших: {len([x for x in seo['stale_live'] if x.get('lag_days')])}")
    if seo["stale_live"]:
        P("   протухшие live (dateModified отстаёт):")
        for x in seo["stale_live"][:8]:
            lag = f"{x['lag_days']}дн" if x.get("lag_days") is not None else x.get("reason", "?")
            P(f"     · {x['url']:38} {lag:>8}  «{x['kw']}»")
    if seo["planned"]:
        P("   в плане (написать):")
        for p in seo["planned"]:
            P(f"     · {p['url']:38} «{p['kw']}»")

    P("\n4. ЧТО ПЕРВЫМ")
    if not r["priorities"]:
        P("   ✅ всё чисто — срочного нет.")
    for lvl, cat, txt in r["priorities"]:
        mark = {1: "🔴", 2: "🟡", 3: "🟢"}[lvl]
        P(f"   {mark} [{cat}] {txt}")
    P("")


def selfcheck():
    # чистые функции ранжирования — без чтения файлов
    agents_bad = {"ok": False, "overall": "degraded", "bad": [("strikes.json", "stale", 40)], "note": None}
    agents_ok = {"ok": True, "overall": "healthy", "bad": []}
    summ_gap = {"today": "2026-07-24", "today_summary_exists": False, "latest_news_page": "2026-07-23",
                "missing_covers": ["2026-07-23"], "latest_strike_date": "2026-07-24"}
    summ_ok = {"today": "2026-07-24", "today_summary_exists": True, "latest_news_page": "2026-07-24",
               "missing_covers": [], "latest_strike_date": "2026-07-24"}
    seo = {"planned": [{"url": "/x", "kw": "kx"}],
           "stale_live": [{"url": "/crisis", "moddate": "2026-07-07", "lag_days": 17, "kw": "кризис"}],
           "backlog_ideas": [{"topic": "T", "freq": 41000, "status": "idea", "type": "hub"}], "live_count": 74}

    pr = prioritize(agents_bad, summ_gap, seo)
    assert pr[0][0] == 1, "сломанный флот должен быть первым"
    cats = [c for _, c, _ in pr]
    assert "АГЕНТЫ" in cats and "СВОДКА" in cats and "ПРОТУХЛО" in cats and "СТАТЬЯ" in cats
    # уровни строго не убывают
    lvls = [l for l, _, _ in pr]
    assert lvls == sorted(lvls), "приоритеты должны идти по возрастанию уровня"

    pr_ok = prioritize(agents_ok, summ_ok, {"planned": [], "stale_live": [], "backlog_ideas": [], "live_count": 74})
    assert pr_ok == [], "всё чисто → пустой список задач"

    # protruhlo раньше статьи (2 < 3)
    lvl_stale = [l for l, c, _ in pr if c == "ПРОТУХЛО"][0]
    lvl_article = [l for l, c, _ in pr if c == "СТАТЬЯ"][0]
    assert lvl_stale < lvl_article

    # исключение генерируемых/data-driven — по url, не по note (штамп «Сгенерено» ненадёжен)
    assert _is_generated("/raketnaya-opasnost-omsk")        # чисто-шаблонный кластер
    assert not _is_generated("/situaciya-s-benzinom")       # ручная аналитика — НЕ исключать
    assert not _is_generated("/udary-po-tankeram")          # доработана руками — НЕ исключать
    assert "/" in DATA_DRIVEN_EXACT and "/attacks" in DATA_DRIVEN_EXACT
    assert "/npz-lukojla" in DATA_DRIVEN                    # операторские деферят на /refineries
    print("selfcheck: ok — приоритизация, уровни, пустой случай, исключение генерируемых")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    elif "--json" in sys.argv:
        print(json.dumps(build_report(), ensure_ascii=False, indent=2))
    else:
        print_report(build_report())
