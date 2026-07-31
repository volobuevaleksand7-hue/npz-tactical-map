#!/usr/bin/env python3
"""position-tracker — снимок позиций НАШИХ (NPZ) запросов из data/position-queries.json.

Зачем: фикс 15.07 (docs/agents/position-tracker-fix.md) убил старый скрейпер
(капча, чужие ИТП-запросы просочились через VPS-cron) и завёл проверку через
agents/almost-there.py — но тот меряет топ-500 запросов сайта ПО ПОКАЗАМ, а не
наш куратор-список data/position-queries.json, и ничего не сохраняет. Дыра:
формально «трекер починен», а сверить позицию конкретно НАШИХ 40 запросов и
получить снимок — было нечем.

Это тонкая обвязка над almost-there.py: тот же Вебмастер API (fetch/token,
без капчи, без скрейпинга), только матчинг по data/position-queries.json и
запись снимка в файл.

Использование (на VPS, где ~/.hermes/.env даёт YANDEX_WEBMASTER_TOKEN):
    python3 agents/position-tracker.py                  # отчёт + data/position-tracker.json
    python3 agents/position-tracker.py --days 14
    python3 agents/position-tracker.py --out /tmp/x.json
    python3 agents/position-tracker.py --selftest        # проверка матчинга без сети

ponytail: импортирует fetch()/token() из almost-there.py вместо нового HTTP-
клиента (тот же файл — hyphen в имени, отсюда importlib вместо `import`).
Вебмастер отдаёт топ-500 по показам за окно — низкочастотные региональные
запросы из position-queries.json туда могут не попасть; такие помечаются
found=false, это честный предел API, а не баг матчинга.
"""
import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
QUERIES_FILE = os.path.join(HERE, "..", "data", "position-queries.json")
DEFAULT_OUT = os.path.join(HERE, "..", "data", "position-tracker.json")


def _load_almost_there():
    spec = importlib.util.spec_from_file_location("almost_there", os.path.join(HERE, "almost-there.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def load_queries(path=QUERIES_FILE):
    data = json.load(open(path, encoding="utf-8"))
    return data["queries"]


def match(queries, rows):
    """Сопоставить куратор-список с живыми строками Вебмастера по точному тексту запроса.

    Матч регистронезависимый (Вебмастер обычно отдаёт нижний регистр, но не гарантирует).
    """
    by_text = {r["q"].strip().lower(): r for r in rows}
    out = []
    for q in queries:
        r = by_text.get(q["query"].strip().lower())
        out.append({
            "query": q["query"],
            "target_url": q.get("target_url"),
            "cluster": q.get("cluster"),
            "freq": q.get("freq"),
            "found": r is not None,
            "pos": r.get("pos") if r else None,
            "shows": r.get("shows") if r else None,
            "clicks": r.get("clicks") if r else None,
        })
    return out


def fmt(m):
    pos = f"{m['pos']:.1f}" if isinstance(m.get("pos"), (int, float)) else "?"
    tag = "  " if m["found"] else "НЕ В ТОП-500"
    return f"поз {pos:>5} · {tag:>13} · {m['query'][:45]:45} → {m['target_url']}"


def selftest():
    queries = [
        {"query": "атака на нпз", "target_url": "/attacks", "cluster": "attacks", "freq": 65028},
        {"query": "низкочастотный запрос вне топ-500", "target_url": "/x", "cluster": "x", "freq": None},
    ]
    rows = [
        {"q": "атака на нпз", "shows": 900, "clicks": 45, "pos": 7.2},
        {"q": "обслуживание итп", "shows": 500, "clicks": 10, "pos": 3.0},  # чужой ИТП-запрос — не должен попасть
    ]
    out = match(queries, rows)
    assert out[0]["found"] is True and out[0]["pos"] == 7.2, out[0]
    assert out[1]["found"] is False and out[1]["pos"] is None, out[1]
    assert all("итп" not in o["query"].lower() for o in out), "чужой ИТП-запрос протёк в вывод"
    assert "НЕ В ТОП-500" in fmt(out[1])
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description="Снимок позиций NPZ-запросов (data/position-queries.json) через Вебмастер API")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--queries", default=QUERIES_FILE, help="путь к куратор-списку запросов")
    ap.add_argument("--out", default=DEFAULT_OUT, help="куда сохранить снимок")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    at = _load_almost_there()
    queries = load_queries(a.queries)
    rows, d1, d2 = at.fetch(a.days)
    results = match(queries, rows)

    found = [m for m in results if m["found"]]
    print(f"период {d1}..{d2} · запросов в списке: {len(results)} · с данными: {len(found)}")
    for m in sorted(results, key=lambda m: (m["pos"] is None, m["pos"] or 999)):
        print(fmt(m))

    snapshot = {
        "generated_at": d2 + "T00:00:00Z",
        "window": {"from": d1, "to": d2},
        "source": "yandex-webmaster-api-v4",
        "queries": results,
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(snapshot, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nsaved {a.out}")


if __name__ == "__main__":
    main()
