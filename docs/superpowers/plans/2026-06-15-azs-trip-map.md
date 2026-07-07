# Вкладка «⛽ АЗС» — карта заправок, наличие (green→red) и карта поездки — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить отдельную вкладку-карту АЗС (Центр+Юг+Крым) с реальными заправками из OSM, покрашенными зелёный→красный по наличию топлива, с комментариями людей и картой поездки (пресеты + кастомный A→B через OSRM).

**Architecture:** Статичный файл координат заправок из OSM (`azs-stations.json`, агент не трогает) джойнится на клиенте с маленьким живым файлом статусов сетей (`fuel-availability.json`, обновляет существующий агент) → цвет каждой точки. Новый таб `view-azs` со своей Leaflet-картой и кластеризацией, по образцу существующего таба КРЫМ. Карта поездки: пресет-коридоры из `azs-routes.json` + кастомный маршрут через бесплатные Nominatim (геокод) и OSRM (маршрут), станции в буфере ±5 км подсвечиваются.

**Tech Stack:** Vanilla ES5-JS в одном IIFE (`app.js`), Leaflet 1.9.4 + Leaflet.markercluster (unpkg, без сборки), Python 3 + shapely (разовая генерация OSM-файла), бесплатные API OSM Overpass / OSRM demo / Nominatim (без ключей).

**Замечание о верификации:** в проекте НЕТ JS-тест-раннера (статический сайт). «Тесты» здесь = (а) Python-валидатор JSON-схемы (`agents/validate-azs.py`, запускается реально), (б) браузерная проверка через preview-MCP (чистая консоль, точки рендерятся, маршрут строится, попап с отзывом открывается). Это соответствует тому, как проект уже верифицируется (`agents/run-agent.sh` валидирует все `data/*.json`).

**Workflow репо:** только ветка `main` (фронт читает `data/*.json` из GitHub raw, push → видно без редеплоя). Коммиты — на main, как у всех агент-рутин проекта. Push на прод — только после браузерной верификации (Task 10).

---

## File Structure

| Файл | Действие | Ответственность |
|---|---|---|
| `agents/refresh-osm-stations.py` | Create | Разовая генерация `azs-stations.json` из Overpass (fetch → нормализация бренда → PIP-регион → запись) |
| `data/azs-stations.json` | Create (генерится) | Статичные координаты+бренд+регион заправок |
| `data/azs-routes.json` | Create | Пресет-коридоры поездок |
| `agents/validate-azs.py` | Create | Валидатор схемы новых JSON (для CI/руки/run-agent) |
| `index.html` | Modify | Кнопка таба + `section#view-azs` + `<script>` markercluster |
| `styles.css` | Modify | Лейаут `view-azs`, пины, панель фильтров/поездки, лента комментов |
| `app.js` | Modify | FILES+S, ленивый init таба+карты, рендер станций+join, комменты, планировщик поездки |
| `agents/update-prompt-availability.md` | Modify | Поле `networks[].level`, покрытие городов Центр+Юг+Крым |
| `agents/update-prompt-voices.md` | Modify | Привязка отзывов к городам Центр+Юг+Крым |
| `sources.html` | Modify | Атрибуция OSM/OSRM/Nominatim + плашка «наличие = оценка» |

---

## Task 1: OSM-генератор и `data/azs-stations.json`

**Files:**
- Create: `agents/refresh-osm-stations.py`
- Create (output): `data/azs-stations.json`

- [ ] **Step 1: Установить зависимости**

Run:
```bash
pip3 install --quiet shapely requests
```
Expected: успешная установка (или «already satisfied»).

- [ ] **Step 2: Проверить ключ имени региона в geojson**

Run:
```bash
cd ~/Documents/npz-tactical-map && python3 -c "import json;d=json.load(open('data/russia-regions.geojson'));print(list(d['features'][0]['properties'].keys()));print(d['features'][0]['properties'])"
```
Expected: видим, как называется поле имени (ожидается `name`; если иначе — подставить в Step 3 переменную `NAME_KEY`).

- [ ] **Step 3: Написать генератор**

Create `agents/refresh-osm-stations.py`:
```python
#!/usr/bin/env python3
"""Разовая/редкая генерация data/azs-stations.json из OpenStreetMap (Overpass).
Координаты+бренды реальные (OSM, ODbL). Регион проставляется point-in-polygon.
Агент-рутина этот файл НЕ трогает — он статичный."""
import json, os, sys, time, requests
from shapely.geometry import shape, Point
from shapely.prepared import prep

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVERPASS = "https://overpass-api.de/api/interpreter"
NAME_KEY = "name"  # см. Task1 Step2; поправить при необходимости

# (south, west, north, east)
BBOXES = {
    "Центр": (50.0, 30.0, 58.5, 43.0),
    "Юг":    (43.5, 37.0, 51.0, 48.5),
    "Крым":  (44.3, 32.4, 46.3, 36.7),
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
    ("еka", "eka", "ЕКА"), ("ека", "eka", "ЕКА"),
    ("трасса", "trassa", "Трасса"),
    ("нефтьмагистраль", "neftmag", "Нефтьмагистраль"), ("нефтемагистраль", "neftmag", "Нефтьмагистраль"),
    ("ннк", "nnk", "ННК"),
    ("газпром", "gazprom", "Газпром"),  # после газпромнефть!
]

def norm_brand(tags):
    raw = (tags.get("brand") or tags.get("operator") or tags.get("name") or "").strip()
    low = raw.lower()
    for sub, key, label in BRAND_RULES:
        if sub in low:
            return key, label
    return "other", (raw if raw else "АЗС")

def fetch_bbox(s, w, n, e):
    q = f'[out:json][timeout:180];node["amenity"="fuel"]({s},{w},{n},{e});out body;'
    for attempt in range(3):
        r = requests.post(OVERPASS, data={"data": q}, timeout=200)
        if r.status_code == 200:
            return r.json().get("elements", [])
        time.sleep(15)
    raise RuntimeError(f"Overpass failed for bbox {(s,w,n,e)}: {r.status_code}")

def load_regions():
    feats = []
    for fn in ["russia-regions.geojson", "crimea-regions.geojson", "new-territories.geojson"]:
        p = os.path.join(ROOT, "data", fn)
        if not os.path.exists(p):
            continue
        gj = json.load(open(p, encoding="utf-8"))
        for f in gj.get("features", []):
            nm = f.get("properties", {}).get(NAME_KEY) or f.get("properties", {}).get("name")
            if not nm:
                continue
            try:
                geom = shape(f["geometry"])
                feats.append((nm, prep(geom), geom))
            except Exception:
                pass
    return feats

def region_of(lat, lon, regions):
    pt = Point(lon, lat)
    for nm, pgeom, _ in regions:
        if pgeom.contains(pt):
            return nm
    return None

def main():
    regions = load_regions()
    print(f"regions loaded: {len(regions)}", file=sys.stderr)
    seen, stations = set(), []
    for label, bbox in BBOXES.items():
        els = fetch_bbox(*bbox)
        print(f"{label}: {len(els)} fuel nodes", file=sys.stderr)
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
                "id": f"osm-{oid}",
                "brand": key,
                "brand_label": blabel,
                "lat": round(lat, 5),
                "lon": round(lon, 5),
                "city": tags.get("addr:city"),
                "region": reg,
                "addr": tags.get("addr:street"),
            })
        time.sleep(3)
    branded = sum(1 for s in stations if s["brand"] != "other")
    out = {
        "meta": {
            "generated_at": time.strftime("%Y-%m-%d"),
            "source": "OpenStreetMap / Overpass API (ODbL)",
            "regions": list(BBOXES.keys()),
            "count": len(stations),
            "branded": branded,
            "note": "Координаты и бренды — реальные (OSM). Наличие топлива — оценка по статусу сети в регионе, не по конкретной колонке.",
        },
        "stations": stations,
    }
    p = os.path.join(ROOT, "data", "azs-stations.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"WROTE {p}: {len(stations)} stations ({branded} branded)")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Запустить генератор**

Run:
```bash
cd ~/Documents/npz-tactical-map && python3 agents/refresh-osm-stations.py
```
Expected: stderr печатает счётчики по bbox; финал `WROTE .../data/azs-stations.json: N stations (M branded)` где N>500, M>100. Если N огромен (>8000) или файл >2МБ — в Step 5 включить отсечение `other`.

- [ ] **Step 5: Проверить размер и распределение; при необходимости отсечь шум**

Run:
```bash
cd ~/Documents/npz-tactical-map && ls -lh data/azs-stations.json && python3 -c "import json,collections;d=json.load(open('data/azs-stations.json'));print('count',d['meta']['count'],'branded',d['meta']['branded']);print('by brand',collections.Counter(s['brand'] for s in d['stations']).most_common(12));print('by region(top)',collections.Counter(s['region'] for s in d['stations']).most_common(8))"
```
Expected: размер < ~2МБ, видно покрытие брендов (lukoil/gazpromneft/rosneft/atan/tes присутствуют) и регионов (Краснодарский край, Республика Крым, Москва/МО, Ростовская и т.д.).
Если файл > 2МБ: в `main()` перед записью добавить строку, оставляющую все branded + не более 1500 случайных `other`:
```python
    others = [s for s in stations if s["brand"] == "other"]
    keep = [s for s in stations if s["brand"] != "other"] + others[:1500]
    stations = keep
