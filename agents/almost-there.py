#!/usr/bin/env python3
"""almost-there — запросы на поз 4-10 с показами: главный рычаг роста кликов.

Зачем: перевод кластера с поз ~7 в топ-3 даёт ×3-4 клика без единой новой статьи
(доказательство в наших же данных: «Карта НПЗ» поз 3.5 → CTR 18.5% против поз ~7 → ~5%).
Этот скрипт находит такие запросы — читает живой API Вебмастера, а НЕ трекер
data/yandex-positions.json (тот засорён чужими ИТП-запросами, см. docs/agents/position-tracker-fix.md).

Использование (на VPS, где лежит ~/.hermes/.env с токеном):
    python3 agents/almost-there.py                    # отчёт за 7 дней
    python3 agents/almost-there.py --days 14 --json /tmp/wm.json
    python3 agents/almost-there.py --min-shows 300    # только жирные
    python3 agents/almost-there.py --selftest         # проверка логики без сети

ponytail: только stdlib (как metrika_summary.py) и печать в stdout — это инструмент
разбора, а не сборщик. Никакого data/*.json на выходе: файл пришлось бы поддерживать
и он бы протухал. Нужен снимок — сохрани через --json.

Задержка данных Вебмастера 1-2 дня: «сегодня» всегда пусто, это не сбой.
"""
import argparse
import json
import os
import re
import sys
import urllib.request

WUID = "2404281298"
HOST = "https%3Anpz-tactical-map.vercel.app%3A443"
API = f"https://api.webmaster.yandex.net/v4/user/{WUID}/hosts/{HOST}"


def env(path, key):
    """Достать KEY=value из .env-файла. None, если файла/ключа нет."""
    p = os.path.expanduser(path)
    if not os.path.exists(p):
        return None
    for line in open(p, encoding="utf-8", errors="ignore"):
        m = re.match(r"^%s=(.*)$" % re.escape(key), line.strip())
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return None


def token():
    return os.environ.get("YANDEX_WEBMASTER_TOKEN") or env("~/.hermes/.env", "YANDEX_WEBMASTER_TOKEN")


def fetch(days):
    """Топ-500 запросов с показами/кликами/позицией. Вебмастер отдаёт страницами по 100."""
    import datetime
    tok = token()
    if not tok:
        sys.exit("нет YANDEX_WEBMASTER_TOKEN (env или ~/.hermes/.env) — запускать на VPS")
    today = datetime.date.today()
    d2, d1 = today.isoformat(), (today - datetime.timedelta(days=days)).isoformat()
    rows = []
    for off in range(0, 500, 100):
        url = (f"{API}/search-queries/popular?order_by=TOTAL_SHOWS&limit=100&offset={off}"
               "&query_indicator=TOTAL_SHOWS&query_indicator=TOTAL_CLICKS"
               "&query_indicator=AVG_SHOW_POSITION"
               f"&date_from={d1}&date_to={d2}")
        req = urllib.request.Request(url, headers={"Authorization": "OAuth " + tok})
        qs = json.load(urllib.request.urlopen(req, timeout=60)).get("queries", [])
        for q in qs:
            i = q.get("indicators", {})
            rows.append({"q": q.get("query_text", ""),
                         "shows": int(i.get("TOTAL_SHOWS") or 0),
                         "clicks": int(i.get("TOTAL_CLICKS") or 0),
                         "pos": i.get("AVG_SHOW_POSITION")})
        if len(qs) < 100:
            break
    return rows, d1, d2


def almost_there(rows, pos_min, pos_max, min_shows):
    """Запросы в окне позиций с порогом показов, по убыванию показов.

    Позиция может быть None (Вебмастер не отдал) — такие отбрасываем, а не считаем нулём.
    """
    sel = [r for r in rows
           if isinstance(r.get("pos"), (int, float))
           and pos_min <= r["pos"] <= pos_max
           and r.get("shows", 0) >= min_shows]
    return sorted(sel, key=lambda r: -r["shows"])


def th(n):
    """12345 → «12 345». Только для чисел: общий .replace(',',' ') съедал запятые в тексте."""
    return f"{n:,}".replace(",", " ")


def fmt(r):
    pos = f"{r['pos']:.1f}" if isinstance(r.get("pos"), (int, float)) else "?"
    ctr = f"{r['clicks'] / r['shows'] * 100:4.1f}%" if r.get("shows") else "   —"
    return f"поз {pos:>5} · показы {r['shows']:>6} · клики {r['clicks']:>5} · CTR {ctr} · {r['q'][:60]}"


def selftest():
    rows = [
        {"q": "в окне, жирный", "shows": 900, "clicks": 45, "pos": 7.0},
        {"q": "в окне, тонкий", "shows": 50, "clicks": 5, "pos": 6.0},      # ниже min_shows
        {"q": "уже в топ-3", "shows": 900, "clicks": 200, "pos": 2.1},      # выше окна
        {"q": "слишком глубоко", "shows": 900, "clicks": 1, "pos": 30.0},   # ниже окна
        {"q": "позиция не отдана", "shows": 900, "clicks": 0, "pos": None},  # не считать нулём
        {"q": "в окне, средний", "shows": 400, "clicks": 20, "pos": 4.0},   # граница окна
    ]
    got = [r["q"] for r in almost_there(rows, 3.5, 10.5, 100)]
    assert got == ["в окне, жирный", "в окне, средний"], got
    assert "CTR  5.0%" in fmt(rows[0]), fmt(rows[0])
    assert "поз     ?" in fmt(rows[4]), fmt(rows[4])           # None-позиция не роняет формат
    assert almost_there([], 3.5, 10.5, 100) == []
    assert th(85768) == "85 768" and th(500) == "500"
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="almost-there запросы из API Яндекс.Вебмастера")
    ap.add_argument("--days", type=int, default=7, help="окно, дней назад (по умолчанию 7)")
    ap.add_argument("--pos-min", type=float, default=3.5, help="верх окна позиций")
    ap.add_argument("--pos-max", type=float, default=10.5, help="низ окна позиций")
    ap.add_argument("--min-shows", type=int, default=100, help="порог показов")
    ap.add_argument("--json", metavar="PATH", help="сохранить сырые запросы в файл")
    ap.add_argument("--selftest", action="store_true", help="проверить логику без сети")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    rows, d1, d2 = fetch(a.days)
    print(f"период {d1}..{d2} · запросов: {len(rows)} · показов: {th(sum(r['shows'] for r in rows))}")

    sel = almost_there(rows, a.pos_min, a.pos_max, a.min_shows)
    print(f"\n=== ALMOST-THERE (поз {a.pos_min}-{a.pos_max}, показы >= {a.min_shows}) — "
          f"{len(sel)} запросов, {th(sum(r['shows'] for r in sel))} показов ===")
    for r in sel:
        print(fmt(r))

    print("\n=== ТОП-15 по показам (любая позиция) ===")
    for r in sorted(rows, key=lambda r: -r["shows"])[:15]:
        print(fmt(r))

    if a.json:
        json.dump(rows, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\nsaved {a.json}")


if __name__ == "__main__":
    main()
