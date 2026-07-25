#!/usr/bin/env python3
"""Пересчёт производных цифр national_balance из таблицы refineries[].

Зачем: 25.07.2026 на главной висело «мощностей переработки выбито полностью 64%»,
хотя по собственным данным проекта выбито 38.5% (130.4 из 338.4 млн т/год).
Агент fuel-market записал в `capacity_offline_*` значение ДРУГОЙ метрики —
недобора с учётом частично работающих (215.0 / 64%). Завышение в 1.7× на
нейтральном OSINT-проекте — это удар по доверию, а не косметика.

Корень: две суммы (down-only и взвешенная) считает LLM-агент на каждом синке —
и однажды перепутал поля. Тот же класс бага, что дрейф /refineries от fuel-state:
лечится тем же лекарством — цифру выводит код, а не модель.

Формулы — из agents/update-prompt-market.md §20-21:
  capacity_offline_mt_year = Σ capacity_mt_year, где status == "down"   (headline)
  capacity_offline_pct     = это / total × 100
  throughput_shortfall_pct = Σ capacity_mt_year·(1 − est_output_pct/100) / total × 100

Не трогает поля-оценки (gasoline/diesel_output_loss_pct, notes) — они по спеке
не выводятся из таблицы.

Запуск:
  python3 agents/recalc-national-balance.py            # починить на месте
  python3 agents/recalc-national-balance.py --check    # только отчёт, rc=1 при дрейфе
  python3 agents/recalc-national-balance.py --demo     # самопроверка
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "fuel-state.json")
FIELDS = ("refining_capacity_total_mt_year", "capacity_offline_mt_year",
          "capacity_offline_pct", "throughput_shortfall_pct")


def derive(refineries):
    """Три производные цифры из таблицы заводов. Единственный источник истины."""
    total = sum(r["capacity_mt_year"] for r in refineries)
    down = sum(r["capacity_mt_year"] for r in refineries if r["status"] == "down")
    # est_output_pct: down=0, operational=100, partial=20..70 — недобор взвешенный
    short = sum(r["capacity_mt_year"] * (1 - r.get("est_output_pct", 0) / 100.0)
                for r in refineries)
    if not total:
        raise ValueError("суммарная мощность 0 — таблица refineries[] пуста или битая")
    return {
        "refining_capacity_total_mt_year": round(total, 1),
        "capacity_offline_mt_year": round(down, 1),
        "capacity_offline_pct": round(down / total * 100),
        "throughput_shortfall_pct": round(short / total * 100),
    }


def drift(doc):
    """[(поле, было, стало)] — расхождения записанного с посчитанным."""
    want = derive(doc["refineries"])
    nb = doc["national_balance"]
    return [(k, nb.get(k), v) for k, v in want.items() if nb.get(k) != v]


def main(check_only=False):
    with open(SRC, encoding="utf8") as f:
        doc = json.load(f)
    diffs = drift(doc)
    if not diffs:
        print("national_balance: цифры сходятся с refineries[]")
        return 0
    for k, was, now in diffs:
        print("  %-34s %s -> %s" % (k, was, now))
    if check_only:
        print("national_balance: ДРЕЙФ от refineries[] (%d полей)" % len(diffs))
        return 1
    doc["national_balance"].update(dict((k, v) for k, _, v in diffs))
    # атомарная запись: обрыв не должен усечь единственный файл состояния
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(SRC), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, SRC)
    print("national_balance: пересчитано полей — %d" % len(diffs))
    return 0


def demo():
    """Самопроверка на синтетике: headline ≠ недобор, и оба считаются верно."""
    r = [
        {"capacity_mt_year": 50.0, "status": "down", "est_output_pct": 0},
        {"capacity_mt_year": 30.0, "status": "partial", "est_output_pct": 50},
        {"capacity_mt_year": 20.0, "status": "operational", "est_output_pct": 100},
    ]
    got = derive(r)
    assert got["refining_capacity_total_mt_year"] == 100.0, got
    assert got["capacity_offline_mt_year"] == 50.0, got      # только down
    assert got["capacity_offline_pct"] == 50, got
    assert got["throughput_shortfall_pct"] == 65, got        # 50 + 15 = 65
    # ключевое свойство: headline НЕ равен недобору, если есть частично работающие
    assert got["capacity_offline_pct"] != got["throughput_shortfall_pct"], \
        "перепутаны метрики — ровно этот баг и ловим"
    # дрейф детектится
    doc = {"refineries": r, "national_balance": dict(got, capacity_offline_pct=65)}
    assert drift(doc) == [("capacity_offline_pct", 65, 50)], drift(doc)
    print("demo OK")
    return 0


if __name__ == "__main__":
    sys.exit(demo() if "--demo" in sys.argv else main("--check" in sys.argv))