```
и перегенерировать (Step 4).

- [ ] **Step 6: Commit**

```bash
git -C ~/Documents/npz-tactical-map add agents/refresh-osm-stations.py data/azs-stations.json
git -C ~/Documents/npz-tactical-map commit -m "feat(azs): OSM station extractor + data/azs-stations.json (Центр+Юг+Крым)"
```

---

## Task 2: Пресет-коридоры `data/azs-routes.json`

**Files:**
- Create: `data/azs-routes.json`

- [ ] **Step 1: Создать файл**

Create `data/azs-routes.json`:
```json
{
  "meta": {
    "generated_at": "2026-06-15",
    "note": "Пресет-коридоры для карты поездки. Геометрия схематичная по ключевым городам; кастомный маршрут строится через OSRM."
  },
  "routes": [
    {
      "id": "m4-don",
      "name": "М4 «Дон»: Москва → Краснодар → Крым",
      "waypoints": [[55.7558,37.6173],[54.1930,37.6173],[52.6031,39.5708],[51.6608,39.2003],[47.2357,39.7015],[45.0448,38.9760],[45.0500,34.1000]],
      "cities": ["Москва","Тула","Липецк","Воронеж","Ростов-на-Дону","Краснодар","Симферополь"]
    },
    {
      "id": "tavrida",
      "name": "«Таврида»: Керчь → Симферополь → Севастополь",
      "waypoints": [[45.3530,36.4750],[45.0500,34.1000],[44.6166,33.5254]],
      "cities": ["Керчь","Симферополь","Севастополь"]
    },
    {
      "id": "m4-south",
      "name": "Юг: Ростов → Краснодар → Сочи",
      "waypoints": [[47.2357,39.7015],[45.0448,38.9760],[43.5855,39.7231]],
      "cities": ["Ростов-на-Дону","Краснодар","Сочи"]
    },
    {
      "id": "volga-south",
      "name": "Поволжье→Юг: Волгоград → Ростов",
      "waypoints": [[48.7080,44.5133],[47.2357,39.7015]],
      "cities": ["Волгоград","Ростов-на-Дону"]
    }
  ]
}
```

- [ ] **Step 2: Валидировать JSON**

Run:
```bash
cd ~/Documents/npz-tactical-map && python3 -c "import json;d=json.load(open('data/azs-routes.json'));print('routes',len(d['routes']));[print(r['id'],len(r['waypoints']),'wp') for r in d['routes']]"
```
Expected: `routes 4`, у каждого ≥2 waypoints.

- [ ] **Step 3: Commit**

```bash
git -C ~/Documents/npz-tactical-map add data/azs-routes.json
git -C ~/Documents/npz-tactical-map commit -m "feat(azs): preset trip corridors data/azs-routes.json"
```

---

## Task 3: HTML — таб, секция, markercluster

**Files:**
- Modify: `index.html` (nav `#tabs`; новая `section`; `<head>` + перед `app.js`)

- [ ] **Step 1: Добавить кнопку таба после КРЫМ**

В `index.html`, найти строку с табом crimea:
```html
        <button data-view="crimea"><span class="tab-ico">⚠</span><span class="tab-lbl">КРЫМ</span></button>
```
Добавить сразу ПОСЛЕ неё:
```html
        <button data-view="azs"><span class="tab-ico">⛽</span><span class="tab-lbl">АЗС</span></button>
```

- [ ] **Step 2: Добавить секцию `view-azs` после секции `view-crimea`**

