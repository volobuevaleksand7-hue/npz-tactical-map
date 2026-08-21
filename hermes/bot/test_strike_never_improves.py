#!/usr/bin/env python3
"""Повторный удар не должен улучшать завод (регресс 21.08.2026).

Прилёт по уже стоящим ТАНЕКО и Лукойл-Пермнефтеоргсинтез перевёл их
down/0% → partial/15-20%, и headline «выбито полностью» просел 40% → 32%.
"""
import json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strike_pipeline as sp


def _fuel(status, out):
    return {"refineries": [
        {"id": "taneco", "name": "ТАНЕКО", "capacity_mt_year": 17.0,
         "status": status, "est_output_pct": out, "status_since": "2026-08-10"},
        {"id": "omsk-npz", "name": "Омский", "capacity_mt_year": 22.0,
         "status": "operational", "est_output_pct": 100},
    ], "national_balance": {}, "events": [], "meta": {}}


def _run(status, out, detail):
    path = tempfile.mktemp(suffix=".json")
    json.dump(_fuel(status, out), open(path, "w"), ensure_ascii=False)
    orig_path, orig_commit = sp.FUEL_STATE_PATH, sp.git_commit_push
    sp.FUEL_STATE_PATH = path
    sp.git_commit_push = lambda *a, **k: True
    try:
        sp.update_map({"target": "ТАНЕКО", "city": "Нижнекамск",
                       "title": "удар БПЛА", "detail": detail})
        return next(r for r in json.load(open(path))["refineries"] if r["id"] == "taneco")
    finally:
        sp.FUEL_STATE_PATH, sp.git_commit_push = orig_path, orig_commit
        os.unlink(path)


def demo():
    r = _run("down", 0, "пожар на установке")
    assert r["status"] == "down", r["status"]
    assert r["est_output_pct"] == 0, r["est_output_pct"]
    assert r["status_since"] == "2026-08-10", "status_since сдвинут без смены статуса"

    r = _run("partial", 40, "повреждена установка")
    assert r["status"] == "partial" and r["est_output_pct"] <= 40, r

    r = _run("operational", 100, "завод полностью остановлен")
    assert r["status"] == "down" and r["est_output_pct"] == 0, r

    # балансовые формулы — только канонические
    nb = sp._recalculate_national_balance(_fuel("down", 0))["national_balance"]
    assert nb["capacity_offline_mt_year"] == 17.0, nb
    print("OK: удар не улучшает завод; баланс из канонической формулы")


if __name__ == "__main__":
    demo()
