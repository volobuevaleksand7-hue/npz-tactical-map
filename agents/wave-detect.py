#!/usr/bin/env python3
"""Детектор «волна дронов» — анализирует radar-state.json, детектит всплеск
активности БПЛА, публикует событие при rising/falling edge.

Чистая функция evaluate() отделена от IO (main()) для тестируемости.
Запускается каждый радар-крон (hermes/cron-radar-refresh.sh).

Структура файлов:
  data/radar-state.json  — вход (cities[], fetched_at)
  data/wave-state.json   — текущее состояние детектора
  data/wave-events.json  — append-only архив событий

Константы (пороги) вынесены наверх файла, как в spec §2.
"""
import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RADAR_PATH = os.path.join(ROOT, "data", "radar-state.json")
WAVE_STATE_PATH = os.path.join(ROOT, "data", "wave-state.json")
WAVE_EVENTS_PATH = os.path.join(ROOT, "data", "wave-events.json")

RISE_CITIES = 25
RISE_REGIONS = 4
FALL_CITIES = 15
FRESH_SEC = 45 * 60
COOLDOWN_SEC = 6 * 3600
STALE_SEC = 30 * 60


def _parse_iso(s):
    """Parse ISO 8601 string to epoch seconds (UTC)."""
    if not s:
        return 0
    s = s.rstrip("Z")
    try:
        if "." in s:
            return int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%f").replace(
                tzinfo=dt.timezone.utc).timestamp())
        return int(dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=dt.timezone.utc).timestamp())
    except ValueError:
        return 0


def _to_iso(epoch):
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _event_id(epoch):
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime(
        "%Y-%m-%d-%H%M")


def evaluate(radar_state, prev_state, now_ts):
    """Pure function — returns action dict, no IO.

    Args:
        radar_state: parsed radar-state.json dict (needs cities[], fetched_at)
        prev_state: parsed wave-state.json dict (or {})
        now_ts: current epoch seconds (int)

    Returns:
        {"publish": bool, "action": str, "new_state": dict, "event": dict|None}
    """
    fetched_at = radar_state.get("fetched_at", "")
    fetched_ts = _parse_iso(fetched_at)

    # STALE guard
    if fetched_ts and (now_ts - fetched_ts) > STALE_SEC:
        return {
            "publish": False,
            "action": "noop",
            "new_state": prev_state,
            "event": None,
        }

    # Count bright fresh cities
    bright = set()
    region_set = set()
    for c in radar_state.get("cities", []):
        if (c.get("bpla") and not c.get("bplaDim")
                and (now_ts - c.get("last_event_ts", 0)) <= FRESH_SEC):
            bright.add(c.get("name", ""))
            region_set.add(c.get("region", ""))

    cities = len(bright)
    regions = len(region_set)

    active = prev_state.get("active", False)

    if not active:
        # quiet → check rise
        last_pub = _parse_iso(prev_state.get("last_event", {}).get("date", ""))
        if (cities >= RISE_CITIES and regions >= RISE_REGIONS
                and (now_ts - last_pub) >= COOLDOWN_SEC):
            now_iso = _to_iso(now_ts)
            ev_id = _event_id(now_ts)
            event = {
                "id": ev_id,
                "date": now_iso[:10],
                "started_at": now_iso,
                "ended_at": None,
                "peak_cities": cities,
                "peak_regions": regions,
                "region_list": sorted(region_set),
                "published_at": now_iso,
            }
            new_state = {
                "active": True,
                "cities": cities,
                "regions": regions,
                "region_list": sorted(region_set),
                "started_at": now_iso,
                "peak_cities": cities,
                "peak_regions": regions,
                "current_event_id": ev_id,
                "updated_at": now_iso,
            }
            return {"publish": True, "action": "start",
                    "new_state": new_state, "event": event}
        # stays quiet
        now_iso = _to_iso(now_ts)
        new_state = dict(prev_state)
        new_state.update({
            "active": False,
            "cities": cities,
            "regions": regions,
            "region_list": sorted(region_set),
            "started_at": None,
            "peak_cities": 0,
            "peak_regions": 0,
            "current_event_id": None,
            "updated_at": now_iso,
        })
        return {"publish": False, "action": "noop",
                "new_state": new_state, "event": None}

    # active — check fall
    if cities < FALL_CITIES:
        now_iso = _to_iso(now_ts)
        ev_id = prev_state.get("current_event_id", "")
        peak_c = max(prev_state.get("peak_cities", 0), cities)
        peak_r = max(prev_state.get("peak_regions", 0), regions)
        all_regions = set(prev_state.get("region_list", [])) | region_set
        event = {
            "id": ev_id,
            "date": prev_state.get("started_at", "")[:10],
            "started_at": prev_state.get("started_at", ""),
            "ended_at": now_iso,
            "peak_cities": peak_c,
            "peak_regions": peak_r,
            "region_list": sorted(all_regions),
            "published_at": prev_state.get("started_at", ""),
        }
        new_state = {
            "active": False,
            "cities": cities,
            "regions": regions,
            "region_list": sorted(region_set),
            "started_at": None,
            "peak_cities": peak_c,
            "peak_regions": peak_r,
            "current_event_id": None,
            "updated_at": now_iso,
            "last_event": {
                "date": prev_state.get("started_at", "")[:10],
                "event_id": ev_id,
            },
        }
        return {"publish": True, "action": "end",
                "new_state": new_state, "event": event}

    # active — still in wave (update)
    now_iso = _to_iso(now_ts)
    peak_c = max(prev_state.get("peak_cities", 0), cities)
    peak_r = max(prev_state.get("peak_regions", 0), regions)
    all_regions = set(prev_state.get("region_list", [])) | region_set
    new_state = dict(prev_state)
    new_state.update({
        "active": True,
        "cities": cities,
        "regions": regions,
        "region_list": sorted(all_regions),
        "peak_cities": peak_c,
        "peak_regions": peak_r,
        "updated_at": now_iso,
    })
    return {"publish": False, "action": "update",
            "new_state": new_state, "event": None}


