#!/usr/bin/env python3
"""Повторный удар не должен улучшать завод (регресс 21.08.2026).

Прилёт по уже стоящим ТАНЕКО и Лукойл-Пермнефтеоргсинтез перевёл их
down/0% → partial/15-20%, и headline «выбито полностью» просел 40% → 32%.
"""
import json, os, re, sys, tempfile

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


def demo_matcher():
    """Сопоставление удара с заводом: покрытие всех 33 и защита от чужого города.

    26.08.2026: словарь покрывал 17 заводов из 33, остальные 16 (102.9 из 338.4
    млн т/год) не могли быть сопоставлены В ПРИНЦИПЕ — Астраханский ГПЗ остался
    «operational» после прямого удара, и headline занижал выбытие.
    """
    import json as _json
    fuel = _json.load(open(os.path.join(os.path.dirname(sp.FUEL_STATE_PATH),
                                        "fuel-state.json"), encoding="utf-8"))
    ids = {r["id"] for r in fuel["refineries"]}
    src = open(sp.__file__, encoding="utf-8").read()
    i = src.index("refinery_keywords = {")
    mapped = set(re.findall(r'"([a-z0-9-]+)":\s*\[', src[i:src.index("\n    }", i)]))
    assert not (ids - mapped), "заводы без ключей: %s" % sorted(ids - mapped)

    CASES = [
        ({"target": "Астраханский газоперерабатывающий завод (ГПЗ)",
          "city": "Красноярский район", "title": ""}, "astrakhan-gpz"),
        ({"target": "Афипский нефтеперерабатывающий завод",
          "city": "Афипский", "title": ""}, "afipsky"),
        # 🔴 город в ЗАГОЛОВКЕ не должен перетягивать удар на одноимённый завод
        ({"target": "жилая многоэтажка (обломки) / Афипский НПЗ", "city": "Краснодар",
          "title": "Обломки БПЛА в многоэтажку Краснодара, пожар на Афипском НПЗ"}, "afipsky"),
        ({"target": "логистический центр Ozon", "city": "Краснодар",
          "title": "Атака БПЛА на Краснодар"}, None),
        ({"target": "логистический центр Wildberries", "city": "Саратов",
          "title": "Атака на Саратов"}, None),
    ]
    for strike, want in CASES:
        got, _ = sp._match_refinery_id(strike)
        assert got == want, (strike["target"][:40], got, want)
    print("OK: все 33 завода покрыты; город не перетягивает удар на чужой НПЗ")


if __name__ == "__main__":
    demo()
    demo_matcher()
