#!/usr/bin/env python3
"""Сборщик рядов /lab/world (без LLM). Пишет data/world/series.json.

Запуск:  python3 agents/world/collect.py [--only <id-или-префикс>] [--dry]
Только stdlib; openpyxl (EU Oil Bulletin) и xlrd (GPR .xls) — по возможности.
xlrd ищется также в agents/world/_vendor (pip install --target agents/world/_vendor xlrd).

Правила (docs/world-lab-spec.md): ошибка источника -> series[id].error, прежние value/history
сохраняются; новые точки сливаются с историей по дате; stale по порогу STALE_DAYS.
Файл пишется атомарно (tmp + os.replace), невалидный JSON невозможен.
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "data", "world", "series.json")
sys.path.insert(0, os.path.join(HERE, "_vendor"))

# FRED молча вешает запросы с чужим UA (проверено 2026-10-11): в UA должен быть префикс Python-urllib/ или curl/.
UA = "Python-urllib/3.14 (npz-tactical-map world-lab)"
TODAY = dt.date.today()


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get(url, timeout=40, retries=4):
    """GET с экспоненциальным backoff на 429/5xx и сетевые сбои. Возвращает bytes."""
    delay = 2.0
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        if i < retries:
            time.sleep(delay)
            delay *= 2
    raise last


def get_json(url, **kw):
    return json.loads(get(url, **kw).decode("utf-8", "replace"))


def iso(d):
    return d.isoformat()


def parse_day(s):
    s = str(s).strip()
    if len(s) == 8 and s.isdigit():
        return dt.date(int(s[:4]), int(s[4:6]), int(s[6:]))
    return dt.date.fromisoformat(s[:10])


def cutoff(years):
    return iso(TODAY - dt.timedelta(days=int(365.25 * years)))


# ---------------------------------------------------------------- источники
def fred(sid, years=5.2):
    def run():
        # cosd обязателен: запрос полной истории FRED часто виснет (проверено 2026-10-11)
        txt = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={cutoff(years)}", timeout=30, retries=3).decode()
        rows = list(csv.reader(io.StringIO(txt)))[1:]
        out = []
        for r in rows:
            if len(r) < 2 or r[1] in ("", "."):
                continue
            try:
                out.append([r[0], float(r[1])])
            except ValueError:
                pass
        return out
    return run


PW_URL = ("https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
          "Daily_Chokepoints_Data/FeatureServer/0/query")


def portwatch(portname, days=800):
    def run():
        since = TODAY - dt.timedelta(days=days)
        out, offset = {}, 0
        while True:
            q = {"where": f"portname='{portname}'", "outFields": "date,portname,n_tanker,n_total",
                 "orderByFields": "date DESC", "resultRecordCount": 2000,
                 "resultOffset": offset, "f": "json"}
            d = get_json(PW_URL + "?" + urllib.parse.urlencode(q))
            if "error" in d:
                raise RuntimeError(f"ArcGIS: {d['error']}")
            feats = d.get("features", [])
            if not feats:
                break
            stop = False
            for f in feats:
                a = f["attributes"]
                v = a.get("date")
                if isinstance(v, (int, float)):
                    day = dt.datetime.fromtimestamp(v / 1000, dt.timezone.utc).date()
                else:
                    day = parse_day(v)
                if day < since:
                    stop = True
                    continue
                if a.get("n_tanker") is not None:
                    out[iso(day)] = float(a["n_tanker"])
            if stop or not d.get("exceededTransferLimit"):
                break
            offset += len(feats)
        if not out:
            raise RuntimeError(f"PortWatch: нет данных для {portname}")
        return sorted([k, v] for k, v in out.items())
    return run


def gpr_daily():
    try:
        import xlrd
    except ImportError:
        raise RuntimeError("нет модуля xlrd (pip install --target agents/world/_vendor xlrd)")
    raw = get("https://www.matteoiacoviello.com/gpr_files/data_gpr_daily_recent.xls", timeout=90)
    wb = xlrd.open_workbook(file_contents=raw)
    sh = wb.sheet_by_index(0)
    head = [str(sh.cell_value(0, c)).strip().upper() for c in range(sh.ncols)]
    ci_d, ci_v = head.index("DAY"), head.index("GPRD")
    since = cutoff(5)
    out = []
    for r in range(1, sh.nrows):
        d, v = sh.cell_value(r, ci_d), sh.cell_value(r, ci_v)
        if v in ("", None):
            continue
        try:
            day = iso(parse_day(str(int(d)) if isinstance(d, float) else d))
        except Exception:
            continue
        if day >= since:
            out.append([day, round(float(v), 3)])
    return out


EU_URL = ("https://energy.ec.europa.eu/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en"
          "?filename=Weekly_Oil_Bulletin_Prices_History_maticni_4web.xlsx")
_eu_cache = {}


def eu_bulletin(col):
    """Лист «Prices with taxes», строки CTR='EU_' (среднее ЕС); col: 2=Euro-super 95, 3=дизель (€/1000 л)."""
    def run():
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError("нет модуля openpyxl")
        if "wb" not in _eu_cache:
            _eu_cache["wb"] = get(EU_URL, timeout=120)
        wb = openpyxl.load_workbook(io.BytesIO(_eu_cache["wb"]), read_only=True, data_only=True)
        ws = wb["Prices with taxes"]
        since = cutoff(5)
        out = {}
        for row in ws.iter_rows(min_row=1, values_only=True):
            if len(row) <= col or row[1] != "EU_" or not isinstance(row[0], dt.datetime):
                continue
            v = row[col]
            day = iso(row[0].date())
            if isinstance(v, (int, float)) and day >= since:
                out[day] = round(float(v), 2)
        if not out:
            raise RuntimeError("EU Oil Bulletin: строки EU_ не найдены (структура листа изменилась?)")
        return sorted([k, v] for k, v in out.items())
    return run


IEA_BASE = "https://api.iea.org/netimports"
IEA_ROWS = {"europe": "Total IEA Europe", "pacific": "Total IEA Asia Pacific",
            "north_america": "Total IEA North America"}
_iea_cache = {}


def iea_months(months_back=60):
    """Загружает недостающие месяцы IEA один раз на запуск: {yyyymm: {name: days|None}}."""
    if "data" in _iea_cache:
        return _iea_cache["data"]
    latest = get_json(IEA_BASE + "/latest")
    y, m = int(latest["year"]), int(latest["month"])
    have = _iea_cache.get("have", set())
    res = {}
    for i in range(months_back):
        yy, mm = y, m - i
        while mm <= 0:
            mm += 12
            yy -= 1
        key = yy * 100 + mm
        if key in have and i >= 2:  # два свежих месяца всегда перекачиваем (ревизии)
            continue
        try:
            rows = get_json(f"{IEA_BASE}/monthly?year={yy}&month={mm:02d}")
        except Exception as e:  # отдельный месяц не роняет ряд
            log(f"  IEA {key}: {e}")
            continue
        time.sleep(0.2)
        cur = {}
        for r in rows if isinstance(rows, list) else []:
            try:
                n = r.get("countryName", "")
                if n in IEA_ROWS.values():
                    t = str(r.get("total", "")).strip()
                    cur[n] = float(t) if t.replace(".", "", 1).isdigit() else None
            except Exception:
                pass
        res[key] = cur
    _iea_cache["data"] = res
    return res


def iea_stocks(region):
    def run():
        name = IEA_ROWS[region]
        out = []
        for key, cur in sorted(iea_months().items()):
            v = cur.get(name)
            if v is None:
                continue
            yy, mm = divmod(key, 100)
            # метка — последний день месяца
            nxt = dt.date(yy + (mm == 12), mm % 12 + 1, 1)
            out.append([iso(nxt - dt.timedelta(days=1)), v])
        if not out:
            raise RuntimeError(f"IEA: для «{name}» нет числовых дней запасов "
                               "(для Северной Америки IEA пишет 'Net Exporter')")
        return out
    return run


def eia(series_id, scale=1000.0):
    """EIA API v2, ключ DEMO_KEY (лимитирован; при 429 backoff). Тыс. барр. -> млн барр."""
    def run():
        q = [("api_key", "DEMO_KEY"), ("frequency", "weekly"), ("data[0]", "value"),
             ("facets[series][]", series_id), ("sort[0][column]", "period"),
             ("sort[0][direction]", "desc"), ("length", 300)]
        d = get_json("https://api.eia.gov/v2/petroleum/stoc/wstk/data/?" + urllib.parse.urlencode(q))
        rows = d["response"]["data"]
        out = [[r["period"], round(float(r["value"]) / scale, 3)] for r in rows if r.get("value") not in (None, "")]
        if not out:
            raise RuntimeError("EIA: пустой ответ")
        return sorted(out)
    return run


# GDELT: регионы -> страны-источники (коды sourcecountry — FIPS 10-4, как принимает DOC 2.0).
# Берём 4 крупнейших англоязычно/широко представленных СМИ-рынка региона; запрос шире не делаем,
# чтобы не размывать сигнал. Значение — доля (%) всех мониторимых статей за день (mode=timelinevol).
GDELT_REGIONS = {
    "europe": ["UK", "GM", "FR", "PL"],
    "russia_cis": ["RS", "KZ", "AJ", "UZ"],
    "middle_east": ["IS", "SA", "EG", "TU"],
    "east_asia": ["JA", "KS", "AS", "ID"],
    "south_asia": ["IN", "PK", "BG", "CE"],
    "north_america": ["US", "CA", "MX"],
    "latin_america": ["BR", "AR", "CO", "CI"],
    "africa": ["NI", "SF", "KE", "GH"],
}
GDELT_TERMS = '("fuel shortage" OR "diesel shortage" OR "petrol shortage")'
_gdelt_last = [0.0]


def gdelt(region):
    def run():
        wait = 10.0 - (time.time() - _gdelt_last[0])
        if wait > 0:
            time.sleep(wait)
        cs = " OR ".join(f"sourcecountry:{c}" for c in GDELT_REGIONS[region])
        qs = urllib.parse.urlencode({"query": f"{GDELT_TERMS} ({cs})", "mode": "timelinevol",
                                     "format": "json", "timespan": "90d"})
        url = "https://api.gdeltproject.org/api/v2/doc/doc?" + qs
        d = None
        for attempt in range(5):
            _gdelt_last[0] = time.time()
            try:
                raw = get(url, retries=1).decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 4:
                    raise
                time.sleep(20 * (attempt + 1))
                continue
            try:
                d = json.loads(raw)
                break
            except ValueError:  # текстовая «please limit requests» / ошибка парсинга запроса
                if attempt == 4:
                    raise RuntimeError("GDELT: не JSON: " + raw[:120].replace("\n", " "))
                time.sleep(8 * (attempt + 1))
        tl = d.get("timeline") or []
        if not tl or not tl[0].get("data"):
            raise RuntimeError("GDELT: пустой timeline")
        out = {}
        for p in tl[0]["data"]:
            out[iso(parse_day(p["date"][:8]))] = round(float(p["value"]), 5)
        return sorted([k, v] for k, v in out.items())
    return run


# --------------------------------------------------------------- реестр
def spec(id_, label, unit, source, url, license_, freq, fn, keep_years, stale_days, agg=None, note=None,
         compact=False):
    return dict(id=id_, label=label, unit=unit, source=source, url=url, license=license_, freq=freq,
                fn=fn, keep_years=keep_years, stale_days=stale_days, agg=agg, note=note, compact=compact)


def build_registry():
    R = []
    fred_url = "https://fred.stlouisfed.org/series/"
    for sid, i, label, unit in [
        ("DCOILBRENTEU", "brent_spot", "Нефть Brent, спот", "USD/барр."),
        ("DCOILWTICO", "wti_spot", "Нефть WTI, спот", "USD/барр."),
        ("DDFUELNYH", "ulsd_nyh", "Дизель ULSD, Нью-Йорк (NYH)", "USD/гал."),
        ("DGASNYH", "gasoline_nyh", "Бензин NYH", "USD/гал."),
    ]:
        R.append(spec(i, label, unit, "FRED / EIA", fred_url + sid, "Public domain (U.S. Gov / EIA)",
                      "daily", fred(sid, 10.2), 10.2, 10, compact=True))  # лаг FRED/EIA ~5-7 дн.: порог 6 выбивал цены из индекса
    R.append(spec("diesel_retail_us", "Дизель, розница США", "USD/гал.", "FRED / EIA",
                  fred_url + "GASDESW", "Public domain (U.S. Gov / EIA)", "weekly", fred("GASDESW"), 5, 15))
    R.append(spec("us_crude_stocks", "Запасы сырой нефти США (без SPR)", "млн барр.", "EIA API v2",
                  "https://www.eia.gov/dnav/pet/pet_stoc_wstk_dcu_nus_w.htm", "Public domain (U.S. Gov / EIA)",
                  "weekly", eia("WCESTUS1"), 5, 15))
    R.append(spec("us_distillate_stocks", "Запасы дистиллятов США", "млн барр.", "EIA API v2",
                  "https://www.eia.gov/dnav/pet/pet_stoc_wstk_dcu_nus_w.htm", "Public domain (U.S. Gov / EIA)",
                  "weekly", eia("WDISTUS1"), 5, 15))
    eu_url = "https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en"
    R.append(spec("eu_diesel_retail", "Дизель, розница ЕС (среднее, с налогами)", "EUR/1000 л", "EU Weekly Oil Bulletin",
                  eu_url, "CC BY 4.0 (European Commission)", "weekly", eu_bulletin(3), 5, 21))
    R.append(spec("eu_gasoline_retail", "Бензин Euro-super 95, розница ЕС (среднее, с налогами)", "EUR/1000 л",
                  "EU Weekly Oil Bulletin", eu_url, "CC BY 4.0 (European Commission)", "weekly", eu_bulletin(2), 5, 21))
    R.append(spec("gpr_daily", "Индекс геополитического риска (GPR, дневной)", "индекс", "Caldara-Iacoviello GPR",
                  "https://www.matteoiacoviello.com/gpr.htm", "Свободное использование со ссылкой на Caldara & Iacoviello (AER 2022)",
                  "daily", gpr_daily, 5, 10))
    cps = [("hormuz", "Strait of Hormuz", "Ормузский пролив"),
           ("bab_el_mandeb", "Bab el-Mandeb Strait", "Баб-эль-Мандебский пролив"),
           ("suez", "Suez Canal", "Суэцкий канал"),
           ("malacca", "Malacca Strait", "Малаккский пролив"),
           ("bosporus", "Bosporus Strait", "Босфор"),
           ("cape", "Cape of Good Hope", "Мыс Доброй Надежды"),
           # v0.2.1: проливы для Латинской Америки и Африки (PortWatch, тот же слой, CC BY 4.0)
           ("panama", "Panama Canal", "Панамский канал"),
           ("yucatan", "Yucatan Channel", "Юкатанский пролив"),
           ("gibraltar", "Gibraltar Strait", "Гибралтарский пролив")]
    for cid, pn, ru in cps:
        R.append(spec(f"chokepoint_{cid}_tankers", f"{ru}: танкеры в сутки", "судов/сут.", "IMF PortWatch",
                      "https://portwatch.imf.org/", "CC BY 4.0 (IMF PortWatch / Oxford)", "daily",
                      portwatch(pn), 2.2, 14, note=f"portname={pn}"))
    for reg in ("europe", "pacific"):  # Северная Америка у IEA — Net Exporter, дней запасов нет
        R.append(spec(f"iea_stocks_days_{reg}", f"Запасы нефти и продуктов, дни чистого импорта (IEA {reg})",
                      "дней", "IEA Net Imports", "https://www.iea.org/data-and-statistics/data-tools/oil-stocks-of-iea-countries",
                      "IEA, публичный API (условия: iea.org/terms)", "monthly", iea_stocks(reg), 5, 150))
    for reg in GDELT_REGIONS:
        R.append(spec(f"gdelt_shortage_{reg}", f"Новости о дефиците топлива: {reg}", "% статей", "GDELT DOC 2.0",
                      "https://www.gdeltproject.org/", "GDELT: свободное использование со ссылкой",
                      "daily", gdelt(reg), 5, 7, note="страны: " + ",".join(GDELT_REGIONS[reg])))
    return R


# ------------------------------------------------------------------ main
def merge_history(old, new, keep_years):
    d = {k: v for k, v in (old or [])}
    d.update({k: v for k, v in new})
    c = cutoff(keep_years)
    return [[k, d[k]] for k in sorted(d) if k >= c]


def compact_weekly(hist, keep_daily_years=1.0):
    """Точки старше keep_daily_years -> недельные средние (метка = понедельник ISO-недели). Свежее — как есть."""
    c = cutoff(keep_daily_years)
    old, recent, weeks = [], [], {}
    for d, v in hist:
        if d >= c:
            recent.append([d, v])
        else:
            day = dt.date.fromisoformat(d)
            weeks.setdefault(iso(day - dt.timedelta(days=day.weekday())), []).append(v)
    for k in sorted(weeks):
        old.append([k, round(sum(weeks[k]) / len(weeks[k]), 4)])
    return old + recent


def is_stale(as_of, stale_days):
    try:
        return (TODAY - dt.date.fromisoformat(as_of)).days > stale_days
    except Exception:
        return True


def last_value(sp, hist):
    """value: для PortWatch/GDELT — как есть (последняя точка); сглаживание делает index.py."""
    return hist[-1][1], hist[-1][0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="id ряда или префикс (например chokepoint_ или brent_spot)")
    ap.add_argument("--dry", action="store_true", help="не писать файл, только напечатать сводку")
    args = ap.parse_args()

    try:
        prev = json.load(open(OUT, encoding="utf-8")).get("series", {})
    except Exception:
        prev = {}
    series = dict(prev)
    reg = build_registry()
    # IEA: известные месяцы не перекачиваем
    have = set()
    for k in ("europe", "pacific", "north_america"):
        for d, _ in prev.get(f"iea_stocks_days_{k}", {}).get("history", []):
            have.add(int(d[:4]) * 100 + int(d[5:7]))
    # месяцы, где ряд вообще пуст (North America), всё равно качаем — набор общий, считаем «известным»
    # только если есть у Европы.
    _iea_cache["have"] = {m for m in have if m in {int(d[:4]) * 100 + int(d[5:7])
                                                    for d, _ in prev.get("iea_stocks_days_europe", {}).get("history", [])}}

    ok = bad = 0
    todo = [sp for sp in reg if not args.only or sp["id"].startswith(args.only)]
    retried = set()
    i = 0
    while i < len(todo):
        sp = todo[i]
        i += 1
        sid = sp["id"]
        old = prev.get(sid, {})
        ent = {"label": sp["label"], "unit": sp["unit"], "source": sp["source"], "url": sp["url"],
               "license": sp["license"], "freq": sp["freq"], "stale_days": sp["stale_days"]}
        if sp.get("note"):
            ent["note"] = sp["note"]
        t0 = time.time()
        try:
            fn = sp["fn"]
            pts = fn() if sid != "gpr_daily" else fn()
            if sp.get("compact"):  # старое хранится недельными средними; полная история приходит из источника
                old_recent = [p for p in old.get("history", []) if p[0] >= cutoff(1.0)]
                hist = compact_weekly(merge_history(old_recent, pts, sp["keep_years"]))
            else:
                hist = merge_history(old.get("history"), pts, sp["keep_years"])
            if not hist:
                raise RuntimeError("пустой ряд после слияния")
            v, as_of = last_value(sp, hist)
            ent.update(as_of=as_of, value=v, error=None, history=hist)
            ent["stale"] = is_stale(as_of, sp["stale_days"])
            ok += 1
            log(f"OK   {sid:38s} {as_of} {v} ({len(hist)} pts, {time.time()-t0:.1f}s)")
        except Exception as e:
            bad += 1
            msg = f"{type(e).__name__}: {e}"[:300]
            ent.update(error=msg, as_of=old.get("as_of"), value=old.get("value"),
                       history=old.get("history", []))
            ent["stale"] = is_stale(old["as_of"], sp["stale_days"]) if old.get("as_of") else True
            log(f"FAIL {sid:38s} {msg}")
            # GDELT: 429 — лимит по IP; второй проход в конце, после длинной паузы (один раз на ряд)
            if sid.startswith("gdelt_") and sid not in retried and "429" in msg:
                retried.add(sid)
                todo.append(sp)
                if len(retried) == 1:
                    log("  GDELT 429: пауза 90 с перед повторным проходом")
                    time.sleep(90)
        else:
            if sid in retried:
                bad -= 1  # повтор удался: ранний FAIL не считаем
        series[sid] = ent

    known = {sp["id"] for sp in reg}
    for k in [k for k in series if k not in known]:  # ряды, убранные из реестра
        del series[k]
    doc = {"generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "series": series}
    if args.dry:
        log(f"dry: ok={ok} fail={bad}")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    json.load(open(tmp, encoding="utf-8"))  # проверка валидности до замены
    os.replace(tmp, OUT)
    log(f"записано {OUT}: ok={ok} fail={bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