Найти конец секции Крыма:
```html
    <!-- ===== VIEW: CRIMEA ===== -->
    <section class="view" id="view-crimea">
      <div id="mapCrimea" class="map"></div>
      <aside class="card card-left wide" id="crimeaPanel">
        <div class="card-h crit">КРЫМ · ОТДЕЛЬНЫЙ ТВД</div>
        <div class="card-b" id="crimeaBody"></div>
      </aside>
    </section>
```
Добавить сразу ПОСЛЕ неё:
```html
    <!-- ===== VIEW: AZS ===== -->
    <section class="view" id="view-azs">
      <div id="mapAzs" class="map"></div>

      <aside class="card card-left azs-ctl" id="azsPanel">
        <div class="card-h">⛽ ЗАПРАВКИ <span class="count" id="azsCount"></span></div>
        <div class="azs-note" id="azsNote">Расположение — реальное (OSM). Наличие — оценка по сети/региону, не по колонке.</div>

        <div class="azs-block">
          <div class="azs-block-h">🚗 Карта поездки</div>
          <div class="azs-presets" id="azsPresets"></div>
          <div class="azs-ab">
            <input type="text" id="azsFrom" placeholder="Откуда (город)" autocomplete="off">
            <input type="text" id="azsTo" placeholder="Куда (город)" autocomplete="off">
            <button id="azsRouteBtn">Маршрут</button>
            <button id="azsRouteClear" title="Сбросить">✕</button>
          </div>
          <div class="azs-trip" id="azsTrip"></div>
        </div>

        <div class="azs-block">
          <div class="azs-block-h">Фильтр сети</div>
          <div class="azs-brands" id="azsBrands"></div>
        </div>

        <div class="azs-legend" id="azsLegend"></div>
      </aside>

      <aside class="card card-right" id="azsCommentsCard">
        <div class="card-h">🗣 КОММЕНТАРИИ <span class="count" id="azsCommentsCount"></span></div>
        <div class="voices" id="azsComments"></div>
      </aside>
    </section>
```

- [ ] **Step 3: Подключить Leaflet.markercluster**

В `<head>`, сразу после строки Leaflet CSS (`leaflet@1.9.4/dist/leaflet.css`), добавить:
```html
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css">
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css">
```
И перед `<script src="app.js"></script>`, после строки Leaflet JS, добавить:
```html
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
```

- [ ] **Step 4: Проверить разметку**

Run:
```bash
cd ~/Documents/npz-tactical-map && grep -c 'data-view="azs"' index.html && grep -c 'id="view-azs"' index.html && grep -c 'markercluster' index.html
```
Expected: `1`, `1`, `2` (один JS + matched через grep по подстроке; если markercluster встретился 3 раза — это 2 css + 1 js, тоже ок, ≥2).

- [ ] **Step 5: Commit**

```bash
git -C ~/Documents/npz-tactical-map add index.html
git -C ~/Documents/npz-tactical-map commit -m "feat(azs): AZS tab markup + markercluster (index.html)"
```

---

## Task 4: CSS для вкладки АЗС

**Files:**
- Modify: `styles.css` (добавить в конец)

- [ ] **Step 1: Добавить стили**

В конец `styles.css` дописать:
```css
/* ===== AZS TAB ===== */
#view-azs { position: relative; }
.azs-ctl { max-width: 320px; }
.azs-note { font-size: 11px; line-height: 1.4; opacity: .75; margin: 6px 0 10px; border-left: 3px solid var(--accent, #e0b020); padding-left: 8px; }
.azs-block { margin: 12px 0; border-top: 1px solid rgba(127,127,127,.2); padding-top: 10px; }
.azs-block-h { font-weight: 700; font-size: 13px; margin-bottom: 8px; letter-spacing: .03em; }
.azs-presets { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }
.azs-presets button { text-align: left; font: inherit; font-size: 12px; padding: 6px 8px; border: 1px solid rgba(127,127,127,.3); border-radius: 6px; background: transparent; color: inherit; cursor: pointer; }
.azs-presets button:hover, .azs-presets button.active { border-color: var(--accent, #e0b020); background: rgba(224,176,32,.12); }
.azs-ab { display: grid; grid-template-columns: 1fr auto; gap: 4px; }
.azs-ab input { grid-column: 1 / 2; font: inherit; font-size: 12px; padding: 6px 8px; border: 1px solid rgba(127,127,127,.3); border-radius: 6px; background: transparent; color: inherit; }
.azs-ab #azsRouteBtn { grid-column: 2; grid-row: 1 / 3; padding: 0 10px; cursor: pointer; border-radius: 6px; border: 1px solid var(--accent, #e0b020); background: rgba(224,176,32,.15); color: inherit; font: inherit; font-size: 12px; }
.azs-ab #azsRouteClear { grid-column: 2; grid-row: 3; cursor: pointer; border-radius: 6px; border: 1px solid rgba(127,127,127,.3); background: transparent; color: inherit; }
.azs-trip { font-size: 12px; line-height: 1.5; margin-top: 8px; }
.azs-trip .tr-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }
.azs-trip .tr-chip { padding: 2px 6px; border-radius: 4px; font-weight: 700; font-size: 11px; }
.azs-brands { display: flex; flex-wrap: wrap; gap: 4px; }
.azs-brands label { display: inline-flex; align-items: center; gap: 3px; font-size: 11px; padding: 3px 6px; border: 1px solid rgba(127,127,127,.3); border-radius: 999px; cursor: pointer; }
.azs-legend { display: flex; flex-direction: column; gap: 3px; font-size: 11px; margin-top: 10px; }
.azs-legend i { display: inline-block; width: 11px; height: 11px; border-radius: 3px; margin-right: 6px; vertical-align: middle; }
.azs-pop .ap-brand { font-weight: 800; font-size: 14px; }
.azs-pop .ap-status { font-weight: 700; padding: 1px 6px; border-radius: 4px; color: #fff; font-size: 11px; }
.azs-pop .ap-row { font-size: 12px; margin: 3px 0; }
.azs-pop .ap-quote { font-style: italic; opacity: .85; font-size: 12px; border-left: 2px solid rgba(127,127,127,.4); padding-left: 6px; margin-top: 5px; }
.azs-route-line { }
@media (max-width: 780px) { .azs-ctl { max-width: 100%; } }
```

- [ ] **Step 2: Проверить, что CSS-правила добавлены**

Run:
```bash
cd ~/Documents/npz-tactical-map && grep -c '.azs-ctl\|.azs-presets\|.azs-pop' styles.css
```
Expected: ≥3.

- [ ] **Step 3: Commit**

```bash
git -C ~/Documents/npz-tactical-map add styles.css
git -C ~/Documents/npz-tactical-map commit -m "feat(azs): styles for AZS tab (panel, presets, popup, legend)"
```

---

## Task 5: app.js — загрузка данных + ленивый init таба и карты

**Files:**
- Modify: `app.js` (FILES объект; S объект; `maps`/слой-холдеры; Promise.all; initTabs; новые функции)

- [ ] **Step 1: Зарегистрировать файлы данных**

В `app.js`, в объекте `FILES` (около строки 6), после `grid: "data/grid-state.json"` добавить запятую и строки:
```javascript
    grid: "data/grid-state.json",
    azsStations: "data/azs-stations.json",
    azsRoutes: "data/azs-routes.json"
```
(убедиться, что у предыдущей строки `grid` есть завершающая запятая)

- [ ] **Step 2: Завести поля состояния**

