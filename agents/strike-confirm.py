#!/usr/bin/env python3
"""Авто-подтверждение ударов по НПЗ из ДВУХ независимых открытых источников:
  1) NASA FIRMS — спутниковые термоточки (пожары) рядом с координатами заводов (нужен бесплатный MAP_KEY).
  2) GDELT DOC 2.0 — поток мировых новостей про удары по НПЗ (без ключа).
Пишет data/strike-confirm.json: спутниковые пожары по заводам + новостные кандидаты.
Фронт может показать «🛰 подтверждено спутником». FIRMS активируется, когда задан FIRMS_MAP_KEY.

Запуск:  FIRMS_MAP_KEY=<key> python3 agents/strike-confirm.py   (без ключа — только GDELT)
"""
import json, os, sys, time, urllib.parse, urllib.request, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "npz-tactical-map/1.0 (OSINT fuel map)"}
FIRMS_KEY = os.environ.get("FIRMS_MAP_KEY", "").strip()


def get(url, timeout=40, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as ex:
            last = ex
            if ex.code == 429:
                time.sleep(8 * (i + 1))  # backoff на rate-limit
                continue
            raise
        except Exception as ex:
            last = ex
            time.sleep(5)
    raise last


# ---------- GDELT (без ключа; лимит 1 запрос / 5 сек) ----------
def gdelt_candidates():
    # Английские ключи + sourcecountry:RS — GDELT транслингвально ловит и русскоязычные источники.
    q = "refinery (drone OR strike OR fire OR halted OR explosion) sourcecountry:RS"
    url = ("https://api.gdeltproject.org/api/v2/doc/doc?query=" + urllib.parse.quote(q)
           + "&mode=artlist&maxrecords=60&timespan=72h&format=json&sort=datedesc")
    out = []
    for attempt in range(5):
        time.sleep(6)  # уважаем лимит 1/5с
        try:
            raw = get(url)
        except Exception as ex:
            print("GDELT fetch error:", ex, file=sys.stderr)
            continue
        if not raw.lstrip().startswith("{"):  # rate-limit/HTML вместо JSON
            print("GDELT rate-limited, retry...", file=sys.stderr)
            continue
        try:
            data = json.loads(raw)
        except Exception as ex:
            print("GDELT parse error:", ex, file=sys.stderr)
            continue
        for a in data.get("articles", []):
            out.append({
                "title": a.get("title", "")[:200], "url": a.get("url", ""),
                "domain": a.get("domain", ""), "seendate": a.get("seendate", ""),
                "lang": a.get("language", ""),
            })
        break
    return out


# ---------- FIRMS (нужен MAP_KEY) ----------
def firms_fires_near(lat, lon, days=3, half=0.06):
    # area/csv/[KEY]/VIIRS_SNPP_NRT/[W,S,E,N]/[DAYS]
    if not FIRMS_KEY:
        return None
    w, s, e, n = lon - half, lat - half, lon + half, lat + half
    fires = []
    for src in ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT"):
        url = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/%s/%s/%s,%s,%s,%s/%d" % (
            FIRMS_KEY, src, w, s, e, n, days)
        try:
            csv = get(url, timeout=60)
            lines = [ln for ln in csv.splitlines() if ln.strip()]
            if len(lines) < 2:
                continue
            hdr = lines[0].split(",")
            li = {k: i for i, k in enumerate(hdr)}
            for ln in lines[1:]:
                c = ln.split(",")
                try:
                    fires.append({
                        "lat": float(c[li["latitude"]]), "lon": float(c[li["longitude"]]),
                        "date": c[li.get("acq_date", 0)], "time": c[li.get("acq_time", 0)],
                        "frp": c[li["frp"]] if "frp" in li else "", "src": src,
                    })
                except Exception:
                    pass
        except Exception as ex:
            print("FIRMS error %s: %s" % (src, ex), file=sys.stderr)
        time.sleep(1)
    return fires


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    # GDELT
    gdelt = gdelt_candidates()
    print("GDELT candidates:", len(gdelt), file=sys.stderr)

    # FIRMS по заводам из fuel-state
    sat = []
    fs = json.load(open(os.path.join(ROOT, "data", "fuel-state.json"), encoding="utf-8"))
    refineries = fs.get("refineries", [])
    if FIRMS_KEY:
        for r in refineries:
            if not isinstance(r.get("lat"), (int, float)):
                continue
            fires = firms_fires_near(r["lat"], r["lon"])
            if fires:
                sat.append({"refinery": r.get("name"), "id": r.get("id"),
                            "lat": r["lat"], "lon": r["lon"], "fire_count": len(fires),
                            "fires": fires[:8]})
        print("FIRMS: %d/%d заводов с термоточками" % (len(sat), len(refineries)), file=sys.stderr)
    else:
        print("FIRMS_MAP_KEY не задан — спутниковая часть пропущена (только GDELT)", file=sys.stderr)

    out = {
        "meta": {
            "generated_at": now.strftime("%Y-%m-%dT%H:%MZ"),
            "firms_enabled": bool(FIRMS_KEY),
            "note": "Авто-кандидаты подтверждения ударов. GDELT — новостной поток (без ключа); FIRMS — спутниковые пожары рядом с НПЗ (нужен бесплатный MAP_KEY). НЕ заменяет ручную верификацию.",
        },
        "satellite_fires": sat,
        "gdelt_candidates": gdelt[:50],
    }
    p = os.path.join(ROOT, "data", "strike-confirm.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("WROTE %s: %d sat-заводов, %d GDELT-кандидатов" % (p, len(sat), len(gdelt)))


if __name__ == "__main__":
    main()
