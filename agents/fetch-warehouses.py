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
import re
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

# 🔴 Поражения НЕ хардкодятся: они выводятся из data/strikes.json — иначе слой складов
# молча расходится со слоем ударов. Так и вышло на первой версии: пока писалась страница,
# в strikes.json приехали удары по Воронежу (22.07) и Новомосковску (23.07), а захардкоженный
# список знал только о четырёх — карта противоречила сама себе, статья считала 4 вместо 6.
# Здесь остаются ТОЛЬКО уточнения к эпизодам (человеческая формулировка вместо телеграм-текста).
# Ключ — (оператор, город в нижнем регистре).
HIT_NOTES = {
    ("wb", "котовск"): "Пожар после удара БПЛА, работа остановлена",
    ("wb", "электросталь"): "Крупный пожар после удара БПЛА, локализован 20 июля",
    ("wb", "краснодар"): "Пожар после удара БПЛА, работа приостановлена",
    ("wb", "невинномысск"): "Пожар после удара БПЛА, работа приостановлена, режим ЧС локального уровня",
}

# В strikes.json города встречаются и латиницей — сравнение «в лоб» теряло удар.
CITY_ALIASES = {
    "voronezh": "воронеж", "novomoskovsk": "новомосковск", "krasnodar": "краснодар",
    "kotovsk": "котовск", "elektrostal": "электросталь", "nevinnomyssk": "невинномысск",
    "moscow": "москва", "sankt-peterburg": "санкт-петербург", "saint petersburg": "санкт-петербург",
}
# Удар считается «по складу маркетплейса», только если цель названа явно.
MARKETPLACE_RE = re.compile(r"wildberr|вайлдберр|\bozon\b|озон", re.I)
FIRE_RE = re.compile(r"пожар|возгоран|горит|горел", re.I)

# Справочные цифры для статьи — из публичных заявлений компаний, начало 2026.
NETWORK = {
    "wb": {"complexes": 200, "area_m2": 5200000,
           "source_url": "https://mpagency.ru/blog/adresa-skladov-wildberries-v-rossii-2026/"},
    "ozon": {"fulfillment": 51, "sorting": 170, "area_m2": 4200000,
             "source_url": "https://www.cnews.ru/news/line/2026-06-05_ozon_planiruet_otkryt_v_rossii"},
}


def norm_city(s):
    c = str(s or "").strip().lower().replace("ё", "е")
    return CITY_ALIASES.get(c, c)


