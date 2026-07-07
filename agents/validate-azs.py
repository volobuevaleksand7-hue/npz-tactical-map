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


# azs-stations.json
st = load("azs-stations.json")
if st.get("meta", {}).get("count", 0) < 100:
    err("azs-stations: count < 100")
for s in st.get("stations", []):
    if not isinstance(s.get("lat"), (int, float)) or not isinstance(s.get("lon"), (int, float)):
        err("station bad coords: " + str(s.get("id")))
        break
    if not s.get("region"):
        err("station no region: " + str(s.get("id")))
        break
    if not s.get("brand"):
        err("station no brand: " + str(s.get("id")))
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
