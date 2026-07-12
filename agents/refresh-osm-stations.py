#!/usr/bin/env python3
"""Разовая/редкая генерация data/azs-stations.json из OpenStreetMap (Overpass).
Координаты+бренды реальные (OSM, ODbL). Регион проставляется point-in-polygon.
Агент-рутина этот файл НЕ трогает — он статичный.

Запуск:  ./.venv/bin/python agents/refresh-osm-stations.py
"""
import json, os, sys, time, requests
from shapely.geometry import shape, Point
from shapely.prepared import prep

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
UA = "npz-tactical-map/1.0 (OSINT fuel availability map; +https://github.com/volobuevaleksand7-hue/npz-tactical-map)"
NAME_KEY = "name"  # подтверждено: russia-regions.geojson использует properties.name

# (south, west, north, east). Тайлы намеренно щедрые/с нахлёстом — point-in-polygon
# по russia-regions.geojson отсекает всё вне РФ, дедуп по OSM id снимает пересечения.
# Покрытие — вся Россия (федеральные округа), а не только Европейская часть.
BBOXES = {
    "Центр":              (50.0, 30.0, 58.5, 43.0),
    "Юг":                 (43.5, 37.0, 51.0, 48.5),
    "Крым":               (44.3, 32.4, 46.3, 36.7),
    "Поволжье-Татарстан": (50.5, 42.5, 57.2, 54.5),  # Саратов/Самара/Пенза/Ульяновск/Чувашия/Марий Эл/Татарстан/Удмуртия
    "Кавказ":             (41.0, 42.5, 44.6, 48.6),  # Дагестан/Чечня/Ингушетия/Осетия/КБР
    "Калининград":        (54.2, 19.4, 55.4, 23.0),
    "Северо-Запад":       (56.0, 27.0, 70.5, 44.5),  # СПб/Карелия/Мурманск/Псков/Новгород/Вологда/Архангельск/Коми
    "Урал-Юг":            (51.0, 54.0, 58.5, 63.0),  # Башкирия-восток/Челябинск/Оренбург-восток/Курган
    "Урал-Север":         (56.0, 58.0, 67.5, 75.0),  # Пермь/Свердловск/Тюмень/ХМАО/ЯНАО
    "Западная Сибирь":    (49.0, 75.0, 61.0, 89.5),  # Омск/Новосибирск/Томск/Алтай/Кемерово/Барнаул
    "Восточная Сибирь":   (49.0, 89.0, 66.0, 119.0), # Красноярск/Хакасия/Тыва/Иркутск/Бурятия/Забайкалье
    "Якутия":             (55.0, 105.0, 72.0, 155.0),# Саха (разрежённо, большой тайл)
    "Дальний Восток":     (42.0, 119.0, 56.5, 145.0),# Амур/ЕАО/Хабаровск-юг/Приморье/Сахалин
    "ДВ-Север":           (50.0, 135.0, 71.0, 180.0),# Магадан/Камчатка/Чукотка/Хабаровск-север
}

# подстрока(низ.регистр) -> (key, label). Порядок важен: первый матч выигрывает.
BRAND_RULES = [
    ("лукойл", "lukoil", "Лукойл"), ("lukoil", "lukoil", "Лукойл"), ("teboil", "lukoil", "Teboil"),
    ("газпромнефт", "gazpromneft", "Газпромнефть"), ("gazprom neft", "gazpromneft", "Газпромнефть"), ("газпром нефт", "gazpromneft", "Газпромнефть"),
    ("роснефт", "rosneft", "Роснефть"), ("rosneft", "rosneft", "Роснефть"),
    ("татнефт", "tatneft", "Татнефть"), ("tatneft", "tatneft", "Татнефть"),
    ("башнефт", "bashneft", "Башнефть"),
    ("сургутнефтегаз", "surgut", "Сургутнефтегаз"),
    ("атан", "atan", "АТАН"),
    ("тэс", "tes", "ТЭС"),
    ("eka", "eka", "ЕКА"), ("ека", "eka", "ЕКА"),
    ("трасса", "trassa", "Трасса"),
    ("нефтьмагистраль", "neftmag", "Нефтьмагистраль"), ("нефтемагистраль", "neftmag", "Нефтьмагистраль"),
    ("ннк", "nnk", "ННК"),
    ("shell", "shell", "Shell"),
    ("газпром", "gazprom", "Газпром"),  # после газпромнефть!
]