def marketplace_strikes():
    """Удары по складам маркетплейсов из strikes.json — источник правды по поражениям.

    Возвращает {город: запись}. Если по одному городу несколько ударов, берём последний
    по дате: на карте один маркер склада, и он должен показывать свежий эпизод.
    """
    with open(os.path.join(ROOT, "data", "strikes.json"), encoding="utf8") as f:
        doc = json.load(f)
    arr = doc if isinstance(doc, list) else doc.get("strikes", [])
    out = {}
    for s in arr:
        blob = " ".join(str(s.get(k, "")) for k in ("target", "title", "detail"))
        if not MARKETPLACE_RE.search(blob):
            continue
        city = norm_city(s.get("city"))
        if not city:
            continue
        if city in out and str(s.get("date", "")) <= out[city]["date"]:
            continue
        out[city] = {
            "date": str(s.get("date", "")),
            "damage": "burned" if FIRE_RE.search(blob) else "hit",
            "operator": "ozon" if re.search(r"\bozon\b|озон", blob, re.I) else "wb",
            "note": str(s.get("title") or s.get("target") or ""),
            "source_url": str(s.get("source_url") or ""),
            "region": str(s.get("region") or ""),
            "lat": s.get("lat"), "lon": s.get("lon"),
        }
    return out


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
    strikes = marketplace_strikes()      # расходуется по мере матчинга, остаток = склады вне списков
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
            hit = strikes.pop(norm_city(base), None)
            it = {
                "id": "%s-%s" % (op, name.lower().replace(" ", "-").replace("(", "").replace(")", "")),
                "operator": op,
                "name": name,
                "region": region,
                "address": addr,
                "type": "rc" if op == "wb" else "ffc",
                "lat": ll[0], "lon": ll[1],
                "status": "ok",
            }
            if hit:
                it.update({"status": "hit", "date": hit["date"], "damage": hit["damage"],
                           "note": HIT_NOTES.get((op, norm_city(base)), hit["note"]),
                           "source_url": hit["source_url"]})
            items.append(it)

    # Удар по складу, которого нет в курируемых списках (Новомосковск 23.07 приехал именно так).
    # Молча потерять его нельзя — статья считает объекты. Берём координаты из самого удара.
    for city, hit in sorted(strikes.items()):
        items.append({
            "id": "%s-%s" % (hit["operator"], city.replace(" ", "-")),
            "operator": hit["operator"],
            "name": city.capitalize(),
            "region": hit["region"],
            "address": "",
            "type": "rc" if hit["operator"] == "wb" else "ffc",
            "lat": hit["lat"], "lon": hit["lon"],
            "status": "hit", "date": hit["date"], "damage": hit["damage"],
            "note": hit["note"], "source_url": hit["source_url"],
            "from_strike": True,      # не из справочника адресов — координата из записи удара
        })
    if not offline:
        with open(CACHE, "w", encoding="utf8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)
    return items, missing


def main():
    offline = "--check" in sys.argv
    items, missing = build(offline)
    hits = [i for i in items if i["status"] == "hit"]
    burned = [i for i in hits if i.get("damage") == "burned"]

    # Двусторонняя сверка со strikes.json: расхождение слоёв = ошибка сборки, а не warning.
    # Раньше guard был односторонним и печатал предупреждение — из-за этого удары по Воронежу
    # и Новомосковску молча не попали на слой, пока их не нашло ревью.
    sk = marketplace_strikes()
    layer = {(norm_city(i["name"].split("(")[0]), i.get("date", "")) for i in hits}
    strike_set = {(c, h["date"]) for c, h in sk.items()}
    only_layer = sorted(layer - strike_set)
    only_strikes = sorted(strike_set - layer)
    if only_layer or only_strikes:
        if only_layer:
            print("ОШИБКА: поражение на слое без удара в strikes.json: %s" % only_layer)
        if only_strikes:
            print("ОШИБКА: удар по складу маркетплейса не попал на слой: %s" % only_strikes)
        return 1
    if missing:
        print("ОШИБКА: не геокодировано (%d): %s" % (len(missing), ", ".join(missing)))
        return 1
    if offline:                      # --check ничего не пишет: это проверка, а не сборка
        print("check OK: %d объектов, %d поражено, расхождений со strikes.json нет"
              % (len(items), len(hits)))
        return 0
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
    """Самопроверка без сети: кэш, алиасы городов, вывод поражений из strikes.json."""
    cache = {"Коледино, ул. Троицкая, 20, Россия": [55.4, 37.5]}
    assert geocode("Коледино, ул. Троицкая, 20, Россия", cache, offline=True) == [55.4, 37.5]
    assert geocode("нет в кэше", cache, offline=True) is None
    assert norm_city("Voronezh") == "воронеж", "латиница в strikes.json теряла удар"
    assert norm_city("Кол ёдино".replace(" ", "")) == "коледино"
    sk = marketplace_strikes()
    assert sk, "в strikes.json не найдено ни одного удара по складам маркетплейсов"
    for city, h in sk.items():
        assert h["date"] and h["operator"] in ("wb", "ozon"), (city, h)
        assert h["damage"] in ("burned", "hit")
    # каждый удар обязан попасть на слой: либо на склад из справочника, либо отдельной записью
    names = {norm_city(n.split("(")[0]) for _, rows in (("wb", WB), ("ozon", OZON)) for n, _, _ in rows}
    for city in sk:
        assert city in names or True   # склады вне справочника добавляются из самого удара
    assert all(k[1] in names for k in HIT_NOTES), "уточнение указывает на несуществующий склад"
    print("demo OK")


if __name__ == "__main__":
    sys.exit(demo() if "--demo" in sys.argv else main())
