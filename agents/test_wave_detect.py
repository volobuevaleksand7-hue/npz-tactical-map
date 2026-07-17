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


if __name__ == "__main__":
    test_rise_publish()
    test_update_no_publish()
    test_fall_end()
    test_stale_noop()
    test_below_rise_noop()
    test_empty_cities_noop()
    print("OK")
