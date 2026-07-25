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

Заодно (25.07) — вторая дыра того же класса: `data/capacity-timeline.json` (график
«динамика выбытия мощностей» на главной, app.js:593 берёт последние 12 точек) никто
не дописывал с 12.07 — ни один прогонный промпт не владеет файлом
(update-prompt-economy.md прямо отсылает к несуществующей «forecast-рутине»).
Дописывание точки живёт здесь же, а не в отдельном скрипте: источник цифр тот же
derive() из refineries[] — держать два места с одной формулой хуже, чем один файл
с двумя обязанностями. Точка пишется, только если capacity_offline_pct изменился
относительно последней сохранённой точки (иначе за 12 ежедневных прогонов график
схлопнется в две точки и потеряет дугу роста с мая) — это же делает вызов
идемпотентным. В --check таймлайн не трогается: check только отчитывается.

Запуск:
  python3 agents/recalc-national-balance.py            # починить national_balance + дописать точку таймлайна
  python3 agents/recalc-national-balance.py --check    # только отчёт, rc=1 при дрейфе (таймлайн не трогает)
  python3 agents/recalc-national-balance.py --demo     # самопроверка
"""
import datetime
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "fuel-state.json")
TIMELINE = os.path.join(ROOT, "data", "capacity-timeline.json")
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


def update_timeline(doc):
    """Дописывает/обновляет точку capacity-timeline.json из derive(refineries[]).

    Возвращает None (файла нет — нечего делать) или строку-отчёт.
    Правило: точка пишется только если capacity_offline_pct отличается от
    последней СОХРАНЁННОЙ точки — иначе ежедневный прогон за 12 дней схлопнет
    12-точечное окно панели в почти одну дугу. Если последняя точка уже за
    сегодня — она перезаписывается (не плодим вторую точку в один день).
    """
    if not os.path.exists(TIMELINE):
        return None
    with open(TIMELINE, encoding="utf8") as f:
        tl = json.load(f)
    points = tl.get("timeline", [])
    derived = derive(doc["refineries"])
    nb = doc["national_balance"]
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    point = {
        "date": today,
        "capacity_offline_pct": derived["capacity_offline_pct"],
        "capacity_offline_mt_year": derived["capacity_offline_mt_year"],
        "gasoline_loss_pct": nb.get("gasoline_output_loss_pct"),
        "diesel_loss_pct": nb.get("diesel_output_loss_pct"),
    }
    last = points[-1] if points else None
    if last and last.get("capacity_offline_pct") == point["capacity_offline_pct"]:
        return None  # процент не изменился — файл не трогаем (идемпотентность)
    if last and last.get("date") == today:
        points[-1] = point  # тот же день, но процент уже изменился — обновляем, не дублируем
    else:
        points.append(point)
    tl["timeline"] = points
    tl.setdefault("meta", {})["generated_at"] = today
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(TIMELINE), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf8") as f:
        json.dump(tl, f, ensure_ascii=False, indent=1)
    os.replace(tmp, TIMELINE)
    return "capacity-timeline.json: точка %s дописана (%s%%)" % (today, point["capacity_offline_pct"])


def main(check_only=False):
    with open(SRC, encoding="utf8") as f:
        doc = json.load(f)
    diffs = drift(doc)
    if not diffs:
        print("national_balance: цифры сходятся с refineries[]")
    else:
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

    if check_only:
        return 0
    tl_report = update_timeline(doc)
    if tl_report:
        print(tl_report)
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

    # ---- capacity-timeline.json: append-only-if-changed логика ----
    global TIMELINE
    real_timeline = TIMELINE
    fd, tmp_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        TIMELINE = tmp_path
        # derive() читает refineries[], не national_balance — варьируем таблицу,
        # чтобы получить разные capacity_offline_pct (50 -> 55)
        r50 = r  # down=50 из 100 -> 50%
        r55 = [dict(r[0], capacity_mt_year=55.0), dict(r[1], capacity_mt_year=25.0), r[2]]  # down=55 из 100 -> 55%
        doc50 = {"refineries": r50, "national_balance": got}
        doc55 = {"refineries": r55, "national_balance": got}
        with open(TIMELINE, "w", encoding="utf8") as f:
            json.dump({"meta": {}, "timeline": [{"date": "2020-01-01", "capacity_offline_pct": 10,
                                                   "capacity_offline_mt_year": 10, "gasoline_loss_pct": None,
                                                   "diesel_loss_pct": None}]}, f)
        # (a) процент изменился (10 -> 50) -> новая точка добавляется
        r1 = update_timeline(doc50)
        assert r1 is not None, "точка с новым процентом должна добавиться"
        tl = json.load(open(TIMELINE, encoding="utf8"))
        assert len(tl["timeline"]) == 2, tl["timeline"]
        assert tl["timeline"][-1]["capacity_offline_pct"] == 50, tl["timeline"]
        # (b) процент не изменился -> файл не трогаем (идемпотентность)
        before = open(TIMELINE, encoding="utf8").read()
        r2 = update_timeline(doc50)
        assert r2 is None, "неизменный процент не должен трогать файл"
        after = open(TIMELINE, encoding="utf8").read()
        assert before == after, "файл изменился при неизменном проценте"
        # (c) повторный вызов с ИЗМЕНИВШИМся процентом в тот же день не плодит дубли,
        # а обновляет последнюю точку
        r3 = update_timeline(doc55)
        assert r3 is not None
        tl = json.load(open(TIMELINE, encoding="utf8"))
        assert len(tl["timeline"]) == 2, "должна обновиться последняя точка, а не добавиться третья"
        assert tl["timeline"][-1]["capacity_offline_pct"] == 55, tl["timeline"]
    finally:
        TIMELINE = real_timeline
        os.path.exists(tmp_path) and os.remove(tmp_path)

    print("demo OK")
    return 0


if __name__ == "__main__":
    sys.exit(demo() if "--demo" in sys.argv else main("--check" in sys.argv))
