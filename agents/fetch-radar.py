#!/usr/bin/env python3
"""
fetch-radar.py — Fetch radar data from radar-map.ru/api/state
Converts to our format and saves to data/radar-state.json

Usage:
  python3 agents/fetch-radar.py          # Fetch and save
  python3 agents/fetch-radar.py --dry-run # Test only, don't save
"""
import json
import os
import sys
import urllib.request
import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
OUTPUT = os.path.join(DATA, "radar-state.json")
API_URL = "https://radar-map.ru/api/state"

def fetch_radar():
    """Fetch radar data from radar-map.ru"""
    req = urllib.request.Request(API_URL, headers={
        "User-Agent": "NPZ-Tactical-Map/1.0",
        "Accept": "application/json"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def convert_format(data):
    """Convert radar-map.ru format to our format"""
    cities_dict = {}
    for city in data.get("cities", []):
        key = city.get("key", "")
        if not key:
            key = f"{city.get('name', '')}|{city.get('region', '')}"
        cities_dict[key] = {
            "name": city.get("name", ""),
            "region": city.get("region", ""),
            "bpla": city.get("bpla", False),
            "bplaDim": city.get("bplaDim", False),
            "uab": city.get("uab", False),
            "uabDim": city.get("uabDim", False),
            "fpv": city.get("fpv", False),
            "rocket": city.get("rocket", False),
            "rocket_level": city.get("rocket_level", False),
            "aviation": city.get("aviation", False),
            "pvo": city.get("pvo", False),
            "lat": city.get("lat", 0),
            "lon": city.get("lon", 0)
        }
    
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "cities": cities_dict,
        "timestamp": now.timestamp(),
        "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")
    }

def stats(result):
    """Print statistics"""
    cities = result.get("cities", {})
    threats = {k: v for k, v in cities.items() if v.get("bpla") or v.get("rocket") or v.get("pvo")}
    
    bpla = sum(1 for v in cities.values() if v.get("bpla"))
    rocket = sum(1 for v in cities.values() if v.get("rocket"))
    pvo = sum(1 for v in cities.values() if v.get("pvo"))
    
    print(f"Всего городов: {len(cities)}")
    print(f"С угрозами: {len(threats)}")
    print(f"БПЛА: {bpla}, Ракеты: {rocket}, ПВО: {pvo}")
    
    if threats:
        print("\nГорода с угрозами:")
        for key, city in list(threats.items())[:10]:
            flags = []
            if city.get("bpla"): flags.append("БПЛА")
            if city.get("rocket"): flags.append("ракета")
            if city.get("pvo"): flags.append("ПВО")
            print(f"  {city['name']} ({city['region']}): {', '.join(flags)}")

def main():
    dry_run = "--dry-run" in sys.argv
    
    print(f"[fetch-radar] Запрос к {API_URL}...")
    try:
        data = fetch_radar()
        print(f"[fetch-radar] ✅ Получено: {len(data.get('regions', {}))} регионов, {len(data.get('cities', []))} городов")
    except Exception as e:
        print(f"[fetch-radar] ❌ Ошибка: {e}")
        sys.exit(1)
    
    print(f"\n[fetch-radar] Конвертация в наш формат...")
    result = convert_format(data)
    
    print(f"\n[fetch-radar] Статистика:")
    stats(result)
    
    if dry_run:
        print(f"\n[fetch-radar] --dry-run: не сохраняю")
        return
    
    os.makedirs(DATA, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"\n[fetch-radar] ✅ Сохранено: {OUTPUT}")

if __name__ == "__main__":
    main()