def _read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _append_event(event):
    events = []
    if os.path.exists(WAVE_EVENTS_PATH):
        try:
            with open(WAVE_EVENTS_PATH, encoding="utf-8") as f:
                events = json.load(f)
        except Exception:
            events = []
    events.append(event)
    _write_json(WAVE_EVENTS_PATH, events)


def main():
    radar_state = _read_json(RADAR_PATH)
    if not radar_state:
        print("wave-detect: ERROR reading %s" % RADAR_PATH, file=sys.stderr)
        sys.exit(1)

    prev_state = _read_json(WAVE_STATE_PATH)
    now_ts = int(dt.datetime.now(dt.timezone.utc).timestamp())

    result = evaluate(radar_state, prev_state, now_ts)
    action = result["action"]
    publish = result["publish"]

    print("wave-detect: cities=%d regions=%d action=%s publish=%s" % (
        result["new_state"].get("cities", 0),
        result["new_state"].get("regions", 0),
        action, publish))

    _write_json(WAVE_STATE_PATH, result["new_state"])

    if result["event"] is not None:
        _append_event(result["event"])

    if publish and action in ("start", "end"):
        # gen-wave.py строит страницы, но НЕ вшивает навигацию (это делает
        # build-nav.py — иначе живая /volna-dronov регенерится без меню/шапки/
        # vpn-nudge). Гоняем обе последовательно; git-sync крона запушит итог.
        for script in ("gen-wave.py", "build-nav.py"):
            try:
                subprocess.run(
                    [sys.executable, os.path.join(ROOT, "agents", script)],
                    check=False)
            except Exception as exc:
                print("wave-detect: WARNING %s failed: %s" % (script, exc),
                      file=sys.stderr)


if __name__ == "__main__":
    main()