Заменить строку определения `S` (около строки 18) на:
```javascript
  var S = { state: null, hist: null, forecast: null, economy: null, strikes: null, roads: null, availability: null, voices: null, grid: null, regionsGeo: null, outlineGeo: null, azsStations: null, azsRoutes: null };
```
И заменить строку `var maps = { ru: null, cr: null };` на:
```javascript
  var maps = { ru: null, cr: null, az: null };
```
И заменить `var L_ru = {}, L_cr = {};` на:
```javascript
  var L_ru = {}, L_cr = {}, L_az = {};
```
И в строке с `crimeaReady = false;` добавить флаг АЗС — заменить:
```javascript
  var nextSyncAt = 0, refreshTimer = null, regionMode = "now", crimeaReady = false;
```
на:
```javascript
  var nextSyncAt = 0, refreshTimer = null, regionMode = "now", crimeaReady = false, azsReady = false;
  var AZS_ROUTE = { layer: null, stationsHi: [] };
```

- [ ] **Step 3: Подгрузить новые файлы в Promise.all**

Найти блок загрузки (около строки 182), добавить два fetch в массив `Promise.all([...])` (после `fetchData("grid").catch(...)`):
```javascript
, fetchData("azsStations").catch(function () { return null; }), fetchData("azsRoutes").catch(function () { return null; })
```
И в `.then(function (res) {` расширить присвоение (после `S.grid = res[8];`):
```javascript
        S.azsStations = res[9]; S.azsRoutes = res[10];
```

- [ ] **Step 4: Ленивый init таба в initTabs**

В функции `initTabs` (строка ~861), в обработчике клика, после строки про crimea:
```javascript
        if (view === "crimea") { if (!crimeaReady) { initCrMap(); renderCrimea(); } setTimeout(function () { maps.cr.invalidateSize(); }, 60); }
```
добавить:
```javascript
        if (view === "azs") { if (!azsReady) { initAzMap(); renderAzsTab(); } setTimeout(function () { maps.az.invalidateSize(); }, 60); }
```

- [ ] **Step 5: Функция инициализации карты АЗС**

В `app.js` найти существующий блок `/* ---------- AZS (fuel availability) ---------- */` (строка ~692). Сразу ПЕРЕД ним вставить новый блок (карта таба + заглушки рендера, которые наполним в Task 6–8):
```javascript
  /* ---------- AZS TAB (separate map) ---------- */
  function initAzMap() {
    if (azsReady) return;
    maps.az = L.map("mapAzs", { center: [49.5, 39.5], zoom: 5, minZoom: 4, maxZoom: 14, worldCopyJump: false });
    setBaseTiles(maps.az);
    L_az.cluster = (L.markerClusterGroup ? L.markerClusterGroup({ maxClusterRadius: 45, chunkedLoading: true }) : L.layerGroup());
    L_az.cluster.addTo(maps.az);
    L_az.comments = L.layerGroup().addTo(maps.az);
    L_az.route = L.layerGroup().addTo(maps.az);
    azsReady = true;
  }
  function renderAzsTab() {
    renderAzsStations();
    renderAzsComments();
    renderAzsPresets();
    renderAzsBrandFilter();
    renderAzsLegend();
    bindAzsRouteUI();
  }
```

- [ ] **Step 6: Хелпер базового слоя (если ещё нет общего)**

Проверить, есть ли общий тайл-хелпер:
```bash
cd ~/Documents/npz-tactical-map && grep -n "function setBaseTiles\|tileLayer(" app.js | head
```
Если функции `setBaseTiles` НЕТ, посмотреть, как тайлы ставятся для `maps.cr` (около строки 169) и определить хелпер по тому же образцу. Вставить рядом с `initAzMap`:
```javascript
  function setBaseTiles(map) {
    var dark = document.documentElement.getAttribute("data-theme") === "dark";
    var url = dark
      ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
    L.tileLayer(url, { attribution: "© OpenStreetMap, © CARTO", maxZoom: 19 }).addTo(map);
  }
```
(Если общий хелпер уже есть — переиспользовать его и НЕ дублировать; в `initAzMap` вызвать существующий.)

- [ ] **Step 7: Временные заглушки рендеров (чтобы не падало до Task 6–8)**

Сразу после `renderAzsTab` добавить пустые заглушки (будут заменены в следующих тасках):
```javascript
  function renderAzsStations() {}
  function renderAzsComments() {}
  function renderAzsPresets() {}
  function renderAzsBrandFilter() {}
  function renderAzsLegend() {}
  function bindAzsRouteUI() {}
```

- [ ] **Step 8: Браузер-проверка каркаса**

Run preview (см. Task 10 Step 1 для запуска сервера, если ещё не запущен), затем:
- preview_eval: `document.querySelector('[data-view=azs]').click()`
- preview_console_logs → Expected: НЕТ ошибок; карта `#mapAzs` появилась (серое полотно с тайлами).
- preview_snapshot → Expected: видна вкладка АЗС, панель «ЗАПРАВКИ», карта.

- [ ] **Step 9: Commit**

```bash
git -C ~/Documents/npz-tactical-map add app.js
git -C ~/Documents/npz-tactical-map commit -m "feat(azs): lazy tab+map init, data wiring, render stubs"
```

---

## Task 6: app.js — рендер станций + join green→red + попап + фильтр

**Files:**
- Modify: `app.js` (заменить заглушки `renderAzsStations`, `renderAzsBrandFilter`, `renderAzsLegend`; добавить `stationLevel`, `azsStationIcon`, `azsStationPopup`, `azsState`)

- [ ] **Step 1: Состояние фильтра + join-функция уровня**

Заменить заглушку `function renderAzsStations() {}` на блок (реализация ниже по шагам). Сначала добавить рядом (над `renderAzsStations`) состояние и join:
```javascript
  var azsState = { brands: null, level: null }; // brands: Set активных ключей или null=все

  // status сети -> уровень шкалы (если у network нет поля level)
  var AZS_STATUS2LVL = { ok: "calm", normal: "calm", available: "calm", minor: "strained", some: "strained", limited: "limited", talony: "limited", severe: "severe", shortage: "severe", critical: "critical", dry: "critical", none: "critical" };

  function azsRegionEntry(regionName) {
    var a = S.availability; if (!a || !a.regions) return null;
    var target = normRegion(regionName);
    for (var i = 0; i < a.regions.length; i++) {
      if (normRegion(a.regions[i].region) === target) return a.regions[i];
    }
    return null;
  }
  function stationLevel(st) {
    var reg = azsRegionEntry(st.region);
    if (!reg) return "unknown";
    // ищем сеть по бренду внутри региона
    if (reg.networks && st.brand && st.brand !== "other") {
      for (var i = 0; i < reg.networks.length; i++) {
        var nw = reg.networks[i];
        if (brandMatchesNetwork(st, nw)) {
          if (nw.level && AZS_LVL[nw.level]) return nw.level;
          var lv = AZS_STATUS2LVL[(nw.status || "").toLowerCase()];
          if (lv) return lv;
          break;
        }
      }
    }
    return reg.level && AZS_LVL[reg.level] ? reg.level : "unknown";
  }
  function brandMatchesNetwork(st, nw) {
    var n = (nw.name || "").toLowerCase();
    var lbl = (st.brand_label || "").toLowerCase();
    if (!n || !lbl) return false;
    return n.indexOf(lbl) >= 0 || lbl.indexOf(n) >= 0;
  }
```