CAP_OTHER = 3500  # макс. число безымянных станций (контроль размера файла; вся РФ → выше прежних 1800)


def norm_brand(tags):
    raw = (tags.get("brand") or tags.get("operator") or tags.get("name") or "").strip()
    low = raw.lower()
    for sub, key, label in BRAND_RULES:
        if sub in low:
            return key, label
    return "other", (raw if raw else "АЗС")


def fetch_bbox(s, w, n, e):
    q = '[out:json][timeout:180];node["amenity"="fuel"](%s,%s,%s,%s);out body;' % (s, w, n, e)
    headers = {"User-Agent": UA, "Accept": "application/json"}
    last = None
    for attempt in range(6):
        ep = OVERPASS_ENDPOINTS[attempt % len(OVERPASS_ENDPOINTS)]
        try:
            r = requests.post(ep, data={"data": q}, headers=headers, timeout=220)
            if r.status_code == 200:
                return r.json().get("elements", [])
            last = "HTTP %s @ %s" % (r.status_code, ep)
        except Exception as ex:
            last = "%s @ %s" % (ex, ep)
        print("  retry %d (%s)" % (attempt + 1, last), file=sys.stderr)
        time.sleep(12)
    raise RuntimeError("Overpass failed for bbox %s: %s" % ((s, w, n, e), last))


def load_regions():
    feats = []
    for fn in ["russia-regions.geojson", "crimea-regions.geojson", "new-territories.geojson"]:
        p = os.path.join(ROOT, "data", fn)
        if not os.path.exists(p):
            continue
        gj = json.load(open(p, encoding="utf-8"))
        for f in gj.get("features", []):
            props = f.get("properties", {})
            nm = props.get(NAME_KEY) or props.get("name")
            if not nm:
                continue
            try:
                geom = shape(f["geometry"])
                feats.append((nm, prep(geom)))
            except Exception:
                pass
    return feats


def region_of(lat, lon, regions):
    pt = Point(lon, lat)
    for nm, pgeom in regions:
        if pgeom.contains(pt):
            return nm
    return None


def main():
    regions = load_regions()
    print("regions loaded: %d" % len(regions), file=sys.stderr)
    if not regions:
        sys.exit("no region polygons loaded")
    seen, stations = set(), []
    for label, bbox in BBOXES.items():
        els = fetch_bbox(*bbox)
        print("%s: %d fuel nodes" % (label, len(els)), file=sys.stderr)
        for el in els:
            oid = el.get("id")
            if oid in seen:
                continue
            seen.add(oid)
            lat, lon = el.get("lat"), el.get("lon")
            if lat is None or lon is None:
                continue
            reg = region_of(lat, lon, regions)
            if not reg:
                continue  # вне целевых регионов РФ (отсекаем Украину/Казахстан/Беларусь из bbox)
            tags = el.get("tags", {})
            key, blabel = norm_brand(tags)
            stations.append({
                "id": "osm-%s" % oid,
                "brand": key,
                "brand_label": blabel,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "city": tags.get("addr:city"),
                "region": reg,
                "addr": tags.get("addr:street"),
            })
        time.sleep(3)

    # контроль размера: все branded + ограниченное число other
    branded = [s for s in stations if s["brand"] != "other"]
    others = [s for s in stations if s["brand"] == "other"]
    if len(others) > CAP_OTHER:
        # равномерная прорежка, чтобы сохранить географическое распределение
        step = len(others) / float(CAP_OTHER)
        others = [others[int(i * step)] for i in range(CAP_OTHER)]
    stations = branded + others

    out = {
        "meta": {
            "generated_at": time.strftime("%Y-%m-%d"),
            "source": "OpenStreetMap / Overpass API (ODbL)",
            "regions": list(BBOXES.keys()),
            "count": len(stations),
            "branded": len(branded),
            "note": "Координаты и бренды — реальные (OSM). Наличие топлива — оценка по статусу сети в регионе, не по конкретной колонке.",
        },
        "stations": stations,
    }
    p = os.path.join(ROOT, "data", "azs-stations.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("WROTE %s: %d stations (%d branded, %d other)" % (p, len(stations), len(branded), len(others)))


if __name__ == "__main__":
    main()
