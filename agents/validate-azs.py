#!/usr/bin/env python3
"""Валидатор схемы данных вкладки АЗС. Запуск: python3 agents/validate-azs.py"""
import json, sys, os, re
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

# fuel-availability.json — цвет точки АЗС берётся отсюда (app.js stationLevel): у безбрендовой
# станции (в Крыму это 72 из 96) уровень = level её региона. Регион, записанный зеленее, чем
# живут его же сети, красит их все в «штатно» — так 29.07.2026 весь Крым стал зелёным при
# QR-лимите 20 л. Инвариант: level не зеленее медианы своих сетей (медиана, а не худшая, —
# иначе одна лимитированная сеть из четырёх перекрасит регион и соврёт в другую сторону).
ORD = {"unknown": 0, "calm": 1, "strained": 2, "limited": 3, "severe": 4, "critical": 5}
STATUS2LVL = {"ok": "calm", "normal": "calm", "available": "calm", "open": "calm",
              "minor": "strained", "some": "strained", "limited": "limited", "talony": "limited",
              "severe": "severe", "shortage": "severe", "critical": "critical", "dry": "critical",
              "none": "critical", "closed": "critical"}
RE_REG = re.compile(r"республика|область|обл\.?|край|автономный округ|автономная|город|г\.")


def norm_region(s):
    s = (s or "").lower().replace("ё", "е")
    return re.sub(r"[^а-я]", "", RE_REG.sub("", s))


def nw_level(nw):
    lvl = nw.get("level")
    if lvl in ORD:
        return lvl
    return STATUS2LVL.get(str(nw.get("status", "")).lower(), "unknown")


av = load("fuel-availability.json")
for reg in av.get("regions", []):
    name, lvl = reg.get("region"), reg.get("level")
    if lvl not in ORD:
        err("availability %s: неизвестный level %r" % (name, lvl))
        continue
    nws = [nw_level(n) for n in reg.get("networks", []) if nw_level(n) != "unknown"]
    if nws:
        med = sorted(nws, key=lambda x: ORD[x])[(len(nws) - 1) // 2]  # нижняя медиана при чётном
        if ORD[lvl] < ORD[med]:
            err("availability %s: level=%s зеленее медианы своих сетей (%s из %s)" %
                (name, lvl, med, ", ".join(nws)))
    # медиана не ловит «одна сеть мертва, остальные живы» и паёк у меньшинства сетей
    if lvl == "calm":
        for nw in reg.get("networks", []):
            cap = nw.get("limit_l")
            if nw_level(nw) in ("severe", "critical"):
                err("availability %s: level=calm при сети %s в статусе %s" % (name, nw.get("name"), nw_level(nw)))
            elif cap and cap < 30:  # 30 л ≈ бак, 20 л — уже паёк
                err("availability %s: level=calm при лимите %s л у сети %s" % (name, cap, nw.get("name")))

# Два датасета описывают одно и то же; расхождение на 2+ ступени — значит один из агентов врёт.
fs_lvl = {norm_region(d.get("region")): (d.get("region"), d.get("level"))
          for d in load("fuel-state.json").get("deficit_regions", [])}
for reg in av.get("regions", []):
    other = fs_lvl.get(norm_region(reg.get("region")))
    if other and other[1] in ORD and reg.get("level") in ORD:
        if abs(ORD[other[1]] - ORD[reg["level"]]) >= 2:
            err("%s: availability=%s, но fuel-state.deficit_regions[%s]=%s" %
                (reg["region"], reg["level"], other[0], other[1]))

print("OK azs data valid (%d stations, %d routes)" % (st["meta"]["count"], len(rt["routes"])) if ok else "INVALID")
sys.exit(0 if ok else 1)