- [ ] **Step 2: Иконка и попап станции**

Добавить под join-функциями:
```javascript
  var AZS_UNKNOWN = "#7a7e85";
  function azsStationIcon(level, hi) {
    var c = AZS_LVL[level] || AZS_UNKNOWN;
    var ring = hi ? '<circle cx="9" cy="9" r="8" fill="none" stroke="#1b6ef3" stroke-width="2"/>' : "";
    var html = '<div class="azs-spin"><svg width="18" height="18" viewBox="0 0 18 18">' + ring +
      '<circle cx="9" cy="9" r="5.5" fill="' + c + '" stroke="#000" stroke-opacity=".35" stroke-width="1"/></svg></div>';
    return L.divIcon({ className: "azs-divicon", html: html, iconSize: [18, 18], iconAnchor: [9, 9] });
  }
  function nearestComments(st, max) {
    var v = (S.voices && S.voices.voices) || [], out = [];
    for (var i = 0; i < v.length && out.length < (max || 2); i++) {
      var q = v[i];
      if (!q.city) continue;
      if ((st.city && q.city && q.city === st.city) || normRegion(q.region || "") === normRegion(st.region)) out.push(q);
    }
    return out;
  }
  function azsStationPopup(st) {
    var lvl = stationLevel(st), c = AZS_LVL[lvl] || AZS_UNKNOWN, lbl = (AZS_LBL[lvl] || "нет данных").toUpperCase();
    var reg = azsRegionEntry(st.region);
    var html = '<div class="azs-pop"><div class="ap-brand">' + (st.brand_label || "АЗС") + '</div>';
    html += '<div class="ap-row"><span class="ap-status" style="background:' + c + '">' + lbl + '</span></div>';
    if (st.addr) html += '<div class="ap-row">📍 ' + st.addr + (st.city ? ", " + st.city : "") + '</div>';
    else if (st.city) html += '<div class="ap-row">📍 ' + st.city + '</div>';
    html += '<div class="ap-row" style="opacity:.7">Регион: ' + st.region + '</div>';
    if (reg) {
      if (reg.ai95_price_rub) html += '<div class="ap-row">АИ-95 ~' + reg.ai95_price_rub + ' ₽/л</div>';
      if (reg.queues_hours) html += '<div class="ap-row">Очередь ~' + reg.queues_hours + ' ч</div>';
    }
    var cm = nearestComments(st, 2);
    cm.forEach(function (q) { html += '<div class="ap-quote">«' + (q.quote || "").replace(/</g, "&lt;") + '»</div>'; });
    html += '<div class="ap-row" style="opacity:.55;font-size:10px;margin-top:5px">Наличие — оценка по сети/региону. Точка — OSM.</div></div>';
    return html;
  }
```

- [ ] **Step 3: Рендер станций в кластер с учётом фильтра**

Заменить заглушку `function renderAzsStations() {}` на:
```javascript
  function renderAzsStations() {
    if (!L_az.cluster) return;
    L_az.cluster.clearLayers();
    var st = (S.azsStations && S.azsStations.stations) || [];
    var shown = 0;
    st.forEach(function (s) {
      if (azsState.brands && !azsState.brands.has(s.brand)) return;
      var lvl = stationLevel(s);
      if (azsState.level && lvl !== azsState.level) return;
      var m = L.marker([s.lat, s.lon], { icon: azsStationIcon(lvl, false) });
      m.bindPopup(azsStationPopup(s));
      m._azs = s;
      L_az.cluster.addLayer(m);
      shown++;
    });
    var cnt = document.getElementById("azsCount"); if (cnt) cnt.textContent = shown;
  }
```

- [ ] **Step 4: Фильтр по сети + легенда**

Заменить заглушки `renderAzsBrandFilter` и `renderAzsLegend`:
```javascript
  function renderAzsBrandFilter() {
    var el = document.getElementById("azsBrands"); if (!el) return;
    var st = (S.azsStations && S.azsStations.stations) || [];
    var counts = {};
    st.forEach(function (s) { counts[s.brand] = counts[s.brand] || { label: s.brand_label, n: 0 }; counts[s.brand].n++; });
    var keys = Object.keys(counts).sort(function (a, b) { return counts[b].n - counts[a].n; });
    el.innerHTML = "";
    keys.forEach(function (k) {
      var lab = document.createElement("label");
      lab.innerHTML = '<input type="checkbox" checked data-brand="' + k + '"> ' + counts[k].label + ' (' + counts[k].n + ')';
      el.appendChild(lab);
    });
    Array.prototype.forEach.call(el.querySelectorAll("input"), function (inp) {
      inp.addEventListener("change", function () {
        var active = new Set();
        Array.prototype.forEach.call(el.querySelectorAll("input"), function (x) { if (x.checked) active.add(x.dataset.brand); });
        azsState.brands = (active.size === keys.length) ? null : active;
        renderAzsStations();
        if (AZS_ROUTE.layer) recomputeTripStations();
      });
    });
  }
  function renderAzsLegend() {
    var el = document.getElementById("azsLegend"); if (!el) return;
    var order = ["calm", "strained", "limited", "severe", "critical"];
    var html = "";
    order.forEach(function (k) { html += '<span><i style="background:' + AZS_LVL[k] + '"></i>' + AZS_LBL[k] + '</span>'; });
    html += '<span><i style="background:' + AZS_UNKNOWN + '"></i>нет данных</span>';
    el.innerHTML = html;
  }
```

- [ ] **Step 5: Браузер-проверка**

- preview_eval: `document.querySelector('[data-view=azs]').click()` → подождать
- preview_console_logs → Expected: без ошибок.
- preview_snapshot → Expected: на карте кластеры точек; в панели чекбоксы брендов с числами; легенда green→red + «нет данных»; счётчик ЗАПРАВКИ > 0.
- preview_eval: `document.querySelectorAll('#mapAzs .leaflet-marker-icon').length` → Expected: > 0 (точки/кластеры есть).
- preview_click по одной точке (зум-ин при необходимости) → попап с брендом/статусом/(возможно) отзывом.

- [ ] **Step 6: Commit**

```bash
git -C ~/Documents/npz-tactical-map add app.js
git -C ~/Documents/npz-tactical-map commit -m "feat(azs): station render + green→red join + popups + brand filter + legend"
```

---

## Task 7: app.js — комментарии (слой на карте + лента)

