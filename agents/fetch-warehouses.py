#!/usr/bin/env python3
"""Генерация data/warehouses.json — крупные РЦ/фулфилмент-центры Wildberries и Ozon.

Скоуп намеренно узкий: только распределительные центры (WB) и РФЦ (Ozon), без
сортировочных центров и ПВЗ — их тысячи, достоверного открытого датасета нет,
а на карте они превратятся в кашу.

Координаты берутся геокодером Nominatim по адресу склада (адреса — из открытых
справочников для селлеров) и кэшируются в agents/.geocache-warehouses.json:
повторный прогон не ходит в сеть и не двигает точки.

🔴 Статус «поражён» ставится ТОЛЬКО по ударам БПЛА/ракет (как и вся остальная
карта), бытовые пожары сюда не попадают — иначе метка читается как удар.

Запуск:  ./.venv/bin/python agents/fetch-warehouses.py
Проверка (без сети):  ./.venv/bin/python agents/fetch-warehouses.py --check
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "warehouses.json")
CACHE = os.path.join(ROOT, "agents", ".geocache-warehouses.json")
UA = "npz-tactical-map/1.0 (OSINT map; +https://github.com/volobuevaleksand7-hue/npz-tactical-map)"

# Крупные РЦ Wildberries (FBO/FBS). Адреса — открытые справочники поставок.
WB = [
    ("Коледино", "Московская область", "Коледино, ул. Троицкая, 20"),
    ("Подольск", "Московская область", "Подольск, ул. Поливановская, 9"),
    ("Электросталь", "Московская область", "Электросталь, посёлок Случайный, Массив 3"),
    ("Белые Столбы", "Московская область", "Белые Столбы, Домодедово"),
    ("Крёкшино", "Москва", "посёлок совхоза Крёкшино, Тупиковый проезд, 1"),
    ("Пушкино", "Московская область", "Пушкино, улица Пушкинское поле, 2"),
    ("Нахабино", "Московская область", "Нахабино, ул. Советская, 111"),
    ("Новокосино", "Москва", "Москва, ул. Салтыковская, 26"),
    ("Чехов", "Московская область", "Чехов, село Новосёлки, промзона Новосёлки"),
    ("Обухово", "Московская область", "Обухово, Атлант-Парк, 35"),
    ("Софьино", "Московская область", "Софьино, Раменский район"),
    ("Алексин", "Тульская область", "Алексин, деревня Кострово"),
    ("Санкт-Петербург (Парголово)", "Санкт-Петербург", "Парголово, ул. Подгорная, 61"),
    ("Казань (Зеленодольск)", "Татарстан", "Зеленодольск, промышленный парк"),
    ("Екатеринбург", "Свердловская область", "Екатеринбург, ул. Испытателей, 14"),
    ("Новосибирск", "Новосибирская область", "Новосибирск, ул. Петухова, 71"),
    ("Краснодар", "Краснодарский край", "Краснодар, ул. Тихорецкая, 40"),
    ("Невинномысск", "Ставропольский край", "Невинномысск, ул. Тимирязева, 16"),
    ("Воронеж", "Воронежская область", "Воронеж, ул. Урывского, 6"),
    ("Саратов", "Саратовская область", "Саратов, станция Трофимовский-2"),
    ("Самара (Новосемейкино)", "Самарская область", "Новосемейкино, Красноярский район"),
    ("Рязань", "Рязанская область", "Рязань, ул. Новосёлковская, 17"),
    ("Иваново", "Ивановская область", "Иваново, ул. Лежневская, 119"),
    ("Хабаровск", "Хабаровский край", "Хабаровск, ул. Краснореченская, 118"),
    ("Улан-Удэ", "Бурятия", "Улан-Удэ"),
    ("Котовск", "Тамбовская область", "Котовск, Тамбовская область"),
]

# Крупные фулфилмент-центры (РФЦ) Ozon.
OZON = [
    ("Хоругвино", "Московская область", "Хоругвино, Солнечногорский район"),
    ("Гривно", "Московская область", "Гривно, промышленный парк Гривно"),
    ("Домодедово (Кучино)", "Московская область", "деревня Кучино, Домодедово"),
    ("Жуковский", "Московская область", "Жуковский"),
    ("Ногинск (Обухово)", "Московская область", "Обухово, Обухово-Парк, 2"),
    ("Пушкино-1", "Московская область", "Пушкино, Ярославское шоссе, 216"),
    ("Пушкино-2", "Московская область", "Пушкино, Ярославское шоссе, 218"),
    ("Софьино", "Московская область", "Логистический технопарк Софьино, Раменский район"),
    ("Санкт-Петербург (Петро-Славянка)", "Санкт-Петербург", "Петро-Славянка, ул. Софийская, 118"),
    ("СПб Бугры", "Ленинградская область", "Бугры, Всеволожский район, ул. Шоссейная, 50"),
    ("СПб Колпино", "Санкт-Петербург", "Шушары, Колпинское шоссе, 135"),
    ("СПб Шушары", "Санкт-Петербург", "Шушары, Московское шоссе, 143"),
    ("Воронеж", "Воронежская область", "Рамонский район, Промышленная зона"),
    ("Екатеринбург (Кольцовский)", "Свердловская область", "Логопарк Кольцовский, Екатеринбург"),
    ("Казань (Зеленодольск)", "Татарстан", "Зеленодольск, промышленный парк Зеленодольск"),
    ("Краснодар-2 (Дружный)", "Краснодарский край", "посёлок Дружный, Индустриальный парк, Краснодар"),
    ("Новосибирск (Толмачёво)", "Новосибирская область", "Толмачёвский сельсовет, Новосибирская область"),
    ("Самара (Чапаевск)", "Самарская область", "Чапаевск, ул. Индустриальная"),
    ("Ватутинки", "Москва", "Ватутинки, Новая Москва"),
]

# Поражённые ударами БПЛА. Ключ — (оператор, название склада) из списков выше.
# 🔴 Только удары. Бытовые пожары (Шушары-2024, Истра-2022) сюда НЕ вносить.
# Коледино (атака 20.07 без остановки работы) намеренно НЕ здесь: удара нет в strikes.json,
# метка «поражён» на работающем складе противоречила бы слою ударов.
HITS = {
    ("wb", "Котовск"): {
        "date": "2026-07-18", "damage": "burned",
        "note": "Пожар после удара БПЛА, работа остановлена",
        "source_url": "https://lenta.ru/articles/2026/07/21/ataka-na-sklady-wildberries-v-iyule-2026-goda/",
    },
    ("wb", "Электросталь"): {
        "date": "2026-07-18", "damage": "burned",
        "note": "Крупный пожар после удара БПЛА, локализован 20 июля",
        "source_url": "https://www.vedomosti.ru/society/news/2026/07/21/1215463-pozhar-wildberries",
    },
    ("wb", "Краснодар"): {
        "date": "2026-07-22", "damage": "burned",
        "note": "Пожар после удара БПЛА, работа приостановлена",
        "source_url": "https://www.vedomosti.ru/society/articles/2026/07/22/1215535-ob-atake-dronov",
    },
    ("wb", "Невинномысск"): {
        "date": "2026-07-22", "damage": "burned",
        "note": "Пожар после удара БПЛА, работа приостановлена, режим ЧС локального уровня",
        "source_url": "https://www.vedomosti.ru/society/articles/2026/07/22/1215535-ob-atake-dronov",
    },
}

# Справочные цифры для статьи — из публичных заявлений компаний, начало 2026.
NETWORK = {
    "wb": {"complexes": 200, "area_m2": 5200000,
           "source_url": "https://mpagency.ru/blog/adresa-skladov-wildberries-v-rossii-2026/"},
    "ozon": {"fulfillment": 51, "sorting": 170, "area_m2": 4200000,
             "source_url": "https://www.cnews.ru/news/line/2026-06-05_ozon_planiruet_otkryt_v_rossii"},
}


def strike_keys():
    """(город, дата) всех ударов из strikes.json — источник правды по поражениям."""
    try:
        with open(os.path.join(ROOT, "data", "strikes.json"), encoding="utf8") as f:
            doc = json.load(f)
    except Exception:
        return None
    arr = doc if isinstance(doc, list) else doc.get("strikes", [])
    return {(str(s.get("city", "")).lower(), str(s.get("date", ""))) for s in arr}


def load_cache():
    try:
        with open(CACHE, encoding="utf8") as f:
            return json.load(f)
    except Exception:
        return {}


def geocode(query, cache, offline=False):
    """Адрес -> (lat, lon). Кэш на диске, чтобы точки не «плавали» между прогонами."""
    if query in cache:
        return cache[query]
    if offline:
        return None
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 1, "countrycodes": "ru"})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            js = json.load(r)
    except Exception as e:
        print("  geocode FAIL %-50s %s" % (query[:50], e))
        return None
    time.sleep(1.5)                      # политика Nominatim — не чаще 1 запроса в секунду
    if not js:
        return None
    hit = [round(float(js[0]["lat"]), 5), round(float(js[0]["lon"]), 5)]
    cache[query] = hit
    return hit


def build(offline=False):
    cache = load_cache()
    items, missing = [], []
    for op, rows in (("wb", WB), ("ozon", OZON)):
        for name, region, addr in rows:
            # Nominatim часто не знает промзоны и логопарки по полному адресу — откатываемся
            # на «населённый пункт + регион». На обзорной карте страны такой точки достаточно,
            # а пустая координата выкинула бы склад с карты совсем.
            base = name.split("(")[0].strip()
            ll = (geocode(addr + ", Россия", cache, offline)
                  or geocode(base + ", " + region + ", Россия", cache, offline))
            if not ll:
                missing.append("%s / %s" % (op, name))
                continue
            hit = HITS.get((op, name))
            it = {
                "id": "%s-%s" % (op, name.lower().replace(" ", "-").replace("(", "").replace(")", "")),
                "operator": op,
                "name": name,
                "region": region,
                "address": addr,
                "type": "rc" if op == "wb" else "ffc",
                "lat": ll[0], "lon": ll[1],
                "status": "hit" if hit else "ok",
            }
            if hit:
                it.update(hit)
            items.append(it)
    with open(CACHE, "w", encoding="utf8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)
    return items, missing


def main():
    offline = "--check" in sys.argv
    items, missing = build(offline)
    hits = [i for i in items if i["status"] == "hit"]
    burned = [i for i in hits if i.get("damage") == "burned"]
    # HITS без объекта в списке складов = опечатка в ключе, метка молча пропала бы с карты
    known = {(i["operator"], i["name"]) for i in items}
    orphan = [k for k in HITS if k not in known]
    if orphan:
        print("ОШИБКА: удары без склада в списке: %s" % orphan)
        return 1
    # Поражения обязаны иметь удар в strikes.json — иначе слой складов и слой ударов
    # разъедутся и карта начнёт противоречить сама себе.
    sk = strike_keys()
    if sk is not None:
        drift = [i["name"] for i in hits
                 if (i["name"].split("(")[0].strip().lower(), i.get("date", "")) not in sk]
        if drift:
            print("ВНИМАНИЕ: нет удара в strikes.json для: %s" % ", ".join(drift))
    doc = {
        "meta": {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scope": "Крупные распределительные центры Wildberries и фулфилмент-центры Ozon. "
                     "Отметка поражения — только удары БПЛА и ракет.",
            "geocoder": "Nominatim / OpenStreetMap (ODbL)",
            "network": NETWORK,
            "counts": {"total": len(items), "hit": len(hits), "burned": len(burned)},
        },
        "warehouses": sorted(items, key=lambda i: (i["operator"], i["name"])),
    }
    with open(OUT, "w", encoding="utf8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("warehouses: %d объектов (WB %d, Ozon %d), поражено %d, из них сгорело %d"
          % (len(items), sum(1 for i in items if i["operator"] == "wb"),
             sum(1 for i in items if i["operator"] == "ozon"), len(hits), len(burned)))
    if missing:
        print("не геокодировано (%d): %s" % (len(missing), ", ".join(missing)))
    return 0


def demo():
    """Самопроверка без сети: удар цепляется к складу, сирота в HITS ловится."""
    cache = {"Коледино, ул. Троицкая, 20, Россия": [55.4, 37.5]}
    ll = geocode("Коледино, ул. Троицкая, 20, Россия", cache, offline=True)
    assert ll == [55.4, 37.5], ll
    assert geocode("нет в кэше", cache, offline=True) is None
    assert HITS[("wb", "Котовск")]["damage"] == "burned"
    names = {(op, n) for op, rows in (("wb", WB), ("ozon", OZON)) for n, _, _ in rows}
    assert not [k for k in HITS if k not in names], "удар указывает на несуществующий склад"
    assert all(h["source_url"].startswith("https://") for h in HITS.values())
    print("demo OK")


if __name__ == "__main__":
    sys.exit(demo() if "--demo" in sys.argv else main())
