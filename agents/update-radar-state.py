#!/usr/bin/env python3
"""Refresh data/radar-state.json from the public RadarMap state endpoint.

This is a data bridge, not a tactical predictor: it stores public alert state,
source timestamps, and feed snippets so the site can show freshness honestly.
If the upstream is unavailable, the script exits non-zero and leaves the last
known snapshot untouched.
"""
import datetime as dt
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "radar-state.json")
URL = os.environ.get("RADAR_STATE_SOURCE", "https://radar-map.ru/api/state")
TIMEOUT = int(os.environ.get("RADAR_STATE_TIMEOUT", "25"))
FEED_LIMIT = int(os.environ.get("RADAR_STATE_FEED_LIMIT", "80"))
UA = "npz-tactical-map-radar-refresh/1.1 (+https://npz-tactical-map.vercel.app/radar)"


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def iso(ts):
    return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": UA,
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        status = getattr(resp, "status", 200)
        raw = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    if status != 200:
        raise RuntimeError("upstream status %s" % status)
    if "json" not in ctype.lower():
        raise RuntimeError("upstream content-type %r" % ctype)
    return json.loads(raw.decode("utf-8"))


def max_event_ts(payload):
    max_ts = 0
    def scan(item):
        nonlocal max_ts
        if isinstance(item, dict):
            ts = item.get("last_event_ts") or item.get("ts")
            if isinstance(ts, (int, float)) and ts > max_ts:
                max_ts = int(ts)
    regions = payload.get("regions") or {}
    if isinstance(regions, dict):
        for item in regions.values():
            scan(item)
    cities = payload.get("cities") or []
    if isinstance(cities, dict):
        cities = cities.values()
    if isinstance(cities, list) or not isinstance(cities, dict):
        for item in cities:
            scan(item)
    districts = payload.get("districts") or {}
    if isinstance(districts, dict):
        for item in districts.values():
            scan(item)
    feed = payload.get("feed") or []
    if isinstance(feed, list):
        for item in feed[:FEED_LIMIT * 3]:
            scan(item)
    return max_ts


def compact_feed(feed):
    if not isinstance(feed, list):
        return []
    out = []
    for item in feed[:FEED_LIMIT]:
        if not isinstance(item, dict):
            continue
        out.append({
            "msg_id": item.get("msg_id"),
            "text": item.get("text", ""),
            "ts": item.get("ts"),
            "time_label": item.get("time_label"),
            "source_id": item.get("source_id"),
            "source_label": item.get("source_label"),
        })
    return out


def normalize(payload):
    now = utc_now()
    ts = max_event_ts(payload)
    if not ts:
        raise RuntimeError("upstream state has no event timestamps")
    return {
        "type": "npz-radar-state",
        "schema_version": 2,
        "source_url": URL,
        "source_label": "RadarMap public state",
        "upstream_type": payload.get("type"),
        "upstream_version": payload.get("version"),
        "regions": payload.get("regions") or {},
        "cities": payload.get("cities") or [],
        "districts": payload.get("districts") or {},
        "airport_markers": payload.get("airport_markers") or [],
        "feed": compact_feed(payload.get("feed") or []),
        "sources": [
            {"id": "radar-map", "label": "RadarMap", "url": "https://radar-map.ru/"},
        ],
        "timestamp": ts,
        "last_event_at": iso(ts),
        "fetched_at": now.isoformat().replace("+00:00", "Z"),
        "poll_interval_sec": int(payload.get("poll_interval_sec") or 60),
        "meta": {
            "generated_at": now.isoformat().replace("+00:00", "Z"),
            "source_age_seconds": max(0, int(now.timestamp()) - ts),
            "city_count": len(payload.get("cities") or []),
            "region_count": len(payload.get("regions") or {}),
            "feed_count": len(payload.get("feed") or []),
        },
    }


def save(state, out=None):
    """Atomic write (tmp + os.replace): a reader never observes a truncated/partial file."""
    out = out or OUT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, out)


def main():
    payload = fetch_json(URL)
    state = normalize(payload)
    save(state)
    print("radar-state: %s events, source age %ss, wrote %s" % (
        state["meta"]["feed_count"], state["meta"]["source_age_seconds"], OUT))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("radar-state: ERROR: %s" % exc, file=sys.stderr)
        sys.exit(1)
