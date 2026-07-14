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
import datetime

try:
    import requests
except ImportError:
    print("[fetch-radar] requests not installed. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
OUTPUT = os.path.join(DATA, "radar-state.json")
API_URL = "https://radar-map.ru/api/state"

def fetch_radar():
    """Fetch radar data from radar-map.ru"""
    try:
        resp = requests.get(API_URL, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) NPZ-Tactical-Map/1.0",
            "Accept": "application/json"
        }, timeout=30, verify=False)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[fetch-radar] requests failed: {e}, falling back to curl...")
        import subprocess, tempfile
        import urllib.request
        # curl -k works reliably when requests/urllib3 SSL fails
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as tmp:
            tmp_path = tmp.name
        cmd = [
            "curl", "-sSfk", "--connect-timeout", "15", "--max-time", "30",
            "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) NPZ-Tactical-Map/1.0",
            "-H", "Accept: application/json",
            "-o", tmp_path,
            API_URL
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if result.returncode != 0:
            raise RuntimeError(f"curl failed (exit {result.returncode}): {result.stderr}")
        with open(tmp_path) as f:
            data = json.load(f)
        os.unlink(tmp_path)
        return data

def convert_format(data):
    """Convert radar-map.ru format to our format (based on regions)"""
    regions_dict = {}
    for region_name, region_data in data.get("regions", {}).items():
        regions_dict[region_name] = {
            "name": region_name,
            "bpla": region_data.get("bpla", False),
            "bplaDim": region_data.get("bplaDim", False),
            "uab": region_data.get("uab", False),
            "uabDim": region_data.get("uabDim", False),
            "fpv": region_data.get("fpv", False),
            "rocket": region_data.get("rocket", False),
            "rocket_level": region_data.get("rocket_level", False),
            "aviation": region_data.get("aviation", False),
            "pvo": region_data.get("pvo", False),
            "explosionOnRegion": region_data.get("explosionOnRegion", False),
            "bplaLaunchAnim": region_data.get("bplaLaunchAnim", False),
            "rocketOnRegion": region_data.get("rocketOnRegion", False),
            "fill": region_data.get("fill", ""),
            "last_event_ts": region_data.get("last_event_ts", 0),
            "source_text": region_data.get("source_text", "")
        }
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "type": data.get("type", "state"),
        "version": data.get("version"),
        "geo_parser_version": data.get("geo_parser_version"),
        "regions": regions_dict,
        "timestamp": now.timestamp(),
        "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")
    }

def stats(result):
    """Print statistics"""
    regions = result.get("regions", {})
    
    with_threats = {k: v for k, v in regions.items()
        if v.get("rocket") or v.get("bpla") or v.get("uab") or v.get("fpv")
        or v.get("aviation") or v.get("explosionOnRegion")}
    
    rocket = sum(1 for v in regions.values() if v.get("rocket") and v.get("rocket_level"))
    bpla = sum(1 for v in regions.values() if v.get("bpla"))
    uab = sum(1 for v in regions.values() if v.get("uab"))
    aviation = sum(1 for v in regions.values() if v.get("aviation"))
    
    red = sum(1 for v in regions.values() if v.get("fill") == "#dc2626")
    yellow = sum(1 for v in regions.values() if v.get("fill") == "#d8c06a")
    
    print(f"Всего регионов: {len(regions)}")
    print(f"С угрозами: {len(with_threats)}")
    print(f"  Красный (ракетная опасность): {red}")
    print(f"  Жёлтый (БПЛА/предупреждение):  {yellow}")
    print(f"  Ракеты: {rocket}, БПЛА: {bpla}, УАБ: {uab}, Авиация: {aviation}")
    
    if with_threats:
        print(f"\nРегионы с угрозами ({len(with_threats)}):")
        for name, r in sorted(with_threats.items()):
            flags = []
            if r.get("rocket") and r.get("rocket_level"): flags.append("ракета")
            if r.get("bpla"): flags.append("БПЛА")
            if r.get("uab"): flags.append("УАБ")
            if r.get("fpv"): flags.append("FPV")
            if r.get("aviation"): flags.append("авиация")
            if r.get("explosionOnRegion"): flags.append("взрывы")
            fill_label = {"#dc2626":"КРАСН","#d8c06a":"ЖЕЛТ","#f59e0b":"ОРАНЖ"}.get(r.get("fill"), r.get("fill"))
            print(f"  {name}: [{'/'.join(flags)}] ({fill_label})")

def main():
    dry_run = "--dry-run" in sys.argv
    
    print(f"[fetch-radar] Запрос к {API_URL}...")
    try:
        data = fetch_radar()
        regions = data.get("regions", {})
        print(f"[fetch-radar] Получено: {len(regions)} регионов")
    except Exception as e:
        print(f"[fetch-radar] Ошибка: {e}")
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
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[fetch-radar] Сохранено: {OUTPUT}")

if __name__ == "__main__":
    main()
