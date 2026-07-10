#!/usr/bin/env python3
"""
fetch-radar.py — manual/dry-run CLI for the radar-map.ru state fetch.

ponytail (H5): this used to be a second, independently-maintained
fetch+convert+save pipeline. It drifted from update-radar-state.py's
schema — dict-keyed `cities` instead of a list, no schema_version/regions/
districts/feed — and wrote data/radar-state.json non-atomically (plain
`open(..., "w")`, no tmp+rename). Since update-radar-state.py already runs
on a 1-5 min cron and is the schema of record (hermes crontab, healthcheck,
radar.html), running this script by hand silently downgraded the live file
mid-write. Delegating to its fetch_json()/normalize()/save() keeps there
being exactly one schema and one atomic writer — extend those, not this.

Usage:
  python3 agents/fetch-radar.py          # Fetch and save (atomic, canonical schema)
  python3 agents/fetch-radar.py --dry-run # Fetch + print stats, don't save
"""
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "update_radar_state", os.path.join(_HERE, "update-radar-state.py"))
_canonical = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_canonical)


def stats(state):
    """Print a quick city/threat summary from the canonical (list-of-cities) schema."""
    cities = state.get("cities") or []
    if isinstance(cities, dict):  # tolerate old-style snapshots if ever read back
        cities = list(cities.values())
    threats = [c for c in cities if isinstance(c, dict) and (c.get("bpla") or c.get("rocket") or c.get("pvo"))]
    bpla = sum(1 for c in cities if isinstance(c, dict) and c.get("bpla"))
    rocket = sum(1 for c in cities if isinstance(c, dict) and c.get("rocket"))
    pvo = sum(1 for c in cities if isinstance(c, dict) and c.get("pvo"))

    print(f"Всего городов: {len(cities)}")
    print(f"С угрозами: {len(threats)}")
    print(f"БПЛА: {bpla}, Ракеты: {rocket}, ПВО: {pvo}")

    if threats:
        print("\nГорода с угрозами:")
        for c in threats[:10]:
            flags = []
            if c.get("bpla"): flags.append("БПЛА")
            if c.get("rocket"): flags.append("ракета")
            if c.get("pvo"): flags.append("ПВО")
            print(f"  {c.get('name')} ({c.get('region')}): {', '.join(flags)}")


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"[fetch-radar] Запрос к {_canonical.URL}...")
    try:
        payload = _canonical.fetch_json(_canonical.URL)
        state = _canonical.normalize(payload)
    except Exception as e:
        print(f"[fetch-radar] ❌ Ошибка: {e}")
        sys.exit(1)

    print("\n[fetch-radar] Статистика:")
    stats(state)

    if dry_run:
        print("\n[fetch-radar] --dry-run: не сохраняю")
        return

    _canonical.save(state)
    print(f"\n[fetch-radar] ✅ Сохранено: {_canonical.OUT}")


if __name__ == "__main__":
    main()
