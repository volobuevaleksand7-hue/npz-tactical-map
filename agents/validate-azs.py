#!/usr/bin/env python3
"""Валидатор схемы данных вкладки АЗС. Запуск: python3 agents/validate-azs.py"""
import json, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(n):
    return json.load(open(os.path.join(ROOT, "data", n), encoding="utf-8"))


ok = True


def err(m):
    global ok
    ok = False
    print("FAIL:", m)


# azs-stations.json — компактная табличная схема: station row =
# [osm_numeric_id, brand, lat, lon, region_idx, city?, addr?, brand_label?]
st = load("azs-stations.json")
if st.get("meta", {}).get("count", 0) < 100:
    err("azs-stations: count < 100")
regions_map = st.get("regions_map", [])
for row in st.get("stations", []):
    if len(row) < 5 or not isinstance(row[2], (int, float)) or not isinstance(row[3], (int, float)):
        err("station bad coords: " + str(row[:1]))
        break
    if not (0 <= row[4] < len(regions_map)):
        err("station bad region_idx: " + str(row[:1]))
        break
    if not row[1]:
        err("station no brand: " + str(row[:1]))
        break

# azs-routes.json
rt = load("azs-routes.json")
if len(rt.get("routes", [])) < 1:
    err("routes empty")
for r in rt.get("routes", []):
    if len(r.get("waypoints", [])) < 2:
        err("route <2 wp: " + str(r.get("id")))

print("OK azs data valid (%d stations, %d routes)" % (st["meta"]["count"], len(rt["routes"])) if ok else "INVALID")
sys.exit(0 if ok else 1)
