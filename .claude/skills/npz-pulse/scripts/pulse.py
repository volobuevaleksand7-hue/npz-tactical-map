#!/usr/bin/env python3
"""pulse.py — сборщик фактов для скилла npz-pulse (проект «Топливный фронт РФ»).

Собирает шесть блоков (здоровье, трафик, топ-страниц, SEO-приток, новостные поводы,
монетизация) и печатает компактный человекочитаемый отчёт. НИЧЕГО не советует и не
анализирует — решения принимает потом человек/модель, читающий отчёт.

Токены Метрики/Вебмастера лежат ТОЛЬКО на hermes-vps (/root/.hermes/.env), не на этой
машине. Все обращения к API идут ОДНОЙ ssh-сессией (bash-скрипт на VPS сам источает .env,
дёргает Метрику/Вебмастер/almost-there.py и печатает единый JSON в stdout) — так дешевле
по времени и токен физически не попадает ни в один локальный лог.

Грабли проекта (см. CLAUDE.md/auto-memory):
  - диапазон дат Метрики/Вебмастера клипается при запросах по дням — всегда один вызов
    на весь диапазон с group=day / явным date_from..date_to, никогда цикл по дням;
  - VPS живёт в UTC, сайт и аудитория — Москва (+3ч); все окна и подписи — в МСК;
  - Вебмастер отдаёт данные с задержкой 1-2 дня — свежие дни там нули, это не ошибка,
    это надо подписывать явно, а не молчать.

Запуск:
    python3 pulse.py [--days N] [--json] [--selfcheck]
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO = Path(os.environ.get("NPZ_REPO", Path.home() / "Documents" / "npz-tactical-map"))
NPZ_STATUS = Path.home() / ".claude" / "skills" / "npz-status" / "scripts" / "npz-status.py"
SSH_HOST = "hermes-vps"  # 104.252.77.253 — 🔴 НЕ 193.28.186.23 (тот другой VPS)

CID = "110490245"
GOAL_VPN = "581227848"
GOAL_BOT = "585110234"
# 🔴 31.07.2026 CTA перевели с замороженного @BPLAlert_bot на канал @npz_karta_online, и
# GOAL_BOT с 02.08 показывает честные нули — а блок монетизации четыре дня выглядел так,
# будто воронка умерла. На деле канал конвертит ~0,6-0,8% против 0,06-0,14% у VPN, то есть
# примерно в 7 раз лучше, и этого в отчёте не было видно вовсе. Живая цель идёт первой,
# GOAL_BOT остаётся хвостом — пока есть страницы со старой ссылкой, история не смешивается.
GOAL_CHANNEL = "591189806"      # «Клик по Telegram-каналу»
WUID = "2404281298"
WHOST = "https%3Anpz-tactical-map.vercel.app%3A443"

MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def rus_date(d: date) -> str:
    return f"{d.day} {MONTHS[d.month]} {d.year}"


def msk_today() -> date:
    # ponytail: сервер (эта машина) может быть в любом TZ, VPS — в UTC. Правило проекта:
    # все окна и подписи считаем в МСК (UTC+3), без библиотек часовых поясов.
    return (datetime.now(timezone.utc) + timedelta(hours=3)).date()


def pct_delta(cur, base):
    """(+37%) / (-12%) / "" если не с чем сравнивать. base<=0 не делим — это не 0%, это неизвестность."""
    if not base:
        return ""
    p = round((cur - base) / base * 100)
    return f" ({'+' if p >= 0 else ''}{p}%)"


def th(n):
    return f"{n:,.0f}".replace(",", " ")


def bar(v, vmax, width=20):
    if vmax <= 0:
        return ""
    n = round(v / vmax * width)
    return "█" * n


# ---------------------------------------------------------------------------
# Блок 1 — ЗДОРОВЬЕ (переиспользуем npz-status.py --json, не дублируем его проверки)
# ---------------------------------------------------------------------------

def collect_health():
    if not NPZ_STATUS.exists():
        return {"ok": False, "error": f"нет {NPZ_STATUS}"}
    try:
        env = dict(os.environ, NPZ_REPO=str(REPO))
        p = subprocess.run(["python3", str(NPZ_STATUS), "--json"],
                            capture_output=True, text=True, timeout=30, env=env)
    except Exception as e:
        return {"ok": False, "error": f"npz-status.py не выполнился: {e}"}
    if p.returncode != 0:
        return {"ok": False, "error": f"npz-status.py rc={p.returncode}: {p.stderr.strip()[:200]}"}
    try:
        d = json.loads(p.stdout)
    except Exception as e:
        return {"ok": False, "error": f"npz-status.py дал не-JSON: {e}"}
    ag = d.get("agents", {})
    sm = d.get("summaries", {})
    seo = d.get("seo", {})
    return {
        "ok": True,
        "healthy": bool(ag.get("ok")),
        "overall": ag.get("overall"),
        "bad_layers": ag.get("bad", []),
        "publish_lag_h": ag.get("publish_lag_h"),
        "today_summary_exists": sm.get("today_summary_exists"),
        "missing_covers": len(sm.get("missing_covers", [])),
        "live_pages": seo.get("live_count"),
        "planned_pages": len(seo.get("planned", [])),
        "stale_pages": len(seo.get("stale_live", [])),
    }


# ---------------------------------------------------------------------------
# Одна ssh-сессия: собирает Метрику + Вебмастер + almost-there.py на VPS,
# печатает ЕДИНЫЙ JSON. Токен читается на VPS через `set -a; . env; set +a`
# и никогда не покидает VPS в открытом виде — наружу идут только цифры.
# ---------------------------------------------------------------------------

REMOTE_PY = r'''
import os, json, urllib.request, urllib.error, datetime

MTOKEN = os.environ.get("YANDEX_METRIKA_TOKEN")
WTOKEN = os.environ.get("YANDEX_WEBMASTER_TOKEN")

def call(url, token, timeout=40):
    req = urllib.request.Request(url, headers={"Authorization": "OAuth " + token})
    try:
        return json.load(urllib.request.urlopen(req, timeout=timeout)), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %s" % e.code
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, str(e)[:120])

result = {"metrika": {}, "webmaster": {}}

if not MTOKEN:
    result["metrika"]["error"] = "нет YANDEX_METRIKA_TOKEN в /root/.hermes/.env"
else:
    base = "https://api-metrika.yandex.net/stat/v1/data?ids=" + "__CID__"
    # диапазон ОДНИМ вызовом с group=day — не клипать циклом по дням (грабля проекта)
    daily, err = call(base + "&metrics=ym:s:visits,ym:s:users,ym:s:pageviews"
                       "&dimensions=ym:s:date&date1=__DAYS__daysAgo&date2=today&group=day", MTOKEN)
    if err:
        result["metrika"]["daily_error"] = err
    else:
        result["metrika"]["daily"] = [{"date": r["dimensions"][0]["name"], "v": r["metrics"]}
                                       for r in daily.get("data", [])]

    # разбивка по страницам за 9 дней (вчера/позавчера/медиана-7/неделю-назад) — тоже 1 вызов
    pages, err = call(base + "&metrics=ym:s:visits&dimensions=ym:s:date,ym:s:startURLPathFull"
                       "&date1=9daysAgo&date2=today&limit=3000", MTOKEN)
    if err:
        result["metrika"]["pages_error"] = err
    else:
        result["metrika"]["pages"] = [
            {"date": r["dimensions"][0]["name"], "url": r["dimensions"][1]["name"], "v": r["metrics"][0]}
            for r in pages.get("data", [])]

    goals, err = call(base + "&metrics=ym:s:goal__GOAL_CH__reaches,ym:s:goal__GOAL_VPN__reaches,"
                       "ym:s:goal__GOAL_BOT__reaches,ym:s:visits"
                       "&dimensions=ym:s:date&date1=7daysAgo&date2=today&group=day", MTOKEN)
    if err:
        result["metrika"]["goals_error"] = err
    else:
        result["metrika"]["goals"] = [{"date": r["dimensions"][0]["name"], "v": r["metrics"]}
                                       for r in goals.get("data", [])]

if not WTOKEN:
    result["webmaster"]["error"] = "нет YANDEX_WEBMASTER_TOKEN в /root/.hermes/.env"
else:
    wbase = "https://api.webmaster.yandex.net/v4/user/__WUID__/hosts/__WHOST__"
    today = datetime.date.today()

    def popular(d_from, d_to):
        url = (wbase + "/search-queries/popular?order_by=TOTAL_SHOWS&limit=200"
               "&query_indicator=TOTAL_SHOWS&query_indicator=TOTAL_CLICKS"
               "&query_indicator=AVG_SHOW_POSITION&date_from=%s&date_to=%s" % (d_from, d_to))
        d, err = call(url, WTOKEN)
        if err:
            return None, err
        out = []
        for q in d.get("queries", []):
            i = q.get("indicators", {})
            out.append({"q": q.get("query_text", ""), "shows": int(i.get("TOTAL_SHOWS") or 0),
                        "clicks": int(i.get("TOTAL_CLICKS") or 0), "pos": i.get("AVG_SHOW_POSITION")})
        return out, None

    cur_from = (today - datetime.timedelta(days=7)).isoformat()
    cur_to = today.isoformat()
    prev_from = (today - datetime.timedelta(days=14)).isoformat()
    prev_to = cur_from

    cur, err = popular(cur_from, cur_to)
    if err:
        result["webmaster"]["current_error"] = err
    else:
        result["webmaster"]["current"] = cur
        result["webmaster"]["current_window"] = [cur_from, cur_to]

    prev, err = popular(prev_from, prev_to)
    if err:
        result["webmaster"]["previous_error"] = err
    else:
        result["webmaster"]["previous"] = prev
        result["webmaster"]["previous_window"] = [prev_from, prev_to]

    # свежесть: последний НЕнулевой день показов за 10 дней (Вебмастер отстаёт 1-2 дня — не ошибка)
    hfrom = (today - datetime.timedelta(days=10)).isoformat()
    hist, err = call(wbase + "/search-queries/all/history?date_from=%s&date_to=%s"
                      "&query_indicator=TOTAL_SHOWS" % (hfrom, cur_to), WTOKEN)
    if not err:
        pts = hist.get("indicators", {}).get("TOTAL_SHOWS", [])
        nz = [p["date"][:10] for p in pts if int(p.get("value") or 0) > 0]
        if nz:
            last_day = nz[-1]
            lag = (today - datetime.date.fromisoformat(last_day)).days
            result["webmaster"]["lag_days"] = lag
            result["webmaster"]["last_fresh_day"] = last_day

print(json.dumps(result, ensure_ascii=False))
'''.replace("__CID__", CID).replace("__GOAL_CH__", GOAL_CHANNEL) \
   .replace("__GOAL_VPN__", GOAL_VPN).replace("__GOAL_BOT__", GOAL_BOT) \
   .replace("__WUID__", WUID).replace("__WHOST__", WHOST)


def fetch_remote(days, timeout=100):
    """Одна ssh-сессия делает ДВЕ вещи ПАРАЛЛЕЛЬНО (иначе не укладывается в ~90с):
    almost-there.py (собственный цикл постраничных запросов Вебмастера, ~40с) — в фоне,
    и наш heredoc (Метрика + Вебмастер popular/history) — на переднем плане. `wait` в конце
    соединяет их, финальный python склеивает два файла в один JSON и печатает в stdout."""
    remote_py = REMOTE_PY.replace("__DAYS__", str(days))
    bash = (
        "set -a; . /root/.hermes/.env 2>/dev/null; set +a\n"
        "cd /root/npz-tactical-map 2>/dev/null\n"
        f"(timeout 70 python3 agents/almost-there.py --days {int(days)} "
        ">/tmp/pulse_almost.txt 2>&1) &\n"
        "ALMOST_PID=$!\n"
        "python3 - <<'PYEOF' > /tmp/pulse_json.txt\n" + remote_py + "\nPYEOF\n"
        "wait $ALMOST_PID\n"
        "python3 -c \"\n"
        "import json\n"
        "r = json.load(open('/tmp/pulse_json.txt'))\n"
        "try:\n"
        "    r['almost_there_raw'] = open('/tmp/pulse_almost.txt', encoding='utf-8', errors='replace').read()\n"
        "except Exception as e:\n"
        "    r['almost_there_raw'] = ''\n"
        "    r['almost_there_error'] = str(e)[:120]\n"
        "print(json.dumps(r, ensure_ascii=False))\n"
        "\"\n"
        "rm -f /tmp/pulse_almost.txt /tmp/pulse_json.txt\n"
    )
    try:
        p = subprocess.run(["ssh", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
                             SSH_HOST, "bash -s"],
                            input=bash, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return None, f"ssh не выполнился: {type(e).__name__}"
    if p.returncode != 0:
        # 🔴 stderr печатаем усечённым и никогда не как есть в JSON-режиме — на всякий случай
        # ловим подстроку токена (y0_... формат Яндекс OAuth) и режем её.
        err = re.sub(r"y0_[A-Za-z0-9_-]+", "***", p.stderr.strip())[:200]
        return None, f"ssh rc={p.returncode}: {err}"
    try:
        # 🔴 split("\n"), НЕ splitlines(): в заголовках страниц из Метрики приезжает
        # U+0085 (NEL) — Python считает его переносом строки, splitlines() рвёт по нему
        # единственную JSON-строку и [-1] отдаёт обрывок. 22.08.2026: японский заголовок
        # положил 4 блока отчёта из 6 под видом «vps вернул не-JSON».
        return json.loads(p.stdout.strip().split("\n")[-1]), None
    except Exception as e:
        return None, f"vps вернул не-JSON: {e}"


# ---------------------------------------------------------------------------
# Блок 2 — ТРАФИК
# ---------------------------------------------------------------------------

def build_traffic(metrika):
    if not metrika or metrika.get("daily_error") or "daily" not in metrika:
        return {"ok": False, "error": metrika.get("daily_error", "нет данных") if metrika else "нет данных"}
    rows = sorted(metrika["daily"], key=lambda r: r["date"])
    today_s = msk_today().isoformat()
    # вчера / медиана предыдущих 7 (без вчера); сегодняшний день неполный — не участвует
    by_date = {r["date"]: r["v"][0] for r in rows}
    yesterday = (msk_today() - timedelta(days=1)).isoformat()
    yv = by_date.get(yesterday)
    prev_window = [(msk_today() - timedelta(days=n)).isoformat() for n in range(2, 9)]
    prev_vals = [by_date[d] for d in prev_window if d in by_date]
    med7 = statistics.median(prev_vals) if prev_vals else None
    return {
        "ok": True,
        "rows": rows,
        "today_incomplete": today_s in by_date,
        "yesterday": yesterday,
        "yesterday_visits": yv,
        "median_prev7": med7,
        "yesterday_vs_median_pct": pct_delta(yv, med7) if (yv is not None and med7) else "",
    }


# ---------------------------------------------------------------------------
# Блок 3 — ЧТО ЛУЧШЕ ВСЕГО ИДЁТ (топ-15 страниц вчера + тренд + новички)
# ---------------------------------------------------------------------------

def build_top_pages(metrika, top_n=15):
    if not metrika or metrika.get("pages_error") or "pages" not in metrika:
        return {"ok": False, "error": metrika.get("pages_error", "нет данных") if metrika else "нет данных"}
    # url -> date -> visits
    by_url = {}
    for r in metrika["pages"]:
        by_url.setdefault(r["url"], {})[r["date"]] = r["v"]

    yesterday = (msk_today() - timedelta(days=1)).isoformat()
    day2 = (msk_today() - timedelta(days=2)).isoformat()
    week_ago = (msk_today() - timedelta(days=8)).isoformat()  # тот же день недели, что вчера
    prev_window = [(msk_today() - timedelta(days=n)).isoformat() for n in range(2, 9)]

    # топ-15 «неделю назад» (на дату week_ago) — база для пометки новичков
    week_ago_top = sorted(
        ((u, d.get(week_ago, 0)) for u, d in by_url.items() if d.get(week_ago, 0) > 0),
        key=lambda x: -x[1])[:top_n]
    week_ago_top_urls = {u for u, _ in week_ago_top}
    week_ago_has_data = any(week_ago in d for d in by_url.values())

    yesterday_ranked = sorted(
        ((u, d.get(yesterday, 0)) for u, d in by_url.items() if d.get(yesterday, 0) > 0),
        key=lambda x: -x[1])[:top_n]

    rows = []
    for url, yv in yesterday_ranked:
        d = by_url[url]
        d2v = d.get(day2, 0)
        # 🔴 Метрика НЕ возвращает строки за дни с нулём — пропущенный день это 0, а не «нет
        # данных». Если их отбрасывать, медиана считается только по дням с трафиком и завышает
        # базу: страница, взлетевшая с нуля 3 дня назад, показывала «медиана7 = 1643» вместо 0
        # и выглядела падающей на ровном месте.
        vals7 = [d.get(dd, 0) for dd in prev_window]
        med7 = statistics.median(vals7) if vals7 else None
        trend = "?"
        if med7 is not None and med7 > 0:
            trend = "↑" if yv > med7 * 1.15 else ("↓" if yv < med7 * 0.85 else "→")
        elif yv > 0:
            trend = "↑"  # взлёт с нуля: неделю назад страницы в трафике не было вовсе
        newcomer = week_ago_has_data and (url not in week_ago_top_urls)
        rows.append({
            "url": url, "visits_yesterday": yv, "visits_day2": d2v, "median_prev7": med7,
            "delta_vs_median_pct": pct_delta(yv, med7) if med7 else "",
            "trend": trend, "newcomer": newcomer,
        })
    return {"ok": True, "yesterday": yesterday, "week_ago_reference": week_ago,
            "week_ago_has_data": week_ago_has_data, "rows": rows}


# ---------------------------------------------------------------------------
# Блок 4 — SEO-ПРИТОК (новые/растущие запросы Вебмастера + almost-there.py)
# ---------------------------------------------------------------------------

def diff_queries(current, previous, min_shows=30, growth_top=15):
    prev_by_q = {r["q"]: r for r in previous}
    new_q = [r for r in current if r["q"] not in prev_by_q and r["shows"] >= min_shows]
    new_q.sort(key=lambda r: -r["shows"])

    growth = []
    for r in current:
        p = prev_by_q.get(r["q"])
        if not p or p["shows"] <= 0 or r["shows"] < min_shows:
            continue
        ratio = r["shows"] / p["shows"]
        if ratio > 1.0:
            growth.append({**r, "prev_shows": p["shows"], "ratio": ratio})
    growth.sort(key=lambda r: -r["ratio"])
    return new_q, growth[:growth_top]


def build_seo_inflow(webmaster, remote):
    out = {"ok": False}
    cur_err = webmaster.get("current_error") if webmaster else "нет данных"
    prev_err = webmaster.get("previous_error") if webmaster else "нет данных"
    if not webmaster or "current" not in webmaster or "previous" not in webmaster:
        out["error"] = cur_err or prev_err or "нет данных"
    else:
        new_q, growth = diff_queries(webmaster["current"], webmaster["previous"])
        out.update({
            "ok": True,
            "current_window": webmaster.get("current_window"),
            "previous_window": webmaster.get("previous_window"),
            "new_queries": new_q[:30],
            "growth_queries": growth,
            "lag_days": webmaster.get("lag_days"),
            "last_fresh_day": webmaster.get("last_fresh_day"),
        })
    out["almost_there_raw"] = (remote or {}).get("almost_there_raw", "")
    return out


# ---------------------------------------------------------------------------
# Блок 5 — НОВОСТНЫЕ ПОВОДЫ (локальные data/strikes.json + data/seo-topics.jsonl)
# ---------------------------------------------------------------------------

def load_json(path):
    try:
        return json.load(open(path, encoding="utf-8")), None
    except Exception as e:
        return None, str(e)[:150]


def load_jsonl(path):
    try:
        rows = []
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows, None
    except Exception as e:
        return None, str(e)[:150]


def strike_key(s):
    return (s.get("region") or s.get("city") or "?", s.get("type") or "?")


def find_topic_for_strike(strike, topics):
    """Простая эвристика: город/регион удара упоминается в ключах/примечании/URL живой темы.
    ponytail: substring-матч, не NLP — сырьё для человека, не окончательный вердикт."""
    needles = [n for n in (strike.get("city"), strike.get("region")) if n]
    needles_low = [n.lower() for n in needles]
    hits = []
    for t in topics:
        hay = " ".join(str(t.get(k, "")) for k in
                        ("url", "primary_kw", "note")) + " " + " ".join(t.get("keywords") or [])
        hay = hay.lower()
        if any(n in hay for n in needles_low):
            hits.append(t.get("url"))
    return hits


def build_news_hooks(days=3):
    strikes, err = load_json(REPO / "data" / "strikes.json")
    if err:
        return {"ok": False, "error": f"data/strikes.json: {err}"}
    topics, terr = load_jsonl(REPO / "data" / "seo-topics.jsonl")
    if terr:
        topics = []  # без реестра всё уйдёт в «страницы нет» — честно помечаем ниже

    since = msk_today() - timedelta(days=days)
    items = strikes.get("strikes", []) if isinstance(strikes, dict) else strikes
    recent = []
    for s in items:
        try:
            d = date.fromisoformat(s.get("date", ""))
        except Exception:
            continue
        if d >= since:
            recent.append(s)

    groups = {}
    for s in recent:
        groups.setdefault(strike_key(s), []).append(s)

    has_page, no_page = [], []
    for (region, typ), evs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        urls = find_topic_for_strike(evs[0], topics) if topics else []
        entry = {"region": region, "type": typ, "count": len(evs),
                  "titles": [e.get("title", "")[:80] for e in evs[:3]]}
        if urls:
            entry["existing_pages"] = urls
            has_page.append(entry)
        else:
            no_page.append(entry)

    return {"ok": True, "window_days": days, "since": since.isoformat(), "total_events": len(recent),
            "topics_registry_error": terr, "has_page": has_page, "no_page": no_page}


# ---------------------------------------------------------------------------
# Блок 6 — МОНЕТИЗАЦИЯ
# ---------------------------------------------------------------------------

def build_monetization(metrika):
    if not metrika or metrika.get("goals_error") or "goals" not in metrika:
        return {"ok": False, "error": metrika.get("goals_error", "нет данных") if metrika else "нет данных"}
    rows = sorted(metrika["goals"], key=lambda r: r["date"])
    out = []
    for r in rows:
        ch, vpn, bot, visits = r["v"]
        out.append({
            "date": r["date"], "tg_channel": int(ch), "vpn_click": int(vpn),
            "bot_click_frozen": int(bot), "visits": int(visits),
            "ch_conv_pct": round(ch / visits * 100, 2) if visits else None,
            "vpn_conv_pct": round(vpn / visits * 100, 2) if visits else None,
            "bot_conv_pct": round(bot / visits * 100, 2) if visits else None,
        })
    return {"ok": True, "rows": out}


# ---------------------------------------------------------------------------
# Печать отчёта
# ---------------------------------------------------------------------------

def line(): print("-" * 70)


def print_report(rep):
    now = msk_today()
    print(f"=== NPZ PULSE — {rus_date(now)} (МСК) ===")
    line()

    print("1. ЗДОРОВЬЕ")
    h = rep["health"]
    if not h.get("ok"):
        print(f"   данные недоступны: {h.get('error')}")
    else:
        status = "OK" if h["healthy"] else f"ПРОБЛЕМЫ ({h['overall']})"
        print(f"   флот: {status}"
              + (f", проблемные слои: {h['bad_layers']}" if h["bad_layers"] else ""))
        print(f"   сводка сегодня: {'есть' if h['today_summary_exists'] else 'НЕТ'}"
              f" · обложек не хватает: {h['missing_covers']}")
        print(f"   страниц live: {h['live_pages']} · запланировано: {h['planned_pages']}"
              f" · протухших: {h['stale_pages']}")
    line()

    print("2. ТРАФИК (14 дней)")
    t = rep["traffic"]
    if not t.get("ok"):
        print(f"   данные недоступны: {t.get('error')}")
    else:
        vmax = max((r["v"][0] for r in t["rows"]), default=0)
        for r in t["rows"]:
            tag = " (неполный день)" if r["date"] == now.isoformat() else ""
            print(f"   {r['date']} {r['v'][0]:>6.0f} {bar(r['v'][0], vmax)}{tag}")
        if t["yesterday_visits"] is not None:
            print(f"   вчера ({t['yesterday']}): {th(t['yesterday_visits'])} визитов"
                  f"{t['yesterday_vs_median_pct']} к медиане предыдущих 7 дней"
                  + (f" ({th(t['median_prev7'])})" if t["median_prev7"] else ""))
    line()

    print("3. ЧТО ЛУЧШЕ ВСЕГО ИДЁТ (топ-15 страниц вчера)")
    tp = rep["top_pages"]
    if not tp.get("ok"):
        print(f"   данные недоступны: {tp.get('error')}")
    else:
        if not tp["week_ago_has_data"]:
            print(f"   ⚠ нет данных на {tp['week_ago_reference']} — новичков не помечаем")
        for r in tp["rows"]:
            nc = " [НОВИЧОК]" if r["newcomer"] else ""
            print(f"   {r['trend']} {r['url']:<45} вчера {r['visits_yesterday']:>5.0f}"
                  f" · позавчера {r['visits_day2']:>5.0f}"
                  f" · медиана7 {r['median_prev7'] or 0:>5.0f}{r['delta_vs_median_pct']}{nc}")
    line()

    print("4. SEO-ПРИТОК")
    si = rep["seo_inflow"]
    if not si.get("ok"):
        print(f"   Вебмастер: данные недоступны: {si.get('error')}")
    else:
        if si.get("lag_days"):
            print(f"   ⚠ данные Вебмастера отстают на {si['lag_days']} дн."
                  f" (последний свежий день: {si.get('last_fresh_day')})")
        cw, pw = si["current_window"], si["previous_window"]
        print(f"   окна сравнения: {cw[0]}..{cw[1]} против {pw[0]}..{pw[1]} (порог 30 показов)")
        print(f"   НОВЫЕ запросы ({len(si['new_queries'])}):")
        for q in si["new_queries"][:15]:
            print(f"     показы {q['shows']:>5} · клики {q['clicks']:>4} · {q['q'][:55]}")
        print(f"   РАСТУЩИЕ запросы (топ по кратности роста):")
        for q in si["growth_queries"][:15]:
            print(f"     ×{q['ratio']:.1f} ({q['prev_shows']}→{q['shows']}) · {q['q'][:55]}")
    if rep["seo_inflow"].get("almost_there_raw"):
        print("   --- almost-there.py (позиции 4-10) ---")
        for ln in rep["seo_inflow"]["almost_there_raw"].splitlines():
            print(f"   {ln}")
    elif si.get("ok") is not False:
        print("   almost-there.py: нет вывода (недоступен на VPS?)")
    line()

    print("5. НОВОСТНЫЕ ПОВОДЫ (последние 3 дня)")
    nh = rep["news_hooks"]
    if not nh.get("ok"):
        print(f"   данные недоступны: {nh.get('error')}")
    else:
        print(f"   событий: {nh['total_events']} с {nh['since']}"
              + (f" · ⚠ реестр тем не прочитан: {nh['topics_registry_error']}"
                 if nh.get("topics_registry_error") else ""))
        print("   ЕСТЬ страница — обновить:")
        for e in nh["has_page"]:
            print(f"     {e['region']} / {e['type']} × {e['count']} → {e['existing_pages']}")
        print("   СТРАНИЦЫ НЕТ — потенциальный повод:")
        for e in nh["no_page"]:
            print(f"     {e['region']} / {e['type']} × {e['count']} — {e['titles']}")
    line()

    print("6. МОНЕТИЗАЦИЯ (7 дней)")
    mo = rep["monetization"]
    if not mo.get("ok"):
        print(f"   данные недоступны: {mo.get('error')}")
    else:
        for r in mo["rows"]:
            # bot_click_frozen печатаем только пока он ещё что-то ловит: с 02.08 там честные
            # нули (CTA переехали на канал), и три колонки подряд с нулём читались как авария.
            tail = (f" · bot_click_frozen {r['bot_click_frozen']:>3} ({r['bot_conv_pct']}%)"
                    if r["bot_click_frozen"] else "")
            print(f"   {r['date']} канал {r['tg_channel']:>3} ({r['ch_conv_pct']}%)"
                  f" · vpn_click {r['vpn_click']:>3} ({r['vpn_conv_pct']}%)"
                  f"{tail} · визитов {r['visits']}")
    line()


# ---------------------------------------------------------------------------
# selfcheck — логика без сети, на фикстурах
# ---------------------------------------------------------------------------

def selfcheck():
    assert rus_date(date(2026, 7, 27)) == "27 июля 2026"
    assert pct_delta(150, 100) == " (+50%)"
    assert pct_delta(50, 100) == " (-50%)"
    assert pct_delta(10, 0) == ""  # база 0 — не делим, не выдумываем -100%/inf
    assert th(12345) == "12 345"
    assert bar(0, 0) == ""

    # diff_queries: новое, рост, отброс по порогу
    cur = [{"q": "новая тема", "shows": 100, "clicks": 5, "pos": 8.0},
           {"q": "новая мелкая", "shows": 10, "clicks": 1, "pos": 8.0},
           {"q": "выросла", "shows": 300, "clicks": 20, "pos": 4.0},
           {"q": "стабильна", "shows": 200, "clicks": 20, "pos": 5.0}]
    prev = [{"q": "выросла", "shows": 100, "clicks": 5, "pos": 6.0},
            {"q": "стабильна", "shows": 190, "clicks": 19, "pos": 5.0}]
    new_q, growth = diff_queries(cur, prev, min_shows=30)
    assert [q["q"] for q in new_q] == ["новая тема"], new_q  # мелкая отсеяна порогом
    assert growth[0]["q"] == "выросла" and abs(growth[0]["ratio"] - 3.0) < 0.01, growth

    # find_topic_for_strike: матч по городу в keywords
    topics = [{"url": "/crimea", "primary_kw": "нет бензина в крыму",
               "keywords": ["бензин в крыму"], "note": ""}]
    hit = find_topic_for_strike({"city": "Симферополь", "region": "Крым"}, topics)
    assert hit == ["/crimea"], hit
    miss = find_topic_for_strike({"city": "Владивосток", "region": "Приморье"}, topics)
    assert miss == [], miss

    # build_traffic / build_top_pages на синтетическом remote
    fake_dates = [(msk_today() - timedelta(days=n)).isoformat() for n in range(0, 9)]
    metrika = {
        "daily": [{"date": d, "v": [100 + i, 80, 200]} for i, d in enumerate(reversed(fake_dates))],
        "pages": ([{"date": fake_dates[1], "url": "/a", "v": 50},
                    {"date": fake_dates[2], "url": "/a", "v": 40}]
                  + [{"date": fake_dates[n], "url": "/a", "v": 30} for n in range(2, 9)]
                  + [{"date": fake_dates[1], "url": "/b-new", "v": 20}]),
    }
    tr = build_traffic(metrika)
    assert tr["ok"] and tr["yesterday_visits"] is not None
    tp = build_top_pages(metrika)
    assert tp["ok"]
    urls = {r["url"]: r for r in tp["rows"]}
    assert urls["/a"]["visits_yesterday"] == 50
    # /a не было на week_ago (fake_dates[8]) в этой фикстуре, кроме случая v=30 повторяется -
    # /a присутствует на week_ago тоже (диапазон n=2..8 включает 8) => не новичок
    assert urls["/a"]["newcomer"] is False
    assert urls["/b-new"]["newcomer"] is True

    # монетизация: порядок метрик в ответе — канал, vpn, бот, визиты. Если его сдвинуть,
    # конверсии молча уедут не в те колонки (ровно так блок и врал: мёртвая цель на виду,
    # живая не запрашивалась вовсе).
    mo = build_monetization({"goals": [{"date": "2026-08-04", "v": [18, 2, 0, 2600]}]})
    assert mo["ok"], mo
    row = mo["rows"][0]
    assert (row["tg_channel"], row["vpn_click"], row["bot_click_frozen"]) == (18, 2, 0), row
    assert row["ch_conv_pct"] == 0.69 and row["vpn_conv_pct"] == 0.08, row

    print("selfcheck OK")


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="npz-pulse — сбор фактов, без анализа")
    ap.add_argument("--days", type=int, default=14, help="окно трафика, дней (по умолчанию 14)")
    ap.add_argument("--json", action="store_true", help="машинный вывод целиком")
    ap.add_argument("--selfcheck", action="store_true", help="прогон логики на фикстурах, без сети")
    a = ap.parse_args()

    if a.selfcheck:
        return selfcheck()

    rep = {"generated_at_msk": rus_date(msk_today()), "days": a.days}
    rep["health"] = collect_health()

    remote, err = fetch_remote(a.days)
    if err:
        unavailable = {"ok": False, "error": err}
        rep["traffic"] = unavailable
        rep["top_pages"] = unavailable
        rep["seo_inflow"] = {**unavailable, "almost_there_raw": ""}
        rep["monetization"] = unavailable
    else:
        metrika = remote.get("metrika", {})
        webmaster = remote.get("webmaster", {})
        if metrika.get("error"):
            unav = {"ok": False, "error": metrika["error"]}
            rep["traffic"] = unav
            rep["top_pages"] = unav
            rep["monetization"] = unav
        else:
            rep["traffic"] = build_traffic(metrika)
            rep["top_pages"] = build_top_pages(metrika)
            rep["monetization"] = build_monetization(metrika)
        rep["seo_inflow"] = build_seo_inflow(webmaster, remote)

    rep["news_hooks"] = build_news_hooks()

    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print_report(rep)


if __name__ == "__main__":
    main()