**Files:**
- Modify: `app.js` (заменить заглушку `renderAzsComments`)

- [ ] **Step 1: Реализовать комментарии**

Заменить `function renderAzsComments() {}` на:
```javascript
  function azsCommentPin() {
    return L.divIcon({ className: "azs-divicon", html: '<div class="voice-pin">🗣</div>', iconSize: [20, 20], iconAnchor: [10, 10] });
  }
  function renderAzsComments(filterCities) {
    var listEl = document.getElementById("azsComments");
    var v = (S.voices && S.voices.voices) || [];
    if (filterCities && filterCities.length) {
      v = v.filter(function (q) { return q.city && filterCities.indexOf(q.city) >= 0; });
    }
    var cnt = document.getElementById("azsCommentsCount"); if (cnt) cnt.textContent = v.length;
    // лента
    if (listEl) {
      listEl.innerHTML = "";
      v.slice(0, 60).forEach(function (q) {
        var d = document.createElement("div");
        d.className = "voice";
        d.innerHTML = '<div class="voice-meta">' + (q.date || "") + " · " + (q.city || q.region || "") + '</div>' +
          '<div class="voice-quote">«' + (q.quote || "").replace(/</g, "&lt;") + '»</div>' +
          (q.source_url ? '<a class="voice-src" href="' + q.source_url + '" target="_blank" rel="noopener">' + (q.source || "источник") + '</a>' : "");
        if (q.lat && q.lon) { d.style.cursor = "pointer"; d.addEventListener("click", function () { maps.az.setView([q.lat, q.lon], 9); }); }
        listEl.appendChild(d);
      });
    }
    // пины на карте
    if (L_az.comments) {
      L_az.comments.clearLayers();
      v.forEach(function (q) {
        if (!q.lat || !q.lon) return;
        L.marker([q.lat, q.lon], { icon: azsCommentPin(), zIndexOffset: 500 })
          .bindPopup('<div class="azs-pop"><div class="ap-row" style="opacity:.7">' + (q.city || q.region || "") + " · " + (q.date || "") + '</div><div class="ap-quote">«' + (q.quote || "").replace(/</g, "&lt;") + '»</div>' + (q.source_url ? '<div class="ap-row"><a href="' + q.source_url + '" target="_blank" rel="noopener">' + (q.source || "источник") + '</a></div>' : "") + '</div>')
          .addTo(L_az.comments);
      });
    }
  }
```

- [ ] **Step 2: CSS для пина комментария**

В `styles.css` дописать:
```css
.voice-pin { font-size: 14px; line-height: 20px; text-align: center; filter: drop-shadow(0 1px 1px rgba(0,0,0,.4)); }
```

- [ ] **Step 3: Браузер-проверка**

- preview_eval: `document.querySelector('[data-view=azs]').click()`
- preview_snapshot → Expected: справа лента «КОММЕНТАРИИ» с цитатами+датами+источниками; на карте пины 🗣.
- preview_console_logs → без ошибок.

- [ ] **Step 4: Commit**

```bash
git -C ~/Documents/npz-tactical-map add app.js styles.css
git -C ~/Documents/npz-tactical-map commit -m "feat(azs): comments layer on map + feed list"
```

---

## Task 8: app.js — карта поездки (пресеты + кастомный A→B через OSRM)

**Files:**
- Modify: `app.js` (заменить заглушки `renderAzsPresets`, `bindAzsRouteUI`; добавить геокод/маршрут/буфер/сводку)

- [ ] **Step 1: Геометрия-хелперы (haversine, точка-к-сегменту)**

Над `renderAzsPresets` добавить:
```javascript
  function haversineKm(a, b) {
    var R = 6371, dLat = (b[0] - a[0]) * Math.PI / 180, dLon = (b[1] - a[1]) * Math.PI / 180;
    var la1 = a[0] * Math.PI / 180, la2 = b[0] * Math.PI / 180;
    var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  function distToPolylineKm(pt, line) {
    var min = Infinity;
    for (var i = 0; i < line.length - 1; i++) {
      var d = distToSegKm(pt, line[i], line[i + 1]);
      if (d < min) min = d;
    }
    return min;
  }
  function distToSegKm(p, a, b) {
    // аппрокс. проекция в локальной плоскости (градусы→км)
    var kx = 111.32 * Math.cos(p[0] * Math.PI / 180), ky = 110.57;
    var ax = a[1] * kx, ay = a[0] * ky, bx = b[1] * kx, by = b[0] * ky, px = p[1] * kx, py = p[0] * ky;
    var dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
    var t = len2 ? ((px - ax) * dx + (py - ay) * dy) / len2 : 0;
    t = Math.max(0, Math.min(1, t));
    var cx = ax + t * dx, cy = ay + t * dy;
    return Math.sqrt((px - cx) * (px - cx) + (py - cy) * (py - cy));
  }
```

- [ ] **Step 2: Подсветка станций вдоль маршрута + сводка**

Добавить:
```javascript
  var TRIP_BUFFER_KM = 5;
  function applyTrip(lineLatLngs, cities) {
    AZS_ROUTE.line = lineLatLngs;
    AZS_ROUTE.cities = cities || [];
    if (L_az.route) {
      L_az.route.clearLayers();
      L.polyline(lineLatLngs, { color: "#1b6ef3", weight: 4, opacity: .8, className: "azs-route-line" }).addTo(L_az.route);
    }
    recomputeTripStations();
    renderAzsComments(AZS_ROUTE.cities.length ? AZS_ROUTE.cities : null);
    try { maps.az.fitBounds(L.polyline(lineLatLngs).getBounds().pad(0.2)); } catch (e) {}
  }
  function recomputeTripStations() {
    var st = (S.azsStations && S.azsStations.stations) || [];
    var line = AZS_ROUTE.line; if (!line) return;
    var along = [];
    st.forEach(function (s) {
      if (azsState.brands && !azsState.brands.has(s.brand)) return;
      if (distToPolylineKm([s.lat, s.lon], line) <= TRIP_BUFFER_KM) along.push(s);
    });
    var tally = { calm: 0, strained: 0, limited: 0, severe: 0, critical: 0, unknown: 0 };
    along.forEach(function (s) { tally[stationLevel(s)]++; });
    var ok = tally.calm + tally.strained, warn = tally.limited, bad = tally.severe + tally.critical;
    var el = document.getElementById("azsTrip");
    if (el) {
      el.innerHTML =
        '<div class="tr-row">Вдоль маршрута: <b>' + along.length + '</b> АЗС (буфер ' + TRIP_BUFFER_KM + ' км)</div>' +
        '<div class="tr-row">' +
        '<span class="tr-chip" style="background:' + AZS_LVL.calm + ';color:#fff">🟢 ' + ok + '</span>' +
        '<span class="tr-chip" style="background:' + AZS_LVL.limited + ';color:#000">🟡 ' + warn + '</span>' +
        '<span class="tr-chip" style="background:' + AZS_LVL.critical + ';color:#fff">🔴 ' + bad + '</span>' +
        '<span class="tr-chip" style="background:' + AZS_UNKNOWN + ';color:#fff">⚪ ' + tally.unknown + '</span>' +
        '</div>' +
        (bad > 0 ? '<div class="tr-row" style="color:' + AZS_LVL.critical + '">⚠ На маршруте есть участки острого дефицита — заправляйтесь заранее.</div>' : '<div class="tr-row" style="color:' + AZS_LVL.calm + '">Топливо вдоль маршрута в целом доступно (оценка).</div>');
    }
  }
  function clearTrip() {
    AZS_ROUTE.line = null; AZS_ROUTE.cities = [];
    if (L_az.route) L_az.route.clearLayers();
    var el = document.getElementById("azsTrip"); if (el) el.innerHTML = "";
    renderAzsComments(null);
    Array.prototype.forEach.call(document.querySelectorAll("#azsPresets button"), function (b) { b.classList.remove("active"); });
  }
```

