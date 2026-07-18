#!/usr/bin/env python3
"""Assert-тесты для agents/wave-detect.py — чистая функция evaluate().

Запуск: python3 agents/test_wave_detect.py
Печатает "OK" если все тесты прошли.
"""
import importlib.util
import os
import sys

_spec = importlib.util.spec_from_file_location(
    "wave_detect",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "wave-detect.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
evaluate = _mod.evaluate
STALE_SEC = _mod.STALE_SEC
_to_iso = _mod._to_iso

NOW = 1783883000


def _make_city(name, region, bpla=True, bplaDim=False, ts=None):
    return {
        "name": name,
        "region": region,
        "bpla": bpla,
        "bplaDim": bplaDim,
        "last_event_ts": ts if ts is not None else NOW - 60,
        "lat": 0.0,
        "lon": 0.0,
    }


def _radar(cities, fetched_ago_sec=60):
    return {
        "fetched_at": _to_iso(NOW - fetched_ago_sec),
        "cities": cities,
    }


def _wave_state(active=False, cities=0, regions=0, region_list=None,
                started_at=None, peak_cities=0, peak_regions=0,
                current_event_id=None, last_event=None):
    s = {
        "active": active,
        "cities": cities,
        "regions": regions,
        "region_list": region_list or [],
        "started_at": started_at,
        "peak_cities": peak_cities,
        "peak_regions": peak_regions,
        "current_event_id": current_event_id,
        "updated_at": None,
    }
    if last_event:
        s["last_event"] = last_event
    return s


def test_rise_publish():
    """49 bright/8 regions, fresh snapshot, cooldown expired → publish=True, action=start."""
    cities = []
    for i in range(49):
        cities.append(_make_city("Город%d" % i, "Область%d" % (i % 8)))
    radar = _radar(cities, fetched_ago_sec=60)
    prev = _wave_state(last_event={"date": "2026-01-01"})

    r = evaluate(radar, prev, NOW)
    assert r["publish"] is True, "expected publish=True, got %s" % r["publish"]
    assert r["action"] == "start", "expected action=start, got %s" % r["action"]
    assert r["new_state"]["active"] is True
    assert r["new_state"]["cities"] == 49
    assert r["new_state"]["regions"] == 8
    assert r["event"] is not None
    assert r["event"]["peak_cities"] == 49
    assert r["event"]["peak_regions"] == 8
    print("  PASS: test_rise_publish")


def test_update_no_publish():
    """Same input 10 min later, active wave (cooldown active) → publish=False, action=update."""
    cities = []
    for i in range(49):
        cities.append(_make_city("Город%d" % i, "Область%d" % (i % 8)))
    radar = _radar(cities, fetched_ago_sec=60)
    prev = _wave_state(
        active=True,
        cities=49,
        regions=8,
        region_list=["Область%d" % i for i in range(8)],
        started_at=_to_iso(NOW - 600),
        peak_cities=49,
        peak_regions=8,
        current_event_id="2026-07-12-1900",
    )

    r = evaluate(radar, prev, NOW)
    assert r["publish"] is False, "expected publish=False, got %s" % r["publish"]
    assert r["action"] == "update", "expected action=update, got %s" % r["action"]
    assert r["new_state"]["active"] is True
    assert r["event"] is None
    print("  PASS: test_update_no_publish")


def test_fall_end():
    """Cities fell to 10 → action=end, ended_at set on event."""
    cities = []
    for i in range(10):
        cities.append(_make_city("Город%d" % i, "Область%d" % (i % 4)))
    radar = _radar(cities, fetched_ago_sec=60)
    prev = _wave_state(
        active=True,
        cities=30,
        regions=6,
        region_list=["Область%d" % i for i in range(6)],
        started_at=_to_iso(NOW - 3600),
        peak_cities=49,
        peak_regions=8,
        current_event_id="2026-07-12-1900",
    )

    r = evaluate(radar, prev, NOW)
    assert r["action"] == "end", "expected action=end, got %s" % r["action"]
    assert r["publish"] is True
    assert r["new_state"]["active"] is False
    assert r["event"] is not None
    assert r["event"]["ended_at"] is not None, "ended_at must be set"
    assert r["event"]["peak_cities"] == 49
    print("  PASS: test_fall_end")


def test_stale_noop():
    """Snapshot older than STALE_SEC → action=noop, state not touched."""
    cities = []
    for i in range(49):
        cities.append(_make_city("Город%d" % i, "Область%d" % (i % 8)))
    radar = _radar(cities, fetched_ago_sec=STALE_SEC + 100)
    prev = _wave_state()

    r = evaluate(radar, prev, NOW)
    assert r["action"] == "noop", "expected action=noop, got %s" % r["action"]
    assert r["publish"] is False
    assert r["new_state"] is prev, "state should be unchanged (same object)"
    print("  PASS: test_stale_noop")


def test_below_rise_noop():
    """20 bright / 3 regions → noop (below RISE threshold)."""
    cities = []
    for i in range(20):
        cities.append(_make_city("Город%d" % i, "Область%d" % (i % 3)))
    radar = _radar(cities, fetched_ago_sec=60)
    prev = _wave_state(last_event={"date": "2026-01-01"})

    r = evaluate(radar, prev, NOW)
    assert r["action"] == "noop", "expected action=noop, got %s" % r["action"]
    assert r["publish"] is False
    assert r["new_state"]["active"] is False
    print("  PASS: test_below_rise_noop")


def test_empty_cities_noop():
    """Пустой cities[] (снимок запасного region-писателя) → noop, активная
    волна НЕ закрывается ложно."""
    radar = _radar([], fetched_ago_sec=60)
    prev = _wave_state(
        active=True,
        cities=30,
        regions=6,
        started_at=_to_iso(NOW - 3600),
        peak_cities=40,
        peak_regions=8,
        current_event_id="2026-07-16-2050",
    )

    r = evaluate(radar, prev, NOW)
    assert r["action"] == "noop", "expected noop on empty cities, got %s" % r["action"]
    assert r["publish"] is False
    assert r["new_state"] is prev, "state must be untouched (wave stays active)"
    assert r["new_state"]["active"] is True
    print("  PASS: test_empty_cities_noop")


def test_publish_pages_ok():
    """Обе отработали (rc=0) → True, отката нет."""
    calls, undone = [], []
    ok = _mod.publish_pages(
        runner=lambda cmd: (calls.append(cmd[-1].split("/")[-1]), 0)[1],
        restore=lambda: undone.append(True))
    assert ok is True
    assert calls == ["gen-wave.py", "build-nav.py"], "порядок пары: %s" % calls
    assert not undone, "при успехе откатывать нечего"
    print("  PASS: test_publish_pages_ok")


def test_publish_pages_buildnav_fail_rolls_back():
    """🔴 Ядро фикса: build-nav упал → откат страниц, брак не уезжает."""
    undone = []

    def runner(cmd):
        return 0 if cmd[-1].endswith("gen-wave.py") else 1

    ok = _mod.publish_pages(runner=runner, restore=lambda: undone.append(True))
    assert ok is False, "провал build-nav должен возвращать False"
    assert undone == [True], "страницы обязаны откатиться (иначе git-sync выкатит брак)"
    print("  PASS: test_publish_pages_buildnav_fail_rolls_back")


def test_publish_pages_genwave_fail_stops_pair():
    """gen-wave упал → build-nav не запускаем, откатываемся."""
    calls, undone = [], []

    def runner(cmd):
        calls.append(cmd[-1].split("/")[-1])
        return 1

    ok = _mod.publish_pages(runner=runner, restore=lambda: undone.append(True))
    assert ok is False
    assert calls == ["gen-wave.py"], "после провала gen-wave пара обрывается: %s" % calls
    assert undone == [True]
    print("  PASS: test_publish_pages_genwave_fail_stops_pair")


def test_publish_pages_exception_rolls_back():
    """Скрипт не запустился вовсе (исключение) → тоже откат, не молчим."""
    undone = []

    def runner(cmd):
        raise OSError("no interpreter")

    ok = _mod.publish_pages(runner=runner, restore=lambda: undone.append(True))
    assert ok is False
    assert undone == [True]
    print("  PASS: test_publish_pages_exception_rolls_back")


def test_commit_artifacts_stages_wave_pages():
    """Автопаблиш коммитит СВОИ файлы (страница+снимок+обложка) — иначе их не
    коммитит никто и pull всех агентов встаёт (инцидент 17.07)."""
    cmds = []

    def runner(cmd):
        cmds.append(cmd)
        return 0

    ok = _mod.commit_artifacts({"id": "2026-07-17-2020", "date": "2026-07-17"},
                               runner=runner)
    assert ok is True
    add = next(c for c in cmds if c[:2] == ["git", "add"])
    assert "volna-dronov.html" in add, "страница волны должна стейджиться"
    assert "volna-dronov" in add, "каталог снимков должен стейджиться"
    assert any(c[:2] == ["git", "commit"] for c in cmds), "должен быть commit"
    print("  PASS: test_commit_artifacts_stages_wave_pages")


def test_commit_artifacts_add_fail_no_commit():
    """git add упал → commit не зовём, не падаем жёстко."""
    calls = []

    def runner(cmd):
        calls.append(cmd[:2])
        return 1 if cmd[:2] == ["git", "add"] else 0

    ok = _mod.commit_artifacts({"id": "x", "date": "2026-07-17"}, runner=runner)
    assert ok is False
    assert ["git", "commit"] not in calls, "после провала add коммит не зовём"
    print("  PASS: test_commit_artifacts_add_fail_no_commit")


if __name__ == "__main__":
    test_rise_publish()
    test_update_no_publish()
    test_fall_end()
    test_stale_noop()
    test_below_rise_noop()
    test_empty_cities_noop()
    test_publish_pages_ok()
    test_publish_pages_buildnav_fail_rolls_back()
    test_publish_pages_genwave_fail_stops_pair()
    test_publish_pages_exception_rolls_back()
    test_commit_artifacts_stages_wave_pages()
    test_commit_artifacts_add_fail_no_commit()
    print("OK")