- [ ] **Step 3: Пресет-коридоры**

Заменить `function renderAzsPresets() {}`:
```javascript
  function renderAzsPresets() {
    var el = document.getElementById("azsPresets"); if (!el) return;
    var routes = (S.azsRoutes && S.azsRoutes.routes) || [];
    el.innerHTML = "";
    routes.forEach(function (r) {
      var b = document.createElement("button");
      b.textContent = r.name;
      b.addEventListener("click", function () {
        Array.prototype.forEach.call(el.querySelectorAll("button"), function (x) { x.classList.remove("active"); });
        b.classList.add("active");
        applyTrip(r.waypoints, r.cities || []);
      });
      el.appendChild(b);
    });
  }
```

- [ ] **Step 4: Кастомный A→B (Nominatim геокод + OSRM маршрут)**

Заменить `function bindAzsRouteUI() {}`:
```javascript
  function geocode(q) {
    var url = "https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=ru,ua&accept-language=ru&q=" + encodeURIComponent(q);
    return fetch(url, { headers: { "Accept": "application/json" } }).then(function (r) { return r.json(); }).then(function (a) {
      if (!a || !a.length) throw new Error("not found: " + q);
      return [parseFloat(a[0].lat), parseFloat(a[0].lon)];
    });
  }
  function osrmRoute(from, to) {
    var url = "https://router.project-osrm.org/route/v1/driving/" + from[1] + "," + from[0] + ";" + to[1] + "," + to[0] + "?overview=full&geometries=geojson";
    return fetch(url).then(function (r) { return r.json(); }).then(function (j) {
      if (!j.routes || !j.routes.length) throw new Error("no route");
      return j.routes[0].geometry.coordinates.map(function (c) { return [c[1], c[0]]; }); // [lon,lat]->[lat,lon]
    });
  }
  function bindAzsRouteUI() {
    var btn = document.getElementById("azsRouteBtn"), clr = document.getElementById("azsRouteClear");
    var fromEl = document.getElementById("azsFrom"), toEl = document.getElementById("azsTo");
    var tripEl = document.getElementById("azsTrip");
    if (clr) clr.addEventListener("click", clearTrip);
    if (btn) btn.addEventListener("click", function () {
      var f = (fromEl.value || "").trim(), t = (toEl.value || "").trim();
      if (!f || !t) { if (tripEl) tripEl.innerHTML = '<div class="tr-row" style="color:' + AZS_LVL.severe + '">Укажите оба города.</div>'; return; }
      if (tripEl) tripEl.innerHTML = '<div class="tr-row">Строю маршрут…</div>';
      Array.prototype.forEach.call(document.querySelectorAll("#azsPresets button"), function (b) { b.classList.remove("active"); });
      Promise.all([geocode(f), geocode(t)]).then(function (pts) {
        return osrmRoute(pts[0], pts[1]).then(function (line) {
          applyTrip(line, [f, t]);
        });
      }).catch(function (e) {
        if (tripEl) tripEl.innerHTML = '<div class="tr-row" style="color:' + AZS_LVL.critical + '">Не удалось построить маршрут (' + (e.message || "ошибка") + '). Попробуйте пресет-коридор.</div>';
      });
    });
  }
```

- [ ] **Step 5: Браузер-проверка пресета**

- preview_eval: `document.querySelector('[data-view=azs]').click()`
- preview_eval: `document.querySelector('#azsPresets button').click()`
- preview_snapshot → Expected: синяя линия маршрута на карте; в панели «Вдоль маршрута: N АЗС» + чипы 🟢🟡🔴⚪; лента комментариев сузилась на города коридора.
- preview_console_logs → без ошибок.

- [ ] **Step 6: Браузер-проверка кастомного A→B**

- preview_fill `#azsFrom` = «Ростов-на-Дону», `#azsTo` = «Краснодар»
- preview_click `#azsRouteBtn` → подождать ~2–3 с
- preview_snapshot → Expected: маршрут построен по дорогам (OSRM), сводка обновилась.
- preview_console_logs → без ошибок (допустимы предупреждения CORS только если запрос упал — тогда проверить, что показан фолбэк-текст).

- [ ] **Step 7: Commit**

```bash
git -C ~/Documents/npz-tactical-map add app.js
git -C ~/Documents/npz-tactical-map commit -m "feat(azs): trip map — preset corridors + custom A→B (Nominatim+OSRM) + along-route summary"
```

---

## Task 9: Агент-рутина + источники

**Files:**
- Modify: `agents/update-prompt-availability.md`
- Modify: `agents/update-prompt-voices.md`
- Modify: `sources.html`

- [ ] **Step 1: Расширить availability-промпт**

Прочитать `agents/update-prompt-availability.md`, затем добавить в раздел требований к каждому объекту `networks[]` инструкцию (дописать пунктом):
```markdown
- Для каждой сети ОБЯЗАТЕЛЬНО проставляй поле `level` из шкалы: `calm` (штатно) / `strained` (перебои) / `limited` (лимиты/талоны) / `severe` (острый дефицит) / `critical` (сухо). Это поле красит точки заправок этой сети на вкладке АЗС (зелёный→красный). Если данных нет — поставь `level` равным общему `level` региона.
- Покрытие регионов приоритетно: Центральный ФО (Москва, МО, Воронеж, Белгород, Тула, Рязань, Липецк), Южный ФО (Краснодарский край, Ростовская, Волгоградская, Астраханская), Ставропольский край, Республика Крым, Севастополь.
```

- [ ] **Step 2: Расширить voices-промпт**

Прочитать `agents/update-prompt-voices.md`, дописать:
```markdown
- Для каждого отзыва ОБЯЗАТЕЛЬНО заполняй `city`, `lat`, `lon` (координаты центра города) — отзывы привязываются к точкам на вкладке АЗС и фильтруются по маршруту поездки.
- Приоритет городов: трасса М4 «Дон» (Москва, Воронеж, Ростов-на-Дону, Краснодар) и Крым (Симферополь, Севастополь, Керчь, Феодосия).
```

- [ ] **Step 3: Источники/атрибуция**

В `sources.html` добавить (в подходящий список источников) пункты:
```html
<li><b>OpenStreetMap</b> (Overpass API) — расположение и бренды заправок на вкладке АЗС. Данные © участники OpenStreetMap, лицензия ODbL.</li>
<li><b>OSRM</b> (router.project-osrm.org) и <b>Nominatim</b> (nominatim.openstreetmap.org) — построение маршрута и геокодинг в «карте поездки». Бесплатные сервисы OSM.</li>
<li><b>Важно:</b> наличие топлива на вкладке АЗС — оценка по статусу сети в регионе из открытых источников, НЕ данные по конкретной колонке.</li>
```

- [ ] **Step 4: Commit**

```bash
git -C ~/Documents/npz-tactical-map add agents/update-prompt-availability.md agents/update-prompt-voices.md sources.html
git -C ~/Documents/npz-tactical-map commit -m "feat(azs): agent prompts (networks[].level + city geo) + sources attribution"
```

---

## Task 10: Валидатор, полная браузер-верификация, деплой, память

**Files:**
- Create: `agents/validate-azs.py`
- Modify: `agents/run-agent.sh` (добавить вызов валидатора — опционально, если структура позволяет)

- [ ] **Step 1: Запустить локальный preview-сервер (если ещё не)**

preview_start в каталоге `~/Documents/npz-tactical-map` (статический сервер). Сохранить URL.

- [ ] **Step 2: Валидатор схемы**

Create `agents/validate-azs.py`:
```python
#!/usr/bin/env python3
import json, sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def load(n): return json.load(open(os.path.join(ROOT, "data", n), encoding="utf-8"))
ok = True
def err(m):
    global ok; ok = False; print("FAIL:", m)
st = load("azs-stations.json")
if st.get("meta", {}).get("count", 0) < 100: err("azs-stations: count < 100")
for s in st["stations"][:99999]:
    if not isinstance(s.get("lat"), (int, float)) or not isinstance(s.get("lon"), (int, float)): err("station bad coords: " + str(s.get("id"))); break
    if not s.get("region"): err("station no region: " + str(s.get("id"))); break
    if not s.get("brand"): err("station no brand: " + str(s.get("id"))); break
rt = load("azs-routes.json")
if len(rt.get("routes", [])) < 1: err("routes empty")
for r in rt["routes"]:
    if len(r.get("waypoints", [])) < 2: err("route <2 wp: " + r.get("id", "?"))
print("OK azs data valid" if ok else "INVALID")
sys.exit(0 if ok else 1)
```
Run:
```bash
cd ~/Documents/npz-tactical-map && python3 agents/validate-azs.py
```
Expected: `OK azs data valid`, exit 0.

- [ ] **Step 3: Полный прогон вкладки в браузере**

- preview_eval: `window.location.reload()` → подождать загрузку.
- preview_eval: `document.querySelector('[data-view=azs]').click()`
- preview_console_logs → Expected: НЕТ ошибок (errors=0).
- preview_snapshot → Expected: карта с кластерами, панель фильтров+поездки, легенда, лента комментариев.
- preview_eval проверка джойна (есть и зелёные, и красные):
```javascript
(function(){var s=document.querySelectorAll('#mapAzs .azs-divicon svg circle[fill^="#"]');var set={};s.forEach(c=>set[c.getAttribute('fill')]=1);return Object.keys(set);})()
```
Expected: массив с несколькими цветами из палитры (минимум 2 разных).
- preview_click пресет → маршрут + сводка.
- preview_resize мобильный (например 390×800) → preview_snapshot → панель не ломает карту.

- [ ] **Step 4: Скриншот-пруф пользователю**

preview_screenshot вкладки АЗС (десктоп) + один со включённым маршрутом. Приложить в ответе.

- [ ] **Step 5: Push на прод**

```bash
git -C ~/Documents/npz-tactical-map add -A
git -C ~/Documents/npz-tactical-map commit -m "feat(azs): validator + verification pass" || echo "nothing to commit"
git -C ~/Documents/npz-tactical-map push origin main
```
Затем подождать ~1–2 мин (raw-CDN кэш 5 мин) и проверить https://npz-tactical-map.vercel.app/ → вкладка ⛽ АЗС.

- [ ] **Step 6: Обновить auto-memory**

Дописать в `~/.claude/projects/-Users-sergeyrama-Documents---------/memory/project_npz_tactical_map.md` строку про новую вкладку АЗС (карта поездки, OSM-станции × живой статус, OSRM). Обновить число агентов/вкладок если нужно.

---

## Self-Review (выполнено автором плана)

**1. Spec coverage:**
- Отдельная карта-вкладка → Task 3,5 ✅
- Реальные заправки из OSM (Центр+Юг+Крым) → Task 1 ✅
- green→red наличие → Task 6 (`stationLevel`+`AZS_LVL`) ✅
- Комментарии людей (карта+лента+попап) → Task 6 (попап) + Task 7 ✅
- Карта поездки: пресеты + кастом A→B OSRM + сводка → Task 8 ✅
- Дёшево для агента (статичный stations + живой availability/voices) → Task 1 (статик) + Task 9 (промпты) ✅
- Только бесплатные API → Overpass/OSRM/Nominatim, без ключей ✅
- Честные дисклеймеры → Task 3 (azsNote), Task 6 (попап), Task 9 (sources) ✅

**2. Placeholder scan:** код приведён полностью в каждом шаге; «заглушки» в Task 5 намеренные и заменяются в Task 6–8 (явно указано). ✅

**3. Type consistency:**
- `L_az.cluster/.comments/.route` заводятся в Task 5 Step 5, используются в Task 6/7/8 ✅
- `AZS_LVL`/`AZS_LBL` — существующие (app.js:694-695), переиспользуются ✅
- `normRegion` — существующая (app.js:393) ✅
- `azsState`, `AZS_ROUTE`, `stationLevel`, `azsRegionEntry`, `recomputeTripStations`, `applyTrip`, `clearTrip` — определены до использования ✅
- `renderAzsStations/Comments/Presets/BrandFilter/Legend`, `bindAzsRouteUI` — заглушки (Task 5) → реализация (Task 6–8), сигнатуры совпадают ✅
- `setBaseTiles` — Task 5 Step 6 проверяет существование общего хелпера перед добавлением ✅

**Open risk:** объём OSM может потребовать отсечения `other` (Task 1 Step 5 это покрывает); ключ имени региона в geojson проверяется (Task 1 Step 2).
